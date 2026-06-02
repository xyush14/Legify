#!/usr/bin/env python3
"""Ingest the official Supreme Court open-data corpus into judgments.sqlite.

Source: the AWS Open Data registry bucket
``indian-supreme-court-judgments`` (CC-BY-4.0). Plain HTTPS — no AWS account,
no boto3, egress sponsored by the Open Data program.

Two phases, independently runnable / resumable:

  Phase A — METADATA  (fast, ~50 MB total over all 77 years)
    Downloads ``metadata/parquet/year=YYYY/metadata.parquet`` for every year
    and upserts one row per reported judgment into ``sc_judgments`` (neutral
    citation, SCR citation, CNR, parties, judges, date, disposal, path). This
    alone makes the corpus searchable/browsable with court-accepted citations.

  Phase B — OFFSETS  (the index that lets us serve real PDFs cheaply)
    Streams each year's ``english.tar`` ONCE (sequential, newest-first) and
    records every PDF's byte ``offset`` + ``size`` into ``sc_tar_offsets``.
    With that index the app serves any judgment PDF via a single HTTP Range
    request and stores ZERO tars in production. ~200–400 MB downloaded per
    year while indexing (the bytes are read, offsets kept, data discarded).

Usage
-----
  # Everything: all metadata, then offsets newest-first for ALL years.
  python scripts/ingest_opendata_sc.py --all

  # Just the metadata (do this first — it's quick and unlocks browse/search):
  python scripts/ingest_opendata_sc.py --metadata

  # Offsets for a window (recent years cover ~all real queries):
  python scripts/ingest_opendata_sc.py --offsets --years 2015-2026

  # Grind every remaining year's offsets in the background overnight:
  python scripts/ingest_opendata_sc.py --offsets --years all

Resumable: years already present are skipped unless --force.
"""

from __future__ import annotations

import argparse
import io
import re
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

import requests

# Make `headnote` importable when run as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from headnote import config  # noqa: E402

BUCKET = config.OPENDATA_SC_BUCKET
SESSION = requests.Session()


# ----------------------------------------------------------------- schema

def ensure_schema(c: sqlite3.Connection) -> None:
    c.executescript(
        """
        CREATE TABLE IF NOT EXISTS sc_judgments (
            path             TEXT PRIMARY KEY,
            year             INTEGER NOT NULL,
            title            TEXT,
            petitioner       TEXT,
            respondent       TEXT,
            case_id          TEXT,   -- spaced neutral, "2024 INSC 735"
            neutral_citation TEXT,   -- compact, "2024INSC735"
            scr_citation     TEXT,   -- "[2024] 10 S.C.R. 108"
            cnr              TEXT,
            judge            TEXT,
            author_judge     TEXT,
            decision_date    TEXT,
            disposal_nature  TEXT,
            court            TEXT DEFAULT 'Supreme Court of India'
        );
        CREATE INDEX IF NOT EXISTS ix_sc_year ON sc_judgments(year);
        CREATE INDEX IF NOT EXISTS ix_sc_nc   ON sc_judgments(neutral_citation);

        CREATE TABLE IF NOT EXISTS sc_tar_offsets (
            path     TEXT PRIMARY KEY,
            year     INTEGER NOT NULL,
            filename TEXT,
            offset   INTEGER NOT NULL,
            size     INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS ix_off_year ON sc_tar_offsets(year);

        CREATE TABLE IF NOT EXISTS sc_indexed_years (
            year       INTEGER PRIMARY KEY,
            file_count INTEGER,
            done_at    TEXT
        );
        """
    )
    c.commit()


# ----------------------------------------------------------------- discovery

def list_years() -> list[int]:
    """All years that have a metadata parquet, via the S3 list API."""
    years: list[str] = []
    token = None
    while True:
        url = (f"{BUCKET}/?list-type=2&prefix=metadata/parquet/"
               f"&delimiter=/&max-keys=1000")
        if token:
            url += f"&continuation-token={requests.utils.quote(token)}"
        xml = SESSION.get(url, timeout=60).text
        years += re.findall(r"year=(\d+)/", xml)
        m = re.search(r"<NextContinuationToken>([^<]+)</NextContinuationToken>", xml)
        if m and "<IsTruncated>true" in xml:
            token = m.group(1)
        else:
            break
    return sorted({int(y) for y in years})


def parse_year_arg(arg: str, available: list[int]) -> list[int]:
    if not arg or arg.lower() == "all":
        return available
    if "-" in arg:
        lo, hi = arg.split("-", 1)
        lo, hi = int(lo), int(hi)
        return [y for y in available if lo <= y <= hi]
    wanted = {int(x) for x in arg.split(",")}
    return [y for y in available if y in wanted]


# ----------------------------------------------------------------- phase A

def ingest_metadata(c: sqlite3.Connection, years: list[int], force: bool) -> None:
    import pyarrow.parquet as pq  # harvest-only dependency

    for y in years:
        if not force:
            n = c.execute("SELECT COUNT(*) FROM sc_judgments WHERE year=?",
                          (y,)).fetchone()[0]
            if n:
                print(f"  [meta] {y}: {n} rows already present — skip")
                continue
        url = f"{BUCKET}/metadata/parquet/year={y}/metadata.parquet"
        try:
            raw = SESSION.get(url, timeout=120).content
            tbl = pq.read_table(io.BytesIO(raw))
        except Exception as e:
            print(f"  [meta] {y}: FAILED ({e})")
            continue
        rows = tbl.to_pylist()
        batch = []
        for d in rows:
            path = (d.get("path") or "").strip()
            if not path:
                continue
            batch.append((
                path, y,
                d.get("title"), d.get("petitioner"), d.get("respondent"),
                d.get("case_id"), d.get("nc_display"), d.get("citation"),
                d.get("cnr"), d.get("judge"), d.get("author_judge"),
                d.get("decision_date"), d.get("disposal_nature"),
                d.get("court") or "Supreme Court of India",
            ))
        c.executemany(
            """INSERT OR REPLACE INTO sc_judgments
               (path, year, title, petitioner, respondent, case_id,
                neutral_citation, scr_citation, cnr, judge, author_judge,
                decision_date, disposal_nature, court)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            batch,
        )
        c.commit()
        print(f"  [meta] {y}: {len(batch)} judgments")


# ----------------------------------------------------------------- phase B

def index_offsets(c: sqlite3.Connection, years: list[int], force: bool) -> None:
    # newest-first: the years people actually query are ready soonest.
    for y in sorted(years, reverse=True):
        if not force:
            done = c.execute("SELECT 1 FROM sc_indexed_years WHERE year=?",
                             (y,)).fetchone()
            if done:
                print(f"  [offs] {y}: already indexed — skip")
                continue
        url = f"{BUCKET}/data/tar/year={y}/english/english.tar"
        t0 = time.time()
        try:
            resp = SESSION.get(url, stream=True, timeout=600)
            if resp.status_code == 404:
                print(f"  [offs] {y}: no english.tar (404) — skip")
                c.execute("INSERT OR REPLACE INTO sc_indexed_years"
                          " (year, file_count, done_at) VALUES (?,0,datetime('now'))",
                          (y,))
                c.commit()
                continue
            resp.raise_for_status()
            resp.raw.decode_content = True
            tf = tarfile.open(fileobj=resp.raw, mode="r|")
        except Exception as e:
            print(f"  [offs] {y}: FAILED to open tar ({e})")
            continue

        batch = []
        n = 0
        try:
            for m in tf:
                if not (m.isfile() and m.name.lower().endswith(".pdf")):
                    continue
                name = m.name
                if name.endswith("_EN.pdf"):
                    stem = name[:-len("_EN.pdf")]
                else:
                    stem = name[:-4]
                batch.append((stem, y, name, m.offset_data, m.size))
                n += 1
                if len(batch) >= 1000:
                    c.executemany(
                        "INSERT OR REPLACE INTO sc_tar_offsets"
                        " (path, year, filename, offset, size) VALUES (?,?,?,?,?)",
                        batch,
                    )
                    c.commit()
                    batch.clear()
        except Exception as e:
            print(f"  [offs] {y}: walk interrupted after {n} ({e})")
        if batch:
            c.executemany(
                "INSERT OR REPLACE INTO sc_tar_offsets"
                " (path, year, filename, offset, size) VALUES (?,?,?,?,?)",
                batch,
            )
            c.commit()
        c.execute("INSERT OR REPLACE INTO sc_indexed_years"
                  " (year, file_count, done_at) VALUES (?,?,datetime('now'))",
                  (y, n))
        c.commit()
        print(f"  [offs] {y}: indexed {n} PDFs in {time.time()-t0:.0f}s")


# ----------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(config.JUDGMENTS_DB),
                    help="judgments sqlite path (default: config.JUDGMENTS_DB)")
    ap.add_argument("--metadata", action="store_true", help="run phase A")
    ap.add_argument("--offsets", action="store_true", help="run phase B")
    ap.add_argument("--all", action="store_true",
                    help="metadata (all years) + offsets (all years)")
    ap.add_argument("--years", default="all",
                    help="'all', 'YYYY-YYYY', or comma list. Default all.")
    ap.add_argument("--force", action="store_true",
                    help="re-ingest even years already present")
    args = ap.parse_args()

    if not (args.metadata or args.offsets or args.all):
        ap.error("choose at least one of --metadata / --offsets / --all")

    print(f"DB: {args.db}")
    c = sqlite3.connect(args.db, timeout=30)
    c.execute("PRAGMA journal_mode=WAL")
    ensure_schema(c)

    available = list_years()
    print(f"Years available on bucket: {len(available)} "
          f"({available[0]}..{available[-1]})")
    target = parse_year_arg(args.years, available)
    print(f"Target years: {len(target)}")

    if args.metadata or args.all:
        print("\n== Phase A: metadata ==")
        ingest_metadata(c, target, args.force)
    if args.offsets or args.all:
        print("\n== Phase B: tar offsets (newest-first) ==")
        index_offsets(c, target, args.force)

    # Summary
    nj = c.execute("SELECT COUNT(*) FROM sc_judgments").fetchone()[0]
    no = c.execute("SELECT COUNT(*) FROM sc_tar_offsets").fetchone()[0]
    nyi = c.execute("SELECT COUNT(*) FROM sc_indexed_years").fetchone()[0]
    print(f"\nDone. sc_judgments={nj:,}  sc_tar_offsets={no:,}  "
          f"years_indexed={nyi}")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
