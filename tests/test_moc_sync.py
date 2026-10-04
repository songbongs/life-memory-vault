#!/usr/bin/env python3
"""Tests for moc_sync (mem.py moc-sync).

빠진 노트만 등록하는지, 요약 대기·중복 마커·설명 우선순위를 지키는지 확인한다.
"""

import argparse
import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import moc_sync  # noqa: E402

IDEAS = "---\ntags:\n  - moc\n---\n# Ideas-MOC\n\n## 써보고 싶은 서비스/앱\n- [[40_Notes/Saves/Old — 기존.md|Old — 기존]] — 이미 있음 (2026-09-01)\n\n## 프로젝트 아이디어\n\n## 질문\n"
LIFE = "# Life Memory MOC\n\n## 최근 추가된 노트\n- [[40_Notes/Saves/Old — 기존.md|Old — 기존]] — 이미 있음\n\n## 기타\n"
SUMMARIZED = (
    "# {t}\n\n## Extracted note\n\n{t}\n\n원래 메모 설명입니다.\n\nhttps://github.com/x/y\n\n"
    "<!-- enrich:begin v1 -->\n> [!abstract] 웹 페이지 — x\n> 출처: https://github.com/x/y\n\n"
    "![[80_Assets/Web/a.png]]\n\n로컬에서 도는 메모리 도구다. 원문을 그대로 저장한다. 세 번째 문장.\n\n"
    "**핵심 포인트**\n- a\n\n제안 태그: #a\n\n> [!note]- 원문 전체 (추출본)\n> ![[80_Assets/Extracts/m]]\n<!-- enrich:end -->\n"
)
EXTRACTED = SUMMARIZED.replace("로컬에서 도는 메모리 도구다. 원문을 그대로 저장한다. 세 번째 문장.", "English excerpt only.")


def _setup():
    vault = Path(tempfile.mkdtemp()) / "vault"
    for d in ("00_Inbox/Processed", "40_Notes/Saves", "10_Daily", "90_System/Index"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    (vault / moc_sync.IDEAS_MOC).write_text(IDEAS, encoding="utf-8")
    (vault / moc_sync.LIFE_MOC).write_text(LIFE, encoding="utf-8")
    cfg = {"memoryVault": {"vaultPath": str(vault), "processedFolder": "00_Inbox/Processed"}}
    return vault, cfg


def _note(vault, name, body, ts="2026-10-01-120000", status="summarized", folder="40_Notes/Saves", **extra):
    rel = f"{folder}/{name}.md"
    (vault / rel).write_text(body.format(t=name), encoding="utf-8")
    marker = {"raw": f"00_Inbox/Raw/2026/10/{ts}-{name}.md", "structured": rel, "mocs_updated": []}
    if status:
        marker["enrichment"] = {"status": status}
    marker.update(extra)
    (vault / "00_Inbox/Processed" / f"{name}.json").write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    return rel


def _args(apply=False, today="2026-10-04", descriptions=None):
    return argparse.Namespace(apply=apply, recent_days=14, wait_days=3, descriptions=descriptions,
                              today=today, verbose=True)


def test_adds_missing_note_with_summary_sentences():
    vault, cfg = _setup()
    _note(vault, "New — 새 도구", SUMMARIZED)
    out = moc_sync.moc_sync(_args(apply=True), cfg)
    assert out["ideas_added"] == 1 and out["life_added"] == 1, out
    ideas = (vault / moc_sync.IDEAS_MOC).read_text(encoding="utf-8")
    line = "- [[40_Notes/Saves/New — 새 도구.md|New — 새 도구]] — 로컬에서 도는 메모리 도구다. 원문을 그대로 저장한다 (2026-10-01)"
    assert line in ideas, ideas
    assert ideas.index(line) < ideas.index("## 프로젝트 아이디어")
    assert "## 질문" in ideas and "Old — 기존" in ideas  # 기존 구조 보존
    life = (vault / moc_sync.LIFE_MOC).read_text(encoding="utf-8")
    assert life.index("New — 새 도구") < life.index("Old — 기존")  # 최신이 위
    marker = json.loads((vault / "00_Inbox/Processed/New — 새 도구.json").read_text(encoding="utf-8"))
    assert moc_sync.IDEAS_MOC in marker["mocs_updated"] and moc_sync.LIFE_MOC in marker["mocs_updated"]


def test_idempotent_second_run_adds_nothing():
    vault, cfg = _setup()
    _note(vault, "New — 새 도구", SUMMARIZED)
    moc_sync.moc_sync(_args(apply=True), cfg)
    out = moc_sync.moc_sync(_args(apply=True), cfg)
    assert out["ideas_added"] == 0 and out["life_added"] == 0, out


def test_dry_run_writes_nothing():
    vault, cfg = _setup()
    _note(vault, "New — 새 도구", SUMMARIZED)
    moc_sync.moc_sync(_args(apply=False), cfg)
    assert (vault / moc_sync.IDEAS_MOC).read_text(encoding="utf-8") == IDEAS


def test_waits_for_summary_then_falls_back_to_raw():
    vault, cfg = _setup()
    _note(vault, "Wait — 대기", EXTRACTED, ts="2026-10-03-120000", status="extracted")
    out = moc_sync.moc_sync(_args(), cfg)
    assert out["waiting_for_summary"] == 1 and out["ideas_added"] == 0, out
    out = moc_sync.moc_sync(_args(today="2026-10-10"), cfg)  # 대기 기한 지남 → raw 설명
    assert out["ideas_added"] == 1, out
    assert "원래 메모 설명입니다 (2026-10-03)" in out["ideas"][0], out["ideas"]
    assert "English" not in out["ideas"][0]


def test_skips_merged_and_duplicate_markers():
    vault, cfg = _setup()
    _note(vault, "Merged — 통합", SUMMARIZED, merged_into="x.json")
    _note(vault, "Dup — 중복", SUMMARIZED, duplicate_of="x.json")
    out = moc_sync.moc_sync(_args(), cfg)
    assert out["ideas_added"] == 0, out


def test_life_moc_only_recent_and_non_saves_skip_ideas():
    vault, cfg = _setup()
    _note(vault, "Old2 — 옛 노트", SUMMARIZED, ts="2026-08-01-120000")
    _note(vault, "할 일", "# {t}\n\n## Extracted note\n\n할 일\n\n우유 사기 메모\n", status=None, folder="10_Daily")
    out = moc_sync.moc_sync(_args(), cfg)
    assert out["ideas_added"] == 1 and "Old2" in out["ideas"][0], out  # 오래된 Saves → Ideas만
    assert out["life_added"] == 1 and "할 일" in out["life"][0], out  # 최근 비-Saves → Life만


def test_empty_non_saves_memo_not_listed():
    vault, cfg = _setup()
    _note(vault, "Telegram non-text message", "# {t}\n\n## Extracted note\n\n[Telegram non-text message]\n\nAttachments:\n", status=None, folder="10_Daily")
    out = moc_sync.moc_sync(_args(), cfg)
    assert out["life_added"] == 0 and out["ideas_added"] == 0, out


def test_no_blank_line_inside_list_and_skip_expired_archive_copy():
    vault, cfg = _setup()
    _note(vault, "New — 새 도구", SUMMARIZED)
    (vault / "40_Archive/링크만료").mkdir(parents=True)
    _note(vault, "Dead — 만료", SUMMARIZED)
    (vault / "40_Archive/링크만료/Dead — 만료.md").write_text("x", encoding="utf-8")
    moc_sync.moc_sync(_args(apply=True), cfg)
    ideas = (vault / moc_sync.IDEAS_MOC).read_text(encoding="utf-8")
    assert "이미 있음 (2026-09-01)\n- [[40_Notes/Saves/New" in ideas, ideas
    assert "Dead — 만료" not in ideas, ideas


def test_descriptions_file_overrides_auto():
    vault, cfg = _setup()
    rel = _note(vault, "New — 새 도구", SUMMARIZED)
    f = vault.parent / "desc.json"
    f.write_text(json.dumps({rel: "직접 쓴 설명"}, ensure_ascii=False), encoding="utf-8")
    out = moc_sync.moc_sync(_args(descriptions=str(f)), cfg)
    assert "— 직접 쓴 설명 (2026-10-01)" in out["ideas"][0], out


def test_shorten_keeps_limit():
    s = moc_sync.shorten("가" * 200 + ". 다음 문장.")
    assert len(s) <= moc_sync.MAX_DESC + 1 and s.endswith("…"), s


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
