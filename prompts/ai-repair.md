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

Expected output:

- Apply the approved/safe repairs.
- Write a short repair report under `90_System/Logs/`.
- Mark the related queue job done or failed with a useful note.
