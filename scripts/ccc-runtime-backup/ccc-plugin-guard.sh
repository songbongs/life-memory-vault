#!/bin/bash
# CCC봇 플러그인 로컬 패치 감시 + 자동 이식 (v2, 2026-08-15)
#
# 배경: 봇의 안정성이 플러그인 캐시 폴더 안을 직접 고친 것에 의존한다.
#   - server.ts : 409 자기충돌 무한루프 수정(2026-08-03) + 스레드(토픽) 답장 지원
#   - .mcp.json : 실행을 ccc-mcp-wrapper.sh 로 돌리는 연결 (2026-07-31)
#     이 연결이 로그·409 스냅샷·감시기·알림 전체의 진입점이다.
# 플러그인이 새 버전으로 올라가면 새 폴더가 생기고 위 수정은 따라가지 않는다.
#
# v1(2026-08-06)의 한계 — 이번에 고친 것:
#   v1은 "기준 버전 = 0.0.6" 을 박아두고 그 폴더만 봤다. 그래서
#   0.0.7이 깔리자(2026-08-15 01:04) 실제로는 수정이 이미 이식됐는데도(02:18)
#   "새 버전이 설치됐습니다" 를 매시간 반복하며 6시간마다 알림을 쐈다.
#   버전 번호를 따라가는 방식은 다음 버전마다 또 깨진다 — 사람이 매번 손대야 하고,
#   헛경보가 쌓이면 진짜 경보도 무시하게 된다.
#
# v2 방식:
#   1) 지금 실제로 쓰이는 버전을 installed_plugins.json 에서 읽는다(번호 안 박는다).
#   2) 그 폴더 안에 우리 수정의 '표식' 5개 + 래퍼 연결이 있는지 내용으로 확인한다.
#      → 0.0.8이든 0.1.0이든 스크립트를 안 고쳐도 된다.
#   3) 없으면 백업해둔 패치(local-patch.diff)를 자동으로 붙이고 검증한다.
#      성공하면 조용히 알리고, 실패할 때만 시끄럽게 알린다.
#
# 안전 설계:
#   - 패치는 임시 사본에 먼저 붙이고, 표식·크기 검증을 통과할 때만 제자리로 옮긴다.
#     즉 중간에 실패해도 원본이 깨지지 않는다.
#   - 원본은 옮기기 전에 반드시 vanilla 백업으로 남긴다.
#   - 기존 ccc-409-snapshot.sh 는 건드리지 않는다. 스탬프·락·로그를 전부 따로 쓴다.
#     이 스크립트가 죽어도 봇·409 감시·로그에는 아무 영향이 없다.
#   - bun 을 부르지 않는다. (23시 bun PATH 고장은 폴러 탈취를 막는 방패라 건드리면 안 된다)
#
# 사용법:
#   ccc-plugin-guard.sh           정기 점검 + 필요시 자동 이식 (launchd, 1시간 주기)
#   ccc-plugin-guard.sh --check   점검 결과만 화면에 출력. 고치지도 알리지도 않음
#   ccc-plugin-guard.sh --repair  지금 즉시 이식 시도 (알림은 보냄)
#   ccc-plugin-guard.sh --test    테스트 알림 발송 (쿨다운 무시, 스탬프 안 남김)

set -uo pipefail
PATH=/usr/bin:/bin:/usr/sbin:/sbin
export PATH

# 경로는 전부 환경변수로 갈아끼울 수 있다. 기본값은 실제 운영 경로다.
# 이 구멍은 오직 시험용이다 — 진짜 폴더를 건드리지 않고 "새 버전이 깔린 상황"을
# 통째로 흉내 내서 자동 이식이 실제로 되는지 확인하려고 뚫어뒀다.
RUNTIME_DIR="${GUARD_RUNTIME_DIR:-$HOME/Library/Application Support/life-memory}"
BACKUP_DIR="${GUARD_BACKUP_DIR:-$RUNTIME_DIR/plugin-backups}"
PATCH_FILE="$BACKUP_DIR/local-patch.diff"
PLUGIN_BASE="${GUARD_PLUGIN_BASE:-$HOME/.claude/plugins/cache/claude-plugins-official/telegram}"
INSTALLED_JSON="${GUARD_INSTALLED_JSON:-$HOME/.claude/plugins/installed_plugins.json}"
MCP_LOG="${GUARD_MCP_LOG:-$HOME/Library/Logs/life-memory/ccc-telegram-mcp.log}"

LOG="${GUARD_LOG:-$HOME/Library/Logs/life-memory/ccc-plugin-guard.log}"
LASTRUN="$RUNTIME_DIR/plugin-guard-lastrun"
LASTSTATE="$RUNTIME_DIR/plugin-guard-laststate"
LASTVER="$RUNTIME_DIR/plugin-guard-lastver"
RESTART_FLAG="$RUNTIME_DIR/plugin-guard-restart-needed"

SENDER="${GUARD_SENDER:-$HOME/Documents/AI-PlayGround/life-memory-vault/scripts/telegram_ops_send.py}"
PY="/opt/homebrew/bin/python3"
THREAD_ID="8461"
STAMP="$RUNTIME_DIR/plugin-guard-last-alert"   # 409 알림과 절대 공유하지 않는다
LOCK="$RUNTIME_DIR/plugin-guard-alert.lock"
COOLDOWN=21600                                  # 6시간에 한 번

# 우리 수정이 살아있는지 확인하는 표식.
# 고른 기준: 전부 로컬 수정으로만 들어가는 문장이고, 업스트림 원본(vanilla)에는 0건이다.
# 표식이 하나라도 없으면 그 수정은 날아간 것으로 본다.
MARKERS=(
  'const threadId = ctx.message?.message_thread_id'   # 받은 메시지의 토픽 번호 읽기
  'message_thread_id: thread_id'                      # 답장을 같은 토픽으로 보내기
  'STABLE_POLL_MS'                                    # 409 수정: 안정 폴링 기준 백오프 리셋
  'try { await bot.stop() } catch {}'                 # 409 수정: 재시도 전 이전 폴링 정리
  'is409 && attempt >= 20'                            # 409 수정: 포기 임계 8→20 + 프로세스 종료
)
WRAPPER_MARK='ccc-mcp-wrapper.sh'                     # .mcp.json 이 래퍼를 거치는지

MODE="${1:-poll}"

mkdir -p "$RUNTIME_DIR" "$BACKUP_DIR" "$(dirname "$LOG")" 2>/dev/null

stamp_now() { date '+%Y-%m-%d %H:%M:%S'; }
logline() { echo "[$(stamp_now)] $*" >>"$LOG"; }

PROBLEMS=""
NOTES=""
add_problem() { PROBLEMS="${PROBLEMS}· $1"$'\n'; }
add_note()    { NOTES="${NOTES}· $1"$'\n'; }

# ── 지금 실제로 쓰이는 버전 찾기 ─────────────────────────────────────
# 1순위: installed_plugins.json 의 installPath (클로드 코드가 실제로 쓰는 값)
# 2순위: 버전 폴더 중 가장 최신 (래퍼의 대체 경로 로직과 같은 규칙)
resolve_active() {
  local p=""
  if [ -f "$INSTALLED_JSON" ]; then
    p=$(tr ',' '\n' <"$INSTALLED_JSON" 2>/dev/null \
        | grep '"installPath"' \
        | grep 'claude-plugins-official/telegram' \
        | head -1 \
        | sed 's/.*"installPath"[[:space:]]*:[[:space:]]*"//; s/".*//')
  fi
  if [ -n "$p" ] && [ -d "$p" ]; then
    echo "$p"; return
  fi
  ls -d "$PLUGIN_BASE"/*/ 2>/dev/null | sort -V | tail -1 | sed 's:/$::'
}

markers_missing() {   # $1 = server.ts 경로. 없는 표식 개수를 출력한다.
  local f="$1" n=0 m
  for m in "${MARKERS[@]}"; do
    grep -qF "$m" "$f" 2>/dev/null || n=$((n + 1))
  done
  echo "$n"
}

# ── 자동 이식 ────────────────────────────────────────────────────────
# 임시 사본에 붙여보고, 검증을 통과할 때만 제자리로 옮긴다.
REPAIRED=""
repair_server_ts() {
  local dir="$1" ver="$2" ts tmp before after lines
  ts=$(date '+%Y%m%d_%H%M%S')

  [ -f "$PATCH_FILE" ] || { add_problem "이식할 패치 파일이 없습니다 ($PATCH_FILE)"; return 1; }
  [ -f "$dir/server.ts" ] || { add_problem "server.ts 가 아예 없습니다 ($dir)"; return 1; }

  tmp=$(mktemp -d) || { add_problem "임시 폴더를 못 만들어 이식을 건너뜁니다"; return 1; }
  cp "$dir/server.ts" "$tmp/server.ts" || { rm -rf "$tmp"; add_problem "server.ts 사본 생성 실패"; return 1; }

  before=$(markers_missing "$tmp/server.ts")

  # --forward: 이미 들어간 부분은 조용히 건너뛴다(업스트림이 일부를 흡수한 경우).
  # --fuzz=3 : 주변 줄이 조금 달라져도 붙인다.
  if ! /usr/bin/patch --forward --fuzz=3 -s "$tmp/server.ts" <"$PATCH_FILE" >/dev/null 2>&1; then
    logline "패치 적용 실패 — 원본은 그대로 둡니다 (버전 $ver)"
  fi

  after=$(markers_missing "$tmp/server.ts")
  lines=$(wc -l <"$tmp/server.ts" | tr -d ' ')

  if [ "$after" -ne 0 ]; then
    rm -rf "$tmp"
    add_problem "자동 이식 실패: 표식 ${after}개가 여전히 없습니다 (버전 $ver, 적용 전 ${before}개)"
    add_problem "업스트림 코드가 많이 바뀌어 패치가 안 붙는 상태입니다 — 사람이 봐야 합니다"
    return 1
  fi
  if [ "$lines" -lt 900 ]; then
    rm -rf "$tmp"
    add_problem "자동 이식 중단: 결과 파일이 비정상적으로 짧습니다 (${lines}줄)"
    return 1
  fi

  cp "$dir/server.ts" "$BACKUP_DIR/server.ts.vanilla-${ver}-${ts}" 2>/dev/null
  if ! cat "$tmp/server.ts" >"$dir/server.ts"; then
    rm -rf "$tmp"
    add_problem "자동 이식 실패: 파일을 제자리에 못 썼습니다 (권한 문제일 수 있음)"
    return 1
  fi
  rm -rf "$tmp"

  logline "server.ts 자동 이식 성공 (버전 $ver, 원본 백업: server.ts.vanilla-${ver}-${ts})"
  REPAIRED="${REPAIRED}· server.ts — 409 수정 + 토픽 답장 기능을 ${ver}에 이식했습니다"$'\n'
  return 0
}

repair_mcp_json() {
  local dir="$1" ver="$2" ts
  ts=$(date '+%Y%m%d_%H%M%S')
  [ -f "$dir/.mcp.json" ] && cp "$dir/.mcp.json" "$BACKUP_DIR/mcp.json.vanilla-${ver}-${ts}" 2>/dev/null

  cat >"$dir/.mcp.json" <<'JSON'
{
  "mcpServers": {
    "telegram": {
      "command": "/bin/bash",
      "args": [
        "/Users/mini-song/Library/Application Support/life-memory/ccc-mcp-wrapper.sh",
        "${CLAUDE_PLUGIN_ROOT}"
      ]
    }
  }
}
JSON

  if grep -qF "$WRAPPER_MARK" "$dir/.mcp.json" 2>/dev/null; then
    logline ".mcp.json 자동 복구 성공 (버전 $ver)"
    REPAIRED="${REPAIRED}· .mcp.json — 로그·409감시·알림 연결을 다시 붙였습니다"$'\n'
    return 0
  fi
  add_problem "자동 복구 실패: .mcp.json 을 못 썼습니다 (권한 문제일 수 있음)"
  return 1
}

# ── 점검 ────────────────────────────────────────────────────────────
ACTIVE=$(resolve_active)
ACTIVE_VER=$(basename "${ACTIVE:-}")
AUTOFIX=0
case "$MODE" in poll|--repair) AUTOFIX=1 ;; esac

if [ ! -d "$PLUGIN_BASE" ]; then
  add_problem "플러그인 폴더 자체가 없습니다 (봇이 아예 못 뜹니다)"
elif [ -z "${ACTIVE:-}" ] || [ ! -d "$ACTIVE" ]; then
  add_problem "지금 쓰이는 플러그인 폴더를 찾지 못했습니다"
else
  # 버전이 바뀌었으면 기록만 남긴다. 그 자체는 문제가 아니다 — 내용이 기준이다.
  PREVVER=$(cat "$LASTVER" 2>/dev/null || echo "")
  if [ -n "$PREVVER" ] && [ "$PREVVER" != "$ACTIVE_VER" ]; then
    logline "버전 변경 감지: ${PREVVER} → ${ACTIVE_VER} (내용으로 확인합니다)"
  fi
  echo "$ACTIVE_VER" >"$LASTVER"

  # 1) server.ts — 우리 수정 표식
  if [ ! -f "$ACTIVE/server.ts" ]; then
    add_problem "server.ts 가 없습니다 (버전 $ACTIVE_VER)"
  else
    MISS=$(markers_missing "$ACTIVE/server.ts")
    if [ "$MISS" -ne 0 ]; then
      logline "표식 ${MISS}개 누락 (버전 $ACTIVE_VER)"
      if [ "$AUTOFIX" = "1" ]; then
        repair_server_ts "$ACTIVE" "$ACTIVE_VER"
      else
        add_problem "409 수정·토픽 답장 표식 ${MISS}개가 없습니다 (버전 $ACTIVE_VER)"
      fi
    fi
  fi

  # 2) .mcp.json — 래퍼 연결
  if ! grep -qF "$WRAPPER_MARK" "$ACTIVE/.mcp.json" 2>/dev/null; then
    logline "래퍼 연결 없음 (버전 $ACTIVE_VER)"
    if [ "$AUTOFIX" = "1" ]; then
      repair_mcp_json "$ACTIVE" "$ACTIVE_VER"
    else
      add_problem "로그·409감시·알림 연결(.mcp.json)이 끊겼습니다 (버전 $ACTIVE_VER)"
    fi
  fi

  # 3) 이식했다면 봇이 새 코드를 읽으려면 재시작이 필요하다.
  #    재시작은 여기서 하지 않는다 — 대화 중인 세션을 끊을 수 있어서다.
  #    깃발만 남기고, 이후 MCP 서버가 다시 뜬 게 확인되면 스스로 지운다.
  if [ -n "$REPAIRED" ]; then
    echo "$(stamp_now)" >"$RESTART_FLAG"
  elif [ -f "$RESTART_FLAG" ]; then
    FLAG_AT=$(cat "$RESTART_FLAG" 2>/dev/null)
    LAST_START=$(grep 'MCP 서버 시작' "$MCP_LOG" 2>/dev/null | tail -1 | sed 's/^\[//; s/\].*//')
    if [ -n "$LAST_START" ] && [ -n "$FLAG_AT" ] && [ "$LAST_START" \> "$FLAG_AT" ]; then
      rm -f "$RESTART_FLAG"
      logline "재시작 반영 확인 (봇이 ${LAST_START}에 새 코드로 다시 떴습니다)"
    else
      add_note "이식한 수정은 봇이 재시작돼야 켜집니다 (매일 04:00 정기 재시작 때 자동 반영)"
    fi
  fi
fi

# ── 알림 ────────────────────────────────────────────────────────────
# 락은 발송 직전까지만 잡는다. 느린 파이썬 호출을 락 안에 두면 중간에 죽었을 때
# 락이 남아 알림이 영영 안 나간다. (409 스크립트에서 배운 방식)
send_telegram() {
  local body="$1"
  [ -f "$SENDER" ] && [ -x "$PY" ] || { logline "알림 발송 불가 — 발송 스크립트나 python3 없음"; return 1; }
  if "$PY" "$SENDER" "$body" --thread-id "$THREAD_ID" >/dev/null 2>&1; then
    logline "텔레그램 알림 발송함"
    return 0
  fi
  logline "텔레그램 알림 발송 실패"
  return 1
}

cooldown_ok() {   # 6시간에 한 번만 통과시킨다
  mkdir "$LOCK" 2>/dev/null || return 1
  local nowsec last
  nowsec=$(date '+%s')
  last=$(cat "$STAMP" 2>/dev/null || echo 0)
  case "$last" in ''|*[!0-9]*) last=0 ;; esac
  if [ $((nowsec - last)) -lt "$COOLDOWN" ]; then
    rmdir "$LOCK" 2>/dev/null
    return 1
  fi
  echo "$nowsec" >"$STAMP"
  rmdir "$LOCK" 2>/dev/null
  return 0
}

notify_problem() {
  cooldown_ok || return 0
  send_telegram "🟠 CCC봇 플러그인 — 자동 복구가 안 됩니다

새 버전에 우리 수정을 자동으로 붙이려다 실패했습니다.

${PROBLEMS}
이대로 두면 이런 일이 생길 수 있습니다:
· 409 무한루프 버그 부활 → 메시지 씹힘
· 답장이 이 대화방이 아닌 엉뚱한 곳으로 감
· 로그·409 감시·이 알림까지 정지 (다음엔 이 알림도 안 옵니다)

터미널에서 클로드코드를 열고
'플러그인 가드가 울렸어, 복구해줘' 라고 말씀해 주세요.

현재 버전: ${ACTIVE_VER:-알 수 없음}
감지 시각: $(stamp_now)
점검 기록: ccc-plugin-guard.log
※ 같은 문제로는 6시간에 한 번만 알립니다."
}

notify_repaired() {
  send_telegram "🔧 CCC봇 플러그인 — 자동 이식 완료

플러그인이 새 버전(${ACTIVE_VER})으로 올라가서, 우리가 손봐둔 수정을
자동으로 다시 붙였습니다. 확인해보니 정상입니다.

${REPAIRED}
${NOTES}
원본은 백업해뒀으니 되돌릴 수 있습니다.
조치 시각: $(stamp_now)"
}

# ── 실행 ────────────────────────────────────────────────────────────
date '+%Y-%m-%d %H:%M:%S' >"$LASTRUN"

if [ "$MODE" = "--test" ]; then
  # 테스트는 쿨다운을 무시하고, 스탬프를 남기지 않는다.
  # (스탬프를 남기면 진짜 문제가 6시간 묵살된다 — 지우는 걸 잊기 쉬워 아예 안 쓴다)
  send_telegram "🧪 [테스트] CCC봇 플러그인 감시 장치 점검

이 메시지가 보이면 감시 장치가 정상 작동합니다.
실제 문제가 생기면 🟠, 자동 복구에 성공하면 🔧 로 옵니다.

현재 버전: ${ACTIVE_VER:-알 수 없음}
점검 결과: ${PROBLEMS:-이상 없음}
점검 시각: $(stamp_now)"
  exit 0
fi

if [ "$MODE" = "--check" ]; then
  if [ -n "$PROBLEMS" ]; then
    printf '이상 감지 (버전 %s):\n%s' "${ACTIVE_VER:-?}" "$PROBLEMS"
  else
    echo "이상 없음 — 버전 ${ACTIVE_VER:-?}, 표식 ${#MARKERS[@]}개 + 래퍼 연결 모두 확인"
  fi
  [ -n "$NOTES" ] && printf '참고:\n%s' "$NOTES"
  exit 0
fi

if [ -n "$REPAIRED" ] && [ -z "$PROBLEMS" ]; then
  echo "OK" >"$LASTSTATE"
  rm -f "$STAMP" 2>/dev/null       # 복구했으니 다음 진짜 문제는 즉시 알린다
  logline "자동 이식 완료:"
  printf '%s' "$REPAIRED" >>"$LOG"
  notify_repaired
  exit 0
fi

if [ -n "$PROBLEMS" ]; then
  echo "BAD" >"$LASTSTATE"
  logline "이상 감지 (버전 ${ACTIVE_VER:-?}):"
  printf '%s' "$PROBLEMS" >>"$LOG"
  notify_problem
  exit 0
fi

# 정상. 직전이 이상 상태였다면 회복을 기록하고 한 번 알린다.
PREV=$(cat "$LASTSTATE" 2>/dev/null || echo "")
echo "OK" >"$LASTSTATE"
if [ "$PREV" = "BAD" ]; then
  logline "정상 회복 (버전 ${ACTIVE_VER:-?})"
  rm -f "$STAMP" 2>/dev/null
  send_telegram "🟢 CCC봇 플러그인 수정사항 정상 회복

아까 알려드린 문제가 해결됐습니다.
현재 버전: ${ACTIVE_VER:-알 수 없음}
확인 시각: $(stamp_now)"
fi
exit 0
