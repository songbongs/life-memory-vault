#!/usr/bin/env python3
"""Tests for link_backlog (mem.py link-backlog).

빈 `## 관련`만 고르는지, 시도한 노트·중복 마커·40_Notes 밖을 빼는지, 최근 것부터인지 확인한다.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import link_backlog  # noqa: E402


def _note(vault, name, body, ts, folder="40_Notes/Saves", **extra):
    rel = f"{folder}/{name}.md"
    (vault / rel).parent.mkdir(parents=True, exist_ok=True)
    (vault / rel).write_text(f"# {name}\n\n본문\n\n{body}", encoding="utf-8")
    marker = {"raw": f"00_Inbox/Raw/2026/10/{ts}-{name}.md", "structured": rel, **extra}
    (vault / "00_Inbox/Processed" / f"{name}.json").write_text(json.dumps(marker), encoding="utf-8")


def test_picks_only_empty_related_newest_first():
    vault = Path(tempfile.mkdtemp()) / "vault"
    (vault / "00_Inbox/Processed").mkdir(parents=True)
    _note(vault, "old-empty", "## 관련\n\n## 메모\n[[다른 섹션 링크]]\n", "2026-09-01-120000")
    _note(vault, "new-nosection", "", "2026-10-20-120000")
    _note(vault, "linked", "## 관련\n- [[40_Notes/Saves/x]] — 이유\n", "2026-10-21-120000")
    _note(vault, "tried", "", "2026-10-22-120000", linked_at="2026-10-28T23:10:00+09:00")
    _note(vault, "dup", "", "2026-10-23-120000", duplicate_of="x.json")
    _note(vault, "task", "", "2026-10-24-120000", folder="30_Actions/Tasks")
    cfg = {"memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed"}}
    res = link_backlog.link_backlog(argparse.Namespace(limit=1), cfg)
    assert res["total"] == 2, res
    assert [n["note"] for n in res["notes"]] == ["40_Notes/Saves/new-nosection.md"], res


if __name__ == "__main__":
    test_picks_only_empty_related_newest_first()
    print("ok")
