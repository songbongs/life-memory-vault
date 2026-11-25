#!/usr/bin/env python3
"""Tests for 여러 링크 메모 → 묶음 노트 + 링크별 노트 (2026-11-24 사용자 결정 A).

Temp vault, no network. Runs without pytest:  python3 tests/test_bundle.py
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

import enrich  # noqa: E402
import mem  # noqa: E402

RAWDIR = "00_Inbox/Raw/2026/11"

MEMO = """AI 코딩 에이전트로 영상을 만드는 무료 도구

1. HyperFrames – HTML로 영상을 구성하고 렌더링
https://github.com/heygen-com/hyperframes

2. Remotion – React 코드로 영상 제작
https://github.com/remotion-dev/remotion

7~8. Three.js Skills — 3D 콘텐츠 및 애니메이션 제작
https://github.com/cloudaix/threejs-skills
https://github.com/impertio-studio/threejs-claude-skill-package

인공지능 정보:
https://t.me/aiinnovationstudio

#AI영상제작"""


def setup():
    base = Path(tempfile.mkdtemp())
    vault = base / "vault"
    for d in [RAWDIR, "00_Inbox/Processed", "40_Notes/Saves", "80_Assets"]:
        (vault / d).mkdir(parents=True, exist_ok=True)
    cfg = {"memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed",
                           "assetsFolder": "80_Assets"},
           "enrichment": {"enabled": True, "maxCandidatesPerRun": 50, "optOutTags": ["#노요약"],
                          "assetsSubdir": "Web", "extractsSubdir": "Extracts"}}
    cfgp = base / "config.json"
    cfgp.write_text(json.dumps(cfg), encoding="utf-8")
    return vault, cfg, cfgp


def raw(vault, name, body):
    p = vault / RAWDIR / name
    p.write_text(f'---\ncaptured_at: "2026-11-24T14:28:17+09:00"\nsource: "telegram"\n'
                 f'raw_type: "raw_url"\n---\n\n{body}\n', encoding="utf-8")
    return f"{RAWDIR}/{name}"


def lint(cfg, force=False):
    orig = mem.load_active_rules
    mem.load_active_rules = lambda a, c: []
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            mem.lint_vault(argparse.Namespace(config="x", force=force), cfg)
    finally:
        mem.load_active_rules = orig
    return json.loads(buf.getvalue())


def markers(vault):
    out = []
    for p in sorted((vault / "00_Inbox/Processed").glob("*.json")):
        out.append((p, json.loads(p.read_text(encoding="utf-8"))))
    return out


def saves(vault):
    return sorted(p.name for p in (vault / "40_Notes/Saves").glob("*.md"))


# ----------------------------------------------------------------------------- parsing
def test_items_names_and_slugs():
    items = mem.bundle_items(MEMO)
    assert [i["url"].split("/")[-1] for i in items] == [
        "hyperframes", "remotion", "threejs-skills", "threejs-claude-skill-package"], items
    assert items[0]["title"] == "HyperFrames — HTML로 영상을 구성하고 렌더링", items[0]
    assert items[1]["title"] == "Remotion — React 코드로 영상 제작"
    # 한 이름에 링크 2개 → 저장소 이름으로 구분, 설명은 공통
    assert items[2]["title"] == "threejs-skills — 3D 콘텐츠 및 애니메이션 제작", items[2]
    assert items[3]["title"] == "threejs-claude-skill-package — 3D 콘텐츠 및 애니메이션 제작"


def test_same_repo_name_gets_owner():
    body = ("12~13. MotionClone — 모션 및 애니메이션 구현\n"
            "https://github.com/LPengYang/MotionClone\nhttps://github.com/Bujiazi/MotionClone")
    t = [i["title"] for i in mem.bundle_items(body)]
    assert t == ["MotionClone (LPengYang) — 모션 및 애니메이션 구현",
                 "MotionClone (Bujiazi) — 모션 및 애니메이션 구현"], t


def test_channel_and_repeat_urls_excluded():
    body = "a https://x.com/a\nb https://x.com/a\nc https://t.me/somechannel\nd https://t.me/c/123/45"
    urls = mem.bundle_urls(body)
    assert urls == ["https://x.com/a", "https://t.me/c/123/45"], urls


def test_numbered_prefix_variants():
    body = "01 Remotion → React로 비디오 제작\nhttp://github.com/remotion-dev/remotion\n\n" \
           "02 Lottie → 가벼운 벡터 애니메이션\nhttp://github.com/airbnb/lottie-web"
    t = [i["title"] for i in mem.bundle_items(body)]
    assert t == ["Remotion — React로 비디오 제작", "Lottie — 가벼운 벡터 애니메이션"], t


# ------------------------------------------------------------------------------- lint
def test_lint_makes_bundle_and_children():
    vault, cfg, _ = setup()
    raw_rel = raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    out = lint(cfg)
    assert out["processed"] == 1 and out["bundle_children"] == 4, out
    ms = markers(vault)
    assert len(ms) == 5, [m[1] for m in ms]
    bundle = [d for _, d in ms if d.get("bundle")]
    kids = [d for _, d in ms if d.get("bundle_url")]
    assert len(bundle) == 1 and len(kids) == 4
    b = bundle[0]
    assert b["enrichment"]["status"] == "skipped" and b["enrichment"]["reason"] == "bundle"
    assert sorted(b["bundle_children"]) == sorted(k["structured"] for k in kids)
    for k in kids:
        assert k["raw"] == raw_rel and k["bundle_parent"] == b["structured"]
        assert k["lint_method"] == "rule_based" and "content_hash" not in k
    btext = (vault / b["structured"]).read_text(encoding="utf-8")
    assert "## 링크별 노트" in btext and btext.index("## 링크별 노트") < btext.index("## Extracted note")
    assert "[[40_Notes/Saves/HyperFrames — HTML로 영상을 구성하고 렌더링|" in btext
    ktext = (vault / "40_Notes/Saves/Remotion — React 코드로 영상 제작.md").read_text(encoding="utf-8")
    assert "https://github.com/remotion-dev/remotion" in ktext
    assert f"- 묶음: [[{b['structured'][:-3]}]]" in ktext
    assert 'memory_type: "save"' in ktext and "needs_review: false" in ktext
    # 일일 인덱스에는 묶음만
    daily = (vault / "10_Daily/2026-11-24.md").read_text(encoding="utf-8")
    assert daily.count("[[") == 1


def test_relint_is_idempotent():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    lint(cfg)
    before = saves(vault)
    out = lint(cfg)
    assert out["processed"] == 0
    lint(cfg, force=True)
    assert saves(vault) == before, (before, saves(vault))
    assert len(markers(vault)) == 5
    btext = next((vault / "40_Notes/Saves").glob("AI 코딩*")).read_text(encoding="utf-8")
    assert btext.count("## 링크별 노트") == 1


def test_single_url_memo_unchanged():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-24-100000-하나.md", "좋은 도구\nhttps://github.com/a/b")
    out = lint(cfg)
    assert out["bundle_children"] == 0
    (_, d), = markers(vault)
    assert "bundle" not in d and "enrichment" not in d


def test_existing_single_link_note_is_linked_not_recreated():
    vault, cfg, _ = setup()
    old_raw = raw(vault, "2026-11-01-090000-리모션.md", "Remotion\nhttps://github.com/remotion-dev/remotion")
    lint(cfg)
    (mp, d), = markers(vault)
    d["enrichment"] = {"status": "summarized", "url_normalized": "https://github.com/remotion-dev/remotion",
                       "extra_urls": []}
    mp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    old_note = d["structured"]
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    out = lint(cfg)
    assert out["bundle_children"] == 3, out
    b = next(d for _, d in markers(vault) if d.get("bundle"))
    assert old_note in b["bundle_children"]
    btext = (vault / b["structured"]).read_text(encoding="utf-8")
    assert "(이미 있던 노트)" in btext
    otext = (vault / old_note).read_text(encoding="utf-8")
    assert "## 다시 만남" in otext and b["structured"][:-3] in otext
    assert not (vault / "40_Notes/Saves/Remotion — React 코드로 영상 제작.md").exists()
    assert old_raw


def test_old_multi_link_memo_is_not_an_existing_note():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-04-131735-옛 묶음.md", "옛 목록\nhttps://github.com/remotion-dev/remotion")
    lint(cfg)
    (mp, d), = markers(vault)
    d["enrichment"] = {"status": "summarized", "url_normalized": "https://github.com/remotion-dev/remotion",
                       "extra_urls": ["http://github.com/remotion-dev/skills"]}
    mp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    out = lint(cfg)
    assert out["bundle_children"] == 4, out
    assert (vault / "40_Notes/Saves/Remotion — React 코드로 영상 제작.md").exists()


def test_same_url_in_two_bundles_same_run():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-24-142429-첫 묶음.md", "첫 묶음\n1. HyperFrames — 영상\nhttps://github.com/heygen-com/hyperframes\n"
                                             "2. Whisper — 자막\nhttps://github.com/openai/whisper")
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    out = lint(cfg)
    assert out["bundle_children"] == 2 + 3, out
    hf = [p for p in saves(vault) if p.startswith("HyperFrames")]
    assert len(hf) == 1, hf


# ----------------------------------------------------------------------------- enrich
def test_enrich_uses_each_child_url():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    lint(cfg)
    seen = []

    def fetch(url, timeout):
        seen.append(url)
        return "<html>" + url + "</html>"

    def extract(html, url, n):
        return {"title": "T " + url, "body": "본문 " * 150, "sitename": "GitHub", "image": None}

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        enrich.enrich_vault(argparse.Namespace(limit=50, all=False, force=False, dry_run=False, status=None),
                            cfg, fetch=fetch, extract=extract, download_image=lambda *a: None,
                            enqueue=lambda n: None)
    assert sorted(seen) == sorted(i["url"] for i in mem.bundle_items(MEMO)), seen
    for _, d in markers(vault):
        if d.get("bundle_url"):
            assert d["enrichment"]["status"] == "extracted", d
            assert d["enrichment"]["url"] == d["bundle_url"]
            text = (vault / d["structured"]).read_text(encoding="utf-8")
            assert d["bundle_url"] in text.split("<!-- enrich:begin")[1]
        if d.get("bundle"):
            assert d["enrichment"]["status"] == "skipped"


def test_enrich_ignores_old_multi_link_summary_for_dedup():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-04-131735-옛 묶음.md", "옛 목록\nhttps://github.com/remotion-dev/remotion")
    lint(cfg)
    (mp, d), = markers(vault)
    d["enrichment"] = {"status": "summarized", "url_normalized": "https://github.com/remotion-dev/remotion",
                       "extra_urls": ["http://github.com/remotion-dev/skills"]}
    mp.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    lint(cfg)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        enrich.enrich_vault(argparse.Namespace(limit=50, all=False, force=False, dry_run=False, status=None),
                            cfg, fetch=lambda u, t: "<html/>",
                            extract=lambda h, u, n: {"title": u, "body": "본문 " * 150, "image": None},
                            download_image=lambda *a: None, enqueue=lambda n: None)
    rem = next(d for _, d in markers(vault) if d.get("bundle_url", "").endswith("remotion"))
    assert rem["enrichment"]["status"] == "extracted", rem


# ------------------------------------------------------------------ other marker tools
def test_dedup_markers_keeps_children():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    lint(cfg)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.dedup_markers(argparse.Namespace(apply=True), cfg)
    out = json.loads(buf.getvalue())
    assert out["removed_same_raw"] == 0 and out["converted_same_note"] == 0, out
    assert len(markers(vault)) == 5


def test_digest_pending_zero_after_bundle():
    vault, cfg, _ = setup()
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    lint(cfg)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.digest(cfg)
    assert json.loads(buf.getvalue())["pending_raw"] == 0


def test_reclassify_child_updates_child_marker_only():
    vault, cfg, cfgp = setup()
    raw(vault, "2026-11-24-142817-영상 도구.md", MEMO)
    lint(cfg)
    b_before = next((p, d) for p, d in markers(vault) if d.get("bundle"))
    child = "40_Notes/Saves/Remotion — React 코드로 영상 제작.md"
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        mem.reclassify(argparse.Namespace(note=child, type="save", signal="", folder="",
                                          title="Remotion — React로 영상 만드는 도구", apply=True), cfg, cfgp)
    b_after = json.loads(b_before[0].read_text(encoding="utf-8"))
    assert b_after["structured"] == b_before[1]["structured"], "묶음 마커가 덮어써지면 안 된다"
    kid = next(d for _, d in markers(vault) if d.get("bundle_url", "").endswith("remotion"))
    assert kid["structured"] == "40_Notes/Saves/Remotion — React로 영상 만드는 도구.md", kid


TESTS = [v for k, v in list(globals().items()) if k.startswith("test_")]

if __name__ == "__main__":
    passed = 0
    for t in TESTS:
        try:
            t()
            passed += 1
        except Exception as exc:  # noqa: BLE001
            import traceback
            print(f"FAIL {t.__name__}: {exc!r}")
            traceback.print_exc()
    print(f"{passed}/{len(TESTS)} passed")
    sys.exit(0 if passed == len(TESTS) else 1)
