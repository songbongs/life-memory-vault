#!/usr/bin/env python3
"""link-backlog — `## 관련`이 빈 옛 노트를 골라 준다 (읽기 전용).

왜 필요한가 (2026-10-28):
  관련 노트 연결(2026-10-27)은 그날 밤 다듬는 새 노트에만 붙는다. 그 전에 쌓인
  노트 650여 건은 연결 칸이 비어 있다. 밤마다 AI 잡이 이 명령으로 몇 건씩 받아
  「관련 노트 연결 규칙」대로 채운다 (`prompts/ai-lint.md` 「연결 백필 패스」).

규칙:
  - 대상: 마커의 `structured`가 `40_Notes/` 아래 실제로 있고, `duplicate_of`/`merged_into`가 아니며,
    `linked_at`(연결을 이미 시도함)이 없고, `## 관련`에 `[[링크]]`가 하나도 없는 노트.
  - 순서: 저장 시각(raw 파일명 앞 날짜) 최근 것부터.
"""

from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path
from typing import Any

NOTES = "40_Notes/"
RELATED = re.compile(r"^## 관련[ \t]*\n(.*?)(?=^## |\Z)", re.M | re.S)


def _nfc(s: str | None) -> str:
    return unicodedata.normalize("NFC", s or "")


def has_links(text: str) -> bool:
    m = RELATED.search(text)
    return bool(m and "[[" in m.group(1))


def collect(vault: Path, processed: Path) -> list[dict[str, str]]:
    seen: set[str] = set()
    out = []
    for mk in processed.glob("*.json"):
        try:
            data = json.loads(mk.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        rel = _nfc(data.get("structured"))
        if (not rel.startswith(NOTES) or rel in seen or data.get("duplicate_of")
                or data.get("merged_into") or data.get("linked_at")):
            continue
        note = vault / rel
        if not note.exists() or has_links(note.read_text(encoding="utf-8")):
            continue
        seen.add(rel)
        out.append({"note": rel, "marker": mk.name, "saved": Path(_nfc(data.get("raw"))).name[:17]})
    out.sort(key=lambda i: i["saved"], reverse=True)
    return out


def link_backlog(args: Any, config: dict[str, Any]) -> dict[str, Any]:
    vault = Path(config["memoryVault"]["vaultPath"]).expanduser()
    processed = vault / config.get("memoryVault", {}).get("processedFolder", "00_Inbox/Processed")
    items = collect(vault, processed)
    return {"total": len(items), "notes": items[: args.limit]}
