#!/usr/bin/env python3
"""Tests for rules.py — learned-rules store (③d-1).

Uses temp files, no vault/network. Runs without pytest:  python3 tests/test_rules.py
"""

import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import rules as R  # noqa: E402


def store(threshold=2):
    d = tempfile.mkdtemp()
    return R.RuleStore(Path(d) / "learned-rules.json", Path(d) / "Learned Rules.md", threshold)


# --- normalization ---

def test_normalize_signal():
    assert R.normalize_signal("  샤워헤드 ") == "샤워헤드"
    assert R.normalize_signal("LED  Bulb") == "led bulb"


# --- empty store ---

def test_empty_store_has_no_active_rules():
    s = store()
    assert s.active_rules() == []
    assert s.rules() == []


# --- promotion threshold (2) ---

def test_one_confirmation_is_candidate():
    s = store(threshold=2)
    s.add_decision("샤워헤드", "maintenance", "20_Records/Maintenance", source_raw="[[raw1]]", by="ai_repair")
    r = s.rules()[0]
    assert r["status"] == "candidate" and r["confirmations"] == 1
    assert s.active_rules() == []


def test_two_distinct_sources_promote_to_active():
    s = store(threshold=2)
    s.add_decision("샤워헤드", "maintenance", "20_Records/Maintenance", source_raw="[[raw1]]")
    s.add_decision("샤워헤드", "maintenance", "20_Records/Maintenance", source_raw="[[raw2]]")
    active = s.active_rules()
    assert len(active) == 1
    assert active[0] == {"signal": "샤워헤드", "type": "maintenance", "folder": "20_Records/Maintenance"}


def test_duplicate_source_does_not_double_count():
    s = store(threshold=2)
    s.add_decision("와이퍼", "maintenance", source_raw="[[raw1]]")
    s.add_decision("와이퍼", "maintenance", source_raw="[[raw1]]")  # same source
    r = s.rules()[0]
    assert r["confirmations"] == 1 and r["status"] == "candidate"


# --- contradiction blocks auto-classification ---

def test_conflicting_types_block():
    s = store(threshold=2)
    s.add_decision("중요", "task", source_raw="[[r1]]")
    s.add_decision("중요", "journal", source_raw="[[r2]]")
    r = s.rules()[0]
    assert r["status"] == "blocked" and r["contradicted"] is True
    assert s.active_rules() == []  # never auto-classify a contradicted signal


# --- remove / revoke ---

def test_remove_revokes_rule():
    s = store(threshold=2)
    s.add_decision("샤워헤드", "maintenance", source_raw="[[r1]]")
    s.add_decision("샤워헤드", "maintenance", source_raw="[[r2]]")
    assert s.active_rules()
    removed = s.remove("샤워헤드")
    assert removed == 2
    assert s.active_rules() == []


# --- persistence + atomicity + mirror ---

def test_persists_and_reloads():
    s = store(threshold=2)
    s.add_decision("샤워헤드", "maintenance", source_raw="[[r1]]")
    s.add_decision("샤워헤드", "maintenance", source_raw="[[r2]]")
    s2 = R.RuleStore(s.json_path, s.mirror_path, 2)
    assert len(s2.active_rules()) == 1


def test_atomic_write_no_temp_and_mirror_written():
    s = store()
    s.add_decision("샤워헤드", "maintenance", source_raw="[[r1]]")
    d = s.json_path.parent
    leftovers = [p.name for p in d.iterdir() if ".tmp." in p.name]
    assert leftovers == [], leftovers
    assert s.mirror_path.exists()
    assert "Learned Rules" in s.mirror_path.read_text(encoding="utf-8")


def test_normalization_groups_decisions():
    s = store(threshold=2)
    s.add_decision(" 샤워헤드  ", "maintenance", source_raw="[[r1]]")
    s.add_decision("샤워헤드", "maintenance", source_raw="[[r2]]")
    assert len(s.active_rules()) == 1  # both normalized to one signal


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
