#!/bin/bash
# CCC봇에 409 Conflict가 발생한 순간의 시스템 상태를 찍어 남긴다.
#
# 409 Conflict = 같은 봇 토큰으로 텔레그램을 동시에 조회하는 상대가 있다는 뜻.
# 상대가 단명 프로세스라 사후에는 흔적이 없어, 발생 시점에 잡아야 한다.
# 대상은 @songbongs_CCC_bot (CCC봇) — 기록봇과는 다른 토큰이다.
#
# 두 가지 방식으로 불린다:
#   1) 주기 실행(launchd, 30초) — 로그에 새 409가 생겼는지 보고 찍는다
#   2) ccc-mcp-wrapper.sh가 409 줄을 보는 즉시 인자 now와 함께 호출 — 실시간
# 실시간 호출이 범인을 잡을 확률이 높다. 주기 실행은 그 보완이다.

set -uo pipefail

RUNTIME_DIR="$HOME/Library/Application Support/life-memory"
LOG_DIR="$HOME/Library/Logs/life-memory"
SRC="$LOG_DIR/ccc-telegram-mcp.log"
OUT="$LOG_DIR/ccc-409-forensics.log"
SEEN="$RUNTIME_DIR/409-seen-count"

# ── 텔레그램 알림 (2026-08-04 추가) ────────────────────────────────
# 예전에는 재발해도 이 파일에만 적고 끝나서, 사용자가 "봇이 또 씹네" 하고
# 체감하기 전에는 아무도 몰랐다. 이제 재발하면 텔레그램으로 바로 알린다.
SENDER="$HOME/Documents/AI-PlayGround/life-memory-vault/scripts/telegram_ops_send.py"
PY="/opt/homebrew/bin/python3"
THREAD_ID="8461"                              # CCC봇 이슈를 논의해 온 토픽
ALERT_STAMP="$RUNTIME_DIR/409-last-alert"     # 마지막 발송 시각(epoch)
ALERT_LOCK="$RUNTIME_DIR/409-alert.lock"      # 동시 실행 방지
ALERT_COOLDOWN=3600                           # 같은 사태로 1시간에 한 번만

mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

TRIGGER="${1:-poll}"

if [ "$TRIGGER" != "now" ]; then
  [ -f "$SRC" ] || exit 0
  # grep -c 는 0건일 때 "0"을 찍고 exit 1 을 낸다. 그래서 `|| echo 0`을 붙이면
  # "0\n0" 두 줄이 되어 아래 숫자 비교가 통째로 깨진다(2026-08-30 수정).
  # 깨지면 조기 종료를 못 해 30초마다 헛스냅샷 + 1시간마다 가짜 409 알림이 간다.
  now=$(grep -c "409 Conflict" "$SRC" 2>/dev/null | head -1)
  prev=$(head -1 "$SEEN" 2>/dev/null)
  case "$now"  in ''|*[!0-9]*) now=0 ;;  esac
  case "$prev" in ''|*[!0-9]*) prev=0 ;; esac
  echo "$now" >"$SEEN"
  # 로그가 새로 만들어져 카운트가 줄면 기준만 다시 잡고 끝낸다.
  [ "$now" -le "$prev" ] && exit 0
  HEADER="409 Conflict 감지 (주기 점검, 누적 ${prev} → ${now})"
  DETAIL="누적 ${prev}건 → ${now}건 (방금 $((now - prev))건 늘었습니다)"
else
  HEADER="409 Conflict 감지 (실시간 — 상대가 아직 살아있을 가능성 높음)"
  DETAIL="봇이 409를 뱉는 순간 바로 잡았습니다"
fi

# 재발을 텔레그램으로 알린다.
# 409 폭주 때는 이 스크립트가 30초마다 + 로그 줄마다 불려서 수백 번 실행된다.
# 그래서 (1) mkdir로 동시 실행을 막고 (2) 1시간에 한 번만 보낸다.
# 잠금은 발송 "직전"까지만 잡는다 — 느린 파이썬 호출을 잠금 안에 두면
# 중간에 죽었을 때 잠금이 남아 알림이 영영 안 나간다.
notify_telegram() {
  mkdir "$ALERT_LOCK" 2>/dev/null || return 0

  local nowsec last
  nowsec=$(date '+%s')
  last=$(cat "$ALERT_STAMP" 2>/dev/null || echo 0)
  case "$last" in ''|*[!0-9]*) last=0 ;; esac

  if [ $((nowsec - last)) -lt "$ALERT_COOLDOWN" ]; then
    rmdir "$ALERT_LOCK" 2>/dev/null
    return 0
  fi
  echo "$nowsec" >"$ALERT_STAMP"
  rmdir "$ALERT_LOCK" 2>/dev/null

  [ -f "$SENDER" ] && [ -x "$PY" ] || {
    echo "  ⚠️ 알림 발송 불가 — 발송 스크립트나 python3가 없다" >>"$OUT"
    return 0
  }

  # 메시지에는 토큰이 될 만한 것을 절대 넣지 않는다. 숫자와 시각만 보낸다.
  local msg="🔴 CCC봇 409 재발

같은 봇 토큰으로 텔레그램을 동시에 조회하는 상대가 다시 나타났습니다.
${DETAIL}

새 토큰까지 새어나갔다는 뜻일 수 있습니다. 토큰을 또 바꾸는 걸로는
해결되지 않고, 유출 경로를 찾아야 합니다.

터미널에서 클로드코드를 열고
'409 재발했어, 조사해줘' 라고 말씀해 주세요.

감지 시각: $(date '+%Y-%m-%d %H:%M:%S')
상세 기록: ccc-409-forensics.log
※ 폭주해도 이 알림은 1시간에 한 번만 갑니다."

  if "$PY" "$SENDER" "$msg" --thread-id "$THREAD_ID" >/dev/null 2>&1; then
    echo "  ✅ 텔레그램 알림 발송함" >>"$OUT"
  else
    echo "  ⚠️ 텔레그램 알림 발송 실패" >>"$OUT"
  fi
}

# ps 출력에는 봇 토큰이 인자로 그대로 노출된다(예: cokacdir --ccserver -- 123:AAF...).
# 로그에 평문으로 남으면 유출이므로, 찍기 전에 비밀 부분만 가린다. 봇 ID는 식별에
# 필요하니 남긴다. (2026-08-03: 이미 남은 318건은 사후 마스킹 처리함)
mask_tokens() {
  sed -E 's/([0-9]{9,10}):[A-Za-z0-9_-]{35}/\1:<토큰가림>/g'
}

{
  echo "════════════════════════════════════════════════"
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] $HEADER"

  echo "--- 최근 409 로그 ---"
  grep "409 Conflict" "$SRC" 2>/dev/null | tail -3

  # 핵심 단서: 텔레그램 플러그인 bun이 2개 이상이면 그게 바로 범인이다.
  echo "--- 텔레그램 플러그인 bun 프로세스 (2개 이상이면 이것이 원인) ---"
  ps -eo pid,ppid,etime,command 2>/dev/null \
    | grep "claude-plugins-official/telegram" | grep -v grep | mask_tokens

  echo "--- claude 프로세스 전체 (특히 -p 세션 주목) ---"
  ps -eo pid,ppid,etime,command 2>/dev/null \
    | grep -E "bin/claude|claude -p" | grep -v grep \
    | grep -viE "Claude Helper|Claude\.app/Contents" | head -15 | mask_tokens

  echo "--- 2분 이내에 시작된 프로세스 ---"
  # macOS ps에는 etimes가 없다. etime이 MM:SS 형태면 1시간 미만이라는 뜻이다.
  ps -eo pid,etime,command 2>/dev/null \
    | awk '$2 ~ /^[0-9]?[0-9]:[0-9][0-9]$/ {
             split($2, t, ":");
             if (t[1] + 0 <= 2) print
           }' \
    | grep -viE "awk|grep|ps -eo" | head -20 | mask_tokens

  echo "--- 텔레그램 서버로 나가는 연결 (범인 특정용) ---"
  # launchd 환경에서는 PATH에 /usr/sbin이 없을 수 있어 절대경로를 먼저 쓴다.
  LSOF=/usr/sbin/lsof
  [ -x "$LSOF" ] || LSOF=$(command -v lsof 2>/dev/null)
  if [ -n "$LSOF" ] && [ -x "$LSOF" ]; then
    all=$("$LSOF" -nP -i TCP 2>/dev/null | grep -E "ESTABLISHED|SYN_SENT")

    # 2026-08-03 수정: 예전에는 전체 목록을 head -25로 잘라서 남겼는데,
    # 앞부분이 Electron/IDE 연결로 꽉 차 정작 봇 연결이 한 번도 안 찍혔다.
    # (스냅샷 1,874건 동안 텔레그램 연결 포착 0건 — 증거를 못 만들고 있었음)
    # 이제는 잘라내지 말고 '텔레그램 서버 대역'과 '봇 관련 프로세스'만 뽑는다.

    # 텔레그램 API 서버 대역: 149.154.160~175.x, 91.108.x
    tg=$(echo "$all" | grep -E "149\.15[0-9]\.|91\.108\.")
    if [ -n "$tg" ]; then
      echo "$tg"
      echo "  ↑ 위 목록에 서로 다른 PID가 2개 이상이면 그게 409의 범인이다."
    else
      echo "(텔레그램 대역 연결 없음 — 장기 폴링이 잠깐 끊긴 순간일 수 있음)"
    fi

    echo "  · 봇 관련 프로세스의 바깥 연결:"
    echo "$all" | grep -iE "^(bun|claude|node|[Pp]ython|cokacdir)" \
      | grep -v "127\.0\.0\.1" | head -20 | sed 's/^/    /' \
      || echo "    (없음)"
  else
    echo "(lsof 없음)"
  fi

  echo ""
} >>"$OUT"

# 증거를 먼저 남기고 나서 알린다 — 알림을 보고 로그를 열었을 때 이미 적혀 있도록.
notify_telegram

exit 0
