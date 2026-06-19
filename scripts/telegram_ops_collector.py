#!/usr/bin/env python3
"""텔레그램 CCC봇 대기열 수신기.

bun(MCP 서버)이 살아있으면 대기, 죽으면 tmux 자동 복구를 시도하고
실패 시 폴링을 인수해서 메시지를 대기열 파일에 저장하고 텔레그램 알림 발송.

- bun 살아있음: 30초마다 확인 후 대기 (충돌 없음)
- bun 죽음:
    1. tmux ccc 세션에 /reload-plugins 자동 전송
    2. 20초 대기 후 bun 복구 확인
    3. 복구 성공: 무음 처리 (사용자 알림 없음)
    4. 복구 실패: 폴링 시작 + 알림 발송 + 메시지 큐 저장
- bun 복구: 폴링 중단, 대기 모드로 복귀
- 409 충돌 감지 시: pgrep으로 bun 실제 실행 여부 재확인 후 판단
  (pgrep OK → bun 복구로 처리, pgrep 실패 → 잔여 연결 타임아웃 대기)
"""

from __future__ import annotations
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
QUEUE_FILE = ROOT / "scripts" / ".telegram-ops-queue.jsonl"
SEND_SCRIPT = ROOT / "scripts" / "telegram_ops_send.py"
LOG_FILE = Path("/tmp/telegram-ops-collector.log")
OFFSET_FILE = ROOT / "scripts" / ".telegram-ops-offset"
PID_FILE = Path("/tmp/telegram-ops-collector.pid")

POLL_TIMEOUT = 30       # Telegram long-poll 대기 시간(초)
ERROR_SLEEP = 5         # 일반 오류 재시도 간격(초)
STANDBY_INTERVAL = 30   # bun 살아있을 때 재확인 주기(초)
ALERT_COOLDOWN = 600    # 동일 이벤트 재알림 최소 간격(초, 10분)
# 409 후 잔여 롱폴 연결이 타임아웃될 때까지 대기.
# Telegram의 롱폴 타임아웃(POLL_TIMEOUT)보다 조금 길게 설정.
STALE_CONN_WAIT = POLL_TIMEOUT + 5

TMUX_SESSION = "ccc"    # CCC가 실행되는 tmux 세션 이름
RECOVERY_WAIT = 20      # /reload-plugins 전송 후 bun 재기동 대기 시간(초)


def log(msg: str) -> None:
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{ts}] {msg}", flush=True)


def load_token() -> str:
    env_file = Path.home() / ".claude" / "channels" / "telegram" / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError("TELEGRAM_BOT_TOKEN not found")


def load_allowed() -> set[str]:
    access_file = Path.home() / ".claude" / "channels" / "telegram" / "access.json"
    data = json.loads(access_file.read_text())
    return {str(uid) for uid in data.get("allowFrom", [])}


def bun_is_running() -> bool:
    result = subprocess.run(["pgrep", "-f", "bun server.ts"], capture_output=True)
    return result.returncode == 0


def try_tmux_recovery() -> bool:
    """tmux ccc 세션에 /reload-plugins를 전송해 자동 복구를 시도한다."""
    check = subprocess.run(
        ["tmux", "has-session", "-t", TMUX_SESSION],
        capture_output=True
    )
    if check.returncode != 0:
        log(f"tmux 세션 '{TMUX_SESSION}' 없음 — 수동 복구 필요")
        return False

    log(f"자동 복구 시도: tmux send-keys -t {TMUX_SESSION} /reload-plugins")
    subprocess.run(
        ["tmux", "send-keys", "-t", TMUX_SESSION, "/reload-plugins", "Enter"],
        capture_output=True
    )

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


def get_updates(token: str, offset: int) -> list[dict]:
    url = (
        f"https://api.telegram.org/bot{token}/getUpdates"
        f"?offset={offset}&timeout={POLL_TIMEOUT}&allowed_updates=[\"message\"]"
    )
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=POLL_TIMEOUT + 10) as resp:
        data = json.loads(resp.read())
    if not data.get("ok"):
        raise RuntimeError(f"getUpdates 실패: {data}")
    return data.get("result", [])


def enqueue(message: dict) -> None:
    text = (
        message.get("text")
        or message.get("caption")
        or (message.get("sticker") and message["sticker"].get("emoji"))
        or "[미디어 메시지]"
    )
    entry = {
        "ts": datetime.now().isoformat(),
        "from_id": str(message.get("from", {}).get("id", "")),
        "from_name": message.get("from", {}).get("first_name", ""),
        "chat_id": str(message.get("chat", {}).get("id", "")),
        "thread_id": str(message["message_thread_id"]) if message.get("message_thread_id") else None,
        "text": text,
        "message_id": message.get("message_id"),
        "processed": False,
    }
    with QUEUE_FILE.open("a") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    log(f"대기열 저장: [{entry['from_name']}] {entry['text'][:50]}")


def load_offset() -> int:
    try:
        return int(OFFSET_FILE.read_text().strip())
    except Exception:
        return 0


def save_offset(offset: int) -> None:
    OFFSET_FILE.write_text(str(offset))


def acquire_lock() -> bool:
    if PID_FILE.exists():
        try:
            existing_pid = int(PID_FILE.read_text().strip())
            os.kill(existing_pid, 0)
            log(f"이미 실행 중인 인스턴스 있음 (PID {existing_pid}), 종료")
            return False
        except (ProcessLookupError, ValueError):
            # 죽은 PID의 잔여 파일 제거
            PID_FILE.unlink(missing_ok=True)
    PID_FILE.write_text(str(os.getpid()))
    return True


def release_lock() -> None:
    try:
        # 자신의 PID 파일만 제거 (다른 인스턴스 파일 건드리지 않음)
        if PID_FILE.exists() and PID_FILE.read_text().strip() == str(os.getpid()):
            PID_FILE.unlink()
    except Exception:
        pass


def main() -> None:
    if not acquire_lock():
        return

    import atexit
    atexit.register(release_lock)

    log("=== 텔레그램 대기열 수신기 시작 ===")
    token = load_token()
    allowed = load_allowed()
    log(f"허용된 사용자: {allowed}")

    offset = load_offset()
    log(f"시작 offset: {offset}")

    bun_was_running = bun_is_running()
    log(f"초기 bun 상태: {'실행 중' if bun_was_running else '미실행'}")
    consecutive_errors = 0
    last_alert_ts: float = 0.0  # 마지막 알림 발송 시각 (쿨다운용)

    # 시작 시 이미 bun이 죽어있으면 자동 복구 시도
    if not bun_was_running:
        log("⚠️ 시작 시 bun 미실행 — 자동 복구 시도")
        if try_tmux_recovery():
            bun_was_running = True
        else:
            send_alert(
                "⚠️ CCC봇이 꺼져 있습니다.\n"
                "자동 복구를 시도했지만 실패했습니다.\n\n"
                "복구 방법:\n"
                "1. Terminal: tmux attach -t ccc\n"
                "2. /reload-plugins 입력"
            )
            last_alert_ts = time.time()

    while True:
        currently_running = bun_is_running()

        # bun 살아있음 → 대기 모드
        if currently_running:
            if not bun_was_running:
                log("✅ bun 복구 감지 — 대기 모드로 전환")
                bun_was_running = True
                consecutive_errors = 0
            time.sleep(STANDBY_INTERVAL)
            continue

        # bun이 방금 죽은 경우 → tmux 자동 복구 시도, 실패 시 알림
        now = time.time()
        if bun_was_running:
            log("⚠️ bun 미실행 감지 — 자동 복구 시도")
            bun_was_running = False
            if try_tmux_recovery():
                bun_was_running = True
                consecutive_errors = 0
                continue  # standby 모드로 자연 전환
            # 자동 복구 실패 → 폴링 인수 + 사용자 알림
            log("자동 복구 실패 — 폴링 인수, 알림 발송")
            send_alert(
                "⚠️ CCC봇이 꺼졌습니다.\n"
                "자동 복구를 시도했지만 실패했습니다.\n\n"
                "복구 방법:\n"
                "1. Terminal: tmux attach -t ccc\n"
                "2. /reload-plugins 입력"
            )
            last_alert_ts = time.time()
        elif now - last_alert_ts >= ALERT_COOLDOWN:
            # 장시간 복구 안 됨 → 쿨다운 지나면 재알림 (최대 1회/10분)
            log(f"⚠️ bun 계속 미실행 ({int((now - last_alert_ts) / 60)}분째) — 재알림 발송")
            send_alert(
                "⚠️ CCC봇이 아직 꺼져 있습니다.\n"
                "메시지는 대기열에 저장 중입니다.\n\n"
                "복구 방법:\n"
                "1. Terminal: tmux attach -t ccc\n"
                "2. /reload-plugins 입력"
            )
            last_alert_ts = now

        # bun 없음 → 직접 폴링, 큐에 저장
        try:
            updates = get_updates(token, offset)
            consecutive_errors = 0

            for update in updates:
                new_offset = update["update_id"] + 1
                message = update.get("message", {})

                if not message:
                    offset = new_offset
                    save_offset(offset)
                    continue

                from_id = str(message.get("from", {}).get("id", ""))
                if from_id not in allowed:
                    log(f"허용되지 않은 사용자 무시: {from_id}")
                    offset = new_offset
                    save_offset(offset)
                    continue

                enqueue(message)
                offset = new_offset
                save_offset(offset)

        except urllib.error.HTTPError as e:
            if e.code == 409:
                # 409 = 다른 getUpdates가 이미 실행 중.
                # pgrep으로 bun 실제 실행 여부를 재확인한 뒤 판단.
                if bun_is_running():
                    # bun이 실제로 살아났음 → 대기 모드로 전환
                    log("409 충돌 + pgrep 확인 → bun 복구됨, 대기 모드로 전환")
                    bun_was_running = True
                    consecutive_errors = 0
                    time.sleep(STANDBY_INTERVAL)
                else:
                    # bun은 없지만 409 → 이전 롱폴 연결이 아직 살아있음.
                    # 잔여 연결이 타임아웃될 때까지 대기 후 재시도.
                    log(f"409 충돌 but bun 미실행 — 잔여 연결 타임아웃 대기 ({STALE_CONN_WAIT}초)")
                    time.sleep(STALE_CONN_WAIT)
            else:
                consecutive_errors += 1
                log(f"HTTP 오류 {e.code} ({consecutive_errors}회): {e}")
                time.sleep(ERROR_SLEEP * min(consecutive_errors, 6))
        except urllib.error.URLError as e:
            consecutive_errors += 1
            log(f"네트워크 오류 ({consecutive_errors}회): {e}")
            time.sleep(ERROR_SLEEP * min(consecutive_errors, 6))
        except Exception as e:
            consecutive_errors += 1
            log(f"예외 ({consecutive_errors}회): {e}")
            time.sleep(ERROR_SLEEP)


if __name__ == "__main__":
    main()
