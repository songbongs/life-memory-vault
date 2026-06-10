# Telegram Collector

This page explains how the Telegram bot connects to the Life Memory Vault.

## Simple Picture

```text
You send a message to Telegram bot
-> Telegram keeps the message
-> telegram_collector.py asks Telegram for new messages
-> normal notes go to mem.py and Obsidian 00_Inbox/Raw
-> slash commands go to memory-state/jobs
-> AI agents process the jobs later
```

The bot itself does not write to Obsidian. The collector running on the MacBook or Mac mini writes to Obsidian.

## Roles

- Telegram bot: the mailbox.
- `scripts/telegram_collector.py`: the delivery person.
- `scripts/mem.py`: the vault writer.
- `scripts/jobs.py`: the AI request box.
- AI agents: the organizer and search assistant after raw notes are saved.

## Setup Steps

1. Get the bot token from BotFather.
2. Keep the token private.
3. Run the collector with the token:

```bash
export TELEGRAM_BOT_TOKEN="PASTE_TOKEN_HERE"
python3 scripts/telegram_collector.py --me
python3 scripts/telegram_collector.py --once
```

4. Add your Telegram numeric user ID to `memory-config.json` under `telegram.allowedUserIds`.
   - `allowedUserIds` is **deny-by-default**: while it is empty, the bot saves nothing and instead replies to any sender with their numeric ID.
   - To learn your ID, just send the running bot any message once — it will answer with `당신의 Telegram ID: <id>`. Paste that number into the list.
5. Run the collector in loop mode:

```bash
python3 scripts/telegram_collector.py --loop
```

## What Gets Saved

- Text: saved as a raw Markdown note.
- URL: saved as text first; later linting can classify it.
- Photo/document/voice/video: collector downloads files under the configured size limit, then `mem.py` copies them into `80_Assets/Originals`.
- Large files: collector records metadata instead of downloading the file.

## AI Commands

Supported commands:

```text
/lint
/doctor
/repair
/seek 검색어
/digest
/status
```

These commands are not stored as memories. They are stored as jobs for Codex, Claude Code, Antigravity, MCP, or a future worker to process.

The queue files live here:

```text
memory-state/jobs/queue-YYYY-MM-DD.jsonl
```

## Current MVP

Before Mac mini:

```text
MacBook must be awake for collection to run.
```

After Mac mini:

```text
Mac mini runs this collector 24/7.
```
