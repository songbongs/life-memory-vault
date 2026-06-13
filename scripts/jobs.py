#!/usr/bin/env python3
"""Small JSONL job queue for Life Memory agent requests.

Telegram commands and future MCP tools write standard jobs here. AI agents then
read the same queue regardless of where the user invoked them from.
"""

from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_QUEUE_DIR = ROOT / "memory-state" / "jobs"
VALID_TYPES = {"lint", "doctor", "repair", "seek", "digest", "status", "enrich"}
VALID_STATUS = {"pending", "running", "done", "failed", "cancelled"}


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def today_queue_path(queue_dir: Path) -> Path:
    return queue_dir / f"queue-{now_local().strftime('%Y-%m-%d')}.jsonl"


def short_id(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


@contextmanager
def queue_lock(queue_dir: Path):
    """Exclusive file lock around read-modify-write on the job queue.

    The collector and the (P4) job processor can both mutate the same daily
    queue file; without this lock a concurrent rewrite could drop jobs.
    """
    queue_dir.mkdir(parents=True, exist_ok=True)
    lock_path = queue_dir / ".queue.lock"
    with open(lock_path, "w") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def all_queue_files(queue_dir: Path) -> list[Path]:
    return sorted(queue_dir.glob("queue-*.jsonl")) if queue_dir.exists() else []


def load_all(queue_dir: Path) -> list[tuple[Path, dict[str, Any]]]:
    items: list[tuple[Path, dict[str, Any]]] = []
    for path in all_queue_files(queue_dir):
        for row in read_jsonl(path):
            items.append((path, row))
    return items


def add_job(args: argparse.Namespace) -> None:
    queue_dir = Path(args.queue_dir).expanduser()
    job_type = args.type.lower().strip()
    if job_type not in VALID_TYPES:
        raise SystemExit(f"Unknown job type: {args.type}. Expected one of: {', '.join(sorted(VALID_TYPES))}")
    created_at = now_local().isoformat(timespec="seconds")
    payload = {
        "query": args.query,
        "raw_text": args.text,
        "requested_by": args.requested_by,
        "source": args.source,
        "chat_id": args.chat_id,
        "message_id": args.message_id,
    }
    seed = f"{created_at}:{job_type}:{json.dumps(payload, ensure_ascii=False, sort_keys=True)}"
    job = {
        "id": short_id(seed),
        "type": job_type,
        "status": "pending",
        "created_at": created_at,
        "updated_at": created_at,
        "adapter": args.adapter,
        "payload": {key: value for key, value in payload.items() if value not in (None, "")},
        "result": {},
        "notes": [],
    }
    path = today_queue_path(queue_dir)
    with queue_lock(queue_dir):
        rows = read_jsonl(path)
        rows.append(job)
        write_jsonl(path, rows)
    print(json.dumps(job, ensure_ascii=False, indent=2))


def list_jobs(args: argparse.Namespace) -> None:
    queue_dir = Path(args.queue_dir).expanduser()
    rows = [row for _, row in load_all(queue_dir)]
    if args.status:
        rows = [row for row in rows if row.get("status") == args.status]
    if args.type:
        rows = [row for row in rows if row.get("type") == args.type]
    rows = sorted(rows, key=lambda row: row.get("created_at", ""))
    if args.limit:
        rows = rows[-args.limit :]
    print(json.dumps({"jobs": rows, "count": len(rows)}, ensure_ascii=False, indent=2))


def next_job(args: argparse.Namespace) -> None:
    queue_dir = Path(args.queue_dir).expanduser()
    rows = [row for _, row in load_all(queue_dir)]
    rows = [row for row in rows if row.get("status") == "pending"]
    if args.type:
        rows = [row for row in rows if row.get("type") == args.type]
    rows = sorted(rows, key=lambda row: row.get("created_at", ""))
    print(json.dumps(rows[0] if rows else {}, ensure_ascii=False, indent=2))


def set_status(args: argparse.Namespace) -> None:
    queue_dir = Path(args.queue_dir).expanduser()
    status = args.status.lower().strip()
    if status not in VALID_STATUS:
        raise SystemExit(f"Unknown status: {args.status}. Expected one of: {', '.join(sorted(VALID_STATUS))}")
    found = False
    with queue_lock(queue_dir):
        for path in all_queue_files(queue_dir):
            rows = read_jsonl(path)
            changed = False
            for row in rows:
                if row.get("id") != args.id:
                    continue
                row["status"] = status
                row["updated_at"] = now_local().isoformat(timespec="seconds")
                if args.note:
                    row.setdefault("notes", []).append(args.note)
                if args.result_json:
                    row["result"] = json.loads(args.result_json)
                changed = True
                found = True
            if changed:
                write_jsonl(path, rows)
                break
    if not found:
        raise SystemExit(f"Job not found: {args.id}")
    print(json.dumps({"id": args.id, "status": status}, ensure_ascii=False, indent=2))


def summary(args: argparse.Namespace) -> None:
    queue_dir = Path(args.queue_dir).expanduser()
    counts: dict[str, dict[str, int]] = {}
    for _, row in load_all(queue_dir):
        job_type = row.get("type", "unknown")
        status = row.get("status", "unknown")
        counts.setdefault(job_type, {})
        counts[job_type][status] = counts[job_type].get(status, 0) + 1
    print(json.dumps({"queue_dir": str(queue_dir), "counts": counts}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Life Memory job queue")
    parser.add_argument("--queue-dir", default=str(DEFAULT_QUEUE_DIR))
    sub = parser.add_subparsers(dest="command", required=True)

    add = sub.add_parser("add")
    add.add_argument("type")
    add.add_argument("--text", default="")
    add.add_argument("--query", default="")
    add.add_argument("--adapter", default="codex")
    add.add_argument("--source", default="telegram")
    add.add_argument("--requested-by", default="")
    add.add_argument("--chat-id", default="")
    add.add_argument("--message-id", default="")

    list_parser = sub.add_parser("list")
    list_parser.add_argument("--status", default="")
    list_parser.add_argument("--type", default="")
    list_parser.add_argument("--limit", type=int, default=0)

    next_parser = sub.add_parser("next")
    next_parser.add_argument("--type", default="")

    status_parser = sub.add_parser("set-status")
    status_parser.add_argument("id")
    status_parser.add_argument("status")
    status_parser.add_argument("--note", default="")
    status_parser.add_argument("--result-json", default="")

    sub.add_parser("summary")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "add":
        add_job(args)
    elif args.command == "list":
        list_jobs(args)
    elif args.command == "next":
        next_job(args)
    elif args.command == "set-status":
        set_status(args)
    elif args.command == "summary":
        summary(args)


if __name__ == "__main__":
    main()
