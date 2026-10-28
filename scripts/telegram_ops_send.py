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

# 2026-10-27 사용자 결정: 이 봇의 모든 메시지 첫머리에 어느 프로젝트 메시지인지 적는다.
# 토픽 번호로 고르고, 모르는 곳은 라이프메모리(이 스크립트의 주인)로 본다.
DEFAULT_PROJECT = "라이프메모리"
THREAD_PROJECTS = {"8461": "CCC 봇 운영"}


def labeled(text: str, project: str) -> str:
    tag = f"[{project}]"
    return text if text.startswith(tag) else f"{tag} {text}"


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


def send_message(text: str, chat_id: str | None = None, thread_id: str | None = None,
                 project: str | None = None) -> dict:
    text = labeled(text, project or THREAD_PROJECTS.get(str(thread_id or ""), DEFAULT_PROJECT))
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


def ops_thread_id() -> str | None:
    """밤 작업 알림을 보낼 토픽(memory-config.json telegram.opsThreadId). 없으면 기본(전체) 창."""
    try:
        cfg = json.loads((ROOT / "memory-config.json").read_text(encoding="utf-8"))
        value = cfg.get("telegram", {}).get("opsThreadId")
        return str(value) if value else None
    except (OSError, ValueError):
        return None


def send_ops_alert(text: str, project: str | None = None) -> dict:
    """밤 작업 알림용. thread 없이 보내면 '모두' 창으로 가서(2026-10-19 확인) 운영 토픽으로 보낸다."""
    return send_message(text, thread_id=ops_thread_id(), project=project)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("text", help="보낼 메시지")
    parser.add_argument("--chat-id", default=None)
    parser.add_argument("--thread-id", default=None, help="텔레그램 포럼 토픽 ID")
    parser.add_argument("--project", default=None, help="메시지 첫머리 [프로젝트] 표시 (기본: 토픽으로 고름)")
    args = parser.parse_args()

    try:
        result = send_message(args.text, args.chat_id, args.thread_id, args.project)
        print("전송 완료")
    except Exception as e:
        print(f"전송 실패: {e}", file=sys.stderr)
        sys.exit(1)
