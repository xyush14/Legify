#!/usr/bin/env python3
"""Backfill facts_json for existing hf_judgments rows.

Walks every row in hf_judgments where facts_json IS NULL, runs the regex
fact extractor on (summary + title + text), and persists the JSON.

Idempotent: re-running only touches rows where facts_json is still NULL.
Pass --redo to re-extract ALL rows (e.g. after extractor improvements).

USAGE
-----
Local dev (against the project DB):
    python scripts/backfill_facts.py

Railway (against the volume-mounted DB):
    python scripts/backfill_facts.py --db /data/kanoon_cache.sqlite

Re-extract everything (e.g. after a fact-extractor patch):
    python scripts/backfill_facts.py --redo

PERFORMANCE
-----------
Pure-Python regex; ~1-3 ms per doc with the 20K-char text cap. 42K rows
finishes in 1-3 minutes. Commits every 1000 rows so interruption is safe.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

# Ensure repo root on sys.path
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from tqdm import tqdm
except ImportError:
    def tqdm(it, **_kwargs):
        return it

from headnote.config import KANOON_CACHE_PATH
from headnote.retrieval.fact_extractor import extract_facts


def _ensure_facts_column(conn: sqlite3.Connection) -> None:
    """Add facts_json column if it doesn't exist (idempotent)."""
    try:
        conn.execute("ALTER TABLE hf_judgments ADD COLUMN facts_json TEXT")
        conn.commit()
        print("  Added facts_json column.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise
        # Column already exists — fine.


def backfill(db_path: Path, *, redo: bool = False, batch_size: int = 1000) -> tuple[int, int]:
    """Walk rows and populate facts_json. Returns (processed, with_facts)."""
    conn = sqlite3.connect(db_path, timeout=30)
    try:
        _ensure_facts_column(conn)

        if redo:
            where = ""
            print("  --redo: re-extracting facts for ALL rows.")
        else:
            where = "WHERE facts_json IS NULL"
            print("  Backfilling rows where facts_json IS NULL only.")

        total = conn.execute(
            f"SELECT COUNT(*) FROM hf_judgments {where}"
        ).fetchone()[0]
        print(f"  Rows to process: {total:,}")
        if total == 0:
            print("  Nothing to do — all rows already have facts_json.")
            return 0, 0

        # Stream rows so we don't load 42K texts into memory
        cur = conn.execute(
            f"SELECT doc_id, title, summary, text FROM hf_judgments {where}"
        )

        processed = 0
        with_facts = 0
        batch: list[tuple[str, str]] = []   # (facts_json, doc_id)
        t0 = time.monotonic()

        pbar = tqdm(total=total, unit="docs", desc="  extracting")
        for row in cur:
            doc_id, title, summary, text = row

            fact_input = ""
            if summary:
                fact_input += summary + "\n\n"
            if title:
                fact_input += title + "\n\n"
            fact_input += (text or "")[:20000]

            try:
                facts = extract_facts(fact_input)
                facts_json = json.dumps(facts, ensure_ascii=False) if facts else ""
            except Exception:
                facts_json = ""

            if facts_json:
                with_facts += 1
            batch.append((facts_json, doc_id))
            processed += 1
            pbar.update(1)

            if len(batch) >= batch_size:
                conn.executemany(
                    "UPDATE hf_judgments SET facts_json = ? WHERE doc_id = ?",
                    batch,
                )
                conn.commit()
                batch = []

        # Flush remainder
        if batch:
            conn.executemany(
                "UPDATE hf_judgments SET facts_json = ? WHERE doc_id = ?",
                batch,
            )
            conn.commit()

        pbar.close()
        elapsed = time.monotonic() - t0
        rate = processed / elapsed if elapsed > 0 else 0
        print(
            f"\n  Done. Processed {processed:,} rows in {elapsed:.1f}s "
            f"({rate:.0f} docs/sec). {with_facts:,} had extractable facts."
        )
        return processed, with_facts

    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--db",
        default=str(KANOON_CACHE_PATH),
        help=f"SQLite DB path (default: {KANOON_CACHE_PATH})",
    )
    parser.add_argument(
        "--redo",
        action="store_true",
        help="Re-extract facts for ALL rows, not just NULL ones",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Commit batch size (default: 1000)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: DB not found at {db_path}")
        return 1

    print(f"Target DB: {db_path}")
    backfill(db_path, redo=args.redo, batch_size=args.batch_size)
    return 0


if __name__ == "__main__":
    sys.exit(main())
