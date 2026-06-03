# Mobile AI Commands

This project separates capture from AI work.

```text
Telegram message
-> collector on MacBook/Mac mini
-> raw note or job queue
-> Codex/Claude/Antigravity processes the job
-> Obsidian vault is updated
```

## Two Kinds of Telegram Messages

### 1. Normal note

Example:

```text
이 서비스 나중에 써보기: https://example.com
```

Result:

```text
Obsidian vault / 00_Inbox/Raw
```

The collector only saves it. AI does not classify it immediately.

### 2. Command

Example:

```text
/lint
/doctor
/repair
/seek 차량용품 교체
/digest
/status
```

Result:

```text
my-life-memory / memory-state/jobs/queue-YYYY-MM-DD.jsonl
```

Telegram itself does not store the job. The collector receives the command and writes a small job request on the MacBook or Mac mini.

## Why Use a Job Queue?

The queue is the project's own request box.

- Telegram, MCP, admin page, and future tools can all write the same kind of job.
- Codex, Claude Code, Antigravity, or another worker can all read the same queue.
- The project does not depend on one specific AI app.
- Many tiny files are avoided because jobs are grouped by day in JSONL files.

## Global Codex Skill

A global Codex skill was added to the user's home directory:

```text
# 맥북이라면:
/Users/sangmin/.codex/skills/life-memory/SKILL.md

# 맥미니라면:
/Users/mini-song/.codex/skills/life-memory/SKILL.md
```

This lets Codex understand Life Memory requests even when it is not opened from the project folder.

Mobile-friendly examples:

```text
life-memory pending 작업 처리해줘
라이프 메모리 큐에 쌓인 /lint 작업 처리해줘
mem-doctor 실행해서 볼트 상태 점검해줘
mem-seek 차량용품 교체 기록 찾아줘
```

Codex should then move to the project root:

```text
# 맥북이라면:
/Users/sangmin/Documents/AI_Playground/my-life-memory

# 맥미니라면:
/Users/mini-song/Documents/AI-PlayGround/life-memory-vault
```

and process jobs from:

```text
memory-state/jobs/
```

## When Codex Should Ask First

Codex should ask a short question before:

- deleting anything
- editing raw notes
- merging ambiguous notes
- moving many files at once
- exposing private memory through a remote channel
- repairing something when the correct target is unclear

Otherwise, it can proceed and report the result.
