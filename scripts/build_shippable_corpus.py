#!/usr/bin/env python3
"""Build the *full* shippable judgments DB — the heavy artifact that lights up
Supreme-Court FACT-PATTERN discovery (retrieval Stage 2.6) in production.

Difference from ``build_judgments_core.py``
-------------------------------------------
``build_judgments_core.py`` emits the ~14 MB metadata+offsets core that is
baked into the Docker image. This script emits the BIG one: metadata + offsets
+ **extracted text** + a **deduped FTS index**, gzipped for download. The boot
bootstrap (``_maybe_bootstrap_judgments_on_boot`` in app.py) pulls it onto the
Railway volume via ``JUDGMENTS_FULL_URL`` when the volume DB has no text yet.

The dedup (this is the win)
---------------------------
The local extractor writes a LEGACY *contentful* ``sc_fts(path UNINDEXED, body)``
that stores a second verbatim copy of every judgment body (~1.9 GB of pure
duplication at full corpus). This script rebuilds the index as a modern
*external-content* FTS5 table that keeps NO copy — the body lives once in
``sc_text``. Net: the shipped/served DB is ~40% smaller AND a single source of
truth. ``opendata.py`` reads/writes both shapes, so nothing else changes.

What it does
------------
1. Copies sc_judgments, sc_tar_offsets, sc_indexed_years, sc_text from the
   source (read-only — never contends with a running extractor's WAL writes).
2. Creates an external-content ``sc_fts`` and bulk-builds it from sc_text
   (``INSERT INTO sc_fts(sc_fts) VALUES('rebuild')``).
3. Adds the three sync triggers (keep the index consistent if ever written;
   harmless in read-only prod) and runs an FTS integrity-check.
4. VACUUMs, then gzips to ``<out>.gz`` for upload (HF dataset / R2 / etc.).

Usage
-----
  python scripts/build_shippable_corpus.py \
      --src judgments.sqlite --out judgments_full.sqlite [--gzip-level 6] \
      [--no-gzip] [--force]

Run this only AFTER extraction (scripts/extract_sc_text.py) is complete, so the
artifact carries every landmark. Reads the source READ-ONLY, so it is safe to
run while the extractor is still writing — you just capture whatever's done so
far.
"""

from __future__ import annotations

import argparse
import gzip
import shutil
import sqlite3
import sys
import time
from pathlib import Path

# Carried verbatim from the source (plain row copy). FTS is rebuilt, not copied.
COPY_TABLES = ("sc_judgments", "sc_tar_offsets", "sc_indexed_years", "sc_text")
# sc_text rows are large (tens–hundreds of KB each); keep batches small so peak
# memory stays bounded. Metadata/offset tables use the larger batch.
TEXT_BATCH = 400
META_BATCH = 5000


def _src_uri(path: Path) -> str:
    # Read-only: never locks / blocks a concurrent WAL writer.
    return f"file:{path.as_posix()}?mode=ro&immutable=0"


def _table_ddl(src: sqlite3.Connection, table: str) -> str | None:
    row = src.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def _index_ddls(src: sqlite3.Connection, table: str) -> list[str]:
    return [
        r[0]
        for r in src.execute(
            "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
            "AND sql IS NOT NULL",
            (table,),
        ).fetchall()
    ]


def _copy_table(src: sqlite3.Connection, dst: sqlite3.Connection,
                table: str, batch: int) -> int:
    cols = [r[1] for r in src.execute(f'PRAGMA table_info("{table}")').fetchall()]
    if not cols:
        return 0
    placeholders = ",".join("?" * len(cols))
    collist = ",".join(f'"{c}"' for c in cols)
    cur = src.execute(f'SELECT {collist} FROM "{table}"')
    n = 0
    while True:
        rows = cur.fetchmany(batch)
        if not rows:
            break
        dst.executemany(
            f'INSERT INTO "{table}" ({collist}) VALUES ({placeholders})', rows
        )
        n += len(rows)
    dst.commit()
    return n


def _build_external_fts(dst: sqlite3.Connection) -> None:
    """Create the deduped external-content FTS over sc_text and bulk-build it."""
    dst.execute(
        "CREATE VIRTUAL TABLE sc_fts USING fts5("
        "text, content='sc_text', content_rowid='rowid', "
        "tokenize='porter unicode61')"
    )
    # Bulk build from sc_text content (far faster than per-row triggers).
    dst.execute("INSERT INTO sc_fts(sc_fts) VALUES('rebuild')")
    # Keep-in-sync triggers (no-ops in read-only prod, correct if ever written).
    dst.execute(
        "CREATE TRIGGER sc_text_ai AFTER INSERT ON sc_text "
        "BEGIN INSERT INTO sc_fts(rowid, text) VALUES (new.rowid, new.text); END"
    )
    dst.execute(
        "CREATE TRIGGER sc_text_ad AFTER DELETE ON sc_text "
        "BEGIN INSERT INTO sc_fts(sc_fts, rowid, text) "
        "VALUES('delete', old.rowid, old.text); END"
    )
    dst.execute(
        "CREATE TRIGGER sc_text_au AFTER UPDATE ON sc_text "
        "BEGIN INSERT INTO sc_fts(sc_fts, rowid, text) "
        "VALUES('delete', old.rowid, old.text); "
        "INSERT INTO sc_fts(rowid, text) VALUES (new.rowid, new.text); END"
    )
    dst.commit()


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Build the full shippable judgments DB (text + deduped FTS).",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--src", default="judgments.sqlite",
                    help="Source full judgments DB (read-only).")
    ap.add_argument("--out", default="judgments_full.sqlite",
                    help="Output DB path (gzip lands at <out>.gz).")
    ap.add_argument("--gzip-level", type=int, default=6,
                    help="gzip compression level 1-9 (default 6).")
    ap.add_argument("--no-gzip", action="store_true",
                    help="Skip gzip; leave the raw .sqlite only.")
    ap.add_argument("--force", action="store_true",
                    help="Overwrite the output if it already exists.")
    args = ap.parse_args()

    src_path = Path(args.src)
    out_path = Path(args.out)
    gz_path = Path(str(out_path) + ".gz")

    if not src_path.exists():
        print(f"ERROR: source not found: {src_path}", file=sys.stderr)
        return 2
    if out_path.exists() and not args.force:
        print(f"ERROR: {out_path} exists. Pass --force to overwrite.",
              file=sys.stderr)
        return 2

    for p in (out_path, Path(str(out_path) + "-wal"), Path(str(out_path) + "-shm")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    t0 = time.time()
    src = sqlite3.connect(_src_uri(src_path), uri=True)
    dst = sqlite3.connect(str(out_path))
    try:
        dst.execute("PRAGMA journal_mode=DELETE")  # plain file — no wal sidecars
        dst.execute("PRAGMA synchronous=OFF")

        total = 0
        n_text = 0
        for table in COPY_TABLES:
            ddl = _table_ddl(src, table)
            if not ddl:
                print(f"  - {table}: absent in source, skipped")
                continue
            dst.execute(ddl)
            batch = TEXT_BATCH if table == "sc_text" else META_BATCH
            n = _copy_table(src, dst, table, batch)
            for idx in _index_ddls(src, table):
                dst.execute(idx)
            dst.commit()
            if table == "sc_text":
                n_text = n
            total += n
            print(f"  - {table}: {n:,} rows", flush=True)

        if n_text == 0:
            print("WARNING: sc_text had 0 rows — the source has no extracted "
                  "text yet. The artifact will NOT enable full-text discovery.",
                  file=sys.stderr)
        else:
            print(f"  building external-content FTS over {n_text:,} texts …",
                  flush=True)
            _build_external_fts(dst)
            # Verify the rebuilt index is internally consistent.
            dst.execute("INSERT INTO sc_fts(sc_fts) VALUES('integrity-check')")
            # Sanity probe: a term that must exist somewhere in the SC corpus.
            hit = dst.execute(
                "SELECT COUNT(*) FROM sc_fts WHERE sc_fts MATCH 'circumstantial'"
            ).fetchone()[0]
            print(f"  FTS integrity OK — 'circumstantial' matches {hit:,} judgments",
                  flush=True)

        print("  VACUUM …", flush=True)
        dst.commit()  # close the txn opened by the FTS integrity-check INSERT
        dst.execute("VACUUM")
        dst.commit()
    finally:
        src.close()
        dst.close()

    size_mb = out_path.stat().st_size / 1e6
    print(f"\nWrote {out_path}  ({size_mb:,.1f} MB, {total:,} rows, "
          f"{n_text:,} texts) in {time.time()-t0:.0f}s")

    if not args.no_gzip and n_text > 0:
        print(f"gzip → {gz_path} (level {args.gzip_level}) …", flush=True)
        tg = time.time()
        try:
            gz_path.unlink()
        except FileNotFoundError:
            pass
        with open(out_path, "rb") as fin, \
                gzip.open(gz_path, "wb", compresslevel=args.gzip_level) as fout:
            shutil.copyfileobj(fin, fout, length=1 << 20)
        gz_mb = gz_path.stat().st_size / 1e6
        ratio = (size_mb / gz_mb) if gz_mb else 0
        print(f"Wrote {gz_path}  ({gz_mb:,.1f} MB, {ratio:.1f}x smaller) "
              f"in {time.time()-tg:.0f}s")
        print("\nUpload this .gz and set JUDGMENTS_FULL_URL to its public URL.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
