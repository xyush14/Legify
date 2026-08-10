"""Export / import the IRREPLACEABLE user data that lives only on the host volume.

Why this exists
---------------
Production splits storage two ways:

  • Supabase Postgres  — auth, cases, hearing_logs, wa_* . Lives OUTSIDE the host,
    survives any hosting migration untouched. Nothing to do here.

  • Host volume (/data) — everything below. If the volume goes away, this data is
    GONE. There is no other copy.

        kanoon_cache.sqlite : drafts, consultations, documents,
                              document_pages (scan images), document_chunks
        feedback.db         : access_grants, consumed_grants  (who has paid access)

The rest of /data (IK cache, hf_judgments corpus, embeddings, judgments.sqlite) is
DERIVED — it re-downloads/rebuilds itself on boot. We deliberately do NOT export it,
which is what keeps this dump small enough to pull over HTTP instead of moving a
2.3 GB volume file.

Usage
-----
    # on the server (or anywhere the volume is mounted)
    python scripts/export_user_data.py --out /tmp/headnote_userdata.sqlite

    # restore onto the new host, before first real traffic
    python scripts/export_user_data.py --import-from headnote_userdata.sqlite

Import is INSERT OR REPLACE keyed on each table's primary key, so it is idempotent
and safe to re-run. It never drops a table and never touches Supabase.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

# Runnable as `python scripts/export_user_data.py` from the repo root, which
# does not put the repo on sys.path — so `import headnote` would fail.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# (source_db_config_attr, table_name) — order matters on import: parents first,
# so a partial restore never leaves child rows pointing at a missing document.
_TABLES: list[tuple[str, str]] = [
    ("KANOON_CACHE_PATH", "drafts"),
    ("KANOON_CACHE_PATH", "consultations"),
    ("KANOON_CACHE_PATH", "documents"),
    ("KANOON_CACHE_PATH", "document_pages"),
    ("KANOON_CACHE_PATH", "document_chunks"),
    ("FEEDBACK_DB", "access_grants"),
    ("FEEDBACK_DB", "consumed_grants"),
]

# documents_fts is a derived FTS5 mirror, not a source of truth. It is rebuilt
# from `documents` on import rather than copied (copying a virtual table's
# shadow tables across files is fragile).


def _source_paths() -> dict[str, Path]:
    from headnote import config

    return {
        "KANOON_CACHE_PATH": Path(str(config.KANOON_CACHE_PATH)),
        "FEEDBACK_DB": Path(str(config.FEEDBACK_DB)),
    }


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row is not None


def _create_sql(conn: sqlite3.Connection, table: str) -> str | None:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (table,)
    ).fetchone()
    return row[0] if row and row[0] else None


def export(out_path: Path) -> int:
    srcs = _source_paths()
    if out_path.exists():
        out_path.unlink()
    out = sqlite3.connect(out_path)
    total = 0

    for db_key, table in _TABLES:
        src_path = srcs[db_key]
        if not src_path.exists():
            print(f"  ! {db_key} not found at {src_path} — skipping {table}")
            continue
        src = sqlite3.connect(f"file:{src_path}?mode=ro", uri=True)
        try:
            if not _table_exists(src, table):
                print(f"  - {table}: table absent, skipped")
                continue
            ddl = _create_sql(src, table)
            if ddl:
                out.execute(ddl)
            cols = [r[1] for r in src.execute(f"PRAGMA table_info({table})")]
            placeholders = ",".join("?" * len(cols))
            collist = ",".join(f'"{c}"' for c in cols)
            n = 0
            # Stream in batches so a big document_pages table (PNG blobs) never
            # has to be materialised in memory all at once.
            cur = src.execute(f"SELECT {collist} FROM {table}")
            while True:
                rows = cur.fetchmany(200)
                if not rows:
                    break
                out.executemany(
                    f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                    rows,
                )
                n += len(rows)
            out.commit()
            print(f"  ✓ {table}: {n} rows")
            total += n
        finally:
            src.close()

    out.commit()
    out.execute("VACUUM")
    out.close()
    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"\nWrote {out_path}  ({size_mb:.1f} MB, {total} rows)")
    return total


def import_into(dump_path: Path) -> int:
    if not dump_path.exists():
        print(f"error: {dump_path} does not exist", file=sys.stderr)
        return -1

    srcs = _source_paths()
    dump = sqlite3.connect(f"file:{dump_path}?mode=ro", uri=True)
    total = 0

    # Let the app create its own schema first, so we restore into tables that
    # already carry the live indexes and any additive migrations.
    from headnote.consultations import storage as consult_storage  # noqa: F401
    from headnote.documents import storage as docs_storage
    from headnote.drafter import storage as draft_storage  # noqa: F401
    from headnote.entitlements import grants  # noqa: F401

    try:
        for db_key, table in _TABLES:
            if not _table_exists(dump, table):
                continue
            dest_path = srcs[db_key]
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            dest = sqlite3.connect(dest_path, timeout=30)
            try:
                if not _table_exists(dest, table):
                    ddl = _create_sql(dump, table)
                    if ddl:
                        dest.execute(ddl)
                cols = [r[1] for r in dump.execute(f"PRAGMA table_info({table})")]
                dest_cols = {r[1] for r in dest.execute(f"PRAGMA table_info({table})")}
                # Only carry columns the destination actually has, so an older
                # dump restores cleanly onto a newer schema.
                use = [c for c in cols if c in dest_cols]
                dropped = [c for c in cols if c not in dest_cols]
                if dropped:
                    print(f"  ! {table}: destination lacks {dropped} — those values dropped")
                collist = ",".join(f'"{c}"' for c in use)
                placeholders = ",".join("?" * len(use))
                n = 0
                cur = dump.execute(f"SELECT {collist} FROM {table}")
                while True:
                    rows = cur.fetchmany(200)
                    if not rows:
                        break
                    dest.executemany(
                        f"INSERT OR REPLACE INTO {table} ({collist}) VALUES ({placeholders})",
                        rows,
                    )
                    n += len(rows)
                dest.commit()
                print(f"  ✓ {table}: {n} rows")
                total += n
            finally:
                dest.close()
    finally:
        dump.close()

    # Rebuild the keyword index from the restored documents — without this the
    # vault's search box silently returns nothing for every migrated document.
    try:
        rebuilt = docs_storage.rebuild_fts() if hasattr(docs_storage, "rebuild_fts") else None
        if rebuilt is None:
            _rebuild_fts_inline(srcs["KANOON_CACHE_PATH"])
        print("  ✓ documents_fts rebuilt")
    except Exception as e:  # non-fatal: text search degrades, data is intact
        print(f"  ! could not rebuild documents_fts ({e}) — run a reindex before go-live")

    print(f"\nRestored {total} rows")
    return total


def _rebuild_fts_inline(cache_path: Path) -> None:
    """Repopulate the standalone FTS5 mirror from `documents`."""
    conn = sqlite3.connect(cache_path, timeout=30)
    try:
        if not _table_exists(conn, "documents"):
            return
        conn.execute(
            "CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts "
            "USING fts5(doc_id UNINDEXED, title, body)"
        )
        conn.execute("DELETE FROM documents_fts")
        conn.execute(
            "INSERT INTO documents_fts (doc_id, title, body) "
            "SELECT id, title, full_text FROM documents"
        )
        conn.commit()
    finally:
        conn.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", type=Path, default=Path("headnote_userdata.sqlite"),
                    help="where to write the export (default: ./headnote_userdata.sqlite)")
    ap.add_argument("--import-from", type=Path, default=None,
                    help="restore a previously exported dump into the live DBs")
    args = ap.parse_args()

    if args.import_from:
        print(f"Importing {args.import_from} …")
        return 0 if import_into(args.import_from) >= 0 else 1

    print("Exporting user data (Supabase-backed tables are NOT included — "
          "they migrate on their own) …")
    export(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
