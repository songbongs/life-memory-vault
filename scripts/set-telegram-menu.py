#!/usr/bin/env python3
"""One-shot: register the CAPTURE bot's command menu via Telegram setMyCommands.

Target: the capture bot (@my_lifelog_memory_bot) that telegram_collector.py polls.
The ops bot (@songbongs_CCC_bot) is managed by Claude Code channels — do NOT touch it.

Telegram only allows command NAMES matching ^[a-z0-9_]{1,32}$, so the menu lists
the English commands with Korean descriptions. Korean aliases (/정리 등) still work
when typed directly; they just cannot appear in the tap-to-select menu.

Token comes from TELEGRAM_BOT_TOKEN env or memory-config.json (never hardcode).

Usage:
    python3 scripts/set-telegram-menu.py            # preview only (no change)
    python3 scripts/set-telegram-menu.py --apply    # actually register the menu
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import telegram_collector as tc  # noqa: E402  (reuse load_dotenv/load_config/token_from/api_json)


MENU = [
    {"command": "seek", "description": "즉시 검색 (예: /seek 어제 식당)"},
    {"command": "status", "description": "봇 상태 (즉시)"},
    {"command": "digest", "description": "통계 (~5분)"},
    {"command": "doctor", "description": "점검 (~5분)"},
    {"command": "lint", "description": "메모 정리 (23시 배치)"},
    {"command": "repair", "description": "수리 (23시 배치)"},
    {"command": "enrich", "description": "저장한 링크 한국어 요약 (23시 배치)"},
    {"command": "help", "description": "도움말 (한국어 명령·처리시점 안내)"},
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default=str(tc.DEFAULT_CONFIG))
    parser.add_argument("--apply", action="store_true", help="Actually call setMyCommands (omit = preview only)")
    args = parser.parse_args()

    tc.load_dotenv()
    config = tc.load_config(Path(args.config).expanduser())
    token = tc.token_from(config)
    if not token:
        raise SystemExit("Missing Telegram bot token. Set TELEGRAM_BOT_TOKEN or telegram.botToken in memory-config.json.")

    print("등록 대상 메뉴 (캡처 봇):")
    for item in MENU:
        print(f"  /{item['command']:8} {item['description']}")

    if not args.apply:
        print("\n(미리보기) 실제 등록하려면 --apply 를 붙여 다시 실행하세요.")
        return 0

    tc.api_json(token, "setMyCommands", {"commands": json.dumps(MENU, ensure_ascii=False)}, timeout=15)
    print("\n✓ setMyCommands 등록 완료 — 텔레그램 입력창의 메뉴(/) 버튼에서 확인하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
