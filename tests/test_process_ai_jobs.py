#!/usr/bin/env python3
"""Tests for process_ai_jobs.py (P4-AI / ③a core).

The agent call is faked — no real claude/codex runs, no vault writes, no usage.

Runs without pytest:  python3 tests/test_process_ai_jobs.py
"""

import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import process_ai_jobs as pa  # noqa: E402

CONFIG = {
    "agent": {
        "default": "claude",
        "aiJobTypes": ["lint", "repair", "seek", "enrich"],
        "commands": {
            "claude": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits"],
            "codex": ["codex", "exec", "{prompt}"],
        },
        "modelByJobType": {
            "claude": {"lint": "sonnet", "repair": "sonnet", "seek": "sonnet", "enrich": "haiku"},
            "codex": {},
        },
    }
}


def make(agent="", exit_code=0, post_status="done", pending=None, **kwargs):
    rec = {"agent_cmds": [], "status_calls": [], "pending": pending or []}

    def fake_agent(cmd):
        rec["agent_cmds"].append(cmd)
        return exit_code

    def fake_jobs(*args):
        if args[0] == "list":
            # status filter present -> return pending list; bare list -> return post-run view
            if "--status" in args:
                return {"jobs": rec["pending"]}
            # after-run status lookup: reflect post_status for processed ids
            return {"jobs": [{**j, "status": post_status} for j in rec["pending"]]}
        if args[0] == "set-status":
            rec["status_calls"].append(args)
        return {}

    proc = pa.AiProcessor(Path("/tmp/x"), CONFIG, agent=agent, agent_run=fake_agent, jobs_run=fake_jobs, **kwargs)
    return proc, rec


def job(job_type, status="pending", jid=None):
    return {"id": jid or f"id-{job_type}", "type": job_type, "status": status, "created_at": "2026-06-10T10:00:00", "payload": {}}


# --- pure helpers ---

def test_build_command_substitutes_prompt():
    cmd = pa.build_command(["claude", "-p", "{prompt}", "--x"], "HELLO")
    assert cmd == ["claude", "-p", "HELLO", "--x"]


def test_build_prompt_has_guards():
    p = pa.build_prompt("abc123", "lint")
    assert "abc123" in p and "NON-INTERACTIVE" in p
    assert "Review" in p and "never edit or delete raw" in p


def test_enrich_recognized_as_ai_type():
    # enrich jobs (from /웹요약 or auto-enqueue) must be picked up by the AI bridge.
    proc, rec = make(pending=[job("enrich")])
    results = proc.run()
    assert len(results) == 1
    assert results[0]["type"] == "enrich" and results[0]["action"] == "ran"


def test_model_routing_haiku_for_enrich():
    proc, rec = make(pending=[job("enrich")], dry_run=True)
    r = proc.run()[0]
    assert r["model"] == "haiku"
    assert r["command"][-2:] == ["--model", "haiku"]


def test_model_routing_sonnet_for_lint():
    proc, rec = make(pending=[job("lint")], dry_run=True)
    r = proc.run()[0]
    assert r["model"] == "sonnet"
    assert "--model" in r["command"] and "sonnet" in r["command"]


def test_no_model_flag_when_agent_map_empty():
    # codex has an empty model map -> no --model appended (uses agent default model).
    proc, rec = make(agent="codex", pending=[job("enrich")], dry_run=True)
    r = proc.run()[0]
    assert r["model"] == "(default)"
    assert "--model" not in r["command"]


def test_build_command_appends_model_only_when_set():
    assert pa.build_command(["claude", "-p", "{prompt}"], "X") == ["claude", "-p", "X"]
    assert pa.build_command(["claude", "-p", "{prompt}"], "X", "haiku") == ["claude", "-p", "X", "--model", "haiku"]


def test_unmapped_job_falls_back_to_default_model():
    # An unmapped/new job type must NOT error — it uses the agent's 'default' entry.
    cfg = {"agent": {"default": "claude", "aiJobTypes": ["lint", "audit"],
                     "commands": {"claude": ["claude", "-p", "{prompt}"]},
                     "modelByJobType": {"claude": {"default": "sonnet", "enrich": "haiku"}}}}

    def fj(*a):
        if a[0] == "list" and "--status" in a:
            return {"jobs": [job("audit")]}
        return {"jobs": []}

    proc = pa.AiProcessor(Path("/tmp/x"), cfg, dry_run=True, jobs_run=fj, agent_run=lambda c: 0)
    r = proc.run()[0]
    assert r["model"] == "sonnet"  # audit is unmapped -> default
    assert r["command"][-2:] == ["--model", "sonnet"]


def test_terminal_action_respects_agent_finalization():
    assert pa.terminal_action(0, "done") == (None, None)
    assert pa.terminal_action(1, "failed") == (None, None)


def test_terminal_action_autofinalizes_on_success():
    status, note = pa.terminal_action(0, "running")
    assert status == "done"


def test_terminal_action_fails_on_nonzero():
    status, note = pa.terminal_action(2, "running")
    assert status == "failed" and "2" in note


# --- selection / gating ---

def test_selects_only_ai_types():
    proc, _ = make(pending=[job("lint"), job("digest"), job("seek"), job("doctor")])
    ids = [j["id"] for j in proc.pending_ai_jobs()]
    assert ids == ["id-lint", "id-seek"], ids


def test_non_ai_type_skipped():
    proc, rec = make()
    r = proc.process(job("digest"))
    assert r["action"] == "skip" and r["reason"] == "not_ai_type"
    assert rec["agent_cmds"] == []


def test_non_pending_skipped():
    proc, rec = make()
    r = proc.process(job("lint", status="done"))
    assert r["action"] == "skip" and r["reason"].startswith("status=")
    assert rec["agent_cmds"] == []


# --- dry-run (no execution) ---

def test_dry_run_builds_command_without_running():
    proc, rec = make(dry_run=True)
    r = proc.process(job("lint"))
    assert r["action"] == "would_run"
    assert r["command"][0] == "claude" and "{prompt}" not in " ".join(r["command"])
    assert rec["agent_cmds"] == [] and rec["status_calls"] == []


# --- run path with fake agent ---

def test_run_marks_running_then_respects_agent_done():
    proc, rec = make(exit_code=0, post_status="done", pending=[job("lint")])
    results = proc.run()
    assert results[0]["action"] == "ran" and results[0]["exit_code"] == 0
    assert rec["agent_cmds"], "agent should have been invoked"
    # set running was called; agent self-finalized to done so no extra terminal write
    assert any(c[2] == "running" for c in rec["status_calls"])
    assert not any(c[2] in ("done", "failed") for c in rec["status_calls"])


def test_run_finalizes_failed_when_agent_errors_and_status_stuck():
    proc, rec = make(exit_code=3, post_status="running", pending=[job("repair")])
    results = proc.run()
    assert results[0]["final_status"] == "failed"
    assert any(c[2] == "failed" for c in rec["status_calls"])


def test_run_autofinalizes_done_when_exit0_but_status_stuck():
    proc, rec = make(exit_code=0, post_status="running", pending=[job("seek")])
    results = proc.run()
    assert results[0]["final_status"] == "done"
    assert any(c[2] == "done" for c in rec["status_calls"])


def test_agent_override_selects_codex_template():
    proc, _ = make(agent="codex")
    assert proc.template[0] == "codex"


def test_unknown_agent_raises():
    try:
        pa.AiProcessor(Path("/tmp/x"), CONFIG, agent="nope")
    except SystemExit:
        return
    raise AssertionError("expected SystemExit for unknown agent")


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
