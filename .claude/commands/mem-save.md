---
description: Life Memory Vault raw capture command
allowedTools: Bash, Read, Write
---

# mem-save

Save a raw memory into the Life Memory Vault inbox.

Rules:

- Read `memory-config.json`.
- Preserve the raw record exactly enough to reconstruct the user's input.
- Do not classify at capture time unless obvious metadata can be added without asking the user.
- Use `scripts/mem.py save`.

Examples:

```bash
python3 scripts/mem.py save "$ARGUMENTS" --source manual
python3 scripts/mem.py save "$ARGUMENTS" --source telegram
python3 scripts/mem.py save --file "/path/to/file.pdf" --source manual
```

If the user asks naturally, route phrases like "remember this", "save this", or "store this in memory" — or Korean phrases like "이거 저장해줘", "메모해줘", "기억해둬" — here.
