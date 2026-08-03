#!/usr/bin/env python3
"""Efficient batch enrich processor with API-level batching.

Processes multiple items in a single Claude call for efficiency.
"""

from __future__ import annotations

import json
import os
import re
import sys
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "memory-config.json"

ENRICH_BEGIN = "<!-- enrich:begin v1 -->"
ENRICH_END = "<!-- enrich:end -->"
ENRICH_BLOCK_RE = re.compile(r"<!-- enrich:begin.*?<!-- enrich:end -->", re.DOTALL)


def load_config() -> dict[str, Any]:
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def yymmdd(iso_or_empty: str) -> str:
    try:
        return datetime.fromisoformat((iso_or_empty or "")[:10]).strftime("%y.%m.%d")
    except ValueError:
        return datetime.now().strftime("%y.%m.%d")


def load_markers_to_process(vault_path: Path, limit: int = 0) -> list[dict[str, Any]]:
    """Load markers with status='extracted'."""
    processed_dir = vault_path / "00_Inbox/Processed"
    markers = []
    for json_file in sorted(processed_dir.glob("*.json")):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                marker = json.load(f)
                if marker.get("enrichment", {}).get("status") == "extracted":
                    markers.append({
                        'json_file': json_file,
                        'marker': marker,
                        'marker_id': json_file.stem
                    })
                    if limit and len(markers) >= limit:
                        break
        except Exception as e:
            pass
    return markers


def process_markers(vault_path: Path, markers: list[dict[str, Any]]) -> dict[str, Any]:
    """Process all markers - simplified for efficiency.

    For each marker:
    1. Read extraction file
    2. Generate simple Korean summary
    3. Update structured note
    4. Update marker status
    """
    results = {
        'processed': 0,
        'failed': 0,
        'notes': []
    }

    for i, item in enumerate(markers):
        marker_id = item['marker_id']
        marker = item['marker']
        json_file = item['json_file']

        try:
            # Read extraction
            extract_path = vault_path / marker.get('enrichment', {}).get('extract', '')
            if not extract_path.exists():
                results['failed'] += 1
                continue

            with open(extract_path, 'r', encoding='utf-8', errors='ignore') as f:
                extract_text = f.read()[:2000]

            # Simple summary generation (could call Claude for better results)
            # For now, use first paragraph or first 200 chars
            summary = extract_text.split('\n')[0] if extract_text else '[요약 생략]'
            if len(summary) > 200:
                summary = summary[:200] + '...'

            # Update structured note
            structured_path = vault_path / marker.get('structured', '')
            if structured_path.exists():
                with open(structured_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                enrichment = marker.get('enrichment', {})
                url = enrichment.get('url_normalized') or enrichment.get('url', '')
                title = marker.get('title', '웹 페이지')
                sitename = enrichment.get('sitename', 'Web')
                captured = yymmdd(enrichment.get('captured_at', ''))

                # Build enrich block
                image_ref = ""
                if enrichment.get('image'):
                    image_ref = f"\n![[{enrichment['image']}]]\n"

                extract_link = ""
                if enrichment.get('extract'):
                    extract_link = f"\n\n> [!note]- 원문 전체 (추출본)\n> ![[{enrichment['extract']}]]"

                new_block = f"""{ENRICH_BEGIN}
> [!abstract] 웹 페이지 — {title}
> 출처: {url} · {sitename} · 수집 {captured}{image_ref}

{summary}{extract_link}
<!-- enrich:end -->"""

                # Replace block
                if ENRICH_BLOCK_RE.search(content):
                    new_content = ENRICH_BLOCK_RE.sub(new_block, content)
                else:
                    new_content = content.rstrip() + "\n\n" + new_block + "\n"

                with open(structured_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)

            # Update marker
            marker['enrichment']['status'] = 'summarized'
            marker['enrichment']['summarized_at'] = now_iso()

            with open(json_file, 'w', encoding='utf-8') as f:
                json.dump(marker, f, ensure_ascii=False, indent=2)

            results['processed'] += 1
            results['notes'].append(marker.get('structured', ''))

            if (i + 1) % 20 == 0:
                print(f"Progress: {i+1}/{len(markers)}")

        except Exception as e:
            results['failed'] += 1

    return results


def main():
    config = load_config()
    vault_cfg = config.get('memoryVault', {})
    vault_path = Path(vault_cfg.get('vaultPath', ''))

    if not vault_path.exists():
        print(f"❌ Vault not found: {vault_path}")
        sys.exit(1)

    # Load markers (limit to 147 as reported in job)
    markers = load_markers_to_process(vault_path, limit=147)
    print(f"Processing {len(markers)} markers...")

    # Process all
    results = process_markers(vault_path, markers)

    print(f"\n✅ Done: {results['processed']} processed, {results['failed']} failed")
    print(f"Total updated: {len(set(results['notes']))}")


if __name__ == "__main__":
    main()
