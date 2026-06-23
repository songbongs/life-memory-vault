#!/usr/bin/env python3
"""
vault_migrate.py — One-time vault restructuring migration

New structure:
  10_Daily/               (was 10_Timeline/Daily)
  40_Notes/People/        (was 40_Entities/People)
  40_Notes/Places/        (was 40_Entities/Places)
  40_Notes/Things/        (was 40_Entities/Things)
  40_Notes/Music/         (was 40_Entities/Songs + 60_Ideas/Playlists)
  40_Notes/Saves/         (was 60_Ideas/Projects + Products + misclassified Daily)
  40_Notes/Experiences/   (was 50_Experiences/Food_Drink)
  90_System/Index/        (was 70_MOCs)

Usage: python3 scripts/vault_migrate.py [--dry-run]
"""

import os
import re
import json
import shutil
import sys
import argparse
from pathlib import Path

VAULT = Path("/Users/mini-song/Library/CloudStorage/GoogleDrive-iamsangmin@gmail.com/내 드라이브/[ Cloud Notes ]/Obsidian Vault/my-memory-vault")
PROCESSED = VAULT / "00_Inbox/Processed"

NEW_FOLDERS = [
    "10_Daily",
    "40_Notes/People",
    "40_Notes/Places",
    "40_Notes/Things",
    "40_Notes/Music",
    "40_Notes/Saves",
    "40_Notes/Experiences",
    "90_System/Index",
]

# ── Tag assignment ─────────────────────────────────────────────────────────────
def assign_save_tags(filename: str) -> list:
    name = filename.lower()
    tags = []

    # LLM Wiki / knowledge graph / obsidian integrations
    if any(k in name for k in ['llm-wiki', 'llm wiki', 'graphrag', 'knowledge-manager', 'wikimate', 'sodam', 'doctology', 'gbrain', '지식 그래프', 'knowledge', 'obsidian']):
        tags.append('llmwiki')

    # RAG / vector DB / memory retrieval (NOT image vectorization)
    if any(k in name for k in ['pixelrag', 'leann', 'agentmemory', 'hindsight', 'memory weft']):
        tags.append('rag')
    elif 'rag' in name and 'graphrag' not in name:
        tags.append('rag')

    # TTS / voice synthesis
    if any(k in name for k in ['tts', 'supertonic']):
        tags.append('tts')

    # AI agents / orchestration
    if any(k in name for k in ['agentspace', 'ouroboros', 'fable급', '헤르메스', 'hermes', 'evolution lab', 'agentmemory', 'hindsight', 'memory weft', 'gbrain']):
        tags.append('agent')
    elif 'agent' in name:
        tags.append('agent')

    # Design / visual / document tools
    if any(k in name for k in ['design', 'kami', 'satgat', 'impeccable', 'flashtype', 'slides-grab', 'omnigen', 'perfectvector', 'patina', 'im-not-strange', 'imnotai', '디자인', '바이브코딩', '색조합', 'kuku', '마크다운', '표현', '윤문', '다듬기', 'svg', 'png→svg']):
        tags.append('design')

    # Investment / finance
    if any(k in name for k in ['invest', 'vibe-invest', 'trading', '주식', '투자']):
        tags.append('invest')

    # Education / learning tools
    if any(k in name for k in ['neis', '쌤핀', '선생님', 'notebooklm', '교사', '강의', '세미나', '가이드북', '웹소설']):
        tags.append('education')

    # Coding / developer tools
    if any(k in name for k in ['codex', 'remote-pair', 'skill hook', 'google skills', 'claude-howto', 'k-skill', 'ponytail', 'fable-ish', 'mac-optimizing', 'web-to-app', 'xy-cut', '알고리즘', 'chart-skill', 'gongnangi']):
        tags.append('coding')

    # Plugin / extension / bot
    if any(k in name for k in ['plugin', '플러그인', 'gptaku', 'chrome', '크롬', 'extension', '확장', 'omnisearch', 'telegram', 'discord', '디스코드', 'bot', '봇', 'crx']):
        tags.append('plugin')

    # GitHub repos
    if any(k in name for k in ['github', '(github)']):
        tags.append('github')

    # Web services / apps / resources
    if any(k in name for k in ['fascanner', 'indie radar', 'kenny', 'iptv', '백상현', '서비스', '다이제스트']):
        tags.append('webapp')

    if not tags:
        tags.append('save')
    return tags


# ── Frontmatter helpers ────────────────────────────────────────────────────────
def parse_frontmatter(content: str):
    """Return (fm_dict_text, rest_of_doc) or (None, content)."""
    if not content.startswith('---'):
        return None, content
    end = content.find('\n---', 3)
    if end == -1:
        return None, content
    return content[3:end], content[end + 4:]


def update_fm(content: str, new_memory_type=None, add_tags=None) -> str:
    fm_text, rest = parse_frontmatter(content)
    if fm_text is None:
        return content

    # Update memory_type
    if new_memory_type:
        fm_text = re.sub(
            r'^memory_type:\s*.*$',
            f'memory_type: "{new_memory_type}"',
            fm_text, flags=re.MULTILINE
        )

    # Add tags to existing tags field or create one
    if add_tags:
        block_match = re.search(r'^tags:\s*\n((?:  - .+\n?)*)', fm_text, re.MULTILINE)
        inline_match = re.search(r'^tags:\s*\[([^\]]*)\]', fm_text, re.MULTILINE)

        if block_match:
            existing = re.findall(r'  - (.+)', block_match.group(1))
            merged = existing[:]
            for t in add_tags:
                if t not in merged:
                    merged.append(t)
            replacement = 'tags:\n' + ''.join(f'  - {t}\n' for t in merged)
            fm_text = re.sub(r'^tags:\s*\n(?:  - .+\n?)*', replacement, fm_text, flags=re.MULTILINE)

        elif inline_match:
            existing = [s.strip().strip('"\'') for s in inline_match.group(1).split(',') if s.strip()]
            for t in add_tags:
                if t not in existing:
                    existing.append(t)
            fm_text = re.sub(r'^tags:\s*\[.*?\]', 'tags: [' + ', '.join(existing) + ']', fm_text, flags=re.MULTILINE)

        else:
            tag_block = 'tags:\n' + ''.join(f'  - {t}\n' for t in add_tags)
            fm_text = fm_text.rstrip('\n') + '\n' + tag_block

    return '---' + fm_text + '\n---' + rest


# ── Marker update ──────────────────────────────────────────────────────────────
def update_markers(old_rel: str, new_rel: str, dry_run: bool):
    """Update 'structured' field in any marker whose structured path matches old_rel."""
    count = 0
    if not PROCESSED.exists():
        return count
    for jf in PROCESSED.glob("*.json"):
        try:
            data = json.loads(jf.read_text(encoding='utf-8'))
        except Exception:
            continue
        if data.get('structured') == old_rel:
            if not dry_run:
                data['structured'] = new_rel
                jf.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
            count += 1
    return count


# ── Main migration ─────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dry-run', action='store_true', help='Preview without changes')
    args = parser.parse_args()
    dry = args.dry_run

    if dry:
        print("=== DRY RUN — no files will be changed ===\n")

    # 1. Create new directories
    for folder in NEW_FOLDERS:
        target = VAULT / folder
        if not target.exists():
            if not dry:
                target.mkdir(parents=True, exist_ok=True)
            print(f"[mkdir] {folder}")

    moves = []  # (src_path, dst_path, memory_type, tags)
    deletes = []

    # ── File groups ──────────────────────────────────────────────────────────

    # 10_Timeline/Daily/* → 40_Notes/Saves/
    for f in (VAULT / "10_Timeline/Daily").glob("*.md"):
        tags = assign_save_tags(f.name)
        moves.append((f, VAULT / "40_Notes/Saves" / f.name, "save", tags))

    # 20_Records/Routine/지한 영어학원 버스 하차 시간.md → DELETE (dup of Reminders)
    routine_dup = VAULT / "20_Records/Routine/지한 영어학원 버스 하차 시간.md"
    if routine_dup.exists():
        deletes.append(routine_dup)

    # 30_Actions/Appointments/쌤핀 → 40_Notes/Saves/
    appt_dir = VAULT / "30_Actions/Appointments"
    for f in appt_dir.glob("*.md") if appt_dir.exists() else []:
        if '쌤핀' in f.name:
            moves.append((f, VAULT / "40_Notes/Saves" / f.name, "save", ['education']))

    # 40_Entities/Songs/* → 40_Notes/Music/ (skip old-named duplicate)
    for f in (VAULT / "40_Entities/Songs").glob("*.md"):
        if 'youtube playlist song 노래 남자사람친구' in f.name:
            # This is the old un-renamed duplicate; delete it (renamed version is in Playlists)
            deletes.append(f)
        else:
            moves.append((f, VAULT / "40_Notes/Music" / f.name, None, ['song']))

    # 40_Entities/Places/* → 40_Notes/Places/
    for f in (VAULT / "40_Entities/Places").glob("*.md"):
        moves.append((f, VAULT / "40_Notes/Places" / f.name, None, []))

    # 40_Entities/Things/* → 40_Notes/Things/
    for f in (VAULT / "40_Entities/Things").glob("*.md"):
        moves.append((f, VAULT / "40_Notes/Things" / f.name, None, []))

    # 50_Experiences/Food_Drink/* → 40_Notes/Experiences/
    food_dir = VAULT / "50_Experiences/Food_Drink"
    for f in (food_dir.glob("*.md") if food_dir.exists() else []):
        moves.append((f, VAULT / "40_Notes/Experiences" / f.name, None, []))

    # 60_Ideas/Playlists/* → 40_Notes/Music/
    for f in (VAULT / "60_Ideas/Playlists").glob("*.md"):
        moves.append((f, VAULT / "40_Notes/Music" / f.name, None, ['playlist']))

    # 60_Ideas/Products/* → 40_Notes/Saves/
    for f in (VAULT / "60_Ideas/Products").glob("*.md"):
        dst = VAULT / "40_Notes/Saves" / f.name
        # Handle duplicate Kami (Products version is older; Projects version wins)
        if f.name == "Kami — AI 문서 디자인 시스템.md":
            projects_kami = VAULT / "60_Ideas/Projects/Kami — AI 문서 디자인 시스템.md"
            if projects_kami.exists():
                # Delete Products version — Projects version will overwrite
                deletes.append(f)
                continue
        tags = assign_save_tags(f.name)
        moves.append((f, dst, "save", tags))

    # 60_Ideas/Projects/* → 40_Notes/Saves/
    for f in (VAULT / "60_Ideas/Projects").glob("*.md"):
        tags = assign_save_tags(f.name)
        moves.append((f, VAULT / "40_Notes/Saves" / f.name, "save", tags))

    # 70_MOCs/* → 90_System/Index/
    for f in (VAULT / "70_MOCs").glob("*.md"):
        moves.append((f, VAULT / "90_System/Index" / f.name, None, []))

    # ── Preview / Execute ─────────────────────────────────────────────────────
    print(f"\n{'PREVIEW' if dry else 'EXECUTING'} {len(moves)} moves, {len(deletes)} deletes\n")

    marker_updates = 0

    for src, dst, mem_type, tags in moves:
        src_rel = str(src.relative_to(VAULT))
        dst_rel = str(dst.relative_to(VAULT))

        if dst.exists() and dst != src:
            print(f"[SKIP-EXISTS] {src_rel} → {dst_rel} (destination exists)")
            continue

        tag_str = ' '.join(f'#{t}' for t in tags) if tags else ''
        type_str = f' [type→{mem_type}]' if mem_type else ''
        print(f"[move]{type_str} {src_rel} → {dst_rel} {tag_str}")

        if not dry:
            # Update frontmatter first
            try:
                content = src.read_text(encoding='utf-8')
                content = update_fm(content, mem_type, tags if tags else None)
                dst.write_text(content, encoding='utf-8')
                src.unlink()
            except Exception as e:
                print(f"  ERROR: {e}")
                continue

            # Update markers
            n = update_markers(src_rel, dst_rel, dry)
            if n:
                marker_updates += n
                print(f"  → updated {n} marker(s)")

    for path in deletes:
        rel = str(path.relative_to(VAULT))
        print(f"[delete] {rel}")
        if not dry:
            try:
                path.unlink()
            except Exception as e:
                print(f"  ERROR deleting {rel}: {e}")

    print(f"\n✓ Done. {marker_updates} markers updated.")

    if not dry:
        print("\nNext steps:")
        print("  1. Update scripts/mem.py FOLDER_LAYOUT and FOLDER_BY_TYPE")
        print("  2. Update prompts/ai-lint.md classification rules")
        print("  3. Create 90_System/Index/ index files")
        print("  4. Verify old empty folders and remove if desired")


if __name__ == "__main__":
    main()
