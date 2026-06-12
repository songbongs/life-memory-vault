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

- "Summarize this week" / "이번 주 요약해줘"
- "What did I capture today?" / "오늘 뭐 저장했지?"
- "Show unprocessed memory state" / "안 처리된 메모 상태 보여줘"
