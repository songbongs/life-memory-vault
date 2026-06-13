# Life Memory Vault — 2026년 6월 개선 작업 완결 기록

작성: 2026-06-14  
기준 커밋: `54e6cfd` (master)  
최종 테스트: 223건 / 18 파일 ALL GREEN

---

## 개요

2026년 6월에 걸쳐 두 차례 대규모 개선 작업을 수행했다.
첫 번째는 P1~P5 + ③a~d 코어 안정화 캠페인(2026-06-10),
두 번째는 Track A(URL 인리치먼트) + Track B(UX 사용성) 캠페인(2026-06-12~14).
마무리 단계에서 코드 리뷰를 통해 발견한 잠재 버그·이슈를 추가 수정했다.

---

## 1차 캠페인 — 코어 안정화 (2026-06-10)

### P1 분류기 정밀화
- `classify()`: " - " 패턴 단독으로 song 분류하지 않도록 수정 (명시적 음악 신호 필요)
- `tests/test_classify.py` 24건

### P2 신뢰성·보안
- `atomic_write_text()`: 쓰기 실패 시 파일 손상 방지
- `jobs.py` 큐 파일 락 + 원자적 쓰기
- Telegram deny-by-default (`allowedUserIds` 화이트리스트)
- `tests/test_reliability.py` 12건

### P3 경로 단일진실원(SSOT)
- 경로 드리프트 수정, `agent.jobsProcessorPath` 설정 키 도입
- `commands/` + `skills/` = `.claude/`와 하드링크 (심볼릭이 아님 — 동일 inode)

### P4 자동화 루프
- `scripts/process_jobs.py`: digest/doctor 자동 완료 + Telegram 회신, 적체 알림
- launchd `com.sangmin.life-memory-jobs` (5분 주기) 활성화
- **macOS TCC exit-126 버그 수정**: launchd에서 `/bin/bash` 대신 `python3` 직접 호출
- `tests/test_process_jobs.py` 26건 (최종)

### ③a AI 호출 브리지
- `scripts/process_ai_jobs.py`: headless claude/codex 실행, 잡 타입별 모델 라우팅
- per-job-type 모델: lint/repair/seek→sonnet, enrich→haiku
- `tests/test_process_ai_jobs.py` 22건

### ③b~c 글로벌 스킬 + 23:00 launchd
- `install-global-skill.sh` → `~/.codex` · `~/.claude` life-memory 스킬
- `com.sangmin.life-memory-ai` launchd (매일 23:00 배치)
- launchd-TCC 검증: claude가 launchd 환경에서도 볼트 쓰기 가능 (GUI Full Disk Access 불필요)

### ③d 학습 루프
- `scripts/rules.py`: 결정→규칙 도출, 2회 확인→활성, 충돌→차단
- `mem.py review list|resolve`: Review 노트 해결 + 결정 기록
- `tests/test_rules.py` 10건 + `test_learning_e2e.py` 2건

### P5 검색 품질
- `mem.seek`: 다중 토큰 스코어링, `--type/--tag/--since` 필터
- `tests/test_seek.py` 8건

---

## 2차 캠페인 — Track A + Track B (2026-06-12~14)

### B1 한국어 UX (2026-06-12, `53c8a47` 이전)
- 텔레그램 캡처봇 한국어 별칭: 정리/점검/수리/검색·찾기/통계·다이제스트/상태/도움말
- `/help` 명령: 이원 봇 구조 + 처리 시점 안내
- `scripts/set-telegram-menu.py`: 캡처봇 메뉴 등록
- `tests/test_telegram_commands.py` 12건

### A0~A3 URL 인리치먼트 Track

| 단계 | 내용 | 커밋 |
|---|---|---|
| A0 | trafilatura 설치 (`--user --break-system-packages`), doctor에 enrichment 상태 추가 | `fc4fcaa` 이전 |
| A1 | `scripts/enrich.py`: URL 추출·og:image·발췌 블록·Extracts 전문 보관 | `fc4fcaa` |
| A2 | `prompts/ai-enrich.md`: 항상 한국어 요약, 주입 방어, 상태→summarized | `fc4fcaa` 이후 |
| A3 | `scheduled_lint.py`에 enrich 연결, digest 통계, 실패 알림 | `2844064` |

### ① 주간 다이제스트 푸시 (`53c8a47`)
- `process_jobs.maybe_weekly_digest()`: intervalDays/hour 설정, 캡처봇으로 발송
- 내용: 기록 수·요약·검토대기·주요분류·중복 요약

### 중복 마커 정리 (`0e5e40e`, `6b2bd6e`)
- `mem.py dedup-markers`: 2단계 (same-raw NFC/NFD 중복 삭제 + same-note duplicate_of 처리)
- digest: structured_notes / duplicate_markers 분리 통계

### ② 분류 수정 (reclassify) (`8e7f848`)
- `mem.py reclassify <note> --type --signal [--apply]`
- 노트 이동 + 마커 업데이트 + 모든 wikilink 업데이트 + 학습 결정 기록
- dry-run 기본, 백업 후 적용

### ③ A4 YouTube + 아카이브 (`e23d452`)
- `enrich.py`: YouTube URL → yt-dlp 자막(ko>en>auto) + 영상 요약
- monolith 전문 박제 scaffold (archivePages: false 기본, 미설치 시 graceful skip)

### ④ 미디어 내용 추출 (`90ae652`)
- `scripts/extract_media.py`: tesseract OCR (HEIC→sips→JPEG 전처리), pdfplumber PDF, 오디오 stub
- `mem.py extract-media` 서브커맨드
- Extracts 저장: `80_Assets/Extracts/{images|pdf|audio}/`
- `prompts/ai-media-enrich.md`: OCR·PDF 한국어 요약
- config `mediaExtraction` 섹션, `media-enrich` AI 잡 타입
- `tests/test_extract_media.py` 29건
- **scheduled_lint.py 조기 종료 버그 수정** (`d7d450c`): `if pending <= 0: return`이 enrich+extract-media까지 막던 문제 → pending 여부와 무관하게 항상 실행

### ⑤ 문서화 마무리 (`ac0fcf8`, `8efc750`)
- `docs/user-guide.md` 전면 갱신 (OCR/PDF/YouTube/주간회고/reclassify/B2 권장동선)
- `docs/operator-guide.md` 전면 갱신 (시스템 다이어그램/스크립트 표/mediaExtraction/트러블슈팅)
- `docs/beginner-guide.md` 신규: 7가지 샘플 시나리오 + 자동화 타임라인 + FAQ
- 볼트 가이드 동기화 (`90_System/Guides/`)
- 홈 대시보드 `90_System/홈.md` 신규 생성

---

## 3차 — 코드 리뷰 기반 추가 수정 (2026-06-14)

리뷰에서 발견한 버그·잠재이슈·UX 개선을 모두 반영.

### 버그 수정 2건 (`54e6cfd`)

**버그 1: `process_jobs.py` AGENT_TYPES 불일치**
- 원인: `AGENT_TYPES = {"lint", "repair", "seek"}` — enrich/media-enrich 누락
- 증상: process_jobs가 enrich 잡을 만나면 5분마다 `unknown_type` 로그 출력
- 수정: `AGENT_TYPES = {"lint", "repair", "seek", "enrich", "media-enrich"}`

**버그 2: `process_ai_jobs.py` AGENT_DEFAULTS 기본값 누락**
- 원인: 하드코딩된 기본값 `["lint","repair","seek"]`에 enrich/media-enrich 없음
- 증상: memory-config.json 없이 실행 시 enrich 잡이 영원히 pending 상태로 방치
- 수정: 기본값에 `"enrich"`, `"media-enrich"` 추가

### 잠재이슈 해결 3건

**이슈 1: Enrich 실패 텔레그램 알림 없음**
- `scheduled_lint.py`에 `_alert_telegram()` 헬퍼 추가 (stdlib urllib, 의존성 없음)
- enrich 실패 건 발생 시 캡처봇으로 즉시 알림 + 재시도 명령어 안내

**이슈 2: 실패 마커 조회 방법 없음**
- `mem.py enrich --status <상태>` 추가
- 처리 없이 특정 상태(failed/extracted/summarized 등) 마커 목록만 조회
- `enrich.py` status_filter 모드: 해당 상태 마커의 URL·시도횟수·오류 출력

**이슈 3: `doctor`가 잡 큐 상태를 보여주지 않음**
- `mem.py doctor()`: `jobs.py list --status pending` 서브프로세스 호출, `queue` 섹션 추가
- `process_jobs.py format_doctor()`: 큐 pending 건수 + 타입별 분류 텔레그램 표시

### UX 개선 2건

**개선 1: 홈 대시보드 자동 갱신**
- `mem.py home-update` 서브커맨드: `90_System/홈.md`의 `<!-- stats:begin/end -->` 블록 갱신
- `process_jobs.py maybe_weekly_digest()`: 주간 다이제스트 발송 후 자동 호출
- 홈.md에 stats 블록 추가: 기록 건수·링크 요약 현황·실패 건 표시

**개선 2: prune-orphans 자가치유 실행**
- 구현은 이미 완료된 상태, 실제 볼트에 유령 파일 3건 발견·정리
  - `10_Timeline/Daily/github.com pbakaus impeccable...` → 정식본: `60_Ideas/Products/`
  - `10_Timeline/Daily/매달 말일 정화에게 생활비 송금...` → 정식본: `30_Actions/Tasks/`
  - `10_Timeline/Daily/관심 프로젝트.md` → 정식본: `60_Ideas/Products/`
- 재실행 시 `would_delete: 0` 확인 (멱등 자가치유 정상)

### 신규 테스트 10건
- `test_process_jobs.py`: enrich/media-enrich 잡 → `reserved_for_agent` 스킵 (2건)
- `test_process_jobs.py`: doctor format에 queue pending 표시, 대기 없음 표시 (2건)
- `test_enrich.py`: `--status failed` 필터, 매칭 없을 때 빈 목록 (2건)
- `test_home_update.py`: stats 블록 생성, 기존 블록 교체, 홈.md 없을 때 skip, 실패 건 표시 (4건)

---

## 최종 상태 (2026-06-14)

### 테스트
```
223 tests / 18 files — ALL GREEN
```

### 커밋 이력 (최신순)
```
54e6cfd  fix+feat: bug fixes, enrich observability, doctor queue, home dashboard
86696ae  docs: add safety improvement work order for future hardening
d7d450c  fix: scheduled_lint always runs enrich+extract-media regardless of pending raw count
8efc750  docs: add beginner quick-start guide with sample scenarios
ac0fcf8  docs: ⑤ refresh user-guide + operator-guide for all new features
90ae652  feat: ④ media extraction — image OCR (tesseract) + PDF text (pdfplumber)
e23d452  feat: A4 enrich — YouTube subtitle summary (yt-dlp) + page-archive scaffold
a633816  chore: gitignore .agents/ (Claude Code skill cache)
8e7f848  feat: reclassify — natural-language category fix + learning (UX ②)
6b2bd6e  feat: dedup-markers 2-stage (same-raw + same-note) + recap dup line
0e5e40e  feat: dedup-markers + digest excludes duplicates (stat coherence)
53c8a47  feat: weekly digest push to Telegram (UX ①)
2844064  feat: A3 automation — daily lint→enrich, digest stats, failure alert
```

### launchd 에이전트 (4개 모두 정상)
```
com.sangmin.life-memory-collector   KeepAlive  텔레그램 수신 (상시)
com.sangmin.life-memory-lint        22:00      lint → enrich → extract-media
com.sangmin.life-memory-jobs        5분 주기   digest/doctor 자동 완료 + 알림
com.sangmin.life-memory-ai          23:00      AI 한국어 요약 (enrich/media-enrich/lint)
```

### 실시간 볼트 현황
- Raw 노트: 37건 | 처리: 38건 | 링크 요약: 7/19건 | 실패: 3건 (threads.com, fascanner 등)
- Pending AI 잡: enrich 1건 (오늘 23:00 처리 예정)

---

## 향후 개선 로드맵 (`docs/safety-improvement-work-order.md`)

우선순위 순:
1. **무인 AI 실행 권한 축소** — manifest 기반 변경 계획 검증 (prompt injection 방어)
2. **URL enrich SSRF 방어** — 로컬/내부망 주소 fetch 차단
3. **Job queue claim/lease** — 중복 실행 및 좀비 잡 방지
4. **Destructive 명령 2단계 적용** — plan-out → apply --manifest 구조
5. **`scripts/mem.py` 모듈 분리** — 단일 파일 분리로 유지보수성 향상

각 단계는 독립 테스트 가능하며, 기존 223건 회귀 통과를 완료 조건으로 한다.
