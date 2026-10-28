#!/usr/bin/env python3
"""Tests for scheduled_lint.enqueue_link_backfill.

밀린 백필 잡이 없으면 잡 2개를 넣고, 남아 있으면 더 쌓지 않는지 확인한다.
(2026-10-28 밤: 로그 한 줄의 따옴표가 빠져 첫 잡만 들어가고 NameError로 끝났다.)
"""

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import scheduled_lint  # noqa: E402


def _run(pending_jobs):
    added = []

    def fake_run_json(args):
        if "link-backlog" in args:
            return {"total": 673}
        if "list" in args:
            return {"jobs": pending_jobs}
        if "add" in args:
            added.append(args)
            return {"id": f"job{len(added)}"}
        raise AssertionError(args)

    scheduled_lint.run_json = fake_run_json
    scheduled_lint.LOG = Path(tempfile.mkdtemp()) / "lint.log"
    scheduled_lint.enqueue_link_backfill()
    return added, scheduled_lint.LOG.read_text(encoding="utf-8")


def test_enqueues_two_jobs_when_none_waiting():
    added, log = _run([])
    assert len(added) == scheduled_lint.BACKFILL_JOBS == 2, log
    assert "failed" not in log and "job2" in log, log


def test_skips_when_backfill_job_still_pending():
    added, log = _run([{"payload": {"raw_text": scheduled_lint.BACKFILL_TEXT}}])
    assert added == [] and "skipped" in log, log


if __name__ == "__main__":
    test_enqueues_two_jobs_when_none_waiting()
    test_skips_when_backfill_job_still_pending()
    print("ok")
