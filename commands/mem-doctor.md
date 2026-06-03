# mem-doctor

Audit the Life Memory Vault.

Current local CLI behavior:

```bash
python3 scripts/mem.py doctor
```

AI Doctor behavior:

1. Read `prompts/ai-doctor.md`.
2. Inspect structured notes and processed markers.
3. Write a dated report under `90_System/Logs/`.
4. Do not change files during doctor mode.
