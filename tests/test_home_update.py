#!/usr/bin/env python3
"""Tests for mem.py home-update command.

Verifies that the stats block in 홈.md is created/updated correctly
and that the vault's raw note counts appear in the output.
"""

import contextlib
import io
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import mem  # noqa: E402


def _setup():
    base = Path(tempfile.mkdtemp())
    vault = base / "vault"
    (vault / "00_Inbox/Raw/2026/06").mkdir(parents=True, exist_ok=True)
    (vault / "00_Inbox/Processed").mkdir(parents=True, exist_ok=True)
    (vault / "90_System").mkdir(parents=True, exist_ok=True)
    cfg = {
        "memoryVault": {
            "vaultPath": str(vault),
            "rawFolder": "00_Inbox/Raw",
            "processedFolder": "00_Inbox/Processed",
        }
    }
    return vault, cfg


def _write_raw(vault, name):
    p = vault / "00_Inbox/Raw/2026/06" / name
    p.write_text("---\nid: x\ncaptured_at: 2026-06-14T00:00+09:00\n---\n\nhello\n", encoding="utf-8")


def _write_marker(vault, name, enrichment=None):
    d = {"raw": f"00_Inbox/Raw/2026/06/{name}.md", "structured": "x.md", "processed_at": "x",
         "lint_method": "rule_based", "plan": {"memory_type": "task"}, "entities_updated": []}
    if enrichment:
        d["enrichment"] = enrichment
    (vault / "00_Inbox/Processed" / f"{name}.json").write_text(json.dumps(d), encoding="utf-8")


def test_creates_stats_block_when_home_exists():
    vault, cfg = _setup()
    home = vault / "90_System" / "홈.md"
    home.write_text("# 홈\n\n내용\n", encoding="utf-8")
    _write_raw(vault, "a.md")
    _write_raw(vault, "b.md")
    _write_marker(vault, "m1", enrichment={"status": "summarized"})

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.home_update(cfg)
    out = json.loads(buf.getvalue())
    assert "updated" in out
    assert "기록 2건" in out["stats"]
    assert "링크 요약 1/1" in out["stats"]
    updated_text = home.read_text(encoding="utf-8")
    assert "<!-- stats:begin -->" in updated_text
    assert "<!-- stats:end -->" in updated_text


def test_updates_existing_stats_block():
    vault, cfg = _setup()
    home = vault / "90_System" / "홈.md"
    home.write_text(
        "# 홈\n\n<!-- stats:begin -->\n> 이전 통계\n<!-- stats:end -->\n\n끝\n",
        encoding="utf-8",
    )
    _write_raw(vault, "x.md")

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.home_update(cfg)
    text = home.read_text(encoding="utf-8")
    assert "이전 통계" not in text
    assert "기록 1건" in text
    assert text.endswith("\n끝\n")


def test_skipped_when_home_missing():
    vault, cfg = _setup()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.home_update(cfg)
    out = json.loads(buf.getvalue())
    assert "skipped" in out


def test_failed_enrich_shown_in_stats():
    vault, cfg = _setup()
    home = vault / "90_System" / "홈.md"
    home.write_text("# 홈\n", encoding="utf-8")
    _write_raw(vault, "f.md")
    _write_marker(vault, "mf", enrichment={"status": "failed"})

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.home_update(cfg)
    out = json.loads(buf.getvalue())
    assert "실패 1건" in out["stats"]


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
