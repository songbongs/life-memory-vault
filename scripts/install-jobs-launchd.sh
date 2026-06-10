#!/bin/bash
# Install a launchd agent that runs the deterministic job-queue bridge every
# few minutes, closing the loop for /digest and /doctor Telegram requests.
#
# Runs python3 directly (like the working collector agent) so it is not blocked
# by macOS TCC the way "/bin/bash <script under ~/Documents>" is (exit 126).
# Label matches the project's existing com.sangmin.* convention.
# Interval: every 5 minutes (StartInterval, seconds). Override with INTERVAL=.

PLIST_NAME="com.sangmin.life-memory-jobs"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="$(command -v python3)"
SCRIPT="$ROOT/scripts/process_jobs.py"
INTERVAL="${INTERVAL:-300}"

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
  <key>StartInterval</key>
  <integer>$INTERVAL</integer>
  <key>StandardOutPath</key>
  <string>$ROOT/memory-state/launchd-jobs.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/memory-state/launchd-jobs.log</string>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "launchd job installed: $PLIST_NAME (매 ${INTERVAL}초 실행)"
echo "확인: launchctl list | grep life-memory"
echo "로그: tail -f $ROOT/memory-state/launchd-jobs.log"
echo "제거: launchctl unload $PLIST_PATH && rm $PLIST_PATH"
