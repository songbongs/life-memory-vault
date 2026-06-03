#!/bin/bash
# Scheduled lint trigger for Life Memory Vault
# MacBook: run via launchd daily (see scripts/install-memory-tools.sh)
# Mac mini: run via cron every few hours

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
LOG="$ROOT/memory-state/scheduled-lint.log"

timestamp() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(timestamp)] scheduled_lint: checking pending count" >> "$LOG"

# digest로 미처리 건수 확인
DIGEST=$("$PYTHON" -B "$ROOT/scripts/mem.py" digest 2>/dev/null)
RAW=$(echo "$DIGEST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('raw_notes',0))" 2>/dev/null || echo "0")
PROCESSED=$(echo "$DIGEST" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('processed_markers',0))" 2>/dev/null || echo "0")
PENDING=$((RAW - PROCESSED))

echo "[$(timestamp)] scheduled_lint: raw=$RAW processed=$PROCESSED pending=$PENDING" >> "$LOG"

if [ "$PENDING" -le 0 ]; then
    echo "[$(timestamp)] scheduled_lint: nothing to do" >> "$LOG"
    exit 0
fi

# AI lint job 등록
JOB=$("$PYTHON" -B "$ROOT/scripts/jobs.py" add lint \
    --text "scheduled lint: $PENDING pending notes" \
    --adapter "codex" \
    --source "scheduled" 2>/dev/null)

JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id','unknown'))" 2>/dev/null || echo "unknown")
echo "[$(timestamp)] scheduled_lint: AI lint job created: $JOB_ID (pending=$PENDING)" >> "$LOG"

# rule-based lint도 즉시 실행 (빠른 1차 처리)
echo "[$(timestamp)] scheduled_lint: running rule-based lint" >> "$LOG"
"$PYTHON" -B "$ROOT/scripts/mem.py" lint >> "$LOG" 2>&1

echo "[$(timestamp)] scheduled_lint: done" >> "$LOG"
