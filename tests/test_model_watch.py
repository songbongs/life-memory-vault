#!/usr/bin/env python3
"""Tests for model_watch (mem.py model-watch).

새 버전은 한 번만 묻고, 승인(apply) 전에는 설정을 안 바꾸고, 바꾼 뒤 실제 사용 모델을 확인하는지 본다.
"""

import datetime as dt
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import model_watch as mw  # noqa: E402

PAGE = "<td>claude-haiku-5-5</td> claude-haiku-4-5-20251001 claude-sonnet-5-5 claude-opus-5-5 claude-sonnet-3-7"
NEWER = PAGE + " claude-haiku-5-6"


def _cfg(enrich="claude-haiku-5-5", lint="claude-sonnet-5-5"):
    return {"agent": {"modelByJobType": {"claude": {"default": "sonnet", "lint": lint, "enrich": enrich}}}}


def _tmp():
    d = Path(tempfile.mkdtemp())
    return d, d / "state.json"


def test_parse_model():
    assert mw.parse_model("claude-haiku-5-5") == ("haiku", (5, 5))
    assert mw.parse_model("claude-haiku-4-5-20251001") == ("haiku", (4, 5))
    assert mw.parse_model("claude-sonnet-5") == ("sonnet", (5, 0))
    assert mw.parse_model("sonnet") == ("sonnet", None)
    assert mw.parse_model("gpt-6.1-sol") == ("", None)


def test_latest_versions_picks_highest_per_family():
    latest = mw.latest_versions(NEWER)
    assert latest["haiku"] == (5, 6) and latest["sonnet"] == (5, 5), latest


def test_no_proposal_when_current_is_latest_except_alias():
    props = mw.proposals(_cfg(), mw.latest_versions(PAGE))
    # 별칭(default: sonnet)은 버전을 몰라서 전체 ID 고정을 제안한다
    assert [(p["job"], p["proposed"]) for p in props] == [("default", "claude-sonnet-5-5")], props


def test_check_asks_once_and_never_changes_config():
    _, state = _tmp()
    sent = []
    cfg = _cfg()
    before = json.dumps(cfg)
    out = mw.check(cfg, sent.append, force=True, fetch=lambda: NEWER, state_path=state)
    assert any(p["proposed"] == "claude-haiku-5-6" for p in out["proposed"]), out
    assert len(sent) == 1 and "claude-haiku-5-5 → claude-haiku-5-6" in sent[0] and "승인" in sent[0], sent
    assert json.dumps(cfg) == before
    mw.check(cfg, sent.append, force=True, fetch=lambda: NEWER, state_path=state)
    assert len(sent) == 1, sent  # 같은 버전은 다시 묻지 않는다


def test_check_respects_weekly_interval():
    _, state = _tmp()
    sent = []
    today = dt.date(2026, 10, 19)
    mw.check(_cfg(), sent.append, fetch=lambda: PAGE, today=today, state_path=state)
    out = mw.check(_cfg(), sent.append, fetch=lambda: NEWER, today=today + dt.timedelta(days=3), state_path=state)
    assert out.get("skipped"), out


def test_fetch_failure_alerts_once_a_week():
    _, state = _tmp()
    sent = []

    def boom():
        raise OSError("offline")
    today = dt.date(2026, 10, 19)
    mw.check(_cfg(), sent.append, force=True, fetch=boom, today=today, state_path=state)
    mw.check(_cfg(), sent.append, force=True, fetch=boom, today=today + dt.timedelta(days=1), state_path=state)
    mw.check(_cfg(), sent.append, force=True, fetch=lambda: "no ids here", today=today + dt.timedelta(days=8),
             state_path=state)
    assert len(sent) == 2 and all("못 읽었어요" in s for s in sent), sent


def test_apply_backs_up_and_changes_only_named_job():
    d, state = _tmp()
    cfg_path = d / "memory-config.json"
    cfg_path.write_text(json.dumps(_cfg()), encoding="utf-8")
    dry = mw.apply(["enrich"], config_path=cfg_path, state_path=state, fetch=lambda: NEWER, dry_run=True)
    assert dry["would_change"] and json.loads(cfg_path.read_text())["agent"]["modelByJobType"]["claude"]["enrich"] == "claude-haiku-5-5"
    out = mw.apply(["enrich"], config_path=cfg_path, state_path=state, fetch=lambda: NEWER)
    models = json.loads(cfg_path.read_text())["agent"]["modelByJobType"]["claude"]
    assert models["enrich"] == "claude-haiku-5-6" and models["default"] == "sonnet", models
    assert Path(out["backup"]).exists()
    assert "enrich" in json.loads(state.read_text())["pending_verify"]


def test_verify_applied_reads_session_models():
    d, state = _tmp()
    sessions = d / "sessions"
    sessions.mkdir()
    since = (dt.datetime.now().astimezone() - dt.timedelta(minutes=5)).isoformat(timespec="seconds")
    mw.save_state({"pending_verify": {"enrich": {"model": "claude-haiku-5-6", "previous": "claude-haiku-5-5",
                                                 "since": since}}}, state)
    sent = []
    out = mw.verify_applied(sent.append, state_path=state, sessions=sessions)
    assert out == {"verified": [], "waiting": ["enrich"]} and not sent, out
    (sessions / "a.jsonl").write_text(
        '{"message":{"content":"Process ONLY the pending job whose id is x (type: enrich)."}}\n'
        '{"message":{"model":"claude-haiku-5-6"}}\n', encoding="utf-8")
    out = mw.verify_applied(sent.append, state_path=state, sessions=sessions)
    assert out["verified"] == ["enrich"] and "✅ enrich" in sent[0], (out, sent)


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
