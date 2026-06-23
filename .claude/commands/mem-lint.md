---
description: Life Memory Vault inbox structuring and lint command
allowedTools: Bash, Read, Write, Glob, Grep
---

# mem-lint

Structure pending raw memories in the Life Memory Vault, then fix any file name violations.

Rules:

- Never edit raw notes under `00_Inbox/Raw`.
- Create processed markers under `00_Inbox/Processed`.
- Create lightweight structured notes that link back to `source_raw`.
- Use free local tools first and avoid metered APIs by default.
- Use `scripts/mem.py lint` for deterministic MVP processing.

## Step 1 — Deterministic lint

```bash
python3 scripts/mem.py lint
```

Report how many notes were processed and how many duplicates were skipped.

## Step 2 — File name violation fix (rename pass)

After deterministic lint, scan all structured notes for naming rule violations and fix them.
Follow the rules in `prompts/ai-lint.md` § "파일 제목 명명 규칙" and § "7단계: 기존 파일명 위반 정리".

Detection: files in `60_Ideas/`, `30_Actions/`, `10_Timeline/`, `20_Records/`, `40_Entities/`, `50_Experiences/` that contain any of:
- `AI 프로젝트`, `AI design`, `AI plugins`, `AI util`, `AI tts`, `AI RAG`, `AI investment` prefix
- `LLMWIKI`, `적용후보`, `관심 프로젝트`, `memory`, `memo`, `메모`, `obsidian`, `song`, `노래`, `요리`, `공부대상`, `추천대상` redundant words
- Raw URL or domain in the name
- Mixed Korean/English without a clear product name exception

Fix: look up the note's marker JSON for enrich title/URL, then:
```bash
python3 scripts/mem.py reclassify "{relative path}" --title "{new title}"
```

Skip if the correct name is ambiguous — do not guess.

## Summary

Report:
- Lint: N processed, N duplicates
- Renamed: N files (old → new)
- Skipped: N (ambiguous)

Natural language routes:

- "clean up today's inbox" / "안 정리된 메모 정리해줘"
- "lint my memory vault" / "받은 메모 구조화해줘"
- "오늘 메모 정리해줘" / "파일명도 정리해줘"
