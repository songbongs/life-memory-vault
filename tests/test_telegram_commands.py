#!/usr/bin/env python3
"""Tests for Telegram command parsing — Korean aliases, /help, capture-bot contract.

No network, no real vault. Runs without pytest:  python3 tests/test_telegram_commands.py
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import telegram_collector as tc  # noqa: E402
import jobs  # noqa: E402


def test_korean_aliases_map_to_job_types():
    cases = {
        "/정리": "lint", "/점검": "doctor", "/수리": "repair",
        "/검색": "seek", "/찾기": "seek",
        "/통계": "digest", "/다이제스트": "digest",
        "/상태": "status", "/도움": "help", "/도움말": "help",
    }
    for text, expected in cases.items():
        got = tc.parse_telegram_command(text)
        assert got is not None, f"{text} returned None"
        assert got[0] == expected, f"{text} -> {got[0]}, expected {expected}"


def test_english_commands_still_work():
    for cmd in ["lint", "doctor", "repair", "seek", "digest", "status", "help"]:
        got = tc.parse_telegram_command(f"/{cmd}")
        assert got is not None and got[0] == ("help" if cmd == "help" else cmd), (cmd, got)


def test_korean_command_with_argument():
    got = tc.parse_telegram_command("/검색 어제 식당")
    assert got == ("seek", "어제 식당"), got


def test_help_takes_no_argument():
    got = tc.parse_telegram_command("/도움")
    assert got == ("help", ""), got


def test_unregistered_slash_is_none():
    # /요약 is reserved for enrich (/웹요약) in A2 — must NOT map to anything yet.
    assert tc.parse_telegram_command("/요약") is None
    assert tc.parse_telegram_command("/웹요약") is None
    assert tc.parse_telegram_command("/없는명령") is None


def test_plain_message_is_not_a_command():
    # The capture-bot contract: a normal memo must fall through to capture.
    assert tc.parse_telegram_command("오늘 좋은 카페 발견 https://x.com") is None
    assert tc.parse_telegram_command("정리 좀 해야겠다") is None  # no leading slash


def test_multiline_command_keeps_extra_lines():
    got = tc.parse_telegram_command("/검색 첫째줄\n둘째줄\n셋째줄")
    assert got is not None and got[0] == "seek"
    assert got[1] == "첫째줄\n둘째줄\n셋째줄", got[1]


def test_command_with_bot_suffix():
    got = tc.parse_telegram_command("/검색@my_lifelog_memory_bot 키워드")
    assert got == ("seek", "키워드"), got


def test_help_is_not_a_job_type():
    # help must never reach jobs.py (it is replied immediately, not queued).
    assert "help" not in jobs.VALID_TYPES


def test_help_text_covers_two_bot_topology_and_timing():
    assert "@songbongs_CCC_bot" in tc.HELP_TEXT      # ops bot referenced
    assert "캡처 봇" in tc.HELP_TEXT                  # capture bot named
    assert "23" in tc.HELP_TEXT                       # per-command timing shown
    assert "저장" in tc.HELP_TEXT                     # capture-default explained


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
