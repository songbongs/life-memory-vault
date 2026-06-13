#!/usr/bin/env python3
"""Media content extraction (④ phase).

For each memo whose attachment is an image, PDF, or audio file, extract
machine-readable text and stage it as a .txt file in 80_Assets/Extracts/.

Pipeline (mirrors enrich.py):
  1. find candidates  — markers with attachments but no media_extract (or --force)
  2. extract_*        — tesseract (image) / pdfplumber (PDF) / stub (audio)
  3. write extract    — 80_Assets/Extracts/{images|pdf|audio}/<marker-id>.txt
  4. update marker    — media_extract.status = "extracted"
  5. update note      — <!-- media-extract:begin --> block with excerpt
  6. enqueue job      — "media-enrich" for 23:00 AI summary batch

Design:
- Raw notes are never touched.
- Only the media-extract block is written in the structured note.
- Idempotent: re-running skips already-extracted markers unless --force.
- Extract backends are injectable for tests (no subprocess/pdfplumber in tests).
- HEIC: macOS sips converts to JPEG before tesseract.
- pdfplumber: imported lazily; graceful no-op if missing.
- audio: stub only — returns None until whisper integration is added.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path
from typing import Any, Callable

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import mem  # noqa: E402  (reuse vault_path/parse_frontmatter/atomic_write_text/rel/now_local)

ROOT = mem.ROOT
JOBS_PY = SCRIPTS / "jobs.py"

MEDIA_BEGIN = "<!-- media-extract:begin v1 -->"
MEDIA_END = "<!-- media-extract:end -->"
MEDIA_BLOCK_RE = re.compile(r"<!-- media-extract:begin.*?<!-- media-extract:end -->", re.DOTALL)

IMAGE_EXTS = frozenset({".jpg", ".jpeg", ".png", ".webp", ".heic", ".bmp", ".tiff", ".tif"})
PDF_EXTS = frozenset({".pdf"})
AUDIO_EXTS = frozenset({".mp3", ".m4a", ".wav", ".ogg", ".opus", ".flac"})
ALL_MEDIA_EXTS = IMAGE_EXTS | PDF_EXTS | AUDIO_EXTS

DONE_STATUSES = frozenset({"extracted", "skipped", "empty", "failed"})
EXCERPT_CHARS = 500


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def _now_iso() -> str:
    return mem.now_local().isoformat(timespec="seconds")


def _yymmdd(iso_or_empty: str) -> str:
    import datetime as dt
    try:
        return dt.date.fromisoformat((iso_or_empty or "")[:10]).strftime("%y.%m.%d")
    except ValueError:
        return mem.now_local().strftime("%y.%m.%d")


# ----------------------------------------------------------------- extraction backends

def _heic_to_jpeg(src: Path, dest: Path) -> bool:
    """Convert HEIC to JPEG using macOS sips. Returns True on success."""
    try:
        r = subprocess.run(
            ["sips", "-s", "format", "jpeg", str(src), "--out", str(dest)],
            capture_output=True, timeout=30,
        )
        return r.returncode == 0 and dest.exists()
    except Exception:  # noqa: BLE001
        return False


def default_extract_image(file_path: Path, tools_config: dict[str, Any], max_chars: int = 8000) -> str | None:
    """OCR an image via tesseract (kor+eng). Converts HEIC first via sips."""
    cmd = tools_config.get("tesseract", "tesseract")
    src = file_path
    tmp_jpeg: Path | None = None

    if file_path.suffix.lower() == ".heic":
        tmp_jpeg = Path(tempfile.mktemp(suffix=".jpg"))
        if not _heic_to_jpeg(file_path, tmp_jpeg):
            return None
        src = tmp_jpeg

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            out_base = Path(tmpdir) / "ocr"
            r = subprocess.run(
                [cmd, str(src), str(out_base), "-l", "kor+eng"],
                capture_output=True, timeout=90,
            )
            out_txt = out_base.with_suffix(".txt")
            if r.returncode != 0 or not out_txt.exists():
                return None
            text = out_txt.read_text(encoding="utf-8", errors="ignore").strip()
            return text[:max_chars] if text else None
    except Exception:  # noqa: BLE001
        return None
    finally:
        if tmp_jpeg and tmp_jpeg.exists():
            tmp_jpeg.unlink(missing_ok=True)


def default_extract_pdf(file_path: Path, tools_config: dict[str, Any], max_chars: int = 8000) -> str | None:
    """Extract text from PDF via pdfplumber. Graceful no-op if not installed."""
    try:
        import pdfplumber  # noqa: PLC0415
    except ImportError:
        return None
    try:
        with pdfplumber.open(str(file_path)) as pdf:
            parts = [t.strip() for page in pdf.pages if (t := page.extract_text())]
            text = "\n\n".join(parts).strip()
            return text[:max_chars] if text else None
    except Exception:  # noqa: BLE001
        return None


def default_extract_audio(_file_path: Path, _tools_config: dict[str, Any], _max_chars: int = 8000) -> str | None:
    """Audio transcription stub — returns None until whisper integration is added."""
    return None


def default_enqueue(count: int) -> None:
    """Enqueue ONE media-enrich job so the AI batch summarises staged extracts."""
    try:
        subprocess.run(
            [sys.executable, str(JOBS_PY), "add", "media-enrich",
             "--text", f"{count} staged media extract(s) to summarize",
             "--adapter", "codex", "--source", "extract-media", "--requested-by", "system"],
            cwd=str(ROOT), check=False, capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass


# ----------------------------------------------------------------- block helpers

def _type_label(ext: str) -> str:
    if ext in IMAGE_EXTS:
        return "이미지 (OCR)"
    if ext in PDF_EXTS:
        return "PDF 텍스트"
    if ext in AUDIO_EXTS:
        return "음성 전사"
    return "파일"


def build_media_block(file_name: str, file_rel: str, captured_at: str,
                      extract_rel: str, method: str, excerpt: str) -> str:
    label = _type_label(Path(file_name).suffix.lower())
    date_str = _yymmdd(captured_at)
    excerpt_text = (excerpt or "").strip()[:EXCERPT_CHARS].strip()
    link = extract_rel[:-4] if extract_rel.endswith(".txt") else extract_rel
    lines = [
        MEDIA_BEGIN,
        f"> [!abstract] {label} — {file_name}",
        f"> 파일: [[{file_rel}]] · 추출 {date_str} · 방법: {method}",
        "",
        excerpt_text if excerpt_text else "(텍스트 추출 결과 없음 — AI 요약 단계에서 확인 예정)",
        "",
        "> [!note]- 원문 전체 (추출본)",
        f"> ![[{link}]]",
        MEDIA_END,
    ]
    return "\n".join(lines)


def upsert_media_block(note_text: str, block: str) -> str:
    """Replace existing media-extract block, or append one. Nothing else is modified."""
    if MEDIA_BLOCK_RE.search(note_text):
        return MEDIA_BLOCK_RE.sub(lambda _m: block, note_text, count=1)
    if note_text.endswith("\n\n"):
        sep = ""
    elif note_text.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    return note_text + sep + block + "\n"


# ----------------------------------------------------------------- main

def extract_media_vault(
    args: object,
    config: dict[str, Any],
    extract_image: Callable[[Path, dict, int], str | None] | None = None,
    extract_pdf: Callable[[Path, dict, int], str | None] | None = None,
    extract_audio: Callable[[Path, dict, int], str | None] | None = None,
    enqueue: Callable[[int], None] | None = None,
) -> dict[str, Any]:
    vault = mem.vault_path(config)
    med_cfg = config.get("mediaExtraction", {})
    tools_cfg = config.get("tools", {})
    max_chars = int(med_cfg.get("maxExtractChars", 8000))
    enable_ocr = bool(med_cfg.get("enableOcr", True))
    enable_pdf = bool(med_cfg.get("enablePdf", True))
    enable_audio = bool(med_cfg.get("enableAudio", False))
    assets = mem.rel(config, "assetsFolder", "80_Assets")

    limit = getattr(args, "limit", 3)
    take_all = getattr(args, "all", False)
    force = getattr(args, "force", False)
    dry_run = getattr(args, "dry_run", False)

    extract_image = extract_image or default_extract_image
    extract_pdf = extract_pdf or default_extract_pdf
    extract_audio = extract_audio or default_extract_audio
    enqueue = enqueue or default_enqueue

    processed_dir = vault / mem.rel(config, "processedFolder", "00_Inbox/Processed")

    candidates: list[dict[str, Any]] = []
    if processed_dir.exists():
        for marker_path in sorted(processed_dir.glob("*.json")):
            try:
                data = json.loads(marker_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            if data.get("duplicate_of"):
                continue
            raw_type = data.get("raw_type", "")
            if raw_type not in {"raw_image", "raw_pdf", "raw_audio"}:
                continue
            med_ex = data.get("media_extract", {})
            if not force and med_ex.get("status") in DONE_STATUSES:
                continue
            atts = data.get("attachments", [])
            if not atts:
                continue
            att_rel = _nfc(str(atts[0]))
            att_path = vault / att_rel
            if not att_path.exists():
                continue
            ext = att_path.suffix.lower()
            if ext in IMAGE_EXTS and not enable_ocr:
                continue
            if ext in PDF_EXTS and not enable_pdf:
                continue
            if ext in AUDIO_EXTS and not enable_audio:
                continue
            if ext not in ALL_MEDIA_EXTS:
                continue
            structured = _nfc(data.get("structured", ""))
            if not structured:
                continue
            candidates.append({
                "marker_path": marker_path,
                "marker_data": data,
                "att_path": att_path,
                "att_rel": att_rel,
                "ext": ext,
                "structured": structured,
            })

    if not take_all:
        candidates = candidates[:limit]

    if dry_run:
        return {
            "dry_run": True,
            "candidates": [c["marker_path"].name for c in candidates],
            "count": len(candidates),
        }

    results = []
    staged = 0

    for cand in candidates:
        marker_path: Path = cand["marker_path"]
        marker_data: dict[str, Any] = cand["marker_data"]
        att_path: Path = cand["att_path"]
        att_rel: str = cand["att_rel"]
        ext: str = cand["ext"]
        structured_rel: str = cand["structured"]
        marker_id = marker_path.stem

        if ext in IMAGE_EXTS:
            method = "ocr"
            text = extract_image(att_path, tools_cfg, max_chars)
        elif ext in PDF_EXTS:
            method = "pdf"
            text = extract_pdf(att_path, tools_cfg, max_chars)
        else:
            method = "audio"
            text = extract_audio(att_path, tools_cfg, max_chars)

        marker_data.setdefault("media_extract", {})

        if not text:
            marker_data["media_extract"].update({
                "status": "empty",
                "method": method,
                "extracted_at": _now_iso(),
            })
            mem.atomic_write_text(marker_path, json.dumps(marker_data, ensure_ascii=False, indent=2))
            results.append({"marker": marker_id, "status": "empty", "method": method})
            continue

        # Stage extract file
        type_subdir = {"ocr": "images", "pdf": "pdf", "audio": "audio"}[method]
        extracts_dir = vault / assets / "Extracts" / type_subdir
        extracts_dir.mkdir(parents=True, exist_ok=True)
        extract_path = extracts_dir / f"{marker_id}.txt"
        mem.atomic_write_text(extract_path, text)
        extract_rel = mem.relative_to_vault(extract_path, vault)

        # Upsert media-extract block in structured note
        structured_path = vault / _nfc(structured_rel)
        if structured_path.exists():
            note_text = structured_path.read_text(encoding="utf-8")
            captured_at = marker_data.get("captured_at", "")
            block = build_media_block(
                att_path.name, att_rel, captured_at,
                extract_rel, method, text,
            )
            new_text = upsert_media_block(note_text, block)
            if new_text != note_text:
                mem.atomic_write_text(structured_path, new_text)

        # Update marker
        marker_data["media_extract"].update({
            "status": "extracted",
            "method": method,
            "extract": extract_rel,
            "extracted_at": _now_iso(),
        })
        mem.atomic_write_text(marker_path, json.dumps(marker_data, ensure_ascii=False, indent=2))
        results.append({"marker": marker_id, "status": "extracted", "method": method, "extract": extract_rel})
        staged += 1

    if staged > 0:
        enqueue(staged)

    return {"extracted": staged, "total_candidates": len(candidates), "results": results}
