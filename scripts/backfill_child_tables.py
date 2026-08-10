#!/usr/bin/env python3
"""Copy drafts / consultations / documents from SQLite into Postgres.

WHY THIS EXISTS
---------------
config.PG_CHILD_TABLES switches those three stores from the local SQLite volume
to Postgres (migration 012). The read path is Postgres-OR-SQLite, never both, so
the moment the flag goes on, every draft, recording and document a lawyer already
has stops being read. Migration 012 creates the tables EMPTY. Until this script
has run against production, flipping the flag empties the app for paying users.

So this is step 1 of a two-step operation:

    1. python -m scripts.backfill_child_tables --db /data/kanoon_cache.sqlite
       python -m scripts.backfill_child_tables --db /data/kanoon_cache.sqlite --commit
    2. PG_CHILD_TABLES=1

RUN IT WHERE THE DATA IS. The SQLite file that matters is the one on the Fly
volume (KANOON_CACHE_PATH), not the copy in your working tree. Either run this on
the machine (`fly ssh console`) or pull the file down first. --db defaults to
KANOON_CACHE_PATH, which is the working-tree copy on a laptop.

SAFETY PROPERTIES
-----------------
  * SQLite is opened read-only (mode=ro), and only SELECT/PRAGMA are issued.
    This deliberately does NOT import the app's storage modules: their _conn()
    runs CREATE TABLE and ALTER TABLE on connect, which is a write.
  * Dry run is the default. --commit is the only thing that writes.
  * Re-runnable. Ids are app-minted uuid4 hex, so a row that is already in
    Postgres is SKIPPED, not rewritten — re-running after the flag is on will
    not stamp a lawyer's newer Postgres edit with the stale SQLite value. Use
    --overwrite for a true upsert when that is what you actually want.
  * A row that Postgres rejects is reported with its reason and does not stop the
    others. Nothing is swallowed: batches that fail are retried row-by-row so the
    output names the row and the error.

WHAT IT DOES NOT COPY
---------------------
Page images, embedding vectors and the FTS mirror. Migration 012 leaves those in
the local cache on purpose: they are derived from full_text and are rebuilt. Only
the record of the lawyer's work moves.

intake_links / intake_uploads (migration 013) are not here either — that feature
shipped Postgres-first, so there is no legacy SQLite data to move.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Import config FIRST: it loads .env, and _supabase binds SUPABASE_URL /
# SERVICE_ROLE_KEY at import time. The other order latches them to None.
import headnote.config as config
from headnote.entitlements import _supabase

import httpx


# --------------------------------------------------------------- table specs
#
# Columns are listed explicitly rather than SELECT *, because the two schemas
# have to agree and an explicit list is the thing you can eyeball against
# migrations/012_child_tables.sql. tests/test_backfill_child_tables.py asserts
# each list matches BOTH the storage module's own column tuple and the migration,
# so a column added on one side and not the other fails a test instead of
# silently not being copied.


@dataclass(frozen=True)
class Spec:
    name: str                              # SQLite table name == public.<name>
    cols: tuple[str, ...]                  # copied, in no particular order
    json_cols: tuple[str, ...] = ()         # TEXT in SQLite, jsonb in Postgres
    bool_cols: tuple[str, ...] = ()         # INTEGER 0/1 in SQLite, boolean in PG
    int_cols: tuple[str, ...] = ()
    # Postgres NOT NULL columns with a default: a missing value is coerced rather
    # than losing the row over a display field.
    coerce: dict[str, Any] = field(default_factory=dict)
    # Postgres NOT NULL with no sensible substitute: a missing value means the
    # row is broken and is reported, not guessed at.
    required: tuple[str, ...] = ()
    order_by: str = "created_at"


DRAFTS = Spec(
    name="drafts",
    cols=("id", "user_id", "case_id", "story_id", "template_version", "lang",
          "answers_json", "title", "created_at", "updated_at", "exported_at",
          "exported_format"),
    json_cols=("answers_json",),
    int_cols=("template_version",),
    coerce={"template_version": 1, "lang": "en", "answers_json": {}},
    required=("story_id",),
    order_by="updated_at",
)

CONSULTATIONS = Spec(
    name="consultations",
    cols=("id", "user_id", "case_id", "title", "matter_type", "parties", "court",
          "lang", "duration_sec", "consent", "transcript", "report_json",
          "created_at", "updated_at"),
    json_cols=("report_json",),
    bool_cols=("consent",),
    int_cols=("duration_sec",),
    coerce={"consent": False, "report_json": {}},
)

DOCUMENTS = Spec(
    name="documents",
    cols=("id", "user_id", "case_id", "title", "doc_type", "original_filename",
          "mime", "page_count", "full_text", "metadata_json", "created_at",
          "updated_at"),
    json_cols=("metadata_json",),
    int_cols=("page_count",),
    coerce={"title": "", "page_count": 1, "full_text": "", "metadata_json": {}},
    order_by="updated_at",
)

SPECS = {s.name: s for s in (DRAFTS, CONSULTATIONS, DOCUMENTS)}

# created_at / updated_at are NOT NULL DEFAULT now() in Postgres. If SQLite has
# no value we omit the key so the default applies, rather than sending null.
_DEFAULTED_TIMESTAMPS = ("created_at", "updated_at")

_BATCH = 50


# ------------------------------------------------------------------- SQLite
# Read-only. Every statement below is a SELECT or a PRAGMA.

def open_ro(path: Path) -> sqlite3.Connection:
    if not path.exists():
        sys.exit(f"no SQLite database at {path} — pass --db with the path on the volume")
    uri = f"file:{path.resolve().as_posix()}?mode=ro"
    return sqlite3.connect(uri, uri=True, timeout=10)


def sqlite_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}


def sqlite_count(conn: sqlite3.Connection, table: str) -> Optional[int]:
    try:
        return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
    except sqlite3.Error:
        return None      # table not in this database at all


def read_rows(conn: sqlite3.Connection, spec: Spec) -> tuple[list[dict], list[str]]:
    """Read every row as a dict. Returns (rows, columns_absent_from_sqlite).

    Older databases predate the guarded `ALTER TABLE ... ADD COLUMN case_id`, and
    a read-only connection cannot add it — so select what is actually there and
    report the gap instead of failing.
    """
    have = sqlite_columns(conn, spec.name)
    use = [c for c in spec.cols if c in have]
    absent = [c for c in spec.cols if c not in have]
    order = spec.order_by if spec.order_by in have else "id"
    sql = f"SELECT {', '.join(use)} FROM {spec.name} ORDER BY {order}"
    return [dict(zip(use, r)) for r in conn.execute(sql).fetchall()], absent


# ----------------------------------------------------------------- Postgres

def _base_url() -> str:
    if not _supabase._enabled():
        sys.exit("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — nothing to copy into")
    return f"{_supabase.SUPABASE_URL}/rest/v1"


def pg_count(table: str) -> Optional[int]:
    """Row count via PostgREST's Content-Range. None = the table is not there."""
    headers = _supabase._headers()
    headers["Prefer"] = "count=exact"
    r = httpx.get(f"{_base_url()}/{table}", headers=headers,
                  params={"select": "id", "limit": "0"}, timeout=30.0)
    if r.status_code >= 400:
        return None
    rng = r.headers.get("content-range", "")
    total = rng.split("/")[-1] if "/" in rng else ""
    return int(total) if total.isdigit() else None


def pg_ids(table: str, *, page: int = 1000) -> set[str]:
    """Every id already in the table, so a re-run can skip instead of overwrite."""
    out: set[str] = set()
    offset = 0
    while True:
        r = httpx.get(f"{_base_url()}/{table}", headers=_supabase._headers(),
                      params={"select": "id", "order": "id",
                              "limit": str(page), "offset": str(offset)},
                      timeout=60.0)
        r.raise_for_status()
        got = r.json() or []
        out.update(str(row["id"]) for row in got)
        if len(got) < page:
            return out
        offset += page


def pg_case_ids() -> set[str]:
    """Ids in public.cases, to check the case_id link before relying on it.

    case_id is a FK. A row pointing at a matter that is not in Postgres would be
    rejected outright, so a stale link would cost the lawyer the whole draft. The
    link is worth less than the draft: unknown links are cleared and counted.
    """
    return pg_ids("cases")


# ------------------------------------------------------------- row transform

def _is_uuid(v: Any) -> bool:
    try:
        uuid.UUID(str(v))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _to_json(v: Any) -> Optional[Any]:
    """SQLite holds JSON as TEXT. None means it would not parse."""
    if v is None or v == "":
        return {}
    if isinstance(v, (dict, list)):
        return v
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return None


@dataclass
class Prepared:
    payload: dict
    unlinked_case: bool = False
    repaired_json: tuple[str, ...] = ()


def prepare(row: dict, spec: Spec, *, known_cases: set[str]) -> tuple[Optional[Prepared], str]:
    """Turn a SQLite row into a Postgres payload. Returns (prepared, skip_reason)."""
    out: dict[str, Any] = {}
    repaired: list[str] = []
    unlinked = False

    row_id = row.get("id")
    if not row_id:
        return None, "no id"

    for col in spec.cols:
        if col not in row:
            continue                        # column absent from this SQLite file
        v = row[col]

        if col in spec.json_cols:
            parsed = _to_json(v)
            if parsed is None:
                repaired.append(col)
                parsed = {}
            out[col] = parsed
            continue

        if col in spec.bool_cols:
            out[col] = bool(v)
            continue

        if col in spec.int_cols:
            try:
                out[col] = int(v) if v is not None else None
            except (TypeError, ValueError):
                out[col] = None
            continue

        out[col] = v

    # user_id is `uuid references auth.users`. A non-uuid is a local-dev or
    # synthetic id, never a real advocate's row — Postgres would reject it, and
    # nulling it would file the row under the anonymous listing instead, so skip.
    uid = out.get("user_id")
    if uid is not None and not _is_uuid(uid):
        return None, f"user_id is not a uuid ({str(uid)[:24]!r})"

    cid = out.get("case_id")
    if cid is not None:
        if not _is_uuid(cid) or str(cid) not in known_cases:
            out["case_id"] = None
            unlinked = True

    for col, fallback in spec.coerce.items():
        if col in out and out[col] in (None, ""):
            out[col] = fallback

    for col in spec.required:
        if not out.get(col):
            return None, f"{col} is empty and Postgres requires it"

    for col in _DEFAULTED_TIMESTAMPS:
        if col in out and not out[col]:
            del out[col]                     # let the Postgres default apply

    return Prepared(payload=out, unlinked_case=unlinked,
                    repaired_json=tuple(repaired)), ""


# ------------------------------------------------------------------- writing

def write_rows(table: str, rows: list[dict], *, overwrite: bool) -> tuple[int, list[str]]:
    """Upsert in batches; on a batch failure retry row-by-row to name the culprit.

    A batch is one statement, so one bad row fails all fifty. Falling back to
    single rows means a bad row costs one row, and the error message says which.
    """
    written, errors = 0, []
    conflict = "id" if overwrite else None
    for i in range(0, len(rows), _BATCH):
        batch = rows[i:i + _BATCH]
        try:
            res = _supabase.upsert_or_raise(table, batch, on_conflict=conflict,
                                            timeout=120.0)
            written += len(res) or len(batch)
            continue
        except _supabase.SupabaseError as e:
            print(f"    batch of {len(batch)} failed ({e}) — retrying row by row")
        for row in batch:
            try:
                _supabase.upsert_or_raise(table, row, on_conflict=conflict,
                                          timeout=60.0)
                written += 1
            except _supabase.SupabaseError as e:
                errors.append(f"{row.get('id')}: {e}")
    return written, errors


# ---------------------------------------------------------------------- main

@dataclass
class Result:
    table: str
    sqlite: Optional[int] = None
    pg_before: Optional[int] = None
    pg_after: Optional[int] = None
    to_copy: int = 0
    already: int = 0
    skipped: list[str] = field(default_factory=list)
    written: int = 0
    errors: list[str] = field(default_factory=list)
    unlinked: int = 0
    repaired_json: int = 0
    absent_cols: list[str] = field(default_factory=list)


def run_table(conn: sqlite3.Connection, spec: Spec, *, commit: bool,
              overwrite: bool, known_cases: set[str], verbose: bool) -> Result:
    res = Result(table=spec.name)
    res.sqlite = sqlite_count(conn, spec.name)
    res.pg_before = pg_count(spec.name)

    print(f"\n── {spec.name}")
    if res.pg_before is None:
        print(f"    public.{spec.name} is NOT READABLE — apply migrations/012_child_tables.sql first")
        return res
    if res.sqlite is None:
        print(f"    no `{spec.name}` table in this SQLite file — nothing to copy")
        return res

    rows, res.absent_cols = read_rows(conn, spec)
    if res.absent_cols:
        print(f"    columns absent from SQLite (left at the Postgres default): "
              f"{', '.join(res.absent_cols)}")

    existing = pg_ids(spec.name)
    payloads: list[dict] = []
    for row in rows:
        rid = str(row.get("id") or "")
        if rid in existing and not overwrite:
            res.already += 1
            continue
        prepared, reason = prepare(row, spec, known_cases=known_cases)
        if prepared is None:
            res.skipped.append(f"{rid or '<no id>'}: {reason}")
            continue
        res.unlinked += int(prepared.unlinked_case)
        res.repaired_json += int(bool(prepared.repaired_json))
        payloads.append(prepared.payload)

    res.to_copy = len(payloads)
    print(f"    sqlite={res.sqlite}  postgres={res.pg_before}  "
          f"already there={res.already}  to copy={res.to_copy}  "
          f"skipped={len(res.skipped)}")
    if res.unlinked:
        print(f"    {res.unlinked} row(s) point at a matter that is not in "
              f"public.cases — the case_id link is cleared, the row is kept")
    if res.repaired_json:
        print(f"    {res.repaired_json} row(s) had unparseable JSON — stored as {{}}")
    for s in res.skipped if verbose else res.skipped[:5]:
        print(f"    SKIP {s}")
    if not verbose and len(res.skipped) > 5:
        print(f"    … and {len(res.skipped) - 5} more (use --verbose)")

    if not payloads:
        res.pg_after = res.pg_before
        return res
    if not commit:
        print(f"    DRY RUN — would write {len(payloads)} row(s). Re-run with --commit.")
        res.pg_after = res.pg_before
        return res

    res.written, res.errors = write_rows(spec.name, payloads, overwrite=overwrite)
    res.pg_after = pg_count(spec.name)
    print(f"    wrote {res.written}, failed {len(res.errors)}  →  postgres={res.pg_after}")
    for e in res.errors if verbose else res.errors[:5]:
        print(f"    FAIL {e}")
    if not verbose and len(res.errors) > 5:
        print(f"    … and {len(res.errors) - 5} more (use --verbose)")
    return res


def main(argv: Optional[list[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="Copy drafts/consultations/documents from SQLite into Postgres.",
        epilog="Dry run by default. Run it where the volume is, not on a laptop copy.")
    p.add_argument("--db", type=Path, default=Path(config.KANOON_CACHE_PATH),
                   help="SQLite file to read (default: KANOON_CACHE_PATH)")
    p.add_argument("--commit", action="store_true",
                   help="actually write to Postgres (default is a dry run)")
    p.add_argument("--overwrite", action="store_true",
                   help="rewrite rows already in Postgres. OFF by default so a "
                        "re-run cannot stamp a newer Postgres edit with a stale "
                        "SQLite value.")
    p.add_argument("--tables", default=",".join(SPECS),
                   help=f"comma-separated subset of: {', '.join(SPECS)}")
    p.add_argument("--verbose", action="store_true",
                   help="list every skipped row and every failure")
    a = p.parse_args(argv)

    wanted = [t.strip() for t in a.tables.split(",") if t.strip()]
    unknown = [t for t in wanted if t not in SPECS]
    if unknown:
        p.error(f"unknown table(s): {', '.join(unknown)}")

    print(f"SQLite : {a.db}  (read-only)")
    print(f"Postgres: {_supabase.SUPABASE_URL}")
    print(f"Mode   : {'COMMIT' if a.commit else 'DRY RUN'}"
          f"{'  +overwrite' if a.overwrite else ''}")

    known_cases = pg_case_ids()
    print(f"public.cases holds {len(known_cases)} matter(s) to link against")

    conn = open_ro(a.db)
    try:
        results = [run_table(conn, SPECS[t], commit=a.commit, overwrite=a.overwrite,
                             known_cases=known_cases, verbose=a.verbose)
                   for t in wanted]
    finally:
        conn.close()

    print("\n" + "=" * 78)
    print(f"{'table':<16}{'sqlite':>9}{'pg before':>11}{'to copy':>9}"
          f"{'skipped':>9}{'written':>9}{'pg after':>10}")
    for r in results:
        print(f"{r.table:<16}{_n(r.sqlite):>9}{_n(r.pg_before):>11}{r.to_copy:>9}"
              f"{len(r.skipped):>9}{r.written:>9}{_n(r.pg_after):>10}")

    failed = sum(len(r.errors) for r in results)
    skipped = sum(len(r.skipped) for r in results)
    missing = [r.table for r in results if r.pg_before is None]
    if missing:
        print(f"\nMISSING TABLES: {', '.join(missing)} — apply migration 012 and re-run.")
    if not a.commit:
        print("\nDry run only. Nothing was written. Re-run with --commit.")
    elif failed == 0 and skipped == 0 and not missing:
        print("\nEvery row copied. PG_CHILD_TABLES=1 is safe for these tables "
              "once you have confirmed the counts above match.")
    else:
        print(f"\n{failed} write failure(s), {skipped} row(s) skipped. "
              "Do NOT set PG_CHILD_TABLES=1 until these are resolved — those "
              "rows would disappear from the app.")
    return 1 if (failed or missing) else 0


def _n(v: Optional[int]) -> str:
    return "—" if v is None else str(v)


if __name__ == "__main__":
    raise SystemExit(main())
