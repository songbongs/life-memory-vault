#!/usr/bin/env python3
"""Batch AI enrich processor for staged web pages.

Reads extraction files (staged web text), generates Korean summaries via Claude,
updates structured notes, and marks markers as summarized.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "memory-config.json"
VAULT_PATH = None
PROCESSED_DIR = None

ENRICH_BEGIN = "<!-- enrich:begin v1 -->"
ENRICH_END = "<!-- enrich:end -->"
ENRICH_BLOCK_RE = re.compile(r"<!-- enrich:begin.*?<!-- enrich:end -->", re.DOTALL)


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s or "")


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def yymmdd(iso_or_empty: str) -> str:
    try:
        return datetime.fromisoformat((iso_or_empty or "")[:10]).strftime("%y.%m.%d")
    except ValueError:
        return datetime.now().strftime("%y.%m.%d")


def load_markers_to_process() -> list[dict[str, Any]]:
    """Load all markers with enrichment.status = 'extracted'."""
    markers = []
    for json_file in PROCESSED_DIR.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                marker = json.load(f)
                if marker.get("enrichment", {}).get("status") == "extracted":
                    markers.append({
                        'json_file': json_file,
                        'marker': marker,
                        'marker_id': json_file.stem
                    })
        except Exception as e:
            print(f"Error loading {json_file}: {e}")
    return sorted(markers, key=lambda x: x['json_file'].name)


def generate_summary(extract_text: str, url: str, title: str, marker_id: str) -> dict[str, str]:
    """Call Claude to generate Korean summary via command line.

    Returns:
        {
            'summary': '3-5줄 한국어 요약',
            'points': '- 포인트1\n- 포인트2\n- 포인트3',
            'tags': '#태그1 #태그2 #태그3'
        }
    """
    if len(extract_text.strip()) < 50:
        return {
            'summary': '본문이 너무 짧아 요약 불가',
            'points': '',
            'tags': ''
        }

    # Truncate to avoid huge prompts
    if len(extract_text) > 5000:
        extract_text = extract_text[:5000] + "\n\n[...이하 생략]"

    prompt = f"""다음은 웹 페이지의 추출된 원문입니다. 한국어로 요약해주세요.

URL: {url}
제목: {title}

===== 원문 시작 =====
{extract_text}
===== 원문 끝 =====

아래 형식으로 정확히 응답하세요:

**요약 (3-5줄)**
[한국어 요약]

**핵심 포인트**
- [포인트1]
- [포인트2]
- [포인트3]

**제안 태그** (최대 3개, #기호 포함)
#태그1 #태그2 #태그3

지시: 원문에 없는 내용을 지어내지 말고, 실제 내용만 요약하세요."""

    try:
        result = subprocess.run(
            ["claude", "-p", prompt, "--permission-mode", "acceptEdits", "--model", "haiku"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            print(f"  ⚠️ Claude error for {marker_id}: {result.stderr[:100]}")
            return {
                'summary': '[요약 생성 실패]',
                'points': '',
                'tags': ''
            }

        output = result.stdout.strip()

        # Parse the structured response
        summary = ""
        points = ""
        tags = ""

        if "**요약" in output:
            summary_match = re.search(r'\*\*요약.*?\n(.*?)(?=\n\*\*|$)', output, re.DOTALL)
            if summary_match:
                summary = summary_match.group(1).strip()

        if "**핵심" in output or "**포인트" in output:
            points_match = re.search(r'\*\*핵심|포인트.*?\n((?:- .*\n?)*)', output, re.DOTALL)
            if points_match:
                points = points_match.group(1).strip()

        if "**제안" in output:
            tags_match = re.search(r'\*\*제안.*?\n(.*?)(?=\n|$)', output)
            if tags_match:
                tags = tags_match.group(1).strip()

        if not summary:
            summary = output[:200] if len(output) > 200 else output

        return {
            'summary': summary or '[요약 생성 실패]',
            'points': points,
            'tags': tags
        }

    except subprocess.TimeoutExpired:
        print(f"  ⏱️ Timeout for {marker_id}")
        return {
            'summary': '[타임아웃]',
            'points': '',
            'tags': ''
        }
    except Exception as e:
        print(f"  ❌ Error generating summary for {marker_id}: {e}")
        return {
            'summary': f'[오류: {str(e)[:50]}]',
            'points': '',
            'tags': ''
        }


def update_structured_note(structured_path: Path, marker: dict[str, Any], summary_data: dict[str, str]) -> bool:
    """Update the enrich block in the structured note."""
    if not structured_path.exists():
        print(f"  ⚠️ Structured note not found: {structured_path}")
        return False

    try:
        with open(structured_path, 'r', encoding='utf-8') as f:
            content = f.read()

        enrichment = marker.get('enrichment', {})
        url = enrichment.get('url_normalized') or enrichment.get('url', '')
        image_ref = ""
        if enrichment.get('image'):
            image_ref = f"\n![[{enrichment['image']}]]\n"

        # Build the new enrich block
        title = marker.get('title', '웹 페이지')
        sitename = enrichment.get('sitename', 'Web')
        captured = yymmdd(enrichment.get('captured_at', ''))

        points_block = ""
        if summary_data.get('points'):
            points_block = f"\n**핵심 포인트**\n{summary_data['points']}"

        tags_block = ""
        if summary_data.get('tags'):
            tags_block = f"\n\n제안 태그: {summary_data['tags']}"

        # Original extract file link (preserved from original block)
        extract_link = ""
        extract_path = enrichment.get('extract', '')
        if extract_path:
            extract_link = f"\n\n> [!note]- 원문 전체 (추출본)\n> ![[{extract_path}]]"

        new_block = f"""{ENRICH_BEGIN}
> [!abstract] 웹 페이지 — {title}
> 출처: {url} · {sitename} · 수집 {captured}{image_ref}

{summary_data.get('summary', '요약 없음')}{points_block}{tags_block}{extract_link}
<!-- enrich:end -->"""

        # Replace or insert the block
        if ENRICH_BLOCK_RE.search(content):
            new_content = ENRICH_BLOCK_RE.sub(new_block, content)
        else:
            # If no block exists, append before any metadata/footer
            new_content = content.rstrip() + "\n\n" + new_block + "\n"

        with open(structured_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return True

    except Exception as e:
        print(f"  ❌ Error updating structured note: {e}")
        return False


def update_marker_json(json_file: Path, marker: dict[str, Any]) -> bool:
    """Update marker status to 'summarized'."""
    try:
        marker['enrichment']['status'] = 'summarized'
        marker['enrichment']['summarized_at'] = now_iso()

        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(marker, f, ensure_ascii=False, indent=2)

        return True
    except Exception as e:
        print(f"  ❌ Error updating marker JSON: {e}")
        return False


def extract_tags_from_summary(tags_str: str) -> list[str]:
    """Extract tag list from '# tag1 #tag2' format."""
    if not tags_str:
        return []
    tags = []
    for tag in tags_str.split():
        if tag.startswith('#'):
            tags.append(tag[1:])
        else:
            tags.append(tag)
    return tags[:3]  # Max 3 tags


def update_frontmatter_tags(structured_path: Path, new_tags: list[str]) -> bool:
    """Add proposed tags to frontmatter tags field (max 5 total)."""
    if not new_tags or not structured_path.exists():
        return True

    try:
        with open(structured_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Parse frontmatter
        if not content.startswith('---'):
            return True

        match = re.match(r'^---\n(.*?)\n---\n', content, re.DOTALL)
        if not match:
            return True

        fm_text = match.group(1)
        body = content[match.end():]

        # Parse tags
        tags_match = re.search(r'^tags:\s*\[(.*?)\]', fm_text, re.MULTILINE)
        existing_tags = []
        if tags_match:
            existing_tags = [t.strip().strip('"\'') for t in tags_match.group(1).split(',')]
            existing_tags = [t for t in existing_tags if t]

        # Merge: keep existing, add new up to 5 total
        all_tags = existing_tags + new_tags
        final_tags = all_tags[:5]

        if final_tags == existing_tags:
            return True  # No change needed

        # Update frontmatter
        tags_str = ', '.join(f'"{t}"' for t in final_tags)

        if tags_match:
            new_fm = fm_text[:tags_match.start()] + f"tags: [{tags_str}]" + fm_text[tags_match.end():]
        else:
            new_fm = fm_text.rstrip() + f"\ntags: [{tags_str}]"

        new_content = f"---\n{new_fm}\n---\n{body}"

        with open(structured_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        return True

    except Exception as e:
        print(f"  ⚠️ Error updating frontmatter tags: {e}")
        return True  # Don't fail the whole process


def process_batch(markers: list[dict[str, Any]], batch_size: int = 10) -> dict[str, Any]:
    """Process markers in batches."""
    results = {
        'total': len(markers),
        'processed': 0,
        'failed': 0,
        'notes_updated': []
    }

    for i, item in enumerate(markers):
        marker_id = item['marker_id']
        marker = item['marker']
        json_file = item['json_file']

        print(f"\n[{i+1}/{len(markers)}] Processing {marker_id}")

        # Read extraction file
        extract_path = VAULT_PATH / marker.get('enrichment', {}).get('extract', '')
        if not extract_path.exists():
            print(f"  ⚠️ Extract file not found: {extract_path}")
            results['failed'] += 1
            continue

        try:
            with open(extract_path, 'r', encoding='utf-8', errors='ignore') as f:
                extract_text = f.read()
        except Exception as e:
            print(f"  ❌ Error reading extract: {e}")
            results['failed'] += 1
            continue

        print(f"  📄 Generating summary ({len(extract_text)} chars)...")

        # Generate summary
        summary_data = generate_summary(
            extract_text,
            marker.get('enrichment', {}).get('url', ''),
            marker.get('title', ''),
            marker_id
        )
        print(f"  ✓ Summary generated")

        # Update structured note
        structured_path = VAULT_PATH / marker.get('structured', '')
        if not update_structured_note(structured_path, marker, summary_data):
            results['failed'] += 1
            continue
        print(f"  ✓ Structured note updated")

        # Extract and update tags
        proposed_tags = extract_tags_from_summary(summary_data.get('tags', ''))
        if proposed_tags:
            update_frontmatter_tags(structured_path, proposed_tags)
            print(f"  ✓ Tags updated: {proposed_tags}")

        # Update marker
        if not update_marker_json(json_file, marker):
            results['failed'] += 1
            continue
        print(f"  ✓ Marker updated")

        results['processed'] += 1
        results['notes_updated'].append(marker.get('structured', ''))

        # Progress update every 10
        if (i + 1) % batch_size == 0:
            print(f"\n✅ Progress: {i+1}/{len(markers)} ({results['processed']} processed, {results['failed']} failed)")

    return results


def main():
    global VAULT_PATH, PROCESSED_DIR

    # Load config
    config = load_config()
    vault_cfg = config.get('memoryVault', {})
    VAULT_PATH = Path(vault_cfg.get('vaultPath', ''))
    PROCESSED_DIR = VAULT_PATH / vault_cfg.get('processedFolder', '00_Inbox/Processed')

    if not VAULT_PATH.exists():
        print(f"❌ Vault not found: {VAULT_PATH}")
        sys.exit(1)

    print(f"🔍 Loading markers from {PROCESSED_DIR}")
    markers = load_markers_to_process()
    print(f"📦 Found {len(markers)} markers with 'extracted' status")

    if not markers:
        print("✅ No markers to process")
        return

    print("\n" + "="*60)
    results = process_batch(markers)
    print("\n" + "="*60)

    print(f"\n📊 Processing complete:")
    print(f"   Total: {results['total']}")
    print(f"   ✅ Processed: {results['processed']}")
    print(f"   ❌ Failed: {results['failed']}")

    if results['notes_updated']:
        print(f"\n📝 Updated notes ({len(results['notes_updated'])} total):")
        for note in results['notes_updated'][:10]:
            print(f"   - {note}")
        if len(results['notes_updated']) > 10:
            print(f"   ... and {len(results['notes_updated']) - 10} more")


if __name__ == "__main__":
    main()
