#!/usr/bin/env python3
"""Scheduled lint trigger (Python port of scheduled_lint.sh).

Runs under launchd via the same homebrew python3 that already has the file
access the collector uses. The old /bin/bash wrapper failed under launchd with
"Operation not permitted" because macOS TCC blocks /bin/bash from reading
scripts under ~/Documents (exit 126). Invoking python3 directly avoids that.

Behavior (steps 3-4 reordered 2026-10-08 so the AI job no longer finds nothing to do):
  1. digest -> compute pending count
  2. if pending <= 0: stop
  3. run rule-based lint immediately (fast first pass)
  4. enqueue an AI "polish" lint job for the notes just rule-linted (or a full
     lint job if rule lint failed)
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
import urllib.request
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


def _alert_telegram(cfg: dict, text: str) -> bool:
    """Best-effort Telegram alert using stdlib only (no python-telegram-bot import)."""
    tg = cfg.get("telegram", {})
    import os
    token = os.environ.get("TELEGRAM_BOT_TOKEN") or tg.get("botToken", "")
    allowed = tg.get("allowedUserIds") or []
    chat_id = tg.get("adminChatId") or (allowed[0] if allowed else None)
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps({"chat_id": int(chat_id), "text": text}).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=10)
        return True
    except Exception as exc:  # noqa: BLE001
        log(f"telegram alert failed: {exc}")
        return False


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
    # pending_raw = 마커 없는 raw 실측. raw − 마커 수로 빼면 NFC/NFD 중복 마커 때문에
    # 실제보다 적게 나와 새 메모를 건너뛰었다 (2026-10-08).
    pending = int(digest.get("pending_raw", max(0, raw - processed)))
    log(f"raw={raw} processed={processed} pending={pending}")

    # Lint only runs when there are unprocessed raw notes.
    if pending > 0:
        since = dt.datetime.now().astimezone().isoformat(timespec="seconds")
        processed_now = 0
        rule_ok = False
        try:
            result = run_json([str(MEM), "lint"])
            processed_now = int(result.get("processed", 0))
            rule_ok = True
            log(f"rule-based lint processed: {processed_now}")
        except Exception as exc:  # noqa: BLE001
            log(f"rule lint failed: {exc}")

        # AI 잡은 rule lint *뒤에* 다듬기(polish) 잡으로 넣는다. 예전엔 "미처리 raw"를 찾는
        # lint 잡을 먼저 넣고 rule lint를 바로 돌려, AI가 늘 "처리할 raw 없음"으로 끝났다.
        # rule lint가 실패하면 예전처럼 AI가 raw부터 처리하는 일반 lint 잡을 넣는다.
        if processed_now > 0 or not rule_ok:
            try:
                text = (f"polish rule_based since {since}: {processed_now} notes" if rule_ok
                        else f"scheduled lint: {pending} pending notes")
                job = run_json([str(JOBS), "add", "lint", "--text", text, "--adapter", "codex", "--source", "scheduled"])
                log(f"AI lint job created: {job.get('id', 'unknown')} ({text})")
            except Exception as exc:  # noqa: BLE001
                log(f"enqueue failed: {exc}")
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
            failed_count = int(res.get("failed", 0))
            if failed_count > 0:
                msg = (
                    f"⚠️ URL 요약 실패 {failed_count}건\n"
                    f"python3 scripts/mem.py enrich --status failed  ← 실패 목록\n"
                    f"python3 scripts/mem.py enrich --force --limit {failed_count}  ← 재시도"
                )
                if _alert_telegram(cfg_data, msg):
                    log(f"enrich failure alert sent: {failed_count}건")
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

    # moc-sync: MOC 등록을 AI 잡에 맡기지 않고 결정적으로 메운다. AI lint 잡이 "0건"으로
    # 끝나거나 실패해도 노트가 목록에서 빠지지 않게 하기 위함 (2026-10-04, 163건 누락 사고).
    # 요약은 23:00 배치에서 생기므로 오늘 노트는 대개 다음 날 22:00에 등록된다.
    try:
        res = run_json([str(MEM), "moc-sync", "--apply"])
        log(f"moc-sync: ideas+{res.get('ideas_added', 0)} life+{res.get('life_added', 0)} waiting={res.get('waiting_for_summary', 0)}")
    except Exception as exc:  # noqa: BLE001
        log(f"moc-sync failed: {exc}")

    log("done")


if __name__ == "__main__":
    main()
