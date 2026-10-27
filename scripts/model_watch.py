#!/usr/bin/env python3
"""model-watch — 밤 작업 모델의 새 버전을 찾아 '바꿀까요?'라고 묻는다. 승인해야만 바꾼다.

왜 필요한가 (2026-10-19):
  설정에 `haiku`라고 별칭만 적어 뒀더니 Claude Code가 claude-haiku-4-5로 풀어서,
  최신 5.5가 나온 뒤에도 요약 작업이 구버전으로 돌고 있었다(밤 배치 세션 기록으로 확인).
  그래서 작업별 모델을 전체 ID(claude-haiku-5-5)로 고정하고, 버전만 따라가도록 한다.

규칙:
  - 모델 이름(haiku/sonnet/opus/fable)은 작업별로 고정. 같은 이름의 더 높은 버전만 후보.
  - 확인 주기는 7일(`--force`로 즉시). 공식 모델 목록 페이지를 읽기만 한다.
  - 새 버전은 한 번만 묻는다(state의 asked). 페이지를 못 읽으면 '감지 실패'를 7일에 한 번 알린다.
  - `--apply`는 사용자 승인 뒤에만 쓴다: 설정 백업 → 해당 작업 ID 교체 → pending_verify 기록.
  - 다음 밤 배치 뒤 세션 기록(jsonl)의 실제 모델로 적용 여부를 확인해 알린다.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import urllib.request
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "memory-config.json"
STATE = ROOT / "memory-state" / "model-watch.json"
MODELS_URL = "https://platform.claude.com/docs/en/models/overview"
SESSIONS = Path.home() / ".claude" / "projects" / ("-" + str(ROOT).strip("/").replace("/", "-"))
CHECK_DAYS = 7
MODEL_ID = re.compile(r"claude-(haiku|sonnet|opus|fable)-(\d+)(?:-(\d{1,2}))?(?:-\d{8})?\b")
ALIASES = {"haiku", "sonnet", "opus", "fable"}


def parse_model(value: str) -> tuple[str, tuple[int, int] | None]:
    """'claude-haiku-5-5' → ('haiku', (5, 5)); 'sonnet' → ('sonnet', None); 기타 → ('', None)."""
    v = (value or "").strip()
    if v in ALIASES:
        return v, None
    m = MODEL_ID.fullmatch(v) or MODEL_ID.match(v)
    if not m:
        return "", None
    return m.group(1), (int(m.group(2)), int(m.group(3) or 0))


def model_id(family: str, version: tuple[int, int]) -> str:
    return f"claude-{family}-{version[0]}-{version[1]}"


def latest_versions(page: str) -> dict[str, tuple[int, int]]:
    latest: dict[str, tuple[int, int]] = {}
    for m in MODEL_ID.finditer(page):
        fam, ver = m.group(1), (int(m.group(2)), int(m.group(3) or 0))
        if ver > latest.get(fam, (0, 0)):
            latest[fam] = ver
    return latest


def fetch_page(url: str = MODELS_URL) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "life-memory-model-watch"})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def load_state(path: Path = STATE) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state: dict[str, Any], path: Path = STATE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def job_models(config: dict[str, Any]) -> dict[str, str]:
    return dict(config.get("agent", {}).get("modelByJobType", {}).get("claude", {}))


def proposals(config: dict[str, Any], latest: dict[str, tuple[int, int]]) -> list[dict[str, Any]]:
    out = []
    for job, value in sorted(job_models(config).items()):
        fam, ver = parse_model(value)
        if not fam or fam not in latest:
            continue
        if ver is None or latest[fam] > ver:
            out.append({"job": job, "current": value, "proposed": model_id(fam, latest[fam]), "family": fam})
    return out


def check(config: dict[str, Any], send: Callable[[str], Any], *, force: bool = False,
          fetch: Callable[[], str] = fetch_page, today: dt.date | None = None,
          state_path: Path = STATE) -> dict[str, Any]:
    """주 1회 새 버전을 찾아 한 번만 묻는다. 설정은 바꾸지 않는다."""
    today = today or dt.date.today()
    state = load_state(state_path)
    last = state.get("last_check", "")
    if not force and last and (today - dt.date.fromisoformat(last)).days < CHECK_DAYS:
        return {"skipped": "checked recently", "last_check": last}
    try:
        latest = latest_versions(fetch())
    except Exception as exc:  # noqa: BLE001
        latest, error = {}, repr(exc)
    else:
        error = "" if latest else "no model ids on page"
    if error:
        last_fail = state.get("last_fail_alert", "")
        if not last_fail or (today - dt.date.fromisoformat(last_fail)).days >= CHECK_DAYS:
            send(f"⚠️ 모델 버전 감시: 공식 모델 목록을 못 읽었어요 ({error[:120]}).\n"
                 f"설정은 그대로예요. 주소: {MODELS_URL}")
            state["last_fail_alert"] = today.isoformat()
        save_state(state, state_path)
        return {"error": error}
    state["last_check"] = today.isoformat()
    state["latest"] = {f: model_id(f, v) for f, v in latest.items()}
    asked = state.setdefault("asked", {})
    new = [p for p in proposals(config, latest) if asked.get(p["job"]) != p["proposed"]]
    if new:
        lines = ["🆕 밤 작업 AI 모델에 새 버전이 있어요. 아직 안 바꿨어요."]
        lines += [f"- {p['job']}: {p['current']} → {p['proposed']}" for p in new]
        lines.append("바꾸려면 이 대화방에 '모델 변경 승인'이라고 보내 주세요. 일부만 바꾸려면 작업 이름도 적어 주세요.")
        send("\n".join(lines))
        for p in new:
            asked[p["job"]] = p["proposed"]
    save_state(state, state_path)
    return {"latest": state["latest"], "proposed": new}


def apply(jobs: list[str] | None, *, config_path: Path = CONFIG, state_path: Path = STATE,
          fetch: Callable[[], str] = fetch_page, dry_run: bool = False) -> dict[str, Any]:
    """사용자 승인 뒤에만 부른다. 설정 백업 후 해당 작업의 모델 ID만 바꾼다."""
    text = config_path.read_text(encoding="utf-8")
    config = json.loads(text)
    todo = proposals(config, latest_versions(fetch()))
    if jobs:
        todo = [p for p in todo if p["job"] in jobs]
    if dry_run or not todo:
        return {"would_change" if dry_run else "changed": todo}
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = config_path.with_name(f"{config_path.name}.bak-model-{stamp}")
    shutil.copy2(config_path, backup)
    models = config["agent"]["modelByJobType"]["claude"]
    for p in todo:
        models[p["job"]] = p["proposed"]
    tmp = config_path.with_name(f".{config_path.name}.tmp.{os.getpid()}")
    tmp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, config_path)
    state = load_state(state_path)
    pending = state.setdefault("pending_verify", {})
    for p in todo:
        pending[p["job"]] = {"model": p["proposed"], "previous": p["current"],
                             "since": dt.datetime.now().astimezone().isoformat(timespec="seconds")}
    save_state(state, state_path)
    return {"changed": todo, "backup": str(backup)}


def session_models(job: str, since: str, sessions: Path = SESSIONS) -> list[str]:
    """since 이후 세션 중 이 작업 종류를 처리한 세션들이 실제로 쓴 모델."""
    found = []
    cutoff = dt.datetime.fromisoformat(since).timestamp()
    marker = f"(type: {job})"
    for f in sessions.glob("*.jsonl"):
        if f.stat().st_mtime < cutoff:
            continue
        text = f.read_text(encoding="utf-8", errors="ignore")
        if marker not in text[:20000]:
            continue
        models = re.findall(r'"model":"(claude-[^"]+)"', text)
        if models:
            found.append(models[-1])
    return found


def verify_applied(send: Callable[[str], Any], *, state_path: Path = STATE,
                   sessions: Path = SESSIONS) -> dict[str, Any]:
    """바꾼 뒤 첫 밤 배치가 정말 새 모델로 돌았는지 확인하고 한 번 알린다."""
    state = load_state(state_path)
    pending = state.get("pending_verify", {})
    done, report = [], []
    for job, info in pending.items():
        used = session_models(job, info["since"], sessions)
        if not used:
            continue
        ok = all(m.startswith(info["model"]) for m in used)
        report.append(f"{'✅' if ok else '❌'} {job}: 설정 {info['model']} / 실제 {', '.join(sorted(set(used)))}")
        done.append(job)
    if report:
        send("🔁 모델 변경 확인 (변경 후 첫 밤 작업)\n" + "\n".join(report)
             + ("" if all(r.startswith("✅") for r in report)
                else "\n되돌리려면 memory-config.json.bak-model-* 백업을 쓰면 돼요."))
        for job in done:
            pending.pop(job, None)
        save_state(state, state_path)
    return {"verified": done, "waiting": sorted(pending)}


def model_watch(args: Any, config: dict[str, Any]) -> dict[str, Any]:
    if getattr(args, "apply", None):
        jobs = None if args.apply == ["all"] else args.apply
        return apply(jobs, dry_run=getattr(args, "dry_run", False))
    if getattr(args, "dry_run", False):
        return {"proposed": proposals(config, latest_versions(fetch_page()))}
    from telegram_ops_send import send_ops_alert
    return check(config, send_ops_alert, force=getattr(args, "force", False))
