#!/usr/bin/env python3
"""Autonomous processor for the Life Memory job queue (P4: close the loop).

The Telegram collector enqueues jobs (/digest, /doctor, /lint, /seek, ...) and
promises "AI 처리 후 결과를 알려드릴게요", but until now nothing consumed the
queue without a human-invoked agent. This bridge closes the loop for the job
types that can be completed deterministically and locally, and replies to the
user on Telegram. AI/semantic types stay reserved for the subscription agent
described in prompts/process-pending-jobs.md (see agent.jobsProcessorPath).

Default autonomous scope: digest, doctor.
Opt-in flags:
  --rule-lint     also complete `lint` jobs via the rule-based mem.py lint
  --keyword-seek  also complete `seek` jobs via the keyword mem.py seek

`repair` and the AI Wiki-layer lint are never auto-completed here; they are left
pending for the subscription agent so this bridge cannot steal agent work.

Idempotent: only jobs with status == "pending" are touched.
Queue writes go through jobs.py, which is file-locked and atomic (see P2).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "memory-config.json"
MEM = ROOT / "scripts" / "mem.py"
JOBS = ROOT / "scripts" / "jobs.py"

sys.path.insert(0, str(ROOT / "scripts"))
import telegram_collector as tc  # noqa: E402

# Types this bridge can complete without any AI/metered API.
DETERMINISTIC_TYPES = {"digest", "doctor"}
# Types reserved for the subscription agent unless explicitly opted in.
AGENT_TYPES = {"lint", "repair", "seek"}


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def today() -> str:
    return now_local().strftime("%Y-%m-%d")


def _run_json(cmd: list[str]) -> dict[str, Any]:
    result = subprocess.run(cmd, cwd=str(ROOT), text=True, capture_output=True, check=True)
    return json.loads(result.stdout or "{}")


def default_mem_run(config_path: Path, *args: str) -> dict[str, Any]:
    return _run_json([sys.executable, str(MEM), "--config", str(config_path), *args])


def default_jobs_run(*args: str) -> dict[str, Any]:
    return _run_json([sys.executable, str(JOBS), *args])


def default_sender(token: str) -> Callable[[Any, str, Any], bool]:
    def send(chat_id: Any, text: str, reply_to: Any) -> bool:
        if not token or not chat_id or not text:
            return False
        try:
            tc.send_message(token, int(chat_id), text, reply_to)
            return True
        except Exception:
            return False

    return send


# --- Reply formatters -------------------------------------------------------

def format_digest(data: dict[str, Any], queue_summary: dict[str, Any] | None) -> str:
    raw = int(data.get("raw_notes", 0))
    processed = int(data.get("processed_markers", 0))
    pending = max(0, raw - processed)
    by_type = data.get("by_type", {})
    top = ", ".join(f"{k} {v}건" for k, v in sorted(by_type.items(), key=lambda x: -x[1])[:5])
    lines = [
        f"📊 Life Memory 요약 ({today()})",
        f"Raw 노트: {raw}건 | 처리: {processed}건 | 미처리: {pending}건",
        f"주요 분류: {top or '없음'}",
    ]
    if queue_summary:
        counts = queue_summary.get("counts", {})
        pend = sum(v.get("pending", 0) for v in counts.values())
        done = sum(v.get("done", 0) for v in counts.values())
        lines.append(f"작업 큐: pending {pend}건, done {done}건")
    return "\n".join(lines)


def format_doctor(data: dict[str, Any]) -> str:
    checks = data.get("checks", {})
    ok = sum(1 for v in checks.values() if v)
    total = len(checks)
    missing = [name for name, available in checks.items() if not available]
    lines = [
        f"🩺 볼트 점검 ({today()})",
        f"도구 가용성: {ok}/{total}",
    ]
    if missing:
        lines.append("미설치: " + ", ".join(missing))
    else:
        lines.append("모든 도구 사용 가능")
    return "\n".join(lines)


def format_lint(data: dict[str, Any]) -> str:
    processed = int(data.get("processed", 0))
    return (
        f"✅ 규칙 기반 Lint 완료 ({today()})\n"
        f"처리: {processed}건\n"
        "AI 심화 정리(엔티티·MOC·링크)는 에이전트가 별도 처리합니다."
    )


def format_seek(query: str, data: dict[str, Any]) -> str:
    hits = data.get("hits", [])
    if not hits:
        return f'🔍 "{query}" 검색 결과 없음 (키워드 기반)'
    lines = [f'🔍 "{query}" 키워드 검색 (상위 {len(hits)}건)']
    for hit in hits[:5]:
        snippet = (hit.get("snippet", "") or "")[:120].replace("\n", " ")
        lines.append(f"\n📄 {hit.get('path', '')}\n{snippet}...")
    return "\n".join(lines)


# --- Backlog alert (P4 follow-up: nudge when agent jobs pile up) -------------

BACKLOG_DEFAULTS = {
    "enabled": True,
    "minPendingAgeHours": 6,
    "minPendingCount": 1,
    "cooldownHours": 6,
}
ALERT_STATE = ROOT / "memory-state" / "last-backlog-alert.json"
WEEKLY_DEFAULTS = {"enabled": True, "intervalDays": 7, "hour": 9}
WEEKLY_STATE = ROOT / "memory-state" / "last-weekly-digest.json"


def parse_iso(value: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


def job_age_hours(job: dict[str, Any], now: dt.datetime) -> float:
    created = parse_iso(job.get("created_at", ""))
    if not created:
        return 0.0
    return (now - created).total_seconds() / 3600.0


def format_backlog_alert(pending: list[dict[str, Any]], age_hours: float) -> str:
    by_type: dict[str, int] = {}
    for job in pending:
        by_type[job.get("type", "?")] = by_type.get(job.get("type", "?"), 0) + 1
    types = ", ".join(f"{k} {v}건" for k, v in sorted(by_type.items()))
    return (
        f"⏳ 미처리 작업 {len(pending)}건 (가장 오래된 건 {age_hours:.0f}시간 전)\n"
        f"유형: {types}\n"
        "에이전트 처리 또는 /lint 가 필요합니다."
    )


def format_weekly_digest(digest: dict[str, Any], review_count: int) -> str:
    raw = int(digest.get("raw_notes", 0))
    processed = int(digest.get("processed_markers", 0))
    pending = max(0, raw - processed)
    enr = digest.get("enrichment", {}) or {}
    by_type = digest.get("by_type", {})
    items = sorted(by_type.items(), key=lambda x: -x[1])
    top = ", ".join(f"{k} {v}" for k, v in items[:5])
    if len(items) > 5:
        top += f" 외 {len(items) - 5}종"
    lines = [
        f"📅 주간 Life Memory 회고 ({today()})",
        f"기록 {raw}건" + (f" · 미처리 {pending}건" if pending else " · 모두 정리됨 ✅"),
        f"링크 요약: 완료 {enr.get('summarized', 0)} · 대기 {enr.get('extracted', 0)}",
    ]
    if review_count > 0:
        lines.append(f"🔎 검토 대기 {review_count}건 — 운영봇에 \"검토할 거 뭐 있어?\"라고 물어보세요")
    lines.append(f"주요 분류: {top or '없음'}")
    dup = int(digest.get("duplicate_markers", 0))
    if dup > 0:
        lines.append(f"📎 중복 저장 {dup}건은 기존 노트에 합쳐졌어요")
    lines.append("")
    lines.append("운영봇에 \"이번 주 저장한 거 보여줘\"라고 물어보면 자세히 알려드려요.")
    return "\n".join(lines)


class Processor:
    def __init__(
        self,
        config_path: Path,
        config: dict[str, Any],
        *,
        rule_lint: bool = False,
        keyword_seek: bool = False,
        dry_run: bool = False,
        queue_dir: str = "",
        mem_run: Callable[..., dict[str, Any]] | None = None,
        jobs_run: Callable[..., dict[str, Any]] | None = None,
        send: Callable[[Any, str, Any], bool] | None = None,
    ) -> None:
        self.config_path = config_path
        self.config = config
        self.rule_lint = rule_lint
        self.keyword_seek = keyword_seek
        self.dry_run = dry_run
        self.queue_dir = queue_dir
        self.mem_run = mem_run or (lambda *a: default_mem_run(config_path, *a))
        if jobs_run:
            self.jobs_run = jobs_run
        else:
            prefix = ("--queue-dir", queue_dir) if queue_dir else ()
            self.jobs_run = lambda *a: default_jobs_run(*prefix, *a)
        token = tc.token_from(config)
        self.send = send or default_sender(token)
        telegram_cfg = config.get("telegram", {})
        allowed = telegram_cfg.get("allowedUserIds", [])
        self.alert_chat_id = telegram_cfg.get("adminChatId") or (allowed[0] if allowed else None)
        self.alert_cfg = {**BACKLOG_DEFAULTS, **config.get("jobs", {}).get("backlogAlert", {})}

    def active_types(self) -> set[str]:
        types = set(DETERMINISTIC_TYPES)
        if self.rule_lint:
            types.add("lint")
        if self.keyword_seek:
            types.add("seek")
        return types

    def pending_jobs(self) -> list[dict[str, Any]]:
        data = self.jobs_run("list", "--status", "pending")
        return data.get("jobs", [])

    def backlog_jobs(self) -> list[dict[str, Any]]:
        """Pending jobs this bridge does NOT auto-complete (left for the agent).

        These are the ones at risk of piling up unnoticed, so they drive the alert.
        """
        active = self.active_types()
        return [j for j in self.pending_jobs() if j.get("type") not in active]

    def maybe_alert(
        self,
        *,
        now: dt.datetime | None = None,
        read_state: Callable[[], str | None] | None = None,
        write_state: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        if not self.alert_cfg.get("enabled", True):
            return {"alert": "disabled"}
        now = now or now_local()
        read_state = read_state or self._read_alert_state
        write_state = write_state or self._write_alert_state

        pending = self.backlog_jobs()
        if not pending:
            return {"alert": "none"}
        oldest = min(pending, key=lambda j: j.get("created_at", ""))
        age = job_age_hours(oldest, now)
        if not (len(pending) >= self.alert_cfg["minPendingCount"] and age >= self.alert_cfg["minPendingAgeHours"]):
            return {"alert": "below_threshold", "pending": len(pending), "age_hours": round(age, 1)}

        last = parse_iso(read_state() or "")
        if last and (now - last).total_seconds() < self.alert_cfg["cooldownHours"] * 3600:
            return {"alert": "cooldown", "pending": len(pending)}

        chat_id = oldest.get("payload", {}).get("chat_id") or self.alert_chat_id
        if self.dry_run:
            return {"alert": "would_send", "pending": len(pending), "chat_id": chat_id}
        text = format_backlog_alert(pending, age)
        sent = self.send(chat_id, text, None) if chat_id else False
        if sent:
            write_state(now.isoformat(timespec="seconds"))
        return {"alert": "sent" if sent else "no_chat", "pending": len(pending)}

    @staticmethod
    def _read_alert_state() -> str | None:
        try:
            return json.loads(ALERT_STATE.read_text(encoding="utf-8")).get("last_alert")
        except Exception:
            return None

    @staticmethod
    def _write_alert_state(stamp: str) -> None:
        ALERT_STATE.parent.mkdir(parents=True, exist_ok=True)
        ALERT_STATE.write_text(json.dumps({"last_alert": stamp}), encoding="utf-8")

    def maybe_weekly_digest(
        self,
        *,
        now: dt.datetime | None = None,
        read_state: Callable[[], str | None] | None = None,
        write_state: Callable[[str], None] | None = None,
    ) -> dict[str, Any]:
        """Push a weekly recap to Telegram so the user actually revisits the vault.

        Fires at most once per intervalDays, only at/after `hour`. State + clock are
        injectable for tests. Best-effort: a send failure leaves state unwritten so
        it retries next run.
        """
        cfg = {**WEEKLY_DEFAULTS, **self.config.get("jobs", {}).get("weeklyDigest", {})}
        if not cfg.get("enabled", True):
            return {"weekly": "disabled"}
        now = now or now_local()
        read_state = read_state or self._read_weekly_state
        write_state = write_state or self._write_weekly_state
        if now.hour < int(cfg.get("hour", 9)):
            return {"weekly": "before_hour"}
        last = parse_iso(read_state() or "")
        if last and (now - last).total_seconds() < int(cfg.get("intervalDays", 7)) * 86400:
            return {"weekly": "interval_not_elapsed"}
        if not self.alert_chat_id:
            return {"weekly": "no_chat"}
        if self.dry_run:
            return {"weekly": "would_send", "chat_id": self.alert_chat_id}
        digest = self.mem_run("digest")
        try:
            review_count = int(self.mem_run("review", "list").get("count", 0))
        except Exception:  # noqa: BLE001
            review_count = 0
        text = format_weekly_digest(digest, review_count)
        sent = self.send(self.alert_chat_id, text, None)
        if sent:
            write_state(now.isoformat(timespec="seconds"))
        return {"weekly": "sent" if sent else "no_chat"}

    @staticmethod
    def _read_weekly_state() -> str | None:
        try:
            return json.loads(WEEKLY_STATE.read_text(encoding="utf-8")).get("last_weekly")
        except Exception:
            return None

    @staticmethod
    def _write_weekly_state(stamp: str) -> None:
        WEEKLY_STATE.parent.mkdir(parents=True, exist_ok=True)
        WEEKLY_STATE.write_text(json.dumps({"last_weekly": stamp}), encoding="utf-8")

    def process(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = job.get("id", "")
        job_type = job.get("type", "")
        if job.get("status") != "pending":
            return {"id": job_id, "action": "skip", "reason": f"status={job.get('status')}"}
        if job_type not in self.active_types():
            reason = "reserved_for_agent" if job_type in AGENT_TYPES else "unknown_type"
            return {"id": job_id, "action": "skip", "reason": reason, "type": job_type}

        if self.dry_run:
            return {"id": job_id, "action": "would_process", "type": job_type}

        payload = job.get("payload", {})
        chat_id = payload.get("chat_id")
        reply_to = payload.get("message_id")
        try:
            self.jobs_run("set-status", job_id, "running", "--note", "process_jobs.py started")
            reply, result = self._handle(job_type, payload)
        except Exception as exc:  # noqa: BLE001
            note = tc.short_error(exc)
            try:
                self.jobs_run("set-status", job_id, "failed", "--note", f"process_jobs.py: {note}")
            except Exception:
                pass
            return {"id": job_id, "action": "failed", "type": job_type, "error": note}

        result["processed_at"] = now_local().isoformat(timespec="seconds")
        result["processor"] = "process_jobs.py"
        self.jobs_run(
            "set-status", job_id, "done",
            "--note", "process_jobs.py completed",
            "--result-json", json.dumps(result, ensure_ascii=False),
        )
        acked = self.send(chat_id, reply, reply_to) if (reply and chat_id) else False
        return {"id": job_id, "action": "done", "type": job_type, "ack": acked}

    def _handle(self, job_type: str, payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        if job_type == "digest":
            data = self.mem_run("digest")
            queue_summary = None
            try:
                queue_summary = self.jobs_run("summary")
            except Exception:
                pass
            return format_digest(data, queue_summary), {"type": "digest", "digest": data}
        if job_type == "doctor":
            data = self.mem_run("doctor")
            return format_doctor(data), {"type": "doctor", "checks": data.get("checks", {})}
        if job_type == "lint":
            data = self.mem_run("lint")
            return format_lint(data), {"type": "lint", "lint_method": "rule_based", "processed": data.get("processed", 0)}
        if job_type == "seek":
            query = payload.get("query") or payload.get("raw_text") or ""
            data = self.mem_run("seek", query, "--limit", "5")
            return format_seek(query, data), {"type": "seek", "seek_method": "keyword", "hits": len(data.get("hits", []))}
        raise ValueError(f"unhandled job type: {job_type}")


def run(processor: Processor, limit: int = 0) -> list[dict[str, Any]]:
    jobs = processor.pending_jobs()
    jobs = sorted(jobs, key=lambda row: row.get("created_at", ""))
    if limit:
        jobs = jobs[:limit]
    return [processor.process(job) for job in jobs]


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending Life Memory jobs (deterministic bridge)")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--queue-dir", default="", help="Override job queue dir (default: jobs.py's own default)")
    parser.add_argument("--once", action="store_true", help="Process the current pending batch and exit (default)")
    parser.add_argument("--limit", type=int, default=0, help="Max jobs to process (0 = all pending)")
    parser.add_argument("--rule-lint", action="store_true", help="Also complete lint jobs via rule-based mem.py lint")
    parser.add_argument("--keyword-seek", action="store_true", help="Also complete seek jobs via keyword mem.py seek")
    parser.add_argument("--dry-run", action="store_true", help="Report what would be processed without changing anything")
    parser.add_argument("--no-alert", action="store_true", help="Skip the backlog alert check")
    args = parser.parse_args()

    tc.load_dotenv()
    config_path = Path(args.config).expanduser()
    config = tc.load_config(config_path)
    processor = Processor(
        config_path,
        config,
        rule_lint=args.rule_lint,
        keyword_seek=args.keyword_seek,
        dry_run=args.dry_run,
        queue_dir=args.queue_dir,
    )
    results = run(processor, limit=args.limit)
    alert = {"alert": "skipped"} if args.no_alert else processor.maybe_alert()
    weekly = {"weekly": "skipped"} if args.no_alert else processor.maybe_weekly_digest()
    print(json.dumps({"processed": results, "count": len(results),
                      "backlog_alert": alert, "weekly_digest": weekly}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
