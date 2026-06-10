#!/usr/bin/env python3
"""Tests for `mem.py review list|resolve` (③d-3).

Builds a temp vault + config; no real vault, no network. Verifies the resolve
flow creates a structured note, records a learned decision, and deletes the
Review file while leaving raw untouched.

Runs without pytest:  python3 tests/test_review_cli.py
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402
import rules as R  # noqa: E402


def setup_vault():
    d = Path(tempfile.mkdtemp())
    vault = d / "vault"
    (vault / "00_Inbox/Review").mkdir(parents=True)
    (vault / "00_Inbox/Raw/2026/06").mkdir(parents=True)
    # a raw note (must remain untouched)
    raw = vault / "00_Inbox/Raw/2026/06/raw1.md"
    raw.write_text("샤워헤드 교체함", encoding="utf-8")
    # a review note
    review = vault / "00_Inbox/Review/review-lint-2026-06-10-shower.md"
    review.write_text(
        "---\n"
        'review_type: "lint_uncertain"\n'
        'source_raw: "[[00_Inbox/Raw/2026/06/raw1]]"\n'
        'reason: "maintenance vs journal 모호"\n'
        'suggested_folder: "20_Records/Maintenance"\n'
        "---\n\n"
        "욕실 샤워헤드 교체함\n",
        encoding="utf-8",
    )
    cfg_path = d / "config.json"
    cfg = {
        "memoryVault": {"vaultPath": str(vault)},
        "learning": {"enabled": True, "promoteThreshold": 2,
                     "rulesPath": "90_System/Rules/learned-rules.json",
                     "mirrorPath": "90_System/Rules/Learned Rules.md"},
    }
    cfg_path.write_text(json.dumps(cfg), encoding="utf-8")
    return d, vault, cfg, cfg_path, review, raw


def test_review_list_finds_items(capsys=None):
    d, vault, cfg, cfg_path, review, raw = setup_vault()
    # review_list prints JSON; capture via building items directly is simpler:
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.review_list(cfg)
    out = json.loads(buf.getvalue())
    assert out["count"] == 1
    assert out["review"][0]["review_type"] == "lint_uncertain"


def _resolve(cfg, cfg_path, review, **over):
    args = argparse.Namespace(file=review.name, type="maintenance", signal="", folder="", title="")
    for k, v in over.items():
        setattr(args, k, v)
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.review_resolve(args, cfg, cfg_path)
    return json.loads(buf.getvalue())


def test_resolve_creates_note_and_deletes_review():
    d, vault, cfg, cfg_path, review, raw = setup_vault()
    out = _resolve(cfg, cfg_path, review)
    assert out["memory_type"] == "maintenance"
    assert (vault / out["resolved"]).exists()
    assert not review.exists()           # review deleted
    assert raw.exists()                  # raw untouched
    assert raw.read_text(encoding="utf-8") == "샤워헤드 교체함"


def test_resolve_uses_suggested_folder():
    d, vault, cfg, cfg_path, review, raw = setup_vault()
    out = _resolve(cfg, cfg_path, review)
    assert out["resolved"].startswith("20_Records/Maintenance/")


def test_resolve_without_signal_records_nothing():
    d, vault, cfg, cfg_path, review, raw = setup_vault()
    out = _resolve(cfg, cfg_path, review)
    assert out["decision"]["recorded"] is False
    store = R.from_config(cfg_path)
    assert store.rules() == []


def test_resolve_with_signal_records_decision():
    d, vault, cfg, cfg_path, review, raw = setup_vault()
    out = _resolve(cfg, cfg_path, review, signal="샤워헤드")
    assert out["decision"]["recorded"] is True
    store = R.from_config(cfg_path)
    r = store.rules()
    assert len(r) == 1 and r[0]["signal"] == "샤워헤드" and r[0]["type"] == "maintenance"
    assert r[0]["status"] == "candidate"  # 1 confirmation < threshold 2


def test_two_resolves_promote_to_active():
    d, vault, cfg, cfg_path, review, raw = setup_vault()
    _resolve(cfg, cfg_path, review, signal="샤워헤드")
    # second review note, different source
    review2 = vault / "00_Inbox/Review/review-lint-2026-06-11-shower2.md"
    review2.write_text(
        "---\nreview_type: \"lint_uncertain\"\nsource_raw: \"[[00_Inbox/Raw/2026/06/raw2]]\"\n"
        "suggested_folder: \"20_Records/Maintenance\"\n---\n\n샤워헤드 또 교체\n",
        encoding="utf-8",
    )
    args = argparse.Namespace(file=review2.name, type="maintenance", signal="샤워헤드", folder="", title="")
    import io, contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        mem.review_resolve(args, cfg, cfg_path)
    store = R.from_config(cfg_path)
    assert {a["signal"] for a in store.active_rules()} == {"샤워헤드"}


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
