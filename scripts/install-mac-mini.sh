#!/bin/bash
# Life Memory Vault — 맥미니 서비스 설치 스크립트
#
# 이 스크립트를 맥미니에서 한 번만 실행하면:
#   1. Telegram 수집기가 항상 켜져 있는 서비스로 등록됩니다
#      (맥미니를 껐다 켜도 자동 시작, 오류로 죽어도 자동 재시작)
#   2. 2시간마다 자동으로 미처리 메모를 정리하는 스케줄러가 등록됩니다
#
# 사용법 (맥미니 터미널에서):
#   bash scripts/install-mac-mini.sh
#
# 제거 방법:
#   bash scripts/install-mac-mini.sh --uninstall

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
# launchd ProgramArguments needs an absolute interpreter path (launchd's PATH is
# minimal and does not include /opt/homebrew/bin).
PYTHON="$(command -v "$PYTHON" 2>/dev/null || echo "$PYTHON")"
LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
err()  { echo -e "${RED}  ❌ $1${NC}"; }
step() { echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"; }

COLLECTOR_PLIST_NAME="com.sangmin.life-memory-collector"
LINT_PLIST_NAME="com.sangmin.life-memory-lint"
COLLECTOR_PLIST="$LAUNCH_AGENTS/$COLLECTOR_PLIST_NAME.plist"
LINT_PLIST="$LAUNCH_AGENTS/$LINT_PLIST_NAME.plist"

# ── 제거 모드 ───────────────────────────────────────────────────────
if [ "${1:-}" = "--uninstall" ]; then
    echo ""
    echo "======================================"
    echo "  서비스 제거 중..."
    echo "======================================"

    for name in "$COLLECTOR_PLIST_NAME" "$LINT_PLIST_NAME"; do
        plist="$LAUNCH_AGENTS/$name.plist"
        launchctl unload "$plist" 2>/dev/null && ok "$name 서비스 중지됨" || true
        rm -f "$plist" && ok "$plist 파일 삭제됨" || true
    done

    echo ""
    ok "서비스 제거 완료"
    echo ""
    exit 0
fi

echo ""
echo "======================================"
echo "  Life Memory Vault 맥미니 서비스 설치"
echo "======================================"
echo ""
echo "  프로젝트 위치: $ROOT"
echo ""

# ── 사전 확인 ──────────────────────────────────────────────────────
step "사전 확인"

# Python 3 확인
if ! command -v "$PYTHON" &>/dev/null; then
    err "Python 3가 설치되어 있지 않습니다. setup.sh를 먼저 실행하세요."
    exit 1
fi
ok "Python 3 확인됨"

# memory-config.json 확인
if [ ! -f "$ROOT/memory-config.json" ]; then
    err "memory-config.json 파일이 없습니다. setup.sh를 먼저 실행하세요:"
    echo "     bash scripts/setup.sh"
    exit 1
fi
ok "memory-config.json 확인됨"

# .env 확인
if [ ! -f "$ROOT/.env" ]; then
    err ".env 파일이 없습니다. setup.sh를 먼저 실행하세요:"
    echo "     bash scripts/setup.sh"
    exit 1
fi
ok ".env 파일 확인됨"

# memory-state 폴더 확인
mkdir -p "$ROOT/memory-state"
ok "memory-state/ 폴더 확인됨"

# LaunchAgents 폴더 확인
mkdir -p "$LAUNCH_AGENTS"

# ── A. Telegram 수집기 서비스 설치 ────────────────────────────────
step "A. Telegram 수집기 서비스 설치 (24/7 자동 실행)"

echo ""
echo "  이 서비스는:"
echo "  • 맥미니를 켤 때마다 Telegram 수집기를 자동으로 시작합니다"
echo "  • 수집기가 오류로 멈추면 즉시 자동으로 재시작합니다"
echo "  • 로그: $ROOT/memory-state/collector-service.log"
echo ""

cat > "$COLLECTOR_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$COLLECTOR_PLIST_NAME</string>

  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-B</string>
    <string>$ROOT/scripts/telegram_collector.py</string>
    <string>--loop</string>
  </array>

  <!-- 맥미니 켤 때 자동 시작 -->
  <key>RunAtLoad</key>
  <true/>

  <!-- 오류로 멈춰도 자동 재시작 (핵심 설정) -->
  <key>KeepAlive</key>
  <true/>

  <!-- 재시작 최소 간격: 10초 (너무 빨리 반복 재시작 방지) -->
  <key>ThrottleInterval</key>
  <integer>10</integer>

  <key>StandardOutPath</key>
  <string>$ROOT/memory-state/collector-service.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/memory-state/collector-service.log</string>

  <!-- 작업 디렉토리 -->
  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
EOF

# 기존 서비스가 있으면 먼저 중지
launchctl unload "$COLLECTOR_PLIST" 2>/dev/null || true

# 새 서비스 등록
launchctl load "$COLLECTOR_PLIST"
ok "수집기 서비스 설치 완료"
ok "서비스명: $COLLECTOR_PLIST_NAME"

# ── B. 자동 정리 스케줄러 설치 (2시간마다) ───────────────────────
step "B. 자동 정리 스케줄러 설치 (2시간마다)"

echo ""
echo "  이 스케줄러는:"
echo "  • 2시간마다 미처리 raw note를 자동으로 감지합니다"
echo "  • 미처리 메모가 있으면 rule-based 정리를 즉시 실행합니다"
echo "  • AI lint job을 큐에 등록합니다 (Claude Code에서 처리)"
echo "  • 미처리 메모가 없으면 그냥 넘어갑니다 (CPU 낭비 없음)"
echo "  • MacBook: 매일 22:00 1회 → 맥미니: 2시간마다"
echo ""

cat > "$LINT_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>$LINT_PLIST_NAME</string>

  <!-- python3 직접 실행: /bin/bash 로 ~/Documents 하위 스크립트를 실행하면
       macOS TCC 에 막혀 exit 126 (Operation not permitted) 발생. -->
  <key>ProgramArguments</key>
  <array>
    <string>$PYTHON</string>
    <string>-B</string>
    <string>$ROOT/scripts/scheduled_lint.py</string>
  </array>

  <!-- 2시간(7200초)마다 실행 -->
  <key>StartInterval</key>
  <integer>7200</integer>

  <key>StandardOutPath</key>
  <string>$ROOT/memory-state/scheduled-lint.log</string>
  <key>StandardErrorPath</key>
  <string>$ROOT/memory-state/scheduled-lint.log</string>

  <key>WorkingDirectory</key>
  <string>$ROOT</string>
</dict>
</plist>
EOF

# 기존 서비스가 있으면 먼저 중지
launchctl unload "$LINT_PLIST" 2>/dev/null || true

# 새 서비스 등록
launchctl load "$LINT_PLIST"
ok "스케줄러 서비스 설치 완료"
ok "서비스명: $LINT_PLIST_NAME"

# ── 설치 결과 확인 ───────────────────────────────────────────────
step "설치 결과 확인"

echo ""
RUNNING=$(launchctl list | grep "life-memory" | awk '{print $3}' | tr '\n' ', ')
if [ -n "$RUNNING" ]; then
    ok "실행 중인 서비스: $RUNNING"
else
    warn "서비스 목록 확인 필요"
fi

# ── 완료 ─────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  맥미니 서비스 설치 완료!"
echo "======================================"
echo ""
echo "  확인 명령어:"
echo ""
echo "  # 서비스 실행 상태 확인"
echo "  launchctl list | grep life-memory"
echo ""
echo "  # 수집기 로그 확인 (최근 20줄)"
echo "  tail -20 $ROOT/memory-state/collector-service.log"
echo ""
echo "  # 스케줄러 로그 확인"
echo "  tail -20 $ROOT/memory-state/scheduled-lint.log"
echo ""
echo "  서비스 제거 방법:"
echo "  bash scripts/install-mac-mini.sh --uninstall"
echo ""
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  이제 Telegram 봇에 메시지를 보내서"
echo "  '✓ 저장 완료' 답장이 오는지 확인하세요!"
echo "  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo ""
