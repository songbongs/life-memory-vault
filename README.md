# My Life Memory

Local-first Life Memory Vault tooling for capturing raw memories, structuring them into an Obsidian vault, and retrieving them later through coding agents or future MCP servers.

## Mission

Capture first, preserve raw records, structure later, and make recall easy from any AI environment.

## Quick Start

```bash
python3 scripts/mem.py doctor
python3 scripts/mem.py init
python3 scripts/mem.py save "IU - Through the Night" --source manual
python3 scripts/mem.py lint
python3 scripts/mem.py seek "Through"
python3 scripts/mem.py digest
```

## Telegram Capture

The Telegram bot is the mailbox. The collector running on the MacBook or Mac mini is the delivery person.

```text
Telegram bot -> scripts/telegram_collector.py -> scripts/mem.py -> Obsidian 00_Inbox/Raw
```

Start with:

```bash
export TELEGRAM_BOT_TOKEN="PASTE_TOKEN_HERE"
python3 scripts/telegram_collector.py --me
python3 scripts/telegram_collector.py --once
```

See [docs/telegram-collector.md](docs/telegram-collector.md).

## Mobile AI Commands

Telegram commands are treated as AI job requests, not as raw notes:

```text
/lint
/doctor
/repair
/seek 차량용품 교체
/digest
/status
```

These requests are saved to `memory-state/jobs/queue-YYYY-MM-DD.jsonl`. A global Codex skill at `/Users/sangmin/.codex/skills/life-memory/SKILL.md` can process those jobs from anywhere, including Codex Remote or a cokacdir-connected Codex session.

See [docs/mobile-ai-commands.md](docs/mobile-ai-commands.md).

## Project Handoff

The full planning-to-current-state handoff document is here:

[docs/project-handoff.md](docs/project-handoff.md)

## Local Admin Dashboard

You can control the Telegram collector from a local browser page:

```bash
python3 scripts/memory_admin.py
```

Then open:

```text
http://127.0.0.1:8765
```

See [docs/admin-dashboard.md](docs/admin-dashboard.md).

## Commands

| 하고 싶은 일 | 명령어식 요청 | 자연어 요청 |
|---|---|---|
| 새 메모 저장 | `life-memory, mem-save "차량 와이퍼 오늘 교체"` | 라이프 메모리에 차량 와이퍼 오늘 교체했다고 저장해줘 |
| Raw 기록 정리 | `life-memory, mem-lint 실행해줘` | 라이프 메모리 Raw 폴더에 쌓인 기록들을 AI로 분류해서 정리해줘 |
| 볼트 상태 점검 | `life-memory, mem-doctor 실행해줘` | 라이프 메모리 볼트에 잘못 분류된 기록이나 문제 있는 노트가 있는지 점검해줘 |
| 문제 수정 | `life-memory, mem-repair 실행해줘` | doctor 결과를 보고 안전하게 고칠 수 있는 것들은 고쳐줘. 애매한 건 먼저 물어봐줘 |
| 기억 검색 | `life-memory, mem-seek "차량용품 교체"` | 내 기억 저장소에서 차량용품 교체 관련 기록 찾아줘 |
| 요약 보기 | `life-memory, mem-digest 실행해줘` | 라이프 메모리 상태를 간단히 요약해줘. Raw가 몇 개 있고 처리된 게 몇 개인지 알려줘 |
| 텔레그램 작업큐 처리 | `life-memory, pending jobs 처리해줘` | 텔레그램에서 요청한 작업들이 있으면 확인해서 처리해줘 |

### CLI 직접 실행

```bash
python3 scripts/mem.py save "텍스트" --source manual
python3 scripts/mem.py lint
python3 scripts/mem.py seek "검색어"
python3 scripts/mem.py digest
python3 scripts/mem.py doctor
```

## Config

Copy `memory-config.example.json` to `memory-config.json` and set `memoryVault.vaultPath`. This local config is ignored by git.

## Roadmap

- MacBook MVP: direct Telegram/polling capture and scheduled lint without MCP.
- Mac mini: local MCP first, then remote MCP with authenticated tunnel.
