#!/usr/bin/env python3
"""moc-sync — 목록(MOC)에 빠진 노트를 찾아 결정적으로 등록한다.

왜 필요한가 (2026-10-04):
  22:00 rule-based lint는 노트만 만들고 MOC는 안 건드린다(`mocs_updated: []`).
  MOC 등록은 23:00 AI lint 잡에 맡겼는데, 그 잡은 "N pending notes"로 들어오고
  그 사이 rule-based lint가 마커를 이미 써 버려서 AI가 "남은 일 0건"으로 끝내거나,
  agent 실패(exit 1)·launchd 정지(EX_CONFIG)로 아예 안 돌았다. 그 결과 Saves 노트
  163건이 Ideas-MOC에 없었다. 이 명령은 AI 성공 여부와 무관하게 매일 빈 곳을 메운다.

규칙:
  - 대상: 마커의 `structured`가 실제로 있고, `merged_into`/`duplicate_of`가 아닌 노트.
  - Ideas-MOC: `40_Notes/Saves/` 노트 전부(오래된 것 포함).
  - Life-Memory-MOC "최근 추가된 노트": 저장일이 최근 `recent_days`일 이내인 노트만.
  - 한 줄 설명: enrich 한국어 요약 첫 문장(최대 두 문장, 160자) → 요약이 아직 없고
    `wait_days` 이내면 다음 실행까지 기다림 → 그래도 없으면 raw 설명 첫 문장.
  - `--descriptions FILE`(JSON: 노트 경로 → 설명)로 설명을 직접 줄 수 있다.
  - 기본은 dry-run. `--apply`일 때만 쓴다. 기존 줄·섹션은 지우지 않고 추가만 한다.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import unicodedata
from pathlib import Path
from typing import Any

SAVES = "40_Notes/Saves/"
IDEAS_MOC = "90_System/Index/Ideas-MOC.md"
LIFE_MOC = "90_System/Index/Life-Memory-MOC.md"
IDEAS_ANCHOR = "\n## 프로젝트 아이디어"
ARCHIVE_EXPIRED = "40_Archive/링크만료"
LIFE_HEADER = "## 최근 추가된 노트\n"
WAIT_STATUSES = {"extracted", "pending", None}
MAX_DESC = 160
HANGUL = re.compile(r"[가-힣]")


def _nfc(s: str | None) -> str:
    return unicodedata.normalize("NFC", s or "")


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def _sentences(text: str) -> list[str]:
    text = re.sub(r"\s+", " ", text).strip()
    parts = re.split(r"(?<=[.!?。])\s+", text)
    return [p.strip() for p in parts if p.strip()]


def shorten(text: str, limit: int = MAX_DESC) -> str:
    """첫 문장(들어가면 두 번째 문장까지)을 limit 안에서 자른다. 끝 마침표는 뺀다."""
    sents = _sentences(text)
    if not sents:
        return ""
    out = sents[0]
    if len(sents) > 1 and len(out) + 1 + len(sents[1]) <= limit:
        out = f"{out} {sents[1]}"
    if len(out) > limit:
        cut = out[:limit]
        out = cut[: cut.rfind(" ")] if " " in cut else cut
        out = out.rstrip(",·— ") + "…"
    return out.rstrip(".。")


def summary_text(note_text: str) -> str:
    """enrich 블록 안의 한국어 요약 첫 문단."""
    m = re.search(r"<!-- enrich:begin[^>]*-->(.*?)<!-- enrich:end -->", note_text, re.S)
    if not m:
        return ""
    for para in re.split(r"\n\s*\n", m.group(1)):
        line = para.strip()
        if not line or line.startswith((">", "!", "<", "**핵심", "제안 태그", "-")):
            continue
        return line
    return ""


def raw_description(note_text: str) -> str:
    """'## Extracted note' 절에서 제목 줄 다음의 설명 문단."""
    m = re.search(r"## Extracted note\s*\n(.*?)(?:\n## |<!-- enrich:begin|\Z)", note_text, re.S)
    if not m:
        return ""
    paras = [p.strip() for p in re.split(r"\n\s*\n", m.group(1)) if p.strip()]
    for p in paras[1:] or paras:
        if p.startswith(("http", "⭐", "#", "![[")):
            continue
        return p
    return ""


def captured_date(marker: dict[str, Any]) -> dt.date | None:
    m = re.search(r"(\d{4}-\d{2}-\d{2})-\d{6}", _nfc(marker.get("raw")))
    if not m:
        return None
    return dt.date.fromisoformat(m.group(1))


def _link(note_rel: str) -> str:
    title = Path(note_rel).stem
    return f"[[{note_rel}|{title}]]"


def _in_text(note_rel: str, text: str) -> bool:
    stem = _nfc(note_rel[:-3] if note_rel.endswith(".md") else note_rel)
    return stem in text


def collect(vault: Path, processed: Path, today: dt.date, *, recent_days: int, wait_days: int,
            overrides: dict[str, str]) -> dict[str, Any]:
    ideas_text = _nfc((vault / IDEAS_MOC).read_text(encoding="utf-8")) if (vault / IDEAS_MOC).exists() else ""
    life_text = _nfc((vault / LIFE_MOC).read_text(encoding="utf-8")) if (vault / LIFE_MOC).exists() else ""
    seen: set[str] = set()
    ideas: list[dict[str, Any]] = []
    life: list[dict[str, Any]] = []
    waiting: list[str] = []
    for mk in sorted(processed.glob("*.json")):
        try:
            marker = json.loads(mk.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        note_rel = _nfc(marker.get("structured"))
        if not note_rel or marker.get("merged_into") or marker.get("duplicate_of") or note_rel in seen:
            continue
        note_path = vault / note_rel
        if not note_path.exists():
            continue
        seen.add(note_rel)
        day = captured_date(marker)
        archived = (vault / ARCHIVE_EXPIRED / Path(note_rel).name).exists()
        need_ideas = note_rel.startswith(SAVES) and not archived and not _in_text(note_rel, ideas_text)
        need_life = (day is not None and (today - day).days <= recent_days
                     and not _in_text(note_rel, life_text))
        if not (need_ideas or need_life):
            continue
        desc = overrides.get(note_rel, "")
        if not desc:
            text = note_path.read_text(encoding="utf-8")
            status = (marker.get("enrichment") or {}).get("status")
            summary = summary_text(text)
            # extracted 상태의 블록에는 요약 대신 원문 발췌(대개 영어)가 들어 있다 — 쓰지 않는다.
            # "요약 생략"이나 한글이 없는 요약도 설명으로 못 쓴다 → raw 설명으로 내려간다.
            usable = (summary and status not in ("extracted", "pending")
                      and "요약 생략" not in summary and HANGUL.search(summary))
            if usable:
                desc = shorten(summary)
            elif "http" in text and status in WAIT_STATUSES and day and (today - day).days < wait_days:
                waiting.append(note_rel)
                continue
            else:
                desc = shorten(raw_description(text))
        if desc and not HANGUL.search(desc) and len(desc) < 20:
            desc = ""  # "Attachments:" 같은 껍데기 줄은 설명이 아니다
        if not desc and not note_rel.startswith(SAVES):
            need_life = False  # 내용 없는 비-Saves 메모(빈 첨부 등)는 최근 목록에 올리지 않는다
            if not need_ideas:
                continue
        item = {"note": note_rel, "marker": mk.name, "date": day.isoformat() if day else "", "desc": desc}
        if need_ideas:
            ideas.append(item)
        if need_life:
            life.append(item)
    ideas.sort(key=lambda i: (i["date"], i["note"]))
    life.sort(key=lambda i: (i["date"], i["note"]), reverse=True)
    return {"ideas": ideas, "life": life, "waiting": waiting}


def line_for(item: dict[str, Any]) -> str:
    tail = f" ({item['date']})" if item["date"] else ""
    desc = f" — {item['desc']}" if item["desc"] else ""
    return f"- {_link(item['note'])}{desc}{tail}"


def apply(vault: Path, processed: Path, plan: dict[str, Any]) -> None:
    if plan["ideas"]:
        path = vault / IDEAS_MOC
        text = path.read_text(encoding="utf-8")
        block = "\n".join(line_for(i) for i in plan["ideas"])
        if "\n" + IDEAS_ANCHOR in text:  # 목록 끝의 빈 줄 앞에 이어 붙여 빈 줄이 끼지 않게 한다
            text = text.replace("\n" + IDEAS_ANCHOR, "\n" + block + "\n" + IDEAS_ANCHOR, 1)
        elif IDEAS_ANCHOR in text:
            text = text.replace(IDEAS_ANCHOR, "\n" + block + IDEAS_ANCHOR, 1)
        else:
            text = text.rstrip("\n") + "\n" + block + "\n"
        _atomic_write(path, text)
    if plan["life"]:
        path = vault / LIFE_MOC
        text = path.read_text(encoding="utf-8")
        block = "\n".join(line_for(i) for i in plan["life"]) + "\n"
        if LIFE_HEADER in text:
            text = text.replace(LIFE_HEADER, LIFE_HEADER + block, 1)
        else:
            text = text.rstrip("\n") + "\n\n" + LIFE_HEADER + block
        _atomic_write(path, text)
    touched: dict[str, list[str]] = {}
    for key, moc in (("ideas", IDEAS_MOC), ("life", LIFE_MOC)):
        for item in plan[key]:
            touched.setdefault(item["marker"], []).append(moc)
    for name, mocs in touched.items():
        mk = processed / name
        marker = json.loads(mk.read_text(encoding="utf-8"))
        cur = marker.get("mocs_updated") or []
        marker["mocs_updated"] = cur + [m for m in mocs if m not in cur]
        _atomic_write(mk, json.dumps(marker, ensure_ascii=False, indent=2))


def moc_sync(args: Any, config: dict[str, Any]) -> dict[str, Any]:
    vault = Path(config["memoryVault"]["vaultPath"]).expanduser()
    processed = vault / config.get("memoryVault", {}).get("processedFolder", "00_Inbox/Processed")
    overrides: dict[str, str] = {}
    if getattr(args, "descriptions", None):
        raw = json.loads(Path(args.descriptions).read_text(encoding="utf-8"))
        overrides = {_nfc(k): v for k, v in raw.items()}
    today = dt.date.fromisoformat(args.today) if getattr(args, "today", None) else dt.date.today()
    plan = collect(vault, processed, today, recent_days=args.recent_days, wait_days=args.wait_days,
                   overrides=overrides)
    if args.apply:
        apply(vault, processed, plan)
    return {
        "applied": bool(args.apply),
        "ideas_added": len(plan["ideas"]),
        "life_added": len(plan["life"]),
        "waiting_for_summary": len(plan["waiting"]),
        "no_description": sum(1 for i in plan["ideas"] + plan["life"] if not i["desc"]),
        "ideas": [line_for(i) for i in plan["ideas"]] if args.verbose else [],
        "life": [line_for(i) for i in plan["life"]] if args.verbose else [],
    }
