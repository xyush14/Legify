#!/usr/bin/env python3
"""
Walk the kanoon cache, embed any paragraphs not yet indexed.

Idempotent — safe to run repeatedly. Cost: ₹0 (no IK calls, all local).

Run:  .venv/bin/python backfill_embeddings.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
import time
from pathlib import Path

from headnote.retrieval.embeddings import EmbeddingIndex
from headnote.kanoon.parser import parse_judgment


CACHE_PATH = Path(__file__).parent / "kanoon_cache.sqlite"


def main() -> int:
    if not CACHE_PATH.exists():
        print(f"No cache at {CACHE_PATH}; nothing to backfill.")
        return 0

    idx = EmbeddingIndex(CACHE_PATH)
    before = idx.stats()
    print(f"Before: {before['paragraph_count']} paragraphs from {before['case_count']} cases indexed")

    conn = sqlite3.connect(CACHE_PATH)
    rows = conn.execute("SELECT tid, response FROM ik_doc").fetchall()
    conn.close()
    print(f"Found {len(rows)} cached IK docs to scan")

    total_new = 0
    for i, (tid, response_text) in enumerate(rows, 1):
        try:
            raw = json.loads(response_text)
            parsed = parse_judgment(
                raw.get("doc", ""),
                tid=tid,
                title_hint=raw.get("title", ""),
                court_hint=raw.get("docsource", ""),
                publishdate_hint=raw.get("publishdate", ""),
            )
        except Exception as e:
            print(f"  [{i}/{len(rows)}] tid={tid}  parse failed: {e}")
            continue

        if not parsed.paragraphs:
            print(f"  [{i}/{len(rows)}] tid={tid}  no paragraphs")
            continue

        # Build the embedding tuples
        case_id = f"ik:{tid}"
        rows_for_embed = [
            (case_id, p.id, p.num, p.structure, p.text)
            for p in parsed.paragraphs
            # skip very short paragraphs that won't carry signal
            if len(p.text) >= 40
        ]
        t0 = time.time()
        n_new = idx.upsert_paragraphs(rows_for_embed)
        elapsed = time.time() - t0
        total_new += n_new
        print(f"  [{i}/{len(rows)}] tid={tid}  {parsed.title[:50]:50s}  +{n_new:>3} embedded ({elapsed:.1f}s)")

    after = idx.stats()
    print()
    print(f"After:  {after['paragraph_count']} paragraphs from {after['case_count']} cases indexed")
    print(f"New this run: {total_new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
