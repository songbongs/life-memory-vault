# Life Memory Vault

This document defines the MVP implementation for a local-first personal memory vault.

## Mission

The project exists to make fragmented personal memory easy to capture from any environment, automatically structure it in an Obsidian vault, and make it easy for the user or AI tools to retrieve later.

Every improvement should reduce capture friction, preserve raw evidence, improve automatic structure, or make recall easier. If a change increases friction, weakens privacy, or makes retrieval less reliable, agents should flag it and propose a simpler alternative.

## Cost Model

The default design avoids metered APIs.

Codex, Claude Code, and Antigravity scheduled runs can be used through existing subscriptions, but those runs still consume each product's usage limits. Treat them as "no separate API bill by default", not as unlimited free compute.

## MVP Architecture

Before the Mac mini arrives:

```text
Telegram or MacBook
-> memory-config.json
-> scripts/mem.py save
-> my-memory-vault/00_Inbox/Raw
-> scripts/mem.py lint
-> Codex/Claude Code/Antigravity direct vault search
```

After the Mac mini arrives:

```text
Telegram / Web AI / Coding AI
-> local + remote MCP
-> Mac mini memory server
-> Obsidian Inbox
-> scheduled mem-lint
-> mem-seek / mem-digest
```

## Storage Policy

Raw records are never edited. Processed markers and structured notes point back to raw records.

Recommended media thresholds:

- Up to 20 MB: store in the vault.
- 20 MB to 100 MB: store only when directly available on the Mac mini or explicitly useful.
- Over 100 MB: keep original outside the vault and store link, transcript, keyframes, and summary.
- Video over 50 MB or longer than 10 minutes: external archive by default.

## Tool Cascade

Use free local tools first:

1. `pdfplumber`, `pdftext`, `youtube-transcript-api`, `yt-dlp`
2. `marker_single`
3. PaddleOCR / PaddleOCR MCP
4. Microsoft MarkItDown local conversion
5. OpenDataLoader PDF
6. kordoc MCP for Korean office/public documents

Paid APIs stay off by default.

## Music Memory

Music records are first-class memories.

Folders:

```text
50_Experiences/Music/Listening_Log/
50_Experiences/Music/Concerts/
40_Entities/Artists/
40_Entities/Songs/
40_Entities/Albums/
60_Ideas/Playlists/
70_MOCs/Music-MOC.md
```

Examples:

- "IU - Through the Night" creates or updates artist and song notes.
- A YouTube Music playlist URL creates a playlist note and tries metadata extraction later.
- Listening contexts such as driving, focus, walking, or late night are captured as frontmatter and tags when an agent structures the note.

## Commands

- `mem-save`: save raw memory.
- `mem-lint`: structure pending inbox notes.
- `mem-seek`: search or recall memory.
- `mem-digest`: summarize recent memory state.

Natural language requests should route to these commands when possible.
