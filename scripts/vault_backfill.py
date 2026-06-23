#!/usr/bin/env python3
"""
vault_backfill.py — 두 가지 일괄 작업

Task 1: Daily 인덱스 백필
  - 기존 모든 마커를 읽어 raw 파일명의 날짜 기준으로 10_Daily/YYYY-MM-DD.md 업데이트

Task 2: Tags 보강
  - 노트 본문 + enrich 블록 키워드로 frontmatter tags 보강
  - 의미 없는 구 태그(관심·프로젝트·적용후보·AI 등) 제거

Usage:
  python3 scripts/vault_backfill.py            # 두 작업 모두
  python3 scripts/vault_backfill.py --daily    # Task 1만
  python3 scripts/vault_backfill.py --tags     # Task 2만
  python3 scripts/vault_backfill.py --dry-run  # 미리보기
"""

import re
import json
import argparse
import datetime as dt
from pathlib import Path

VAULT = Path("/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault")
PROCESSED = VAULT / "00_Inbox/Processed"

# ── 제거할 구 태그 (중복·무의미) ───────────────────────────────────────────────
STALE_TAGS = {
    "관심", "프로젝트", "적용후보", "관심 프로젝트", "AI", "ai",
    "일상", "메모", "memo", "memory", "노래", "song", "플레이리스트",
    "공부대상", "추천대상", "내프로젝트참조대상", "음악",
}

# ── 키워드 → 태그 매핑 (본문·enrich 블록에서 매칭) ──────────────────────────
KEYWORD_TAG_MAP = [
    # 키워드 목록(소문자),  추가할 태그
    (["협업", "collaboration", "팀워크", "팀 작업"],           "협업"),
    (["자동화", "automation", "워크플로우", "workflow"],        "자동화"),
    (["지식 그래프", "knowledge graph", "그래프rag", "graphrag"], "지식그래프"),
    (["벡터", "vector", "임베딩", "embedding"],                 "벡터"),
    (["멀티에이전트", "multi-agent", "다중 에이전트"],          "멀티에이전트"),
    (["에이전트 메모리", "agent memory"],                       "에이전트메모리"),
    (["옵시디언", "obsidian"],                                  "Obsidian"),
    (["마크다운", "markdown"],                                  "마크다운"),
    (["한국어", "korean", "국내"],                              "한국어"),
    (["로컬", "온디바이스", "on-device", "local llm"],          "로컬"),
    (["파인튜닝", "fine-tun"],                                  "파인튜닝"),
    (["크롬", "chrome", "브라우저 확장"],                       "크롬확장"),
    (["디스코드", "discord"],                                   "Discord"),
    (["텔레그램", "telegram"],                                  "Telegram"),
    (["ui ", "ux ", "인터페이스", "interface"],                 "UI/UX"),
    (["음성", "tts", "text-to-speech", "speech"],              "음성합성"),
    (["투자", "주식", "stock", "trading", "금융"],              "투자"),
    (["교육", "학습", "강의", "세미나", "튜토리얼"],            "교육"),
    (["오픈소스", "open source", "github"],                     "오픈소스"),
    (["이미지 생성", "image generation", "이미지 ai"],          "이미지생성"),
    (["코드 생성", "code generation", "코딩 ai"],               "코드생성"),
    (["문서", "document", "편집기", "editor"],                  "문서"),
    (["슬라이드", "presentation", "발표"],                      "프레젠테이션"),
    (["맥", "mac", "macos", "apple"],                          "macOS"),
    (["ios", "iphone", "앱스토어"],                             "iOS"),
    (["무료", "free tier", "freemium"],                         "무료"),
    (["api", "sdk", "개발자 도구"],                             "개발자도구"),
]


# ── 유틸 ──────────────────────────────────────────────────────────────────────
def atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(content, encoding="utf-8")
    tmp.replace(path)


def parse_date_from_raw(raw_rel: str) -> dt.date | None:
    """'00_Inbox/Raw/2026/06/2026-06-13-090429-title.md' → date(2026,6,13)"""
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})-\d{6}", raw_rel)
    if m:
        return dt.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return None


def parse_date_from_iso(s: str) -> dt.date | None:
    try:
        return dt.datetime.fromisoformat(s).date()
    except Exception:
        return None


def get_note_title(note_path: Path) -> str:
    """파일 stem을 제목으로 사용 (H1보다 정확 — reclassify 후 H1이 구 제목인 경우 있음)."""
    return note_path.stem


def update_daily_index(date: dt.date, note_rel: str, title: str, dry: bool) -> bool:
    daily_dir = VAULT / "10_Daily"
    daily_dir.mkdir(parents=True, exist_ok=True)
    daily_file = daily_dir / f"{date.strftime('%Y-%m-%d')}.md"
    link = f"- [[{note_rel}|{title}]]"

    if daily_file.exists():
        content = daily_file.read_text(encoding="utf-8")
        if note_rel in content:
            return False  # already linked
        new_content = content.rstrip() + "\n" + link + "\n"
    else:
        header = (
            f"---\ntype: daily-index\ndate: {date.strftime('%Y-%m-%d')}\n---\n\n"
            f"# {date.strftime('%Y-%m-%d')}\n\n"
        )
        new_content = header + link + "\n"

    if not dry:
        atomic_write(daily_file, new_content)
    return True


# ── Task 1: Daily 인덱스 백필 ─────────────────────────────────────────────────
def backfill_daily(dry: bool) -> None:
    print("\n=== Task 1: Daily 인덱스 백필 ===")
    added = 0
    skipped = 0

    for jf in sorted(PROCESSED.glob("*.json")):
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("duplicate_of") or not data.get("structured"):
            continue

        structured_rel = data["structured"]
        note_path = VAULT / structured_rel

        # 날짜 결정: raw 파일명 → processed_at 순
        date = parse_date_from_raw(data.get("raw", ""))
        if not date:
            date = parse_date_from_iso(data.get("processed_at", ""))
        if not date:
            skipped += 1
            continue

        # 파일이 없으면 건너뜀 (구 마커가 이전 경로 참조하는 경우)
        if not note_path.exists():
            skipped += 1
            continue

        title = get_note_title(note_path)
        was_added = update_daily_index(date, structured_rel, title, dry)
        if was_added:
            added += 1
            print(f"  [{date}] {title[:50]}")
        else:
            skipped += 1

    print(f"\n  완료: {added}개 추가, {skipped}개 이미 있음/건너뜀")


# ── Task 2: Tags 보강 ─────────────────────────────────────────────────────────
FM_END_PAT = re.compile(r"^---\s*$", re.MULTILINE)
TAGS_BLOCK_PAT = re.compile(r"^tags:\s*\n((?:  - .+\n?)*)", re.MULTILINE)
TAGS_INLINE_PAT = re.compile(r"^tags:\s*\[([^\]]*)\]", re.MULTILINE)
ENRICH_PAT = re.compile(r"<!-- enrich:begin.*?-->(.+?)<!-- enrich:end -->", re.DOTALL)


def extract_enrich_text(content: str) -> str:
    m = ENRICH_PAT.search(content)
    return m.group(1).lower() if m else ""


def derive_new_tags(content: str, existing_tags: list) -> list:
    """본문 + enrich 블록 키워드 매칭으로 추가할 태그 반환."""
    body_lower = content.lower()
    enrich_lower = extract_enrich_text(content)
    combined = body_lower + " " + enrich_lower

    new_tags = []
    for keywords, tag in KEYWORD_TAG_MAP:
        if tag in existing_tags:
            continue
        if any(kw in combined for kw in keywords):
            new_tags.append(tag)

    return new_tags


def update_tags_in_fm(content: str, dry: bool, note_path: Path) -> tuple[str, list, list]:
    """태그 정리 + 보강. (new_content, removed, added) 반환."""
    if not content.startswith("---"):
        return content, [], []

    ends = [m.start() for m in FM_END_PAT.finditer(content)]
    if len(ends) < 2:
        return content, [], []
    fm_end = ends[1]
    fm_text = content[3:fm_end]
    rest = content[fm_end:]

    # 기존 태그 파싱
    block_m = TAGS_BLOCK_PAT.search(fm_text)
    inline_m = TAGS_INLINE_PAT.search(fm_text)

    if block_m:
        existing = [t.strip().strip('"') for t in re.findall(r"  - (.+)", block_m.group(1))]
    elif inline_m:
        existing = [t.strip().strip('"\'') for t in inline_m.group(1).split(",") if t.strip()]
    else:
        existing = []

    # 구 태그 제거
    cleaned = [t for t in existing if t.lower() not in STALE_TAGS and t not in STALE_TAGS]
    removed = [t for t in existing if t not in cleaned]

    # 새 태그 추가
    added = derive_new_tags(content, cleaned)
    merged = cleaned + [t for t in added if t not in cleaned]

    if merged == existing and not removed:
        return content, [], []

    # frontmatter 재작성
    tag_block = "tags:\n" + "".join(f"  - {t}\n" for t in merged)
    if block_m:
        new_fm = TAGS_BLOCK_PAT.sub(tag_block, fm_text)
    elif inline_m:
        new_fm = TAGS_INLINE_PAT.sub(tag_block.rstrip("\n"), fm_text)
    else:
        new_fm = fm_text.rstrip("\n") + "\n" + tag_block

    return "---" + new_fm + rest, removed, added


def enrich_tags(dry: bool) -> None:
    print("\n=== Task 2: Tags 보강 ===")
    total = updated = 0

    note_folders = [
        VAULT / "40_Notes/Saves",
        VAULT / "40_Notes/Music",
        VAULT / "40_Notes/Things",
        VAULT / "40_Notes/Places",
        VAULT / "40_Notes/People",
        VAULT / "40_Notes/Experiences",
        VAULT / "30_Actions",
        VAULT / "20_Records",
    ]

    for folder in note_folders:
        if not folder.exists():
            continue
        for note in sorted(folder.rglob("*.md")):
            total += 1
            content = note.read_text(encoding="utf-8")
            new_content, removed, added = update_tags_in_fm(content, dry, note)
            if removed or added:
                updated += 1
                rel = str(note.relative_to(VAULT))
                print(f"  {rel}")
                if removed:
                    print(f"    - 제거: {removed}")
                if added:
                    print(f"    + 추가: {added}")
                if not dry:
                    atomic_write(note, new_content)

    print(f"\n  완료: {total}개 중 {updated}개 업데이트")


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--daily", action="store_true", help="Task 1만")
    parser.add_argument("--tags", action="store_true", help="Task 2만")
    args = parser.parse_args()

    dry = args.dry_run
    if dry:
        print("=== DRY RUN ===")

    run_daily = args.daily or (not args.daily and not args.tags)
    run_tags = args.tags or (not args.daily and not args.tags)

    if run_daily:
        backfill_daily(dry)
    if run_tags:
        enrich_tags(dry)


if __name__ == "__main__":
    main()
