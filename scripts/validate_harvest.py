#!/usr/bin/env python3
"""Sanity-check a harvested kanoon_cache.sqlite.

Confirms:
  - hf_judgments table exists and has rows
  - facts_json column exists and is populated for most rows
  - Per-source distribution looks right
  - A sample of extracted facts looks reasonable

Run after each harvest (small test OR full) to catch silent failures.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=str(_REPO_ROOT / "kanoon_cache.sqlite"))
    parser.add_argument("--samples", type=int, default=5,
                        help="How many sample rows to display")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"ERROR: {db} does not exist")
        return 1

    conn = sqlite3.connect(db)

    total = conn.execute("SELECT COUNT(*) FROM hf_judgments").fetchone()[0]
    print(f"Total rows: {total:,}")
    if total == 0:
        print("FAIL: no rows imported")
        return 1

    with_facts = conn.execute(
        "SELECT COUNT(*) FROM hf_judgments WHERE facts_json IS NOT NULL AND facts_json != ''"
    ).fetchone()[0]
    pct = 100.0 * with_facts / total
    print(f"Rows with extracted facts: {with_facts:,} ({pct:.1f}%)")

    print("\nBy source / language:")
    for source, lang, n in conn.execute(
        "SELECT source, language, COUNT(*) FROM hf_judgments GROUP BY source, language ORDER BY source"
    ).fetchall():
        print(f"  {source:6} {lang:3}  {n:,} rows")

    print(f"\n--- {args.samples} sample rows with facts ---")
    rows = conn.execute(
        f"SELECT doc_id, title, facts_json FROM hf_judgments "
        f"WHERE facts_json IS NOT NULL AND facts_json != '' "
        f"ORDER BY RANDOM() LIMIT {args.samples}"
    ).fetchall()
    for doc_id, title, fj in rows:
        print(f"\n  {doc_id}")
        print(f"  title: {title[:80] if title else '(none)'}")
        try:
            f = json.loads(fj)
            print(f"  facts: {json.dumps(f, indent=4, ensure_ascii=False)[:600]}")
        except Exception as e:
            print(f"  facts parse error: {e}")

    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
