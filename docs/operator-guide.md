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
              ┌────────────────────────────────┼─────────────────────────────┐
              ▼ (결정론·무료)                                                  ▼ (AI·구독)
        mem.py lint                                              process_ai_jobs.py → claude/codex
        (분류·중복제거·날짜보강)                                  (Wiki layer: 엔티티·MOC·링크)
              │                                                                │
              └──────────→ 00_Inbox/Processed/*.json (마커) ←──────────────────┘
                           00_Inbox/Review (애매한 건)
                                               │
                           review resolve → rules.py (학습) → classify 자동분류
```

핵심 스크립트 (`scripts/`):

| 파일 | 역할 |
|---|---|
| `mem.py` | 메인 CLI: save / lint / seek / digest / doctor / init / review |
| `rules.py` | 학습 규칙 저장소 (add-decision / list / active / remove) |
| `jobs.py` | 작업 큐 (텔레그램 명령 → JSONL 큐) |
| `telegram_collector.py` | 텔레그램 수집기(메일박스→Raw) |
| `process_jobs.py` | 결정론적 작업 처리 브리지 (digest/doctor 자동 회신 + 적체 알림) |
| `process_ai_jobs.py` | AI 작업(lint/repair/seek)을 헤드리스 에이전트로 처리 |
| `scheduled_lint.py` | 정기 lint 트리거(미처리 감지→AI job 등록 + 규칙 lint) |
| `memory_admin.py` | 로컬 관리 대시보드 (수집기 start/stop) |
| `install-*.sh` | launchd/스킬 설치 스크립트 |

---

## 2. 설정 파일

### `memory-config.json` (로컬 전용, git 제외)

`memory-config.example.json`을 복사해 작성. 주요 키:

- `memoryVault.vaultPath` — Obsidian 볼트 절대경로 (★필수)
- `telegram.allowedUserIds` — **허용된 텔레그램 숫자 ID 목록**. **비어 있으면 전부 거부**(보안 기본값)하고 발신자에게 본인 ID를 안내.
- `agent.default` (기본 `claude`) / `agent.commands` — 헤드리스 에이전트 호출 템플릿(`{prompt}` 치환). claude는 `--permission-mode bypassPermissions` 사용.
- `agent.jobsProcessorPath` — 글로벌 스킬 위치(SSOT, 기본 `~/.codex/skills/life-memory/SKILL.md`)
- `agent.modelByJobType.<agent>.<jobtype>` — **잡 타입별 모델**. process_ai_jobs.py가 값이 있으면 `--model <값>`을 붙이고, 빈 값/생략이면 에이전트 기본 모델. **claude는 별칭(`haiku`/`sonnet`/`opus`)을 쓰면 항상 그 계열 최신 모델로 해석**되어 신규 버전이 나와도 설정 변경이 불필요하다. 현재: claude는 `enrich`=haiku(반복·정형), `lint`/`repair`/`seek`=sonnet(추론·분석); codex/antigravity는 비워 기본 모델(작업별 지정 가능).
- `learning.{enabled, promoteThreshold(=2), rulesPath, mirrorPath}` — 학습 루프 설정
- `jobs.backlogAlert.{enabled, minPendingAgeHours, minPendingCount, cooldownHours}` — 적체 알림(선택)
- `enrichment.{enabled, auto, maxCandidatesPerRun(=5), onDemandNoticeThreshold(=10), timeoutSeconds, maxExtractChars, imageMaxBytes, optOutTags, assetsSubdir, stagingDir}` — URL enrich(트랙 A) 설정. `maxCandidatesPerRun`=무인 run당 상한(초과분은 다음날 자동 이월), `onDemandNoticeThreshold`=운영 봇 온디맨드가 대기 전부 처리하되 이 값 초과 시 사전 고지.

### `.env` (git 제외)

```
TELEGRAM_BOT_TOKEN=...   # @BotFather에서 발급
```

> 비밀값(`memory-config.json`, `.env`)은 `.gitignore`로 제외됩니다. 커밋 전 `git check-ignore memory-config.json .env`로 항상 확인.

### 선택 의존성 — enrich용 `trafilatura`

URL enrich(트랙 A)는 결정적 본문 추출에 `trafilatura`를 씁니다. **이것이 프로젝트의 첫 외부 pip 패키지**입니다.

```bash
# launchd 자동화가 쓰는 인터프리터와 동일해야 함 (현재 /opt/homebrew/bin/python3)
python3 -m pip install --user --break-system-packages trafilatura
```

- Homebrew python은 PEP 668로 일반 `pip install`을 막으므로 `--break-system-packages`가 필요하고, `--user`를 함께 줘 사용자 사이트(`~/Library/Python/3.x/...`)에만 설치한다(시스템 python 보호).
- launchd plist에 `PYTHONNOUSERSITE`가 없어야 무인 실행에서도 보인다(현재 4개 plist 모두 미설정 — OK).
- **미설치여도 안전**: `mem.py doctor`의 `enrichment.trafilatura`가 `false`로 뜨고 설치 안내를 주며, enrich 기능만 비활성된다(다른 경로 무영향).

---

## 3. 텔레그램 봇 운영

1. `@BotFather`에서 봇 생성 → 토큰을 `.env`의 `TELEGRAM_BOT_TOKEN`에 저장.
2. 본인 ID 확인: 수집기 실행 후 봇에 메시지 1회 전송 → "당신의 Telegram ID: N" 회신.
3. 그 N을 `memory-config.json`의 `telegram.allowedUserIds`에 추가.
4. 수집기 실행:
   ```bash
   python3 scripts/telegram_collector.py --me     # 봇 신원 확인
   python3 scripts/telegram_collector.py --once   # 1회 폴링
   python3 scripts/telegram_collector.py --loop    # 지속 폴링(보통 launchd가 담당)
   ```

지원 명령(봇에게 전송): `/lint /doctor /repair /seek <쿼리> /digest /status`. `/seek`·`/status`는 즉시 회신, 나머지는 작업 큐에 등록.

관리 대시보드(수집기 켜고 끄기):
```bash
python3 scripts/memory_admin.py   # → http://127.0.0.1:8765
```

---

## 4. 자동화 (launchd)

설치 스크립트가 `~/Library/LaunchAgents/`에 plist를 만들고 로드합니다. 레이블은 `com.sangmin.*` 컨벤션 유지.

| 설치 스크립트 | 레이블 | 주기 | 하는 일 |
|---|---|---|---|
| `install-mac-mini.sh` | `com.sangmin.life-memory-collector` | 상시(KeepAlive) | 텔레그램 수집기 |
| `install-launchd.sh` | `com.sangmin.life-memory-lint` | 매일 22:00 | 정기 lint(`scheduled_lint.py`) |
| `install-jobs-launchd.sh` | `com.sangmin.life-memory-jobs` | 5분마다 | digest/doctor 자동 처리 + 적체 알림(`process_jobs.py`) |
| `install-ai-jobs-launchd.sh` | `com.sangmin.life-memory-ai` | 매일 23:00 | AI 작업(lint/repair/seek) 헤드리스 처리(`process_ai_jobs.py`) |

설치/확인/제거:
```bash
bash scripts/install-jobs-launchd.sh
launchctl list | grep life-memory                 # 가운데 열=마지막 exit code (0 정상)
launchctl kickstart -k gui/$(id -u)/com.sangmin.life-memory-jobs   # 수동 1회 실행
launchctl unload ~/Library/LaunchAgents/<레이블>.plist && rm ~/Library/LaunchAgents/<레이블>.plist
```

로그: `memory-state/collector-service.log`, `scheduled-lint.log`, `launchd-jobs.log`, `launchd-ai-jobs.log`.

### ⚠️ macOS TCC 함정 (중요)

`~/Documents` 는 macOS가 보호하는 폴더라, **launchd가 `/bin/bash <스크립트>`로 실행하면 권한 거부(exit 126, "Operation not permitted")**로 실패합니다. 그래서 모든 launchd 작업은 **`python3`를 절대경로로 직접 실행**합니다(`WorkingDirectory` 설정 + `PATH` 환경변수로 `claude`/`codex` 해석). 새 launchd 작업을 만들 때 `/bin/bash` 패턴을 쓰지 마세요. 자세한 내용은 improvement-plan.md의 "P4-AI / TCC" 참조.

---

## 5. AI 자율 처리 (③ 학습 루프 포함)

- `process_ai_jobs.py`가 pending lint/repair/seek 작업을 꺼내 **헤드리스 에이전트**(기본 `claude -p`)를 호출, `prompts/process-pending-jobs.md` 프로토콜대로 처리하게 합니다.
  ```bash
  python3 scripts/process_ai_jobs.py --dry-run        # 실행될 명령 미리보기(안전)
  python3 scripts/process_ai_jobs.py --once           # 실제 처리(사용량 소모 + 볼트 쓰기)
  python3 scripts/process_ai_jobs.py --once --agent codex
  ```
- **권한 주의**: 무인 실행이 도구/쓰기를 승인 대기 없이 하려면 `bypassPermissions`가 필요합니다. 가드는 프롬프트(애매→Review, raw 불변)뿐이므로, **하루 1회 + pending 있을 때만** 돌려 노출을 최소화합니다. 권한 수위 재검토는 백로그 C 항목.
- **글로벌 스킬**: 어느 에이전트/폴더에서든 "라이프 메모리 작업 처리"가 되도록 설치:
  ```bash
  bash scripts/install-global-skill.sh   # → ~/.codex/skills, ~/.claude/skills
  ```

### 학습 규칙 관리

```bash
python3 scripts/rules.py list           # 규칙(active/candidate/blocked)
python3 scripts/rules.py active         # 자동 적용 중인 규칙
python3 scripts/rules.py remove "키워드"  # 잘못 배운 규칙 취소
```
저장소: 볼트 `90_System/Rules/learned-rules.json` + 사람용 미러 `Learned Rules.md`. 모순(같은 키워드, 다른 분류)은 `blocked`로 자동 적용 안 함.

---

## 6. 운영 점검 루틴

```bash
launchctl list | grep life-memory      # 4개 작업 모두 exit 0 인지
python3 scripts/mem.py doctor           # 도구 설치 상태
python3 scripts/mem.py digest           # raw/처리/분류 통계
python3 scripts/jobs.py summary         # 작업 큐 적체
python3 scripts/mem.py prune-orphans    # orphan/ghost 노트 점검(dry-run). --apply로 정리
tail -f memory-state/launchd-ai-jobs.log
python3 tests/run_all.py                # 전체 테스트
```

---

## 7. 재분류·정리 운영 (안전 절차)

분류 규칙을 개선했거나 오분류를 고칠 때. **항상 백업 후 타겟 리셋 → 재lint** (전체 `--force`는 위험하니 피함).

표준 절차:
1. 개선된 `classify`로 어떤 기록이 바뀌는지 **read-only 미리보기**.
2. 대상 raw의 **마커 + 구조화 노트를 백업 후 삭제**(`/var/folders/.../lmv-*-backup-*` 같은 임시 백업 권장).
3. `python3 scripts/mem.py lint` (마커 없는 것만 재처리) → 개선 분류 + 중복 제거 적용.
4. 검증: 모든 기록이 현재 분류기와 일치하는지, orphan 없는지 확인.

### ⚠️ song/playlist 재분류 시 — 엔티티 side-effect 정리 필수

song으로 분류되면 `extract_artist_song`이 `40_Entities/Artists`·`Songs`에 엔티티 노트를 만듭니다. song→비song으로 재분류할 때 **메인 노트뿐 아니라 엔티티 노트도 정리**해야 orphan이 안 남습니다. 마커의 `entities_updated`에 생성 엔티티 경로가 기록되므로 그걸로 추적하세요. orphan 점검은 "각 음악 엔티티의 `source_raw` 원본을 현재 분류기로 재평가 → 음악이 아니면 orphan"으로 판단.

### 중복(dedup)

`lint`는 내용 해시(`content_hash`)로 동일 내용을 묶어 구조화 노트를 1개만 만듭니다(원본은 모두 보존, 중복은 마커에 `duplicate_of` 기록). 과거(개선 이전) 마커엔 `content_hash`가 없어 소급 적용은 부분적입니다.

---

## 8. 트러블슈팅

| 증상 | 원인 / 조치 |
|---|---|
| 봇이 저장 안 함 | `allowedUserIds`에 내 ID 없음 → 봇에 메시지 보내 ID 확인 후 추가 |
| 매일 lint 실패(exit 126) | launchd가 `/bin/bash` 사용 → `python3` 직접 실행 plist로 재설치(§4 TCC) |
| `claude`/`codex` 못 찾음(launchd) | plist `EnvironmentVariables.PATH`에 homebrew bin 추가 필요 |
| 구조화 노트 중복 | `lint`가 dedup 처리. 과거 중복은 백업 후 타겟 리셋+재lint |
| 분류가 계속 틀림 | `review resolve --signal`로 2회 학습 → 자동화. 또는 `classify` 키워드 보강 |
| 잘못 배운 규칙 | `rules.py remove "키워드"` |
| 서로 다른 노트가 한 파일로 합쳐짐 | 제목 충돌. `create_structured_note(on_conflict="unique")`가 해시 접미사로 분리(이미 적용됨) |
| 지운 노트가 다시 살아남(유령) | 볼트가 **Google Drive 동기화**라 삭제가 ~30분 뒤 복원될 수 있음. `python3 scripts/mem.py prune-orphans`(dry-run) 확인 → `--apply`로 정리(백업됨). **멱등**이라 또 복원되면 재실행하면 됨 |
| song→task 등 재분류 후 음악 폴더에 잔재 | song 분류가 만든 엔티티 orphan. `prune-orphans`가 source_raw로 역추적해 정리 |

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
- **원자적 쓰기 + 큐 락**: 노트/마커/큐 쓰기는 임시파일→교체, 큐는 파일 락. 동시 실행에도 안전.
- **무인 AI 실행 최소화**: bypassPermissions는 하루 1회·pending 있을 때만.
- **변경 후 검증**: `tests/run_all.py` + `doctor` + `digest`로 회귀 확인.
