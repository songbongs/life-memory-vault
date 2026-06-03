# AI Doctor Prompt

Goal: inspect the Life Memory vault for quality problems without changing anything.

Check for:

- Structured notes that appear misclassified.
- Duplicate notes that should be linked or merged.
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
