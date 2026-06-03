#!/usr/bin/env python3
"""Tiny local web dashboard for Life Memory Vault.

Open http://127.0.0.1:8765 to start/stop the Telegram collector without typing
collector commands repeatedly.
"""

from __future__ import annotations

import html
import json
import os
import signal
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "memory-config.json"
ENV_FILE = ROOT / ".env"
STATE = ROOT / "memory-state"
PID_FILE = STATE / "telegram-collector.pid"
LOG_FILE = STATE / "telegram-collector.log"
COLLECTOR = ROOT / "scripts" / "telegram_collector.py"
MEM = ROOT / "scripts" / "mem.py"


def load_dotenv(path: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def load_config() -> dict[str, Any]:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def token_configured() -> bool:
    config = load_config()
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") or load_dotenv().get("TELEGRAM_BOT_TOKEN") or config.get("telegram", {}).get("botToken"))


def pid_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def current_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
    except ValueError:
        return None
    if pid_running(pid):
        return pid
    PID_FILE.unlink(missing_ok=True)
    return None


def start_collector() -> str:
    pid = current_pid()
    if pid:
        return f"이미 실행 중입니다. PID {pid}"
    if not token_configured():
        return ".env 또는 memory-config.json에 TELEGRAM_BOT_TOKEN이 없습니다."
    STATE.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.update(load_dotenv())
    log = LOG_FILE.open("a", encoding="utf-8")
    process = subprocess.Popen(
        [sys.executable, "-B", str(COLLECTOR), "--loop"],
        cwd=str(ROOT),
        stdout=log,
        stderr=subprocess.STDOUT,
        env=env,
        start_new_session=True,
    )
    PID_FILE.write_text(str(process.pid), encoding="utf-8")
    return f"수집기를 켰습니다. PID {process.pid}"


def stop_collector() -> str:
    pid = current_pid()
    if not pid:
        return "실행 중인 수집기가 없습니다."
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as exc:
        return f"종료 요청 실패: {exc}"
    PID_FILE.unlink(missing_ok=True)
    return "수집기를 껐습니다."


JOBS = ROOT / "scripts" / "jobs.py"


def run_mem(command: str) -> str:
    result = subprocess.run(
        [sys.executable, "-B", str(MEM), command],
        cwd=str(ROOT),
        text=True,
        capture_output=True,
        check=False,
    )
    return (result.stdout or result.stderr or "").strip()


def run_jobs(command: str) -> dict[str, Any]:
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(JOBS)] + command.split(),
            cwd=str(ROOT),
            text=True,
            capture_output=True,
            check=False,
        )
        return json.loads(result.stdout or "{}")
    except Exception:
        return {}


def enqueue_ai_lint() -> str:
    try:
        result = subprocess.run(
            [sys.executable, "-B", str(JOBS), "add", "lint",
             "--text", "manual AI lint request from admin dashboard",
             "--adapter", "codex", "--source", "admin"],
            cwd=str(ROOT), text=True, capture_output=True, check=True,
        )
        data = json.loads(result.stdout)
        return f"AI lint job 등록됨: {data.get('id')} — Codex/Claude에게 처리 요청하세요."
    except Exception as exc:
        return f"AI lint job 등록 실패: {exc}"


def tail_log(lines: int = 60) -> str:
    if not LOG_FILE.exists():
        return "아직 로그가 없습니다."
    content = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(content[-lines:])


def status() -> dict[str, Any]:
    pid = current_pid()
    digest = run_mem("digest")
    job_summary = run_jobs("summary")
    return {
        "running": bool(pid),
        "pid": pid,
        "token": token_configured(),
        "digest": digest,
        "job_summary": job_summary,
    }


def _job_counts_html(job_summary: dict[str, Any]) -> str:
    counts = job_summary.get("counts", {})
    if not counts:
        return "<p>큐에 작업이 없습니다.</p>"
    rows = []
    for job_type, statuses in sorted(counts.items()):
        pending = statuses.get("pending", 0)
        running = statuses.get("running", 0)
        done = statuses.get("done", 0)
        failed = statuses.get("failed", 0)
        failed_html = f' <span style="color:#c33">실패 {failed}건</span>' if failed else ""
        rows.append(
            f"<tr><td><b>{html.escape(job_type)}</b></td>"
            f"<td>대기 {pending}</td><td>진행 {running}</td>"
            f"<td>완료 {done}</td><td>{failed_html}</td></tr>"
        )
    return f'<table style="border-collapse:collapse;width:100%">{"".join(rows)}</table>'


def page(message: str = "") -> bytes:
    stat = status()
    running = "ON" if stat["running"] else "OFF"
    color = "#0f8f46" if stat["running"] else "#a33"
    token = "설정됨" if stat["token"] else "없음"
    job_html = _job_counts_html(stat.get("job_summary", {}))
    body = f"""<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Life Memory 관리자</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 32px; max-width: 960px; }}
    .status {{ font-size: 48px; font-weight: 800; color: {color}; margin: 12px 0; }}
    .row {{ display: flex; gap: 12px; flex-wrap: wrap; margin: 20px 0; }}
    button {{ font-size: 16px; padding: 12px 18px; border-radius: 8px; border: 1px solid #bbb; background: #f7f7f7; cursor: pointer; }}
    button.primary {{ background: #111; color: white; }}
    button.ai {{ background: #1a5fb4; color: white; border-color: #1a5fb4; }}
    .box {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px; margin: 16px 0; background: #fafafa; }}
    pre {{ white-space: pre-wrap; word-break: break-word; font-size: 13px; }}
    .msg {{ color: #075; font-weight: 700; padding: 8px 0; }}
    table td {{ padding: 4px 12px; }}
    .hint {{ font-size: 13px; color: #777; margin-top: 6px; }}
  </style>
</head>
<body>
  <h1>Life Memory 관리자</h1>
  <div class="box">
    <div>Telegram 수집기 상태</div>
    <div class="status">{running}</div>
    <div>PID: {html.escape(str(stat["pid"] or "-"))} &nbsp;|&nbsp; Bot Token: {token}</div>
  </div>
  {'<p class="msg">' + html.escape(message) + '</p>' if message else ''}
  <div class="row">
    <form method="post" action="/start"><button class="primary">수집기 켜기</button></form>
    <form method="post" action="/stop"><button>수집기 끄기</button></form>
    <form method="get" action="/"><button>새로고침</button></form>
  </div>
  <div class="box">
    <h2>정리 (Lint)</h2>
    <div class="row">
      <form method="post" action="/lint-rule">
        <button>Rule-based 즉시 정리</button>
      </form>
      <form method="post" action="/lint-ai">
        <button class="ai">AI Lint Job 등록</button>
      </form>
    </div>
    <p class="hint">
      <b>Rule-based 즉시 정리</b>: 키워드 기반 분류. 즉시 실행, AI 없음.<br>
      <b>AI Lint Job 등록</b>: job queue에 등록. Codex/Claude Code에서 "life-memory pending 처리해줘"로 실행.
    </p>
  </div>
  <div class="box">
    <h2>Job Queue 현황</h2>
    {job_html}
  </div>
  <div class="box">
    <h2>현재 기록 상태</h2>
    <pre>{html.escape(stat["digest"])}</pre>
  </div>
  <div class="box">
    <h2>최근 수집기 로그</h2>
    <pre>{html.escape(tail_log())}</pre>
  </div>
  <div class="box">
    <h2>주의</h2>
    <p>기존 터미널에서 <code>telegram_collector.py --loop</code>를 직접 실행 중이라면 먼저 Ctrl+C로 끄고 이 화면을 사용하세요. 수집기는 한 대에서 하나만 실행하는 것이 좋습니다.</p>
  </div>
</body>
</html>"""
    return body.encode("utf-8")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.respond(page())

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        _ = parse_qs(self.rfile.read(length).decode("utf-8")) if length else {}
        if self.path == "/start":
            message = start_collector()
        elif self.path == "/stop":
            message = stop_collector()
        elif self.path == "/lint-rule":
            message = run_mem("lint")
        elif self.path == "/lint-ai":
            message = enqueue_ai_lint()
        elif self.path == "/lint":
            message = run_mem("lint")
        else:
            message = "알 수 없는 요청입니다."
        self.respond(page(message))

    def respond(self, content: bytes) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    host = "127.0.0.1"
    port = 8765
    print(f"Life Memory 관리자: http://{host}:{port}")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()
