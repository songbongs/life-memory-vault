#!/usr/bin/env python3
"""Headless agent bridge for AI-only Life Memory jobs (P4-AI / ③a core).

`process_jobs.py` deliberately leaves lint (Wiki-layer), repair, and AI-seek
jobs pending for a subscription agent. This script invokes that agent headlessly
(default: Claude Code `claude -p`, configurable to codex via agent.commands) to
process those jobs by following the in-repo prompt prompts/process-pending-jobs.md.

③a scope = side-effect-free core only:
  - select pending AI jobs
  - build the agent command from the config template
  - gate / mark running / decide the terminal status from the agent exit code
  - --dry-run prints the exact command without running anything
The real agent call (subprocess) is injectable so it can be faked in tests and
exercised manually before any scheduled/unattended activation.

Autonomy contract (passed to the agent in the prompt): non-interactive, never
ask the user; ambiguous items go to 00_Inbox/Review with a reason; raw notes are
never edited. The agent marks the job done/failed itself; this script only marks
`running` up front and finalizes as a safety net if the agent exits abnormally.
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
JOBS = ROOT / "scripts" / "jobs.py"
PROMPT_FILE = "prompts/process-pending-jobs.md"

AGENT_DEFAULTS: dict[str, Any] = {
    "default": "claude",
    "aiJobTypes": ["lint", "repair", "seek", "enrich", "media-enrich", "discover"],
    "commands": {
        "claude": ["claude", "-p", "{prompt}", "--permission-mode", "acceptEdits",
                   "--allowedTools", "Bash", "Read", "Write", "Edit", "Grep", "Glob"],
        "codex": ["codex", "exec", "{prompt}"],
    },
}
TERMINAL_STATUSES = {"done", "failed", "cancelled"}


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def default_jobs_run(*args: str) -> dict[str, Any]:
    result = subprocess.run([sys.executable, str(JOBS), *args], cwd=str(ROOT), text=True, capture_output=True, check=True)
    return json.loads(result.stdout or "{}")


def default_agent_run(cmd: list[str]) -> int:
    """Run the agent command in the project root and return its exit code."""
    return subprocess.run(cmd, cwd=str(ROOT)).returncode


def build_prompt(job_id: str, job_type: str) -> str:
    return (
        "You are processing the Life Memory job queue in a NON-INTERACTIVE session. "
        f"Project root: {ROOT}. Read and follow {PROMPT_FILE} for HOW to process jobs. "
        f"Process ONLY the pending job whose id is {job_id} (type: {job_type}). "
        "Hard rules: never ask the user anything; if any classification or merge is "
        "ambiguous, leave the item in 00_Inbox/Review with a one-line reason and do NOT "
        "guess; never edit or delete raw notes in 00_Inbox/Raw; preserve source_raw links. "
        "When finished, mark the job done (or failed with a reason) via "
        "scripts/jobs.py set-status, and send the Telegram reply if the job has a chat_id."
    )


def build_command(template: list[str], prompt: str, model: str = "") -> list[str]:
    cmd = [part.replace("{prompt}", prompt) for part in template]
    if model:
        # claude: alias (haiku/sonnet/opus) = latest in tier; codex: -m/--model.
        cmd += ["--model", model]
    return cmd


def terminal_action(exit_code: int, post_status: str) -> tuple[str | None, str | None]:
    """Decide how this script should finalize a job after the agent run.

    The agent is expected to set done/failed itself. This is only a safety net.
    """
    if post_status in TERMINAL_STATUSES:
        return None, None  # agent already finalized; respect it
    if exit_code == 0:
        return "done", "agent finished; auto-finalized by process_ai_jobs"
    return "failed", f"agent exited with code {exit_code}"


def notify_failures(config: dict[str, Any], failed: list[dict[str, Any]], send=None) -> bool:
    """Tell the user (via the capture bot) when an unattended batch had failures.

    Most likely cause is a logged-out Claude Code session (401), which the user
    must notice to re-login — otherwise jobs keep failing silently. `send` is
    injectable for tests. Returns True if a message was sent.
    """
    if not failed:
        return False
    import telegram_collector as tc
    token = tc.token_from(config)
    allowed = config.get("telegram", {}).get("allowedUserIds", [])
    if not token or not allowed:
        return False
    chat_id = failed[0].get("chat_id") or allowed[0]
    types = ", ".join(sorted({f.get("type", "?") for f in failed}))
    msg = (
        f"⚠️ 예약 작업 실패 ({len(failed)}건: {types})\n"
        "Claude 로그인이 풀렸을 수 있습니다. Claude Code 채널 터미널에서 재로그인을 확인해주세요.\n"
        "작업 대상은 보존돼 있어, 재로그인 후 다음 배치에서 자동으로 재처리됩니다."
    )
    send = send or tc.send_message
    try:
        send(token, int(chat_id), msg)
        return True
    except Exception:  # noqa: BLE001
        return False


class AiProcessor:
    def __init__(
        self,
        config_path: Path,
        config: dict[str, Any],
        *,
        agent: str = "",
        dry_run: bool = False,
        queue_dir: str = "",
        agent_run: Callable[[list[str]], int] | None = None,
        jobs_run: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self.config_path = config_path
        self.config = config
        self.dry_run = dry_run
        self.queue_dir = queue_dir
        acfg = config.get("agent", {})
        self.agent_name = agent or acfg.get("default", AGENT_DEFAULTS["default"])
        self.commands = acfg.get("commands", AGENT_DEFAULTS["commands"])
        self.ai_types = set(acfg.get("aiJobTypes", AGENT_DEFAULTS["aiJobTypes"]))
        self.model_by_job = acfg.get("modelByJobType", {}).get(self.agent_name, {})
        self.template = self.commands.get(self.agent_name)
        if not self.template:
            raise SystemExit(f"No agent command template for '{self.agent_name}'. Set agent.commands.{self.agent_name} in {config_path}.")
        self.agent_run = agent_run or default_agent_run
        if jobs_run:
            self.jobs_run = jobs_run
        else:
            prefix = ("--queue-dir", queue_dir) if queue_dir else ()
            self.jobs_run = lambda *a: default_jobs_run(*prefix, *a)

    def pending_ai_jobs(self) -> list[dict[str, Any]]:
        jobs = self.jobs_run("list", "--status", "pending").get("jobs", [])
        jobs = [j for j in jobs if j.get("type") in self.ai_types]
        return sorted(jobs, key=lambda j: j.get("created_at", ""))

    def _status_of(self, job_id: str) -> str:
        for job in self.jobs_run("list").get("jobs", []):
            if job.get("id") == job_id:
                return job.get("status", "")
        return ""

    def process(self, job: dict[str, Any]) -> dict[str, Any]:
        job_id = job.get("id", "")
        job_type = job.get("type", "")
        if job.get("status") != "pending":
            return {"id": job_id, "action": "skip", "reason": f"status={job.get('status')}"}
        if job_type not in self.ai_types:
            return {"id": job_id, "action": "skip", "reason": "not_ai_type", "type": job_type}

        prompt = build_prompt(job_id, job_type)
        # job-type mapping first; else the agent's "default" entry; else "" (agent's own default model).
        model = self.model_by_job.get(job_type) or self.model_by_job.get("default", "")
        command = build_command(self.template, prompt, model)
        if self.dry_run:
            return {"id": job_id, "action": "would_run", "type": job_type, "agent": self.agent_name, "model": model or "(default)", "command": command}

        self.jobs_run("set-status", job_id, "running", "--note", f"process_ai_jobs.py -> {self.agent_name}{' ' + model if model else ''}")
        exit_code = self.agent_run(command)
        post = self._status_of(job_id)
        status, note = terminal_action(exit_code, post)
        if status:
            self.jobs_run("set-status", job_id, status, "--note", note or "")
            final = status
        else:
            final = post
        return {"id": job_id, "action": "ran", "type": job_type, "agent": self.agent_name, "model": model or "(default)", "exit_code": exit_code, "final_status": final}

    def run(self, limit: int = 0) -> list[dict[str, Any]]:
        jobs = self.pending_ai_jobs()
        if limit:
            jobs = jobs[:limit]
        return [self.process(job) for job in jobs]


def main() -> None:
    parser = argparse.ArgumentParser(description="Process pending AI Life Memory jobs via a headless agent")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG))
    parser.add_argument("--queue-dir", default="")
    parser.add_argument("--agent", default="", help="Override agent name (default: agent.default in config)")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--once", action="store_true", help="Process current pending AI batch and exit (default)")
    parser.add_argument("--dry-run", action="store_true", help="Print the agent commands without running them")
    args = parser.parse_args()

    config_path = Path(args.config).expanduser()
    with config_path.open("r", encoding="utf-8") as handle:
        config = json.load(handle)
    processor = AiProcessor(
        config_path, config,
        agent=args.agent, dry_run=args.dry_run, queue_dir=args.queue_dir,
    )
    results = processor.run(limit=args.limit)
    if not args.dry_run:
        failed = [r for r in results if r.get("final_status") == "failed"]
        if failed:
            notify_failures(config, failed)
    print(json.dumps({"agent": processor.agent_name, "processed": results, "count": len(results)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
