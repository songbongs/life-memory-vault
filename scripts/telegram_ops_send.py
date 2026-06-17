#!/usr/bin/env python3
"""텔레그램 직접 API 발신 스크립트 — MCP 없이 메시지를 보냄.

사용법:
  python3 telegram_ops_send.py "보낼 메시지" --chat-id 466137686
  python3 telegram_ops_send.py "메시지" --chat-id 466137686 --thread-id 123
"""

from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CURL = "/usr/bin/curl"


def load_token() -> str:
    env_file = Path.home() / ".claude" / "channels" / "telegram" / ".env"
    for line in env_file.read_text().splitlines():
        if line.startswith("TELEGRAM_BOT_TOKEN="):
            return line.split("=", 1)[1].strip()
    raise RuntimeError(f"TELEGRAM_BOT_TOKEN not found in {env_file}")


def load_default_chat_id() -> str:
    access_file = Path.home() / ".claude" / "channels" / "telegram" / "access.json"
    data = json.loads(access_file.read_text())
    allowed = data.get("allowFrom", [])
    if not allowed:
        raise RuntimeError("allowFrom 목록이 비어있습니다")
    return str(allowed[0])


def send_message(text: str, chat_id: str | None = None, thread_id: str | None = None) -> dict:
    token = load_token()
    if chat_id is None:
        chat_id = load_default_chat_id()

    body: dict = {"chat_id": chat_id, "text": text}
    if thread_id:
        body["message_thread_id"] = int(thread_id)

    cmd = [
        CURL, "-s", "--http1.1", "--max-time", "15",
        "-X", "POST",
        f"https://api.telegram.org/bot{token}/sendMessage",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(body, ensure_ascii=False),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=20)
    if result.returncode != 0:
        raise RuntimeError(f"curl 실패 (코드 {result.returncode}): {result.stderr}")

    data = json.loads(result.stdout)
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API 오류: {data}")
    return data


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="보낼 메시지")
    parser.add_argument("--chat-id", default=None)
    parser.add_argument("--thread-id", default=None, help="텔레그램 포럼 토픽 ID")
    args = parser.parse_args()

    try:
        result = send_message(args.text, args.chat_id, args.thread_id)
        print("전송 완료")
    except Exception as e:
        print(f"전송 실패: {e}", file=sys.stderr)
        sys.exit(1)
