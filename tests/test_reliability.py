#!/usr/bin/env python3
"""Reliability/security tests (P2: atomic writes, queue lock, telegram auth).

Runs without pytest:  python3 tests/test_reliability.py
"""

import argparse
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402
import jobs  # noqa: E402
import telegram_collector as tc  # noqa: E402


# --- P2-a: atomic_write_text ---

def test_atomic_write_creates_file_with_content():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sub" / "note.md"
        mem.atomic_write_text(p, "hello\nworld\n")
        assert p.read_text(encoding="utf-8") == "hello\nworld\n"


def test_atomic_write_leaves_no_temp_file():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "note.md"
        mem.atomic_write_text(p, "data")
        leftovers = [x.name for x in Path(d).iterdir() if x.name != "note.md"]
        assert leftovers == [], leftovers


def test_atomic_write_overwrites_existing():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "note.md"
        mem.atomic_write_text(p, "v1")
        mem.atomic_write_text(p, "v2")
        assert p.read_text(encoding="utf-8") == "v2"


# --- P2-b: queue lock + atomic write_jsonl ---

def _add(queue_dir, job_type, text):
    args = argparse.Namespace(
        queue_dir=str(queue_dir), type=job_type, text=text, query="",
        adapter="codex", source="test", requested_by="", chat_id="", message_id="",
    )
    jobs.add_job(args)


def test_queue_add_preserves_all_jobs():
    with tempfile.TemporaryDirectory() as d:
        qd = Path(d) / "jobs"
        for i in range(5):
            _add(qd, "lint", f"job {i}")
        rows = [row for _, row in jobs.load_all(qd)]
        assert len(rows) == 5, rows
        # all ids unique, nothing dropped by the read-modify-write
        assert len({r["id"] for r in rows}) == 5


def test_queue_write_leaves_no_temp_file():
    with tempfile.TemporaryDirectory() as d:
        qd = Path(d) / "jobs"
        _add(qd, "digest", "x")
        leftovers = [p.name for p in qd.iterdir() if p.name.startswith(".") and ".tmp." in p.name]
        assert leftovers == [], leftovers


def test_queue_lock_is_usable():
    with tempfile.TemporaryDirectory() as d:
        qd = Path(d) / "jobs"
        with jobs.queue_lock(qd):
            pass  # acquiring + releasing must not raise
        assert (qd / ".queue.lock").exists()


# --- P2-c: telegram auth deny-by-default ---

def _msg(uid):
    return {"from": {"id": uid}, "chat": {"id": uid}, "message_id": 1}


def test_empty_allowlist_denies():
    assert tc.user_allowed({"telegram": {"allowedUserIds": []}}, _msg(123)) is False


def test_registered_id_allowed():
    cfg = {"telegram": {"allowedUserIds": [123, 456]}}
    assert tc.user_allowed(cfg, _msg(123)) is True


def test_unregistered_id_denied():
    cfg = {"telegram": {"allowedUserIds": [456]}}
    assert tc.user_allowed(cfg, _msg(123)) is False


# --- D-1: frontmatter list round-trip ---

def test_frontmatter_scalar_still_parses():
    text = mem.frontmatter({"memory_type": "maintenance", "sensitivity": "private"}) + "body"
    meta, body = mem.parse_frontmatter(text)
    assert meta["memory_type"] == "maintenance" and meta["sensitivity"] == "private"
    assert body == "body"


def test_frontmatter_list_round_trips():
    fields = {"memory_type": "song", "tags": ["음악", "발라드"], "related": ["[[A]]", "[[B]]"]}
    text = mem.frontmatter(fields) + "body\n"
    meta, _ = mem.parse_frontmatter(text)
    assert meta["tags"] == ["음악", "발라드"], meta
    assert meta["related"] == ["[[A]]", "[[B]]"]
    assert meta["memory_type"] == "song"


def test_frontmatter_no_frontmatter():
    meta, body = mem.parse_frontmatter("just text\n")
    assert meta == {} and body == "just text\n"


# --- digest pending_raw: 마커 수가 아니라 raw별 마커 존재로 센다 (2026-10-08) ---

def test_digest_pending_raw_ignores_extra_markers():
    import contextlib, hashlib, io, json
    with tempfile.TemporaryDirectory() as d:
        vault = Path(d)
        raw_dir = vault / "00_Inbox/Raw/2026/10"
        proc = vault / "00_Inbox/Processed"
        raw_dir.mkdir(parents=True)
        proc.mkdir(parents=True)
        for name in ("a.md", "b.md"):
            (raw_dir / name).write_text("x\n", encoding="utf-8")
        done = hashlib.sha1("00_Inbox/Raw/2026/10/a.md".encode()).hexdigest()[:16]
        (proc / f"{done}.json").write_text("{}", encoding="utf-8")
        # 같은 raw의 NFC/NFD 변형 같은 여분 마커 2개 → raw − 마커 = 0 이 되어버리는 상황
        (proc / "extra1.json").write_text("{}", encoding="utf-8")
        (proc / "extra2.json").write_text("{}", encoding="utf-8")
        cfg = {"memoryVault": {"vaultPath": str(vault), "rawFolder": "00_Inbox/Raw",
                               "processedFolder": "00_Inbox/Processed"}}
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mem.digest(cfg)
        out = json.loads(buf.getvalue())
        assert out["raw_notes"] - out["processed_markers"] <= 0
        assert out["pending_raw"] == 1, out


# --- send_message 재시도: 순간 끊김이면 다시 보내고, 4xx면 바로 포기 (2026-10-08) ---

def _send_with(errors):
    import urllib.error  # noqa: F401
    calls = []
    orig_api, orig_sleep = tc.api_json, tc.time.sleep
    def fake(token, method, params, timeout=0):
        calls.append(method)
        err = errors[len(calls) - 1] if len(calls) <= len(errors) else None
        if err:
            raise err
        return {}
    tc.api_json, tc.time.sleep = fake, (lambda s: None)
    try:
        try:
            tc.send_message("t", 1, "hi")
            return "ok", len(calls)
        except Exception as exc:  # noqa: BLE001
            return type(exc).__name__, len(calls)
    finally:
        tc.api_json, tc.time.sleep = orig_api, orig_sleep


def test_send_message_retries_connection_reset():
    import urllib.error
    reset = urllib.error.URLError(ConnectionResetError(54, "reset"))
    assert _send_with([reset, None]) == ("ok", 2)
    assert _send_with([reset, reset, reset]) == ("URLError", 3)


def test_send_message_does_not_retry_client_error():
    import io, urllib.error
    bad = urllib.error.HTTPError("u", 400, "bad", {}, io.BytesIO())
    assert _send_with([bad]) == ("HTTPError", 1)


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
