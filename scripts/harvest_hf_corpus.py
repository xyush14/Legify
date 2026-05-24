#!/usr/bin/env python3
"""Harvest the IL-TUR Indian legal corpus from HuggingFace into local SQLite.

This is a ONE-TIME (or rare cron) bulk import. Downloads ~50K-250K Indian
judgments from the IL-TUR benchmark — Supreme Court (CJPE), expert-summarised
judgments (SUMM), and district-court bail applications (BAIL) — and stores
them in the same SQLite file as the IK cache so a single Railway Volume
covers both.

USAGE
-----
Setup (one-time):
    pip install -r requirements-harvest.txt

Run a small test import (1000 rows per subset):
    python scripts/harvest_hf_corpus.py --subsets cjpe summ --limit 1000

Full import (CJPE 34K + SUMM 7K = ~41K English SC judgments, ~1.3GB):
    python scripts/harvest_hf_corpus.py --subsets cjpe summ

Full import including Hindi bail apps (adds 176K, total ~2.3GB):
    python scripts/harvest_hf_corpus.py --subsets cjpe summ bail

Target a specific DB path (e.g. local dev vs Railway Volume):
    python scripts/harvest_hf_corpus.py --db /data/kanoon_cache.sqlite

DEPLOYMENT NOTES
----------------
- Railway Hobby Volume sizing: minimum 2GB for CJPE+SUMM, 3GB for everything.
- The first run downloads ~1.6GB from HuggingFace; subsequent runs use the
  HF datasets cache.
- INSERT OR IGNORE on doc_id makes re-running idempotent — you can interrupt
  and resume without dupes.
- Hindi (BAIL) is stored with language='hi'; query separately or together
  via the language filter.

SCHEMA
------
The `hf_judgments` table is defined in headnote/kanoon/client.py
(_init_cache). This script just populates it.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

# Ensure repo root on sys.path so `from headnote.config import ...` works
# regardless of CWD.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

try:
    from datasets import load_dataset
except ImportError:
    sys.exit(
        "ERROR: `datasets` not installed.\n"
        "Run: pip install -r requirements-harvest.txt"
    )

try:
    from tqdm import tqdm
except ImportError:
    # tqdm is nice-to-have; fall back to no progress bar if missing.
    def tqdm(it, **_kwargs):
        return it

from headnote.config import KANOON_CACHE_PATH
from headnote.retrieval.fact_extractor import extract_facts


# IL-TUR is hosted under a single repo with config-named subsets.
HF_REPO = "Exploration-Lab/IL-TUR"

# Per-subset config: HF config name + how to materialise the row.
# Keep the script open/closed — adding a subset means adding one entry.
_SUBSETS = {
    "cjpe": {
        "hf_config": "cjpe",
        "court": "supreme_court",
        "language": "en",
        "description": "Court Judgment Prediction & Explanation: 34K SC judgments",
    },
    "summ": {
        "hf_config": "summ",
        "court": "supreme_court_or_hc",
        "language": "en",
        "description": "Expert-summarised: 7.1K SC + HC judgments w/ gold summaries",
    },
    "bail": {
        "hf_config": "bail",
        "court": "district_court",
        "language": "hi",
        "description": "Bail applications (Hindi): 176K district court orders",
    },
    "lsi": {
        "hf_config": "lsi",
        "court": "supreme_court_or_hc",
        "language": "en",
        "description": "Legal Statute Identification: 66K judgments mapped to statutes",
    },
    "pcr": {
        "hf_config": "pcr",
        "court": "supreme_court_or_hc",
        "language": "en",
        "description": "Prior Case Retrieval: ~8K judgments with citation graph",
    },
}


# ----------------------------------------------------------------- helpers

def _synthesize_title(text: str, doc_id: Any) -> str:
    """Use the first non-empty line of the judgment as the title.

    Indian judgments almost always begin with the court name, case caption,
    and parties on the first few lines — close enough for a title. Falls
    back to the doc_id if the text is unusable.
    """
    if not text:
        return f"Judgment {doc_id}"
    for line in text.split("\n")[:5]:
        cleaned = line.strip()
        if cleaned and len(cleaned) > 10:
            if len(cleaned) > 200:
                cleaned = cleaned[:200].rsplit(" ", 1)[0] + "…"
            return cleaned
    return f"Judgment {doc_id}"


def _coerce_text(value: Any) -> str:
    """Different IL-TUR subsets store text as either a string, a list of
    sentences, or a dict-of-sections. Flatten everything to a single string."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(str(x) for x in value if x)
    if isinstance(value, dict):
        parts = []
        for section, content in value.items():
            parts.append(f"=== {section.replace('-', ' ').title()} ===")
            parts.append(_coerce_text(content))
        return "\n".join(parts)
    return str(value)


def _label_for(subset: str, raw_label: Any) -> Optional[str]:
    """Normalise the binary label across subsets."""
    if raw_label is None:
        return None
    try:
        as_int = int(raw_label)
    except (ValueError, TypeError):
        return str(raw_label)
    if subset == "cjpe":
        return "accepted" if as_int == 1 else "rejected"
    if subset == "bail":
        return "granted" if as_int == 1 else "rejected"
    return str(as_int)


# ----------------------------------------------------------------- core

def _open_db(db_path: Path) -> sqlite3.Connection:
    """Open the DB and ensure the schema is present.

    Even though headnote.kanoon.client._init_cache normally creates the
    table at app startup, this script may run before the app has ever
    touched the DB (e.g. fresh Railway Volume). So we mirror the DDL here.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=30)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS hf_judgments (
            rowid        INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id       TEXT NOT NULL UNIQUE,
            source       TEXT NOT NULL,
            court        TEXT,
            title        TEXT,
            text         TEXT NOT NULL,
            summary      TEXT,
            label        TEXT,
            district     TEXT,
            language     TEXT NOT NULL DEFAULT 'en',
            word_count   INTEGER NOT NULL DEFAULT 0,
            raw_metadata TEXT,
            facts_json   TEXT,
            imported_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hf_source   ON hf_judgments(source);
        CREATE INDEX IF NOT EXISTS idx_hf_court    ON hf_judgments(court);
        CREATE INDEX IF NOT EXISTS idx_hf_district ON hf_judgments(district);
        CREATE INDEX IF NOT EXISTS idx_hf_language ON hf_judgments(language);
        CREATE INDEX IF NOT EXISTS idx_hf_label    ON hf_judgments(label);
    """)
    # facts_json was added after the initial schema shipped. ALTER TABLE is
    # idempotent only via column-existence check — try the add and swallow
    # the "duplicate column" error from existing DBs that already have it.
    try:
        conn.execute("ALTER TABLE hf_judgments ADD COLUMN facts_json TEXT")
        conn.commit()
    except sqlite3.OperationalError as e:
        if "duplicate column name" not in str(e).lower():
            raise
    return conn


def import_subset(
    subset: str,
    db_path: Path,
    limit: Optional[int] = None,
    batch_size: int = 500,
) -> int:
    """Stream the given IL-TUR subset into hf_judgments. Returns inserted count.

    Streams rather than loads the full split into memory — important for
    BAIL (176K rows). Commits in batches of `batch_size` so an interrupted
    run still leaves the DB in a queryable state.
    """
    if subset not in _SUBSETS:
        raise ValueError(f"Unknown subset {subset!r}. Choices: {list(_SUBSETS)}")

    cfg = _SUBSETS[subset]
    print(f"\n=== Importing IL-TUR / {cfg['hf_config']} ===")
    print(f"    {cfg['description']}")
    print(f"    court={cfg['court']} language={cfg['language']}")
    if limit:
        print(f"    LIMIT={limit:,} rows (capped for testing)")

    # IL-TUR moved its named configs ('CJPE', 'SUMM', etc.) off the legacy
    # `revision='script'` branch onto the default main revision. Try the
    # default first; fall back to `revision='script'` for older snapshots.
    try:
        ds = load_dataset(HF_REPO, cfg["hf_config"])
    except Exception as e:
        print(f"    Default revision failed ({e}); trying revision='script' fallback")
        try:
            ds = load_dataset(HF_REPO, cfg["hf_config"], revision="script")
        except Exception as e2:
            print(f"    ERROR loading dataset: {e2}")
            return 0

    inserted = 0
    skipped_empty = 0
    skipped_dup = 0
    batch = []
    now = datetime.now(timezone.utc).isoformat()

    conn = _open_db(db_path)
    try:
        # IL-TUR has multiple splits (train/dev/test). Import all — we don't
        # care about ML eval semantics, just the corpus.
        for split_name in ds:
            split = ds[split_name]
            iterator = tqdm(split, desc=f"  {cfg['hf_config']}/{split_name}", unit="docs")
            for row in iterator:
                if limit and inserted >= limit:
                    break

                row_id = row.get("id", "")
                doc_id = f"hf:{subset}:{row_id}"

                text = _coerce_text(row.get("text") or row.get("document"))
                if not text or len(text) < 100:
                    skipped_empty += 1
                    continue

                summary = _coerce_text(row.get("summary")) if "summary" in row else None
                title = _synthesize_title(text, row_id)
                label = _label_for(subset, row.get("label"))
                district = row.get("district") if subset == "bail" else None

                # Strip the heavy fields from raw_metadata — we already have
                # text/summary/label/district as columns. Keep only the
                # things we'd want to debug later (split, any extra fields).
                extras = {
                    k: v for k, v in row.items()
                    if k not in {"text", "document", "summary", "label", "id", "district"}
                }
                raw_meta = json.dumps({
                    "split": split_name,
                    "original_id": row_id,
                    **extras,
                }, ensure_ascii=False, default=str)[:5000]   # cap blob

                # Extract facts at ingest time. We feed (summary + title + text)
                # into the extractor — summary first because it's denser. Cap
                # the body at 20K chars to bound regex cost; the most salient
                # facts (statutes, parties, stage, outcome) almost always
                # appear in the opening + closing of a judgment, not the
                # middle. ~1-3 ms per doc at this cap.
                fact_input = ""
                if summary:
                    fact_input += summary + "\n\n"
                if title:
                    fact_input += title + "\n\n"
                fact_input += text[:20000]
                try:
                    facts = extract_facts(fact_input)
                    facts_json = json.dumps(facts, ensure_ascii=False) if facts else None
                except Exception:
                    # Never let a single bad row kill the whole import
                    facts_json = None

                batch.append((
                    doc_id, subset, cfg["court"], title, text, summary,
                    label, district, cfg["language"], len(text.split()),
                    raw_meta, facts_json, now,
                ))

                if len(batch) >= batch_size:
                    n_new, n_dup = _flush_batch(conn, batch)
                    inserted += n_new
                    skipped_dup += n_dup
                    batch = []

            if limit and inserted >= limit:
                break

        # Flush remainder
        if batch:
            n_new, n_dup = _flush_batch(conn, batch)
            inserted += n_new
            skipped_dup += n_dup

    finally:
        conn.commit()
        conn.close()

    print(
        f"    inserted={inserted:,}  duplicates={skipped_dup:,}  "
        f"empty/skipped={skipped_empty:,}"
    )
    return inserted


def _flush_batch(conn: sqlite3.Connection, batch: list[tuple]) -> tuple[int, int]:
    """Insert a batch with INSERT OR IGNORE; return (new_rows, duplicates)."""
    before = conn.execute("SELECT COUNT(*) FROM hf_judgments").fetchone()[0]
    conn.executemany("""
        INSERT OR IGNORE INTO hf_judgments
        (doc_id, source, court, title, text, summary, label, district,
         language, word_count, raw_metadata, facts_json, imported_at)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, batch)
    conn.commit()
    after = conn.execute("SELECT COUNT(*) FROM hf_judgments").fetchone()[0]
    new_rows = after - before
    dup = len(batch) - new_rows
    return new_rows, dup


# ----------------------------------------------------------------- main

def _print_summary(db_path: Path) -> None:
    """Final summary after all imports complete."""
    with sqlite3.connect(db_path) as c:
        total = c.execute("SELECT COUNT(*) FROM hf_judgments").fetchone()[0]
        by_source = c.execute("""
            SELECT source, language, COUNT(*), SUM(word_count)
            FROM hf_judgments GROUP BY source, language
            ORDER BY source, language
        """).fetchall()

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print("\n" + "=" * 60)
    print(f"  HARVEST COMPLETE — {total:,} judgments stored")
    print("=" * 60)
    for source, lang, n, words in by_source:
        avg_words = int(words / n) if n else 0
        print(f"    {source:6} {lang:3}  {n:>8,} docs  avg {avg_words:>6,} words")
    print(f"\n  DB: {db_path}  ({size_mb:,.1f} MB)")
    print()


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__.split("\n\n")[0],
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--subsets",
        nargs="+",
        default=["cjpe", "summ"],
        choices=list(_SUBSETS),
        help="Which IL-TUR subsets to import (default: cjpe summ)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap rows per subset (for testing). Omit for full import.",
    )
    parser.add_argument(
        "--db",
        default=str(KANOON_CACHE_PATH),
        help=f"Target SQLite path (default: {KANOON_CACHE_PATH})",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=500,
        help="Commit batch size (default: 500)",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    print(f"Target DB: {db_path}")
    print(f"Subsets:   {', '.join(args.subsets)}")

    # --- Pre-flight disk check ------------------------------------------
    # Estimated disk needed per subset, in MB. These are observed sizes after
    # SQLite compresses + indexes the imports. The Hindi BAIL subset is the
    # big one — 176K rows averaging ~1500 words each = ~2.5 GB.
    _DISK_ESTIMATE_MB = {
        "cjpe": 900,   # ~34K SC English judgments
        "summ": 200,   # ~7K SC/HC with gold summaries
        "bail": 2500,  # ~176K Hindi district-court bail orders
        "lsi":  1500,  # ~66K judgments with statute mapping
        "pcr":  250,   # ~8K judgments with citation graph
    }
    requested_mb = sum(_DISK_ESTIMATE_MB.get(s, 500) for s in args.subsets)
    try:
        import shutil
        free_bytes = shutil.disk_usage(db_path.parent if db_path.parent.exists() else Path(".")).free
        free_mb = free_bytes // (1024 * 1024)
        # Need the requested size + a 500 MB working buffer (SQLite WAL,
        # temp indexes, fastembed model file).
        needed_mb = requested_mb + 500
        if free_mb < needed_mb:
            print(f"\n  ⚠️  INSUFFICIENT DISK SPACE")
            print(f"     Free:     {free_mb:,} MB")
            print(f"     Needed:   {needed_mb:,} MB (subsets: {requested_mb:,} MB + 500 MB working buffer)")
            print(f"     Shortfall: {needed_mb - free_mb:,} MB")
            print(f"\n  Either resize the Railway Volume / free up disk, or pass --limit to test with fewer rows.")
            return 2
        print(f"Disk OK:   {free_mb:,} MB free / {needed_mb:,} MB needed")
    except Exception as e:
        # Don't block the import if the check itself fails — just log.
        print(f"(disk check failed: {e}; proceeding anyway)")

    for subset in args.subsets:
        try:
            import_subset(subset, db_path, limit=args.limit, batch_size=args.batch_size)
        except KeyboardInterrupt:
            print("\n  Interrupted. Partial data is committed; re-run to resume.")
            break
        except Exception as e:
            print(f"\n  FAILED on subset {subset}: {e}")
            continue

    _print_summary(db_path)

    # Hint the operator about the next step. Embedding the freshly-imported
    # judgments is a separate, idempotent script — it's not auto-run here
    # because (a) it has heavy ML deps not always installed on harvest
    # hosts, and (b) re-running harvest shouldn't re-embed already-indexed
    # rows.
    print("\nNEXT: embed the new judgments for semantic retrieval —")
    print("      python scripts/backfill_embeddings.py --skip-ik")
    print("      (idempotent; only embeds rows not yet in paragraph_embeddings)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
