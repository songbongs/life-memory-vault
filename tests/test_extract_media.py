#!/usr/bin/env python3
"""Tests for `mem.py extract-media` / `scripts/extract_media.py`.

Temp vault, no real OCR/PDF subprocess. Backends are injected (returns fake text).
Runs without pytest:  python3 tests/test_extract_media.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import extract_media as em  # noqa: E402
import mem  # noqa: E402


# ----------------------------------------------------------------- helpers

def _config(vault: Path) -> dict:
    return {
        "memoryVault": {"vaultPath": str(vault)},
        "mediaExtraction": {
            "enabled": True, "auto": True, "maxPerRun": 3,
            "maxExtractChars": 8000, "enableOcr": True,
            "enablePdf": True, "enableAudio": False,
        },
        "tools": {"tesseract": "tesseract"},
    }


def _args(limit=3, all_=False, force=False, dry_run=False):
    import argparse
    a = argparse.Namespace()
    a.limit = limit
    a.all = all_
    a.force = force
    a.dry_run = dry_run
    return a


def _make_vault(vault: Path) -> None:
    for d in ["00_Inbox/Raw/2026/06", "00_Inbox/Processed",
              "30_Actions/Tasks", "60_Ideas/Products",
              "80_Assets/Originals/images", "80_Assets/Originals/pdf",
              "80_Assets/Extracts/images", "80_Assets/Extracts/pdf"]:
        (vault / d).mkdir(parents=True, exist_ok=True)


def _add_note(vault: Path, folder: str, title: str, body: str = "") -> Path:
    path = vault / folder / f"{title}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\ntitle: {title}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _add_image_memo(vault: Path, marker_id: str, img_name: str = "photo.jpg") -> tuple[Path, Path]:
    """Create a fake image file + marker for OCR test."""
    img_path = vault / "80_Assets/Originals/images" / img_name
    img_path.write_bytes(b"\xff\xd8\xff\xe0" + b"\x00" * 100)  # minimal JPEG header

    note = _add_note(vault, "30_Actions/Tasks", "image-note")
    att_rel = mem.relative_to_vault(img_path, vault)
    marker = {
        "id": marker_id,
        "raw_type": "raw_image",
        "attachments": [att_rel],
        "structured": mem.relative_to_vault(note, vault),
        "captured_at": "2026-06-14T10:00:00+09:00",
    }
    mpath = vault / "00_Inbox/Processed" / f"{marker_id}.json"
    mpath.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    return mpath, img_path


def _add_pdf_memo(vault: Path, marker_id: str, pdf_name: str = "doc.pdf") -> tuple[Path, Path]:
    """Create a fake PDF file + marker for PDF extraction test."""
    pdf_path = vault / "80_Assets/Originals/pdf" / pdf_name
    pdf_path.write_bytes(b"%PDF-1.4 fake")

    note = _add_note(vault, "60_Ideas/Products", "pdf-note")
    att_rel = mem.relative_to_vault(pdf_path, vault)
    marker = {
        "id": marker_id,
        "raw_type": "raw_pdf",
        "attachments": [att_rel],
        "structured": mem.relative_to_vault(note, vault),
        "captured_at": "2026-06-14T11:00:00+09:00",
    }
    mpath = vault / "00_Inbox/Processed" / f"{marker_id}.json"
    mpath.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")
    return mpath, pdf_path


# ----------------------------------------------------------------- tests

_PASS = 0
_FAIL = 0


def _ok(name: str, cond: bool, msg: str = "") -> None:
    global _PASS, _FAIL
    if cond:
        _PASS += 1
        print(f"PASS  {name}")
    else:
        _FAIL += 1
        print(f"FAIL  {name}" + (f": {msg}" if msg else ""))


def test_image_ocr_extracted():
    """OCR text is staged and marker/note are updated."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        _make_vault(vault)
        mpath, img_path = _add_image_memo(vault, "aabbcc001122")
        enqueued = []

        result = em.extract_media_vault(
            _args(),
            _config(vault),
            extract_image=lambda p, t, m: "영수증 내용: 커피 4500원",
            extract_pdf=lambda p, t, m: None,
            enqueue=lambda n: enqueued.append(n),
        )

        _ok("image_result_extracted", result["extracted"] == 1,
            f"extracted={result['extracted']}")
        _ok("image_enqueued", enqueued == [1], f"enqueued={enqueued}")

        marker = json.loads(mpath.read_text(encoding="utf-8"))
        _ok("image_marker_status", marker["media_extract"]["status"] == "extracted",
            marker.get("media_extract", {}).get("status"))
        _ok("image_marker_method", marker["media_extract"]["method"] == "ocr")

        ext_path = vault / marker["media_extract"]["extract"]
        _ok("image_extract_file_exists", ext_path.exists())
        _ok("image_extract_content", "커피" in ext_path.read_text(encoding="utf-8"))

        note_text = (vault / marker["structured"]).read_text(encoding="utf-8")
        _ok("image_note_has_block", em.MEDIA_BEGIN in note_text)
        _ok("image_note_has_excerpt", "커피" in note_text)


def test_pdf_extracted():
    """PDF text is staged and marker updated."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        _make_vault(vault)
        mpath, pdf_path = _add_pdf_memo(vault, "ddeeffe12345")
        enqueued = []

        result = em.extract_media_vault(
            _args(),
            _config(vault),
            extract_image=lambda p, t, m: None,
            extract_pdf=lambda p, t, m: "PDF 내용: 개인정보 처리방침",
            enqueue=lambda n: enqueued.append(n),
        )

        _ok("pdf_result_extracted", result["extracted"] == 1)
        marker = json.loads(mpath.read_text(encoding="utf-8"))
        _ok("pdf_marker_method", marker["media_extract"]["method"] == "pdf")
        ext_path = vault / marker["media_extract"]["extract"]
        _ok("pdf_extract_content", "개인정보" in ext_path.read_text(encoding="utf-8"))


def test_empty_ocr_marks_empty():
    """When OCR returns None, marker is set to 'empty', not 'extracted'."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        _make_vault(vault)
        mpath, _ = _add_image_memo(vault, "empty000001")

        result = em.extract_media_vault(
            _args(),
            _config(vault),
            extract_image=lambda p, t, m: None,
            extract_pdf=lambda p, t, m: None,
            enqueue=lambda n: None,
        )

        marker = json.loads(mpath.read_text(encoding="utf-8"))
        _ok("empty_status", marker["media_extract"]["status"] == "empty",
            marker.get("media_extract", {}).get("status"))
        _ok("empty_no_extract_key", "extract" not in marker.get("media_extract", {}))
        _ok("empty_not_counted", result["extracted"] == 0)


def test_dry_run_no_changes():
    """--dry-run reports candidates but writes nothing."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        _make_vault(vault)
        mpath, _ = _add_image_memo(vault, "dryrun000001")
        mtime_before = mpath.stat().st_mtime

        result = em.extract_media_vault(
            _args(dry_run=True),
            _config(vault),
            extract_image=lambda p, t, m: "some text",
            extract_pdf=lambda p, t, m: None,
            enqueue=lambda n: None,
        )

        _ok("dry_run_flag", result.get("dry_run") is True)
        _ok("dry_run_count", result.get("count", 0) == 1)
        _ok("dry_run_no_write", mpath.stat().st_mtime == mtime_before)
        marker = json.loads(mpath.read_text(encoding="utf-8"))
        _ok("dry_run_no_marker_update", "media_extract" not in marker)


def test_already_done_skipped():
    """Markers with status 'extracted' are not reprocessed unless --force."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        _make_vault(vault)
        mpath, _ = _add_image_memo(vault, "done000001")
        data = json.loads(mpath.read_text(encoding="utf-8"))
        data["media_extract"] = {"status": "extracted", "method": "ocr"}
        mpath.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        called = []
        result = em.extract_media_vault(
            _args(),
            _config(vault),
            extract_image=lambda p, t, m: called.append(1) or "text",
            extract_pdf=lambda p, t, m: None,
            enqueue=lambda n: None,
        )

        _ok("done_skipped", result["extracted"] == 0 and not called)

        # --force re-processes
        result2 = em.extract_media_vault(
            _args(force=True),
            _config(vault),
            extract_image=lambda p, t, m: "re-extracted text",
            extract_pdf=lambda p, t, m: None,
            enqueue=lambda n: None,
        )
        _ok("force_reprocesses", result2["extracted"] == 1)


def test_no_attachment_skipped():
    """Markers without attachments are silently skipped."""
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp) / "vault"
        _make_vault(vault)
        note = _add_note(vault, "30_Actions/Tasks", "no-att-note")
        marker = {
            "id": "noatt000001",
            "raw_type": "raw_image",
            "attachments": [],
            "structured": mem.relative_to_vault(note, vault),
            "captured_at": "2026-06-14T12:00:00+09:00",
        }
        mpath = vault / "00_Inbox/Processed" / "noatt000001.json"
        mpath.write_text(json.dumps(marker, ensure_ascii=False), encoding="utf-8")

        result = em.extract_media_vault(
            _args(),
            _config(vault),
            extract_image=lambda p, t, m: "text",
            extract_pdf=lambda p, t, m: None,
            enqueue=lambda n: None,
        )
        _ok("no_att_skipped", result["extracted"] == 0)


def test_block_upsert_idempotent():
    """upsert_media_block replaces an existing block without duplicating."""
    original = "---\ntitle: t\n---\n\n본문.\n\n" + em.MEDIA_BEGIN + "\n임시 발췌\n" + em.MEDIA_END + "\n"
    new_block = em.MEDIA_BEGIN + "\n새 요약\n" + em.MEDIA_END
    result = em.upsert_media_block(original, new_block)
    _ok("upsert_only_one_block", result.count(em.MEDIA_BEGIN) == 1)
    _ok("upsert_has_new_content", "새 요약" in result)
    _ok("upsert_no_old_content", "임시 발췌" not in result)


def test_build_media_block_structure():
    """build_media_block generates expected structure."""
    block = em.build_media_block(
        "photo.jpg", "80_Assets/Originals/images/photo.jpg",
        "2026-06-14T10:00:00+09:00",
        "80_Assets/Extracts/images/abc123.txt",
        "ocr", "커피 영수증 내용",
    )
    _ok("block_has_begin", em.MEDIA_BEGIN in block)
    _ok("block_has_end", em.MEDIA_END in block)
    _ok("block_has_label", "이미지 (OCR)" in block)
    _ok("block_has_excerpt", "커피 영수증" in block)
    _ok("block_has_extract_link", "abc123" in block)


# ----------------------------------------------------------------- run

if __name__ == "__main__":
    test_image_ocr_extracted()
    test_pdf_extracted()
    test_empty_ocr_marks_empty()
    test_dry_run_no_changes()
    test_already_done_skipped()
    test_no_attachment_skipped()
    test_block_upsert_idempotent()
    test_build_media_block_structure()

    total = _PASS + _FAIL
    print(f"\n{_PASS}/{total} passed")
    sys.exit(0 if _FAIL == 0 else 1)
