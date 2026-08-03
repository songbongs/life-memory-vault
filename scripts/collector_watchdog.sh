#!/bin/bash
# 기록봇(telegram_collector) 헬스체크 및 자동 복구.
#
# 2026-07-31 사고 대응: brew가 python@3.14를 올리면서
#   (1) 실행 중이던 수집기의 파이썬 바이너리가 삭제되고
#   (2) 새 바이너리가 macOS TCC(문서 폴더) 승인을 잃어
# 수집기가 "실행 중"인 채로 12분 넘게 정지했다. 프로세스는 살아 있었으므로
# 기존 감시(KeepAlive)로는 잡히지 않았다.
#
# 일부러 bash로 작성한다 — 파이썬이 망가진 상황을 감지하는 것이 목적이므로
# 감시자 자신이 파이썬에 의존하면 같이 죽는다.
#
# 감시자 자신도 절대 매달리면 안 된다. 모든 외부 명령은 run_bounded로 감싼다
# (첫 버전에서 launchctl bootout이 21분간 블록된 사고가 있었다).
#
# 배포 위치 주의: 이 파일이 원본이지만, 실제로 도는 것은
#   ~/Library/Application Support/life-memory/collector_watchdog.sh 사본이다.
# launchd가 띄우는 /bin/bash는 ~/Documents 접근 권한(TCC)이 없어서
# 이 경로에 둔 채로는 "Operation not permitted"로 실행조차 되지 않는다.
# 수정한 뒤에는 scripts/deploy_watchdog.sh로 다시 배포해야 반영된다.

set -uo pipefail

LABEL="com.sangmin.life-memory-collector"
ROOT="/Users/mini-song/Documents/AI-PlayGround/life-memory-vault"
PLIST="$HOME/Library/LaunchAgents/${LABEL}.plist"
LOG_DIR="$HOME/Library/Logs/life-memory"
LOG="$LOG_DIR/watchdog.log"
TCC_FIX="$HOME/fix-python-tcc.sh"

# 상태 파일은 ~/Documents 밖에 둔다 — launchd로 실행될 때 그 안에는 쓸 수 없다.
RUNTIME_DIR="$HOME/Library/Application Support/life-memory"
STATE="$RUNTIME_DIR/watchdog-state"
NOTOKEN_MARK="$RUNTIME_DIR/watchdog-no-token"
# 봇 토큰/채팅 ID를 Documents 밖에서도 읽을 수 있게 하려면 이 파일에 넣는다(선택).
# TELEGRAM_BOT_TOKEN=... / TELEGRAM_CHAT_ID=... 두 줄. 없으면 4번 점검만 생략된다.
FALLBACK_ENV="$RUNTIME_DIR/watchdog.env"

# 하위 프로세스가 이보다 오래 살아 있으면 정지로 본다(초).
# telegram_collector.py의 SUBPROCESS_TIMEOUT(120초)보다 넉넉히 크게 잡아
# 정상적인 느린 작업을 오탐하지 않는다.
STUCK_CHILD_SECONDS=300

# 외부 명령 제한시간(초)
LAUNCHCTL_TIMEOUT=30
TCC_TIMEOUT=60

mkdir -p "$LOG_DIR" "$RUNTIME_DIR"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >>"$LOG"; }

# 명령을 제한시간 안에서 실행한다. 초과하면 종료시키고 124를 돌려준다.
run_bounded() {
  local secs="$1"; shift
  "$@" &
  local pid=$! waited=0
  while kill -0 "$pid" 2>/dev/null && [ "$waited" -lt "$secs" ]; do
    sleep 1
    waited=$((waited + 1))
  done
  if kill -0 "$pid" 2>/dev/null; then
    kill -TERM "$pid" 2>/dev/null
    sleep 1
    kill -KILL "$pid" 2>/dev/null
    wait "$pid" 2>/dev/null
    return 124
  fi
  wait "$pid" 2>/dev/null
  return $?
}

notify() {
  # 텔레그램 알림은 실패해도 복구를 막지 않는다.
  local msg="$1" token chat
  token=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
  # allowedUserIds 배열의 첫 번째 ID. 파일 앞쪽의 바이트 크기 설정값을 집지 않도록
  # 반드시 그 키 다음부터 찾는다.
  chat=$(awk '/"allowedUserIds"/{f=1;next} f&&/[0-9]/{gsub(/[^0-9]/,"");if(length($0))print;exit}' \
    "$ROOT/memory-config.json" 2>/dev/null)
  # Documents가 막혀 있으면(launchd 실행 시) 밖에 둔 사본을 쓴다.
  if [ -r "$FALLBACK_ENV" ]; then
    [ -z "$token" ] && token=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$FALLBACK_ENV" | cut -d= -f2- | tr -d '"'"'"' ')
    [ -z "$chat" ] && chat=$(grep -m1 '^TELEGRAM_CHAT_ID=' "$FALLBACK_ENV" | cut -d= -f2- | tr -d '"'"'"' ')
  fi
  [ -n "$token" ] && [ -n "$chat" ] && \
    curl -s -m 10 -o /dev/null "https://api.telegram.org/bot${token}/sendMessage" \
      --data-urlencode "chat_id=${chat}" --data-urlencode "text=${msg}" || true
}

collector_pid() {
  launchctl list 2>/dev/null | awk -v l="$LABEL" '$3==l {print $1}' | grep -E '^[0-9]+$' || true
}

service_loaded() {
  launchctl list 2>/dev/null | awk -v l="$LABEL" '$3==l {found=1} END{exit !found}'
}

# recover <사유> <tcc: yes|no>
# TCC 초기화는 승인을 걷어내고 다시 받게 하는 무거운 작업이라
# 실제로 권한 정지가 의심될 때만 한다. 단순히 안 떠 있는 경우엔 건너뛴다.
recover() {
  local reason="$1" want_tcc="${2:-no}"
  log "복구 시작 — 사유: $reason (TCC 초기화: $want_tcc)"

  # 정지한 하위 프로세스부터 정리 (부모가 subprocess.run에 묶여 있다)
  local pid
  pid=$(collector_pid)
  if [ -n "$pid" ]; then
    pkill -TERM -P "$pid" 2>/dev/null && log "  하위 프로세스 종료 신호 전송"
  fi

  if [ "$want_tcc" = "yes" ] && [ -x "$TCC_FIX" ]; then
    log "  TCC 권한 복구: $TCC_FIX"
    run_bounded "$TCC_TIMEOUT" bash "$TCC_FIX" >>"$LOG" 2>&1
    [ $? -eq 124 ] && log "  경고: TCC 복구가 ${TCC_TIMEOUT}초를 넘겨 중단됨"
  fi

  # 서비스가 등록돼 있으면 kickstart(제자리 재시작)가 빠르고 안전하다.
  # bootout은 서비스 해제가 끝날 때까지 매달릴 수 있어 최후 수단으로만 쓴다.
  if service_loaded; then
    log "  kickstart로 재시작"
    run_bounded "$LAUNCHCTL_TIMEOUT" launchctl kickstart -k "gui/$(id -u)/${LABEL}"
    [ $? -eq 124 ] && log "  경고: kickstart가 ${LAUNCHCTL_TIMEOUT}초를 넘김"
  else
    log "  서비스 미등록 — bootstrap으로 등록"
    run_bounded "$LAUNCHCTL_TIMEOUT" launchctl bootstrap "gui/$(id -u)" "$PLIST"
    [ $? -eq 124 ] && log "  경고: bootstrap이 ${LAUNCHCTL_TIMEOUT}초를 넘김"
  fi

  # 최대 30초까지 기다리며 기동 확인
  local newpid="" waited=0
  while [ "$waited" -lt 30 ]; do
    sleep 2
    waited=$((waited + 2))
    newpid=$(collector_pid)
    [ -n "$newpid" ] && break
  done

  if [ -n "$newpid" ]; then
    log "  ✅ 재기동 완료 (PID $newpid, ${waited}초 소요)"
    notify "🔧 기록봇 자동 복구됨
사유: ${reason}
새 PID: ${newpid}
자세한 내용: ~/Library/Logs/life-memory/watchdog.log"
  else
    log "  ❌ 재기동 실패 — 수동 확인 필요"
    notify "⚠️ 기록봇 자동 복구 실패
사유: ${reason}
수동 확인이 필요합니다."
  fi
  rm -f "$STATE"
}

PID=$(collector_pid)

# 1) 아예 안 떠 있는 경우 — TCC와 무관하므로 초기화 없이 재기동만 한다
if [ -z "$PID" ]; then
  recover "수집기 프로세스 없음" no
  exit 0
fi

# 2) 실행 중인 파이썬 바이너리가 디스크에서 사라진 경우 (brew 업그레이드 직후).
#    새 바이너리는 TCC 승인을 새로 받아야 하므로 초기화까지 함께 한다.
#    절대경로일 때만 판단한다 — ps가 경로가 아닌 이름만 돌려주면 오탐으로
#    무한 재기동에 빠지므로 조용히 건너뛴다.
EXEC_PATH=$(ps -p "$PID" -o comm= 2>/dev/null)
if [ "${EXEC_PATH:0:1}" = "/" ] && [ ! -e "$EXEC_PATH" ]; then
  recover "실행 중인 파이썬 바이너리가 삭제됨 ($EXEC_PATH)" yes
  exit 0
fi

# 3) 하위 프로세스가 너무 오래 살아 있는 경우 — TCC 승인 대기 정지의 전형적 증상
for child in $(pgrep -P "$PID" 2>/dev/null); do
  etime=$(ps -p "$child" -o etimes= 2>/dev/null | tr -d ' ')
  if [ -n "$etime" ] && [ "$etime" -gt "$STUCK_CHILD_SECONDS" ]; then
    cmd=$(ps -p "$child" -o command= 2>/dev/null | cut -c1-80)
    recover "하위 프로세스가 ${etime}초째 정지 ($cmd)" yes
    exit 0
  fi
done

# 4) 텔레그램에 밀린 메시지가 연속 2회 남아 있는 경우
#    (프로세스는 멀쩡해 보이지만 폴링을 못 하고 있는 상태)
#
#    이 점검만 봇 토큰이 필요하다. 토큰은 ~/Documents 안에 있어서 launchd로
#    실행될 때는 TCC에 막혀 못 읽는다. 그때는 1~3번 점검만으로 동작하고
#    조용히 건너뛴다 — 오늘(2026-07-31) 사고는 3번으로 잡힌다.
TOKEN=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$ROOT/.env" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
if [ -z "$TOKEN" ] && [ -r "$FALLBACK_ENV" ]; then
  TOKEN=$(grep -m1 '^TELEGRAM_BOT_TOKEN=' "$FALLBACK_ENV" 2>/dev/null | cut -d= -f2- | tr -d '"'"'"' ')
fi
if [ -z "$TOKEN" ]; then
  # 5분마다 같은 줄을 남기지 않도록 최초 1회만 기록한다.
  if [ ! -f "$NOTOKEN_MARK" ]; then
    log "봇 토큰을 읽을 수 없어 밀린 메시지 점검을 건너뜀 (1~3번 점검은 정상 동작)"
    log "  활성화하려면: $FALLBACK_ENV 에 TELEGRAM_BOT_TOKEN=... 한 줄 추가"
    : >"$NOTOKEN_MARK"
  fi
else
  rm -f "$NOTOKEN_MARK"
fi
if [ -n "$TOKEN" ]; then
  PENDING=$(curl -s -m 15 "https://api.telegram.org/bot${TOKEN}/getWebhookInfo" \
    | sed -n 's/.*"pending_update_count":\([0-9]*\).*/\1/p')
  if [ -n "$PENDING" ] && [ "$PENDING" -gt 0 ]; then
    if [ -f "$STATE" ]; then
      recover "밀린 메시지 ${PENDING}건이 연속 2회 확인됨 (폴링 정지 의심)" yes
      exit 0
    fi
    log "밀린 메시지 ${PENDING}건 — 다음 점검에서 재확인"
    echo "$PENDING" >"$STATE"
    exit 0
  fi
fi

rm -f "$STATE"
exit 0
