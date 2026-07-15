#!/usr/bin/env python3
"""텔레그램 CCC봇 감시 프로세스.

bun(MCP 서버)이 살아있는지 주기적으로 확인하고,
죽으면 tmux 자동 복구를 시도하고 실패 시 텔레그램 알림 발송.

직접 폴링(getUpdates)은 하지 않는다 — bun과의 409 Conflict로
bun이 스스로 종료하는 원인이 되기 때문.
Telegram 서버는 메시지를 24시간 보관하므로 bun 복구 후 자동 전달된다.

- bun 살아있음: 30초마다 확인 후 대기
- bun 죽음:
    1. tmux ccc 세션에 /reload-plugins 자동 전송
    2. 90초 대기 후 bun 복구 확인 (LLM 처리 포함 최대 70초 소요)
    3. 복구 성공: 무음 처리
    4. 복구 실패: 사용자 알림 발송 + 10분마다 재시도/재알림
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
RECOVERY_WAIT = 90      # /reload-plugins 전송 후 bun 재기동 대기 시간(초)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def bun_is_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "bun server.ts"], capture_output=True)
    return result.returncode == 0


def claude_is_busy() -> bool:
    """ccc tmux 세션에서 claude가 현재 작업 처리 중(⏵⏵)인지 확인한다."""
    result = subprocess.run(
        ["tmux", "capture-pane", "-t", TMUX_SESSION, "-p"],
        capture_output=True, text=True
    )
    return "⏵⏵" in result.stdout


def try_tmux_recovery() -> bool:
    """tmux ccc 세션에 /reload-plugins를 전송해 자동 복구를 시도한다."""
    check = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    )
    if check.returncode != 0:
        log(f"tmux 세션 '{TMUX_SESSION}' 없음 — 수동 복구 필요")
        return False

    if claude_is_busy():
        # 처리 중이면 Escape 생략 — Escape는 실행 중인 tool을 강제 중단시킴
        log("claude 처리 중(⏵⏵) — Escape 생략, /reload-plugins만 큐에 적재")
    else:
        # 유휴 상태 또는 MCP 메뉴에 갇혀있을 수 있으므로 Escape로 초기화
        subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Escape"], capture_output=True)
        time.sleep(1)

    # 입력줄에 남아있을 수 있는 이전 입력을 비운다
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "C-u"], capture_output=True)
    time.sleep(0.5)

    log(f"자동 복구 시도: /reload-plugins → {TMUX_SESSION}")
    # 슬래시 명령은 반드시 '-l'(리터럴)로 보내야 한다
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "-l", "/reload-plugins"], capture_output=True)
    time.sleep(0.5)
    subprocess.run(["tmux", "send-keys", "-t", TMUX_SESSION, "Enter"], capture_output=True)

    log(f"bun 재기동 대기 중 ({RECOVERY_WAIT}초)...")
    time.sleep(RECOVERY_WAIT)

    if bun_is_running():
        log("✅ 자동 복구 성공")
        return True
    else:
        log("❌ 자동 복구 실패 — 사용자 수동 개입 필요")
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
                "자동으로 살리려 했는데 실패했어요.\n\n"
                "💬 지금 보내시는 메시지는 Telegram이 보관 중이에요.\n"
                "봇이 살아나면 자동으로 전달됩니다!\n\n"
                "🔧 직접 복구 방법 (1~2분이면 돼요)\n\n"
                "1️⃣ Mac에서 Terminal 앱을 여세요\n"
                "   화면 오른쪽 상단 돋보기 🔍 → 'Terminal' 검색 → Enter\n\n"
                "2️⃣ Terminal 창에 아래를 붙여넣고 Enter:\n"
                "   tmux attach -t ccc\n\n"
                "3️⃣ 화면이 바뀌면 아래를 입력하고 Enter:\n"
                "   /reload-plugins\n\n"
                "4️⃣ 30초 기다리면 봇이 살아납니다 ✅"
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
                "자동으로 살리려 했는데 실패했어요.\n\n"
                "💬 지금 보내시는 메시지는 Telegram이 보관 중이에요.\n"
                "봇이 살아나면 자동으로 전달됩니다!\n\n"
                "🔧 직접 복구 방법 (1~2분이면 돼요)\n\n"
                "1️⃣ Mac에서 Terminal 앱을 여세요\n"
                "   화면 오른쪽 상단 돋보기 🔍 → 'Terminal' 검색 → Enter\n\n"
                "2️⃣ Terminal 창에 아래를 붙여넣고 Enter:\n"
                "   tmux attach -t ccc\n\n"
                "3️⃣ 화면이 바뀌면 아래를 입력하고 Enter:\n"
                "   /reload-plugins\n\n"
                "4️⃣ 30초 기다리면 봇이 살아납니다 ✅"
            )
            last_alert_ts = time.time()

        elif now - last_alert_ts >= ALERT_COOLDOWN:
            # 장시간 복구 안 됨 → 재복구 시도 + 재알림
            log(f"⚠️ bun 계속 미실행 ({int((now - last_alert_ts) / 60)}분째) — 재복구 시도")
            if try_tmux_recovery():
                bun_was_running = True
                continue
            send_alert(
                "⏰ CCC봇이 아직 꺼져 있어요.\n\n"
                "아직 복구가 안 됐다면:\n\n"
                "1️⃣ Terminal에 아래를 붙여넣고 Enter:\n"
                "   tmux attach -t ccc\n\n"
                "2️⃣ 이어서 아래를 입력하고 Enter:\n"
                "   /reload-plugins\n\n"
                "봇이 살아나면 그동안 보낸 메시지도 받아요 ✅"
            )
            last_alert_ts = now

        # bun 없는 동안 직접 폴링 안 함 — 409 Conflict로 bun 죽이는 원인
        time.sleep(STANDBY_INTERVAL)


if __name__ == "__main__":
    main()
