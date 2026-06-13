#!/usr/bin/env python3
"""Scheduled lint trigger (Python port of scheduled_lint.sh).

Runs under launchd via the same homebrew python3 that already has the file
access the collector uses. The old /bin/bash wrapper failed under launchd with
"Operation not permitted" because macOS TCC blocks /bin/bash from reading
scripts under ~/Documents (exit 126). Invoking python3 directly avoids that.

Behavior (unchanged from the shell version):
  1. digest -> compute pending count
  2. if pending <= 0: stop
  3. enqueue an AI lint job (for the subscription agent)
  4. run rule-based lint immediately (fast first pass)
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEM = ROOT / "scripts" / "mem.py"
JOBS = ROOT / "scripts" / "jobs.py"
LOG = ROOT / "memory-state" / "scheduled-lint.log"
CONFIG = ROOT / "memory-config.json"


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"[{ts}] scheduled_lint: {msg}\n")


def run_json(args: list[str]) -> dict:
    result = subprocess.run([sys.executable, "-B", *args], cwd=str(ROOT), text=True, capture_output=True, check=True)
    return json.loads(result.stdout or "{}")


def main() -> None:
    try:
        digest = run_json([str(MEM), "digest"])
    except Exception as exc:  # noqa: BLE001
        log(f"digest failed: {exc}")
        return
    raw = int(digest.get("raw_notes", 0))
    processed = int(digest.get("processed_markers", 0))
    pending = max(0, raw - processed)
    log(f"raw={raw} processed={processed} pending={pending}")

    # Lint only runs when there are unprocessed raw notes.
    if pending > 0:
        try:
            job = run_json([str(JOBS), "add", "lint", "--text", f"scheduled lint: {pending} pending notes", "--adapter", "codex", "--source", "scheduled"])
            log(f"AI lint job created: {job.get('id', 'unknown')}")
        except Exception as exc:  # noqa: BLE001
            log(f"enqueue failed: {exc}")

        try:
            result = run_json([str(MEM), "lint"])
            log(f"rule-based lint processed: {result.get('processed', 0)}")
        except Exception as exc:  # noqa: BLE001
            log(f"rule lint failed: {exc}")
    else:
        log("lint skipped (no pending raw notes)")

    cfg_data = {}
    try:
        cfg_data = json.loads(CONFIG.read_text(encoding="utf-8")) if CONFIG.exists() else {}
    except Exception as exc:  # noqa: BLE001
        log(f"config read failed: {exc}")

    # enrich (Track A): extract URL memos. trafilatura only — no agent auth needed here.
    # Korean summary is a separate AI job (23:00 batch). Isolated so enrich failure
    # never masks lint success.
    try:
        enr = cfg_data.get("enrichment", {})
        if enr.get("enabled") and enr.get("auto"):
            limit = int(enr.get("maxCandidatesPerRun", 5))
            res = run_json([str(MEM), "enrich", "--limit", str(limit)])
            log(f"enrich: {res}")
        else:
            log("enrich skipped (disabled or auto=false)")
    except Exception as exc:  # noqa: BLE001
        log(f"enrich failed: {exc}")

    # extract-media (④): OCR / PDF text extraction for image/PDF attachments.
    # Isolated from enrich — a media failure never masks URL enrich success.
    try:
        med = cfg_data.get("mediaExtraction", {})
        if med.get("enabled") and med.get("auto"):
            limit = int(med.get("maxPerRun", 3))
            res = run_json([str(MEM), "extract-media", "--limit", str(limit)])
            log(f"extract-media: {res}")
        else:
            log("extract-media skipped (disabled or auto=false)")
    except Exception as exc:  # noqa: BLE001
        log(f"extract-media failed: {exc}")

    log("done")


if __name__ == "__main__":
    main()
