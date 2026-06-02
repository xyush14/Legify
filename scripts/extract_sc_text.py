#!/usr/bin/env python3
"""Extract the text layer from the official Supreme Court PDFs into a searchable
index, so SC judgments become a first-class FACT-PATTERN discovery source in
research mode (not just a citation / official-copy layer).

What it does
------------
For each year (newest-first), streams that year's ``english.tar`` ONCE
(sequential, like the offset indexer), reads every judgment PDF, pulls its text
layer with PyMuPDF (born-digital e-SCR PDFs — no OCR), and stores the text +
an FTS5 index entry via ``headnote.judgments.opendata``:

    sc_text  (path, year, n_chars, n_pages, extracted_at, text)
    sc_fts   (path UNINDEXED, body)            -- FTS5/BM25, porter unicode61

Once populated, ``opendata.search_fulltext(tokens)`` returns the best-matching
SC judgments by relevance, and retrieval can surface them WITH their official
neutral/SCR citation and signed PDF.

Why stream the tar (not Range-GET per PDF)
------------------------------------------
We want every PDF in a year, so one sequential pass over the tar is far cheaper
than thousands of small Range requests. Extraction does NOT need the offset
index — it works for any year that has a tar, even un-indexed ones.

Resumable
---------
Paths already in ``sc_text`` are skipped. A year whose extracted count already
covers its judgment count is skipped without re-downloading. ``--force``
re-extracts.

Usage
-----
  # Recent years first (covers ~all real queries), then grind the rest:
  python scripts/extract_sc_text.py --years 2015-2026
  python scripts/extract_sc_text.py --all

  # Smoke test: just a handful of the newest judgments.
  python scripts/extract_sc_text.py --years 2026 --limit 5

Notes
-----
* Shares judgments.sqlite with the offset-indexing job — uses WAL + a long
  busy_timeout so the two coexist without "database is locked".
* PyMuPDF (fitz) is a production dependency; pypdf is the fallback. If neither
  imports, extraction yields empty text and the row is skipped.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import tarfile
import time
from pathlib import Path

import requests

# Make `headnote` importable when run as a script from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from headnote import config  # noqa: E402
from headnote.judgments import opendata  # noqa: E402

SESSION = requests.Session()
BATCH = 200  # texts are large; keep transactions short to limit lock time


# ----------------------------------------------------------------- helpers

def open_db(db_path: str) -> sqlite3.Connection:
    c = sqlite3.connect(db_path, timeout=120)
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA busy_timeout=60000")
    c.execute("PRAGMA synchronous=NORMAL")
    has_fts = opendata._ensure_text_schema(c)
    c.commit()
    if not has_fts:
        print("WARNING: FTS5 unavailable — text will be stored but not "
              "full-text searchable.")
    return c


def db_years(c: sqlite3.Connection) -> list[int]:
    return [r[0] for r in c.execute(
        "SELECT DISTINCT year FROM sc_judgments ORDER BY year").fetchall()]


def parse_year_arg(arg: str, available: list[int]) -> list[int]:
    if not arg or arg.lower() == "all":
        return available
    if "-" in arg:
        lo, hi = arg.split("-", 1)
        lo, hi = int(lo), int(hi)
        return [y for y in available if lo <= y <= hi]
    wanted = {int(x) for x in arg.split(",")}
    return [y for y in available if y in wanted]


def _stem(name: str) -> str:
    """Tar member filename -> sc_judgments.path (matches the offset indexer)."""
    if name.endswith("_EN.pdf"):
        return name[: -len("_EN.pdf")]
    return name[:-4]


def flush(c: sqlite3.Connection, has_fts: bool, text_rows: list, fts_rows: list) -> None:
    if not text_rows:
        return
    c.executemany(
        "INSERT OR REPLACE INTO sc_text "
        "(path, year, n_chars, n_pages, extracted_at, text) "
        "VALUES (?,?,?,?,datetime('now'),?)",
        text_rows,
    )
    if has_fts:
        c.executemany("DELETE FROM sc_fts WHERE path = ?",
                      [(r[0],) for r in fts_rows])
        c.executemany("INSERT INTO sc_fts (path, body) VALUES (?, ?)", fts_rows)
    c.commit()
    text_rows.clear()
    fts_rows.clear()


# ----------------------------------------------------------------- per-year

def extract_year(c: sqlite3.Connection, year: int, *, force: bool,
                 has_fts: bool, remaining: int | None) -> int:
    """Extract one year's PDFs. Returns count extracted this run."""
    n_judg = c.execute("SELECT COUNT(*) FROM sc_judgments WHERE year=?",
                        (year,)).fetchone()[0]
    done = {r[0] for r in c.execute(
        "SELECT path FROM sc_text WHERE year=?", (year,)).fetchall()}
    if not force and n_judg and len(done) >= n_judg:
        print(f"  [{year}] {len(done)}/{n_judg} already extracted — skip")
        return 0

    url = opendata._tar_url(year)
    t0 = time.time()
    try:
        resp = SESSION.get(url, stream=True, timeout=600)
        if resp.status_code == 404:
            print(f"  [{year}] no english.tar (404) — skip")
            return 0
        resp.raise_for_status()
        resp.raw.decode_content = True
        tf = tarfile.open(fileobj=resp.raw, mode="r|")
    except Exception as e:
        print(f"  [{year}] FAILED to open tar ({e})")
        return 0

    text_rows: list = []
    fts_rows: list = []
    n_ok = n_empty = n_skip = 0
    try:
        for m in tf:
            if not (m.isfile() and m.name.lower().endswith(".pdf")):
                continue
            path = _stem(m.name)
            if not force and path in done:
                n_skip += 1
                continue
            if remaining is not None and remaining <= 0:
                break
            f = tf.extractfile(m)
            if f is None:
                continue
            data = f.read()
            text, n_pages = opendata.extract_pdf_text(data)
            if not text:
                n_empty += 1
                continue
            text_rows.append((path, year, len(text), n_pages, text))
            fts_rows.append((path, text))
            n_ok += 1
            if remaining is not None:
                remaining -= 1
            if len(text_rows) >= BATCH:
                flush(c, has_fts, text_rows, fts_rows)
                print(f"  [{year}] … {n_ok} extracted "
                      f"({time.time()-t0:.0f}s)", flush=True)
    except Exception as e:
        print(f"  [{year}] walk interrupted after {n_ok} ({e})")
    finally:
        flush(c, has_fts, text_rows, fts_rows)

    print(f"  [{year}] done: {n_ok} extracted, {n_skip} already had text, "
          f"{n_empty} empty/no-text-layer in {time.time()-t0:.0f}s")
    return n_ok


# ----------------------------------------------------------------- main

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", default=str(config.JUDGMENTS_DB),
                    help="judgments sqlite path (default: config.JUDGMENTS_DB)")
    ap.add_argument("--years", default="all",
                    help="'all', 'YYYY-YYYY', or comma list. Default all.")
    ap.add_argument("--all", action="store_true",
                    help="extract every year (same as --years all)")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after N extractions total this run (testing)")
    ap.add_argument("--force", action="store_true",
                    help="re-extract even paths already stored")
    args = ap.parse_args()

    print(f"DB: {args.db}")
    c = open_db(args.db)
    has_fts = opendata._table_exists(c, "sc_fts")

    available = db_years(c)
    if not available:
        print("No sc_judgments rows — run ingest_opendata_sc.py --metadata first.")
        return 1
    target = parse_year_arg("all" if args.all else args.years, available)
    # Newest-first: the years people actually query are ready soonest.
    target = sorted(target, reverse=True)
    print(f"Years available: {len(available)} ({available[0]}..{available[-1]})")
    print(f"Target years (newest-first): {target}")

    remaining = args.limit
    total = 0
    for y in target:
        if remaining is not None and remaining <= 0:
            break
        got = extract_year(c, y, force=args.force, has_fts=has_fts,
                           remaining=remaining)
        total += got
        if remaining is not None:
            remaining -= got

    stats = opendata.text_stats()
    print(f"\nDone. Extracted {total} this run. "
          f"Corpus now: {stats['texts']:,} texts across "
          f"{stats['years_with_text']} years.")
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
