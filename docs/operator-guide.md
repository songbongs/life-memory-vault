# Life Memory Vault — 운영자 가이드

이 문서는 시스템을 **설치·운영·점검·복구**하는 사람을 위한 것입니다. 일상 사용법은 [사용자 가이드](user-guide.md)를 보세요.

설계 의도/이력은 [project-handoff.md](project-handoff.md), 개선 작업 전체 기록은 [improvement-plan.md](improvement-plan.md)에 있습니다.

---

## 1. 시스템 구성 (한눈에)

```
[캡처]  텔레그램 봇 ─→ telegram_collector.py ──┐
        CLI/에이전트 ───────────────────────────┤
                                               ▼
                                    mem.py save → 00_Inbox/Raw (원본, 불변)
                                               │
              ┌────────────────────────────────┼─────────────────────────────────────┐
              ▼ (결정론·무료)                   │                                     ▼ (AI·구독)
        mem.py lint                            │                    process_ai_jobs.py → claude/codex
        (분류·중복제거·날짜보강)                 │                    (lint/repair/seek/enrich/media-enrich)
        mem.py enrich                          │                                     │
        (URL 추출·유튜브자막·이미지저장)          │                                     │
        mem.py extract-media                   │                                     │
        (이미지 OCR·PDF 텍스트 추출)             │                                     │
              │                                │                                     │
              └──────────────────────────────→ 00_Inbox/Processed/*.json (마커) ←────┘
                                               00_Inbox/Review (애매한 건)
                                                               │
                               review resolve → rules.py (학습) → classify 자동분류
```

핵심 스크립트 (`scripts/`):

| 파일 | 역할 |
|---|---|
| `mem.py` | 메인 CLI: save / lint / seek / digest / doctor / init / review / enrich / extract-media / dedup-markers / reclassify / prune-orphans |
| `enrich.py` | URL 내용 추출 (trafilatura + yt-dlp 유튜브 자막) + 이미지 저장 |
| `extract_media.py` | 이미지 OCR(tesseract) + PDF 텍스트(pdfplumber) 추출 → 23:00 AI 요약 큐잉 |
| `rules.py` | 학습 규칙 저장소 (add-decision / list / active / remove) |
| `jobs.py` | 작업 큐 (텔레그램 명령 → JSONL 큐) |
| `telegram_collector.py` | 텔레그램 수집기(폴링→Raw 저장) |
| `process_jobs.py` | 결정론적 작업 처리 브리지 (digest/doctor 자동 회신 + 주간 회고 발송 + 적체 알림) |
| `process_ai_jobs.py` | AI 작업(lint/repair/seek/enrich/media-enrich)을 헤드리스 에이전트로 처리 |
| `scheduled_lint.py` | 정기 lint 트리거 → enrich 추출 → extract-media 텍스트 추출 |
| `memory_admin.py` | 로컬 관리 대시보드 (수집기 start/stop) |
| `install-*.sh` | launchd/스킬 설치 스크립트 |

---

## 2. 설정 파일

### `memory-config.json` (로컬 전용, git 제외)

`memory-config.example.json`을 복사해 작성. 주요 키:

- `memoryVault.vaultPath` — Obsidian 볼트 절대경로 (★필수)
- `telegram.allowedUserIds` — **허용된 텔레그램 숫자 ID 목록**. **비어 있으면 전부 거부**(보안 기본값)하고 발신자에게 본인 ID를 안내.
- `agent.default` (기본 `claude`) / `agent.commands` — 헤드리스 에이전트 호출 템플릿(`{prompt}` 치환).
- `agent.aiJobTypes` — AI 에이전트가 처리하는 잡 타입 목록. 기본: `["lint","repair","seek","enrich","media-enrich"]`.
- `agent.modelByJobType.<agent>.<jobtype>` — **잡 타입별 모델**. process_ai_jobs.py가 값이 있으면 `--model <값>`을 붙이고, 빈 값/생략이면 에이전트 기본 모델. **claude는 별칭(`haiku`/`sonnet`/`opus`)을 쓰면 항상 그 계열 최신 모델로 해석**되어 신규 버전이 나와도 설정 변경 불필요. 현재: `default`·`lint`·`repair`·`seek`=sonnet; `enrich`·`media-enrich`=haiku(반복·정형). **매핑 없는 새 잡 타입은 claude의 `default`(=sonnet)으로 안전 처리**.
- `enrichment.{enabled, auto, maxCandidatesPerRun(=5), onDemandNoticeThreshold(=10), timeoutSeconds, maxExtractChars, imageMaxBytes, optOutTags, assetsSubdir, archivePages}` — URL enrich(트랙 A). `archivePages: true` + monolith 설치 시 페이지 전문 HTML 박제 활성.
- `mediaExtraction.{enabled, auto, maxPerRun(=3), enableOcr(=true), enablePdf(=true), enableAudio(=false)}` — 이미지 OCR·PDF 텍스트·음성 전사 설정. 음성은 현재 stub(기본 off).
- `learning.{enabled, promoteThreshold(=2), rulesPath, mirrorPath}` — 학습 루프
- `jobs.weeklyDigest.{enabled, intervalDays, hour}` — 주간 회고 자동 발송. 설정 시간(기본 9:00) 이후 + intervalDays 경과 시 캡처봇으로 1회 발송.

### `.env` (git 제외)

```
TELEGRAM_BOT_TOKEN=...   # @BotFather에서 발급
```

> 비밀값(`memory-config.json`, `.env`)은 `.gitignore`로 제외됩니다. 커밋 전 `git check-ignore memory-config.json .env`로 항상 확인.

### 선택 의존성

```bash
# URL 추출 (enrich)
python3 -m pip install --user --break-system-packages trafilatura

# PDF 텍스트 추출 (extract-media)
python3 -m pip install --user --break-system-packages pdfplumber

# 이미지 OCR (extract-media)
brew install tesseract tesseract-lang   # kor+eng 언어팩 포함

# 유튜브 자막 (enrich)
brew install yt-dlp

# 페이지 전문 박제 (enrich, 선택)
# brew install monolith   # 설치 후 config archivePages: true로 활성
```

- Homebrew python은 PEP 668로 일반 `pip install`을 막으므로 `--break-system-packages`가 필요하고, `--user`를 함께 줘 사용자 사이트에만 설치(시스템 python 보호).
- **미설치여도 안전**: `mem.py doctor`에서 상태 확인 가능. 기능만 비활성되고 다른 경로에 영향 없음.

---

## 3. 텔레그램 봇 운영

1. `@BotFather`에서 봇 생성 → 토큰을 `.env`의 `TELEGRAM_BOT_TOKEN`에 저장.
2. 본인 ID 확인: 수집기 실행 후 봇에 메시지 1회 전송 → "당신의 Telegram ID: N" 회신.
3. 그 N을 `memory-config.json`의 `telegram.allowedUserIds`에 추가.
4. 수집기 실행:
   ```bash
   python3 scripts/telegram_collector.py --me     # 봇 신원 확인
   python3 scripts/telegram_collector.py --once   # 1회 폴링
   python3 scripts/telegram_collector.py --loop   # 지속 폴링(보통 launchd 담당)
   ```

지원 명령(봇에게 전송, 한국어 별칭 가능):
- `/lint`(`/정리`) `/doctor`(`/점검`) `/repair`(`/수리`) `/seek`(`/검색`) `/digest`(`/통계`) `/status`(`/상태`) `/enrich`(`/웹요약`) `/help`(`/도움`)
- `/seek`·`/status`·`/help`는 **즉시** 회신; `/digest`·`/doctor`는 **~5분**; `/lint`·`/repair`·`/enrich`는 **23시 배치**
- 봇 메뉴 등록: `python3 scripts/set-telegram-menu.py --apply`

관리 대시보드(수집기 켜고 끄기):
```bash
python3 scripts/memory_admin.py   # → http://127.0.0.1:8765
```

---

## 4. 자동화 (launchd)

설치 스크립트가 `~/Library/LaunchAgents/`에 plist를 만들고 로드합니다.

| 설치 스크립트 | 레이블 | 주기 | 하는 일 |
|---|---|---|---|
| `install-mac-mini.sh` | `com.sangmin.life-memory-collector` | 상시(KeepAlive) | 텔레그램 수집기 |
| `install-launchd.sh` | `com.sangmin.life-memory-lint` | 매일 22:00 | `scheduled_lint.py`: lint → enrich(URL추출+유튜브자막) → extract-media(OCR/PDF) 순서로 실행. 각 단계 독립 — 이전 단계 실패가 다음 단계를 막지 않음 |
| `install-jobs-launchd.sh` | `com.sangmin.life-memory-jobs` | 5분마다 | `process_jobs.py`: digest/doctor 자동 처리 + **주간 회고 발송** + 적체 알림 |
| `install-ai-jobs-launchd.sh` | `com.sangmin.life-memory-ai` | 매일 23:00 | `process_ai_jobs.py`: AI 작업(lint/repair/seek/**enrich 한국어 요약**/**media-enrich 미디어 한국어 요약**)을 헤드리스 에이전트로 처리. **실패 시(예: Claude 로그아웃 401) 캡처봇으로 "재로그인 확인" 알림** — 작업 대상은 보존돼 재로그인 후 자동 재처리 |

설치/확인/제거:
```bash
bash scripts/install-jobs-launchd.sh
launchctl list | grep life-memory                 # 가운데 열=마지막 exit code (0 정상)
launchctl kickstart -k gui/$(id -u)/com.sangmin.life-memory-lint   # 수동 1회 실행
launchctl unload ~/Library/LaunchAgents/<레이블>.plist && rm ~/Library/LaunchAgents/<레이블>.plist
```

로그: `memory-state/collector-service.log`, `scheduled-lint.log`, `launchd-jobs.log`, `launchd-ai-jobs.log`.

### ⚠️ macOS TCC 함정 (중요)

`~/Documents` 는 macOS가 보호하는 폴더라, **launchd가 `/bin/bash <스크립트>`로 실행하면 권한 거부(exit 126)**로 실패합니다. 모든 launchd 작업은 **`python3`를 절대경로로 직접 실행**합니다. 새 launchd 작업을 만들 때 `/bin/bash` 패턴을 쓰지 마세요.

### Claude 로그인 유지 (23:00 배치)

Claude Code 채널(`@songbongs_CCC_bot`) 터미널은 **항상 로그인된 상태**를 유지해야 23:00 무인 배치가 작동합니다.
- 로그인이 풀리면 → 캡처봇으로 "⚠️ 예약 작업 실패" 알림이 옵니다.
- Claude Code 채널 터미널에서 재로그인 후 → 다음 23:00 배치가 자동으로 밀린 작업을 처리합니다.

---

## 5. AI 자율 처리

- `process_ai_jobs.py`가 pending 잡(lint/repair/seek/enrich/media-enrich)을 꺼내 **헤드리스 에이전트**를 호출, 각 프롬프트 파일에 따라 처리합니다.

  | 잡 타입 | 프롬프트 | 모델 |
  |---|---|---|
  | lint / repair / seek | `prompts/process-pending-jobs.md` | sonnet |
  | enrich | `prompts/ai-enrich.md` | haiku |
  | media-enrich | `prompts/ai-media-enrich.md` | haiku |

  ```bash
  python3 scripts/process_ai_jobs.py --dry-run    # 실행될 명령 미리보기(안전)
  python3 scripts/process_ai_jobs.py --once       # 실제 처리(사용량 소모 + 볼트 쓰기)
  ```

- **글로벌 스킬**: `bash scripts/install-global-skill.sh` → `~/.codex/skills/life-memory/`

### 학습 규칙 관리

```bash
python3 scripts/rules.py list           # 규칙(active/candidate/blocked)
python3 scripts/rules.py active         # 자동 적용 중인 규칙
python3 scripts/rules.py remove "키워드"  # 잘못 배운 규칙 취소
```
저장소: `90_System/Rules/learned-rules.json` + 사람용 미러 `Learned Rules.md`.

---

## 6. 운영 점검 루틴

```bash
launchctl list | grep life-memory               # 4개 작업 exit 0 확인
python3 scripts/mem.py doctor                   # 도구 설치 상태 (pdfplumber/tesseract/yt-dlp/monolith)
python3 scripts/mem.py digest                   # 통계 (enrichment·media_extraction 포함)
python3 scripts/jobs.py summary                 # 잡 큐 적체
python3 scripts/mem.py prune-orphans            # orphan/ghost 노트 점검 → --apply로 정리
tail -f memory-state/launchd-ai-jobs.log
python3 tests/run_all.py                        # 전체 테스트 (213건)
```

---

## 7. 재분류·정리 운영 커맨드

| 커맨드 | 용도 |
|---|---|
| `mem.py reclassify "경로" --type X` | 이미 분류된 노트를 올바른 분류로 이동 + 마커/링크 자동 업데이트 + 학습 기록 |
| `mem.py dedup-markers` | 중복 마커 정리 (같은 raw → duplicate_of 전환). `--dry-run`으로 먼저 확인 |
| `mem.py prune-orphans` | Google Drive 복원 등으로 되살아난 ghost 노트 탐지. `--apply`로 백업 후 삭제 (멱등) |
| `mem.py enrich --all` | 대기 중인 URL 전체 추출 (운영봇 온디맨드용) |
| `mem.py extract-media --all` | 대기 중인 이미지/PDF 전체 추출 |

표준 재분류 절차:
1. `mem.py reclassify "파일경로" --type <올바른타입>` — 미리보기 후 확인
2. 또는 운영 봇에 "이 메모 task야" → 자연어 처리

---

## 8. 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| 봇이 저장 안 함 | `allowedUserIds`에 내 ID 없음 → 봇에 메시지 보내 ID 확인 후 추가 |
| 매일 lint 실패(exit 126) | launchd가 `/bin/bash` 사용 → `python3` 직접 실행 plist로 재설치(§4 TCC) |
| `claude`/`codex` 못 찾음(launchd) | plist `EnvironmentVariables.PATH`에 homebrew bin 추가 필요 |
| 23:00 배치 실패 / 401 오류 | Claude Code 채널 로그인 풀림 → 캡처봇 알림 확인 → 터미널 재로그인. 작업 자동 재처리됨 |
| 구조화 노트 중복 | `dedup-markers --dry-run` → `--apply`로 정리 |
| 분류가 계속 틀림 | `review resolve --signal`로 2회 학습 → 자동화. 또는 `reclassify`로 즉시 수정 |
| 잘못 배운 규칙 | `rules.py remove "키워드"` |
| 지운 노트가 다시 살아남(유령) | 볼트가 **Google Drive 동기화**라 삭제가 ~30분 뒤 복원될 수 있음. `prune-orphans --apply`로 정리(멱등). Drive가 또 복원하면 재실행 |
| OCR 결과가 없음 | tesseract 미설치 (`doctor` 확인) / HEIC는 macOS sips로 자동 변환 시도 / 스캔 품질 낮은 이미지는 OCR 실패 가능 |
| PDF 텍스트가 없음 | pdfplumber 미설치 (`pip install pdfplumber`) / 이미지 기반 PDF(스캔본)는 OCR 필요 — 현재 unsupported |
| 음성 첨부 요약 없음 | 음성 전사는 현재 stub(기본 off). `memory-config.json`의 `mediaExtraction.enableAudio` 관련 whisper 통합 추후 예정 |
| 주간 회고가 오지 않음 | `jobs.weeklyDigest.enabled` 확인. `process_jobs.py` launchd(5분마다)가 실행 중인지 확인 |
| song→task 등 재분류 후 음악 폴더에 잔재 | `prune-orphans`가 source_raw로 역추적해 정리 |

---

## 9. 백업·복구

- **원본(Raw)** 이 진실의 원천입니다. 구조화 노트·마커·엔티티·MOC는 raw에서 재생성 가능.
- 재분류/정리 시 삭제 전 임시 디렉터리에 백업합니다(스크립트가 경로를 출력). 문제 시 복사해 되돌리세요.
- 볼트 자체는 Google Drive로 동기화되므로 클라우드 이력도 활용 가능.

---

## 10. 안전 원칙 (운영 시 항상 지킬 것)

- **Raw는 신성**: 원본 수정/삭제 금지. 정리는 복사본으로만.
- **민감 정보 기본 보호**: `#private`/`sensitivity: private`는 넓게 노출되는 위치로 이동 금지.
- **거부 우선(deny-by-default)**: 텔레그램은 등록된 사용자만.
- **원자적 쓰기 + 큐 락**: 노트/마커/큐 쓰기는 임시파일→교체, 큐는 파일 락. 동시 실행 안전.
- **무인 AI 실행 최소화**: bypassPermissions는 하루 1회·pending 있을 때만.
- **변경 후 검증**: `tests/run_all.py` + `doctor` + `digest`로 회귀 확인.
- **비밀값 커밋 금지**: `memory-config.json`, `.env`는 `.gitignore` 제외 확인 후 커밋.
