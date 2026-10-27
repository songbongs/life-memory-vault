#!/usr/bin/env python3
"""verify — 처리 결과(노트·요약·링크)가 제자리에 맞게 들어갔는지 채점한다. 읽기 전용.

왜 필요한가 (2026-10-19):
  10-18 23:00 AI 요약 배치에서 `SeeCode …`와 `AI 워터마크 제거 도구`의 요약·핵심
  포인트·제안 태그가 서로 뒤바뀌어 들어갔다. 사진·추출본·Raw는 맞았고, 요약 글만
  엉뚱한 노트에 들어갔다. 10-08 everything-to-discord에 이어 두 번째. 그동안 AI가
  쓴 결과를 기계가 다시 확인하는 단계가 없어서 사용자가 직접 발견할 때까지 몰랐다.

검사 (마커 하나 = 노트 하나 기준):
  - missing_structured / missing_raw: 마커가 가리키는 파일이 없다.
  - source_raw_mismatch: 노트 `source_raw`가 마커의 raw를 가리키지 않는다.
  - enrich_url_mismatch: 노트 enrich 블록 `출처` 주소 중 마커 주소와 같은 것이 없다.
  - raw_url_missing: 마커 주소가 Raw 메모 본문에 없다.
  - asset_missing / asset_link_mismatch: 마커의 사진·추출본 파일이 없거나 노트가 안 가리킨다.
  - summary_mismatch_suspect: 같은 배치(같은 날 같은 시각대에 요약된) 두 노트 A·B에서
    A 요약이 B 원문을, B 요약이 A 원문을 더 닮았다 — 서로 자리가 바뀐 것. 10-18 사례.
    한쪽만 엉뚱한 경우(10-08 everything-to-discord처럼)나 셋 이상이 돌아간 경우는 못 잡는다.
  - summary_low_overlap: 요약 글이 자기 원문과 겹치는 조각이 사실상 없다.
  - duplicate_fm_keys: 프론트매터에 같은 키가 두 번 있다.

닮은 정도: 원문(Raw 설명+추출본+제목+주소)과 요약을 한글 두 글자 조각·영문 단어로
쪼개고, 모든 원문에 흔한 조각(예: '니다')은 가중치를 낮춰(IDF) 겹친 비율을 잰다.
한쪽 방향 비교('다른 원문을 더 닮았나')는 헛경보가 수백 건이었다(2026-10-19 첫 실행 331건,
배치 제한+코사인 후에도 98건). 한국어 요약 대 영어 추출본은 원래 잘 안 겹쳐서다. 그래서
'서로 맞바뀜'만 의심으로 올린다. low_overlap은 '주의'로만 둔다.

등급: SERIOUS(내용이 엉뚱한 곳에 들어갔을 수 있음) / MINOR(정리 상태 문제).
아무것도 고치지 않는다. 결과만 JSON으로 낸다.
"""

from __future__ import annotations

import ast
import datetime as dt
import json
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

ENRICH_BLOCK = re.compile(r"<!-- enrich:begin[^>]*-->(.*?)<!-- enrich:end -->", re.S)
SOURCE_URL = re.compile(r"^>\s*출처:\s*(\S+)", re.M)
EMBED = re.compile(r"!\[\[([^\]|#]+)")
URL = re.compile(r"https?://[^\s)\]>\"'`]+")
HANGUL_RUN = re.compile(r"[가-힣]+")
LATIN_WORD = re.compile(r"[a-z][a-z0-9_+.-]{2,}")
SKIP_LINK = {"merged_into", "duplicate_of"}
EXTRACT_CHARS = 6000

SERIOUS = {"missing_structured", "missing_raw", "enrich_url_mismatch", "raw_url_missing",
           "summary_mismatch_suspect"}

# 채점 기준 (2026-10-19 볼트 전체 실행으로 맞춘 값: 실제 볼트 헛경보 0, 10-18 뒤바뀜 재현 시 검출)
LOW_OVERLAP = 0.003
SWAP_MARGIN = 0.03


def _nfc(s: str | None) -> str:
    return unicodedata.normalize("NFC", s or "")


def _read(path: Path) -> str:
    try:
        return _nfc(path.read_text(encoding="utf-8", errors="ignore"))
    except OSError:
        return ""


def norm_url(url: str) -> str:
    url = _nfc(url).strip().rstrip(".,;)")
    m = re.match(r"(https?://)([^/]+)(.*)$", url, re.I)
    if not m:
        return url.rstrip("/")
    return ("https://" + m.group(2).lower().removeprefix("www.") + m.group(3)).rstrip("/")


def tokens(text: str) -> set[str]:
    text = _nfc(text).lower()
    out: set[str] = set()
    for run in HANGUL_RUN.findall(text):
        out.update(run[i:i + 2] for i in range(len(run) - 1))
    out.update(w.strip(".-") for w in LATIN_WORD.findall(text))
    out.discard("")
    return out


def enrich_blocks(note_text: str) -> list[dict[str, Any]]:
    """노트의 enrich 블록마다 출처 주소·첨부 링크·요약 글을 뽑는다."""
    blocks = []
    for m in ENRICH_BLOCK.finditer(note_text):
        body = m.group(1)
        src = SOURCE_URL.search(body)
        summary = []
        for para in re.split(r"\n\s*\n", body):
            line = para.strip()
            if not line or line.startswith((">", "![[", "<")):
                continue
            if line.startswith("제안 태그"):
                line = re.sub(r"#(\w+)", r"\1", line.replace("제안 태그:", ""))
            summary.append(line)
        blocks.append({
            "url": norm_url(src.group(1)) if src else "",
            "embeds": {_nfc(e).strip() for e in EMBED.findall(body)},
            "summary": "\n".join(summary),
        })
    return blocks


def raw_description(note_text: str) -> str:
    m = re.search(r"## Extracted note\s*\n(.*?)(?:\n## |<!-- enrich:begin|\Z)", note_text, re.S)
    return m.group(1) if m else ""


def frontmatter_dup_keys(note_text: str) -> list[str]:
    m = re.match(r"^---\n(.*?)\n---", note_text, re.S)
    if not m:
        return []
    keys = re.findall(r"^([A-Za-z_][\w-]*):", m.group(1), re.M)
    return sorted(k for k, n in Counter(keys).items() if n > 1)


def _strip_link(value: str) -> str:
    v = re.sub(r"^(?:-\s*)+", "", _nfc(value).strip()).strip().strip('"').strip("'")
    v = re.sub(r"^\[\[|\]\]$", "", v).split("|")[0]
    return v[:-3] if v.endswith(".md") else v


def source_raws(note_text: str) -> list[str]:
    m = re.match(r"^---\n(.*?)\n---", note_text, re.S)
    if not m:
        return []
    fm = m.group(1)
    line = re.search(r"^source_raw:[ \t]*(.*)$((?:\n[ \t]+-.*)*)", fm, re.M)
    if not line:
        return []
    inline = line.group(1).strip()
    items = re.findall(r"^[ \t]+-\s*(.+)$", line.group(2) or "", re.M)
    if inline.startswith("[") and not inline.startswith("[["):
        items += inline.strip("[]").split(",")
    elif inline:
        items.append(inline)
    return [_strip_link(i) for i in items if i.strip()]


def _enrichment(marker: dict[str, Any]) -> dict[str, Any]:
    e = marker.get("enrichment") or {}
    if isinstance(e, str):
        try:
            e = ast.literal_eval(e)
        except (ValueError, SyntaxError):
            e = {}
    return e if isinstance(e, dict) else {}


def _marker_day(marker: dict[str, Any], e: dict[str, Any]) -> str:
    stamps = [e.get("summarized_at"), marker.get("polished_at"), marker.get("processed_at")]
    m = re.search(r"(\d{4}-\d{2}-\d{2})-\d{6}", _nfc(marker.get("raw")))
    if m:
        stamps.append(m.group(1))
    return max((str(s)[:10] for s in stamps if s), default="")


def load_items(vault: Path, processed: Path) -> list[dict[str, Any]]:
    items = []
    for f in sorted(processed.glob("*.json")):
        try:
            marker = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        # structured_deleted: 사용자가 노트를 일부러 지운 기록(10_Daily/사진.md, 2026-08-29)
        if not isinstance(marker, dict) or any(marker.get(k) for k in SKIP_LINK | {"structured_deleted"}):
            continue
        e = _enrichment(marker)
        items.append({
            "marker": f.name,
            "raw": _nfc(marker.get("raw")),
            "structured": _nfc(marker.get("structured")),
            "status": e.get("status"),
            "url": norm_url(e.get("url_normalized") or e.get("url") or ""),
            "url_raw": norm_url(e.get("url") or ""),
            # 깨진 딥링크 대신 다른 주소로 다시 받은 경우(fable-ish-codex README 404 → 저장소 루트)
            "url_fetched": norm_url(e.get("fetched_url") or ""),
            "image": _nfc(e.get("image")),
            "extract": _nfc(e.get("extract")),
            "day": _marker_day(marker, e),
            "batch": str(e.get("summarized_at") or "")[:13],
        })
    return items


def check(vault: Path, items: list[dict[str, Any]], since: str = "") -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []

    def flag(item: dict[str, Any], kind: str, **detail: Any) -> None:
        problems.append({"kind": kind, "level": "SERIOUS" if kind in SERIOUS else "MINOR",
                         "note": item["structured"] or item["raw"],
                         "marker": item["marker"], **detail})

    # 1단계: 파일·링크 검사, 그리고 요약 비교에 쓸 원문/요약 모으기
    refs: dict[str, set[str]] = {}
    summaries: dict[str, tuple[dict[str, Any], set[str]]] = {}
    # 같은 노트를 가리키는 마커들(추가 저장으로 합쳐진 노트) — 형제 마커 주소의 블록이 있으면 통과
    note_urls: dict[str, set[str]] = {}
    for item in items:
        note_urls.setdefault(item["structured"], set()).update(
            u for u in (item["url"], item["url_raw"], item["url_fetched"]) if u)

    for item in items:
        note_path = vault / item["structured"] if item["structured"] else None
        raw_path = vault / item["raw"] if item["raw"] else None
        note_text = _read(note_path) if note_path and note_path.is_file() else ""
        raw_text = _read(raw_path) if raw_path and raw_path.is_file() else ""
        extract_text = ""
        if item["extract"] and (vault / item["extract"]).is_file():
            extract_text = _read(vault / item["extract"])[:EXTRACT_CHARS]
        # 출처 줄 없는 블록은 '이미 정리된 링크' 안내라 비교에서 뺀다
        blocks = [b for b in enrich_blocks(note_text) if b["url"]]
        mine = {u for u in (item["url"], item["url_raw"], item["url_fetched"]) if u}
        own = next((b for b in blocks if b["url"] in mine), None)
        if item["url"]:
            ref_text = " ".join([raw_description(note_text) or raw_text, extract_text,
                                 Path(item["structured"]).stem, item["url"]])
            refs[item["marker"]] = tokens(ref_text)

        if since and item["day"] < since:
            continue
        if not note_text:
            flag(item, "missing_structured")
            continue
        if not raw_text:
            flag(item, "missing_raw")
        elif source_raws(note_text) and _strip_link(item["raw"]) not in source_raws(note_text):
            flag(item, "source_raw_mismatch", source_raw=source_raws(note_text))
        dup = frontmatter_dup_keys(note_text)
        if dup:
            flag(item, "duplicate_fm_keys", keys=dup)
        if not item["url"]:
            continue
        if raw_text and not ({item["url"], item["url_raw"]} & {norm_url(u) for u in URL.findall(raw_text)}):
            flag(item, "raw_url_missing", url=item["url"])
        # skipped·empty 등은 요약 블록을 안 쓰므로 주소 대조 대상이 아니다(Cokacdir install.sh)
        sibling_ok = any(b["url"] in note_urls.get(item["structured"], set()) for b in blocks)
        if blocks and own is None and item["status"] in ("summarized", "extracted") and not sibling_ok:
            flag(item, "enrich_url_mismatch", url=item["url"], block_urls=[b["url"] for b in blocks])
        for key in ("image", "extract"):
            rel = item[key]
            if not rel:
                continue
            if not (vault / rel).is_file():
                flag(item, "asset_missing", asset=rel)
            elif own is not None and not any(_nfc(e).removesuffix(".md") == rel.removesuffix(".md")
                                             for e in own["embeds"]):
                flag(item, "asset_link_mismatch", asset=rel, embeds=sorted(own["embeds"]))
        if own is not None and item["status"] == "summarized" and own["summary"].strip():
            summaries[item["marker"]] = (item, tokens(own["summary"]))

    # 2단계: 같은 배치 안에서 두 요약이 서로 자리를 바꾼 것처럼 보이는지
    df: Counter[str] = Counter()
    for toks in refs.values():
        df.update(toks)
    n = max(len(refs), 1)

    def weight(t: str) -> float:
        return math.log((n + 1) / (df.get(t, 0) + 1)) + 0.1

    ref_w = {m: sum(weight(t) for t in r) for m, r in refs.items()}
    sum_w = {m: sum(weight(t) for t in toks) for m, (_, toks) in summaries.items()}

    def sim(summary_marker: str, ref_marker: str) -> float:
        # 긴 원문이 무엇과도 닮아 보이지 않게 양쪽 크기로 나눈다(코사인)
        denom = math.sqrt(sum_w[summary_marker] * ref_w.get(ref_marker, 0))
        if not denom:
            return 0.0
        common = summaries[summary_marker][1] & refs[ref_marker]
        return sum(weight(t) for t in common) / denom

    keys = [m for m in summaries if m in refs and sum_w[m]]
    for marker in keys:
        if sim(marker, marker) < LOW_OVERLAP:
            item = summaries[marker][0]
            flag(item, "summary_low_overlap", own_score=round(sim(marker, marker), 3))
    for i, a in enumerate(keys):
        item_a = summaries[a][0]
        if not item_a["batch"]:
            continue
        for b in keys[i + 1:]:
            item_b = summaries[b][0]
            if item_b["batch"] != item_a["batch"]:
                continue
            aa, ab, bb, ba = sim(a, a), sim(a, b), sim(b, b), sim(b, a)
            if ab > aa and ba > bb and (ab + ba) - (aa + bb) > SWAP_MARGIN:
                scores = {"own_score": round(aa, 3), "swapped_score": round(ab, 3)}
                flag(item_a, "summary_mismatch_suspect", looks_like=item_b["structured"], **scores)
                scores = {"own_score": round(bb, 3), "swapped_score": round(ba, 3)}
                flag(item_b, "summary_mismatch_suspect", looks_like=item_a["structured"], **scores)
    return problems


def verify(args: Any, config: dict[str, Any]) -> dict[str, Any]:
    mv = config["memoryVault"]
    vault = Path(mv["vaultPath"])
    processed = vault / mv.get("processedFolder", "00_Inbox/Processed")
    since = ""
    if getattr(args, "days", None):
        since = (dt.date.today() - dt.timedelta(days=args.days)).isoformat()
    if getattr(args, "since", None):
        since = args.since
    items = load_items(vault, processed)
    problems = sorted(check(vault, items, since), key=lambda p: (p["level"] != "SERIOUS", p["kind"], p["note"]))
    counts = Counter(p["kind"] for p in problems)
    result = {
        "checked": sum(1 for i in items if not since or i["day"] >= since),
        "since": since or "all",
        "problems": len(problems),
        "serious": sum(1 for p in problems if p["level"] == "SERIOUS"),
        "by_kind": dict(sorted(counts.items())),
        "items": problems if getattr(args, "verbose", False) else problems[:30],
    }
    out = getattr(args, "json", None)
    if out:
        Path(out).write_text(json.dumps({**result, "items": problems}, ensure_ascii=False, indent=2),
                             encoding="utf-8")
        result["report"] = out
    return result
