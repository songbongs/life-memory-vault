#!/bin/bash
# Install launchd plist for scheduled Life Memory lint on MacBook
# Runs daily at 22:00 (10pm)

PLIST_NAME="com.sangmin.life-memory-lint"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/scripts/scheduled_lint.sh"

chmod +x "$SCRIPT"

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
    <string>/bin/bash</string>
    <string>$SCRIPT</string>
  </array>
  <key>StartCalendarInterval</key>
  <dict>
    <key>Hour</key>
    <integer>22</integer>
    <key>Minute</key>
    <integer>0</integer>
  </dict>
  <key>StandardOutPath</key>
  <string>$ROOT/memory-state/launchd-lint.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/memory-state/launchd-lint.log</string>
  <key>RunAtLoad</key>
  <false/>
</dict>
</plist>
EOF

launchctl unload "$PLIST_PATH" 2>/dev/null || true
launchctl load "$PLIST_PATH"
echo "launchd job installed: $PLIST_NAME (매일 22:00 실행)"
echo "확인: launchctl list | grep life-memory"
echo "제거: launchctl unload $PLIST_PATH && rm $PLIST_PATH"
