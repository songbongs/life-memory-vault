#!/bin/bash
# CCC봇(telegram MCP 서버) 실행 래퍼 — 시작/종료/오류를 파일에 남긴다.
#
# 배경: 2026-07-31 오후 bun MCP 서버가 4번 종료됐는데(16:10/16:29/17:11/17:34),
# claude 세션(PID 9418)은 계속 살아 있었다. 즉 세션이 아니라 MCP 자식만 죽는다.
# 그런데 이 서버는 로그를 전혀 남기지 않아 원인 추적이 불가능했다.
#
# 원본 실행 명령(플러그인 .mcp.json):
#   bun run --cwd ${CLAUDE_PLUGIN_ROOT} --shell=bun --silent start
#
# 사용법: ccc-mcp-wrapper.sh <플러그인 루트>
#
# 주의: stdout은 MCP 프로토콜 통로다. 절대 건드리지 않는다.
#       기록은 stderr만 가로채서 남긴다.

PLUGIN_ROOT="${1:-}"
LOG_DIR="$HOME/Library/Logs/life-memory"
LOG="$LOG_DIR/ccc-telegram-mcp.log"

mkdir -p "$LOG_DIR"

# ── 문지기: 정식 CCC 세션이 띄운 것만 통과시킨다 (2026-08-22 추가) ──────────
# 배경: cokacdir봇 등이 띄운 `claude -p`도 이 플러그인을 같이 로드한다
#       (~/.claude/settings.json 의 enabledPlugins 가 전역이라서).
#       그러면 server.ts 63~77줄이 bot.pid 에 적힌 폴러를 조건 없이 SIGTERM 하고,
#       그 단명 프로세스가 끝나면 폴러가 0개가 되어 CCC봇이 귀머거리가 된다.
#       409는 안 뜬다 — 충돌이 아니라 정중한 인계라서다. 2026-08-22 하루에만 9번 발생.
# 판별: 정식 세션만 `--channels plugin:telegram@claude-plugins-official` 을 달고 뜬다
#       (run-ccc.sh 40줄). 남이 띄운 claude 에는 없다.
# 안전: 조상 명령줄을 하나도 못 읽으면 통과시킨다(fail-open). 잘못 막아 봇이 죽는 것보다
#       한 번 뺏기는 편이 낫다.
GATE_CHAIN=""
GATE_OK=0
GATE_READ=0
gate_pid="$PPID"
for _ in 1 2 3 4 5; do
  [ -z "$gate_pid" ] && break
  [ "$gate_pid" = "0" ] || [ "$gate_pid" = "1" ] && break
  gate_cmd=$(ps -o command= -p "$gate_pid" 2>/dev/null)
  [ -n "$gate_cmd" ] && GATE_READ=1
  GATE_CHAIN="$GATE_CHAIN | $gate_pid:$(echo "$gate_cmd" | cut -c1-70)"
  case "$gate_cmd" in *--channels*) GATE_OK=1; break ;; esac
  gate_pid=$(ps -o ppid= -p "$gate_pid" 2>/dev/null | tr -d ' ')
done

if [ "$GATE_OK" != "1" ] && [ "$GATE_READ" = "1" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 🚫 비인가 호출 차단 — --channels 없는 claude가 폴러를 뺏으려 함$GATE_CHAIN" >>"$LOG"
  exit 0
fi
if [ "$GATE_READ" != "1" ]; then
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] ⚠️ 문지기: 조상 명령줄을 못 읽어 통과시킴 (PPID $PPID)" >>"$LOG"
fi
echo "[$(date '+%Y-%m-%d %H:%M:%S')] 문지기 통과$GATE_CHAIN" >>"$LOG"

# 안전장치: 인자가 비었거나 치환되지 않은 문자열이거나 실제 폴더가 아니면
# 플러그인 캐시에서 가장 최신 버전을 직접 찾는다.
# 이 래퍼가 실패하면 텔레그램 채널 자체가 끊기므로, 경로 문제로 죽지 않게 한다.
if [ -z "$PLUGIN_ROOT" ] || [ ! -d "$PLUGIN_ROOT" ]; then
  FALLBACK=$(ls -d "$HOME/.claude/plugins/cache/claude-plugins-official/telegram"/*/ 2>/dev/null \
    | sort -V | tail -1)
  echo "[$(date '+%Y-%m-%d %H:%M:%S')] 경고: 전달된 루트('$PLUGIN_ROOT')가 유효하지 않아 대체 경로 사용: $FALLBACK" >>"$LOG"
  PLUGIN_ROOT="${FALLBACK%/}"
fi

stamp() { date '+%Y-%m-%d %H:%M:%S'; }

echo "[$(stamp)] ===== MCP 서버 시작 (wrapper PID $$) root=$PLUGIN_ROOT" >>"$LOG"

# stderr만 타임스탬프를 붙여 로그로. stdout은 그대로 통과시킨다.
# 409 Conflict가 보이면 그 자리에서 스냅샷을 뜬다 — 상대가 아직 살아있을 때
# 잡아야 정체를 알 수 있다. 배경 실행이라 로그 처리를 막지 않는다.
SNAPSHOT="$HOME/Library/Application Support/life-memory/ccc-409-snapshot.sh"
bun run --cwd "$PLUGIN_ROOT" --shell=bun --silent start \
  2> >(while IFS= read -r line; do
          echo "[$(stamp)] $line"
          if [ "${line#*409 Conflict}" != "$line" ] && [ -x "$SNAPSHOT" ]; then
            bash "$SNAPSHOT" now >/dev/null 2>&1 &
          fi
        done >>"$LOG")
code=$?

echo "[$(stamp)] ===== MCP 서버 종료 (exit=$code)" >>"$LOG"
exit "$code"