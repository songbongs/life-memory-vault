#!/usr/bin/env python3
"""Tests for normalize_dates — date enrichment to YY.MM.DD (capture-relative).

Runs without pytest:  python3 tests/test_dates.py
"""

import datetime as dt
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402

REF = dt.date(2026, 6, 11)  # capture date


def nd(text, ref=REF):
    return mem.normalize_dates(text, ref)


def test_slash_md_gets_current_year():
    assert nd("1) 6/11(목) 타운홀 2) 6/16(화) 점심") == ["26.06.11", "26.06.16"]


def test_korean_md_gets_current_year():
    assert nd("3월 2일 회의") == ["26.03.02"]


def test_day_only_gets_capture_year_and_month():
    assert nd("16일에 보자") == ["26.06.16"]


def test_md_and_day_only_no_double_count():
    # "6월 16일" must be 06.16 (not ref-month), and not also produce a day-only dup
    assert nd("6월 16일 약속") == ["26.06.16"]


def test_relative_day_words():
    assert nd("내일 미팅") == ["26.06.12"]
    assert nd("어제 한 일") == ["26.06.10"]
    assert nd("오늘 메모") == ["26.06.11"]


def test_relative_month_plus_day():
    assert nd("다음달 5일 결제") == ["26.07.05"]
    assert nd("지난달 30일 송금") == ["26.05.30"]


def test_relative_month_year_boundary():
    assert mem.normalize_dates("지난달 3일", dt.date(2026, 1, 10)) == ["25.12.03"]


def test_relative_year_plus_md():
    assert nd("작년 3월 2일") == ["25.03.02"]
    assert nd("내년 1월 1일 목표") == ["27.01.01"]


def test_no_false_positive_on_durations():
    assert nd("3일간 여행했다") == []        # 간 -> not a date
    assert nd("프로젝트 2일째 진행") == []     # 째 -> not a date


def test_no_dates_returns_empty():
    assert nd("그냥 일상 메모, 날짜 없음") == []


def test_invalid_md_ignored():
    assert nd("13월 40일") == []             # out of range
    assert "26.99" not in " ".join(nd("화면 99/99"))


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
