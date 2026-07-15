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

## Scheduled repair-check job (graph-layer G, 2026-07-15)

A weekly deterministic sweep (`process_jobs.py::maybe_weekly_repair_check`) runs
`mem.py dedup-markers` and `mem.py prune-orphans` (both dry-run) and enqueues a
`repair` job — payload `raw_text` like `"scheduled repair-check: marker 중복 6건,
고스트 orphan 32건 발견"` — whenever either finds something. Handle it like this:

1. Re-run both commands yourself to get current, itemized detail (the enqueue-time
   count can be stale by the time you process it):
   ```bash
   python3 scripts/mem.py dedup-markers      # dry-run: same-raw dupes + same-note re-captures
   python3 scripts/mem.py prune-orphans      # dry-run: ghost duplicates left behind + report-only
   ```
2. Read a sample of the flagged pairs (both file paths in each `ghost_duplicate(정식본=...)`
   line) to confirm they're really the same memory before doing anything — a shared
   raw source is strong evidence, but verify content, don't assume.
3. **This counts as "merging notes when identity is ambiguous" per the rule above —
   always present the specific findings to the user and get confirmation before
   running either command with `--apply`.** Never auto-apply from this job type.
4. If confirmed: run `dedup-markers --apply` first (cleans markers, keeps raw
   untouched), then `prune-orphans --apply` (removes the now-orphaned duplicate
   `.md` files it flagged — both back up what they touch, see each command's own
   help for the backup path).
5. If the user wants to wait, mark the job `done` with the findings summarized in
   the result JSON (not `failed` — nothing went wrong, a decision is just pending)
   and mention it's safe to revisit any time via `/mem-doctor` or asking directly.

## MOC edits (preserve structure)

If a repair touches a `90_System/Index/*.md` MOC (2026-07-15: current location — `70_MOCs/` is a legacy copy last updated 2026-06-13, do not use): read it first and **add to the right section only**.
Never overwrite a MOC with a minimal stub or drop existing sections/entries. If a MOC is
missing, recreate it from the `scripts/mem.py` init template skeleton first.

Expected output:

- Apply the approved/safe repairs.
- Write a short repair report under `90_System/Logs/`.
- Mark the related queue job done or failed with a useful note.
