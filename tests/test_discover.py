#!/usr/bin/env python3
"""Tests for graph-layer F — discover.py tag-cluster scoring. Temp vault, no network.

Runs without pytest:  python3 tests/test_discover.py
"""

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import discover  # noqa: E402


def note(vault, rel, memory_type, tags, date, body, sensitivity="normal"):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---", f'memory_type: "{memory_type}"', f'sensitivity: "{sensitivity}"', f'updated_at: "{date}"']
    if tags:
        fm.append("tags:")
        fm += [f'  - "{t}"' for t in tags]
    fm.append("---")
    p.write_text("\n".join(fm) + "\n\n" + body + "\n", encoding="utf-8")
    return p


def setup():
    vault = Path(tempfile.mkdtemp()) / "vault"
    vault.mkdir()
    return vault, {"memoryVault": {"vaultPath": str(vault)}}


def run(config, **over):
    kwargs = {"min_cluster": 3, "max_cluster": 20, "top_n": 3}
    kwargs.update(over)
    return discover.discover_candidates(config, **kwargs)


def test_below_min_cluster_excluded():
    vault, cfg = setup()
    note(vault, "40_Notes/Saves/a.md", "save", ["niche"], "2026-06-01T10:00:00", "a")
    note(vault, "40_Notes/Saves/b.md", "save", ["niche"], "2026-06-08T10:00:00", "b")
    out = run(cfg)
    assert not any(c["tag"] == "niche" for c in out["all"])  # only 2 members, min is 3


def test_oversized_cluster_excluded_as_bucket():
    vault, cfg = setup()
    for i in range(25):
        note(vault, f"40_Notes/Saves/n{i}.md", "save", ["github"], f"2026-06-0{(i % 9) + 1}T10:00:00", "repo")
    out = run(cfg, max_cluster=20)
    assert not any(c["tag"] == "github" for c in out["all"])


def test_save_tag_always_excluded():
    vault, cfg = setup()
    for i in range(4):
        note(vault, f"40_Notes/Saves/n{i}.md", "save", ["save", "niche"], "2026-06-01T10:00:00", "x")
    out = run(cfg)
    assert not any(c["tag"] == "save" for c in out["all"])
    assert any(c["tag"] == "niche" for c in out["all"])


def test_private_cluster_excluded_entirely():
    vault, cfg = setup()
    note(vault, "40_Notes/Saves/a.md", "save", ["sensitive-topic"], "2026-06-01T10:00:00", "a")
    note(vault, "40_Notes/Saves/b.md", "save", ["sensitive-topic"], "2026-06-08T10:00:00", "b")
    note(vault, "40_Notes/Saves/c.md", "save", ["sensitive-topic"], "2026-06-15T10:00:00", "c", sensitivity="private")
    out = run(cfg)
    assert not any(c["tag"] == "sensitive-topic" for c in out["all"])


def test_type_diversity_raises_score():
    vault, cfg = setup()
    # cluster A: all same memory_type
    for i in range(3):
        note(vault, f"40_Notes/Saves/a{i}.md", "save", ["mono-type"], f"2026-06-0{i+1}T10:00:00", "x")
    # cluster B: spans two memory_types, same size/weeks
    note(vault, "40_Notes/Saves/b0.md", "save", ["cross-type"], "2026-06-01T10:00:00", "x")
    note(vault, "40_Notes/Saves/b1.md", "save", ["cross-type"], "2026-06-02T10:00:00", "x")
    note(vault, "30_Actions/Tasks/b2.md", "task", ["cross-type"], "2026-06-03T10:00:00", "x")
    out = run(cfg, top_n=10)
    by_tag = {c["tag"]: c for c in out["all"]}
    assert by_tag["cross-type"]["score"] > by_tag["mono-type"]["score"]


def test_emotion_words_raise_score():
    vault, cfg = setup()
    for i in range(3):
        note(vault, f"40_Notes/Saves/q{i}.md", "save", ["quiet-topic"], f"2026-06-0{i+1}T10:00:00", "그냥 저장")
    note(vault, "40_Notes/Saves/e0.md", "save", ["loud-topic"], "2026-06-01T10:00:00", "이거 반드시 써야함")
    note(vault, "40_Notes/Saves/e1.md", "save", ["loud-topic"], "2026-06-02T10:00:00", "완전 좋다")
    note(vault, "40_Notes/Saves/e2.md", "save", ["loud-topic"], "2026-06-03T10:00:00", "그냥 저장")
    out = run(cfg, top_n=10)
    by_tag = {c["tag"]: c for c in out["all"]}
    assert by_tag["loud-topic"]["score"] > by_tag["quiet-topic"]["score"]


def test_weeks_spanned_counts_distinct_iso_weeks():
    vault, cfg = setup()
    # three notes, same week
    note(vault, "40_Notes/Saves/s0.md", "save", ["same-week"], "2026-06-01T10:00:00", "x")
    note(vault, "40_Notes/Saves/s1.md", "save", ["same-week"], "2026-06-02T10:00:00", "x")
    note(vault, "40_Notes/Saves/s2.md", "save", ["same-week"], "2026-06-03T10:00:00", "x")
    out = run(cfg, top_n=10)
    by_tag = {c["tag"]: c for c in out["all"]}
    assert by_tag["same-week"]["weeks_spanned"] == 1


def test_top_n_caps_result_and_all_is_full_ranked_list():
    vault, cfg = setup()
    for tag_i in range(5):
        for i in range(3):
            note(vault, f"40_Notes/Saves/t{tag_i}_{i}.md", "save", [f"topic{tag_i}"], f"2026-06-0{i+1}T10:00:00", "x")
    out = run(cfg, top_n=2)
    assert len(out["top"]) == 2
    assert len(out["all"]) == 5


def test_no_frontmatter_notes_ignored():
    vault, cfg = setup()
    p = vault / "10_Daily" / "plain.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("no frontmatter here\n", encoding="utf-8")
    out = run(cfg)
    assert out["all"] == []


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as exc:
            failed += 1
            print(f"FAIL  {t.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"ERROR {t.__name__}: {exc!r}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(_run())
