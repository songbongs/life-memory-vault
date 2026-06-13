#!/usr/bin/env python3
"""Tests for `mem.py enrich` / scripts/enrich.py — deterministic URL enrichment (A1).

All fetch/extract/image backends are injected, so there is NO network and NO real
vault. Staging is redirected into the temp dir via config.enrichment.stagingDir
(absolute path overrides enrich.ROOT join), so the real project tree is untouched.

    python3 tests/test_enrich.py
"""

import argparse
import contextlib
import hashlib
import io
import json
import re
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import enrich  # noqa: E402
import mem  # noqa: E402


# --------------------------------------------------------------------------- setup
def setup():
    base = Path(tempfile.mkdtemp())
    vault = base / "vault"
    for d in ["00_Inbox/Raw/2026/06", "00_Inbox/Processed", "60_Ideas/Products",
              "80_Assets", "10_Timeline/Daily"]:
        (vault / d).mkdir(parents=True, exist_ok=True)
    cfg = {
        "memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed",
                        "assetsFolder": "80_Assets"},
        "enrichment": {"enabled": True, "maxCandidatesPerRun": 5, "timeoutSeconds": 20,
                       "maxExtractChars": 8000, "imageMaxBytes": 5242880,
                       "optOutTags": ["#노요약", "#raw"], "assetsSubdir": "Web",
                       "extractsSubdir": "Extracts"},
    }
    return base, vault, cfg


def write_raw(vault, name, body):
    p = vault / "00_Inbox/Raw/2026/06" / name
    p.write_text(
        f'---\nid: "x"\ncaptured_at: "2026-06-09T06:41:43+09:00"\n'
        f'source: "telegram"\nraw_type: "raw_url"\n---\n\n{body}\n',
        encoding="utf-8",
    )
    return f"00_Inbox/Raw/2026/06/{name}"


def write_note(vault, relpath, source_raw, body=None):
    p = vault / relpath
    p.parent.mkdir(parents=True, exist_ok=True)
    link = source_raw[:-3] if source_raw.endswith(".md") else source_raw
    text = body or (
        f'---\nmemory_type: "product"\nsource_raw: "[[{link}]]"\n---\n\n'
        f'# 제목\n\n## Source\n\n- [[{link}]]\n\n## Extracted note\n\n원본 메모\n'
    )
    p.write_text(text, encoding="utf-8")
    return relpath


def write_marker(vault, raw_rel, structured, **extra):
    rid = hashlib.sha1(raw_rel.encode()).hexdigest()[:16]
    d = {"raw": raw_rel, "structured": structured, "processed_at": "x",
         "lint_method": "rule_based", "plan": {"memory_type": "product"},
         "entities_updated": []}
    d.update(extra)
    mp = vault / "00_Inbox/Processed" / f"{rid}.json"
    mp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return mp


def args(limit=5, all=False, force=False, dry_run=False):
    return argparse.Namespace(limit=limit, all=all, force=force, dry_run=dry_run)


def run(cfg, a, **backends):
    # Default enqueue to a no-op so tests never touch the real job queue.
    backends.setdefault("enqueue", lambda n: None)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        out = enrich.enrich_vault(a, cfg, **backends)
    return out


# --------------------------------------------------------------------- fake backends
def f_ok(url, timeout):
    return "<html>" + url + "</html>"


def f_fail(url, timeout):
    return None


def f_raise(url, timeout):
    raise RuntimeError("network down")


def x_full(html, url, max_chars):
    return {"title": "페이지제목", "sitename": "사이트", "image": "https://img.example/x.jpg",
            "description": "설명", "body": "본문 내용입니다. " * 50}


def x_empty(html, url, max_chars):
    return {"title": None, "sitename": None, "image": None, "description": None, "body": "짧"}


def dl_ok(image_url, dest_dir, url_norm, max_bytes):
    dest_dir.mkdir(parents=True, exist_ok=True)
    fn = hashlib.sha1(url_norm.encode()).hexdigest()[:12] + ".jpg"
    (dest_dir / fn).write_bytes(b"\xff\xd8\xff")
    return fn


def dl_none(image_url, dest_dir, url_norm, max_bytes):
    return None


# --------------------------------------------------------------------------- tests
def test_extract_inserts_block_marker_image_staging():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/page")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    out = run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_ok)
    assert out["enriched"] == 1, out
    note = (vault / "60_Ideas/Products/a.md").read_text(encoding="utf-8")
    assert "enrich:begin" in note and "페이지제목" in note
    assert "![[80_Assets/Web/" in note
    d = json.loads(mp.read_text())
    assert d["enrichment"]["status"] == "extracted"
    assert d["enrichment"]["image"].startswith("80_Assets/Web/")
    assert list((vault / "80_Assets/Web").glob("*.jpg"))
    # (B) full original archived permanently in the vault + linked in the note
    extract_file = vault / "80_Assets/Extracts" / f"{mp.stem}.md"
    assert extract_file.exists()
    assert d["enrichment"]["extract"] == f"80_Assets/Extracts/{mp.stem}.md"
    assert "![[80_Assets/Extracts/" in note and "원문 전체" in note


def test_idempotent_second_run_keeps_one_block():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/page")
    write_note(vault, "60_Ideas/Products/a.md", r)
    write_marker(vault, r, "60_Ideas/Products/a.md")
    run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_ok)
    note1 = (vault / "60_Ideas/Products/a.md").read_text()
    # second run: marker is 'extracted' (DONE) -> not reprocessed; note stable
    out2 = run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_ok)
    note2 = (vault / "60_Ideas/Products/a.md").read_text()
    assert note1.count("enrich:begin") == 1 and note2.count("enrich:begin") == 1
    assert out2["enriched"] == 0
    # force re-run replaces in place, still one block
    run(cfg, args(force=True), fetch=f_ok, extract=x_full, download_image=dl_ok)
    note3 = (vault / "60_Ideas/Products/a.md").read_text()
    assert note3.count("enrich:begin") == 1


def test_block_outside_and_frontmatter_unchanged():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    original = ('---\nmemory_type: "product"\nsource_raw: "[[x]]"\ntags:\n  - 중요\n---\n\n'
                '# 제목\n\n사용자가 손으로 쓴 본문\n\n## 내 섹션\n\n보존되어야 함\n')
    np = vault / "60_Ideas/Products/a.md"
    np.write_text(original, encoding="utf-8")
    write_marker(vault, r, "60_Ideas/Products/a.md")
    run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_none)
    after = np.read_text(encoding="utf-8")
    stripped = re.sub(r"\n*<!-- enrich:begin.*?<!-- enrich:end -->\n*", "", after, flags=re.DOTALL)
    assert stripped.rstrip("\n") == original.rstrip("\n"), repr(stripped)


def test_optout_tag_skipped():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p #노요약")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    note_before = (vault / "60_Ideas/Products/a.md").read_text()
    out = run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_ok)
    assert out["skipped"] == 1 and out["enriched"] == 0
    assert (vault / "60_Ideas/Products/a.md").read_text() == note_before  # note untouched
    assert json.loads(mp.read_text())["enrichment"]["status"] == "skipped"


def test_empty_body_status():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    out = run(cfg, args(), fetch=f_ok, extract=x_empty, download_image=dl_none)
    assert out["empty"] == 1
    assert json.loads(mp.read_text())["enrichment"]["status"] == "empty"


def test_fetch_failure_increments_attempts_then_skips():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    for expected in (1, 2, 3):
        run(cfg, args(), fetch=f_fail, extract=x_full, download_image=dl_none)
        d = json.loads(mp.read_text())
        assert d["enrichment"]["status"] == "failed"
        assert d["enrichment"]["attempts"] == expected, (expected, d)
    # attempts now 3 -> further runs skip it
    out = run(cfg, args(), fetch=f_fail, extract=x_full, download_image=dl_none)
    assert out["failed"] == 0


def test_fetch_exception_is_failed():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    out = run(cfg, args(), fetch=f_raise, extract=x_full, download_image=dl_none)
    assert out["failed"] == 1
    assert json.loads(mp.read_text())["enrichment"]["status"] == "failed"


def test_image_none_no_embed_but_still_extracted():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_none)
    note = (vault / "60_Ideas/Products/a.md").read_text()
    assert "enrich:begin" in note
    assert "![[80_Assets/Web/" not in note          # no image embed
    assert "![[80_Assets/Extracts/" in note         # but original archive IS linked (B)
    assert json.loads(mp.read_text())["enrichment"]["image"] == ""


def test_duplicate_url_links_to_existing():
    base, vault, cfg = setup()
    same = "https://x.com/same"
    un = enrich.normalize_url(same)
    r1 = write_raw(vault, "a.md", same)
    write_note(vault, "60_Ideas/Products/a.md", r1)
    write_marker(vault, r1, "60_Ideas/Products/a.md",
                 enrichment={"status": "summarized", "url": same, "url_normalized": un})
    r2 = write_raw(vault, "b.md", same)
    write_note(vault, "60_Ideas/Products/b.md", r2)
    mp2 = write_marker(vault, r2, "60_Ideas/Products/b.md")
    out = run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_none)
    assert out["duplicate_url"] == 1, out
    d2 = json.loads(mp2.read_text())
    assert d2["enrichment"]["status"] == "duplicate_url"
    assert "이미 정리된 링크" in (vault / "60_Ideas/Products/b.md").read_text()


def test_first_url_and_extra_urls():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/1 그리고 https://y.com/2 참고")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_none)
    e = json.loads(mp.read_text())["enrichment"]
    assert e["url"] == "https://x.com/1"
    assert e["extra_urls"] == ["https://y.com/2"]


def test_dry_run_changes_nothing():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    mp = write_marker(vault, r, "60_Ideas/Products/a.md")
    note_before = (vault / "60_Ideas/Products/a.md").read_text()
    out = run(cfg, args(dry_run=True), fetch=f_ok, extract=x_full, download_image=dl_ok)
    assert out["dry_run"] and out["total"] == 1 and out["would_process"] == 1
    assert (vault / "60_Ideas/Products/a.md").read_text() == note_before
    assert "enrichment" not in json.loads(mp.read_text())
    assert not (vault / "80_Assets/Web").exists() or not list((vault / "80_Assets/Web").glob("*"))
    assert not (vault / "80_Assets/Extracts").exists() or not list((vault / "80_Assets/Extracts").glob("*"))


def test_limit_then_all_drains_rest():
    base, vault, cfg = setup()
    for name in ["a", "b", "c"]:
        r = write_raw(vault, f"{name}.md", f"https://x.com/{name}")
        write_note(vault, f"60_Ideas/Products/{name}.md", r)
        write_marker(vault, r, f"60_Ideas/Products/{name}.md")
    out1 = run(cfg, args(limit=2), fetch=f_ok, extract=x_full, download_image=dl_none)
    assert out1["enriched"] == 2, out1
    out2 = run(cfg, args(all=True), fetch=f_ok, extract=x_full, download_image=dl_none)
    assert out2["enriched"] == 1, out2  # only the remaining one


def test_enqueue_called_once_with_extracted_count():
    base, vault, cfg = setup()
    for name in ["a", "b"]:
        r = write_raw(vault, f"{name}.md", f"https://x.com/{name}")
        write_note(vault, f"60_Ideas/Products/{name}.md", r)
        write_marker(vault, r, f"60_Ideas/Products/{name}.md")
    calls = []
    run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_none,
        enqueue=lambda n: calls.append(n))
    assert calls == [2], calls  # 2 extracted -> exactly one enqueue carrying the count


def test_enqueue_not_called_when_nothing_extracted():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    write_marker(vault, r, "60_Ideas/Products/a.md")
    calls = []
    run(cfg, args(), fetch=f_fail, extract=x_full, download_image=dl_none,
        enqueue=lambda n: calls.append(n))
    assert calls == []  # fetch failed -> no staging -> no summary job


def test_prune_orphans_ignores_enrich_output():
    base, vault, cfg = setup()
    r = write_raw(vault, "a.md", "https://x.com/p")
    write_note(vault, "60_Ideas/Products/a.md", r)
    write_marker(vault, r, "60_Ideas/Products/a.md")
    run(cfg, args(), fetch=f_ok, extract=x_full, download_image=dl_ok)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.prune_orphans(argparse.Namespace(apply=False), cfg)
    pr = json.loads(buf.getvalue())
    assert pr["would_delete"] == 0, pr  # enrich output (image, block) must not be flagged


def test_digest_reports_enrichment_stats():
    base, vault, cfg = setup()
    r1 = write_raw(vault, "a.md", "https://x.com/a")
    write_marker(vault, r1, "60_Ideas/Products/a.md",
                 enrichment={"status": "summarized", "url": "https://x.com/a"})
    r2 = write_raw(vault, "b.md", "https://x.com/b")
    write_marker(vault, r2, "60_Ideas/Products/b.md",
                 enrichment={"status": "extracted", "url": "https://x.com/b"})
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.digest(cfg)
    out = json.loads(buf.getvalue())
    assert out["enrichment"]["total"] == 2
    assert out["enrichment"]["summarized"] == 1
    assert out["enrichment"]["extracted"] == 1
    assert out["enrichment"]["failed"] == 0


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
