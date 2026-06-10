# My Life Memory Project Handoff

작성일: 2026-06-01  
최종 업데이트: 2026-06-01 (2차 개선 작업 반영)

이 문서는 `life-memory-vault`(My Life Memory) 프로젝트를 이어받는 사용자, Codex, Claude Code, Antigravity, MCP worker, 또는 미래의 AI agent가 프로젝트의 의도와 현재 상태를 빠르게 이해하고 작업을 이어갈 수 있도록 만든 핸드오프 문서다.

---

## 1. 프로젝트 정체성

### 프로젝트 이름

```
My Life Memory
```

### 프로젝트 루트

`memory-config.json` 이 있는 폴더가 프로젝트 루트다. 이 기기에서는:

```
/Users/mini-song/Documents/AI-PlayGround/life-memory-vault
```

### Obsidian Memory Vault

경로는 `memory-config.json` → `memoryVault.vaultPath` 에서 읽는다. 이 기기에서는:

```
/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault
```

### 핵심 정의

이 프로젝트는 사용자가 살아가며 마주치는 크고 작은 기억, 정보, 할 일, 감정, 링크, 파일, 장소, 사람, 물건, 일정, 비용, 음악, 아이디어를 최대한 쉽게 저장하고, AI가 나중에 알아서 구조화하며, 사용자가 필요할 때 다시 쉽게 꺼내 쓰게 만드는 개인 기억 저장 시스템이다.

---

## 2. Soul, Mission, Vision

### Soul

사용자는 정보와 기억의 과잉 속에서 산다. 중요한 것, 사소하지만 나중에 의미가 생길 수 있는 것, 지금은 분류하기 귀찮지만 잊고 싶지 않은 것들이 계속 흩어진다.

이 프로젝트의 영혼은 사용자가 "정리해야 한다"는 부담 없이 기억을 던질 수 있게 해주는 것이다.

### Mission Statement

파편화된 기억이나 정보를 모바일, 랩탑, AI 환경 등 어떤 환경에서든 매우 간단하게 쌓을 수 있어야 한다.

쌓인 기록은 사용자의 개입 없이 Obsidian vault에 잘 구조화되어 정리되어야 한다.

구조화된 기록은 사용자 또는 AI가 어떤 환경에서든 손쉽게 꺼내고 활용할 수 있어야 한다.

### Vision (엔드 이미지)

```
어떤 기기에서든 → 기억을 던진다
                  ↓ (자동)
         Obsidian vault에 구조화 저장
         엔티티 페이지 업데이트
         MOC(지도) 업데이트
                  ↓
         AI에게 물어보면 어디서든 찾아준다
         (Telegram / Claude / ChatGPT / Obsidian)
```

---

## 3. 설계 원칙

### Capture First
기록 순간에는 분류를 요구하지 않는다. 사용자는 그냥 던진다.

### Raw Is Sacred
`00_Inbox/Raw`에 들어간 원본 기록은 절대 수정하거나 삭제하지 않는다. 구조화 노트는 raw로 되돌아가는 `source_raw` 링크를 반드시 가져야 한다.

### Structure Later (Wiki Layer)
정리는 기록 당시가 아니라 이후 AI lint 단계에서 수행한다. AI lint는 단순 분류를 넘어 엔티티 페이지 업데이트, 노트 간 `[[wikilink]]` 삽입, MOC 갱신까지 수행하는 Wiki Layer 구축이 목표다. (Karpathy LLM Wiki + 제텔카스텐 원칙 반영)

### Zettelkasten 링크 원칙
- 노트 하나 = 아이디어/이벤트 하나 (atomic)
- 폴더가 아닌 `[[wikilink]]`로 연결
- MOC(Map of Content)로 카테고리별 진입점 제공
- 엔티티 페이지(`40_Entities/`)는 시간이 지나며 누적되는 Evergreen Note

### Doctor Before Broad Repair
기존 구조화 기록이 잘못 분류되었는지 확인하는 doctor 단계 필요. repair는 doctor 결과나 명확한 사용자 요청을 바탕으로 수행.

### Local First, API-Free First
유료 API 종량 과금은 피하고, 사용자가 이미 구독 중인 Codex, Claude Code, Antigravity 등의 agent 실행을 활용한다.

### Tool-Agnostic Core
중심은 Obsidian vault + 내부 job queue + 프롬프트다. Codex, Claude Code, Antigravity, MCP 등은 adapter/worker로 다룬다.

---

## 4. 전체 아키텍처

```
[모바일 Telegram]
      │ 메시지/파일/명령
      ▼
telegram_collector.py (long-poll, --loop 모드)
      │
   ┌──┴──────────────────────┐
   │                         │
일반 메시지/파일          /slash 명령어
   │                         │
mem.py save              jobs.py add
   │                         │
Obsidian                 memory-state/jobs/
00_Inbox/Raw/            queue-YYYY-MM-DD.jsonl
                              │
                    AI Agent (Claude Code / Codex / 미래 daemon)
                         prompts/process-pending-jobs.md
                              │
                   ┌──────────┼──────────┐
                   │          │          │
               ai-lint    ai-doctor  ai-repair
                   │
         structured notes 생성/업데이트
         40_Entities/ 업데이트
         70_MOCs/ 업데이트
         [[wikilink]] 연결
                   │
            Telegram으로 결과 알림
```

---

## 5. 파일 구조 전체 목록

### 프로젝트 루트

```
life-memory-vault/
├── README.md
├── memory-config.json          ← 개인 설정 (gitignore)
├── memory-config.example.json  ← 설정 템플릿
├── .gitignore
│
├── scripts/
│   ├── mem.py                  ← 핵심 CLI (711줄)
│   ├── telegram_collector.py   ← Telegram 수집기 (447줄)
│   ├── memory_admin.py         ← 로컬 웹 어드민 (305줄)
│   ├── jobs.py                 ← AI 작업 큐 (210줄)
│   ├── scheduled_lint.sh       ← 스케줄 자동 lint 스크립트 ★신규
│   ├── install-launchd.sh      ← MacBook launchd 설치 스크립트 ★신규
│   └── install-memory-tools.sh ← 로컬 도구 설치 가이드
│
├── prompts/
│   ├── ai-lint.md              ← AI Lint 프롬프트 ★전면 개선
│   ├── ai-doctor.md            ← AI Doctor 프롬프트
│   ├── ai-repair.md            ← AI Repair 프롬프트
│   └── process-pending-jobs.md ← Job 처리 워크플로우 ★전면 개선
│
├── commands/                   ← Claude Code slash commands
│   ├── mem-save.md
│   ├── mem-lint.md
│   ├── mem-seek.md             ← ★전면 개선 (6단계 프로토콜)
│   ├── mem-digest.md
│   ├── mem-doctor.md
│   └── mem-repair.md
│
├── .claude/
│   ├── commands/               ← commands/ 와 동기화 유지
│   └── skills/memory-vault.md
│
├── docs/
│   ├── project-handoff.md      ← 이 문서
│   ├── vault-index.md          ← ★신규: 폴더별 용도 + 검색 가이드
│   ├── moc-template.md         ← ★신규: MOC 유지 규칙
│   ├── review-workflow.md      ← ★신규: 00_Inbox/Review 워크플로우
│   ├── telegram-collector.md
│   ├── admin-dashboard.md
│   ├── mobile-ai-commands.md
│   └── life-memory-vault.md
│
├── memory-state/
│   ├── telegram-offset.json    ← Telegram 수신 오프셋
│   ├── telegram-collector.pid  ← collector PID
│   ├── telegram-collector.log  ← collector 로그
│   └── jobs/
│       └── queue-YYYY-MM-DD.jsonl ← AI 작업 큐 (일별)
│
└── skills/
    └── memory-vault.md         ← Codex 전역 스킬 참조
```

### Codex 전역 스킬

경로는 `memory-config.json` → `agent.jobsProcessorPath` 에서 읽는다 (`~` 는 현재 사용자 홈으로 확장):

```
~/.codex/skills/life-memory/SKILL.md
```

---

## 6. Obsidian Vault 구조

```
00_Inbox/
  Raw/           ← 원본 저장 (절대 수정 금지)
  Processed/     ← lint 처리 마커 .json
  Review/        ← 불확실 분류, seek 합성 결과, doctor 격리

10_Timeline/Daily, Weekly, Monthly

20_Records/
  Ledger/        ← 지출/수입
  Health/        ← 병원/약/건강
  Routine/       ← 반복 루틴
  Maintenance/   ← 차량/가전/집 유지보수 ★MOC 있음
  LifeAdmin/     ← 보험/계약/행정

30_Actions/
  Tasks, Shopping, Appointments, Reminders, Decisions

40_Entities/     ← Evergreen Note (시간이 지나며 누적)
  People, Groups, Places, Things, Situations
  Artists, Songs, Albums

50_Experiences/
  Trips, Food_Drink, Events, Visits
  Music/Listening_Log, Music/Concerts

60_Ideas/
  Projects, Writing, Products, Questions, Playlists

70_MOCs/         ← Map of Content (AI lint가 유지 관리)
  Life-Memory-MOC.md  ← 전체 진입점
  Music-MOC.md
  Maintenance-MOC.md  ★신규
  Food-MOC.md         ★신규
  People-MOC.md       ★신규
  Travel-MOC.md       ★신규
  Ideas-MOC.md        ★신규
  Health-MOC.md       ★신규
  Tasks-MOC.md        ★신규

80_Assets/Originals + Extracts (pdf/images/audio/video)

90_System/
  Memory Charter.md
  Schemas/Memory Schema.md  ← ★필드 확장됨
  Rules/Local Tool Policy.md
  Logs/                     ← doctor/repair 보고서
  Prompts/
```

---

## 7. 스크립트별 상세 기능

### 7.1 `scripts/mem.py` (711줄)

핵심 CLI. 6개 서브커맨드.

#### 주요 상수
- `FOLDER_LAYOUT`: 52개 폴더 목록
- `HASHTAG_SENSITIVITY`: `{"private", "비공개", "민감"}` ★신규
- `HASHTAG_TYPE_HINTS`: `{"task": "task", "할일": "task", ...}` ★신규
- `LIFE_MEMORY_MOC`, `MAINTENANCE_MOC`: init 시 생성할 MOC 템플릿 ★신규

#### 주요 함수

| 함수 | 역할 |
|---|---|
| `init_vault()` | 폴더 52개 + 시스템 파일 생성. MOC 8개 포함 ★개선 |
| `parse_hashtags(text)` | `#태그` 파싱 → sensitivity/type 추출 ★신규 |
| `save_raw(args, config)` | Raw 노트 저장. hashtags 파싱 + sensitivity 자동 설정 ★개선 |
| `infer_raw_type()` | 파일 확장자/URL로 raw_type 자동 감지 |
| `classify(text, meta)` | 키워드 기반 memory_type + 폴더 결정 |
| `lint_vault(args, config)` | Rule-based lint. 마커에 `lint_method: "rule_based"` 기록 ★개선 |
| `seek(args, config)` | 전체 vault 텍스트 검색 (grep 방식) |
| `digest(config)` | raw/processed 카운트 + 타입별 통계 |
| `doctor(config, path)` | 로컬 툴 13개 설치 여부 점검 |

#### Raw Note Frontmatter 스키마 (현재 버전)

```yaml
---
id: "sha1[:12]"
captured_at: "2026-06-01T22:00:00+09:00"
source: "telegram | manual | codex"
raw_type: "raw_text | raw_url | raw_youtube | raw_pdf | raw_image | raw_audio | raw_video | raw_file"
status: "pending"
sensitivity: "normal | private"
source_url: ""
attachments: []
hashtags: ["task", "private"]   ← ★신규: 인라인 #태그 자동 파싱
---
```

#### Structured Note Frontmatter 스키마 (현재 버전)

```yaml
---
memory_type: "maintenance | task | song | ..."
source_raw: "[[00_Inbox/Raw/경로/파일]]"
confidence: "high | medium | low"
needs_review: false
sensitivity: "normal | private"
tags: ["차량", "소모품"]              ← ★신규
related: ["[[40_Entities/Things/내 차량]]"] ← ★신규
updated_at: "2026-06-01T22:00:00+09:00"    ← ★신규
lint_method: "rule_based | ai"              ← ★신규
entity_refs: ["40_Entities/Things/내 차량.md"] ← ★신규
---
```

#### Processed 마커 스키마 (현재 버전)

```json
{
  "raw": "00_Inbox/Raw/...",
  "structured": "20_Records/Maintenance/...",
  "processed_at": "2026-06-01T22:00:00+09:00",
  "lint_method": "rule_based",      ← ★신규
  "plan": { "memory_type": "...", "folder": "...", "confidence": "...", "needs_review": false },
  "entities_updated": [],           ← ★신규 (AI lint 시 채워짐)
  "links_added": [],                ← ★신규
  "mocs_updated": []                ← ★신규
}
```

AI lint가 처리하면:

```json
{
  "lint_method": "ai",
  "ai_model": "claude-sonnet-4-6",
  "entities_updated": ["40_Entities/Things/내 차량.md"],
  "links_added": ["[[40_Entities/Things/내 차량]]"],
  "mocs_updated": ["70_MOCs/Maintenance-MOC.md", "70_MOCs/Life-Memory-MOC.md"]
}
```

---

### 7.2 `scripts/telegram_collector.py` (447줄)

표준 라이브러리만 사용 (`urllib`). `python-telegram-bot` 불필요.

#### 주요 함수

| 함수 | 역할 |
|---|---|
| `run_seek_immediate(config_path, query)` | keyword 검색 즉시 실행, Telegram 회신용 포맷 반환 ★신규 |
| `run_status_immediate(config_path)` | digest 즉시 실행, Telegram 회신용 포맷 반환 ★신규 |
| `get_pending_count(config_path)` | 미처리 raw note 수 반환 ★신규 |
| `build_save_ack(save_result, pending)` | 저장 완료 ack 메시지 생성 ★신규 |
| `process_update(...)` | 메시지 처리 분기 (명령어/일반) ★개선 |
| `parse_telegram_command(text)` | `/command` 파싱 |
| `run_mem_save(...)` | mem.py save 서브프로세스 실행 |
| `run_job_add(...)` | jobs.py add 서브프로세스 실행 |
| `poll_once(...)` | Telegram getUpdates 1회 실행 |

#### 메시지 처리 분기 (현재 버전)

```
수신된 Telegram update
  → allowedUserIds 화이트리스트 검사
  → parse_telegram_command() 시도
      │
      ├─ /seek [쿼리]
      │    → run_seek_immediate() → 즉시 Telegram 회신 ★신규
      │    → run_job_add("seek") → AI seek job도 큐에 등록
      │
      ├─ /status
      │    → run_status_immediate() → 즉시 Telegram 회신 ★신규
      │    → (job queue 불필요)
      │
      ├─ /lint, /doctor, /repair, /digest
      │    → run_job_add(job_type) → job queue 등록
      │    → 맥락 있는 ack 메시지 전송 ★개선
      │
      └─ 일반 메시지/파일
           → pick_file() (첨부파일 있으면 임시 다운로드)
           → run_mem_save() → 00_Inbox/Raw 저장
           → build_save_ack(result, pending_count) → 개선된 ack ★신규
```

#### ack 메시지 예시 (현재 버전)

```
일반 저장:
"✓ 저장 완료 (텍스트) | 미처리 7건 누적
/lint 로 정리 요청"

#private 포함:
"✓ 저장 완료 (이미지) 🔒 #private | 미처리 3건 누적
/lint 로 정리 요청"

/lint 요청:
"📋 정리 작업 요청 등록
Job ID: abc123def
AI 처리 후 결과를 알려드릴게요."

/status 요청 (즉시 답변):
"📊 Life Memory 상태
Raw 노트: 15건
처리 완료: 8건
미처리: 7건
주요 분류: song 3건, task 2건, maintenance 1건"
```

#### 네트워크 에러 로그 (`telegram_network_retry`) 설명

Admin 대시보드 로그에 다음과 같은 메시지가 대량 쌓이는 것은 **정상 동작**이다:

```json
{"warning": "telegram_network_retry", "message": "<urlopen error [Errno 8] nodename nor servname provided, or not known>"}
```

의미: MacBook이 오프라인(잠자기/Wi-Fi 끊김)일 때 `api.telegram.org` DNS 조회 실패. 10초 대기 후 재시도. 수집기가 죽지 않고 살아있다는 증거. 인터넷 연결 복구 시 자동 정상화.

---

### 7.3 `scripts/memory_admin.py` (305줄)

`http.server` 기반 로컬 웹 어드민. 포트 8765. 외부 의존성 없음.

**실행:**
```bash
python3 scripts/memory_admin.py
# → http://127.0.0.1:8765
```

**주의:** 코드 변경 후에는 반드시 프로세스 재시작 필요.
```bash
lsof -i :8765 | grep LISTEN  # PID 확인
kill [PID]
python3 scripts/memory_admin.py &
```

#### 현재 기능 (★개선 항목 포함)

| 기능 | 설명 |
|---|---|
| Telegram 수집기 켜기/끄기 | `subprocess.Popen` + PID 파일 관리 |
| Rule-based 즉시 정리 | `mem.py lint` 실행 ★버튼 분리 |
| AI Lint Job 등록 | `jobs.py add lint` 실행 → Codex/Claude에서 처리 ★신규 |
| Job Queue 현황 | 타입별 pending/running/done/failed 표 ★신규 |
| Digest 표시 | raw/processed 카운트 |
| 수집기 로그 | 최근 60줄 |

#### 주요 함수

| 함수 | 역할 |
|---|---|
| `enqueue_ai_lint()` | jobs.py add lint 실행 ★신규 |
| `run_jobs(command)` | jobs.py 서브커맨드 실행 ★신규 |
| `_job_counts_html(job_summary)` | job 현황 HTML 테이블 생성 ★신규 |
| `status()` | collector 상태 + digest + job summary ★개선 |
| `page(message)` | 전체 HTML 페이지 생성 ★개선 |

---

### 7.4 `scripts/jobs.py` (210줄)

AI 작업 큐. JSONL 포맷, 일별 파일.

#### 파일 위치

```
memory-state/jobs/queue-YYYY-MM-DD.jsonl
```

#### Job 스키마

```json
{
  "id": "sha1[:12]",
  "type": "lint | doctor | repair | seek | digest | status",
  "status": "pending | running | done | failed | cancelled",
  "created_at": "2026-06-01T22:00:00+09:00",
  "updated_at": "2026-06-01T22:05:00+09:00",
  "adapter": "codex",
  "payload": {
    "query": "",
    "raw_text": "",
    "requested_by": "466137686",
    "source": "telegram",
    "chat_id": "123456789",
    "message_id": "42"
  },
  "result": {},
  "notes": []
}
```

`chat_id`와 `message_id`는 AI가 결과를 Telegram으로 회신할 때 사용한다.

#### 주요 명령

```bash
python3 -B scripts/jobs.py add lint --text "요청 내용" --adapter codex
python3 -B scripts/jobs.py list --status pending
python3 -B scripts/jobs.py next
python3 -B scripts/jobs.py set-status <id> running --note "Started by Claude Code"
python3 -B scripts/jobs.py set-status <id> done --note "Finished" --result-json '{"processed": 3}'
python3 -B scripts/jobs.py summary
```

---

### 7.5 `scripts/scheduled_lint.py` (launchd) / `scheduled_lint.sh` (수동)

미처리 raw note 감지 → AI lint job 등록 + rule-based lint 즉시 실행.

> launchd 는 `scheduled_lint.py` 를 `python3` 로 직접 실행한다. 과거 `/bin/bash
> scheduled_lint.sh` 형태는 macOS TCC 때문에 `~/Documents` 하위 스크립트 실행이
> 막혀 exit 126 으로 실패했다. `.sh` 는 셸에서 수동 실행할 때만 사용한다.

```bash
# launchd 설치 (MacBook 매일 22:00 / Mac mini 2시간마다)
bash scripts/install-launchd.sh

# 수동 실행 (셸에서는 TCC 영향 없음)
python3 scripts/scheduled_lint.py

# 로그 확인
cat memory-state/scheduled-lint.log
```

---

## 8. 프롬프트 상세

### 8.1 `prompts/ai-lint.md` ★전면 개선

**7단계 처리 프로세스:**

1. Raw note 읽기 + `#태그` 파싱 + memory_type 결정
2. `40_Entities/`에서 관련 엔티티 탐색 → 있으면 업데이트, 없으면 신규 생성 판단
3. Structured note 생성 (tags, related, updated_at, lint_method, entity_refs 포함)
4. `[[wikilink]]` 삽입 (structured ↔ entity 양방향)
5. 해당 MOC 업데이트 (`70_MOCs/`)
6. Processed 마커 저장 (lint_method: "ai", entities_updated, links_added, mocs_updated 기록)
7. 처리 요약 리포트 + job `chat_id` 있으면 Telegram 발송

**핵심: rule-based lint와의 차이**

| | rule-based (`mem.py lint`) | AI lint (`ai-lint.md`) |
|---|---|---|
| 분류 방식 | 키워드 매칭 | 의미 이해 |
| 엔티티 업데이트 | 없음 | 있음 |
| wikilink 삽입 | 없음 | 있음 |
| MOC 업데이트 | 없음 | 있음 |
| 실행 속도 | 즉시 | 수분 |
| 트리거 | 자동 가능 | AI 도구 필요 |
| 마커 | lint_method: "rule_based" | lint_method: "ai" |

rule-based가 이미 처리한 노트도 AI lint로 재처리 가능 (마커의 lint_method로 구분).

### 8.2 `prompts/process-pending-jobs.md` ★전면 개선

AI agent가 job queue를 처리할 때의 완전한 워크플로우.

주요 추가 내용:
- `docs/vault-index.md` 참조 지시
- **AI Seek 프로토콜**: vault-index → MOC → keyword → 전체 컨텍스트 로딩 → 합성 → Telegram 회신 → 선택적 저장
- **Lint 완료 Telegram 알림 형식**
- **Digest/Status 프로토콜**

### 8.3 `prompts/ai-doctor.md`

Vault 품질 감사. 파일 수정 없이 보고서만 작성.

점검 항목: 잘못 분류된 노트, 중복, source_raw 누락, 미처리 raw, needs_review 항목, 민감 정보 노출 위험, 깨진 첨부파일 링크

보고서 위치: `90_System/Logs/doctor-YYYY-MM-DD.md`

### 8.4 `prompts/ai-repair.md`

Doctor 보고서 또는 사용자 요청 기반 수정.

안전 수정 (즉시 가능): 폴더 이동, source_raw 추가, needs_review 설정, aliases/tags/cross-links 추가

사용자 확인 필요: 삭제, raw 노트 편집, 모호한 병합, 민감 정보 이동, 광범위 변경

---

## 9. 신규 문서

### 9.1 `docs/vault-index.md` ★신규

AI agent가 검색 전 범위를 좁히기 위한 정적 가이드.

- 전체 폴더별 용도 설명 표
- 카테고리별 검색 범위 좁히기 가이드 (차량 → `20_Records/Maintenance/`, 음악 → `70_MOCs/Music-MOC.md` 등)
- AI 검색 프로토콜 (vault-index → MOC → keyword → 전체 컨텍스트 → 합성)

**AI agent는 검색 시 반드시 이 문서를 먼저 참조할 것.**

### 9.2 `docs/moc-template.md` ★신규

MOC 파일 목록과 AI lint의 MOC 업데이트 규칙 정의.

### 9.3 `docs/review-workflow.md` ★신규

`00_Inbox/Review/` 폴더의 3가지 용도와 처리 워크플로우:

1. AI lint가 낮은 confidence로 분류한 노트 (`review-lint-날짜-제목.md`)
2. mem-seek 합성 결과 저장 (`seek-날짜-검색어.md`)
3. AI doctor 격리 노트 (`doctor-날짜-이슈.md`)

---

## 10. Claude Code 슬래시 커맨드

`.claude/commands/`와 `commands/` 두 위치에 동일한 파일이 있다. **항상 동기화 유지.**

동기화 명령:
```bash
cp commands/mem-seek.md .claude/commands/mem-seek.md
# (나머지 파일도 동일)
```

| 커맨드 | 핵심 동작 |
|---|---|
| `/mem-save` | `mem.py save` 실행. "기억해줘"/"저장해줘" 트리거 |
| `/mem-lint` | `mem.py lint` (rule-based) + AI lint 안내 |
| `/mem-seek` | **6단계 프로토콜**: vault-index → MOC → keyword → 전체 로딩 → 합성 → 선택적 저장 ★전면 개선 |
| `/mem-digest` | `mem.py digest` + AI 요약 |
| `/mem-doctor` | CLI 점검 + AI 감사 보고서 |
| `/mem-repair` | AI 가이드 수리. 파괴적 변경 전 반드시 질문 |

---

## 11. Telegram 명령 전체 동작표

| 명령 | 현재 동작 | 결과 전달 방식 |
|---|---|---|
| 일반 메시지/파일 | Raw 저장 즉시 | ack 메시지 즉시 |
| `/seek [검색어]` | keyword 결과 즉시 + AI job 등록 | **즉시 Telegram 회신** ★신규 |
| `/status` | digest 즉시 실행 | **즉시 Telegram 회신** ★신규 |
| `/lint` | job queue 등록 | AI 처리 완료 후 Telegram 알림 |
| `/doctor` | job queue 등록 | AI 처리 완료 후 Telegram 알림 |
| `/repair` | job queue 등록 | AI 처리 완료 후 알림 |
| `/digest` | job queue 등록 | AI 처리 완료 후 알림 |

---

## 12. 미디어/파일 처리 방향

### 처리 도구 우선순위

1. `pdfplumber`, `pdftext` — 가벼운 PDF 텍스트
2. `marker_single` — 복잡한 PDF to Markdown
3. `paddleocr_file`, `paddleocr_mcp` — OCR, 한국어 OCR
4. `tesseract` — OCR fallback
5. `yt-dlp`, `youtube-transcript-api` — YouTube
6. `markitdown` — 범용 문서 변환
7. `kordoc MCP` — HWP/HWPX/HWPML

### 크기 기준

- ~20MB: vault 내 Originals에 저장
- 20~100MB: 로컬에 있을 때만 저장
- 100MB 초과: external 링크만 저장
- 동영상 50MB 초과 or 10분 초과: external 기본

### 미완성 파이프라인

다음은 도구는 있지만 자동 파이프라인 미완성:
- YouTube transcript 자동 추출
- 음성 STT 자동 처리
- PDF 자동 OCR 및 extract 노트 생성
- 동영상 keyframe/transcript 자동 저장

---

## 13. 현재 구축 현황 (2026-06-01 기준)

```
Phase 1: 캡처 (Telegram → Raw)          ██████████ 100%  ✅ 완성
Phase 2: Rule-based Lint                 ████████░░  80%  ✅ 작동
Phase 3: AI Lint 인프라                  ██████░░░░  60%  🟡 수동 트리거만
Phase 4: AI Seek                         █████░░░░░  50%  🟡 수동 트리거만
Phase 5: Telegram 명령                   ███████░░░  70%  🟡 일부 즉시 응답
Phase 6: 자동화 (스케줄러)               ████░░░░░░  40%  🟡 스크립트 완성, 미설치
Phase 7: Admin 대시보드                  █████████░  90%  ✅ 작동
Phase 8: MCP 서버                        ░░░░░░░░░░   0%  ❌ 미착수
Phase 9: Mac mini 이전                   ░░░░░░░░░░   0%  ❌ 미착수
```

### 지금 당장 동작하는 것

- Telegram → Raw 저장 (텍스트/사진/파일/URL/YouTube)
- `#해시태그` → sensitivity/type 자동 설정
- 개선된 ack 메시지 (타입 + 미처리 건수)
- `/status` 즉시 Telegram 응답
- `/seek` 즉시 keyword 결과 Telegram 응답
- Rule-based lint (`mem.py lint`)
- Admin 대시보드 (job queue 현황, 버튼 분리)
- `mem.py seek/digest/doctor` CLI

### 동작하지만 수동 트리거 필요한 것

- AI lint (Claude Code/Codex에서 "life-memory pending 처리해줘")
- AI seek 합성 답변 (Claude Code에서 직접 요청)
- `/lint /doctor /repair /digest` 결과 Telegram 회신
- 스케줄러 (`bash scripts/install-launchd.sh` 설치 필요)

### 미구현 (코드 없음)

- AI job 자동 처리 daemon
- MCP 서버
- Mac mini 이전
- 파일 처리 자동 파이프라인 (YouTube transcript, 음성 STT 등)

---

## 14. 현재 알려진 이슈

### 이슈 1: Rule-based lint 오분류

`classify()` 함수의 키워드 기반 분류는 맥락 파악 불가. 짧은 메모나 키워드가 없는 텍스트는 모두 `journal`로 분류. AI lint로 재처리 필요.

처리 방법:
```bash
# rule-based로 처리된 것을 AI lint로 재처리
# ai-lint.md의 "lint_method: 'rule_based'" 마커 탐색 후 재처리
```

### 이슈 2: AI lint의 Telegram 알림이 자동이 아님

`process-pending-jobs.md`에 Telegram 회신 지시가 있지만, AI가 이를 따르려면 `telegram_collector.py`의 `send_message()` 함수를 직접 호출하거나 별도 스크립트로 발송해야 한다. 현재는 AI agent가 수동으로 이 로직을 실행해야 함.

향후 해결 방향: `scripts/notify.py` 유틸리티 스크립트 추가로 단순화 예정.

### 이슈 3: MOC가 AI lint 전까지 비어있음

`mem.py init`으로 8개 MOC 파일이 생성되지만 섹션 헤더만 있는 빈 파일. AI lint가 처음 실행될 때부터 항목이 채워진다. Rule-based lint는 MOC를 업데이트하지 않는다.

### 이슈 4: `/lint /digest` 결과가 Telegram으로 자동 회신 안 됨

현재 job queue에만 등록되고 AI가 처리해도 결과가 자동 발송되지 않는다. AI agent가 `process-pending-jobs.md`의 지시를 따라 수동으로 `send_message()`를 호출해야 함.

### 이슈 5: `.claude/commands/`와 `commands/` 동기화 수동 관리

두 폴더를 수동으로 동기화해야 한다. 파일 변경 시 반드시 둘 다 업데이트.

---

## 15. 남은 개발 과제 (우선순위 순)

### 🔴 1순위: 스케줄러 설치 (1시간)

```bash
bash scripts/install-launchd.sh
```

효과: 매일 22:00 자동 rule-based lint + AI lint job 등록.

### 🔴 2순위: AI Lint 실제 검증 (1회 수행)

Telegram으로 5~10개 메모 저장 후 전체 AI lint 워크플로우를 처음부터 끝까지 실행해서 검증.

```
1. Telegram으로 메모 5개 저장 (다양한 타입)
2. /lint 전송 → job queue 확인
3. Claude Code: "life-memory pending 작업 처리해줘"
4. 결과 확인:
   - 40_Entities/ 에 엔티티 페이지 생성/업데이트 여부
   - 70_MOCs/ 항목 추가 여부
   - [[wikilink]] 삽입 여부
   - Telegram 알림 도착 여부
5. process-pending-jobs.md의 Telegram 알림 부분 실제 동작 확인/수정
```

### 🟡 3순위: `scripts/notify.py` 유틸리티 추가

AI agent가 Telegram 메시지를 쉽게 발송할 수 있는 독립 스크립트.

```bash
python3 scripts/notify.py --chat-id 123456 --message "lint 완료: 5건 처리"
```

현재는 AI가 `telegram_collector.py`의 `send_message()` 함수를 직접 참조해야 해서 불편.

### 🟡 4순위: Admin 대시보드 → Review 폴더 건수 표시

`docs/review-workflow.md`에 정의된 Review 폴더 활용을 위해 대시보드에 "검토 대기: N건" 표시 추가.

### 🟡 5순위: Mac mini 이전

```
준비 사항:
- Mac mini에 프로젝트 복사 또는 git 관리 시작
- vault Google Drive sync 확인
- .env와 memory-config.json 안전 이전
- launchd → cron 전환 (Mac mini)
- MacBook collector 자동 실행 해제
```

### 🟠 6순위: MCP 서버 구축

```
Local MCP 목표 tools:
- mem_save(text, source)
- mem_seek(query)
- mem_digest()
- job_add(type, text)
- job_status(id)

Remote MCP (Mac mini 이후):
- 인증 필수
- read-only / write 권한 분리
- 민감 정보 접근 범위 제한
```

### 🟠 7순위: 파일 처리 파이프라인 자동화

YouTube transcript, 음성 STT, PDF OCR, 이미지 OCR의 자동 처리 파이프라인 완성.

---

## 16. 운영 가이드

### MacBook에서 수집기 시작

```bash
# Admin 대시보드에서 켜기 버튼 클릭 (권장)
python3 scripts/memory_admin.py
# http://127.0.0.1:8765 → "수집기 켜기"

# 또는 터미널 직접 실행 (프로젝트 루트 = memory-config.json 이 있는 폴더)
cd /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
python3 scripts/telegram_collector.py --loop
```

### Admin 대시보드

```bash
python3 scripts/memory_admin.py
# → http://127.0.0.1:8765
```

대시보드 기능:
- 수집기 켜기/끄기
- **Rule-based 즉시 정리** (키워드 기반, 즉시 실행)
- **AI Lint Job 등록** (job queue에 추가, Codex/Claude로 처리)
- **Job Queue 현황** 패널
- Digest 및 로그 확인

### Codex/Claude에서 job 처리

```
life-memory pending 작업 처리해줘
life-memory, mem-lint 실행해줘
life-memory, mem-doctor 실행해줘
life-memory, mem-seek "차량용품 교체 언제 했어?"
```

### Telegram에서 사용

```
일반 메모: 그냥 텍스트 전송
URL 저장: URL 전송
사진 저장: 사진 전송 (캡션 선택)
#태그 활용: "#private 민감한 내용" or "#task 해야할 일"

즉시 응답 명령:
/status   → 볼트 현황 즉시 확인
/seek [검색어]  → keyword 검색 즉시 확인

AI 작업 요청:
/lint     → Raw 기록 AI 정리 요청
/doctor   → 볼트 상태 점검 요청
/repair   → 문제 수정 요청
/digest   → 상세 요약 요청
```

### vault-index.md 검색 가이드 활용

AI에게 검색 요청 시 vault-index.md를 먼저 확인하도록 지시:

```
"docs/vault-index.md 참조해서 차량 관련 기억 찾아줘"
```

---

## 17. 다음 작업자가 반드시 기억할 것

1. **Raw note는 절대 수정하거나 삭제하지 않는다.** 원본 증거.
2. **Rule-based lint (`mem.py lint`)는 AI lint의 MVP일 뿐이다.** 최종 목표는 AI lint.
3. **AI lint는 단순 분류가 아니다.** 엔티티 업데이트 + wikilink 삽입 + MOC 갱신까지 수행해야 한다.
4. **`docs/vault-index.md`는 AI 검색의 첫 번째 참조 문서다.** 검색 전 반드시 확인.
5. **MOC 8개는 AI lint가 처음 실행될 때까지 비어있다.** 정상이다.
6. **`commands/`와 `.claude/commands/`를 항상 동기화한다.**
7. **Telegram bot은 mailbox이고, collector가 실제 저장자다.** 두 역할 혼동 금지.
8. **`telegram_network_retry` 로그는 에러가 아니다.** 오프라인 상태의 재시도 기록.
9. **job의 `chat_id`를 활용해 AI 작업 결과를 Telegram으로 회신한다.**
10. **API 종량 과금은 기본적으로 피한다.** Codex/Claude Code 구독 활용.
11. **애매한 repair, 삭제, 병합, 민감 정보 노출은 반드시 사용자에게 먼저 물어본다.**

---

## 18. 변경 이력

### 2026-06-01: 1차 구축 (초기 MVP)

- `mem.py` MVP CLI 구현
- `telegram_collector.py` 구현
- `memory_admin.py` 구현
- `jobs.py` 구현
- rule-based lint MVP
- Telegram slash command → job queue 연결
- AI lint/doctor/repair 프롬프트 초안
- Codex 전역 skill 추가

### 2026-06-01: 2차 개선 (Karpathy LLM Wiki + 제텔카스텐 반영)

**구조 개선:**
- `docs/vault-index.md` 신규 — 폴더별 용도 + 검색 가이드
- `docs/moc-template.md` 신규 — MOC 유지 규칙
- `docs/review-workflow.md` 신규 — Review 워크플로우 정의
- `mem.py init` — MOC 8개 추가 (Life-Memory, Music, Maintenance, Food, People, Travel, Ideas, Health, Tasks)
- Raw/Structured note frontmatter 스키마 강화 (`hashtags`, `tags`, `related`, `updated_at`, `lint_method`, `entity_refs`)
- Processed 마커 스키마 강화 (`lint_method`, `entities_updated`, `links_added`, `mocs_updated`)

**AI Lint 완성:**
- `prompts/ai-lint.md` 전면 재작성 — 7단계 프로세스, 엔티티 업데이트, wikilink, MOC 갱신 포함

**캡처 개선:**
- `parse_hashtags()` — `#private`, `#task` 등 인라인 태그 자동 파싱
- `build_save_ack()` — 타입 + 미처리 건수 포함 개선된 ack

**Telegram 명령 개선:**
- `/seek` — keyword 결과 즉시 Telegram 회신 + AI job 병렬 등록
- `/status` — 즉시 digest 결과 Telegram 회신 (job queue 우회)
- 나머지 명령 — 맥락 있는 ack 메시지

**Seek 고도화:**
- `commands/mem-seek.md` 전면 재작성 — 6단계 프로토콜 (vault-index → MOC → keyword → 전체 컨텍스트 → 합성 → 선택적 저장)

**Admin 대시보드 개선:**
- Job Queue 현황 패널 추가
- lint 버튼 분리 (Rule-based / AI Lint Job 등록)
- `enqueue_ai_lint()`, `run_jobs()` 함수 추가

**자동화:**
- `scripts/scheduled_lint.sh` 신규 — 미처리 감지 → AI job 등록 + rule-based lint
- `scripts/install-launchd.sh` 신규 — MacBook launchd 설치

**프로세스 문서 개선:**
- `prompts/process-pending-jobs.md` 전면 재작성 — AI Seek/Lint/Digest/Status 프로토콜 + Telegram 알림 형식
