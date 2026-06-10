# Life Memory Vault 개선 작업계획서

작성일: 2026-06-10
대상 저장소 루트: `life-memory-vault/` (이 문서가 있는 `docs/`의 상위 = `memory-config.json`이 있는 폴더)

이 문서는 코드 검증을 거쳐 작성된 **실행 가능한 작업 지시서**다. 각 페이즈는 독립 커밋/PR로 분리 가능하며, 아래 "충돌 재검증" 절의 근거대로 서로 다른 함수·파일을 건드려 충돌이 없도록 설계되었다.

핵심 설계 원칙(`scripts/mem.py`의 `CHARTER`)을 모든 변경에서 깨지 않는다:
capture-first / raw-sacred / local-free-first / sensitive-by-default.

---

## 현황 대시보드 (최종 업데이트 2026-06-10)

| 페이즈 | 상태 | 한 줄 요약 |
|---|---|---|
| **P1** 분류기 정밀화 | ✅ 완료·검증 | song 오탐 제거. `tests/test_classify.py` 12건 |
| **P2** 신뢰성·보안 | ✅ 완료·검증 | 원자적 쓰기 + 큐 락 + 텔레그램 deny-by-default. `tests/test_reliability.py` 9건 |
| **P3** 경로 SSOT | ✅ 완료 | 경로 드리프트 0, `agent.jobsProcessorPath`, 중복 디렉터리 심볼릭 통합 (launchd 레이블은 `com.sangmin.*` 유지) |
| **P4** 자동화 루프 | ✅ 완료·검증 | `process_jobs.py`(digest/doctor 자동+회신, 적체 알림) + launchd. **macOS TCC exit126 버그 수정**. `tests/test_process_jobs.py` 22건 |
| **③a** AI 호출 브리지 | ✅ 완료·검증 | `process_ai_jobs.py` + 실제 1건 검증. `tests/test_process_ai_jobs.py` 14건 |
| **③b** 글로벌 스킬 | ✅ 완료 | `install-global-skill.sh` → `~/.codex`·`~/.claude` 스킬 |
| **③c** 매일 23:00 launchd | ✅ 완료·검증 | `install-ai-jobs-launchd.sh`. launchd-TCC로 claude 볼트 쓰기 실측 통과(GUI 권한 불필요) |
| **③d** 학습 루프 | ✅ 완료·검증 | rules.py + classify 선패스 + review CLI + 프롬프트 통합(+MOC stub 해결) + e2e. `tests/test_rules·review_cli·learning_e2e` |
| **P5** 검색 품질 | ✅ 1·2단계 완료·검증 (3단계 선택 보류) | `mem.seek` 점수 정렬·다중 토큰 + `--type/--tag/--since`. `tests/test_seek.py` 8건 |
| 후속/품질 백로그 | ⬜ | 문서 맨 끝 "남은 작업 & 후속 백로그" 참조 |

- 테스트 총 **89건 GREEN**, 스크립트 7개 `py_compile` OK, launchd 4개 모두 exit 0.
- **계획서의 모든 주요 페이즈(P1–P5 + ③a–d) 완료.** 남은 것은 선택/관찰 항목뿐(아래 백로그).
- **커밋 미실시**(사용자 요청 시 진행). git 저장소이므로 페이즈별 커밋 가능.
- 진행 리듬: 페이즈 종료 → 요약 → 사용자 컨펌 → 다음.

---

## 0. 진행 순서 & 충돌 매트릭스

작고 명확 → 크고 불명확 순.

| 순서 | 페이즈 | 인사이트 | 크기 | 명확도 | 주 변경 대상 | 선행 의존성 |
|---|---|---|---|---|---|---|
| **P1** | 규칙 분류기 정밀화(song 오탐) | #1 | 작음 | 매우 높음 | `mem.py::classify`, `extract_artist_song` | 없음 |
| **P2** | 신뢰성·보안 하드닝 | #4 | 작음~중 | 높음 | `mem.py` 쓰기 헬퍼 / `jobs.py::write_jsonl` / `telegram_collector.py::user_allowed` | 없음 |
| **P3** | 경로 단일 진실원(SSOT) | #3 | 중 | 높음 | `docs/*`, `scripts/install-*.sh` 레이블, 중복 디렉터리 | 없음 |
| **P4** | 자동화 루프 닫기 | #2 | 큼 | 중 | 신규 `scripts/process_jobs.py`, launchd, 기존 `process-pending-jobs.md`/`scheduled_lint.sh` | P2(큐 락), P3(레이블/경로) |
| **P5** | 검색 품질 강화 | #5 | 큼 | 낮음 | `mem.py::seek` | 없음 |

### 충돌 재검증 (코드 확인 결과)

- `mem.py` 안에서 **P1 = `classify`/`extract_artist_song`**, **P2 = 쓰기 헬퍼(`write_if_missing`:307, `create_structured_note`:521, 마커 쓰기:568, `save_raw` 쓰기:470)**, **P5 = `seek`:589** — 세 영역이 **서로 겹치지 않는 별개 함수**다. 동시 작업·병렬 머지 가능.
- **P2**의 큐 락(`jobs.py::write_jsonl`:48)은 **P4**의 큐 소비기가 안전하게 동작하기 위한 전제. 따라서 P2 → P4 순서 고정.
- **P3**의 launchd 레이블/경로 정리는 **P4**가 launchd로 자율 실행을 붙일 때 정합성의 전제. 따라서 P3 → P4 순서 권장.
- 중복 디렉터리(`commands/`↔`.claude/commands/`, `skills/`↔`.claude/skills/`)는 **바이트 단위 동일**함을 확인 → P3에서 안전하게 통합.

권장 진행: **P1 → P2 → P3 → P4 → P5**. (P1·P2·P3는 상호 독립이라 병렬 가능하나, 리뷰 단순화를 위해 순차 권장.)

---

## P1 — 규칙 기반 분류기 정밀화 (song 오탐 제거)

### 목표
`"엄마 - 병원 예약"`처럼 첫 줄에 ` - `만 있어도 노래로 오분류되고, 가짜 아티스트/곡 엔티티가 생성되는 문제를 제거한다.

### 현재 상태 (확인됨)
- `mem.py:480`: `re.match(r"^\s*.+?\s+-\s+.+\s*$", text.strip())` 이 **최우선** 분기 → ` - ` 패턴만으로 `song` 확정.
- `extract_artist_song`(506) 가 이를 받아 `40_Entities/Artists`·`Songs`에 노트 생성(lint 561~563).
- 이 규칙 기반 lint는 `scheduled_lint.sh`를 통해 **매일 22:00 launchd로 자동 실행**되므로 오탐이 누적될 수 있음.

### 작업 내용
1. song 판정 조건을 강화: `YouTube Music/음악 URL` **또는** `#음악/#music 태그` **또는** (` - ` 패턴 **AND** 음악 키워드 동반) 일 때만 `song`/`playlist`.
2. `classify()` 분기 순서 재배치 — song 단독 패턴을 **최우선에서 후순위로 강등**, 명시적 키워드(task/appointment/maintenance 등)가 먼저 평가되게.
3. 매칭이 약하면 `confidence: "low"`로 낮춰 AI lint 재처리 대상으로 표시(“확신 없으면 보류” 원칙을 규칙기에도 적용).
4. `extract_artist_song` 호출을 song 확정 케이스로만 제한.

### 방식
순수 로직 변경. 의존성 추가 없음. P1 단위 테스트와 같은 커밋으로 묶는다(아래 DoD).

### 테스트 (신규 `tests/test_classify.py`)
- `"엄마 - 병원 예약 잡기"` → `appointment` (not song)
- `"회의 - 3시로 변경"` → `task`/`journal` (not song)
- `"IU - 밤편지 https://music.youtube.com/..."` → `song` + 엔티티 생성
- `"#음악 좋아하는 곡"` → 음악 계열

### 사용자 경험 개선
lint 후 엔티티 폴더에 쓰레기 노트가 쌓이지 않고, `digest`의 `by_type` 통계가 신뢰 가능해짐. 매일 자동 lint 품질이 즉시 향상.

### 사용 예시
```bash
python3 scripts/mem.py save "엄마 - 병원 예약 잡기"
python3 scripts/mem.py lint
# Before: memory_type=song, 40_Entities/Artists/엄마.md 생성(오류)
# After : memory_type=appointment, 30_Actions/Appointments/ 정리, 가짜 엔티티 없음
```

### 완료 조건(DoD)
- 위 테스트 통과 / 기존 음악 케이스 회귀 없음 / 분기 순서 변경이 다른 타입 분류를 깨지 않음.

---

## P2 — 신뢰성·보안 하드닝 (독립 3건 묶음)

### 목표
데이터 유실·손상·무단 쓰기라는 "조용한 실패"를 막는다. 개인 민감 데이터 저장소의 최소 안전선.

### 작업 내용

**(P2-a) 원자적 쓰기**
- 신규 헬퍼 `atomic_write_text(path, content)` 추가: `path.with_suffix(path.suffix + ".tmp")`에 쓴 뒤 `os.replace`로 교체.
- 적용 지점: `write_if_missing`(307), `create_structured_note`(521, append 경로 포함), 마커 쓰기(568), `save_raw` 본문 쓰기(470).
- 표준 라이브러리만 사용(stdlib-only 원칙 유지).

**(P2-b) 큐 파일 락**
- `jobs.py::write_jsonl`(48)과 읽기-수정-쓰기 구간(`add_job`/`set_status`)을 `fcntl.flock` 배타 락으로 감싼다.
- 수집기와 (P4) 소비기가 동시에 같은 `queue-YYYY-MM-DD.jsonl`을 써도 작업 유실 없음.

**(P2-c) 텔레그램 인증 기본값 전환**
- `telegram_collector.py::user_allowed`(271): `allowedUserIds`가 비어 있을 때 현재 **전체 허용** → **거부 + 발신자 ID 안내**로 변경.
- 미등록 사용자에게 1회 회신: "🔒 등록되지 않은 사용자입니다. 당신의 Telegram ID: N — memory-config.json의 telegram.allowedUserIds에 추가하세요." (저장은 하지 않음)
- `memory-config.example.json`·README의 "최초 설정 시 비워둠" 안내도 함께 수정.

### 방식
세 건 모두 국소적·독립적. `os.replace`/`fcntl`은 표준 라이브러리.

### 테스트 (신규 `tests/test_reliability.py`)
- 원자성: 임시파일 잔존 없음, 정상 내용 보존.
- 큐 락: 동시 add 시뮬레이션에서 모든 job 보존.
- 인증: 빈 allowlist + 미등록 ID → 저장 안 됨/안내 회신; 등록 ID → 정상 저장.

### 사용자 경험 개선
동기화 중 크래시에도 노트가 깨지지 않음 / 폰에서 메시지를 연달아 던지거나 자동 처리가 겹쳐도 작업이 사라지지 않음 / 토큰이 노출돼도 모르는 사람이 내 기억 저장소에 글을 못 씀.

### 사용 예시
```text
# (P2-c) 미등록 사용자 메시지 → 저장 안 됨, 안내만 회신:
🔒 등록되지 않은 사용자입니다. 당신의 Telegram ID: 123456789
   memory-config.json의 telegram.allowedUserIds에 추가하세요.
# 설정: "allowedUserIds": [123456789]
```

### 완료 조건(DoD)
- 위 테스트 통과 / 기존 정상 흐름 동작 / README·example 설정 안내 일치.

---

## P3 — 경로 단일 진실원(SSOT) 정리

### 목표
산문/레이블에 흩어진 하드코딩 경로가 실제 환경과 어긋난 드리프트를 해소하고, 미래 에이전트가 올바른 위치를 찾게 한다.

### 현재 상태 (확인됨)
- **스크립트 자체는 안전**: `Path(__file__).resolve().parents[1]`로 루트를 상대 해석 → 기능상 어느 경로에서도 동작.
- **드리프트는 산문/레이블에 한정**:
  - `docs/project-handoff.md`(21,27,134,191,824), `docs/admin-dashboard.md`(19): `/Users/sangmin/.../AI_Playground/my-life-memory`, `~/.codex/skills/life-memory/SKILL.md` 등 옛 경로.
  - launchd 레이블: `scripts/install-launchd.sh`(`com.sangmin.life-memory-lint`), `scripts/install-mac-mini.sh`(`com.sangmin.*`) — 기능은 하나 오해 소지/충돌 위험.
- 중복 디렉터리(`commands/`↔`.claude/commands/`, `skills/`↔`.claude/skills/`)는 **바이트 동일**.

### 작업 내용 (진행 기록 2026-06-10 반영)
1. ✅ 문서의 하드코딩 절대경로를 정정/플레이스홀더화하고 "실제 값은 `memory-config.json`에서 읽는다"로 기술. (README, project-handoff, admin-dashboard, mobile-ai-commands, process-pending-jobs)
2. ⏸ launchd 레이블 중립화는 **보류**(사용자 결정). 기존 `com.sangmin.*` 작업이 이미 설치·실행 중이라 무중단 유지를 택함. `install-*.sh`/`mac-mini-*` 문서의 레이블은 현행 유지.
3. ✅ 중복 디렉터리 통합: `.claude/commands`·`.claude/skills`를 정본으로 유지(Claude Code가 직접 읽음), 루트 `commands`·`skills`는 그쪽을 가리키는 **상대 심볼릭 링크**로 대체. 내용 드리프트 제거 + 양쪽 경로 모두 동작.
4. ✅ 머신 종속 외부 경로(Codex 스킬 위치)를 `memory-config.json`의 새 키 `agent.jobsProcessorPath`(기본 `~/.codex/skills/life-memory/SKILL.md`)로 모음 → P4가 참조.

### 방식
대부분 문서/구성 정리. 코드 로직 변경 최소. 변경 후 `grep -rn "sangmin\|AI_Playground\|my-life-memory"`로 잔존 드리프트 0 확인.

### 사용자 경험 개선
기기 이전(맥북→맥미니)·새 에이전트 인계 시 문서만 보고 정확히 동작. "문서대로 했는데 경로가 없다"가 사라짐. launchd 레이블 충돌 위험 제거.

### 사용 예시
```text
# Before: 핸드오프 문서의 /Users/sangmin/.codex/skills/... → 미존재 → 작업 미처리
# After : memory-config.json
#   "agent": { "jobsProcessorPath": "~/.codex/skills/life-memory/SKILL.md" }
#   문서·스크립트가 이 값을 참조 → 한 곳만 고치면 전부 정합
```

### 완료 조건(DoD)
- 드리프트 grep 결과 0(의도적 기기별 실경로 제외) / 중복 디렉터리 단일화 / launchd 설치·제거 예시 동작.

---

## P4 — 자동화 루프 닫기 (큐 → 처리 → 회신)

### 목표
`/lint`·`/seek` 등에 봇이 한 "AI 처리 후 알려드릴게요" 약속(`telegram_collector.py:329`)을 **자율적으로** 이행한다.

### 현재 상태 (확인됨 — 인프라는 이미 상당 부분 존재)
- `prompts/process-pending-jobs.md`: 큐 list→pick→running→실행→done/failed + 텔레그램 회신까지의 **에이전트용 소비 로직**이 이미 정의됨(AI Seek/Digest/Status 프로토콜 포함).
- `scripts/scheduled_lint.sh`: 미처리 건수 확인 → AI lint **job 등록** + 규칙 lint 즉시 실행. `install-launchd.sh`로 매일 22:00 실행.
- **빠진 조각(좁고 명확)**: 위 소비 로직을 **사람 개입 없이 자율 실행**하고, 완료 시 **텔레그램으로 결과를 회신**하는 브리지가 없음. 현재는 사람/에이전트가 `process-pending-jobs.md`를 수동 호출해야 루프가 닫힘.

### 작업 내용 (진행 기록 2026-06-10 — 완료)
1. ✅ 신규 `scripts/process_jobs.py`(stdlib-only) 작성. **충돌 회피를 위해 자동 완료 범위를 결정론적 타입으로 한정**:
   - 기본 자동 완료: `digest`, `doctor`(현재 큐에 등록돼도 영영 pending이던 타입). `mem.py` subprocess 처리 → `set-status running`→`done` + `result-json` 기록 → `chat_id` 있으면 `telegram_collector.send_message` 회신.
   - `seek`/`lint`/`repair`는 **건너뜀(에이전트 몫)**. `scheduled_lint.sh`가 만드는 codex용 lint 작업을 가로채지 않음. `--rule-lint`/`--keyword-seek` 플래그로 opt-in 가능.
   - **멱등**: `status == pending`만 처리(`jobs.py list --status pending` 기반). P2의 큐 락/원자성 위에서 안전. `--queue-dir` 패스스루로 격리 테스트/운영 큐 지정 가능.
2. ✅ launchd 주기 실행: `scripts/process_jobs.sh`(래퍼) + `scripts/install-jobs-launchd.sh`(`com.sangmin.life-memory-jobs`, StartInterval 300s). 기존 lint 스케줄과 별도 plist. (레이블은 사용자 결정대로 `com.sangmin.*` 컨벤션 유지.)
3. ✅ 적체/실패 알림: 실패 시 `set-status failed` + 노트. 장기 pending 적체 알림(`maybe_alert`)도 구현 — 에이전트 몫 작업이 기준 시간 이상 쌓이면 텔레그램 알림(`jobs.backlogAlert`로 튜닝, 쿨다운 적용).

### 후속 진행 기록 (2026-06-10)
- ✅ **브리지 활성화**: `install-jobs-launchd.sh` 실행 → `com.sangmin.life-memory-jobs` 5분 주기 등록·검증(exit 0).
- ✅ **macOS TCC 버그 수정(★중요)**: 기존 `com.sangmin.life-memory-lint`가 `/bin/bash scheduled_lint.sh`로 `~/Documents` 하위 스크립트를 실행하다 TCC에 막혀 exit 126(매일 lint 실패)이었음. 원인 규명 후 **launchd가 `python3`를 직접 실행**(동작하는 collector와 동일 패턴)하도록 `scheduled_lint.py` 신규 포트 + `install-launchd.sh`/`install-mac-mini.sh` 수정. 재설치·강제실행으로 exit 0 검증.
- ✅ 불필요한 bash 래퍼(`process_jobs.sh`) 제거, launchd는 모두 python3 직접 실행으로 통일.

### 방식
새 코드는 **기존 자산을 오케스트레이션**하는 얇은 브리지(루프 로직을 새로 발명하지 않음 — `process-pending-jobs.md`의 단계를 코드/어댑터로 실행). 종량 API 회피 위해 AI 위임은 구독 에이전트 경로 사용.

### 테스트 (신규 `tests/test_process_jobs.py`)
- pending digest job → done + result 기록 + (모킹된) send_message 호출.
- 이미 done인 job → skip(멱등).
- 처리 예외 → failed + blocker 노트.

### 사용자 경험 개선
폰에서 `/lint` 하나 던지면 잠시 후 "✅ AI Lint 완료 N건 / needs_review 1건" 회신이 **자동** 도착. "던지면 알아서 정리되고 결과까지 온다"는 비전이 비로소 완성.

### 사용 예시
```text
[폰] /lint
[봇] 📋 정리 작업 요청 등록 (Job a1b2c3) — 처리 후 알려드릴게요
  ...(launchd가 N분 내 process_jobs 실행)...
[봇] ✅ AI Lint 완료 (2026-06-10 22:05)
     처리 3건 / 신규: 와이퍼 교체(maintenance)
     needs_review 1건 → 00_Inbox/Review 확인
```
```bash
python3 scripts/process_jobs.py --once   # 수동 1회
```

### 완료 조건(DoD)
- 위 테스트 통과 / launchd 주기 실행 시 pending 작업이 자동 done + 회신 / P2 락과 동시 실행 시 유실 0.

---

## P4-AI (③) — AI 심화 처리 자율화 (사용자 결정 반영 2026-06-10)

`process_jobs.py`가 일부러 남겨둔 AI 타입(lint Wiki-layer / repair / AI-seek)을 구독 에이전트로 자율 처리한다. 범위가 커서 하위 페이즈로 나눈다.

### 확정된 설계 결정
- **에이전트**: 기본 = **Claude Code**(`claude -p ... --permission-mode ... --allowedTools ...`). codex(`codex exec`)/antigravity도 동일 요청 가능하도록 **에이전트 비종속**으로 구성(`agent.command` 템플릿). 전역에서 호출 가능한 **글로벌 스킬**로도 제공.
- **호출 주기**: **매일 23:00 일괄 처리**(launchd) + **온디맨드 수동 호출**(`--once`).
- **자율 수위**: 명확한 건만 자동 반영, **애매하면 `00_Inbox/Review`로 미루고 알림**. 나아가 사용자의 Review 결정을 **학습**해 동일 패턴은 이후 자동 분류로 승격(피드백 루프).
- **헤드리스 확인됨**: claude 2.1.153 `-p`, codex 0.137.0 `exec` 모두 비대화형 지원.
- **미검증 리스크**: 에이전트 바이너리가 launchd(TCC) 컨텍스트에서 `~/Documents` + Google Drive 볼트에 접근 가능한지 ③c에서 확인 필요(P4에서 겪은 TCC 변수의 연장).

### 하위 페이즈
- **③a — 호출 브리지 코어** ✅(2026-06-10): `scripts/process_ai_jobs.py` 신규. pending AI 작업 선별 → `agent.commands` 템플릿으로 에이전트 헤드리스 호출(프롬프트 = `prompts/process-pending-jobs.md` + 특정 job id). 비대화형 가드("묻지 말 것, 애매하면 Review, raw 불변") 주입. running 마킹 후 종료코드로 안전 종결(에이전트가 자체 done/failed 마킹하면 존중). `agent`(claude/codex)·`--queue-dir`·`--dry-run` 지원. **fake 에이전트로 14건 테스트 + dry-run으로 실제 `claude -p` 명령 구성 확인(claude 실행/볼트 변경 없음).** 설정 키 `agent.default/aiJobTypes/commands` 추가. **실제 1건 검증 완료(2026-06-10)**: 실제 볼트에서 lint 1건을 `claude -p --permission-mode bypassPermissions`로 처리 → AI Wiki-layer 구조화 노트(`lint_method: ai`)+엔티티+MOC 생성, raw 불변, Review 비어있음, job done, 텔레그램 회신 발송 모두 정상. (헤드리스 동작에는 `bypassPermissions` 필요 — acceptEdits는 Bash 도구 차단. 무인 launchd ③c에서 이 권한 수위 재확인 필요.)
- **③b — 글로벌 스킬** ✅(2026-06-10): `scripts/install-global-skill.sh` 신규 — 에이전트 비종속 `life-memory` 스킬(SKILL.md)을 `~/.codex/skills/`·`~/.claude/skills/`에 설치. 프로젝트 루트는 설치 시 주입(repo엔 하드코딩 안 함). 어디서든 "라이프 메모리 작업 처리" 호출 가능. `agent.jobsProcessorPath`가 가리키던 미존재 스킬 파일도 이로써 실재하게 됨.
- **③c — 매일 23:00 launchd** ✅(2026-06-10): `scripts/install-ai-jobs-launchd.sh` 신규 — `com.sangmin.life-memory-ai`(python3 직접, `EnvironmentVariables.PATH`로 claude 바이너리 해석, 매일 23:00, 온디맨드 kickstart 가능). **launchd-TCC 실측 통과**: launchd→python3→claude 경로로 통제 테스트 1건 실행 → claude가 launchd 컨텍스트에서 볼트 쓰기 성공, job done(~100s). **GUI 전체디스크접근 부여 불필요**. 4개 launchd 모두 exit 0. (무인 claude는 `bypassPermissions`로 동작 — 가드는 프롬프트의 애매→Review·raw 불변. 매일 1회+pending 있을 때만으로 노출 최소화.)
- **③d — 학습 루프(별도, 가장 큰 범위)**: Review 결정 캡처 → 규칙 저장소 → `classify`/AI lint에 반영해 애매 케이스를 점진적으로 자동화. 독립 페이즈로 추후 설계.

### 진행 원칙
- ③a 코어(부작용 없는 부분)부터 빌드·테스트. 실제 에이전트 실행·매일 launchd 활성화·학습 루프는 각각 별도 확인 지점.

---

## ③d — 학습 루프 상세 설계 (확정 2026-06-10, 미구현)

> 목표: 사용자의 `00_Inbox/Review` 결정을 캡처 → 규칙으로 축적 → 임계 도달 시 자동분류로 **승격** → 이후 동일 패턴은 Review를 거치지 않음.

### 확정된 설계 결정 (사용자, 2026-06-10)
| 항목 | 결정 |
|---|---|
| 결정 캡처 | **AI 처리 시 자동 기록**(ai-lint/ai-repair가 Review 해결 시 결정 저장) + 보조 CLI |
| 규칙 저장소 | **볼트 `90_System/Rules/`** (동기화·사용자 가시, 원자적 쓰기) |
| 승격 임계 | **2회** 일관 확인 + 모순 없음 |
| 매칭 단위(signal) | **키워드/구절**(case-insensitive substring, 기존 classify와 일관) |

### 기존 흐름 (확인됨)
- Review 노트 포맷: `review_type / source_raw / reason / suggested_folder` (docs/review-workflow.md).
- 현재 Review 해결은 대화형이며 **결정이 명시적으로 기록되지 않음**(구조화 노트 생성으로 암묵 소멸). ③d가 이 결정을 영속 기록한다.
- `90_System/Rules/`는 이미 존재(Local Tool Policy.md). 학습 규칙의 집.

### 데이터 모델 — `90_System/Rules/learned-rules.json` (SSOT) + `Learned Rules.md`(자동생성 미러, 사람용)
```jsonc
{
  "version": 1,
  "decisions": [   // append-only 결정 로그
    {"signal": "샤워헤드", "type": "maintenance", "folder": "20_Records/Maintenance",
     "source_raw": "[[00_Inbox/Raw/...]]", "decided_at": "ISO", "by": "ai_repair|cli|frontmatter"}
  ],
  "rules": [       // decisions를 signal별로 집계한 파생 규칙
    {"signal": "샤워헤드", "type": "maintenance", "folder": "20_Records/Maintenance",
     "status": "active|candidate|blocked", "confirmations": 2,
     "examples": ["[[raw1]]","[[raw2]]"], "contradicted": false,
     "created_at": "ISO", "updated_at": "ISO"}
  ]
}
```
- 집계 규칙: signal별 그룹 → 모두 같은 type & count≥2 → `active`; count<2 → `candidate`; 같은 signal에 다른 type 존재 → `blocked`(자동분류 안 함, 사용자 플래그).
- signal 도출: 캡처 주체(AI)가 모호성을 가른 **핵심 키워드**를 지정. CLI 경로는 `--signal` 명시.

### 하위 단계 (결정론적 코어 먼저, 프롬프트 통합 마지막)
- **③d-1 규칙 저장소 모듈** ✅(2026-06-10): `scripts/rules.py`(stdlib) — `RuleStore`(load/save 원자적·`add_decision`·`derive` 집계·`active_rules`·`remove`) + `Learned Rules.md` 미러 + CLI(`add-decision/list/active/remove`, `--rules-file` 격리). 집계: 같은 type 2회↑=active / 미만=candidate / 모순=blocked, 중복 source 미카운트. `tests/test_rules.py` 10건.
- **③d-2 classify 학습-규칙 선패스** ✅(2026-06-10): `mem.py::classify(text, meta, rules=None)` 가산 인자 + `match_learned_rule`(최장 signal 우선 substring) + `FOLDER_BY_TYPE` 폴백. `lint_vault`가 `load_active_rules`로 1회 로드해 전달(실패해도 []→무영향). **빈/None이면 기존과 100% 동일** 확인(P1 12건 무손상, classify는 IO 안 함). 미디어(raw_image 등)는 규칙 매치돼도 needs_review 유지. `tests/test_classify.py` 18건(P1 12 + ③d-2 6).
- **③d-3 CLI** ✅(2026-06-10): `mem.py review list` / `review resolve <file> --type X [--signal kw] [--folder] [--title]` — Review 노트를 구조화 노트로 전환(confidence high, `lint_method: user_resolved`) + `--signal` 시 `rules.add_decision`로 결정 기록 + Review 파일 삭제(**raw 불변**). 감사·취소는 기존 `rules.py list|active|remove` 사용. `tests/test_review_cli.py` 6건(2회 resolve→active 승격 루프 포함).
- **③d-4 프롬프트 통합** ✅(2026-06-10): `ai-lint.md`(우선순위 0 = active 규칙 최우선, step1에 `rules.py active` 적용, 미디어는 needs_review 유지) / `ai-repair.md`(Review 해결 시 `mem.py review resolve --signal` 또는 `rules.py add-decision`로 결정 기록) / `process-pending-jobs.md`(Learning loop 섹션). **⚠️ B(MOC stub) 함께 해결**: ai-lint·ai-repair에 "MOC를 통째로 덮어쓰지 말고 해당 섹션에만 추가, 없으면 init 골격 생성" 지침 추가. 글로벌 스킬은 이 프롬프트를 참조하므로 자동 반영.
- **③d-5 테스트** ✅(2026-06-10): 단위(`test_rules.py` 10·`test_classify.py` ③d-2 6·`test_review_cli.py` 6) + **통합 `test_learning_e2e.py` 2건**(resolve×2→active→`load_active_rules`→classify 자동분류 / learning.enabled=false 시 무규칙). 전체 **81건 GREEN**.

### 사이드 이펙트 분석 (무충돌 근거)
- `rules.py` 신규·독립. `classify` 변경은 **가산적**(default 인자 → 현행 동작). `mem.py` 신규 서브커맨드는 가산적. 기존 57 테스트 무손상 목표.
- 학습 규칙은 **승격(애매→확신)만**, raw 불변·명시 `#tag` 우선 해치지 않음. 모순은 blocked.
- 규칙 저장소 원자적 쓰기. 사용자 감사·취소 가능(`rules remove`, MD 미러).
- 함수 단위 분리: ③d=`classify`/신규, P5=`seek` → 충돌 없음. **단 ③d-4와 백로그 B(MOC stub)는 동일 프롬프트 파일 → 함께/순차 처리 필요.**

### 설정 키 (신규)
`learning`: `{ "enabled": true, "promoteThreshold": 2, "rulesPath": "90_System/Rules/learned-rules.json", "mirrorPath": "90_System/Rules/Learned Rules.md" }`

### DoD
- 빈 저장소에서 기존 동작/테스트 무변화 / 2회 확인 시 signal 자동분류 승격 / 모순 signal은 자동분류 안 함 / 사용자가 규칙 감사·삭제 가능 / raw 불변.

---

## P5 — 검색 품질 강화 (이 시스템의 ROI)

### 목표
"쉽게 꺼내 쓴다"는 비전의 절반. 가장 약한 retrieval을 끌어올린다. (가장 크고 불명확 → 마지막)

### 현재 상태 (확인됨)
- `mem.py::seek`(589): 매 호출 전체 `.md` 스캔 + 단일 substring + 정렬 없이 `limit` 도달 시 임의 절단.
- AI Seek(의미 기반)는 별도 파일이 아니라 `prompts/process-pending-jobs.md` 내부 "AI Seek 프로토콜"에 정의됨(참고: `prompts/ai-seek.md`는 없음).

### 작업 내용 (점진 3단계)
1. ✅ **점수 정렬 + 다중 토큰**(2026-06-10): 공백 분리 토큰 매칭 수(×10) + 제목(×5)·`tags`(×3) 가중, `(score, date)` 내림차순 정렬, 임의 절단 제거(전체 수집 후 상위 `limit`). `make_snippet`로 첫 매칭 토큰 주변 스니펫. 출력에 `score/memory_type/date/total` 추가하되 `path/snippet` 유지(텔레그램 `run_seek_immediate` 하위호환).
2. ✅ **필터 옵션**(2026-06-10): `--type`/`--tag`/`--since`. `--tag`는 `extract_search_tags`(frontmatter `tags:` 리스트 + 본문 `#해시태그`)로 매칭(`parse_frontmatter` 비대칭 회피, 독립 헬퍼). `--since`는 ISO 접두 문자열 비교.
3. ⬜ **(선택·보류) 경량 인덱스 + 한국어 보완**: lint 시점 역색인 JSON, 한국어 bigram/부분일치. 규모 커질 때 착수하는 옵션 단계. (현재 전체 스캔으로 충분, 미착수)

### 방식
1·2단계는 의존성 없이 `seek` 함수만 교체(P1·P2와 다른 함수 → 충돌 없음). 3단계는 불확실성이 커서 별도 후속.

### 테스트 (신규 `tests/test_seek.py`)
- 다중 토큰 쿼리에서 매칭 많은 노트가 상위.
- `--type maintenance` 필터가 타입 외 결과 배제.
- `--since`가 captured_at/updated_at 기준 동작.

### 사용자 경험 개선
관련도순 + 타입/기간 필터로 즉시 답. 캡처·구조화 노력이 비로소 회수됨. P4의 `/seek` 회신 품질도 함께 향상.

### 사용 예시
```bash
python3 scripts/mem.py seek "차량 교체" --type maintenance --since 2026-01
[폰] /seek 작년에 갔던 카페
[봇] 🔍 상위 3건 (food_drink, 관련도순) ...
```

### 완료 조건(DoD)
- 위 테스트 통과 / 기존 단일 쿼리 호환 / 큰 볼트에서 체감 가능한 관련도 향상.

---

## 공통 사항 (모든 페이즈)

- **테스트 디렉터리 신설**: 현재 이 프로젝트엔 `tests/`가 없음(형제 프로젝트엔 있음). 각 페이즈의 테스트를 같은 커밋에 포함해 회귀 방지.
- **커밋 분리**: 페이즈별 독립 커밋/PR. P1·P2·P3 병렬 가능, P4는 P2/P3 이후, P5는 임의 시점.
- **원칙 검증**: 변경마다 CHARTER 4원칙 위배 여부 확인(capture-first / raw-sacred / local-free / sensitive-by-default).
- **회귀 확인**: `python3 scripts/mem.py doctor`로 도구 가용성, 기존 lint→digest 흐름이 깨지지 않는지 매 페이즈 후 점검.

---

## 기존 기록 재분류 감사 (2026-06-10, 완료)

today 개선 반영 전 rule-based lint된 기록을 재검토 → 오분류·잠재이슈 분석 후 수정.

**발견 & 조치:**
- A. 옛 " - " 규칙 잔재 1건(`할일 프로젝트…`→song) — 개선 classify가 `task`로 교정. ✅
- B-1. github/도구 링크 다수가 journal → `classify`에 `github.com`+`설치/라이브러리/오픈소스/repo` 추가(단 `할일` 신호 있으면 task 우선 가드) → product. ✅
- B-2. 정기 송금 → journal → `송금/reminder/리마인더` 키워드를 task에 추가. ✅ (`매주 학원버스` 류는 의도적으로 학습 루프 몫으로 남김 — "둘 다" 전략)
- B-3. 접속정보/주소(reference 성격) → 신규 `reference` 타입은 미도입(구조 변경 커서 보류), 학습 루프로 대응.
- C-1. **중복 캡처 미제거** → `lint_vault`에 content_hash 기반 dedup 추가(raw 보존, 동일 내용 구조화 노트 1개만; `--force` 자기중복 방지). `tests/test_lint_dedup.py` 5건. ✅
- 키워드 보강 테스트 `tests/test_classify.py` +6.

**실볼트 적용**: 백업 후 변경 대상 11 raw만 타겟 리셋 → 재lint. 결과 분류 변경 9 + 중복정리 1, **전 기록이 개선 classify와 일치(불일치 0)**. journal 14→6, product→13, task→3, song 3→2.

**선제 발견 잠재이슈(기록)**: reference 타입 부재(C-2), journal 과적재(C-3) — 학습 루프가 점진 보완. 과거 마커에 content_hash 없어 소급 dedup 불완전(향후 자연 정리).

### 추가 개선 (2026-06-10, 메모 반영)
- **제목 충돌 병합 수정 ★**: `create_structured_note(on_conflict="unique")` — 같은 제목이라도 다른 source_raw면 해시 접미사로 분리(서로 다른 노트 병합 방지), 같은 source면 제자리 덮어쓰기. lint 메인 노트·review resolve에 적용. 엔티티(artist/song)는 기존 append 유지. `tests/test_lint_dedup.py` +3.
- **날짜 정규화 보강(`normalize_dates`)**: 기록 저장일 기준으로 날짜를 `YY.MM.DD` 절대화해 structured note frontmatter `dates`에 추가. 연도없음→올해, 월없이 일만→저장월, 상대표현(오늘/내일/어제·지난달/다음달·작년/내년+M월D일) 환산. 기간표현(N일간/째)·범위초과 제외. lint·review resolve에 배선, ai-lint 프롬프트에도 반영. 실볼트 일정 노트 1건 보강 적용. `tests/test_dates.py` 11.

### 추가 발견 — 음악 엔티티 orphan (2026-06-11)
- **증상**: `40_Entities/Songs`/`Artists`에 task여야 할 "할일 …- 카카오톡 요약봇…" 메모가 song/artist 엔티티로 남아 있음.
- **원인**: 옛 " - " 규칙(P1 이전)이 이를 song으로 오분류 → `extract_artist_song`이 artist/song 엔티티 생성. 이후 재분류(Step3)는 **메인 노트만** task로 교정·삭제했고, **엔티티 노트는 마커에 기록되지 않아(entities_updated=[]) 정리되지 못해 orphan**으로 잔존.
- **조치**: (1) 전체 음악 엔티티의 source_raw를 현재 분류기로 재평가 → orphan 2건만 확인(나머지 4건 정상) → 백업 후 삭제. (2) **재발 방지**: `lint_vault`가 생성한 song/artist 엔티티 경로를 마커 `entities_updated`에 기록 → 향후 song→비song 재분류 시 추적·정리 가능. `tests/test_lint_dedup.py` +2.
- **규칙(교훈)**: song/playlist 재분류·삭제 시 **엔티티 side-effect까지 함께 정리**할 것. 엔티티는 `source_raw`로 역추적해 원본의 현재 분류가 음악이 아니면 orphan으로 판단.

---

## 남은 작업 & 후속 백로그 (2026-06-10 기준)

완료 항목은 위 "현황 대시보드" 참조. 아래는 **미착수/후속** 전부.

### A. 남은 선택/관찰 항목 (주요 페이즈는 모두 완료)
- **③d 관찰**: 실제 AI lint 1회에서 (a) MOC stub 미발생, (b) Review 해결 시 결정 기록 동작 확인 권장.
- **P5 3단계(선택)**: 경량 역색인 + 한국어 bigram. 노트 수가 많아져 전체 스캔이 느려질 때 착수.
- **P5 — 검색 품질**: `mem.py::seek` 점수 정렬 + 다중 토큰 + `--type/--tag/--since` 필터(1·2단계), 경량 인덱스+한국어 보완(3단계, 선택). 위 P5 섹션 참조. `seek`는 P1/P2/③와 다른 함수라 충돌 없음.

### B. 품질 이슈 (관찰됨, 후속 보완)
- **AI lint의 MOC stub 문제** ✅ 프롬프트 보강 완료(2026-06-10, ③d-4와 함께): `ai-lint.md`·`ai-repair.md`에 "MOC를 통째로 덮어쓰지 말고 해당 섹션에만 추가, 없으면 init 골격 생성, 기존 섹션·항목 삭제 금지" 지침 추가. **남은 확인**: 다음 실제 AI lint 실행에서 MOC가 stub로 덮이지 않고 골격이 유지되는지 1회 관찰 권장(프롬프트 준수 검증).
- **실제 볼트 init 미완**(관찰): 실볼트 `70_MOCs/`에 `Music/Life-Memory/Maintenance`만 존재하고 init 템플릿의 나머지 6개(Food/People/Travel/Ideas/Health/Tasks)가 없음. `python3 scripts/mem.py init`을 실볼트에 1회 실행하면 누락 MOC가 생성됨(write_if_missing라 기존 파일 안전). 사용자 확인 후 실행 권장.

### C. 보안·운영 후속
- **무인 `bypassPermissions` 재검토**: ③c의 매일 23:00 claude는 `--permission-mode bypassPermissions`로 동작(가드는 프롬프트뿐). 현재 노출 최소화(1일 1회 + pending 있을 때만)했으나, 더 좁은 권한 모드/허용 도구 제한을 추후 검토 가능.
- **launchd 레이블**: 사용자 결정으로 `com.sangmin.*` 유지 중. 중립화는 보류 상태(원하면 마이그레이션 가능).
- **관측성**: 적체 알림(`maybe_alert`)은 구현됨. 에이전트 실행 실패의 사용자 가시성(텔레그램 실패 알림)은 부분 구현 — 강화 여지.

### D. 코드 정리
- **frontmatter 라운드트립 비대칭** ✅(2026-06-10): `parse_frontmatter`가 `key:` + 들여쓴 `- item`을 리스트로 파싱하도록 개선(스칼라 무변경, 가산적). `frontmatter()` 출력과 라운드트립. `tests/test_reliability.py`에 3건.
- **`title_seed` 표현식 가독성** ✅(2026-06-10): `save_raw`의 헷갈리는 한 줄을 명시적 `if/else`로 교체(동작 동일).

### E. 마무리 작업
- **테스트 일괄 러너** ✅(2026-06-10): `tests/run_all.py` — 모든 `test_*.py` 실행 + 합계 보고(pytest 불필요).
- **커밋**: 전 작업 미커밋(master). 첫 커밋 시점/전략 결정 필요.

### F. P5 3단계 (선택, 보류 결론)
- 검토 결과 **현 시점 불필요로 보류**: 볼트가 ~23노트라 전체 스캔이 즉시 끝나(역색인 불필요), 현재 seek은 이미 **substring 매칭이라 한국어 단일어 부분일치도 동작**(예: "와이퍼"가 "와이퍼교체"에 매치). 역색인+bigram은 노트가 수천 개로 늘거나 오타 보정이 필요해질 때 착수.
