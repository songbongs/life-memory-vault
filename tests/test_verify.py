#!/usr/bin/env python3
"""Tests for verify (mem.py verify).

10-18 요약 뒤바뀜 같은 오배정을 잡는지, 정상 노트는 통과시키는지 확인한다.
"""

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify  # noqa: E402

PAGES = {
    "seecode": ("SeeCode 애니메이션 다이어그램 생성기", "https://github.com/a/seecode",
                "SeeCode는 짧은 JSON 사양을 기반으로 애니메이션이 포함된 탐색 가능한 다이어그램을 생성합니다.",
                "Ask your agent for a diagram. SeeCode turns a short spec into an animated explorable diagram. Export SVG PNG GIF MP4.",
                "SeeCode는 짧은 사양으로 움직이는 다이어그램을 만들어 주는 에이전트 스킬입니다. SVG·PNG·GIF·MP4로 내보낼 수 있습니다."),
    "watermark": ("AI 워터마크 제거 도구", "https://github.com/b/remove-ai-watermarks",
                  "이미지와 비디오에서 가시적 및 비가시적 AI 워터마크를 제거하는 파이썬 라이브러리입니다.",
                  "Remove AI provenance marks from images and video. Gemini sparkle watermark, C2PA, EXIF metadata.",
                  "이미지·영상에서 보이는 워터마크와 보이지 않는 워터마크, C2PA·EXIF 메타데이터를 제거하는 파이썬 라이브러리입니다."),
    "collie": ("Collie 모바일 AI 에이전트 관리 앱", "https://github.com/c/collie",
               "모바일에서 코딩 에이전트 세션을 관리하는 앱입니다.",
               "Collie lets you manage agent sessions from your phone. iOS and Android approvals.",
               "휴대폰에서 에이전트 세션을 관리하고 승인할 수 있는 앱입니다. iOS와 Android를 지원합니다."),
}


def _block(url, key, summary):
    return (f"<!-- enrich:begin v1 -->\n> [!abstract] 웹 페이지\n> 출처: {url} · 수집 26.10.18\n\n"
            f"![[80_Assets/Web/{key}.png]]\n\n{summary}\n\n**핵심 포인트**\n- 포인트\n\n"
            f"> [!note]- 원문 전체 (추출본)\n> ![[80_Assets/Extracts/{key}.md]]\n<!-- enrich:end -->\n")


def _setup(swap=False, **overrides):
    vault = Path(tempfile.mkdtemp()) / "vault"
    for d in ("00_Inbox/Processed", "00_Inbox/Raw/2026/10", "40_Notes/Saves", "80_Assets/Web", "80_Assets/Extracts"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    keys = list(PAGES)
    for i, key in enumerate(keys):
        title, url, desc, extract, summary = PAGES[key]
        if swap and key in ("seecode", "watermark"):
            summary = PAGES["watermark" if key == "seecode" else "seecode"][4]
        raw = f"00_Inbox/Raw/2026/10/2026-10-18-0{i}0000-{title}.md"
        note = f"40_Notes/Saves/{title}.md"
        (vault / raw).write_text(f"---\nid: x\n---\n\n{title}\n\n{desc}\n\n{url}\n", encoding="utf-8")
        body = overrides.get(key, {}).get("note") or (
            f"---\nmemory_type: \"save\"\nsource_raw: \"[[{raw[:-3]}]]\"\ntags:\n  - save\n---\n\n# {title}\n\n"
            f"## Extracted note\n\n{title}\n\n{desc}\n\n{url}\n\n" + _block(url, key, summary))
        (vault / note).write_text(body, encoding="utf-8")
        (vault / f"80_Assets/Web/{key}.png").write_bytes(b"png")
        (vault / f"80_Assets/Extracts/{key}.md").write_text(extract, encoding="utf-8")
        marker = {"raw": raw, "structured": note, "enrichment": {
            "status": "summarized", "url": url, "url_normalized": url, "image": f"80_Assets/Web/{key}.png",
            "extract": f"80_Assets/Extracts/{key}.md", "summarized_at": "2026-10-18T23:03:05"}}
        (vault / f"00_Inbox/Processed/{key}.json").write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    cfg = {"memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed"}}
    return vault, cfg


class _Args:
    days = None
    since = None
    json = None
    verbose = True


def _kinds(cfg):
    out = verify.verify(_Args(), cfg)
    return [(p["kind"], Path(p["note"]).stem) for p in out["items"]], out


def test_clean_vault_passes():
    _, cfg = _setup()
    kinds, out = _kinds(cfg)
    assert kinds == [], kinds
    assert out["checked"] == 3, out


def test_swapped_summaries_are_flagged():
    _, cfg = _setup(swap=True)
    kinds, _ = _kinds(cfg)
    flagged = {stem for kind, stem in kinds if kind == "summary_mismatch_suspect"}
    assert flagged == {"SeeCode 애니메이션 다이어그램 생성기", "AI 워터마크 제거 도구"}, kinds


def test_wrong_source_url_is_flagged():
    vault, cfg = _setup()
    note = vault / "40_Notes/Saves/Collie 모바일 AI 에이전트 관리 앱.md"
    note.write_text(note.read_text(encoding="utf-8").replace("출처: https://github.com/c/collie",
                                                             "출처: https://github.com/z/other"), encoding="utf-8")
    kinds, _ = _kinds(cfg)
    assert ("enrich_url_mismatch", "Collie 모바일 AI 에이전트 관리 앱") in kinds, kinds


def test_wrong_extract_link_and_missing_asset():
    vault, cfg = _setup()
    note = vault / "40_Notes/Saves/Collie 모바일 AI 에이전트 관리 앱.md"
    note.write_text(note.read_text(encoding="utf-8").replace("Extracts/collie.md", "Extracts/seecode.md"),
                    encoding="utf-8")
    (vault / "80_Assets/Web/watermark.png").unlink()
    kinds, _ = _kinds(cfg)
    assert ("asset_link_mismatch", "Collie 모바일 AI 에이전트 관리 앱") in kinds, kinds
    assert ("asset_missing", "AI 워터마크 제거 도구") in kinds, kinds


def test_source_raw_and_duplicate_keys():
    vault, cfg = _setup()
    note = vault / "40_Notes/Saves/Collie 모바일 AI 에이전트 관리 앱.md"
    text = note.read_text(encoding="utf-8")
    text = text.replace("2026-10-18-020000", "2026-10-18-999999").replace("tags:\n  - save\n", "tags:\n  - save\ntags: \"[]\"\n")
    note.write_text(text, encoding="utf-8")
    kinds, _ = _kinds(cfg)
    assert ("source_raw_mismatch", "Collie 모바일 AI 에이전트 관리 앱") in kinds, kinds
    assert ("duplicate_fm_keys", "Collie 모바일 AI 에이전트 관리 앱") in kinds, kinds


def test_already_saved_link_block_is_not_a_mismatch():
    vault, cfg = _setup()
    note = vault / "40_Notes/Saves/Collie 모바일 AI 에이전트 관리 앱.md"
    text = note.read_text(encoding="utf-8")
    text = text[:text.index("<!-- enrich:begin")] + (
        "<!-- enrich:begin v1 -->\n> [!info] 이미 정리된 링크\n> https://github.com/c/collie 은(는) "
        "[[40_Notes/Saves/다른 노트]] 에 정리되어 있습니다.\n<!-- enrich:end -->\n")
    note.write_text(text, encoding="utf-8")
    kinds, _ = _kinds(cfg)
    assert kinds == [], kinds


def test_known_exceptions_pass():
    vault, cfg = _setup()
    proc = vault / "00_Inbox/Processed"
    # 다시 받은 주소(fetched_url)로 블록이 쓰인 경우
    note = vault / "40_Notes/Saves/Collie 모바일 AI 에이전트 관리 앱.md"
    note.write_text(note.read_text(encoding="utf-8").replace("출처: https://github.com/c/collie",
                                                             "출처: https://github.com/c/collie-root"), encoding="utf-8")
    data = json.loads((proc / "collie.json").read_text(encoding="utf-8"))
    data["enrichment"]["fetched_url"] = "https://github.com/c/collie-root"
    (proc / "collie.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    # 사용자가 일부러 지운 노트
    (proc / "gone.json").write_text(json.dumps({"raw": "00_Inbox/Raw/x.md", "structured": "10_Daily/사진.md",
                                                "structured_deleted": {"reason": "불필요"}}), encoding="utf-8")
    # skipped 마커가 같은 노트를 가리킴(설치 스크립트 주소)
    raw = vault / "00_Inbox/Raw/2026/10/2026-10-18-000000-SeeCode 애니메이션 다이어그램 생성기.md"
    raw.write_text(raw.read_text(encoding="utf-8") + "\nhttps://seecode.dev/install.sh\n", encoding="utf-8")
    (proc / "skip.json").write_text(json.dumps({
        "raw": "00_Inbox/Raw/2026/10/2026-10-18-000000-SeeCode 애니메이션 다이어그램 생성기.md",
        "structured": "40_Notes/Saves/SeeCode 애니메이션 다이어그램 생성기.md",
        "enrichment": {"status": "skipped", "url": "https://seecode.dev/install.sh"}}), encoding="utf-8")
    kinds, _ = _kinds(cfg)
    assert not [k for k in kinds if k[0] in verify.SERIOUS], kinds


def test_merged_markers_are_skipped():
    vault, cfg = _setup()
    m = vault / "00_Inbox/Processed/collie.json"
    data = json.loads(m.read_text(encoding="utf-8"))
    data["merged_into"] = "40_Notes/Saves/다른 노트.md"
    data["structured"] = "40_Notes/Saves/없는 노트.md"
    m.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    kinds, out = _kinds(cfg)
    assert kinds == [] and out["checked"] == 2, (kinds, out)


def test_since_limits_scope():
    _, cfg = _setup(swap=True)
    args = _Args()
    args.since = "2026-10-19"
    out = verify.verify(args, cfg)
    assert out["checked"] == 0 and out["problems"] == 0, out


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
