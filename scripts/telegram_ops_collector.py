#!/usr/bin/env python3
"""텔레그램 CCC봇 감시 프로세스.

bun(MCP 서버)이 살아있는지 주기적으로 확인하고,
죽으면 tmux 자동 복구를 시도하고 실패 시 텔레그램 알림 발송.

직접 폴링(getUpdates)은 하지 않는다 — bun과의 409 Conflict로
bun이 스스로 종료하는 원인이 되기 때문.
Telegram 서버는 메시지를 24시간 보관하므로 bun 복구 후 자동 전달된다.

- bun 살아있음: 30초마다 확인 후 대기
- bun 죽음 (3단 복구):
    0단계. claude 프로세스 기동 확인 + bun 자동 기동 유예(최대 60+90초) —
           claude 부재 중(일일 재시작 직후) 키를 보내면 아무도 받지 못하고,
           입력 큐에 쌓였다가 새 claude가 뜬 뒤 엉뚱하게 소비된다.
           claude가 뜨면 bun이 스스로 뜨는지 잠깐 기다려 보고, 뜨면
           키 없이 복구 완료. (2026-09-27 개선: 04:00:26 헛발 사례)
    1단계. tmux ccc 세션에 /reload-plugins 전송 → 30초 대기
    2단계. 실패 시 /mcp 메뉴에서 Reconnect 자동 실행 → 30초 대기
           (화살표 횟수를 박지 않는다. capture-pane으로 ❯ 커서 줄을 매번
            읽어 확인하고, 확인 못 하면 Escape로 빠져나와 실패 처리한다)
    3단계. 그래도 실패: 사용자에게 /exit 안내 알림 + 10분마다 재시도/재알림
  복구 성공 판정은 bun_is_running()이 결정하고,
  래퍼 로그의 '===== MCP 서버 시작' 줄로 교차 확인한다.
  /reload-plugins가 보고하는 '1 plugin MCP server'는 근거로 쓰지 않는다
  (2026-09-10: 그렇게 보고하고도 bun이 안 떴다).
- bun 복구: 대기 모드로 복귀
"""

from __future__ import annotations
import os
import subprocess
import sys
import time
from pathlib import Path
from datetime import datetime

SEND_SCRIPT = Path(__file__).resolve().parent / "telegram_ops_send.py"
PID_FILE = Path("/tmp/telegram-ops-collector.pid")

STANDBY_INTERVAL = 30   # bun 살아있을 때 재확인 주기(초)
ALERT_COOLDOWN = 600    # 동일 이벤트 재알림 최소 간격(초, 10분)
TMUX_SESSION = "ccc"    # CCC가 실행되는 tmux 세션 이름
RECOVERY_WAIT = 30      # 1단계: /reload-plugins 전송 후 bun 재기동 대기(초)
MCP_RECONNECT_WAIT = 30  # 2단계: /mcp Reconnect 후 bun 재기동 대기(초)
CLAUDE_START_WAIT = 60   # 0단계-1: claude 프로세스 기동 대기(초) — 래퍼 재기동 창 30초의 2배
CLAUDE_BOOT_GRACE = 90   # 0단계-2: claude 기동 후 bun 자동 기동 유예(초) — 최악 150초 지연 한도
CLAUDE_PGREP = "claude --channels plugin:telegram"  # 운영봇 claude 판별(2026-09-27 실측)
MCP_MENU_MAX_STEPS = 30  # /mcp 메뉴에서 Down 최대 횟수 — 넘으면 Escape로 탈출
MCP_CURSOR = "❯"         # 메뉴 선택 커서 (2026-09-10 실화면 확인)
MCP_TARGET_LINE = "plugin:telegram:telegram"   # 1차 메뉴에서 고를 항목
MCP_ACTION_LINE = "Reconnect"                  # 2차 메뉴에서 고를 항목
MCP_LOG = Path.home() / "Library/Logs/life-memory/ccc-telegram-mcp.log"
MCP_START_MARK = "===== MCP 서버 시작"
# claude가 '진짜 실행 중'일 때만 footer에 뜨는 문자열.
# 옛 판정은 "⏵⏵"였는데, ccc봇은 --dangerously-skip-permissions로 떠서
# footer에 "⏵⏵ bypass permissions on"이 항상 박혀 있다 → 언제나 True였다.
# (2026-09-10 실측: 유휴 상태에서도 ⏵⏵ 존재)
BUSY_MARKER = "esc to interrupt"


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def _ppid_of(pid: int) -> int | None:
    """주어진 PID의 부모 PID를 반환한다. 조회 실패 시 None."""
    r = subprocess.run(["ps", "-p", str(pid), "-o", "ppid="],
                       capture_output=True, text=True)
    out = r.stdout.strip()
    if r.returncode != 0 or not out.isdigit():
        return None
    return int(out)


def _owned_by_ccc_session(pid: int) -> bool:
    """이 PID의 조상 중에 운영봇 claude(--channels plugin:telegram)가 있는지 확인.

    운영봇 bun의 계보: bun server.ts → bun run(플러그인) → claude --channels ...
    반면 cokacdir가 띄우는 claude -p 세션도 플러그인을 로드해 bun을 만드는데,
    그 bun의 조상에는 '--channels'가 없고 '-p'가 있다. 이걸로 구분한다.
    """
    seen = 0
    cur: int | None = pid
    while cur and cur > 1 and seen < 10:   # 무한루프 방지
        r = subprocess.run(["ps", "-p", str(cur), "-o", "command="],
                           capture_output=True, text=True)
        cmd = r.stdout.strip()
        if "--channels" in cmd and "plugin:telegram" in cmd:
            return True
        cur = _ppid_of(cur)
        seen += 1
    return False


def bun_is_running() -> bool:
    """운영봇(ccc 세션)에 속한 bun이 살아있는지 확인한다.

    주의: 단순히 `pgrep -f "bun server.ts"`로 판단하면 안 된다.
    cokacdir가 실행하는 `claude -p` 세션도 텔레그램 플러그인을 로드하면서
    별도의 bun을 띄우기 때문에, 운영봇 bun이 죽어 있어도 남의 bun을 보고
    '살아있다'고 오판한다. (2026-07-28: 이 오판으로 약 10시간 동안 자동복구가
    발동하지 않아 운영봇 먹통이 방치됨)
    따라서 각 bun의 조상 계보를 확인해 운영봇 소속만 인정한다.
    """
    result = subprocess.run(["pgrep", "-f", "bun server.ts"],
                            capture_output=True, text=True)
    if result.returncode != 0:
        return False
    for line in result.stdout.split():
        if line.isdigit() and _owned_by_ccc_session(int(line)):
            return True
    return False


def claude_process_running() -> bool:
    """운영봇 claude(--channels) 프로세스가 실제로 떠 있는지 확인한다.

    bun이 죽었을 때 두 경우가 있다: (a) claude는 살아있는데 MCP(bun)만
    안 떴다, (b) claude 자체가 재기동 창에 있다(일일 재시작 직후 등).
    (b)에서 복구 키를 보내면 아무도 받지 못하고, 입력 큐에 쌓였다가
    새 claude가 뜬 뒤 엉뚱하게 소비된다. (2026-09-27 04:00:26 사례)
    판정 실패(pgrep 이상 등)는 False로 — 이때 0단계는 최대 60초만 기다리고
    본래 절차로 진행하므로, 오검출 비용은 유예 지연뿐이다.
    """
    r = subprocess.run(["pgrep", "-f", CLAUDE_PGREP],
                       capture_output=True, text=True)
    return r.returncode == 0


def capture_pane() -> str:
    """ccc tmux 세션의 현재 화면을 문자열로 읽는다. 실패하면 빈 문자열."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p"],
        capture_output=True, text=True
    )
    return result.stdout if result.returncode == 0 else ""


def claude_is_busy() -> bool:
    """ccc 세션의 claude가 지금 작업을 처리 중인지 확인한다.

    주의: "⏵⏵"로 판정하면 안 된다. ccc봇은 --dangerously-skip-permissions로
    떠 있어서 footer에 "⏵⏵ bypass permissions on"이 상시 표시된다.
    그래서 옛 판정은 놀고 있을 때도 항상 True를 냈고, 2026-09-10 09:08:23
    로그의 "claude 처리 중(⏵⏵)"도 그 오판이었다(실제로는 유휴).
    "esc to interrupt"는 실제로 실행 중일 때만 나온다.
    """
    return BUSY_MARKER in capture_pane()


def mcp_start_count() -> int:
    """래퍼 로그에 남은 '===== MCP 서버 시작' 줄 수. 읽기 실패 시 -1."""
    try:
        return MCP_LOG.read_text(errors="replace").count(MCP_START_MARK)
    except Exception as e:
        log(f"래퍼 로그 읽기 실패({e}) — 교차 확인 생략")
        return -1


def recovery_succeeded(before: int, stage: str) -> bool:
    """복구 성공 판정. bun_is_running()이 결정권을 갖고, 래퍼 로그로 교차 확인한다.

    래퍼 로그를 못 읽는 상황에서 bun이 멀쩡한데도 실패로 몰면
    쓸데없는 알림과 2단계 메뉴 조작이 발생한다. 그래서 로그는 '거부권'이 아니라
    '교차 확인'으로만 쓰고, 두 신호가 어긋나면 경고를 남긴다.
    """
    bun_ok = bun_is_running()
    after = mcp_start_count()
    if after < 0 or before < 0:
        log(f"{stage} 판정: bun={'있음' if bun_ok else '없음'} / 래퍼로그 확인불가")
        return bun_ok
    log(f"{stage} 판정: bun={'있음' if bun_ok else '없음'} / "
        f"'{MCP_START_MARK}' {before}줄 → {after}줄")
    if bun_ok and after == before:
        log("⚠️ 판정 불일치 — bun은 있는데 래퍼 로그에 새 시작 줄이 없다 "
            "(남의 bun이거나 로그 회전 가능성). bun 판정을 따른다")
    return bun_ok


def cursor_is_on(pane: str, needle: str) -> bool:
    """❯ 커서가 needle을 포함한 줄에 있는지 확인한다.

    입력 프롬프트 줄도 "❯ "로 시작하므로, 커서 문자만 보고 판단하면 안 된다.
    반드시 같은 줄에 needle이 함께 있어야 인정한다.
    """
    for line in pane.splitlines():
        if MCP_CURSOR in line and needle in line:
            return True
    return False


def send_keys(*keys: str) -> None:
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, *keys],
                   capture_output=True)


def move_cursor_to(needle: str) -> bool:
    """메뉴에서 ❯ 커서가 needle 줄에 올 때까지 Down을 누른다.

    화살표 횟수를 박지 않는다 — 커넥터가 붙었다 끊길 때마다 목록 길이가 바뀌기
    때문이다. 매번 화면을 다시 읽어 확인하고, MCP_MENU_MAX_STEPS를 넘으면
    포기한다(호출한 쪽에서 Escape로 빠져나온다).
    """
    for step in range(MCP_MENU_MAX_STEPS):
        pane = capture_pane()
        if cursor_is_on(pane, needle):
            log(f"커서가 '{needle}' 줄에 있음 (Down {step}회)")
            return True
        if needle not in pane:
            log(f"화면에 '{needle}' 자체가 없음 — 메뉴가 안 열렸을 수 있다")
            return False
        send_keys("Down")
        time.sleep(0.3)
    log(f"❌ Down {MCP_MENU_MAX_STEPS}회 안에 '{needle}' 줄에 못 갔다")
    return False


def try_mcp_reconnect() -> bool:
    """2단계: /mcp 메뉴에서 telegram MCP를 Reconnect 한다.

    Enter는 화면에서 대상 줄을 눈으로(capture-pane으로) 확인한 뒤에만 누른다.
    확인 못 하면 Escape로 빠져나오고 실패 처리한다 — 엉뚱한 항목(2번 Disable 등)을
    누르면 멀쩡한 MCP를 꺼버리기 때문이다.
    """
    if claude_is_busy():
        log("claude 작업 중 — /mcp 메뉴 조작은 작업을 망가뜨린다. 2단계 생략")
        return False

    before = mcp_start_count()

    send_keys("Escape")
    time.sleep(1)
    send_keys("C-u")
    time.sleep(0.5)

    log("2단계: /mcp 메뉴 열기")
    send_keys("-l", "/mcp")
    time.sleep(0.5)
    send_keys("Enter")
    time.sleep(2)

    if not move_cursor_to(MCP_TARGET_LINE):
        send_keys("Escape")
        log("❌ 2단계 실패 — 대상 서버 줄을 확인하지 못해 Escape로 빠져나옴")
        return False

    send_keys("Enter")
    time.sleep(1.5)

    if not move_cursor_to(MCP_ACTION_LINE):
        send_keys("Escape")
        time.sleep(0.3)
        send_keys("Escape")
        log("❌ 2단계 실패 — 'Reconnect' 항목을 확인하지 못해 Escape로 빠져나옴")
        return False

    log("'Reconnect' 선택 확인 — Enter")
    send_keys("Enter")

    log(f"bun 재기동 대기 중 ({MCP_RECONNECT_WAIT}초)...")
    time.sleep(MCP_RECONNECT_WAIT)
    return recovery_succeeded(before, "2단계")


def try_reload_plugins() -> bool:
    """1단계: tmux ccc 세션에 /reload-plugins를 전송한다."""
    before = mcp_start_count()

    if claude_is_busy():
        # 처리 중이면 Escape 생략 — Escape는 실행 중인 tool을 강제 중단시킴
        log("claude 작업 중 — Escape 생략, /reload-plugins만 큐에 적재")
    else:
        # 유휴 상태 또는 MCP 메뉴에 갇혀있을 수 있으므로 Escape로 초기화
        send_keys("Escape")
        time.sleep(1)

    # 입력줄에 남아있을 수 있는 이전 입력을 비운다
    send_keys("C-u")
    time.sleep(0.5)

    log(f"1단계: /reload-plugins → {TMUX_SESSION}")
    # 슬래시 명령은 반드시 '-l'(리터럴)로 보내야 한다
    send_keys("-l", "/reload-plugins")
    time.sleep(0.5)
    send_keys("Enter")

    log(f"bun 재기동 대기 중 ({RECOVERY_WAIT}초)...")
    time.sleep(RECOVERY_WAIT)
    return recovery_succeeded(before, "1단계")


def try_tmux_recovery() -> bool:
    """자동 복구. 0단계 claude 기동 확인 → 1단계 /reload-plugins → 2단계 /mcp Reconnect."""
    check = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    )
    if check.returncode != 0:
        log(f"tmux 세션 '{TMUX_SESSION}' 없음 — 수동 복구 필요")
        return False

    # 0단계-1: claude 프로세스가 뜰 때까지 기다린다. 부재 중 키 전송은 헛발이다.
    waited = 0
    if not claude_process_running():
        log(f"claude 프로세스 없음 — 래퍼 재기동 대기(최대 {CLAUDE_START_WAIT}초)")
    while not claude_process_running():
        if waited >= CLAUDE_START_WAIT:
            log(f"claude 미기동 {CLAUDE_START_WAIT}초 경과 — 본래 절차로 진행")
            break
        time.sleep(10)
        waited += 10

    # 0단계-2: claude가 살아있으면 bun이 스스로 뜰 유예를 준다. 방금 부팅한
    # claude에 키를 보내면 입력이 엉뚱하게 소비될 수 있다
    # (2026-09-27 04:11 사례: 기동 10분 시점 시도도 실패, 20분 시점에 성공).
    if claude_process_running():
        log(f"claude 기동 확인 — bun 자동 기동 유예(최대 {CLAUDE_BOOT_GRACE}초)")
        deadline = time.time() + CLAUDE_BOOT_GRACE
        while time.time() < deadline:
            if bun_is_running():
                log("bun 자동 기동 확인 — 복구 키 불필요")
                return True
            time.sleep(10)
        log("유예 내 bun 미기동 — 본래 복구 절차 진행")

    if try_reload_plugins():
        log("✅ 자동 복구 성공 (1단계 /reload-plugins)")
        return True

    log("1단계 실패 — 2단계로 넘어감")
    if try_mcp_reconnect():
        log("✅ 자동 복구 성공 (2단계 /mcp Reconnect)")
        return True

    log("❌ 자동 복구 실패 (1·2단계 모두) — 사용자 수동 개입 필요")
    return False


def send_alert(text: str) -> None:
    try:
        subprocess.run(
            [sys.executable, str(SEND_SCRIPT), text],
            capture_output=True, timeout=15
        )
        log(f"알림 발송: {text[:60]}")
    except Exception as e:
        log(f"알림 발송 실패: {e}")


def acquire_lock() -> bool:
    if PID_FILE.exists():
        try:
            existing_pid = int(PID_FILE.read_text().strip())
            os.kill(existing_pid, 0)
            log(f"이미 실행 중인 인스턴스 있음 (PID {existing_pid}), 종료")
            return False
        except (ProcessLookupError, ValueError):
            PID_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    try:
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
    except Exception:
        pass


def main() -> None:
    if not acquire_lock():
        return

    import atexit
    atexit.register(release_lock)

    log("=== CCC봇 감시 시작 ===")

    bun_was_running = bun_is_running()
    log(f"초기 bun 상태: {'실행 중' if bun_was_running else '미실행'}")
    last_alert_ts: float = 0.0

    # 시작 시 이미 bun이 죽어있으면 자동 복구 시도
    if not bun_was_running:
        log("⚠️ 시작 시 bun 미실행 — 자동 복구 시도")
        if try_tmux_recovery():
            bun_was_running = True
        else:
            send_alert(
                "🔴 CCC봇이 꺼졌습니다.\n"
                "자동 복구를 두 가지 다 해봤는데 실패했어요.\n"
                "(1단계 /reload-plugins · 2단계 /mcp Reconnect)\n\n"
                "💬 지금 보내시는 메시지는 Telegram이 보관 중이에요.\n"
                "봇이 살아나면 자동으로 전달됩니다!\n\n"
                "🔧 남은 방법은 세션 재시작이에요 (1~2분)\n\n"
                "1️⃣ Mac에서 Terminal 앱을 여세요\n"
                "   화면 오른쪽 상단 돋보기 🔍 → 'Terminal' 검색 → Enter\n\n"
                "2️⃣ Terminal 창에 아래를 붙여넣고 Enter:\n"
                "   tmux attach -t ccc\n\n"
                "3️⃣ 화면이 바뀌면 아래를 입력하고 Enter:\n"
                "   /exit\n\n"
                "4️⃣ 30초 뒤 래퍼가 알아서 다시 띄웁니다.\n"
                "   1~2분 기다리면 봇이 살아납니다 ✅\n\n"
                "⚠️ /reload-plugins 와 /mcp Reconnect 는 이미 실패했으니\n"
                "   다시 시도하지 마세요."
            )
            last_alert_ts = time.time()

    while True:
        currently_running = bun_is_running()

        # bun 살아있음 → 대기
        if currently_running:
            if not bun_was_running:
                log("✅ bun 복구 감지 — 대기 모드로 전환")
                bun_was_running = True
            time.sleep(STANDBY_INTERVAL)
            continue

        # bun이 방금 죽은 경우 → 자동 복구 시도
        now = time.time()
        if bun_was_running:
            log("⚠️ bun 미실행 감지 — 자동 복구 시도")
            bun_was_running = False
            if try_tmux_recovery():
                bun_was_running = True
                continue
            log("자동 복구 실패 — 알림 발송 후 대기")
            send_alert(
                "🔴 CCC봇이 꺼졌습니다.\n"
                "자동 복구를 두 가지 다 해봤는데 실패했어요.\n"
                "(1단계 /reload-plugins · 2단계 /mcp Reconnect)\n\n"
                "💬 지금 보내시는 메시지는 Telegram이 보관 중이에요.\n"
                "봇이 살아나면 자동으로 전달됩니다!\n\n"
                "🔧 남은 방법은 세션 재시작이에요 (1~2분)\n\n"
                "1️⃣ Mac에서 Terminal 앱을 여세요\n"
                "   화면 오른쪽 상단 돋보기 🔍 → 'Terminal' 검색 → Enter\n\n"
                "2️⃣ Terminal 창에 아래를 붙여넣고 Enter:\n"
                "   tmux attach -t ccc\n\n"
                "3️⃣ 화면이 바뀌면 아래를 입력하고 Enter:\n"
                "   /exit\n\n"
                "4️⃣ 30초 뒤 래퍼가 알아서 다시 띄웁니다.\n"
                "   1~2분 기다리면 봇이 살아납니다 ✅\n\n"
                "⚠️ /reload-plugins 와 /mcp Reconnect 는 이미 실패했으니\n"
                "   다시 시도하지 마세요."
            )
            last_alert_ts = time.time()

        elif now - last_alert_ts >= ALERT_COOLDOWN:
            # 장시간 복구 안 됨 → 재복구 시도 + 재알림
            log(f"⚠️ bun 계속 미실행 ({int((now - last_alert_ts) / 60)}분째) — 재복구 시도")
            if try_tmux_recovery():
                bun_was_running = True
                continue
            send_alert(
                "⏰ CCC봇이 아직 꺼져 있어요.\n"
                "자동 복구를 10분마다 계속 시도했지만 안 되고 있어요.\n\n"
                "직접 세션을 재시작해 주세요:\n\n"
                "1️⃣ Terminal에 아래를 붙여넣고 Enter:\n"
                "   tmux attach -t ccc\n\n"
                "2️⃣ 이어서 아래를 입력하고 Enter:\n"
                "   /exit\n\n"
                "3️⃣ 30초 뒤 자동으로 다시 뜹니다.\n\n"
                "봇이 살아나면 그동안 보낸 메시지도 받아요 ✅"
            )
            last_alert_ts = now

        # bun 없는 동안 직접 폴링 안 함 — 409 Conflict로 bun 죽이는 원인
        time.sleep(STANDBY_INTERVAL)


if __name__ == "__main__":
    main()
