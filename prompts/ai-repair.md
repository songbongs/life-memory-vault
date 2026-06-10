# AI Repair Prompt

Goal: apply safe fixes recommended by AI Doctor or requested by the user.

Safe repair actions:

- Move a structured note to a better folder.
- Add missing `source_raw` links when the source is clear.
- Add `needs_review: true` where classification is uncertain.
- Add aliases, tags, or cross-links.
- Create a review note when the right fix is unclear.

Ask the user first before:

- Deleting anything.
- Editing raw notes.
- Merging notes when identity is ambiguous.
- Moving private/sensitive records into a more visible location.
- Making broad changes across many files.

## Resolving Review items + learning (③d)

When you resolve a `00_Inbox/Review/` item to a confirmed `memory_type` (after the user
agrees), **record the decision** so the same pattern can be auto-classified later:

- Prefer: `python3 scripts/mem.py review resolve <review_file> --type <type> --signal "<핵심 키워드>"`
  — creates the structured note, deletes the Review file (raw stays), and records the decision.
- Or, if resolved manually: `python3 scripts/rules.py add-decision --signal "<핵심 키워드>" --type <type> --folder <folder> --source "<source_raw>" --by ai_repair`.
- `signal` = the short disambiguating keyword that decides the type (e.g. `샤워헤드` → maintenance). Pick a specific, reusable noun — not a whole sentence.
- A signal confirmed twice (consistently) is auto-promoted; contradictory decisions stay blocked. Inspect with `python3 scripts/rules.py list`.

## MOC edits (preserve structure)

If a repair touches a `70_MOCs/*.md`: read it first and **add to the right section only**.
Never overwrite a MOC with a minimal stub or drop existing sections/entries. If a MOC is
missing, recreate it from the `scripts/mem.py` init template skeleton first.

Expected output:

- Apply the approved/safe repairs.
- Write a short repair report under `90_System/Logs/`.
- Mark the related queue job done or failed with a useful note.
