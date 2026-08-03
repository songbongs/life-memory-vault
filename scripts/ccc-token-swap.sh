#!/bin/bash
#
# 정본 위치: <저장소>/scripts/ccc-token-swap.sh  (~/ccc-token-swap.sh 는 이 파일을 가리키는 링크)
# 실행: bash ~/ccc-token-swap.sh   — 반드시 CCC 세션이 아닌 별도 터미널 창에서
# CCC봇 토큰 교체 도구
#
# 하는 일:
#   1. 현재 .env 백업
#   2. 새 토큰을 화면에 안 보이게 입력받음
#   3. 텔레그램에 진짜 유효한 토큰인지 먼저 확인 (getMe)
#   4. 확인되면 교체, 실패하면 원래대로 되돌림
#   5. 봇 재기동 후 3분간 409가 멎었는지 검증
#
# 토큰은 화면·로그·기록 어디에도 남지 않는다.

set -u

ENVF="$HOME/.claude/channels/telegram/.env"
LOG="$HOME/Library/Logs/life-memory/ccc-telegram-mcp.log"
BACKUP_DIR="$HOME/Library/Application Support/life-memory/token-backups"
TMUX_BIN="/opt/homebrew/bin/tmux"
STAMP=$(date '+%Y%m%d_%H%M%S')

RED=$'\033[31m'; GRN=$'\033[32m'; YLW=$'\033[33m'; BLD=$'\033[1m'; OFF=$'\033[0m'
say() { echo "$*"; }
ok()  { echo "${GRN}✅ $*${OFF}"; }
bad() { echo "${RED}❌ $*${OFF}"; }
warn(){ echo "${YLW}⚠️  $*${OFF}"; }

echo
echo "${BLD}════════ CCC봇 토큰 교체 ════════${OFF}"
echo

# ── 0. 사전 점검 ──────────────────────────────────
if [ ! -f "$ENVF" ]; then
  bad "설정 파일을 찾을 수 없습니다: $ENVF"
  echo "   교체를 진행할 수 없습니다. 이 화면을 그대로 캡처해서 알려주세요."
  exit 1
fi

OLD_ID=$(/usr/bin/awk -F'[=:]' '/^TELEGRAM_BOT_TOKEN=/{print $2}' "$ENVF" | tr -d ' \r')
say "현재 등록된 봇 번호: ${OLD_ID:-(없음)}"
echo

# ── 1. 백업 ──────────────────────────────────────
mkdir -p "$BACKUP_DIR"
BACKUP="$BACKUP_DIR/env.bak-$STAMP"
cp "$ENVF" "$BACKUP" && chmod 600 "$BACKUP"
ok "백업 완료: $BACKUP"
echo "   (문제가 생기면 이 파일로 언제든 되돌릴 수 있습니다)"
echo

# ── 2. 새 토큰 입력 ───────────────────────────────
echo "${BLD}새 토큰을 붙여넣고 Enter를 누르세요.${OFF}"
echo "  · 화면에는 ${BLD}아무것도 안 보입니다${OFF} — 정상입니다. 그냥 붙여넣고 Enter 하세요"
echo "  · 붙여넣기: ⌘ + V"
echo "  · 취소하려면 Enter만 누르세요"
echo
printf "새 토큰 > "
read -s NEWTOK
echo
echo

if [ -z "$NEWTOK" ]; then
  warn "입력이 없어 취소했습니다. 바뀐 것은 없습니다."
  exit 0
fi

# 앞뒤 공백·따옴표 제거
NEWTOK=$(echo "$NEWTOK" | tr -d ' \r\n"'"'")

# ── 3. 형식 검사 ──────────────────────────────────
if ! echo "$NEWTOK" | grep -qE '^[0-9]{8,12}:[A-Za-z0-9_-]{30,}$'; then
  bad "토큰 형식이 올바르지 않습니다."
  echo "   토큰은 '숫자10자리:영문숫자35자' 모양이어야 합니다."
  echo "   예시 모양: 1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ123456789"
  echo "   BotFather가 준 줄을 통째로 복사했는지 확인해 주세요."
  echo "   ${BLD}바뀐 것은 없습니다.${OFF}"
  exit 1
fi

NEW_ID="${NEWTOK%%:*}"
say "입력된 봇 번호: $NEW_ID"
if [ -n "$OLD_ID" ] && [ "$NEW_ID" != "$OLD_ID" ]; then
  warn "기존 봇 번호($OLD_ID)와 다릅니다!"
  echo "   토큰을 재발급하면 봇 번호는 ${BLD}그대로여야${OFF} 합니다."
  echo "   번호가 다르다면 다른 봇의 토큰을 복사하셨을 가능성이 큽니다."
  echo "   (그대로 진행하면 대화창이 바뀌어 기존 대화 내역을 못 씁니다)"
  printf "   그래도 진행할까요? [y/N] > "
  read ANS
  case "$ANS" in y|Y) ;; *) warn "취소했습니다. 바뀐 것은 없습니다."; exit 0;; esac
fi
echo

# ── 4. 유효성 확인 (텔레그램에 직접 물어봄) ────────
say "텔레그램에 이 토큰이 진짜 유효한지 확인 중..."
RESP=$(/usr/bin/curl -s -m 20 "https://api.telegram.org/bot${NEWTOK}/getMe")
if ! echo "$RESP" | grep -q '"ok":true'; then
  bad "텔레그램이 이 토큰을 거부했습니다."
  echo "   응답: $(echo "$RESP" | cut -c1-120)"
  echo "   토큰을 다시 복사해서 시도해 주세요."
  echo "   ${BLD}바뀐 것은 없습니다.${OFF}"
  exit 1
fi
UNAME=$(echo "$RESP" | /usr/bin/sed -n 's/.*"username":"\([^"]*\)".*/\1/p')
ok "유효한 토큰입니다 — 봇 이름: @${UNAME:-확인불가}"
echo

# ── 5. 교체 ──────────────────────────────────────
TMP=$(mktemp)
if grep -q '^TELEGRAM_BOT_TOKEN=' "$ENVF"; then
  # 해당 줄만 교체, 나머지 설정은 그대로 보존
  /usr/bin/awk -v t="$NEWTOK" '/^TELEGRAM_BOT_TOKEN=/{print "TELEGRAM_BOT_TOKEN=" t; next} {print}' "$ENVF" > "$TMP"
else
  cp "$ENVF" "$TMP"; echo "TELEGRAM_BOT_TOKEN=$NEWTOK" >> "$TMP"
fi
cp "$TMP" "$ENVF" && chmod 600 "$ENVF"
rm -f "$TMP"
unset NEWTOK
ok "설정 파일 교체 완료"
echo

# ── 6. 봇 재기동 ──────────────────────────────────
say "봇을 재기동합니다 (1~2분 걸립니다)..."
for b in $(/usr/bin/pgrep -f "bun server.ts" 2>/dev/null); do
  /bin/kill -TERM "$b" 2>/dev/null && say "   기존 수신기 종료 (PID $b)"
done
sleep 5
for b in $(/usr/bin/pgrep -f "bun server.ts" 2>/dev/null); do /bin/kill -KILL "$b" 2>/dev/null; done
sleep 2

if [ -x "$TMUX_BIN" ] && "$TMUX_BIN" has-session -t ccc 2>/dev/null; then
  "$TMUX_BIN" send-keys -t ccc "/reload-plugins" Enter
  say "   ccc 세션에 재기동 명령 전송"
else
  warn "ccc 세션을 못 찾았습니다. 봇이 자동으로 안 살아나면 알려주세요."
fi

say "   재기동 대기 중..."
UP=""
for i in $(seq 1 24); do
  sleep 5
  if /usr/bin/pgrep -f "bun server.ts" >/dev/null 2>&1; then UP="yes"; break; fi
done
if [ -n "$UP" ]; then ok "봇 재기동 확인"; else warn "2분 내 재기동 안 됨 — 아래 검증 결과를 보고 알려주세요"; fi
echo

# ── 7. 검증 ──────────────────────────────────────
say "${BLD}409가 멎었는지 3분간 지켜봅니다...${OFF}"
START_LINES=$(wc -l < "$LOG" 2>/dev/null || echo 0)
for m in 1 2 3; do
  sleep 60
  DELTA=$(/usr/bin/tail -n +$((START_LINES+1)) "$LOG" 2>/dev/null)
  N409=$(echo "$DELTA" | grep -c "409 Conflict")
  say "   ${m}분 경과 — 409 발생 누적: ${N409}건"
done

echo
echo "${BLD}════════ 결과 ════════${OFF}"
DELTA=$(/usr/bin/tail -n +$((START_LINES+1)) "$LOG" 2>/dev/null)
N409=$(echo "$DELTA" | grep -c "409 Conflict")
NPOLL=$(echo "$DELTA" | grep -c "polling as")

if [ "$N409" -le 2 ]; then
  ok "성공입니다! 3분간 409가 ${N409}건뿐입니다 (교체 전에는 3분에 40건 이상)"
  echo "   경쟁 상대가 차단됐습니다. 이제 텔레그램에서 CCC봇에게 말을 걸어보세요."
else
  bad "409가 여전합니다 (3분간 ${N409}건)"
  echo "   ${BLD}이건 중요한 정보입니다${OFF} — 새 토큰까지 새어나가고 있다는 뜻이라"
  echo "   이 맥 안에서 토큰이 유출되는 경로를 따로 조사해야 합니다."
  echo "   이 화면을 그대로 알려주세요."
fi
echo
say "폴링 시도 횟수: $NPOLL회 / 백업 위치: $BACKUP"
echo
echo "되돌리려면 (필요할 때만):"
echo "  cp \"$BACKUP\" \"$ENVF\" && $TMUX_BIN send-keys -t ccc \"/reload-plugins\" Enter"
echo
