#!/usr/bin/env python3
"""Regression tests for mem.classify (P1: song over-classification fix).

Runs without pytest:  python3 tests/test_classify.py
Also discoverable by:  python3 -m pytest tests/
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import mem  # noqa: E402


def c(text, **meta):
    return mem.classify(text, meta)


# --- 핵심 회귀: " - " 단독 패턴이 더 이상 song이 아니어야 한다 ---

def test_dash_with_appointment_keyword_is_not_song():
    r = c("엄마 - 병원 예약 잡기")
    assert r["memory_type"] == "appointment", r


def test_dash_without_music_signal_is_not_song():
    r = c("회의 - 3시로 변경")
    assert r["memory_type"] != "song", r


def test_plain_dash_falls_back_to_journal():
    r = c("프로젝트 A - 내부 검토 메모")
    assert r["memory_type"] == "journal", r


# --- 음악은 명시 신호가 있을 때만 song/playlist ---

def test_dash_with_music_url_is_song():
    r = c("IU - 밤편지 https://music.youtube.com/watch?v=abc")
    assert r["memory_type"] == "song", r
    assert r["confidence"] == "medium", r


def test_music_keyword_only_is_low_confidence_song():
    r = c("좋아하는 노래 하나 떠올림 #음악")
    assert r["memory_type"] == "song", r
    assert r["confidence"] == "low", r


def test_playlist_keyword_is_playlist():
    r = c("드라이브용 플레이리스트 https://music.youtube.com/playlist?list=xyz")
    assert r["memory_type"] == "playlist", r


# --- 기존 분류 회귀 방지 ---

def test_maintenance_still_works():
    assert c("차량 와이퍼 오늘 교체")["memory_type"] == "maintenance"


def test_purchase_still_works():
    assert c("세제 15000원 구매")["memory_type"] == "purchase"


def test_task_still_works():
    assert c("내일 보고서 제출 해야 함")["memory_type"] == "task"


def test_food_still_works():
    assert c("성수동 새로 생긴 카페 가봄")["memory_type"] == "food_drink"


def test_media_raw_type_needs_review():
    r = c("스캔한 영수증", raw_type="raw_image")
    assert r["needs_review"] is True
    assert r["confidence"] == "low"


def test_album_purchase_prefers_purchase_over_song():
    # "앨범"은 음악 신호지만, 구매 키워드가 우선이라 purchase로 가야 한다.
    assert c("좋아하는 앨범 30000원 주고 샀다")["memory_type"] == "purchase"


# --- ③d-2: learned-rule pre-pass (additive) ---

def test_no_rules_arg_is_unchanged():
    # 명시적으로 rules 없이 호출하면 기존과 동일 (P1 회귀 보호의 핵심)
    assert mem.classify("회의 - 3시로 변경", {})["memory_type"] != "song"


def test_empty_rules_list_is_unchanged():
    assert mem.classify("그냥 일상 메모", {}, [])["memory_type"] == "journal"


def test_learned_rule_promotes_classification():
    rules = [{"signal": "샤워헤드", "type": "maintenance", "folder": "20_Records/Maintenance"}]
    r = mem.classify("욕실 샤워헤드 점검함", {}, rules)
    assert r["memory_type"] == "maintenance"
    assert r["confidence"] == "high" and r["needs_review"] is False


def test_learned_rule_folder_fallback_by_type():
    # folder 비어도 타입으로 폴더 유추
    rules = [{"signal": "샤워헤드", "type": "maintenance", "folder": ""}]
    assert mem.classify("샤워헤드 교체", {}, rules)["folder"] == "20_Records/Maintenance"


def test_more_specific_signal_wins():
    rules = [
        {"signal": "헤드", "type": "thing", "folder": ""},
        {"signal": "샤워헤드", "type": "maintenance", "folder": "20_Records/Maintenance"},
    ]
    assert mem.classify("샤워헤드 교체", {}, rules)["memory_type"] == "maintenance"


def test_learned_rule_media_still_needs_review():
    # 학습 규칙이 매치해도 미디어(raw_image)는 보수적으로 needs_review 유지
    rules = [{"signal": "영수증", "type": "purchase", "folder": "30_Actions/Shopping"}]
    r = mem.classify("영수증 스캔", {"raw_type": "raw_image"}, rules)
    assert r["needs_review"] is True


# --- 재분류 감사 후 키워드 보강 (B-1 github→product, B-2 송금→task) ---

def test_github_link_is_product():
    r = c("https://github.com/x/y 라이브러리", raw_type="raw_url", source_url="https://github.com/x/y")
    assert r["memory_type"] == "product", r


def test_github_link_with_action_keyword_is_task():
    # "할일" 신호가 있으면 github 링크라도 task가 우선 (가드)
    r = c("할일: github.com/x/y 코드리뷰 해야 함", raw_type="raw_url", source_url="https://github.com/x/y")
    assert r["memory_type"] == "task", r


def test_install_keyword_url_is_product():
    r = c("이 도구 설치 고려: https://example.com/tool", raw_type="raw_url", source_url="https://example.com/tool")
    assert r["memory_type"] == "product", r


def test_remittance_is_task():
    assert c("매달 말일 정화에게 생활비 송금")["memory_type"] == "task"


def test_existing_product_keyword_still_works():
    r = c("https://fascanner.duckdns.org/ 이 서비스 다음에 사용해볼 서비스로 저장", raw_type="raw_url", source_url="https://fascanner.duckdns.org/")
    assert r["memory_type"] == "product"


def test_task_project_note_still_task():
    # 감사에서 song으로 오분류됐던 건 — 개선판은 task
    assert c("* 할일: 프로젝트 이어서 진행 - 카카오톡 요약봇 추가")["memory_type"] == "task"


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
