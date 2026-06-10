#!/usr/bin/env python3
"""Tests for process_jobs.py (P4: deterministic job-queue bridge).

Dependencies (mem.py runs, queue writes, Telegram sends) are injected as fakes,
so these tests need no network and no real vault.

Runs without pytest:  python3 tests/test_process_jobs.py
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import process_jobs as pj  # noqa: E402

CONFIG = {"telegram": {"botToken": ""}}


def make_processor(pending=None, **kwargs):
    """Build a Processor with recording fakes. Returns (processor, recorder)."""
    rec = {"mem": [], "jobs": [], "sent": [], "pending": pending or []}

    def fake_mem(*args):
        rec["mem"].append(args)
        cmd = args[0]
        if cmd == "digest":
            return {"raw_notes": 10, "processed_markers": 7, "by_type": {"maintenance": 3, "task": 2}}
        if cmd == "doctor":
            return {"checks": {"yt-dlp": True, "tesseract": True, "marker_single": False}}
        if cmd == "lint":
            return {"processed": 4}
        if cmd == "seek":
            return {"hits": [{"path": "20_Records/Maintenance/x.md", "snippet": "와이퍼 교체"}]}
        return {}

    def fake_jobs(*args):
        rec["jobs"].append(args)
        if args[0] == "list":
            return {"jobs": rec["pending"]}
        if args[0] == "summary":
            return {"counts": {}}
        return {}

    def fake_send(chat_id, text, reply_to):
        rec["sent"].append({"chat_id": chat_id, "text": text, "reply_to": reply_to})
        return True

    proc = pj.Processor(
        Path("/tmp/none"), CONFIG,
        mem_run=fake_mem, jobs_run=fake_jobs, send=fake_send,
        **kwargs,
    )
    return proc, rec


def job(job_type, status="pending", **payload):
    return {"id": f"id-{job_type}", "type": job_type, "status": status, "payload": payload}


def status_calls(rec):
    return [a for a in rec["jobs"] if a and a[0] == "set-status"]


# --- active type selection ---

def test_default_active_types_are_deterministic_only():
    proc, _ = make_processor()
    assert proc.active_types() == {"digest", "doctor"}


def test_rule_lint_flag_adds_lint():
    proc, _ = make_processor(rule_lint=True)
    assert "lint" in proc.active_types()


def test_keyword_seek_flag_adds_seek():
    proc, _ = make_processor(keyword_seek=True)
    assert "seek" in proc.active_types()


# --- deterministic completion + reply ---

def test_digest_job_completes_and_replies():
    proc, rec = make_processor()
    r = proc.process(job("digest", chat_id=466137686, message_id=5))
    assert r["action"] == "done", r
    assert r["ack"] is True
    assert ("digest",) in rec["mem"]
    # marked running then done
    sc = status_calls(rec)
    assert sc[0][2] == "running" and sc[-1][2] == "done", sc
    assert "Life Memory 요약" in rec["sent"][0]["text"]


def test_doctor_job_completes_and_replies():
    proc, rec = make_processor()
    r = proc.process(job("doctor", chat_id=1, message_id=2))
    assert r["action"] == "done"
    assert "볼트 점검" in rec["sent"][0]["text"]
    assert "marker_single" in rec["sent"][0]["text"]  # missing tool listed


# --- conflict avoidance: agent types are NOT stolen by default ---

def test_lint_skipped_by_default():
    proc, rec = make_processor()
    r = proc.process(job("lint", chat_id=1))
    assert r["action"] == "skip" and r["reason"] == "reserved_for_agent", r
    assert status_calls(rec) == []  # nothing touched


def test_repair_always_skipped():
    proc, rec = make_processor(rule_lint=True, keyword_seek=True)
    r = proc.process(job("repair"))
    assert r["action"] == "skip" and r["reason"] == "reserved_for_agent"


def test_seek_skipped_by_default():
    proc, _ = make_processor()
    r = proc.process(job("seek", query="와이퍼"))
    assert r["action"] == "skip" and r["reason"] == "reserved_for_agent"


# --- opt-in handling ---

def test_lint_completed_with_rule_lint_flag():
    proc, rec = make_processor(rule_lint=True)
    r = proc.process(job("lint", chat_id=1, message_id=9))
    assert r["action"] == "done"
    assert ("lint",) in rec["mem"]
    assert "규칙 기반 Lint" in rec["sent"][0]["text"]


def test_seek_completed_with_keyword_seek_flag():
    proc, rec = make_processor(keyword_seek=True)
    r = proc.process(job("seek", chat_id=1, query="와이퍼"))
    assert r["action"] == "done"
    assert rec["mem"][0][0] == "seek"


# --- idempotency & robustness ---

def test_non_pending_job_is_skipped():
    proc, rec = make_processor()
    r = proc.process(job("digest", status="done"))
    assert r["action"] == "skip" and r["reason"].startswith("status=")
    assert status_calls(rec) == []


def test_unknown_type_is_skipped():
    proc, _ = make_processor()
    r = proc.process(job("frobnicate"))
    assert r["action"] == "skip" and r["reason"] == "unknown_type"


def test_dry_run_changes_nothing():
    proc, rec = make_processor(dry_run=True)
    r = proc.process(job("digest", chat_id=1))
    assert r["action"] == "would_process"
    assert status_calls(rec) == [] and rec["sent"] == []


def test_failure_marks_job_failed():
    proc, rec = make_processor()

    def boom(*args):
        raise RuntimeError("mem blew up")

    proc.mem_run = boom
    r = proc.process(job("digest", chat_id=1))
    assert r["action"] == "failed", r
    failed = [a for a in status_calls(rec) if a[2] == "failed"]
    assert failed, status_calls(rec)


def test_reply_skipped_when_no_chat_id():
    proc, rec = make_processor()
    r = proc.process(job("digest"))  # no chat_id
    assert r["action"] == "done"
    assert r["ack"] is False
    assert rec["sent"] == []


# --- backlog alert (P4 follow-up) ---

import datetime as dt  # noqa: E402

NOW = dt.datetime(2026, 6, 10, 12, 0, 0)


def old_job(job_type, hours_ago, **payload):
    created = (NOW - dt.timedelta(hours=hours_ago)).isoformat()
    return {"id": f"id-{job_type}", "type": job_type, "status": "pending",
            "created_at": created, "payload": payload}


def test_alert_none_when_no_backlog():
    proc, _ = make_processor(pending=[])
    assert proc.maybe_alert(now=NOW)["alert"] == "none"


def test_alert_excludes_active_types():
    # digest is auto-completed by the bridge → not a backlog item
    proc, _ = make_processor(pending=[old_job("digest", 48)])
    assert proc.maybe_alert(now=NOW)["alert"] == "none"


def test_alert_below_threshold_when_recent():
    proc, _ = make_processor(pending=[old_job("lint", 1)])  # 1h < 6h default
    r = proc.maybe_alert(now=NOW, read_state=lambda: None, write_state=lambda s: None)
    assert r["alert"] == "below_threshold", r


def test_alert_sent_when_old_enough():
    proc, rec = make_processor(pending=[old_job("lint", 8, chat_id=466137686)])
    wrote = {}
    r = proc.maybe_alert(now=NOW, read_state=lambda: None, write_state=lambda s: wrote.setdefault("t", s))
    assert r["alert"] == "sent", r
    assert "미처리 작업" in rec["sent"][0]["text"]
    assert wrote.get("t")  # state persisted


def test_alert_cooldown_blocks_repeat():
    recent = (NOW - dt.timedelta(hours=1)).isoformat()
    proc, rec = make_processor(pending=[old_job("lint", 8, chat_id=1)])
    r = proc.maybe_alert(now=NOW, read_state=lambda: recent, write_state=lambda s: None)
    assert r["alert"] == "cooldown", r
    assert rec["sent"] == []


def test_alert_disabled_via_config():
    proc, _ = make_processor(pending=[old_job("lint", 48)])
    proc.alert_cfg["enabled"] = False
    assert proc.maybe_alert(now=NOW)["alert"] == "disabled"


def test_job_age_hours():
    assert round(pj.job_age_hours(old_job("lint", 5), NOW)) == 5


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
