# Life Memory Vault Safety Improvement Work Order

작성일: 2026-06-13

## 목적

이 문서는 Life Memory Vault 프로젝트의 안전성 개선 작업지시서다. 어떤 AI 서비스나 모델이든 이 문서만 읽고도 다음을 이해할 수 있어야 한다.

- 이 프로젝트가 어떤 시스템인지
- 어떤 부분이 왜 위험하거나 취약한지
- 어떤 순서로 개선해야 하는지
- 작업 중 절대 건드리면 안 되는 기록과 파일이 무엇인지
- 개선 완료를 어떻게 검증해야 하는지

이 문서는 구현 코드가 아니라 작업 지시서다. 실제 개선 작업을 시작하기 전에는 반드시 현재 코드와 테스트를 다시 읽고, 이 문서의 지시와 현재 코드 상태가 다른 경우 현재 코드 상태를 우선 확인한 뒤 보수적으로 진행한다.

## 프로젝트 요약

Life Memory Vault는 개인 기억 저장소를 운영하기 위한 로컬 우선 도구다.

주요 흐름:

```text
Telegram / CLI
  -> scripts/telegram_collector.py 또는 scripts/mem.py save
  -> Obsidian vault의 00_Inbox/Raw 에 원본 기록 저장
  -> scripts/mem.py lint / enrich / review / reclassify / prune-orphans
  -> 구조화 노트, processed marker, Review 항목, 요약 블록 생성
  -> scripts/jobs.py 큐와 process_jobs.py / process_ai_jobs.py 로 자동 처리
```

핵심 원칙:

- Raw 기록은 원본이다. 절대 수정하거나 삭제하면 안 된다.
- 구조화 노트, marker, MOC, Review 항목은 raw에서 파생된 결과물이다.
- AI 자동화는 편의를 위한 도구일 뿐이며, 원본 기록의 무결성을 침해하면 안 된다.
- 개인 기록이 포함될 수 있으므로 보안 기본값은 항상 보수적으로 잡는다.

## 절대 작업 금지 사항

개선 작업 중 아래 항목은 명시적 사용자 승인 없이 절대 변경하지 않는다.

- 실제 Obsidian vault의 `00_Inbox/Raw` 안의 원본 기록
- 실제 개인 메모 내용
- `memory-state/jobs/*.jsonl`의 실제 큐 상태
- `.env`
- `memory-config.json`
- 실제 Telegram token, chat id, 개인 계좌, 연락처, 개인 식별 정보
- Google Drive/Obsidian vault 안의 실제 노트 삭제
- `prune-orphans --apply`, `reclassify --apply`, `dedup-markers --apply` 같은 적용형 명령

리뷰나 검증이 필요할 때는 가능한 한 dry-run, 임시 디렉터리, 테스트 fixture를 사용한다.

## 작업 전 필수 확인

작업자는 먼저 아래를 읽고 현재 상태를 파악한다.

- `README.md`
- `docs/operator-guide.md`
- `docs/project-handoff.md`
- `memory-config.example.json`
- `scripts/mem.py`
- `scripts/jobs.py`
- `scripts/process_jobs.py`
- `scripts/process_ai_jobs.py`
- `scripts/enrich.py`
- `scripts/telegram_collector.py`
- `tests/run_all.py`
- 관련 테스트 파일 전체

작업 전 확인 명령 예시:

```bash
git status --short
python3 -B tests/run_all.py
python3 -B scripts/process_ai_jobs.py --dry-run --limit 1
python3 -B scripts/mem.py enrich --dry-run --limit 5
python3 -B scripts/mem.py prune-orphans
```

주의: 위 명령 중 `prune-orphans`는 기본 dry-run이다. `--apply`를 붙이지 않는다.

## 개선 우선순위

반드시 아래 순서로 진행한다.

1. 무인 AI 실행 권한 축소
2. URL enrich의 로컬/내부망 fetch 방어
3. job queue claim/lease/recovery 개선
4. destructive 명령의 2단계 적용 구조
5. `scripts/mem.py` 모듈 분리

각 단계는 독립적으로 테스트 가능해야 한다. 한 단계가 끝날 때마다 테스트를 통과시키고, 실제 개인 기록에는 쓰지 않았음을 확인한다.

---

## 1. 무인 AI 실행 권한 축소

### 왜 필요한가

현재 AI job 처리 경로는 `scripts/process_ai_jobs.py`가 headless agent를 호출해 pending job을 처리하는 구조다. 예시 설정에서는 Claude가 다음과 같이 실행될 수 있다.

```json
"claude": ["claude", "-p", "{prompt}", "--permission-mode", "bypassPermissions"]
```

이는 비개발자에게 비유하면, AI에게 "집 전체 마스터키"를 주고 "안방은 들어가지 마"라고 안내문을 붙여 둔 상태와 비슷하다.

프롬프트에는 raw 기록을 수정하지 말라는 규칙이 있지만, 프롬프트는 잠금장치가 아니다. 외부 웹본문, 사용자가 저장한 메모, 악의적인 텍스트가 AI에게 "이전 지시를 무시하고 파일을 고쳐라" 같은 문장을 포함할 수 있다. 이를 prompt injection이라고 부른다.

목표는 AI를 못 믿는 것이 아니라, AI가 실수해도 큰 피해가 나지 않도록 작업별 열쇠만 주는 것이다.

### 목표 상태

AI job type마다 가능한 작업 범위를 명확히 제한한다.

예시:

```text
lint job:
  허용:
    - 00_Inbox/Raw 읽기
    - 구조화 노트 생성
    - processed marker 생성
    - Review 항목 생성
  금지:
    - 00_Inbox/Raw 수정/삭제
    - memory-config.json 수정
    - .env 읽기/수정
    - launchd/script 설치 파일 수정
    - 외부 네트워크 전송

enrich job:
  허용:
    - 80_Assets/Extracts/*.md 읽기
    - 해당 structured note의 enrich block 내부만 교체
    - 해당 marker JSON의 enrichment.status 갱신
  금지:
    - URL 직접 fetch
    - Raw 수정
    - 파일 삭제
    - 설정 파일 수정
    - unrelated note 수정
```

### 구현 방향

1. `memory-config.example.json`의 기본 agent command를 더 좁은 권한 모드로 바꾼다.
2. job type별 policy를 코드로 표현한다.
3. AI가 직접 무제한 파일 수정을 하지 않고, 가능하면 "변경 계획 manifest"를 출력하게 한다.
4. 적용은 별도 검증기가 manifest를 확인한 뒤 제한된 파일만 수정하게 한다.
5. 최소한 raw 폴더와 설정 파일은 코드상 write/delete 불가능하도록 guard를 둔다.

권장 구조:

```text
process_ai_jobs.py
  -> AI에게 작업 지시
  -> AI는 변경 manifest 생성
  -> validator가 manifest 검사
  -> 허용된 파일/블록만 적용
```

manifest 예시:

```json
{
  "job_id": "abc123",
  "job_type": "enrich",
  "changes": [
    {
      "path": "60_Ideas/Products/example.md",
      "operation": "replace_enrich_block",
      "marker": "00_Inbox/Processed/abc.json"
    }
  ]
}
```

검증기는 다음을 거부해야 한다.

- `00_Inbox/Raw` 하위 path에 대한 write/delete
- `.env`, `memory-config.json`, `memory-state/jobs/*.jsonl` 직접 수정
- vault 외부 path
- `..`를 포함한 path traversal
- symlink를 통한 vault 외부 접근
- job type policy에 없는 operation

### 테스트 요구사항

추가할 테스트:

- raw path 수정 manifest는 거부된다.
- config/env 수정 manifest는 거부된다.
- enrich job이 enrich block 외부 수정 요청을 하면 거부된다.
- lint job이 raw를 읽기만 하는 계획은 허용된다.
- symlink/path traversal 시도가 거부된다.
- 기존 정상 AI job dry-run은 계속 동작한다.

---

## 2. URL enrich의 로컬/내부망 fetch 방어

### 왜 필요한가

`scripts/enrich.py`는 raw note 안의 URL을 가져와 본문과 대표 이미지를 추출한다. 이때 사용자가 저장한 URL이 다음과 같으면 로컬 머신이 내부 자원에 접근할 수 있다.

```text
http://127.0.0.1:8765
http://localhost:8765
http://192.168.0.1
http://10.0.0.1
http://169.254.169.254
```

개인용 도구라도, URL fetch는 "내 컴퓨터가 대신 접속하는 기능"이다. 악의적인 URL이나 실수로 내부 주소를 저장했을 때 민감한 로컬 서비스에 접근할 수 있다. 이를 SSRF 성격의 위험으로 본다.

### 목표 상태

enrich는 외부 공개 웹 URL만 가져온다. 로컬 주소, 사설망 주소, link-local, multicast, loopback은 차단한다.

차단 대상 예시:

- `localhost`
- `127.0.0.0/8`
- `::1`
- `10.0.0.0/8`
- `172.16.0.0/12`
- `192.168.0.0/16`
- `169.254.0.0/16`
- private IPv6
- link-local IPv6
- URL scheme이 `http` 또는 `https`가 아닌 값

redirect가 발생하면 최종 URL도 다시 검사해야 한다.

대표 이미지 URL도 같은 정책을 적용해야 한다.

### 구현 방향

1. `scripts/enrich.py`에 URL 안전성 검사 함수를 추가한다.
2. hostname을 resolve한 뒤 IP가 차단 범위인지 검사한다.
3. fetch 전 URL 검사, redirect 후 최종 URL 검사를 모두 수행한다.
4. 이미지 다운로드에도 같은 검사 함수를 적용한다.
5. 차단된 경우 marker에 실패가 아니라 명확한 skipped 상태를 남긴다.

권장 marker 상태:

```json
{
  "enrichment": {
    "status": "skipped_blocked_url",
    "reason": "private_or_local_address",
    "url": "http://127.0.0.1:8765"
  }
}
```

### 테스트 요구사항

추가할 테스트:

- `localhost` 차단
- `127.0.0.1` 차단
- `10.x.x.x`, `172.16.x.x`, `192.168.x.x` 차단
- `169.254.x.x` 차단
- `file://` 같은 비 HTTP scheme 차단
- redirect 후 private IP가 되면 차단
- 정상 공개 HTTPS URL은 허용
- 이미지 URL도 동일하게 차단

---

## 3. job queue claim/lease/recovery 개선

### 왜 필요한가

`scripts/jobs.py`는 JSONL 파일 기반 job queue다. 파일락과 atomic write는 이미 있다. 그러나 현재 구조는 "pending job 하나를 안전하게 집어서 running으로 바꾸는 claim" 의미론이 약하다.

문제 예시:

```text
프로세서 A가 pending job을 읽음
프로세서 B도 같은 pending job을 읽음
A와 B가 동시에 처리 시작
```

또 다른 문제:

```text
job이 running으로 바뀜
프로세서가 중간에 죽음
job이 영원히 running으로 남음
```

### 목표 상태

job 처리자는 `list -> set-status` 흐름 대신 `claim` 명령을 사용한다.

claim은 lock 안에서 다음을 한 번에 수행한다.

```text
가장 오래된 pending job 찾기
상태를 running으로 변경
worker_id 기록
lease_expires_at 기록
변경된 job 반환
```

lease가 만료된 running job은 재시도 가능해야 한다.

### 구현 방향

1. `scripts/jobs.py`에 `claim` subcommand 추가.
2. job row에 아래 필드 추가.

```json
{
  "status": "running",
  "worker_id": "hostname-pid-random",
  "claimed_at": "2026-06-13T21:00:00+09:00",
  "lease_expires_at": "2026-06-13T21:30:00+09:00",
  "attempts": 1
}
```

3. `process_jobs.py`와 `process_ai_jobs.py`가 pending list를 직접 읽지 않고 claim을 사용하게 변경.
4. lease 만료 job은 `pending`으로 되돌리거나 `failed_retryable` 상태로 관리.
5. attempts가 일정 횟수 이상이면 `failed`로 전환.

### 테스트 요구사항

추가할 테스트:

- claim은 가장 오래된 pending 하나만 running으로 바꾼다.
- 두 번 claim해도 같은 job이 중복 claim되지 않는다.
- lease 만료 running job은 재claim 가능하다.
- lease가 살아 있는 running job은 재claim되지 않는다.
- attempts가 증가한다.
- process_jobs/process_ai_jobs는 claim 결과가 없으면 아무 작업도 하지 않는다.

---

## 4. destructive 명령의 2단계 적용 구조

### 왜 필요한가

다음 명령들은 실제 파일 삭제/이동/수정이 가능하다.

- `mem.py prune-orphans --apply`
- `mem.py reclassify --apply`
- `mem.py dedup-markers --apply`

백업을 만들기는 하지만, 개인 기록 시스템에서는 "백업했으니 괜찮다"만으로는 부족하다. 특히 Google Drive 동기화, macOS Unicode 정규화, Obsidian link rewrite가 얽히면 사용자가 예상하지 못한 파일이 움직일 수 있다.

### 목표 상태

destructive 명령은 바로 적용하지 않는다.

1단계:

```bash
python3 scripts/mem.py prune-orphans --plan-out /tmp/prune-plan.json
```

2단계:

```bash
python3 scripts/mem.py prune-orphans --apply --manifest /tmp/prune-plan.json
```

적용 시에는 manifest가 현재 파일 상태와 맞는지 다시 검증한다. 상태가 달라졌으면 중단한다.

### 구현 방향

manifest에는 최소한 다음 정보를 포함한다.

```json
{
  "command": "prune-orphans",
  "created_at": "2026-06-13T21:00:00+09:00",
  "vault": "/absolute/vault/path",
  "actions": [
    {
      "operation": "delete_structured_note",
      "path": "10_Timeline/Daily/example.md",
      "reason": "ghost_duplicate",
      "sha1_before": "..."
    }
  ]
}
```

적용 전 검증:

- manifest의 vault가 현재 vault와 동일한가
- 대상 파일이 여전히 존재하는가
- 파일 hash가 plan 생성 당시와 같은가
- 대상이 `00_Inbox/Raw`가 아닌가
- 대상 path가 vault 밖으로 나가지 않는가
- 예상 action 수가 사용자에게 출력되는가

### 테스트 요구사항

추가할 테스트:

- plan 생성은 파일을 변경하지 않는다.
- hash가 달라지면 apply가 중단된다.
- raw path 삭제 action은 거부된다.
- vault 밖 path는 거부된다.
- 정상 manifest는 백업 후 적용된다.
- apply 결과에 backup path와 action count가 출력된다.

---

## 5. `scripts/mem.py` 모듈 분리

### 왜 필요한가

`scripts/mem.py`는 현재 매우 크고 많은 책임을 가진다. 저장, frontmatter, 분류, lint, search, digest, doctor, review, reclassify, prune 기능이 한 파일에 함께 있다.

이 구조에서는 다음 문제가 생긴다.

- raw 불변 원칙을 여러 함수에서 따로 지켜야 한다.
- 테스트가 특정 기능 단위로 격리되기 어렵다.
- 작은 변경도 큰 파일 전체를 이해해야 한다.
- destructive 명령과 read-only 명령이 같은 모듈에 섞여 있다.

### 목표 상태

기능 단위로 파일을 분리하되, CLI 사용법은 가능하면 유지한다.

권장 분리:

```text
scripts/lmv/
  __init__.py
  config.py
  vault_io.py
  frontmatter.py
  classify.py
  lint.py
  search.py
  digest.py
  review.py
  destructive.py
  doctor.py
  cli.py

scripts/mem.py
  thin wrapper only
```

책임 예시:

```text
vault_io.py:
  - vault path resolve
  - safe path join
  - atomic write
  - raw write guard

classify.py:
  - classify
  - learned rule application
  - date normalization

lint.py:
  - raw -> structured note
  - marker creation
  - dedup

review.py:
  - review list/resolve
  - reclassify planning

destructive.py:
  - manifest validation
  - backup
  - guarded delete/move
```

### 주의사항

- 한 번에 전부 갈아엎지 않는다.
- 먼저 테스트를 고정한 뒤, 기능 단위로 옮긴다.
- `python3 scripts/mem.py ...` 기존 CLI는 유지한다.
- raw 관련 쓰기는 `vault_io.py`에서 중앙 차단한다.
- 기존 marker JSON schema는 후방 호환을 유지한다.

### 테스트 요구사항

- 기존 `tests/run_all.py` 전체 통과
- CLI 명령 호환성 유지
- save/lint/seek/digest/doctor/review/reclassify/prune 기존 테스트 유지
- 새 safe path/raw guard 테스트 추가

---

## 보안/개인정보 주의사항

작업자는 로그와 테스트 출력에 개인 기록을 과도하게 노출하지 않는다.

특히 다음을 최종 보고서나 PR 본문에 그대로 쓰지 않는다.

- Telegram token
- Telegram numeric user id
- 개인 계좌/주소/연락처
- raw note 전문
- private/sensitive note 내용
- 실제 vault absolute path가 불필요하게 포함된 긴 로그

필요하면 다음처럼 요약한다.

```text
raw note 3건에서 ghost duplicate 후보 발견
private note 내용은 출력하지 않음
```

## 권장 검증 명령

개선 작업 후 최소 검증:

```bash
python3 -B tests/run_all.py
python3 -m py_compile scripts/*.py tests/*.py
python3 -B scripts/process_ai_jobs.py --dry-run --limit 1
python3 -B scripts/mem.py enrich --dry-run --limit 5
python3 -B scripts/mem.py prune-orphans
git status --short
```

주의:

- `prune-orphans`는 반드시 dry-run으로만 실행한다.
- 실제 vault를 쓰는 명령은 사용자 승인 없이 실행하지 않는다.
- 테스트가 실제 개인 vault를 변경하지 않도록 fixture/temp directory를 사용한다.

## 완료 조건

각 개선 단계는 다음 조건을 만족해야 완료로 본다.

- 기존 테스트 전체 통과
- 새 위험에 대한 회귀 테스트 추가
- 실제 raw 기록 수정 없음
- 실제 queue 상태 임의 변경 없음
- 설정 파일의 비밀값 노출 없음
- 사용자에게 변경 파일, 검증 결과, 남은 위험을 한국어로 보고

## 최종 작업자 메모

이 프로젝트의 핵심 가치는 "기억을 잃지 않는 것"이다. 편의 기능이 조금 불편해지더라도 raw 기록 보존과 개인 정보 보호를 우선한다.

가장 중요한 판단 기준:

```text
AI가 실수하거나 속아도, 원본 기록과 개인 정보가 안전한가?
```

이 질문에 "예"라고 답할 수 있을 때만 자동화를 켠다.
