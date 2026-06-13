#!/usr/bin/env python3
"""URL enrichment core (Track A, phase A1).

For each memo whose raw note contains a URL, fetch the page, extract title /
representative image / body excerpt, and write them into the structured note as
an IDEMPOTENT block delimited by `<!-- enrich:begin ... -->` / `<!-- enrich:end -->`.

Design invariants (do not violate):
- Raw notes are never touched.
- Only the enrich block is written in the structured note. Everything outside the
  block — including frontmatter — is byte-for-byte preserved. (v1 writes no frontmatter.)
- Idempotent: re-running replaces the block in place; the marker `enrichment.status`
  guards against reprocessing.
- Deterministic extraction here (trafilatura); AI summary is phase A2.
- All path/marker comparisons are NFC-normalized (macOS NFD filenames vs NFC JSON).
- trafilatura is imported lazily (only the default fetch/extract paths need it), so
  this module imports fine without it; the real `enrich` command gates on doctor's
  dependency check and exits 2 with an install hint if it is missing.

Tested via injected fetch/extract/download_image (no network). See tests/test_enrich.py.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

SCRIPTS = Path(__file__).resolve().parent
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))
import mem  # noqa: E402  (reuse vault_path/parse_frontmatter/atomic_write_text/rel/now_local)

ROOT = mem.ROOT
JOBS_PY = SCRIPTS / "jobs.py"

URL_RE = re.compile(r"https?://[^\s)\]>\"'`]+")
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "igshid", "ref_src", "ref", "spm", "mc_cid", "mc_eid",
}
ENRICH_BEGIN = "<!-- enrich:begin v1 -->"
ENRICH_END = "<!-- enrich:end -->"
# Version-agnostic matcher so a future v2 block is still found and replaced.
ENRICH_BLOCK_RE = re.compile(r"<!-- enrich:begin.*?<!-- enrich:end -->", re.DOTALL)
# Marker statuses that mean "already handled" — skipped unless --force.
DONE_STATUSES = {"summarized", "extracted", "skipped", "empty", "duplicate_url"}
IMAGE_EXT = {"image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
             "image/webp": ".webp", "image/gif": ".gif"}
EXCERPT_CHARS = 500
MIN_BODY_CHARS = 200


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def now_iso() -> str:
    return mem.now_local().isoformat(timespec="seconds")


def yymmdd(iso_or_empty: str) -> str:
    """captured_at ISO -> 'YY.MM.DD'; fall back to today if unparseable."""
    import datetime as dt
    try:
        return dt.date.fromisoformat((iso_or_empty or "")[:10]).strftime("%y.%m.%d")
    except ValueError:
        return mem.now_local().strftime("%y.%m.%d")


# --------------------------------------------------------------------------- URLs
def all_urls(text: str) -> list[str]:
    return [u.rstrip(".,);:") for u in URL_RE.findall(text or "")]


def first_url(text: str) -> str:
    urls = all_urls(text)
    return urls[0] if urls else ""


def normalize_url(url: str) -> str:
    """Lowercase host, drop tracking params and fragment. Used as the dedup key."""
    try:
        p = urlsplit(url)
        q = [(k, v) for k, v in parse_qsl(p.query) if k.lower() not in TRACKING_PARAMS]
        return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path, urlencode(q), ""))
    except ValueError:
        return url


# ---------------------------------------------------------------- default backends
def _default_fetch(url: str, timeout: int) -> str | None:
    import trafilatura
    return trafilatura.fetch_url(url)


def _og_image_fallback(html: str) -> str | None:
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.img: str | None = None

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            if tag != "meta" or self.img:
                return
            a = {k.lower(): (v or "") for k, v in attrs}
            key = (a.get("property") or a.get("name") or "").lower()
            if key in ("og:image", "twitter:image", "og:image:url") and a.get("content"):
                self.img = a["content"]

    parser = _P()
    try:
        parser.feed(html or "")
    except Exception:  # noqa: BLE001  malformed HTML must not crash enrich
        pass
    return parser.img


def _default_extract(html: str, url: str, max_chars: int) -> dict[str, Any]:
    import trafilatura
    body = trafilatura.extract(html, url=url, output_format="markdown", with_metadata=False) or ""
    meta = trafilatura.extract_metadata(html, default_url=url)
    title = getattr(meta, "title", None) if meta else None
    sitename = getattr(meta, "sitename", None) if meta else None
    image = (getattr(meta, "image", None) if meta else None) or _og_image_fallback(html)
    description = getattr(meta, "description", None) if meta else None
    return {
        "title": title, "sitename": sitename, "image": image,
        "description": description, "body": body[:max_chars],
    }


def _default_download_image(image_url: str, dest_dir: Path, url_norm: str, max_bytes: int) -> str | None:
    """Download an image to dest_dir/<sha1(url_norm)[:12]>.<ext>. Returns filename or None.

    Only image/* content types are kept; oversize is discarded. Filename is an ASCII
    hash of the PAGE url_norm (one image per page) so re-runs overwrite, not pile up.
    """
    import urllib.request
    req = urllib.request.Request(image_url, headers={"User-Agent": "Mozilla/5.0 (life-memory enrich)"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
            ext = IMAGE_EXT.get(ctype)
            if not ext:
                return None
            data = resp.read(max_bytes + 1)
            if len(data) > max_bytes:
                return None
    except Exception:  # noqa: BLE001  network/IO failure -> just skip the image
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = hashlib.sha1(url_norm.encode("utf-8")).hexdigest()[:12] + ext
    (dest_dir / fname).write_bytes(data)
    return fname


# --------------------------------------------------------------------- youtube
def is_youtube(url: str) -> bool:
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return False
    return host.endswith("youtube.com") or host.endswith("youtu.be")


def _vtt_to_text(vtt: str, max_chars: int) -> str:
    """VTT subtitle -> plain text (drop timestamps, tags, duplicate lines)."""
    lines: list[str] = []
    seen: set[str] = set()
    for ln in vtt.splitlines():
        ln = ln.strip()
        if not ln or "-->" in ln or ln.startswith(("WEBVTT", "Kind:", "Language:")):
            continue
        ln = re.sub(r"<[^>]+>", "", ln)
        ln = re.sub(r"\[.*?\]", "", ln).strip()
        if ln and ln not in seen:
            seen.add(ln)
            lines.append(ln)
    return " ".join(lines)[:max_chars]


def _default_youtube_extract(url: str, max_chars: int) -> dict[str, Any]:
    """yt-dlp: YouTube metadata + subtitles (prefer manual ko>en, else auto)."""
    import subprocess
    import tempfile
    empty = {"title": None, "sitename": None, "image": None, "description": None, "body": ""}
    try:
        p = subprocess.run(["yt-dlp", "--skip-download", "--dump-json", url],
                           capture_output=True, text=True, timeout=90)
        if p.returncode != 0 or not p.stdout:
            return empty
        j = json.loads(p.stdout)
    except Exception:  # noqa: BLE001
        return empty
    channel = j.get("channel") or j.get("uploader") or ""
    desc = j.get("description") or ""
    subs, autos = j.get("subtitles") or {}, j.get("automatic_captions") or {}
    lang, auto = None, True
    for code in ("ko", "en"):
        if code in subs:
            lang, auto = code, False
            break
    if lang is None:
        for code in ("ko", "en"):
            if code in autos:
                lang, auto = code, True
                break
    body = ""
    if lang:
        with tempfile.TemporaryDirectory() as td:
            cmd = ["yt-dlp", "--skip-download",
                   "--write-auto-subs" if auto else "--write-subs",
                   "--sub-langs", lang, "--sub-format", "vtt",
                   "-o", f"{td}/%(id)s.%(ext)s", url]
            try:
                subprocess.run(cmd, capture_output=True, timeout=150)
            except Exception:  # noqa: BLE001
                pass
            vtts = sorted(Path(td).glob("*.vtt"))
            if vtts:
                body = _vtt_to_text(vtts[0].read_text(encoding="utf-8", errors="ignore"), max_chars)
    if not body:
        body = desc[:max_chars]
    return {"title": j.get("title"), "sitename": "YouTube" + (f" · {channel}" if channel else ""),
            "image": j.get("thumbnail"), "description": desc[:200], "body": body}


def _default_archive_page(url: str, dest_dir: Path, url_norm: str) -> str | None:
    """Archive the full page as a single HTML via monolith. None if not installed (graceful)."""
    import shutil as _sh
    import subprocess
    if not _sh.which("monolith"):
        return None
    dest_dir.mkdir(parents=True, exist_ok=True)
    fname = hashlib.sha1(url_norm.encode("utf-8")).hexdigest()[:12] + ".html"
    try:
        p = subprocess.run(["monolith", url, "-o", str(dest_dir / fname)],
                           capture_output=True, timeout=60)
        if p.returncode == 0 and (dest_dir / fname).exists():
            return fname
    except Exception:  # noqa: BLE001
        pass
    return None


# ------------------------------------------------------------------- summary job
def _default_enqueue(count: int) -> None:
    """Enqueue ONE enrich job so the 23:00 AI batch summarizes the staged bodies.

    One job per run (not per page) to avoid job spam; the AI prompt drains all
    staged files. Best-effort: a queue failure must not fail the extraction.
    """
    import subprocess
    try:
        subprocess.run(
            [sys.executable, str(JOBS_PY), "add", "enrich",
             "--text", f"{count} staged page(s) to summarize",
             "--adapter", "codex", "--source", "enrich", "--requested-by", "system"],
            cwd=str(ROOT), check=False, capture_output=True,
        )
    except Exception:  # noqa: BLE001
        pass


# ------------------------------------------------------------------- note block
def build_block(title: str, url: str, sitename: str, captured_at: str,
                image_rel: str | None, body: str, extract_rel: str | None = None,
                archive_rel: str | None = None) -> str:
    src = [url]
    if sitename:
        src.append(sitename)
    src.append(f"수집 {yymmdd(captured_at)}")
    lines = [ENRICH_BEGIN, f"> [!abstract] 웹 페이지 — {title}", "> 출처: " + " · ".join(src), ""]
    if image_rel:
        lines += [f"![[{image_rel}]]", ""]
    excerpt = (body or "").strip()[:EXCERPT_CHARS].strip()
    lines.append(excerpt if excerpt else "(본문 추출 결과 없음 — A2에서 요약 예정)")
    if extract_rel:
        # (B) Collapsed link to the full original, archived in the vault (survives link rot).
        link = extract_rel[:-3] if extract_rel.endswith(".md") else extract_rel
        lines += ["", "> [!note]- 원문 전체 (추출본)", f"> ![[{link}]]"]
    if archive_rel:
        # (A4) Link to the full-page snapshot (monolith HTML); kept as a plain link.
        lines += ["", "> [!info]- 페이지 보관본 (전문 HTML)", f"> [[{archive_rel}]]"]
    lines.append(ENRICH_END)
    return "\n".join(lines)


def build_duplicate_block(url: str, other_structured: str) -> str:
    other = other_structured[:-3] if other_structured.endswith(".md") else other_structured
    return "\n".join([
        ENRICH_BEGIN,
        "> [!info] 이미 정리된 링크",
        f"> {url} 은(는) [[{other}]] 에 정리되어 있습니다.",
        ENRICH_END,
    ])


def upsert_block(note_text: str, block: str) -> str:
    """Replace an existing enrich block, or append one. Nothing else is modified."""
    if ENRICH_BLOCK_RE.search(note_text):
        # lambda avoids backreference/escape interpretation of `block`
        return ENRICH_BLOCK_RE.sub(lambda _m: block, note_text, count=1)
    if note_text.endswith("\n\n"):
        sep = ""
    elif note_text.endswith("\n"):
        sep = "\n"
    else:
        sep = "\n\n"
    return note_text + sep + block + "\n"


# --------------------------------------------------------------------------- marker
def write_marker(path: Path, data: dict[str, Any]) -> None:
    mem.atomic_write_text(path, json.dumps(data, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- main
def enrich_vault(
    args: argparse.Namespace,
    config: dict[str, Any],
    fetch: Callable[[str, int], str | None] | None = None,
    extract: Callable[[str, str, int], dict[str, Any]] | None = None,
    download_image: Callable[[str, Path, str, int], str | None] | None = None,
    enqueue: Callable[[int], None] | None = None,
    youtube_extract: Callable[[str, int], dict[str, Any]] | None = None,
    archive_page: Callable[[str, Path, str], str | None] | None = None,
) -> dict[str, Any]:
    vault = mem.vault_path(config)
    enr = config.get("enrichment", {})
    timeout = int(enr.get("timeoutSeconds", 20))
    max_chars = int(enr.get("maxExtractChars", 8000))
    max_img = int(enr.get("imageMaxBytes", 5242880))
    optout_tags = enr.get("optOutTags", []) or []
    assets = mem.rel(config, "assetsFolder", "80_Assets")
    subdir = enr.get("assetsSubdir", "Web")
    extracts_subdir = enr.get("extractsSubdir", "Extracts")
    extracts_dir = vault / assets / extracts_subdir
    archive_pages = bool(enr.get("archivePages", False))  # A4: monolith 전문 박제(설치+토글 시)
    archive_subdir = enr.get("archiveSubdir", "Archive")
    archive_dir = vault / assets / archive_subdir
    processed = vault / mem.rel(config, "processedFolder", "00_Inbox/Processed")

    # --status listing mode: read-only, no enrichment performed.
    status_filter = getattr(args, "status", None)
    if status_filter:
        results = []
        if processed.exists():
            for jp in sorted(processed.glob("*.json")):
                try:
                    d = json.loads(jp.read_text(encoding="utf-8"))
                except (ValueError, OSError):
                    continue
                e = d.get("enrichment") or {}
                if e.get("status") == status_filter:
                    results.append({
                        "marker": jp.name,
                        "structured": d.get("structured", ""),
                        "url": e.get("url", ""),
                        "attempts": int(e.get("attempts", 0)),
                        "error": str(e.get("error", "")),
                        "updated_at": d.get("updated_at", ""),
                    })
        out = {"status_filter": status_filter, "count": len(results), "markers": results}
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    limit = getattr(args, "limit", 5)
    take_all = getattr(args, "all", False)
    force = getattr(args, "force", False)
    dry_run = getattr(args, "dry_run", False)

    # Real run needs trafilatura; injected backends (tests) skip the gate.
    if fetch is None and extract is None and not dry_run:
        if not mem.enrichment_dependency_status()["trafilatura"]:
            out = {"error": "trafilatura_missing",
                   "hint": "python3 -m pip install --user --break-system-packages trafilatura"}
            print(json.dumps(out, ensure_ascii=False))
            raise SystemExit(2)
    fetch = fetch or _default_fetch
    extract = extract or _default_extract
    download_image = download_image or _default_download_image
    youtube_extract = youtube_extract or _default_youtube_extract
    archive_page = archive_page or _default_archive_page

    # Pass 1: load markers, remember already-summarized URLs for dedup.
    markers: list[tuple[Path, dict[str, Any]]] = []
    summarized_urls: dict[str, str] = {}
    if processed.exists():
        for jp in sorted(processed.glob("*.json")):
            try:
                d = json.loads(jp.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            markers.append((jp, d))
            e = d.get("enrichment") or {}
            if e.get("status") == "summarized" and e.get("url_normalized"):
                summarized_urls[nfc(e["url_normalized"])] = nfc(d.get("structured", ""))

    # Pass 2: pick candidates.
    candidates: list[dict[str, Any]] = []
    optouts: list[tuple[Path, dict[str, Any], str]] = []
    for jp, d in markers:
        structured = d.get("structured")
        raw_rel = d.get("raw")
        if not structured or not raw_rel:  # duplicate marker or unprocessed
            continue
        e = d.get("enrichment") or {}
        if e and not force:
            st = e.get("status")
            if st in DONE_STATUSES:
                continue
            if st == "failed" and int(e.get("attempts", 0)) >= 3:
                continue
        raw_path = vault / raw_rel
        if not raw_path.exists():
            continue
        raw_text = raw_path.read_text(encoding="utf-8", errors="ignore")
        _meta, raw_body = mem.parse_frontmatter(raw_text)
        urls = all_urls(raw_body)
        if not urls:
            continue
        if any(tag in raw_text for tag in optout_tags):
            optouts.append((jp, d, urls[0]))
            continue
        candidates.append({
            "jp": jp, "d": d, "structured": structured, "url": urls[0],
            "extra_urls": urls[1:], "captured_at": _meta.get("captured_at", ""),
        })

    if dry_run:
        would = len(candidates) if take_all else min(limit, len(candidates))
        out = {
            "dry_run": True,
            "candidates": [{"raw": c["jp"].name, "url": c["url"], "structured": c["structured"]}
                           for c in candidates],
            "total": len(candidates),
            "would_process": would,
            "opt_out": len(optouts),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return out

    counts = {"enriched": 0, "empty": 0, "failed": 0, "duplicate_url": 0, "skipped": 0}

    # Record opt-outs so they are not re-scanned every run.
    for jp, d, url in optouts:
        d["enrichment"] = {"status": "skipped", "reason": "opt_out",
                           "url": url, "enriched_at": now_iso()}
        write_marker(jp, d)
        counts["skipped"] += 1

    todo = candidates if take_all else candidates[:limit]
    seen_urls = dict(summarized_urls)

    for c in todo:
        jp, d, structured = c["jp"], c["d"], c["structured"]
        url = c["url"]
        url_norm = nfc(normalize_url(url))
        struct_path = vault / structured
        prev_attempts = int((d.get("enrichment") or {}).get("attempts", 0))

        # Duplicate of an already-summarized page elsewhere.
        if url_norm in seen_urls and seen_urls[url_norm] != nfc(structured):
            if struct_path.exists():
                note_text = struct_path.read_text(encoding="utf-8")
                mem.atomic_write_text(struct_path, upsert_block(note_text,
                                      build_duplicate_block(url, seen_urls[url_norm])))
            d["enrichment"] = {"status": "duplicate_url", "url": url, "url_normalized": url_norm,
                               "duplicate_of": seen_urls[url_norm], "enriched_at": now_iso(),
                               "method": "trafilatura", "attempts": prev_attempts}
            write_marker(jp, d)
            counts["duplicate_url"] += 1
            continue

        attempts = prev_attempts + 1
        # YouTube -> yt-dlp (metadata + subtitles); everything else -> fetch + trafilatura.
        if is_youtube(url):
            method = "yt-dlp"
            try:
                info = youtube_extract(url, max_chars)
            except Exception:  # noqa: BLE001
                info = None
        else:
            method = "trafilatura"
            try:
                html = fetch(url, timeout)
            except Exception:  # noqa: BLE001
                html = None
            info = extract(html, url, max_chars) if html else None

        if not info or not (info.get("body") or info.get("title") or info.get("image")):
            d["enrichment"] = {"status": "failed", "url": url, "url_normalized": url_norm,
                               "attempts": attempts, "method": method, "enriched_at": now_iso()}
            write_marker(jp, d)
            counts["failed"] += 1
            continue

        body = info.get("body") or ""
        title = info.get("title") or url
        sitename = info.get("sitename") or ""

        image_rel = None
        if info.get("image"):
            fname = download_image(info["image"], vault / assets / subdir, url_norm, max_img)
            if fname:
                image_rel = f"{assets}/{subdir}/{fname}"

        is_empty = len(body) < MIN_BODY_CHARS and not info.get("title") and not image_rel
        status = "empty" if is_empty else "extracted"

        # (B) Archive the extracted full body PERMANENTLY in the vault — survives link
        # rot, and is also the A2 Korean-summary input. Never deleted (unlike a temp stage).
        extract_rel = None
        if body:
            extracts_dir.mkdir(parents=True, exist_ok=True)
            mem.atomic_write_text(extracts_dir / f"{jp.stem}.md", body)
            extract_rel = f"{assets}/{extracts_subdir}/{jp.stem}.md"

        # (A4) Optional full-page archive via monolith — only when enabled AND installed,
        # and not for YouTube. No-op/None otherwise (graceful).
        archive_rel = None
        if archive_pages and status == "extracted" and method != "yt-dlp":
            try:
                afname = archive_page(url, archive_dir, url_norm)
            except Exception:  # noqa: BLE001
                afname = None
            if afname:
                archive_rel = f"{assets}/{archive_subdir}/{afname}"

        block = build_block(title, url, sitename, c["captured_at"], image_rel, body, extract_rel, archive_rel)
        if struct_path.exists():
            note_text = struct_path.read_text(encoding="utf-8")
            mem.atomic_write_text(struct_path, upsert_block(note_text, block))

        d["enrichment"] = {
            "status": status, "enriched_at": now_iso(), "url": url, "url_normalized": url_norm,
            "image": image_rel or "", "extract": extract_rel or "", "archive": archive_rel or "",
            "method": method, "attempts": attempts, "extra_urls": c["extra_urls"],
        }
        write_marker(jp, d)
        seen_urls[url_norm] = nfc(structured)
        counts["enriched" if status == "extracted" else "empty"] += 1

    # One AI-summary job per run when new bodies were staged (extracted > 0).
    if counts["enriched"] > 0:
        (enqueue or _default_enqueue)(counts["enriched"])

    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return counts
