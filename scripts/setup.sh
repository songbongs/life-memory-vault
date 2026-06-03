#!/bin/bash
# Life Memory Vault — 새 기기 초기 설정 스크립트
#
# 처음 이 프로젝트를 설치할 때 한 번만 실행하면 됩니다.
# 사용법:
#   bash scripts/setup.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

ok()   { echo -e "${GREEN}  ✅ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠️  $1${NC}"; }
err()  { echo -e "${RED}  ❌ $1${NC}"; }
step() { echo -e "\n${YELLOW}━━━ $1 ━━━${NC}"; }

echo ""
echo "======================================"
echo "  Life Memory Vault 초기 설정"
echo "======================================"
echo ""
echo "  프로젝트 위치: $ROOT"
echo ""

# ── STEP 1: Python 3 확인 ──────────────────────────────────────────
step "STEP 1: Python 3 설치 확인"

if command -v python3 &>/dev/null; then
    PY_VER=$(python3 --version 2>&1)
    ok "Python 3 설치됨: $PY_VER"
else
    err "Python 3가 설치되어 있지 않습니다."
    echo ""
    echo "  설치 방법:"
    echo "  1. https://brew.sh 에서 Homebrew를 먼저 설치하세요"
    echo "  2. 터미널에서: brew install python3"
    echo ""
    exit 1
fi

# ── STEP 2: 필요한 폴더 생성 ───────────────────────────────────────
step "STEP 2: 필요한 폴더 생성"

mkdir -p "$ROOT/memory-state/jobs"
ok "memory-state/ 폴더 준비됨"
ok "memory-state/jobs/ 폴더 준비됨"

# ── STEP 3: memory-config.json 확인 ───────────────────────────────
step "STEP 3: memory-config.json 설정 확인"

CONFIG="$ROOT/memory-config.json"
EXAMPLE="$ROOT/memory-config.example.json"

if [ -f "$CONFIG" ]; then
    ok "memory-config.json 이미 존재합니다"
else
    if [ -f "$EXAMPLE" ]; then
        cp "$EXAMPLE" "$CONFIG"
        warn "memory-config.json이 없어서 example에서 복사했습니다."
        echo ""
        echo "  ┌─────────────────────────────────────────────────────────┐"
        echo "  │  지금 해야 할 일: memory-config.json 파일 편집          │"
        echo "  │                                                         │"
        echo "  │  아래 항목을 실제 Obsidian vault 경로로 바꿔 주세요:    │"
        echo "  │                                                         │"
        echo "  │  \"vaultPath\": \"/path/to/your/memory/vault\"          │"
        echo "  │               ↓                                         │"
        echo "  │  맥미니 예시:                                           │"
        echo "  │  \"/Users/mini-song/Library/CloudStorage/...vault\"     │"
        echo "  │                                                         │"
        echo "  │  편집 명령어: open $CONFIG  │"
        echo "  └─────────────────────────────────────────────────────────┘"
        echo ""
    else
        err "memory-config.example.json 파일을 찾을 수 없습니다."
        exit 1
    fi
fi

# ── STEP 4: .env 확인 ─────────────────────────────────────────────
step "STEP 4: .env (봇 토큰) 설정 확인"

ENV_FILE="$ROOT/.env"
ENV_EXAMPLE="$ROOT/.env.example"

if [ -f "$ENV_FILE" ]; then
    if grep -q "TELEGRAM_BOT_TOKEN=" "$ENV_FILE" && ! grep -q "여기에_봇_토큰_입력" "$ENV_FILE"; then
        ok ".env 파일에 봇 토큰이 설정되어 있습니다"
    else
        warn ".env 파일은 있지만 봇 토큰이 아직 입력되지 않았습니다."
        echo ""
        echo "  $ENV_FILE 파일을 열어서"
        echo "  TELEGRAM_BOT_TOKEN= 뒤에 실제 봇 토큰을 입력해 주세요."
        echo ""
    fi
else
    if [ -f "$ENV_EXAMPLE" ]; then
        cp "$ENV_EXAMPLE" "$ENV_FILE"
        warn ".env 파일이 없어서 example에서 복사했습니다."
        echo ""
        echo "  ┌─────────────────────────────────────────────────────────┐"
        echo "  │  지금 해야 할 일: .env 파일 편집                        │"
        echo "  │                                                         │"
        echo "  │  Telegram @BotFather 에게 받은 봇 토큰을 넣어주세요:    │"
        echo "  │                                                         │"
        echo "  │  TELEGRAM_BOT_TOKEN=여기에_봇_토큰_입력                 │"
        echo "  │                    ↓                                    │"
        echo "  │  TELEGRAM_BOT_TOKEN=1234567890:ABCdef...               │"
        echo "  │                                                         │"
        echo "  │  편집 명령어: open $ENV_FILE"
        echo "  └─────────────────────────────────────────────────────────┘"
        echo ""
    else
        err ".env.example 파일을 찾을 수 없습니다."
        exit 1
    fi
fi

# ── STEP 5: 도구 점검 ─────────────────────────────────────────────
step "STEP 5: 필요한 도구 점검"

python3 -B "$ROOT/scripts/mem.py" doctor 2>/dev/null || true

# ── 완료 ──────────────────────────────────────────────────────────
echo ""
echo "======================================"
echo "  초기 설정 완료!"
echo "======================================"
echo ""
echo "  다음 단계:"
echo ""
echo "  1. memory-config.json에 Obsidian vault 경로를 설정하세요"
echo "     (아직 안 했다면)"
echo ""
echo "  2. .env에 Telegram 봇 토큰을 입력하세요"
echo "     (아직 안 했다면)"
echo ""
echo "  3. 맥미니에서 수집기를 24/7 서비스로 설치하려면:"
echo "     bash scripts/install-mac-mini.sh"
echo ""
echo "  4. 바로 수동으로 시작하려면:"
echo "     python3 scripts/memory_admin.py"
echo "     브라우저: http://127.0.0.1:8765"
echo ""
