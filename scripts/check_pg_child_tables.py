#!/usr/bin/env python3
"""Preflight for PG_CHILD_TABLES=1. Read-only; run it before every flip.

Four things have to be true before the switch can go on, and each one fails
SILENTLY if it isn't — which is exactly why this script exists rather than a
manual look at the Supabase dashboard.

  1. public.drafts / consultations / documents exist (migration 012). If one is
     missing, pgstore.ready() falls back to SQLite for it — survivable, but it
     means the flag did nothing for that table.

  2. Each one is NOT EMPTY while SQLite still holds rows. The read path is
     Postgres-OR-SQLite, never both, so flipping the flag against an empty table
     hides every draft/recording/document the user already has.

  3. documents.search_tsv is present. The Document Vault's keyword search goes
     through it (pgstore.search_text), and without it search returns nothing.

  4. saved_caselaw.matter_id is present (also migration 012). This is the nastiest
     one: headnote/api/saved_caselaw.py selects a fixed column list including
     matter_id. PostgREST rejects the WHOLE select if one column is unknown, the
     route catches the failure and returns [] — so the lawyer's Saved library goes
     silently EMPTY instead of erroring. Note this trap is live whether or not
     PG_CHILD_TABLES is on, because saved_caselaw was always in Postgres.

Usage:
    python -m scripts.check_pg_child_tables
    python -m scripts.check_pg_child_tables --db /data/kanoon_cache.sqlite
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# config first: it loads .env, and _supabase binds its constants at import time.
import headnote.config as config
from headnote.entitlements import _supabase

import httpx

CHILD_TABLES = ("drafts", "consultations", "documents")

# Columns whose absence breaks a whole select rather than one field.
REQUIRED_COLUMNS = {
    "documents": ("search_tsv",),
    "saved_caselaw": ("matter_id",),
}

OK, WARN, BAD = "PASS", "WARN", "FAIL"


def _url(table: str) -> str:
    return f"{_supabase.SUPABASE_URL}/rest/v1/{table}"


def probe(table: str, *, select: str = "id") -> tuple[bool, str]:
    """Can PostgREST serve this select? Returns (ok, detail)."""
    try:
        r = httpx.get(_url(table), headers=_supabase._headers(),
                      params={"select": select, "limit": "1"}, timeout=20.0)
    except Exception as e:  # noqa: BLE001
        return False, f"unreachable: {e}"
    if r.status_code >= 400:
        return False, f"HTTP {r.status_code}: {r.text[:200]}"
    return True, ""


def count(table: str) -> Optional[int]:
    headers = _supabase._headers()
    headers["Prefer"] = "count=exact"
    try:
        r = httpx.get(_url(table), headers=headers,
                      params={"select": "id", "limit": "0"}, timeout=30.0)
    except Exception:  # noqa: BLE001
        return None
    if r.status_code >= 400:
        return None
    total = r.headers.get("content-range", "").split("/")[-1]
    return int(total) if total.isdigit() else None


def sqlite_count(db: Path, table: str) -> Optional[int]:
    if not db.exists():
        return None
    conn = sqlite3.connect(f"file:{db.resolve().as_posix()}?mode=ro", uri=True, timeout=10)
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(description="Preflight before PG_CHILD_TABLES=1.")
    p.add_argument("--db", type=Path, default=Path(config.KANOON_CACHE_PATH),
                   help="SQLite file to compare against (default: KANOON_CACHE_PATH)")
    a = p.parse_args(argv)

    if not _supabase._enabled():
        print("FAIL  SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — "
              "pgstore.enabled() is False, so the flag would do nothing.")
        return 1

    print(f"Postgres: {_supabase.SUPABASE_URL}")
    print(f"SQLite  : {a.db}{'' if a.db.exists() else '  (not present here)'}\n")

    verdicts: list[tuple[str, str]] = []

    def say(level: str, msg: str) -> None:
        verdicts.append((level, msg))
        print(f"{level:<5} {msg}")

    # 1 + 2 — the three child tables exist and are populated
    for t in CHILD_TABLES:
        ok, detail = probe(t)
        if not ok:
            say(BAD, f"public.{t} is not selectable ({detail}) — apply "
                     f"migrations/012_child_tables.sql")
            continue
        pg, sq = count(t), sqlite_count(a.db, t)
        shape = f"postgres={pg if pg is not None else '?'}, sqlite=" \
                f"{sq if sq is not None else 'n/a'}"
        if pg == 0 and (sq or 0) > 0:
            say(BAD, f"public.{t} is EMPTY but SQLite holds {sq} row(s) ({shape}) — "
                     f"run scripts/backfill_child_tables.py --commit first, or those "
                     f"rows vanish from the app")
        elif pg is not None and sq is not None and pg < sq:
            say(WARN, f"public.{t} has fewer rows than SQLite ({shape}) — the "
                      f"backfill looks incomplete")
        else:
            say(OK, f"public.{t} exists ({shape})")

    # 3 + 4 — columns whose absence breaks an entire select
    for table, cols in REQUIRED_COLUMNS.items():
        for col in cols:
            ok, detail = probe(table, select=col)
            if ok:
                say(OK, f"{table}.{col} is applied")
            else:
                extra = ""
                if (table, col) == ("saved_caselaw", "matter_id"):
                    extra = (" — headnote/api/saved_caselaw.py selects this column, "
                             "PostgREST rejects the whole select, and the route "
                             "returns [] — the Saved library goes silently EMPTY")
                say(BAD, f"{table}.{col} is MISSING ({detail}){extra}")

    print()
    if any(level == BAD for level, _ in verdicts):
        print("NOT SAFE to set PG_CHILD_TABLES=1. Fix the FAILs above and re-run.")
        return 1
    if any(level == WARN for level, _ in verdicts):
        print("Check the WARNs above before setting PG_CHILD_TABLES=1.")
        return 1
    print("All checks passed. PG_CHILD_TABLES=1 is safe.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
