#!/usr/bin/env python3
"""Tests for lint-time dedup (C-1) — identical content -> one structured note.

Temp vault, no network. Runs without pytest:  python3 tests/test_lint_dedup.py
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
    (vault / "00_Inbox/Raw/2026/06").mkdir(parents=True)
    (vault / "00_Inbox/Processed").mkdir(parents=True)
    return vault, {"memoryVault": {"vaultPath": str(vault)}}


def raw(vault, name, body):
    p = vault / "00_Inbox/Raw/2026/06" / name
    p.write_text(f'---\nsource: "manual"\n---\n\n{body}\n', encoding="utf-8")
    return p


def lint(config, force=False):
    args = argparse.Namespace(config="ignored", force=force)
    # avoid touching real learning config: stub load_active_rules
    orig = mem.load_active_rules
    mem.load_active_rules = lambda a, c: []
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mem.lint_vault(args, config)
    finally:
        mem.load_active_rules = orig
    return json.loads(buf.getvalue())


def structured_count(vault):
    return sum(1 for p in vault.rglob("*.md")
               if "00_Inbox" not in p.relative_to(vault).parts and "90_System" not in p.relative_to(vault).parts)


def test_identical_content_makes_one_note():
    vault, cfg = setup()
    raw(vault, "a.md", "https://fascanner.duckdns.org/ 이 서비스 사용해볼 서비스로 저장")
    raw(vault, "b.md", "https://fascanner.duckdns.org/ 이 서비스 사용해볼 서비스로 저장")  # identical
    raw(vault, "c.md", "https://fascanner.duckdns.org/ 이 서비스 사용해볼 서비스로 저장")  # identical
    out = lint(cfg)
    assert out["duplicates"] == 2, out
    assert structured_count(vault) == 1, "only one structured note for identical content"


def test_whitespace_differences_still_dedup():
    vault, cfg = setup()
    raw(vault, "a.md", "거실 전구 교체")
    raw(vault, "b.md", "거실   전구  교체  ")  # same content, different spacing
    out = lint(cfg)
    assert out["duplicates"] == 1, out


def test_distinct_content_not_deduped():
    vault, cfg = setup()
    raw(vault, "a.md", "거실 전구 교체")
    raw(vault, "b.md", "욕실 샤워헤드 교체")
    out = lint(cfg)
    assert out["duplicates"] == 0 and out["processed"] == 2


def test_force_relint_does_not_self_duplicate():
    vault, cfg = setup()
    raw(vault, "a.md", "거실 전구 교체")
    lint(cfg)                      # first pass: 1 processed
    out = lint(cfg, force=True)    # re-lint same note must NOT flag itself a duplicate
    assert out["duplicates"] == 0, out
    assert out["processed"] == 1


def test_marker_records_duplicate_of():
    vault, cfg = setup()
    raw(vault, "a.md", "동일 내용 메모")
    raw(vault, "b.md", "동일 내용 메모")
    lint(cfg)
    markers = [json.loads(p.read_text(encoding="utf-8")) for p in (vault / "00_Inbox/Processed").glob("*.json")]
    dup = [m for m in markers if m.get("duplicate_of")]
    assert len(dup) == 1 and dup[0]["plan"]["memory_type"] == "duplicate"


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
