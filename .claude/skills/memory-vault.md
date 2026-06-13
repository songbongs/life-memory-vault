---
name: memory-vault
description: Use when capturing, structuring, searching, or operating the Life Memory Vault. Supports mem-save, mem-lint, mem-seek, mem-digest, local-first media handling, music memory, and MacBook-to-Mac-mini migration.
---

# Life Memory Vault Skill

Use this skill for the user's personal memory vault workflows.

## Mission

Reduce memory friction. The user should be able to throw fragmented memories into one simple capture path from phone, laptop, or AI tools. The system should preserve raw records, structure them automatically, and make them easy to retrieve later.

Alert the user if a proposed change increases capture friction, weakens raw preservation, increases avoidable API cost, or makes retrieval less reliable.

## Config

Read `memory-config.json` first. If it is missing, tell the user to copy `memory-config.example.json`.

Do not use `km-config.json` for Life Memory Vault operations unless the user explicitly asks to bridge the knowledge vault and memory vault.

## Commands

Prefer the local CLI:

```bash
python3 scripts/mem.py init
python3 scripts/mem.py save "memory text" --source manual
python3 scripts/mem.py lint
python3 scripts/mem.py seek "query"
python3 scripts/mem.py digest
python3 scripts/mem.py doctor
python3 scripts/mem.py enrich --all   # URL 메모 보강 → 이후 prompts/ai-enrich.md로 한국어 요약
```

Natural language routing (English or Korean):

- "remember this" / "save this" / "이거 저장해줘" / "메모해줘" -> `mem-save`
- "clean up inbox" / "lint today's notes" / "안 정리된 메모 정리해줘" -> `mem-lint`
- "what was that..." / "그거 뭐였지" / "어제 메모한 거 찾아줘" -> `mem-seek`
- "summarize this week" / "이번 주 요약해줘" -> `mem-digest`
- "웹요약" / "링크 요약해줘" / "저장한 URL 정리해줘" -> `mem-enrich`
- "이거 분류 틀렸어" / "task 아니라 idea야" / "X를 product로 바꿔줘" -> `mem-reclassify`

## Raw Preservation

Raw inbox notes are sacred. Do not edit raw notes in `00_Inbox/Raw`. Write processed markers under `00_Inbox/Processed` and create structured notes that link back with `source_raw`.

## Media Policy

Default thresholds:

- Up to 20 MB: store original in the vault.
- 20 MB to 100 MB: store original only when locally available and useful.
- Over 100 MB: keep original outside the vault and store link, transcript, keyframes, and summary.
- Video over 50 MB or over 10 minutes: external archive by default.

Use free local tools first. Avoid metered APIs by default.

## Tool Cascade

1. Lightweight parsers: `pdfplumber`, `pdftext`, `youtube-transcript-api`, `yt-dlp`
2. Marker: `marker_single`
3. PaddleOCR: `paddleocr_file` or `paddleocr_mcp`
4. MarkItDown local conversion
5. OpenDataLoader PDF
6. kordoc MCP for HWP/HWPX/HWPML

## Music Memory

Music and playlists are first-class memory types.

Folders:

```text
40_Entities/Artists/
40_Entities/Songs/
40_Entities/Albums/
50_Experiences/Music/Listening_Log/
50_Experiences/Music/Concerts/
60_Ideas/Playlists/
70_MOCs/Music-MOC.md
```

Examples:

- `IU - Through the Night` creates artist and song notes.
- A YouTube Music playlist URL creates a playlist note and later metadata extraction can fill tracks.
- Contexts such as driving, focus, walking, late night, or family should become structured fields when linting.

## MCP Roadmap

Before Mac mini: direct file operations from MacBook and coding agents.

After Mac mini:

- Local MCP first for coding agents and local clients.
- Remote MCP second for ChatGPT/Claude/Gemini web clients through authenticated HTTPS/tunnel.
- Remote write access should start with `mem_save` only; bulk linting and destructive edits stay local until reviewed.
