# AI Doctor Prompt

Goal: inspect the Life Memory vault for quality problems without changing anything.

Check for:

- Structured notes that appear misclassified.
- Duplicate notes that should be linked or merged — run `python3 scripts/mem.py dedup-markers`
  and `python3 scripts/mem.py prune-orphans` (both dry-run) and include their findings in the
  report. (2026-07-15: this pair also now runs on its own weekly schedule — see
  `prompts/ai-repair.md` § "Scheduled repair-check job" for how those auto-created jobs get
  handled; a manual `/mem-doctor` run is just the on-demand version of the same check.)
- Missing `source_raw` links.
- Raw notes that are still unprocessed.
- Notes with low confidence or `needs_review: true`.
- Sensitive notes that may need a stronger privacy label.
- Broken attachment links or external file references.

Expected output:

- Write a dated report under `90_System/Logs/`.
- Group findings by severity: high, medium, low.
- Include exact file paths and recommended repair actions.
- Do not move, rename, merge, or delete files.
