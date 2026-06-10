#!/usr/bin/env python3
"""End-to-end integration for the learning loop (③d-5).

Ties the whole chain in a temp vault (no real vault/network):
  review resolve ×2 (same signal) -> rule promoted active
  -> mem.load_active_rules (the lint_vault wiring) loads it
  -> classify() auto-classifies a new, previously-ambiguous note.

Runs without pytest:  python3 tests/test_learning_e2e.py
"""

import argparse
import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402


def setup(enabled=True):
    d = Path(tempfile.mkdtemp())
    vault = d / "vault"
    (vault / "00_Inbox/Review").mkdir(parents=True)
    cfg_path = d / "config.json"
    cfg = {
        "memoryVault": {"vaultPath": str(vault)},
        "learning": {"enabled": enabled, "promoteThreshold": 2,
                     "rulesPath": "90_System/Rules/learned-rules.json",
                     "mirrorPath": "90_System/Rules/Learned Rules.md"},
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return vault, cfg, cfg_path


def make_review(vault, name, source):
    p = vault / "00_Inbox/Review" / name
    p.write_text(
        f'---\nreview_type: "lint_uncertain"\nsource_raw: "[[{source}]]"\n'
        f'suggested_folder: "20_Records/Maintenance"\n---\n\n욕실 샤워헤드 관련 메모\n',
        encoding="utf-8",
    )
    return p


def resolve(cfg, cfg_path, filename):
    args = argparse.Namespace(file=filename, type="maintenance", signal="샤워헤드", folder="", title="")
    with contextlib.redirect_stdout(io.StringIO()):
        mem.review_resolve(args, cfg, cfg_path)


def test_full_loop_resolve_promote_load_classify():
    vault, cfg, cfg_path = setup(enabled=True)
    r1 = make_review(vault, "review-1.md", "00_Inbox/Raw/2026/06/raw1")
    r2 = make_review(vault, "review-2.md", "00_Inbox/Raw/2026/06/raw2")

    # before learning: a bare "샤워헤드" note has no maintenance keyword -> not maintenance
    assert mem.classify("샤워헤드 어쩌고", {})["memory_type"] != "maintenance"

    resolve(cfg, cfg_path, r1.name)   # 1st confirmation -> candidate
    args = argparse.Namespace(config=str(cfg_path))
    assert mem.load_active_rules(args, cfg) == []   # not promoted yet

    resolve(cfg, cfg_path, r2.name)   # 2nd distinct source -> active
    active = mem.load_active_rules(args, cfg)
    assert any(r["signal"] == "샤워헤드" and r["type"] == "maintenance" for r in active), active

    # after learning: the same bare note is now auto-classified via the loaded rules
    r = mem.classify("샤워헤드 어쩌고", {}, active)
    assert r["memory_type"] == "maintenance"
    assert r["confidence"] == "high" and r["needs_review"] is False


def test_learning_disabled_loads_no_rules():
    vault, cfg, cfg_path = setup(enabled=False)
    make_review(vault, "review-1.md", "raw1")
    make_review(vault, "review-2.md", "raw2")
    resolve(cfg, cfg_path, "review-1.md")
    resolve(cfg, cfg_path, "review-2.md")
    # rule exists in the store, but load_active_rules respects learning.enabled=false
    args = argparse.Namespace(config=str(cfg_path))
    assert mem.load_active_rules(args, cfg) == []


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
