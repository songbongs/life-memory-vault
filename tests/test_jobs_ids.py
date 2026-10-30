#!/usr/bin/env python3
"""같은 초에 같은 잡을 두 번 넣어도 id가 달라야 한다 (2026-10-29 백필 잡 2개가 한 id로 묶였다)."""

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import jobs  # noqa: E402


def test_same_job_twice_gets_two_ids():
    queue = tempfile.mkdtemp()
    args = argparse.Namespace(queue_dir=queue, type="lint", query=None, text="link backfill: 25 notes",
                              requested_by="system", source="scheduled", chat_id=None, message_id=None,
                              adapter="codex")
    ids = []
    for _ in range(2):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            jobs.add_job(args)
        ids.append(json.loads(out.getvalue())["id"])
    assert ids[0] != ids[1], ids


if __name__ == "__main__":
    test_same_job_twice_gets_two_ids()
    print("ok")
