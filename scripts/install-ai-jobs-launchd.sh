#!/bin/bash
# Install a launchd agent that drains AI Life Memory jobs (lint/repair/seek) once
# a day at 23:00 by invoking process_ai_jobs.py (which calls the configured agent
# headlessly). On-demand manual runs still work: python3 scripts/process_ai_jobs.py --once
#
# Runs python3 directly (TCC: see install-launchd.sh). Also sets PATH so the agent
# binary (claude/codex) resolves under launchd's minimal environment.

PLIST_NAME="com.sangmin.life-memory-ai"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
BINDIR="$(dirname "$PYTHON")"
SCRIPT="$ROOT/scripts/process_ai_jobs.py"
HOUR="${HOUR:-23}"
MIN="${MIN:-0}"

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$PLIST_NAME</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-B</string>
    <string>$SCRIPT</string>
    <string>--once</string>
  </array>
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>PATH</key>
    <string>$BINDIR:/usr/bin:/bin:/usr/sbin:/sbin</string>
    <key>HOME</key>
    <string>$HOME</string>
  </dict>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>$HOUR</integer>
    <key>Minute</key>
    <integer>$MIN</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$ROOT/memory-state/launchd-ai-jobs.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/memory-state/launchd-ai-jobs.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "launchd job installed: $PLIST_NAME (매일 ${HOUR}:$(printf '%02d' "$MIN") 실행)"
echo "확인: launchctl list | grep life-memory"
echo "로그: tail -f $ROOT/memory-state/launchd-ai-jobs.log"
echo "수동 1회: launchctl kickstart -k gui/\$(id -u)/$PLIST_NAME"
echo "제거: launchctl unload $PLIST_PATH && rm $PLIST_PATH"
