---
description: Life Memory Vault inbox structuring and lint command
allowedTools: Bash, Read, Write, Glob, Grep
---

# mem-lint

Structure pending raw memories in the Life Memory Vault.

Rules:

- Never edit raw notes under `00_Inbox/Raw`.
- Create processed markers under `00_Inbox/Processed`.
- Create lightweight structured notes that link back to `source_raw`.
- Use free local tools first and avoid metered APIs by default.
- Use `scripts/mem.py lint` for deterministic MVP processing.

Examples:

```bash
python3 scripts/mem.py lint
python3 scripts/mem.py lint --force
```

Natural language routes:

- "clean up today's inbox" / "안 정리된 메모 정리해줘"
- "lint my memory vault" / "받은 메모 구조화해줘"
- "structure the raw records" / "오늘 메모 정리해줘"
