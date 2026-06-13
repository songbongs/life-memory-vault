#!/usr/bin/env python3
"""Tests for `mem.py dedup-markers` + digest excluding duplicate markers.

Temp vault, no network.  python3 tests/test_dedup_markers.py
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


def setup():
    vault = Path(tempfile.mkdtemp()) / "vault"
    for d in ["00_Inbox/Raw", "00_Inbox/Processed", "60_Ideas/Products"]:
        (vault / d).mkdir(parents=True, exist_ok=True)
    return vault, {"memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed",
                                   "rawFolder": "00_Inbox/Raw"}}


def marker(vault, name, structured=None, dup_of=None, processed_at="2026-06-01", mtype="product", raw=None):
    d = {"raw": raw or f"00_Inbox/Raw/{name}.md", "processed_at": processed_at,
         "plan": {"memory_type": mtype}, "content_hash": "h"}
    if dup_of:
        d["duplicate_of"] = dup_of
    else:
        d["structured"] = structured
    p = vault / "00_Inbox/Processed" / f"{name}.json"
    p.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return p


def run_dedup(cfg, apply=False):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.dedup_markers(argparse.Namespace(apply=apply), cfg)
    return json.loads(buf.getvalue())


def run_digest(cfg):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.digest(cfg)
    return json.loads(buf.getvalue())


def test_dry_run_reports_but_does_not_change():
    vault, cfg = setup()
    marker(vault, "a", "60_Ideas/Products/x.md", processed_at="2026-06-01")
    marker(vault, "b", "60_Ideas/Products/x.md", processed_at="2026-06-02")
    out = run_dedup(cfg, apply=False)
    assert out["converted_same_note"] == 1  # different raws, same note
    db = json.loads((vault / "00_Inbox/Processed/b.json").read_text())
    assert "structured" in db and "duplicate_of" not in db  # untouched


def test_apply_converts_newer_keeps_oldest():
    vault, cfg = setup()
    marker(vault, "a", "60_Ideas/Products/x.md", processed_at="2026-06-01")  # oldest = canonical
    marker(vault, "b", "60_Ideas/Products/x.md", processed_at="2026-06-03")
    marker(vault, "c", "60_Ideas/Products/x.md", processed_at="2026-06-02")
    out = run_dedup(cfg, apply=True)
    assert out["converted_same_note"] == 2
    da = json.loads((vault / "00_Inbox/Processed/a.json").read_text())
    assert "structured" in da and "duplicate_of" not in da  # canonical kept
    for n in ("b", "c"):
        d = json.loads((vault / "00_Inbox/Processed" / f"{n}.json").read_text())
        assert d.get("duplicate_of") == "60_Ideas/Products/x.md" and "structured" not in d
        assert d["plan"]["memory_type"] == "duplicate"


def test_same_raw_markers_collapsed():
    # NFC/NFD-style: two markers for the SAME raw -> one removed (backed up).
    vault, cfg = setup()
    marker(vault, "a", "60_Ideas/Products/x.md", raw="00_Inbox/Raw/same.md", processed_at="2026-06-01")
    marker(vault, "b", "60_Ideas/Products/x.md", raw="00_Inbox/Raw/same.md", processed_at="2026-06-02")
    out = run_dedup(cfg, apply=True)
    assert out["removed_same_raw"] == 1
    remaining = list((vault / "00_Inbox/Processed").glob("*.json"))
    assert len(remaining) == 1  # only canonical kept
    assert Path(out["backup"]).exists()


def test_single_marker_group_untouched():
    vault, cfg = setup()
    marker(vault, "a", "60_Ideas/Products/x.md")
    out = run_dedup(cfg, apply=True)
    assert out["converted_same_note"] == 0 and out["removed_same_raw"] == 0


def test_existing_duplicate_not_recounted():
    vault, cfg = setup()
    marker(vault, "a", "60_Ideas/Products/x.md")
    marker(vault, "b", dup_of="60_Ideas/Products/x.md")  # already duplicate, different raw
    out = run_dedup(cfg, apply=True)
    assert out["converted_same_note"] == 0


def test_digest_excludes_duplicate_markers():
    vault, cfg = setup()
    marker(vault, "a", "60_Ideas/Products/x.md", mtype="product")
    marker(vault, "b", dup_of="60_Ideas/Products/x.md", mtype="duplicate")
    out = run_digest(cfg)
    assert out["structured_notes"] == 1            # canonical only
    assert out["by_type"].get("product") == 1
    assert "duplicate" not in out["by_type"]       # duplicate marker excluded


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
