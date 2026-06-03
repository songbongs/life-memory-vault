---
description: Life Memory Vault daily or weekly digest command
allowedTools: Bash, Read, Glob, Grep
---

# mem-digest

Summarize recent Life Memory Vault state.

Rules:

- Report raw count, processed count, review-needed items, and notable memory types.
- For agent-authored summaries, link to source notes.
- Use `scripts/mem.py digest` for deterministic counts before synthesis.

Example:

```bash
python3 scripts/mem.py digest
```

Natural language routes:

- "Summarize this week"
- "What did I capture today?"
- "Show unprocessed memory state"
