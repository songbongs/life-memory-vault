#!/bin/bash
# collector_watchdog.sh를 launchd가 실제로 실행할 수 있는 위치로 배포한다.
#
# 왜 복사하나: launchd가 띄우는 /bin/bash는 macOS TCC 때문에 ~/Documents를
# 읽지 못한다. 저장소 안(scripts/)에 둔 채로 plist에 걸면 실행 자체가
# "Operation not permitted"로 실패한다. 그래서 Documents 밖으로 복사해서 돌린다.
#
# 감시 스크립트를 수정한 뒤에는 이 스크립트를 다시 실행해야 반영된다.

set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/collector_watchdog.sh"
DEST_DIR="$HOME/Library/Application Support/life-memory"
DEST="$DEST_DIR/collector_watchdog.sh"

mkdir -p "$DEST_DIR"
cp "$SRC" "$DEST"
chmod 755 "$DEST"

echo "배포 완료: $DEST"

if launchctl list 2>/dev/null | grep -q com.sangmin.life-memory-watchdog; then
  launchctl kickstart gui/"$(id -u)"/com.sangmin.life-memory-watchdog 2>/dev/null || true
  echo "감시 에이전트 재실행 요청함"
fi
