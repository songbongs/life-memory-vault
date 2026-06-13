#!/usr/bin/env python3
"""Life Memory Vault MVP CLI.

This script is intentionally local-first and API-free. It captures raw records,
creates lightweight deterministic structure, searches the vault, and reports
tool readiness for the MacBook/Mac mini transition.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "memory-config.json"
EXAMPLE_CONFIG = ROOT / "memory-config.example.json"


FOLDER_LAYOUT = [
    "00_Inbox/Raw",
    "00_Inbox/Processed",
    "00_Inbox/Review",
    "10_Timeline/Daily",
    "10_Timeline/Weekly",
    "10_Timeline/Monthly",
    "20_Records/Ledger",
    "20_Records/Health",
    "20_Records/Routine",
    "20_Records/Maintenance",
    "20_Records/LifeAdmin",
    "30_Actions/Tasks",
    "30_Actions/Shopping",
    "30_Actions/Appointments",
    "30_Actions/Reminders",
    "30_Actions/Decisions",
    "40_Entities/People",
    "40_Entities/Groups",
    "40_Entities/Places",
    "40_Entities/Things",
    "40_Entities/Situations",
    "40_Entities/Artists",
    "40_Entities/Songs",
    "40_Entities/Albums",
    "50_Experiences/Trips",
    "50_Experiences/Food_Drink",
    "50_Experiences/Events",
    "50_Experiences/Visits",
    "50_Experiences/Music/Listening_Log",
    "50_Experiences/Music/Concerts",
    "60_Ideas/Projects",
    "60_Ideas/Writing",
    "60_Ideas/Products",
    "60_Ideas/Questions",
    "60_Ideas/Playlists",
    "70_MOCs",
    "80_Assets/Originals/pdf",
    "80_Assets/Originals/images",
    "80_Assets/Originals/audio",
    "80_Assets/Originals/video",
    "80_Assets/Extracts/pdf",
    "80_Assets/Extracts/images",
    "80_Assets/Extracts/audio",
    "80_Assets/Extracts/video",
    "80_Assets/Thumbnails",
    "80_Assets/Keyframes",
    "90_System/Schemas",
    "90_System/Rules",
    "90_System/Templates",
    "90_System/Logs",
    "90_System/Prompts",
]


CHARTER = """# Memory Charter

This vault exists to remove friction from personal memory.

Mission:
- Capture fragmented memories from mobile, laptop, and AI environments with minimal effort.
- Preserve raw records without mutation.
- Let agents structure, link, lint, and retrieve the memories without adding burden to the user.
- Make memories easy to reuse from Obsidian, coding agents, and future MCP clients.

Operating principles:
- Capture first. Do not ask the user to classify at capture time.
- Raw is sacred. Never edit raw inbox notes; write processed markers or structured notes instead.
- Local and free first. Prefer local tools and subscription-based agent runs over metered APIs.
- Sensitive by default. Mark private memories clearly and avoid broad remote write access.
- Alert on friction. If the workflow becomes harder to use, report the friction and propose a simpler path.
"""


MEMORY_SCHEMA = """# Memory Schema

Raw note fields:
- id
- captured_at
- source
- raw_type
- status
- sensitivity
- source_url
- attachments
- hashtags (inline tags parsed from text: #private, #urgent, #task, etc.)

Structured note fields:
- memory_type
- source_raw
- confidence
- needs_review
- context
- sensitivity
- tags (list, for cross-search)
- related (list of [[wikilinks]] to related notes)
- updated_at (last modified by lint or repair)
- lint_method ("rule_based" or "ai")
- entity_refs (list of entity note paths referenced)

Common memory_type values:
- journal
- ledger
- task
- appointment
- purchase
- maintenance
- person
- group
- place
- thing
- situation
- trip
- food_drink
- artist
- song
- album
- playlist
- listening_log
- idea
- decision
"""


MUSIC_MOC = """# Music MOC

## Playlists

## Artists

## Songs

## Albums

## Listening Log

## Concerts
"""


LIFE_MEMORY_MOC = """# Life Memory MOC

전체 vault의 진입점이다. 카테고리별 MOC 링크와 주요 노트 목록을 유지한다.
AI lint가 새 노트를 추가할 때마다 이 문서의 관련 섹션을 업데이트한다.

## 카테고리별 MOC

- [[70_MOCs/Music-MOC|Music MOC]] — 음악, 아티스트, 플레이리스트, 청취 기록
- [[70_MOCs/Maintenance-MOC|Maintenance MOC]] — 차량, 가전, 집 유지보수/교체 기록
- [[70_MOCs/Food-MOC|Food MOC]] — 맛집, 카페, 음식 경험
- [[70_MOCs/People-MOC|People MOC]] — 사람, 관계, 그룹
- [[70_MOCs/Travel-MOC|Travel MOC]] — 여행, 방문, 장소 경험
- [[70_MOCs/Ideas-MOC|Ideas MOC]] — 아이디어, 서비스, 프로젝트 구상
- [[70_MOCs/Health-MOC|Health MOC]] — 건강, 병원, 약
- [[70_MOCs/Tasks-MOC|Tasks MOC]] — 할 일, 약속, 결정

## 최근 추가된 노트

<!-- AI lint가 새 노트 생성 시 이 섹션에 항목 추가 (최신순, 최대 20개 유지) -->

## Vault 검색 가이드

검색 전 docs/vault-index.md를 확인해서 관련 폴더를 먼저 파악할 것.
"""


MAINTENANCE_MOC = """# Maintenance MOC

차량, 가전, 집, 기기 등 유지보수 및 교체 기록 전체 진입점.

## 차량

<!-- 차량 관련 유지보수 노트 -->

## 가전/기기

<!-- 가전 및 전자기기 유지보수 노트 -->

## 집/시설

<!-- 집 관련 유지보수 노트 -->
"""


TOOL_POLICY = """# Local Tool Policy

Default order:
1. Lightweight local parsers: pdfplumber, pdftext, youtube-transcript-api, yt-dlp
2. Marker for complex PDF to Markdown conversion
3. PaddleOCR or PaddleOCR MCP for images, scans, receipts, and Korean OCR
4. Microsoft MarkItDown for broad office/document to Markdown conversion
5. OpenDataLoader PDF for reading order, tables, and bounding boxes
6. kordoc MCP for HWP/HWPX/HWPML and Korean public documents

Paid APIs are off by default. Subscription agent runs may be scheduled, but they still consume plan usage limits.
"""


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise SystemExit(f"Missing config: {path}. Copy memory-config.example.json to memory-config.json.")
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def vault_path(config: dict[str, Any]) -> Path:
    value = config.get("memoryVault", {}).get("vaultPath", "")
    if not value or value == "/path/to/your/memory/vault":
        raise SystemExit("memoryVault.vaultPath is not configured.")
    return Path(value).expanduser()


def rel(config: dict[str, Any], key: str, default: str) -> str:
    return config.get("memoryVault", {}).get(key, default)


def now_local() -> dt.datetime:
    return dt.datetime.now().astimezone()


def stamp() -> str:
    return now_local().strftime("%Y-%m-%d-%H%M%S")


def yaml_scalar(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def frontmatter(fields: dict[str, Any]) -> str:
    lines = ["---"]
    for key, value in fields.items():
        if value is None or value == "":
            continue
        if isinstance(value, list) and not value:
            continue
        if isinstance(value, bool):
            lines.append(f"{key}: {'true' if value else 'false'}")
        elif isinstance(value, (int, float)):
            lines.append(f"{key}: {value}")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - {yaml_scalar(str(item))}")
        else:
            lines.append(f"{key}: {yaml_scalar(str(value))}")
    lines.append("---")
    return "\n".join(lines) + "\n\n"


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse YAML-ish frontmatter. Scalars stay strings; a `key:` with no value
    followed by `  - item` lines becomes a list (round-trips with frontmatter())."""
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end == -1:
        return {}, text
    raw = text[4:end].strip().splitlines()
    data: dict[str, Any] = {}
    list_key: str | None = None
    for line in raw:
        if list_key is not None and re.match(r"^\s+-\s+", line):
            data[list_key].append(re.sub(r"^\s+-\s+", "", line).strip().strip('"'))
            continue
        if ":" not in line or line.startswith((" ", "\t")):
            list_key = None
            continue
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if value == "":
            # frontmatter() only emits an empty-value key as a (non-empty) list header
            data[key] = []
            list_key = key
        else:
            data[key] = value.strip('"')
            list_key = None
    return data, text[end + 4 :].lstrip()


def safe_name(text: str, fallback: str = "memory") -> str:
    text = re.sub(r"https?://", "", text)
    text = re.sub(r"[\\/:*?\"<>|#\[\]\n\r\t]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    text = text[:80].strip(" .")
    return text or fallback


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def atomic_write_text(path: Path, content: str) -> None:
    """Write text atomically: write to a temp file in the same directory, then os.replace.

    Prevents partial/corrupt files if the process is interrupted mid-write.
    The temp file lives in the same dir so os.replace stays on one filesystem.
    """
    ensure_parent(path)
    tmp = path.with_name(f".{path.name}.tmp.{os.getpid()}")
    try:
        tmp.write_text(content, encoding="utf-8")
        os.replace(tmp, path)
    finally:
        if tmp.exists():
            tmp.unlink(missing_ok=True)


def write_if_missing(path: Path, content: str) -> bool:
    if path.exists():
        return False
    atomic_write_text(path, content)
    return True


def relative_to_vault(path: Path, vault: Path) -> str:
    return path.relative_to(vault).as_posix()


def note_link(path: Path, vault: Path) -> str:
    rel_path = relative_to_vault(path, vault)
    if rel_path.endswith(".md"):
        rel_path = rel_path[:-3]
    return f"[[{rel_path}]]"


def init_vault(config: dict[str, Any]) -> None:
    vault = vault_path(config)
    created_dirs = 0
    for folder in FOLDER_LAYOUT:
        path = vault / folder
        if not path.exists():
            path.mkdir(parents=True, exist_ok=True)
            created_dirs += 1

    files = {
        "90_System/Memory Charter.md": CHARTER,
        "90_System/Schemas/Memory Schema.md": MEMORY_SCHEMA,
        "90_System/Rules/Local Tool Policy.md": TOOL_POLICY,
        "70_MOCs/Music-MOC.md": MUSIC_MOC,
        "70_MOCs/Life-Memory-MOC.md": LIFE_MEMORY_MOC,
        "70_MOCs/Maintenance-MOC.md": MAINTENANCE_MOC,
        "70_MOCs/Food-MOC.md": "# Food MOC\n\n맛집, 카페, 베이커리, 음식 경험 전체 진입점.\n\n## 맛집\n\n## 카페\n\n## 베이커리\n\n## 기타 음식 경험\n",
        "70_MOCs/People-MOC.md": "# People MOC\n\n사람, 관계, 그룹 전체 진입점.\n\n## 사람\n\n## 그룹/조직\n",
        "70_MOCs/Travel-MOC.md": "# Travel MOC\n\n여행, 방문, 장소 경험 전체 진입점.\n\n## 여행\n\n## 방문\n",
        "70_MOCs/Ideas-MOC.md": "# Ideas MOC\n\n아이디어, 서비스, 프로젝트 구상 전체 진입점.\n\n## 써보고 싶은 서비스/앱\n\n## 프로젝트 아이디어\n\n## 글쓰기\n\n## 질문\n",
        "70_MOCs/Health-MOC.md": "# Health MOC\n\n건강, 병원, 약, 검진 전체 진입점.\n\n## 병원 방문\n\n## 약/처방\n\n## 건강 기록\n",
        "70_MOCs/Tasks-MOC.md": "# Tasks MOC\n\n할 일, 약속, 결정 전체 진입점.\n\n## 할 일\n\n## 약속/예약\n\n## 결정\n",
    }
    created_files = 0
    for rel_path, content in files.items():
        if write_if_missing(vault / rel_path, content):
            created_files += 1

    print(json.dumps({"vault": str(vault), "created_dirs": created_dirs, "created_files": created_files}, ensure_ascii=False, indent=2))


def infer_raw_type(text: str, source_url: str | None, file_path: Path | None) -> str:
    target = " ".join([text, source_url or "", str(file_path or "")]).lower()
    if file_path:
        suffix = file_path.suffix.lower()
        if suffix in {".pdf"}:
            return "raw_pdf"
        if suffix in {".png", ".jpg", ".jpeg", ".heic", ".webp"}:
            return "raw_image"
        if suffix in {".mp3", ".m4a", ".wav", ".ogg", ".opus"}:
            return "raw_audio"
        if suffix in {".mp4", ".mov", ".mkv", ".webm"}:
            return "raw_video"
        return "raw_file"
    if "youtube.com" in target or "youtu.be" in target or "music.youtube.com" in target:
        return "raw_youtube"
    if source_url or re.search(r"https?://", target):
        return "raw_url"
    return "raw_text"


def copy_attachment(config: dict[str, Any], vault: Path, file_path: Path, raw_type: str) -> str:
    if not file_path.exists():
        raise SystemExit(f"Attachment not found: {file_path}")
    size = file_path.stat().st_size
    archive = config.get("archive", {})
    large_file = int(archive.get("largeFileBytes", 104857600))
    large_video = int(archive.get("largeVideoBytes", 52428800))
    is_video = raw_type == "raw_video"
    if size > (large_video if is_video else large_file):
        return f"external:{file_path}"

    assets = rel(config, "assetsFolder", "80_Assets")
    kind = {
        "raw_pdf": "pdf",
        "raw_image": "images",
        "raw_audio": "audio",
        "raw_video": "video",
    }.get(raw_type, "files")
    dest = vault / assets / "Originals" / kind / now_local().strftime("%Y/%m") / file_path.name
    ensure_parent(dest)
    if dest.exists():
        digest = hashlib.sha1(str(file_path).encode("utf-8")).hexdigest()[:8]
        dest = dest.with_name(f"{dest.stem}-{digest}{dest.suffix}")
    shutil.copy2(file_path, dest)
    return relative_to_vault(dest, vault)


HASHTAG_SENSITIVITY = {"private", "비공개", "민감"}
HASHTAG_TYPE_HINTS = {
    "task": "task", "할일": "task", "todo": "task",
    "maintenance": "maintenance", "교체": "maintenance", "정비": "maintenance",
    "purchase": "purchase", "구매": "purchase",
    "health": "health", "병원": "health", "약": "health",
    "food": "food_drink", "맛집": "food_drink", "카페": "food_drink",
    "idea": "idea", "아이디어": "idea",
    "trip": "trip", "여행": "trip",
    "music": "listening_log", "음악": "listening_log",
}


def parse_hashtags(text: str) -> tuple[list[str], str | None, str | None]:
    """Extract #hashtags from text. Returns (tags, sensitivity_override, type_hint)."""
    found = re.findall(r"#([\w가-힣]+)", text)
    tags = [t.lower() for t in found]
    sensitivity = "private" if any(t in HASHTAG_SENSITIVITY for t in tags) else None
    type_hint = next((HASHTAG_TYPE_HINTS[t] for t in tags if t in HASHTAG_TYPE_HINTS), None)
    return tags, sensitivity, type_hint


def save_raw(args: argparse.Namespace, config: dict[str, Any]) -> None:
    vault = vault_path(config)
    raw_folder = rel(config, "rawFolder", "00_Inbox/Raw")
    text = args.text or ""
    if not text and not sys.stdin.isatty():
        text = sys.stdin.read().strip()
    source_url = args.url
    file_path = Path(args.file).expanduser() if args.file else None
    raw_type = args.raw_type or infer_raw_type(text, source_url, file_path)
    attachments: list[str] = []
    if file_path:
        attachments.append(copy_attachment(config, vault, file_path, raw_type))

    hashtags, sensitivity_override, _type_hint = parse_hashtags(text)
    sensitivity = sensitivity_override or args.sensitivity

    captured = now_local().isoformat(timespec="seconds")
    if args.title or source_url or text:
        title_seed = args.title or source_url or (text.splitlines()[0] if text else "")
    else:
        title_seed = raw_type
    title = safe_name(str(title_seed), raw_type)
    path = vault / raw_folder / now_local().strftime("%Y/%m") / f"{stamp()}-{title}.md"
    record_id = hashlib.sha1(f"{captured}:{title}:{text}:{source_url}".encode("utf-8")).hexdigest()[:12]
    body = []
    if text:
        body.append(text)
    if source_url:
        body.append(f"Source URL: {source_url}")
    if attachments:
        body.append("Attachments:")
        body.extend(f"- [[{item}]]" if not item.startswith("external:") else f"- {item}" for item in attachments)

    content = frontmatter(
        {
            "id": record_id,
            "captured_at": captured,
            "source": args.source,
            "raw_type": raw_type,
            "status": "pending",
            "sensitivity": sensitivity,
            "source_url": source_url,
            "attachments": attachments,
            "hashtags": hashtags,
        }
    ) + "\n\n".join(body).strip() + "\n"
    atomic_write_text(path, content)
    print(json.dumps({"saved": relative_to_vault(path, vault), "id": record_id, "raw_type": raw_type, "hashtags": hashtags, "sensitivity": sensitivity}, ensure_ascii=False, indent=2))


MUSIC_URL_SIGNALS = ["music.youtube.com", "music.apple.com", "spotify.com", "soundcloud.com"]
MUSIC_SIGNALS = MUSIC_URL_SIGNALS + [
    "노래", "곡", "song", "artist", "아티스트", "앨범", "album",
    "playlist", "플레이리스트", "음악", "#music", "#음악",
]

FOLDER_BY_TYPE = {
    "task": "30_Actions/Tasks", "appointment": "30_Actions/Appointments",
    "purchase": "30_Actions/Shopping", "decision": "30_Actions/Decisions",
    "maintenance": "20_Records/Maintenance", "ledger": "20_Records/Ledger",
    "health": "20_Records/Health", "person": "40_Entities/People",
    "place": "40_Entities/Places", "thing": "40_Entities/Things",
    "artist": "40_Entities/Artists", "song": "40_Entities/Songs",
    "album": "40_Entities/Albums", "trip": "50_Experiences/Trips",
    "food_drink": "50_Experiences/Food_Drink",
    "listening_log": "50_Experiences/Music/Listening_Log",
    "playlist": "60_Ideas/Playlists", "product": "60_Ideas/Products",
    "idea": "60_Ideas/Projects", "journal": "10_Timeline/Daily",
}


def match_learned_rule(combined_lower: str, rules: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Return the most specific active learned rule whose signal occurs in text, or None.

    rules: list of {signal(normalized lowercase), type, folder}. None/empty -> no match,
    so classify() with no rules behaves exactly as before (③d additive guarantee).
    """
    if not rules:
        return None
    for rule in sorted(rules, key=lambda r: len(r.get("signal", "")), reverse=True):
        signal = rule.get("signal", "")
        if signal and signal in combined_lower:
            return rule
    return None


def classify(text: str, meta: dict[str, str], rules: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    lower = text.lower()
    source_url = meta.get("source_url", "")
    combined = f"{lower} {source_url.lower()}"
    text_without_urls = re.sub(r"https?://\S+", " ", lower)
    first_line = text.strip().splitlines()[0] if text.strip() else ""
    # "Artist - Title" 형태의 음악 메모 힌트. 그 자체로는 song을 확정하지 않고,
    # 아래 음악 분기에서 다른 음악 신호와 결합될 때만 song 확신을 높이는 데 쓴다.
    dash_pattern = bool(re.match(r"^\s*.+?\s+-\s+.+\s*$", first_line))
    has_music_signal = any(k in combined for k in MUSIC_SIGNALS)
    has_music_url = any(u in combined for u in MUSIC_URL_SIGNALS)
    # 명시적 "할 일" 신호. github 링크가 task를 product로 가로채지 않도록 가드로 쓴다.
    has_action = any(k in combined for k in ["할일", "todo", "to-do", "해야", "task"])

    result = {"memory_type": "journal", "folder": "10_Timeline/Daily", "needs_review": False, "confidence": "medium"}
    # 학습된 규칙(③d) 선패스: 사용자 확인으로 승격된 signal이 매치되면 그 분류로 확정한다.
    # rules가 None/빈 리스트면 아래 키워드 분기로 흘러가 기존 동작과 100% 동일하다.
    matched = match_learned_rule(combined, rules)
    if matched is not None:
        folder = matched.get("folder") or FOLDER_BY_TYPE.get(matched["type"], result["folder"])
        result.update({"memory_type": matched["type"], "folder": folder, "confidence": "high", "needs_review": False})
    # 명시적 키워드를 음악보다 먼저 평가한다. 과거에는 " - " 패턴이 최우선이어서
    # "엄마 - 병원 예약" 같은 일반 메모가 song으로 오분류되고 가짜 엔티티가 생성됐다.
    elif not has_action and ("github.com" in combined or (meta.get("raw_type") == "raw_url" and any(k in combined for k in ["서비스", "사용해볼", "써볼", "나중에", "tool", "app", "web service", "설치", "라이브러리", "오픈소스", "repo"]))):
        # 저장해 둔 도구·서비스·리포(github 등) → "써볼 것" 성격이라 product. 단 "할일" 신호가 있으면 task가 우선.
        result.update({"memory_type": "product", "folder": "60_Ideas/Products"})
    elif any(k in text_without_urls for k in ["구매", "샀", "쇼핑", "장바구니", "shopping", "price"]) or re.search(r"\d[\d,]*\s*원", text_without_urls):
        result.update({"memory_type": "purchase", "folder": "30_Actions/Shopping"})
    elif any(k in combined for k in ["교체", "정비", "수리", "maintenance", "replace"]):
        result.update({"memory_type": "maintenance", "folder": "20_Records/Maintenance"})
    elif any(k in combined for k in ["할일", "todo", "to-do", "해야", "task", "송금", "reminder", "리마인더"]):
        result.update({"memory_type": "task", "folder": "30_Actions/Tasks"})
    elif any(k in combined for k in ["예약", "약속", "일정", "appointment", "meeting"]):
        result.update({"memory_type": "appointment", "folder": "30_Actions/Appointments"})
    elif any(k in combined for k in ["카페", "맛집", "식당", "restaurant", "cafe", "bakery"]):
        result.update({"memory_type": "food_drink", "folder": "50_Experiences/Food_Drink"})
    elif any(k in combined for k in ["여행", "trip", "travel"]):
        result.update({"memory_type": "trip", "folder": "50_Experiences/Trips"})
    elif any(k in combined for k in ["아이디어", "idea"]):
        result.update({"memory_type": "idea", "folder": "60_Ideas/Projects"})
    elif has_music_signal:
        # 음악은 명시적 신호(음악 URL / 음악 키워드 / #음악 태그)가 있을 때만 분류한다.
        if "playlist" in combined or "플레이리스트" in combined:
            result.update({"memory_type": "playlist", "folder": "60_Ideas/Playlists", "confidence": "medium"})
        else:
            # 음악 URL이나 "Artist - Title" 패턴이 동반되면 확신을 높이고,
            # 단순 음악 키워드만 있으면 low로 두어 AI lint가 재검토하게 한다.
            confidence = "medium" if (has_music_url or dash_pattern) else "low"
            result.update({"memory_type": "song", "folder": "60_Ideas/Playlists", "confidence": confidence})
    if meta.get("raw_type") in {"raw_pdf", "raw_image", "raw_audio", "raw_video"}:
        result["needs_review"] = True
        result["confidence"] = "low"
    return result


def extract_artist_song(text: str) -> tuple[str | None, str | None]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    first = lines[0] if lines else text.strip()
    patterns = [
        r"^(.+?)\s+-\s+(.+)$",
        r"^(.+?)\s+--\s+(.+)$",
        r"^(.+?)\s+:\s+(.+)$",
    ]
    for pattern in patterns:
        match = re.match(pattern, first)
        if match:
            return safe_name(match.group(1), "artist"), safe_name(match.group(2), "song")
    return None, safe_name(first, "song") if first else None


def create_structured_note(vault: Path, folder: str, title: str, fields: dict[str, Any], body: str, on_conflict: str = "append") -> Path:
    """Write a structured note.

    on_conflict:
      "append"  - accumulate into the existing file (entity pages: artist/song).
      "unique"  - one file per distinct note. If a file with the same title already
                  exists but belongs to a *different* source_raw, write a hash-suffixed
                  file instead of merging two unrelated notes (title-collision fix).
                  Same source_raw -> overwrite in place (idempotent re-lint).
    """
    path = vault / folder / f"{safe_name(title)}.md"
    if on_conflict == "unique" and path.exists():
        existing = path.read_text(encoding="utf-8")
        source_raw = str(fields.get("source_raw", ""))
        if not (source_raw and source_raw in existing):
            digest = hashlib.sha1((source_raw or body).encode("utf-8")).hexdigest()[:6]
            path = path.with_name(f"{path.stem}-{digest}{path.suffix}")
        atomic_write_text(path, frontmatter(fields) + body.strip() + "\n")
        return path
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if body not in existing:
            atomic_write_text(path, existing.rstrip() + "\n\n" + body + "\n")
    else:
        atomic_write_text(path, frontmatter(fields) + body.strip() + "\n")
    return path


def load_active_rules(args: argparse.Namespace, config: dict[str, Any]) -> list[dict[str, Any]]:
    """Load promoted learned rules (③d) to feed classify. Never fatal: any
    problem yields [] so lint behaves exactly as before learning existed."""
    if not config.get("learning", {}).get("enabled", True):
        return []
    try:
        import rules as rules_mod  # scripts/ is on sys.path when run as a script
        return rules_mod.from_config(args.config).active_rules()
    except Exception:
        return []


def content_hash(body: str) -> str:
    """Hash of the meaningful content (whitespace/case-normalized) for dedup."""
    return hashlib.sha1(" ".join(body.split()).lower().encode("utf-8")).hexdigest()[:16]


_REL_DAY = {"오늘": 0, "금일": 0, "내일": 1, "명일": 1, "모레": 2, "어제": -1, "엊그제": -2, "그저께": -2}
_REL_MONTH = {"지지난달": -2, "지난달": -1, "이번달": 0, "이달": 0, "다음달": 1, "담달": 1}
_REL_YEAR = {"재작년": -2, "작년": -1, "올해": 0, "금년": 0, "내년": 1, "명년": 1}


def _ymd2(year: int, month: int, day: int) -> str:
    return f"{year % 100:02d}.{month:02d}.{day:02d}"


def _shift_month(year: int, month: int, off: int) -> tuple[int, int]:
    idx = year * 12 + (month - 1) + off
    return idx // 12, idx % 12 + 1


def normalize_dates(text: str, ref: dt.date) -> list[str]:
    """Resolve dates mentioned in text to absolute YY.MM.DD, relative to capture date `ref`.

    - bare M/D or M월 D일 (no year) -> ref's year
    - bare D일 (no month) -> ref's year+month
    - relative words (오늘/내일/어제, 지난달/다음달 +D일, 작년/내년 +M월D일) -> resolved from ref
    Enriches records without mutating the raw. Best-effort; unknown forms are skipped.
    """
    out: set[str] = set()
    for word, off in _REL_DAY.items():
        if word in text:
            d = ref + dt.timedelta(days=off)
            out.add(_ymd2(d.year, d.month, d.day))
    for word, off in _REL_YEAR.items():
        for m, d in re.findall(re.escape(word) + r"\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일", text):
            m, d = int(m), int(d)
            if 1 <= m <= 12 and 1 <= d <= 31:
                out.add(_ymd2(ref.year + off, m, d))
    for word, off in _REL_MONTH.items():
        for d in re.findall(re.escape(word) + r"\s*(\d{1,2})\s*일", text):
            d = int(d)
            if 1 <= d <= 31:
                y, m = _shift_month(ref.year, ref.month, off)
                out.add(_ymd2(y, m, d))
    # Strip relative-prefixed forms so the absolute passes below don't re-count them
    # (e.g. "작년 3월 2일" must not also yield this year's 3월 2일).
    residual = re.sub(r"(?:재작년|작년|올해|금년|내년|명년)\s*\d{1,2}\s*월\s*\d{1,2}\s*일", "  ", text)
    residual = re.sub(r"(?:지지난달|지난달|이번달|이달|다음달|담달)\s*\d{1,2}\s*일", "  ", residual)
    for m, d in re.findall(r"(\d{1,2})\s*월\s*(\d{1,2})\s*일", residual):
        m, d = int(m), int(d)
        if 1 <= m <= 12 and 1 <= d <= 31:
            out.add(_ymd2(ref.year, m, d))
    for m, d in re.findall(r"(?<!\d)(\d{1,2})\s*/\s*(\d{1,2})(?!\d)", residual):
        m, d = int(m), int(d)
        if 1 <= m <= 12 and 1 <= d <= 31:
            out.add(_ymd2(ref.year, m, d))
    # day-only: further strip absolute M월D일 / M/D to avoid wrong-month duplicates
    day_only = re.sub(r"\d{1,2}\s*월\s*\d{1,2}\s*일", "  ", residual)
    day_only = re.sub(r"(?<!\d)\d{1,2}\s*/\s*\d{1,2}(?!\d)", "  ", day_only)
    for d in re.findall(r"(?<![\d/])(\d{1,2})\s*일(?!\s*(?:간|째|동안|치))", day_only):
        d = int(d)
        if 1 <= d <= 31:
            out.add(_ymd2(ref.year, ref.month, d))
    return sorted(out)


def lint_vault(args: argparse.Namespace, config: dict[str, Any]) -> None:
    vault = vault_path(config)
    raw_root = vault / rel(config, "rawFolder", "00_Inbox/Raw")
    processed_root = vault / rel(config, "processedFolder", "00_Inbox/Processed")
    if not raw_root.exists():
        print(json.dumps({"processed": 0, "message": "raw folder missing"}, ensure_ascii=False, indent=2))
        return
    active_rules = load_active_rules(args, config)
    # content_hash -> {structured, raw}: first note per identical content (dedup).
    seen: dict[str, dict[str, str]] = {}
    if processed_root.exists():
        for mk in processed_root.glob("*.json"):
            try:
                d = json.loads(mk.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            ch, st = d.get("content_hash"), d.get("structured")
            if ch and st and not d.get("duplicate_of"):
                seen.setdefault(ch, {"structured": st, "raw": d.get("raw", "")})
    processed = 0
    duplicates = 0
    for raw_path in sorted(raw_root.rglob("*.md")):
        raw_rel = relative_to_vault(raw_path, vault)
        raw_id = hashlib.sha1(raw_rel.encode("utf-8")).hexdigest()[:16]
        marker = processed_root / f"{raw_id}.json"
        if marker.exists() and not args.force:
            continue
        text = raw_path.read_text(encoding="utf-8")
        meta, body = parse_frontmatter(text)

        # Dedup: identical content already structured by a *different* raw -> mark duplicate, skip note.
        chash = content_hash(body)
        prior = seen.get(chash)
        if prior and prior["raw"] != raw_rel:
            atomic_write_text(marker, json.dumps({
                "raw": raw_rel,
                "duplicate_of": prior["structured"],
                "content_hash": chash,
                "processed_at": now_local().isoformat(timespec="seconds"),
                "lint_method": "rule_based",
                "plan": {"memory_type": "duplicate", "folder": "", "confidence": "high", "needs_review": False},
            }, ensure_ascii=False, indent=2))
            duplicates += 1
            continue

        plan = classify(body, meta, active_rules)
        raw_link = note_link(raw_path, vault)
        ref_date = now_local().date()
        captured = meta.get("captured_at", "")
        if captured:
            try:
                ref_date = dt.datetime.fromisoformat(captured).date()
            except ValueError:
                pass
        base_fields = {
            "memory_type": plan["memory_type"],
            "source_raw": raw_link,
            "confidence": plan["confidence"],
            "needs_review": plan["needs_review"],
            "sensitivity": meta.get("sensitivity", "normal"),
            "dates": normalize_dates(body, ref_date),
        }
        title = safe_name(body.splitlines()[0] if body.splitlines() else raw_path.stem, plan["memory_type"])
        entities_updated: list[str] = []
        if plan["memory_type"] in {"song", "playlist"}:
            artist, song = extract_artist_song(body)
            if artist:
                ap = create_structured_note(vault, "40_Entities/Artists", artist, {"memory_type": "artist", "source_raw": raw_link}, f"# {artist}\n\n## Related raw\n\n- {raw_link}")
                entities_updated.append(relative_to_vault(ap, vault))
            if song:
                sp = create_structured_note(vault, "40_Entities/Songs", song, {"memory_type": "song", "artist": artist or "", "source_raw": raw_link}, f"# {song}\n\n## Source\n\n- {raw_link}")
                entities_updated.append(relative_to_vault(sp, vault))
            title = title if plan["memory_type"] == "playlist" else song or title
        structured_body = f"# {title}\n\n## Source\n\n- {raw_link}\n\n## Extracted note\n\n{body.strip()}\n"
        note_path = create_structured_note(vault, str(plan["folder"]), title, base_fields, structured_body, on_conflict="unique")
        structured_rel = relative_to_vault(note_path, vault)
        seen.setdefault(chash, {"structured": structured_rel, "raw": raw_rel})
        atomic_write_text(
            marker,
            json.dumps(
                {
                    "raw": raw_rel,
                    "structured": structured_rel,
                    "content_hash": chash,
                    "processed_at": now_local().isoformat(timespec="seconds"),
                    "lint_method": "rule_based",
                    "plan": plan,
                    "entities_updated": entities_updated,
                    "links_added": [],
                    "mocs_updated": [],
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
        processed += 1
    print(json.dumps({"processed": processed, "duplicates": duplicates}, ensure_ascii=False, indent=2))


def extract_search_tags(text: str) -> set[str]:
    """Tags for search: frontmatter `tags:` list values + inline #hashtags (lowercased)."""
    tags: set[str] = set()
    if text.startswith("---\n"):
        end = text.find("\n---", 4)
        fm = text[4:end] if end != -1 else ""
        in_tags = False
        for line in fm.splitlines():
            if re.match(r"^tags:\s*$", line):
                in_tags = True
                continue
            if in_tags:
                m = re.match(r'^\s+-\s*"?(.+?)"?\s*$', line)
                if m:
                    tags.add(m.group(1).lower())
                elif not line.startswith((" ", "\t")):
                    in_tags = False
    for h in re.findall(r"#([\w가-힣]+)", text):
        tags.add(h.lower())
    return tags


def make_snippet(text: str, lower: str, tokens: list[str]) -> str:
    idx = -1
    for token in tokens:
        i = lower.find(token)
        if i != -1:
            idx = i
            break
    idx = max(idx, 0)
    start = max(0, idx - 120)
    end = min(len(text), idx + 180)
    return re.sub(r"\s+", " ", text[start:end]).strip()


def seek(args: argparse.Namespace, config: dict[str, Any]) -> None:
    vault = vault_path(config)
    tokens = [t for t in args.query.lower().split() if t]
    type_filter = (getattr(args, "type", "") or "").lower()
    tag_filter = (getattr(args, "tag", "") or "").lower()
    since = getattr(args, "since", "") or ""
    limit = args.limit

    results = []
    for path in vault.rglob("*.md"):
        if any(part.startswith(".") for part in path.relative_to(vault).parts):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        meta, body = parse_frontmatter(text)
        memory_type = meta.get("memory_type", "").lower()
        note_tags = extract_search_tags(text)
        note_date = meta.get("updated_at") or meta.get("captured_at") or ""

        # filters
        if type_filter and memory_type != type_filter:
            continue
        if tag_filter and tag_filter not in note_tags:
            continue
        if since and (not note_date or note_date[:len(since)] < since):
            continue

        lower = text.lower()
        # scoring: distinct tokens matched dominates; title/tag presence boosts.
        distinct = sum(1 for t in tokens if t in lower)
        if tokens and distinct == 0:
            continue
        title = f"{path.stem} {body.splitlines()[0] if body.splitlines() else ''}".lower()
        tags_joined = " ".join(note_tags)
        score = distinct * 10 + sum(1 for t in tokens if t in title) * 5 + sum(1 for t in tokens if t in tags_joined) * 3
        results.append({
            "path": relative_to_vault(path, vault),
            "score": score,
            "date": note_date,
            "memory_type": memory_type,
            "snippet": make_snippet(text, lower, tokens),
        })

    results.sort(key=lambda r: (r["score"], r["date"]), reverse=True)
    hits = results[:limit] if limit else results
    print(json.dumps({"query": args.query, "hits": hits, "total": len(results)}, ensure_ascii=False, indent=2))


_HOME_STATS_BEGIN = "<!-- stats:begin -->"
_HOME_STATS_END = "<!-- stats:end -->"


def home_update(config: dict[str, Any]) -> None:
    """Update the stats block in 90_System/홈.md with current digest numbers."""
    vault = vault_path(config)
    home = vault / "90_System" / "홈.md"
    if not home.exists():
        print(json.dumps({"skipped": "홈.md not found", "path": str(home)}, ensure_ascii=False, indent=2))
        return

    processed_root = vault / rel(config, "processedFolder", "00_Inbox/Processed")
    raw_root = vault / rel(config, "rawFolder", "00_Inbox/Raw")
    raw_count = len(list(raw_root.rglob("*.md"))) if raw_root.exists() else 0
    enr_total = enr_summarized = enr_failed = 0
    for mk in (processed_root.rglob("*.json") if processed_root.exists() else []):
        try:
            d = json.loads(mk.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        e = d.get("enrichment") or {}
        if e:
            enr_total += 1
            st = e.get("status", "")
            if st == "summarized":
                enr_summarized += 1
            elif st == "failed":
                enr_failed += 1

    date_str = now_local().strftime("%Y-%m-%d %H:%M")
    stats_line = f"**현황** ({date_str} 자동 갱신): 기록 {raw_count}건 · 링크 요약 {enr_summarized}/{enr_total}"
    if enr_failed:
        stats_line += f" · 실패 {enr_failed}건 ⚠️"
    stats_block = f"{_HOME_STATS_BEGIN}\n> {stats_line}\n{_HOME_STATS_END}"

    text = home.read_text(encoding="utf-8")
    if _HOME_STATS_BEGIN in text and _HOME_STATS_END in text:
        begin_idx = text.index(_HOME_STATS_BEGIN)
        end_idx = text.index(_HOME_STATS_END) + len(_HOME_STATS_END)
        new_text = text[:begin_idx] + stats_block + text[end_idx:]
    else:
        new_text = text.rstrip() + "\n\n" + stats_block + "\n"
    atomic_write_text(home, new_text)
    print(json.dumps({"updated": str(home), "stats": stats_line}, ensure_ascii=False, indent=2))


def digest(config: dict[str, Any]) -> None:
    vault = vault_path(config)
    raw_root = vault / rel(config, "rawFolder", "00_Inbox/Raw")
    processed_root = vault / rel(config, "processedFolder", "00_Inbox/Processed")
    raw_count = len(list(raw_root.rglob("*.md"))) if raw_root.exists() else 0
    processed_count = len(list(processed_root.rglob("*.json"))) if processed_root.exists() else 0
    by_type: dict[str, int] = {}
    # enrichment(트랙 A) 진행 통계: extracted=요약 대기, summarized=완료.
    enrichment = {"total": 0, "summarized": 0, "extracted": 0, "failed": 0, "skipped": 0, "duplicate_url": 0}
    structured_count = 0  # 중복 마커(duplicate_of) 제외 = 실제 구조화 노트 수
    duplicate_count = 0   # 같은 내용 재캡처로 기존 노트에 합쳐진 마커 수
    for marker in processed_root.rglob("*.json") if processed_root.exists() else []:
        try:
            data = json.loads(marker.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("duplicate_of"):  # 같은 내용 재캡처 마커 — 통계에서 제외
            duplicate_count += 1
            continue
        structured_count += 1
        memory_type = data.get("plan", {}).get("memory_type", "unknown")
        by_type[memory_type] = by_type.get(memory_type, 0) + 1
        enr = data.get("enrichment")
        if enr:
            enrichment["total"] += 1
            status = enr.get("status", "")
            if status in enrichment:
                enrichment[status] += 1
    print(json.dumps({"raw_notes": raw_count, "processed_markers": processed_count,
                      "structured_notes": structured_count, "duplicate_markers": duplicate_count,
                      "by_type": by_type, "enrichment": enrichment}, ensure_ascii=False, indent=2))


def command_exists(command: str) -> bool:
    if not command:
        return False
    if "/" in command:
        return Path(command).expanduser().exists()
    return shutil.which(command) is not None


def python_module_exists(name: str) -> bool:
    code = f"import importlib.util as u; raise SystemExit(0 if u.find_spec({name!r}) else 1)"
    return subprocess.run([sys.executable, "-c", code], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0


def enrichment_dependency_status(checker=python_module_exists) -> dict[str, Any]:
    """trafilatura(URL enrich 기능 필수) 설치 여부 + 미설치 안내.

    checker 주입으로 테스트 가능. trafilatura가 없어도 doctor는 실패하지 않고,
    enrich 기능만 비활성된다(실제 enrich 명령은 A1에서 지연 import로 가드).
    """
    ok = checker("trafilatura")
    return {
        "trafilatura": ok,
        "hint": "" if ok else (
            "enrich 기능에 trafilatura가 필요합니다: "
            "python3 -m pip install --user --break-system-packages trafilatura"
        ),
    }


def doctor(config: dict[str, Any], config_path: Path) -> None:
    tools = config.get("tools", {})
    checks = {
        "yt-dlp": command_exists(tools.get("ytDlp", "yt-dlp")),
        "tesseract": command_exists(tools.get("tesseract", "tesseract")),
        "marker_single": command_exists(tools.get("markerSingle", "marker_single")),
        "paddleocr_file": command_exists(tools.get("paddleOcrFile", "paddleocr_file")),
        "paddleocr_mcp": command_exists(tools.get("paddleOcrMcp", "paddleocr_mcp")),
        "markitdown": command_exists(tools.get("markitdown", "markitdown")),
        "pdfplumber": python_module_exists("pdfplumber"),
        "pdftext": python_module_exists("pdftext"),
        "surya": python_module_exists("surya"),
        "youtube_transcript_api": python_module_exists("youtube_transcript_api"),
        "python_telegram_bot": python_module_exists("telegram"),
        "fastapi": python_module_exists("fastapi"),
        "mcp": python_module_exists("mcp"),
        "monolith": command_exists("monolith"),
    }
    queue_info: dict[str, Any] = {}
    try:
        _JOBS = ROOT / "scripts" / "jobs.py"
        jr = subprocess.run(
            [sys.executable, str(_JOBS), "list", "--status", "pending"],
            cwd=str(ROOT), text=True, capture_output=True,
        )
        if jr.returncode == 0:
            jdata = json.loads(jr.stdout or "{}")
            pending_jobs = jdata.get("jobs", [])
            by_type: dict[str, int] = {}
            for j in pending_jobs:
                t = j.get("type", "?")
                by_type[t] = by_type.get(t, 0) + 1
            oldest = min((j.get("created_at", "") for j in pending_jobs), default="")
            queue_info = {"pending_total": len(pending_jobs), "by_type": by_type, "oldest": oldest}
        else:
            queue_info = {"error": f"jobs exit {jr.returncode}"}
    except Exception as exc:  # noqa: BLE001
        queue_info = {"error": str(exc)[:100]}

    result = {
        "config": str(config_path),
        "vault": str(vault_path(config)),
        "checks": checks,
        "enrichment": enrichment_dependency_status(),
        "queue": queue_info,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def review_list(config: dict[str, Any]) -> None:
    vault = vault_path(config)
    review_root = vault / rel(config, "reviewFolder", "00_Inbox/Review")
    items = []
    if review_root.exists():
        for path in sorted(review_root.glob("*.md")):
            meta, _ = parse_frontmatter(path.read_text(encoding="utf-8", errors="ignore"))
            items.append({
                "file": path.name,
                "review_type": meta.get("review_type", ""),
                "reason": meta.get("reason", ""),
                "suggested_folder": meta.get("suggested_folder", ""),
            })
    print(json.dumps({"review": items, "count": len(items)}, ensure_ascii=False, indent=2))


def review_resolve(args: argparse.Namespace, config: dict[str, Any], config_path: Path) -> None:
    """Resolve a Review note into a structured note, record the decision (③d), delete the Review file.

    Raw notes are never touched. The decision is captured only when --signal is given.
    """
    vault = vault_path(config)
    review_root = vault / rel(config, "reviewFolder", "00_Inbox/Review")
    review_path = Path(args.file).expanduser()
    if not review_path.is_absolute():
        review_path = review_root / args.file
    if not review_path.exists():
        raise SystemExit(f"Review file not found: {review_path}")

    meta, body = parse_frontmatter(review_path.read_text(encoding="utf-8"))
    memory_type = args.type
    folder = args.folder or meta.get("suggested_folder") or FOLDER_BY_TYPE.get(memory_type, "10_Timeline/Daily")
    source_raw = meta.get("source_raw", "")
    title = args.title or safe_name(body.splitlines()[0] if body.splitlines() else review_path.stem, memory_type)

    ref_date = now_local().date()
    captured = meta.get("captured_at", "")
    if captured:
        try:
            ref_date = dt.datetime.fromisoformat(captured).date()
        except ValueError:
            pass
    base_fields = {
        "memory_type": memory_type,
        "source_raw": source_raw,
        "confidence": "high",
        "needs_review": False,
        "sensitivity": meta.get("sensitivity", "normal"),
        "lint_method": "user_resolved",
        "updated_at": now_local().isoformat(timespec="seconds"),
        "dates": normalize_dates(body, ref_date),
    }
    structured_body = f"# {title}\n\n## 출처\n\n- {source_raw}\n\n## 내용\n\n{body.strip()}\n"
    note_path = create_structured_note(vault, folder, title, base_fields, structured_body, on_conflict="unique")

    decision = {"recorded": False}
    if args.signal:
        try:
            import rules as rules_mod
            store = rules_mod.from_config(config_path)
            store.add_decision(args.signal, memory_type, folder, source_raw, by="cli")
            decision = {"recorded": True, "signal": rules_mod.normalize_signal(args.signal)}
        except Exception as exc:
            decision = {"recorded": False, "error": str(exc)[:200]}

    review_path.unlink()
    print(json.dumps({
        "resolved": relative_to_vault(note_path, vault),
        "memory_type": memory_type,
        "review_deleted": review_path.name,
        "decision": decision,
    }, ensure_ascii=False, indent=2))


MUSIC_TYPES = {"song", "playlist", "artist", "album", "listening_log"}
MUSIC_PREFIXES = ("40_Entities/Songs", "40_Entities/Artists", "40_Entities/Albums", "60_Ideas/Playlists", "50_Experiences/Music")
CLASSIFIED_TOPS = {"10_Timeline", "20_Records", "30_Actions", "40_Entities", "50_Experiences", "60_Ideas"}


def _link_to_relpath(link: str) -> str:
    """'[[00_Inbox/Raw/...]]' -> '00_Inbox/Raw/....md' (relative path string)."""
    m = re.search(r"\[\[(.+?)\]\]", link or "")
    if not m:
        return ""
    rel_path = m.group(1)
    return rel_path if rel_path.endswith(".md") else rel_path + ".md"


def prune_orphans(args: argparse.Namespace, config: dict[str, Any]) -> None:
    """Find (and with --apply, remove) orphan/ghost structured notes.

    Repeatable & idempotent — re-run to clean files that Google Drive restored.
    Detection is source_raw-based so legit-but-unreferenced music entities survive:
      (a) music-entity folder + its source raw classifies non-music (or raw gone) -> orphan
      (b) other folder + its source raw's current marker points to a DIFFERENT note -> ghost duplicate
      (c) otherwise unreferenced -> report only (could be a hand-made note)
    """
    vault = vault_path(config)
    processed_root = vault / rel(config, "processedFolder", "00_Inbox/Processed")
    # macOS stores filenames NFD while marker JSON holds NFC; normalize to NFC for
    # all path-string comparisons, otherwise referenced notes look "unreferenced".
    nfc = lambda s: unicodedata.normalize("NFC", s or "")
    referenced: set[str] = set()
    raw_to_structured: dict[str, str] = {}
    if processed_root.exists():
        for mk in processed_root.glob("*.json"):
            try:
                d = json.loads(mk.read_text(encoding="utf-8"))
            except (ValueError, OSError):
                continue
            structured = d.get("structured")
            if structured:
                referenced.add(nfc(structured))
            for ent in d.get("entities_updated", []) or []:
                referenced.add(nfc(ent))
            if structured and not d.get("duplicate_of"):
                raw_to_structured[nfc(d.get("raw", ""))] = nfc(structured)

    orphans: list[dict[str, str]] = []
    report_only: list[str] = []
    for note in sorted(vault.rglob("*.md")):
        relp = relative_to_vault(note, vault)
        relp_n = nfc(relp)
        if relp_n.split("/")[0] not in CLASSIFIED_TOPS or relp_n in referenced:
            continue
        meta, _ = parse_frontmatter(note.read_text(encoding="utf-8", errors="ignore"))
        src = nfc(_link_to_relpath(meta.get("source_raw", "")))
        if relp_n.startswith(MUSIC_PREFIXES):
            raw = vault / src if src else None
            if not src or not raw.exists():
                orphans.append({"path": relp, "reason": "music_orphan(source raw 없음)"})
            else:
                _, raw_body = parse_frontmatter(raw.read_text(encoding="utf-8", errors="ignore"))
                mt = classify(raw_body, {})["memory_type"]
                if mt not in MUSIC_TYPES:
                    orphans.append({"path": relp, "reason": f"music_orphan(원본 현재분류={mt})"})
        else:
            current = raw_to_structured.get(src)
            if src and current and current != relp_n:
                orphans.append({"path": relp, "reason": f"ghost_duplicate(정식본={current})"})
            else:
                report_only.append(relp)

    if not args.apply:
        print(json.dumps({"would_delete": len(orphans), "orphans": orphans, "report_only": report_only}, ensure_ascii=False, indent=2))
        return

    import tempfile
    backup = Path(tempfile.mkdtemp(prefix="lmv-prune-orphans-"))
    deleted: list[str] = []
    for o in orphans:
        p = vault / o["path"]
        if p.exists():
            shutil.copy2(p, backup / p.name)
            p.unlink()
            deleted.append(o["path"])
    print(json.dumps({"deleted": len(deleted), "backup": str(backup), "paths": deleted, "report_only": report_only}, ensure_ascii=False, indent=2))


def dedup_markers(args: argparse.Namespace, config: dict[str, Any]) -> None:
    """Clean up duplicate markers in two stages (dry-run default; --apply writes).

    1. Same raw (NFC/NFD filename dupes = one memo processed twice) -> keep one
       (prefer a structured marker, else oldest), delete the rest with backup.
    2. Same structured note from different raws (re-captured content) -> keep the
       oldest as canonical, convert the rest to duplicate_of (history kept).

    Raw files are never touched.
    """
    import tempfile
    nfc = lambda s: unicodedata.normalize("NFC", s or "")  # noqa: E731
    vault = vault_path(config)
    processed = vault / rel(config, "processedFolder", "00_Inbox/Processed")
    backup: list[Path | None] = [None]

    def _backup_unlink(mk: Path) -> None:
        if backup[0] is None:
            backup[0] = Path(tempfile.mkdtemp(prefix="lmv-dedup-markers-"))
        shutil.copy2(mk, backup[0] / mk.name)
        mk.unlink()

    def _load_all() -> list[tuple[Path, dict[str, Any]]]:
        out: list[tuple[Path, dict[str, Any]]] = []
        if processed.exists():
            for mk in sorted(processed.glob("*.json")):
                try:
                    out.append((mk, json.loads(mk.read_text(encoding="utf-8"))))
                except (ValueError, OSError):
                    continue
        return out

    # Stage 1: markers for the SAME raw (NFC/NFD filename dupes = same memo processed
    # twice). Keep one (prefer a structured/canonical marker, else oldest), delete the
    # rest with backup. Raw files are untouched.
    by_raw: dict[str, list[tuple[Path, dict[str, Any]]]] = {}
    for mk, d in _load_all():
        by_raw.setdefault(nfc(d.get("raw", "")), []).append((mk, d))
    removed: list[str] = []
    for rr, members in by_raw.items():
        if not rr or len(members) < 2:
            continue
        members.sort(key=lambda x: (0 if x[1].get("structured") else 1, x[1].get("processed_at", "")))
        for mk, _ in members[1:]:
            removed.append(mk.name)
            if args.apply:
                _backup_unlink(mk)

    # Stage 2: markers (different raws) for the SAME structured note = same content
    # re-captured. Keep oldest as canonical; convert the rest to duplicate_of.
    groups: dict[str, list[tuple[str, Path, dict[str, Any]]]] = {}
    for mk, d in _load_all():
        if d.get("duplicate_of"):
            continue
        s = nfc(d.get("structured", ""))
        if s:
            groups.setdefault(s, []).append((d.get("processed_at", ""), mk, d))
    converted: list[str] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        members.sort(key=lambda x: x[0])  # oldest = canonical
        canonical = members[0][2].get("structured", "")
        for _, mk, d in members[1:]:
            converted.append(mk.name)
            if args.apply:
                new = {k: v for k, v in d.items() if k != "structured"}
                new["duplicate_of"] = canonical
                new.setdefault("plan", {})
                new["plan"]["memory_type"] = "duplicate"
                atomic_write_text(mk, json.dumps(new, ensure_ascii=False, indent=2))
    print(json.dumps({"removed_same_raw": len(removed), "converted_same_note": len(converted),
                      "backup": str(backup[0]) if backup[0] else "", "applied": bool(args.apply)},
                     ensure_ascii=False, indent=2))


def reclassify(args: argparse.Namespace, config: dict[str, Any], config_path: Path) -> None:
    """Re-file an already-structured note to a new memory_type (full move).

    Moves the note to the new type's folder, updates its marker (structured +
    plan), rewrites every `[[old-path]]` wikilink across the vault to the new
    path (so MOCs/links don't break), and records a learning decision when
    --signal is given (a signal confirmed twice auto-classifies later). Raw notes
    are never touched. Dry-run by default; --apply writes (with backup).
    """
    import tempfile
    nfc = lambda s: unicodedata.normalize("NFC", s or "")  # noqa: E731
    vault = vault_path(config)
    note_path = Path(args.note).expanduser()
    if not note_path.is_absolute():
        note_path = vault / args.note
    if not note_path.exists():
        raise SystemExit(f"Note not found: {note_path}")

    old_rel = relative_to_vault(note_path, vault)
    meta, body = parse_frontmatter(note_path.read_text(encoding="utf-8"))
    new_type = args.type
    new_folder = args.folder or FOLDER_BY_TYPE.get(new_type, "10_Timeline/Daily")
    title = args.title or note_path.stem
    source_raw = meta.get("source_raw", "")
    new_rel_preview = f"{new_folder}/{safe_name(title, new_type)}.md"

    if not args.apply:
        # Count wikilinks that would be rewritten (best-effort preview).
        old_link = old_rel[:-3] if old_rel.endswith(".md") else old_rel
        would_links = sum(
            1 for md in vault.rglob("*.md")
            if f"[[{old_link}" in (md.read_text(encoding="utf-8", errors="ignore"))
        )
        print(json.dumps({"dry_run": True, "note": old_rel, "to_type": new_type,
                          "to_folder": new_folder, "wikilinks_to_update": would_links,
                          "signal": args.signal or ""}, ensure_ascii=False, indent=2))
        return

    # 1) Create the note in the new folder (keep frontmatter, bump memory_type).
    fields = dict(meta)
    fields["memory_type"] = new_type
    fields["lint_method"] = "user_reclassified"
    fields["needs_review"] = False
    fields["updated_at"] = now_local().isoformat(timespec="seconds")
    new_path = create_structured_note(vault, new_folder, title, fields, body, on_conflict="unique")
    new_rel = relative_to_vault(new_path, vault)
    moved = nfc(new_rel) != nfc(old_rel)

    # 2) Update the marker (found via source_raw).
    marker_updated = ""
    raw_rel = _link_to_relpath(source_raw)
    if raw_rel:
        mid = hashlib.sha1(raw_rel.encode("utf-8")).hexdigest()[:16]
        mk = vault / rel(config, "processedFolder", "00_Inbox/Processed") / f"{mid}.json"
        if mk.exists():
            try:
                d = json.loads(mk.read_text(encoding="utf-8"))
                d["structured"] = new_rel
                d.setdefault("plan", {})
                d["plan"]["memory_type"] = new_type
                d["plan"]["folder"] = new_folder
                atomic_write_text(mk, json.dumps(d, ensure_ascii=False, indent=2))
                marker_updated = mk.name
            except (ValueError, OSError):
                pass

    # 3) Rewrite [[old]] -> [[new]] across the vault (keep MOCs/links intact).
    old_link = old_rel[:-3] if old_rel.endswith(".md") else old_rel
    new_link = new_rel[:-3] if new_rel.endswith(".md") else new_rel
    links_updated = 0
    if moved and nfc(old_link) != nfc(new_link):
        for md in vault.rglob("*.md"):
            if nfc(relative_to_vault(md, vault)) == nfc(new_rel):
                continue
            try:
                txt = md.read_text(encoding="utf-8")
            except OSError:
                continue
            if f"[[{old_link}" in txt:
                new_txt = txt.replace(f"[[{old_link}]]", f"[[{new_link}]]").replace(f"[[{old_link}|", f"[[{new_link}|")
                if new_txt != txt:
                    atomic_write_text(md, new_txt)
                    links_updated += 1

    # 4) Remove the old note (with backup) when it actually moved.
    backup = ""
    if moved and note_path.exists():
        bdir = Path(tempfile.mkdtemp(prefix="lmv-reclassify-"))
        shutil.copy2(note_path, bdir / note_path.name)
        note_path.unlink()
        backup = str(bdir)

    # 5) Learn (signal -> type) so similar memos auto-classify later.
    decision = {"recorded": False}
    if args.signal:
        try:
            import rules as rules_mod
            store = rules_mod.from_config(config_path)
            store.add_decision(args.signal, new_type, new_folder, source_raw, by="reclassify")
            decision = {"recorded": True, "signal": rules_mod.normalize_signal(args.signal)}
        except Exception as exc:  # noqa: BLE001
            decision = {"recorded": False, "error": str(exc)[:200]}

    print(json.dumps({"reclassified": old_rel, "to": new_rel, "memory_type": new_type,
                      "marker_updated": marker_updated, "links_updated": links_updated,
                      "backup": backup, "decision": decision}, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Life Memory Vault MVP CLI")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to memory-config.json")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("init", help="Create vault folder structure and system notes")

    save = sub.add_parser("save", help="Save a raw memory note")
    save.add_argument("text", nargs="?", default="", help="Text to capture. Reads stdin if omitted.")
    save.add_argument("--source", default="manual", help="Capture source, e.g. telegram, macbook, codex")
    save.add_argument("--url", default="", help="Source URL")
    save.add_argument("--file", default="", help="Optional local attachment path")
    save.add_argument("--title", default="", help="Optional note title")
    save.add_argument("--raw-type", default="", help="Override inferred raw type")
    save.add_argument("--sensitivity", default="normal", help="normal or private")

    lint = sub.add_parser("lint", help="Create lightweight structured notes for pending raw notes")
    lint.add_argument("--force", action="store_true", help="Reprocess notes with existing processed markers")

    seek_parser = sub.add_parser("seek", help="Search memory vault markdown (scored, filterable)")
    seek_parser.add_argument("query")
    seek_parser.add_argument("--limit", type=int, default=10)
    seek_parser.add_argument("--type", default="", help="Filter by memory_type")
    seek_parser.add_argument("--tag", default="", help="Filter by tag/hashtag")
    seek_parser.add_argument("--since", default="", help="Only notes with updated_at/captured_at >= this ISO date prefix (e.g. 2026-01)")

    sub.add_parser("digest", help="Report raw/processed counts")
    sub.add_parser("doctor", help="Check local tool readiness")

    prune = sub.add_parser("prune-orphans", help="Find/remove orphan & ghost structured notes (e.g. Drive-restored leftovers)")
    prune.add_argument("--apply", action="store_true", help="Delete with backup. Default: dry-run report.")

    dedup = sub.add_parser("dedup-markers", help="같은 노트를 가리키는 중복 마커를 duplicate_of로 전환")
    dedup.add_argument("--apply", action="store_true", help="실제 전환. 기본은 dry-run 보고.")

    recl = sub.add_parser("reclassify", help="이미 분류된 노트를 다른 memory_type으로 재분류 (이동+마커+링크+학습)")
    recl.add_argument("note", help="대상 구조화 노트 경로 (볼트 상대 또는 절대)")
    recl.add_argument("--type", required=True, dest="type", help="새 memory_type")
    recl.add_argument("--signal", default="", help="학습할 키워드 (2회 일관 시 자동 분류)")
    recl.add_argument("--folder", default="", help="대상 폴더 (기본: 타입별 기본 폴더)")
    recl.add_argument("--title", default="", help="제목 변경 (기본: 기존 파일명 유지)")
    recl.add_argument("--apply", action="store_true", help="실제 적용. 기본은 dry-run 보고.")

    enrich_p = sub.add_parser("enrich", help="URL 메모에 제목/대표이미지/발췌를 보강 (트랙 A)")
    enrich_grp = enrich_p.add_mutually_exclusive_group()
    enrich_grp.add_argument("--limit", type=int, default=5, help="처리 최대 건수 (무인 기본 5)")
    enrich_grp.add_argument("--all", action="store_true", help="대기 전체 처리 (온디맨드)")
    enrich_p.add_argument("--force", action="store_true", help="이미 처리된 것도 재처리")
    enrich_p.add_argument("--dry-run", action="store_true", help="후보만 보고, 변경 없음")
    enrich_p.add_argument(
        "--status",
        choices=["failed", "extracted", "summarized", "duplicate_url", "skipped", "empty"],
        help="이 상태인 마커 목록만 출력 (처리 없음; --status failed 로 실패 목록 확인)",
    )

    ext_media = sub.add_parser("extract-media", help="이미지/PDF 첨부 메모에서 텍스트 추출 (OCR·PDF파싱)")
    ext_grp = ext_media.add_mutually_exclusive_group()
    ext_grp.add_argument("--limit", type=int, default=3, help="처리 최대 건수 (무인 기본 3)")
    ext_grp.add_argument("--all", action="store_true", help="대기 전체 처리 (온디맨드)")
    ext_media.add_argument("--force", action="store_true", help="이미 처리된 것도 재처리")
    ext_media.add_argument("--dry-run", action="store_true", help="후보만 보고, 변경 없음")

    sub.add_parser("home-update", help="90_System/홈.md 통계 블록을 현재 digest 수치로 갱신")

    review = sub.add_parser("review", help="List or resolve 00_Inbox/Review items")
    rsub = review.add_subparsers(dest="review_command", required=True)
    rsub.add_parser("list", help="List pending Review items")
    resolve = rsub.add_parser("resolve", help="Resolve a Review note into a structured note (+ record decision)")
    resolve.add_argument("file", help="Review filename under 00_Inbox/Review (or a path)")
    resolve.add_argument("--type", required=True, dest="type", help="Confirmed memory_type")
    resolve.add_argument("--signal", default="", help="Keyword to learn (records a decision for ③d)")
    resolve.add_argument("--folder", default="", help="Override target folder")
    resolve.add_argument("--title", default="", help="Override note title")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(args.config).expanduser()
    config = load_config(config_path)
    if args.command == "init":
        init_vault(config)
    elif args.command == "save":
        save_raw(args, config)
    elif args.command == "lint":
        lint_vault(args, config)
    elif args.command == "seek":
        seek(args, config)
    elif args.command == "digest":
        digest(config)
    elif args.command == "doctor":
        doctor(config, config_path)
    elif args.command == "prune-orphans":
        prune_orphans(args, config)
    elif args.command == "dedup-markers":
        dedup_markers(args, config)
    elif args.command == "reclassify":
        reclassify(args, config, config_path)
    elif args.command == "enrich":
        from enrich import enrich_vault
        enrich_vault(args, config)
    elif args.command == "extract-media":
        from extract_media import extract_media_vault
        print(json.dumps(extract_media_vault(args, config), ensure_ascii=False, indent=2))
    elif args.command == "home-update":
        home_update(config)
    elif args.command == "review":
        if args.review_command == "list":
            review_list(config)
        elif args.review_command == "resolve":
            review_resolve(args, config, config_path)


if __name__ == "__main__":
    main()
