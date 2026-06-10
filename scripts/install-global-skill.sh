#!/bin/bash
# Install an agent-agnostic global "life-memory" skill so any agent (Claude Code,
# Codex, ...) can process the Life Memory job queue from anywhere.
#
# The project root is injected at install time (kept out of the committed repo to
# avoid path drift). Installs to both Codex and Claude global skill dirs.

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"

read -r -d '' SKILL <<EOF || true
---
name: life-memory
description: Process the Life Memory Vault job queue and capture/recall personal memories. Use when asked to handle life-memory jobs, to lint/repair/seek the vault, or to process pending Telegram requests — from any project or agent.
---

# Life Memory Vault — Job Processing (global skill)

Project root: \`$ROOT\`
(the folder containing \`memory-config.json\`; cd here first.)

## When invoked
The user wants you to process the Life Memory Vault. Always work from the project root above.

## Pending jobs
Telegram commands and schedulers enqueue jobs in \`memory-state/jobs/queue-*.jsonl\`.

1. List pending: \`python3 scripts/jobs.py list --status pending\`
2. Deterministic jobs (\`digest\`, \`doctor\`): run \`python3 scripts/process_jobs.py --once\`.
3. AI jobs (\`lint\`, \`repair\`, \`seek\`): read and follow \`prompts/process-pending-jobs.md\`, then do the work yourself (entities, MOCs, links).

## Hard rules
- Raw notes in \`00_Inbox/Raw\` are immutable. Never edit or delete them.
- If a classification or merge is ambiguous, leave it in \`00_Inbox/Review\` with a one-line reason. Do NOT guess.
- Preserve \`source_raw\` links. Mark each job done/failed via \`scripts/jobs.py set-status\`.
- Local/free first; avoid metered APIs.

## Unattended automation
A launchd agent runs \`scripts/process_ai_jobs.py --once\`, which invokes the configured agent headlessly to drain AI jobs. For interactive use, prefer doing the work directly per the protocol above.
EOF

install_to() {
  local dir="$1"
  mkdir -p "$dir/life-memory"
  printf '%s\n' "$SKILL" > "$dir/life-memory/SKILL.md"
  echo "  installed: $dir/life-memory/SKILL.md"
}

echo "Installing global life-memory skill (project root: $ROOT)"
install_to "$HOME/.codex/skills"
install_to "$HOME/.claude/skills"
echo "Done. Antigravity or other agents can point at the same project root and prompts/process-pending-jobs.md."
