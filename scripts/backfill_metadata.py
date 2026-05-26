"""
Backfill case_metadata_json for every HF judgment in the database.

Runs the regex-based metadata extractor (parties, citation, court, judges,
date, case_number) over `hf_judgments.text` and stores the JSON blob in
the new `case_metadata_json` column. Idempotent — only processes rows
where the column is NULL or empty.

This is the catalogue layer that fixes the broken case-title problem.
After this runs, retrieval can show clean "X v. State" captions instead
of garbage like "On a companyplaint filed by..."

Usage
-----
    python scripts/backfill_metadata.py                  # full backfill
    python scripts/backfill_metadata.py --limit 1000     # testing
    python scripts/backfill_metadata.py --force          # re-process all

Runtime
-------
~3-5 ms per case via regex; ~290K cases = ~15-25 min wall clock.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

# Make `headnote` importable
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from headnote.config import KANOON_CACHE_PATH
from headnote.retrieval.case_metadata_extractor import extract_metadata


def _ensure_column(conn: sqlite3.Connection) -> None:
    """Add case_metadata_json column if it doesn't exist. SQLite ALTER TABLE
    is idempotent in the sense that adding the same column twice is an
    error, so we check first."""
    cols = {row[1] for row in conn.execute("PRAGMA table_info(hf_judgments)").fetchall()}
    if "case_metadata_json" not in cols:
        conn.execute("ALTER TABLE hf_judgments ADD COLUMN case_metadata_json TEXT")
        conn.commit()
        print("[migrate] added column case_metadata_json")
    else:
        print("[migrate] case_metadata_json column already exists")


def _backfill(conn: sqlite3.Connection, limit: int | None, force: bool, batch: int) -> tuple[int, int]:
    """Process every row that doesn't yet have metadata. Returns
    (processed_count, high_confidence_count)."""
    where = "" if force else "WHERE case_metadata_json IS NULL OR case_metadata_json = ''"
    if limit:
        rows = conn.execute(
            f"SELECT doc_id, source, text FROM hf_judgments {where} LIMIT ?",
            (int(limit),),
        ).fetchall()
    else:
        rows = conn.execute(
            f"SELECT doc_id, source, text FROM hf_judgments {where}"
        ).fetchall()

    total = len(rows)
    if total == 0:
        print("[backfill] nothing to process")
        return 0, 0

    print(f"[backfill] processing {total:,} rows")
    high_conf = 0
    medium_conf = 0
    low_conf = 0
    t_start = time.time()
    batch_buf: list[tuple[str, str]] = []
    n_committed = 0

    for i, (doc_id, source, text) in enumerate(rows, 1):
        try:
            md = extract_metadata(text or "", source=source or "", doc_id=doc_id or "")
            blob = md.to_json()
            batch_buf.append((blob, doc_id))
            if md.confidence == "high":
                high_conf += 1
            elif md.confidence == "medium":
                medium_conf += 1
            else:
                low_conf += 1
        except Exception as e:
            # Don't let one bad row kill the whole backfill
            batch_buf.append(("{}", doc_id))
            print(f"[backfill] {doc_id}: extract failed: {e}")
            low_conf += 1

        if len(batch_buf) >= batch:
            conn.executemany(
                "UPDATE hf_judgments SET case_metadata_json=? WHERE doc_id=?",
                batch_buf,
            )
            conn.commit()
            n_committed += len(batch_buf)
            batch_buf = []
            elapsed = time.time() - t_start
            rate = i / elapsed
            eta = (total - i) / rate if rate > 0 else 0
            print(f"  [{i:>7,}/{total:,}] high={high_conf} med={medium_conf} low={low_conf} "
                  f"rate={rate:.0f}/s eta={eta/60:.1f}m")

    # Final commit
    if batch_buf:
        conn.executemany(
            "UPDATE hf_judgments SET case_metadata_json=? WHERE doc_id=?",
            batch_buf,
        )
        conn.commit()
        n_committed += len(batch_buf)

    elapsed = time.time() - t_start
    print()
    print(f"[backfill] done — {n_committed:,} rows updated in {elapsed/60:.1f}m")
    print(f"           high confidence: {high_conf:,}  ({100*high_conf/total:.1f}%)")
    print(f"           medium confidence: {medium_conf:,}  ({100*medium_conf/total:.1f}%)")
    print(f"           low confidence:    {low_conf:,}  ({100*low_conf/total:.1f}%)")
    return n_committed, high_conf


def _show_samples(conn: sqlite3.Connection, n: int = 5) -> None:
    """Print n sample extracted-metadata rows so the founder can sanity-check."""
    rows = conn.execute(
        "SELECT doc_id, source, case_metadata_json FROM hf_judgments "
        "WHERE case_metadata_json IS NOT NULL AND case_metadata_json != '{}' "
        "ORDER BY RANDOM() LIMIT ?",
        (n,),
    ).fetchall()
    print(f"\n=== {n} random samples ===\n")
    for doc_id, source, blob in rows:
        try:
            md = json.loads(blob)
        except Exception:
            continue
        print(f"  doc_id:     {doc_id}")
        print(f"  source:     {source}")
        print(f"  parties:    {md.get('parties')}")
        print(f"  court:      {md.get('court')}")
        print(f"  citation:   {md.get('citation')}")
        print(f"  case_no:    {md.get('case_number')}")
        print(f"  date:       {md.get('date')}")
        print(f"  confidence: {md.get('confidence')}")
        print()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(KANOON_CACHE_PATH),
                        help=f"SQLite DB path (default: {KANOON_CACHE_PATH})")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap rows processed (testing only)")
    parser.add_argument("--force", action="store_true",
                        help="Re-extract even for rows that already have metadata")
    parser.add_argument("--batch", type=int, default=500,
                        help="Commit batch size (default: 500)")
    parser.add_argument("--samples-only", action="store_true",
                        help="Skip backfill — just show 5 samples of existing metadata")
    args = parser.parse_args()

    db = Path(args.db)
    if not db.exists():
        print(f"[backfill] DB not found at {db}; nothing to do")
        return 1

    conn = sqlite3.connect(db)
    try:
        _ensure_column(conn)
        if not args.samples_only:
            _backfill(conn, limit=args.limit, force=args.force, batch=args.batch)
        _show_samples(conn, n=5)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
