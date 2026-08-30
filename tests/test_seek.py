#!/usr/bin/env python3
"""Tests for P5 — scored, filterable seek. Temp vault, no network.

Runs without pytest:  python3 tests/test_seek.py
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


def note(vault, rel, memory_type, tags, date, body):
    p = vault / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    fm = ["---", f'memory_type: "{memory_type}"', f'updated_at: "{date}"']
    if tags:
        fm.append("tags:")
        fm += [f'  - "{t}"' for t in tags]
    fm.append("---")
    p.write_text("\n".join(fm) + "\n\n" + body + "\n", encoding="utf-8")
    return p


def setup():
    vault = Path(tempfile.mkdtemp()) / "vault"
    vault.mkdir()
    note(vault, "20_Records/Maintenance/wiper.md", "maintenance", ["차량", "와이퍼"], "2026-05-01T10:00:00", "차량 와이퍼 교체")
    note(vault, "10_Timeline/Daily/journal1.md", "journal", [], "2026-03-01T10:00:00", "와이퍼 이야기 잠깐 나옴")
    note(vault, "20_Records/Maintenance/brake.md", "maintenance", ["차량"], "2026-06-01T10:00:00", "차량 브레이크 패드 교체")
    # 링크가 죽은 노트 — 기본 검색에서 빠져야 한다
    note(vault, "40_Notes/Saves/dead.md", "save", ["차량", "링크만료"], "2026-07-01T10:00:00", "차량 와이퍼 관련 죽은 링크")
    return {"memoryVault": {"vaultPath": str(vault)}}


def run(config, query, **over):
    args = argparse.Namespace(query=query, limit=10, type="", tag="", since="", include_expired=False)
    for k, v in over.items():
        setattr(args, k, v)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.seek(args, config)
    return json.loads(buf.getvalue())


def test_multi_token_ranks_more_matches_first():
    cfg = setup()
    out = run(cfg, "차량 와이퍼")
    assert out["hits"], out
    assert out["hits"][0]["path"].endswith("wiper.md")  # matches both tokens
    # journal note matches only one token but should still appear
    paths = [h["path"] for h in out["hits"]]
    assert any(p.endswith("journal1.md") for p in paths)


def test_type_filter():
    cfg = setup()
    out = run(cfg, "와이퍼", type="maintenance")
    assert all(h["memory_type"] == "maintenance" for h in out["hits"])
    assert not any(h["path"].endswith("journal1.md") for h in out["hits"])


def test_tag_filter():
    cfg = setup()
    out = run(cfg, "교체", tag="와이퍼")
    assert len(out["hits"]) == 1 and out["hits"][0]["path"].endswith("wiper.md")


def test_since_filter_excludes_older():
    cfg = setup()
    out = run(cfg, "와이퍼", since="2026-05")
    paths = [h["path"] for h in out["hits"]]
    assert not any(p.endswith("journal1.md") for p in paths)  # 2026-03 excluded


def test_recency_tiebreak():
    cfg = setup()
    out = run(cfg, "차량")  # wiper(05) and brake(06) tie on score -> newer first
    top2 = [h["path"] for h in out["hits"][:2]]
    assert top2[0].endswith("brake.md"), top2


def test_no_token_match_returns_empty():
    cfg = setup()
    out = run(cfg, "존재하지않는단어xyz")
    assert out["hits"] == []


def test_backward_compatible_fields():
    cfg = setup()
    out = run(cfg, "와이퍼")
    h = out["hits"][0]
    assert "path" in h and "snippet" in h  # telegram run_seek_immediate depends on these


def test_limit_applies_after_sort():
    cfg = setup()
    out = run(cfg, "교체", limit=1)
    assert len(out["hits"]) == 1 and out["total"] >= 1


def test_expired_notes_excluded_by_default():
    """#링크만료 노트는 평소 검색 결과를 어지럽히지 않는다 (2026-08-30)."""
    cfg = setup()
    out = run(cfg, "와이퍼")
    assert not any(h["path"].endswith("dead.md") for h in out["hits"]), out["hits"]


def test_expired_notes_visible_with_flag():
    cfg = setup()
    out = run(cfg, "와이퍼", include_expired=True)
    assert any(h["path"].endswith("dead.md") for h in out["hits"]), out["hits"]


def test_expired_tag_filter_finds_them():
    """--tag 링크만료 로 콕 집어 찾을 때는 제외가 풀린다."""
    cfg = setup()
    out = run(cfg, "차량", tag="링크만료")
    paths = [h["path"] for h in out["hits"]]
    assert paths and all(p.endswith("dead.md") for p in paths), paths


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
