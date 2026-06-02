#!/usr/bin/env python3
"""Build the slim *core* judgments DB shipped inside the Docker image.

The full ``judgments.sqlite`` is ~950 MB and growing (the heavy bit is the
extracted-text + FTS tables, ~99% of the file). But production only needs the
**court-accepted moat** to go live:

    sc_judgments    — 38,277 rows of metadata (neutral + SCR citation, parties,
                      judges, date, disposal) → powers SC-first ordering, the
                      IK→corpus cross-resolution, and the case-viewer header.
    sc_tar_offsets  — byte offsets → "tap → real official PDF" via one Range GET.
    sc_indexed_years— tiny bookkeeping (ingest resume marker); harmless to ship.

That core is ~14 MB — small enough to bake into the image and copy onto the
Railway volume on first boot (see ``_maybe_bootstrap_judgments_on_boot`` in
app.py). Full-text *discovery* (Stage 2.6) degrades gracefully to ``[]`` until
the text tables are present, so shipping core-only loses no correctness — only
the fact-pattern-search-over-SC feature, which comes online later.

Usage:
    python scripts/build_judgments_core.py \
        [--src judgments.sqlite] [--out judgments_core.sqlite] [--force]

Reads the source READ-ONLY (URI mode=ro) so it never contends with a running
extractor writing in WAL mode. VACUUMs the output so the shipped file is tight.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from pathlib import Path

# Tables that make up the shippable core. Order matters only for readability.
CORE_TABLES = ("sc_judgments", "sc_tar_offsets", "sc_indexed_years")


def _src_uri(path: Path) -> str:
    # Read-only URI: never locks / blocks a concurrent WAL writer.
    return f"file:{path.as_posix()}?mode=ro&immutable=0"


def _table_ddl(src: sqlite3.Connection, table: str) -> str | None:
    row = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _index_ddls(src: sqlite3.Connection, table: str) -> list[str]:
    # Explicit CREATE INDEX statements only. Autoindexes (PRIMARY KEY / UNIQUE)
    # have sql IS NULL and are recreated automatically by the table DDL.
    return [
        r[0]
        for r in src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection, table: str) -> int:
    cols = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")').fetchall()]
    if not cols:
        return 0
    placeholders = ",".join("?" * len(cols))
    collist = ",".join(f'"{c}"' for c in cols)
    cur = src.execute(f'SELECT {collist} FROM "{table}"')
    n = 0
    while True:
        batch = cur.fetchmany(5000)
        if not batch:
            break
        dst.executemany(
            f'INSERT INTO "{table}" ({collist}) VALUES ({placeholders})', batch
        )
        n += len(batch)
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the slim core judgments DB.")
    ap.add_argument("--src", default="judgments.sqlite",
                    help="Source full judgments DB (read-only).")
    ap.add_argument("--out", default="judgments_core.sqlite",
                    help="Output core DB (overwritten unless it exists w/o --force).")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite the output if it already exists.")
    args = ap.parse_args()

    src_path = Path(args.src)
    out_path = Path(args.out)

    if not src_path.exists():
        print(f"ERROR: source not found: {src_path}", file=sys.stderr)
        return 2
    if out_path.exists() and not args.force:
        print(f"ERROR: {out_path} exists. Pass --force to overwrite.", file=sys.stderr)
        return 2

    # Fresh output (drop stale -wal/-shm too so SQLite never reads a stale txn).
    for p in (out_path, Path(str(out_path) + "-wal"), Path(str(out_path) + "-shm")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    src = sqlite3.connect(_src_uri(src_path), uri=True)
    dst = sqlite3.connect(str(out_path))
    try:
        dst.execute("PRAGMA journal_mode=DELETE")  # plain file — no wal sidecars
        dst.execute("PRAGMA synchronous=OFF")
        total = 0
        for table in CORE_TABLES:
            ddl = _table_ddl(src, table)
            if not ddl:
                print(f"  - {table}: absent in source, skipped")
                continue
            dst.execute(ddl)
            n = _copy_table(src, dst, table)
            for idx in _index_ddls(src, table):
                dst.execute(idx)
            total += n
            print(f"  - {table}: {n:,} rows")
        dst.commit()
        dst.execute("VACUUM")
        dst.commit()
    finally:
        src.close()
        dst.close()

    size_mb = out_path.stat().st_size / 1e6
    print(f"\nWrote {out_path}  ({size_mb:.2f} MB, {total:,} rows total)")
    if size_mb > 40:
        print("WARNING: core is larger than expected (>40 MB) — did text tables "
              "sneak in? Check CORE_TABLES.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
