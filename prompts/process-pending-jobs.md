# Process Pending Life Memory Jobs

Use this prompt when an AI agent is asked to process pending Life Memory jobs.

Project root:

```text
이 파일(prompts/process-pending-jobs.md)에서 두 단계 상위 폴더가 프로젝트 루트입니다.
memory-config.json 파일이 있는 폴더가 프로젝트 루트입니다.

예시:
  맥북: /Users/sangmin/Documents/AI_Playground/my-life-memory
  맥미니: /Users/mini-song/Documents/AI-PlayGround/life-memory-vault
```

Vault index (검색 범위 좁히기):

```text
docs/vault-index.md
```

Core rule:

- Raw records in the Obsidian vault are immutable. Do not edit or delete raw notes.
- AI lint/doctor/repair work must preserve source links back to raw records.
- If an action could lose information, expose private data, or merge ambiguous memories, ask the user first.

## Workflow

1. Run `python3 -B scripts/jobs.py list --status pending`.
2. Pick the oldest pending job unless the user specified a job id or type.
3. Mark it running with `python3 -B scripts/jobs.py set-status <id> running --note "Started by <agent-name>"`.
4. Execute the matching prompt:
   - `lint`: use `prompts/ai-lint.md` (Wiki Layer 구축 포함, MOC 업데이트 필수)
   - `doctor`: use `prompts/ai-doctor.md`
   - `repair`: use `prompts/ai-repair.md`
   - `seek`: 아래 AI Seek 프로토콜 참조
   - `digest`: 아래 Digest 프로토콜 참조
   - `status`: 아래 Status 프로토콜 참조
5. 결과를 job result에 기록하고 Telegram 알림이 필요하면 발송 (아래 참조).
6. Mark the job done with a short result. If blocked, mark it failed and include the question/blocker.

Prefer small, reversible edits. Keep raw material intact.

## AI Seek 프로토콜

1. `docs/vault-index.md`에서 검색 쿼리에 맞는 폴더 파악
2. 해당 폴더의 MOC 파일 확인 (`70_MOCs/`)
3. 관련 structured notes 파일 전체 내용을 컨텍스트에 로딩
4. 의미 기반 합성 답변 생성 (출처 파일 경로 포함)
5. 단순 키워드 매칭이 아닌 의미적 유사성으로 판단
6. job의 `chat_id`가 있으면 아래 형식으로 Telegram 발송:

```
🔍 AI 검색: "[쿼리]"

[합성 답변]

📄 출처:
- [[파일 경로]] — 관련 내용 요약
```

7. 검색 결과가 유의미하면 `00_Inbox/Review/seek-[날짜]-[쿼리].md`에 저장 (재사용 가능한 합성 지식)

## Lint 완료 후 Telegram 알림

lint job 완료 시 `chat_id`가 있으면 아래 형식으로 Telegram 발송:

```python
# scripts/telegram_collector.py의 send_message() 함수 사용
send_message(token, int(chat_id), result_summary, reply_to_message_id=message_id)
```

발송 형식:
```
✅ AI Lint 완료 (YYYY-MM-DD HH:MM)

처리: N건
- 생성된 노트: N개 (task 1, maintenance 2, ...)
- 업데이트된 엔티티: N개
- 업데이트된 MOC: N개
- needs_review: N건 → 00_Inbox/Review 확인 필요

/status 로 전체 현황 확인
```

## Digest 프로토콜

1. `python3 -B scripts/mem.py digest` 실행
2. `scripts/jobs.py summary` 실행
3. 최근 structured notes 5건 제목 나열
4. job의 `chat_id`가 있으면 Telegram 발송:

```
📊 Life Memory 요약 (YYYY-MM-DD)

Raw 노트: N건 | 처리: N건 | 미처리: N건
최근 분류: task 2건, maintenance 1건, song 3건

최근 추가 기억:
- [노트 제목] (날짜)
- ...

Job 큐: pending N건, done N건
```

## Status 프로토콜

`/status`는 telegram_collector.py에서 즉시 처리한다.
job queue로 넘어온 status job은 더 상세한 버전을 처리:

1. digest 실행
2. job queue summary 실행
3. collector 실행 중인지 확인 (memory-state/telegram-collector.pid)
4. Telegram 발송
