#!/usr/bin/env python3
"""Curator-style "discovered connections" candidate detection (graph-layer F).

Deterministic half of the discover pipeline: scan the vault, group structured
notes by shared frontmatter tag, and score each group on how likely it is to be
a genuine, worth-surfacing pattern rather than a coincidence or a bare
classification bucket (see docs/graph-layer-plan.md section F).

This module only *scores and lists* candidates — it never writes anything and
never decides what to tell the user. Turning a scored tag-group into an actual
Korean observation (and verifying the notes are *really* thematically related,
not just tag-adjacent) is the AI's job, done by following prompts/ai-discover.md
against this module's JSON output.

Design invariants:
- Read-only. No file is created, edited, or deleted here.
- Uses only data lint/enrich already wrote (frontmatter tags, memory_type,
  sensitivity, dates) — no new infrastructure.
- A tag group whose members include any `sensitivity: private` note is dropped
  entirely, never surfaced (section F-4 privacy rule).

Tested via a synthetic vault directory (no network, no real vault). See
tests/test_discover.py.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mem  # noqa: E402

# Tags carrying no topical signal — every `save` note has this, so it groups
# everything and nothing. Add here, not in scoring, so it's a single visible list.
EXCLUDE_TAGS = {"save"}

# Words that, found verbatim in a note's own text, signal the user reacted
# strongly rather than just bookmarking. Kept short and literal on purpose —
# this is a real-text-match signal, not sentiment inference.
EMOTION_WORDS = ["반드시", "완전", "대박", "짱", "레전드", "무조건", "꼭 써", "꼭 써야"]


def _iso_week(date_str: str) -> tuple[int, int] | None:
    d = (date_str or "")[:10]
    if not d:
        return None
    try:
        year, week, _ = dt.date.fromisoformat(d).isocalendar()
        return (year, week)
    except ValueError:
        return None


def _load_notes(vault: Path) -> list[dict[str, Any]]:
    notes = []
    for path in vault.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        meta, _body = mem.parse_frontmatter(text)
        if not meta:
            continue
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [tags]
        if not tags:
            continue
        notes.append({
            "path": mem.relative_to_vault(path, vault),
            "tags": [t.lower() for t in tags],
            "memory_type": (meta.get("memory_type") or "").strip('"'),
            "sensitivity": (meta.get("sensitivity") or "normal").strip('"'),
            "date": meta.get("updated_at") or meta.get("captured_at") or "",
            "text": text,
        })
    return notes


def discover_candidates(
    config: dict[str, Any],
    *,
    min_cluster: int = 3,
    max_cluster: int = 20,
    top_n: int = 3,
    notes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Group notes by tag, score each group, return top_n plus the full ranked list.

    `notes` is injectable for tests (skips the filesystem scan).

    `max_cluster` excludes tag-groups above this size outright: a tag that ~half
    the vault carries (`github`, `coding`, ...) is a classification bucket, not a
    discovery — "you have 75 GitHub bookmarks" isn't an insight, it's the folder
    listing. Real curated finds are the tight, specific groups.
    """
    vault = mem.vault_path(config)
    if notes is None:
        notes = _load_notes(vault)

    tag_map: dict[str, list[dict[str, Any]]] = {}
    for note in notes:
        for tag in note["tags"]:
            if tag in EXCLUDE_TAGS:
                continue
            tag_map.setdefault(tag, []).append(note)

    all_candidates = []
    for tag, members in tag_map.items():
        if len(members) < min_cluster or len(members) > max_cluster:
            continue
        if any(m["sensitivity"] == "private" for m in members):
            continue

        weeks = {w for m in members if (w := _iso_week(m["date"])) is not None}
        types = {m["memory_type"] for m in members if m["memory_type"]}
        emotion_hits = sum(1 for m in members if any(w in m["text"] for w in EMOTION_WORDS))

        score = (
            len(weeks) * 3
            + (5 if len(types) > 1 else 0)
            + min(emotion_hits, 3) * 2
            + min(len(members), 3)
        )
        all_candidates.append({
            "tag": tag,
            "count": len(members),
            "weeks_spanned": len(weeks),
            "type_diversity": len(types),
            "emotion_hits": emotion_hits,
            "score": score,
            "notes": [
                {"path": m["path"], "date": m["date"], "memory_type": m["memory_type"]}
                for m in members
            ],
        })

    all_candidates.sort(key=lambda c: -c["score"])
    return {
        "top": all_candidates[:top_n],
        "all": all_candidates,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Score tag-clusters as candidate 'discovered connections'")
    parser.add_argument("--config", default=str(mem.DEFAULT_CONFIG))
    parser.add_argument("--min-cluster", type=int, default=3)
    parser.add_argument("--max-cluster", type=int, default=20)
    parser.add_argument("--top-n", type=int, default=3)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    config = mem.load_config(Path(args.config).expanduser())
    result = discover_candidates(config, min_cluster=args.min_cluster, max_cluster=args.max_cluster, top_n=args.top_n)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
