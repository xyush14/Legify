"""Shared Postgres row-store helpers for the per-matter child tables.

drafts, consultations and documents are all the same shape of problem: rows
owned by a user, optionally filed under a matter, read back newest-first. Rather
than write three near-identical Supabase backends, each storage module calls
these helpers and keeps its own SQLite path untouched.

`enabled()` is the single switch every caller uses, so a module is never half on
Postgres and half on SQLite — the thing that would quietly split a lawyer's
drafts across two stores.

Note on ids: the app mints uuid4 hex strings for these rows (not Postgres
defaults), so an id is stable whichever backend wrote it.
"""

from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

# Import config FIRST: it loads .env, and _supabase binds SUPABASE_URL /
# SERVICE_ROLE_KEY at import time. Import them the other way round and those
# constants latch to None — the durable backend would silently switch itself off
# and everything would keep working on local SQLite while looking fine.
import headnote.config  # noqa: F401  (imported for the .env side-effect)
from headnote.entitlements import _supabase

log = logging.getLogger(__name__)

# Tables whose migration has not been applied yet. A missing table is a
# deployment state, not a bug in the caller, so we note it once and let the
# caller fall back to SQLite rather than failing a lawyer's save.
_absent: set[str] = set()


def enabled() -> bool:
    """True when the durable Postgres path should be used at all.

    Two conditions, both required:
      * config.PG_CHILD_TABLES — the deliberate opt-in, DEFAULT OFF. Reads are
        Postgres-OR-SQLite, never both, so turning this on before the existing
        SQLite rows are copied across hides every draft, document and recording
        a user already has. See the note in headnote/config.py.
      * Supabase is actually configured.
    """
    if not headnote.config.PG_CHILD_TABLES:
        return False
    return _supabase._enabled()


_present: set[str] = set()


def ready(table: str) -> bool:
    """Is the durable path usable for this table right now?

    Probed once per process, because the answer cannot be inferred from a normal
    call: the Supabase wrapper logs HTTP errors and returns [], so a table that
    does not exist is indistinguishable from a table that is empty. Without this
    probe, deploying before running the migration would make a lawyer's drafts
    look like they had vanished — far worse than falling back to the local store.
    """
    if not enabled():
        return False
    # absent wins over present: a table can probe fine and then fail a write, and
    # from that moment reads must come from the same store the write went to
    if table in _absent:
        return False
    if table in _present:
        return True

    try:
        r = _supabase._http().get(f"{_supabase.SUPABASE_URL}/rest/v1/{table}",
                                  headers=_supabase._headers(),
                                  params={"select": "id", "limit": "1"}, timeout=5.0)
        if r.status_code < 400:
            _present.add(table)
            return True
        mark_absent(table, RuntimeError(f"HTTP {r.status_code}: {r.text[:120]}"))
        return False
    except Exception as e:  # noqa: BLE001 — unreachable Supabase → use the local store
        mark_absent(table, e)
        return False


def mark_absent(table: str, err: Exception) -> None:
    """Remember that a table isn't there, so we try Postgres once, not per call."""
    _present.discard(table)
    if table not in _absent:
        _absent.add(table)
        log.warning("public.%s unavailable (%s) — using the local store for now. "
                    "Run the migration to enable durable storage.", table, str(err)[:160])


def missing_table(err: Exception) -> bool:
    """Postgres/PostgREST signal for 'relation does not exist'."""
    s = str(err).lower()
    return ("does not exist" in s or "42p01" in s
            or "could not find the table" in s or "pgrst205" in s)


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _jsonify(v: Any) -> Any:
    """SQLite stores JSON as TEXT; Postgres wants the object. Accept either."""
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return {}
    return v if v is not None else {}


def parse_json(v: Any, default: Any = None) -> Any:
    """Read a JSON column back, whichever backend it came from."""
    if v is None:
        return {} if default is None else default
    if isinstance(v, str):
        try:
            return json.loads(v)
        except Exception:  # noqa: BLE001
            return {} if default is None else default
    return v


def _guard(table: str, fn, *, default=None):
    """Run a Supabase call; on a missing table degrade instead of raising."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        if missing_table(e):
            mark_absent(table, e)
            return default
        raise


class MissingTable(RuntimeError):
    """public.<table> is not there — the migration has not been applied yet."""


class WriteFailed(RuntimeError):
    """A durable write did not land, and the table exists.

    Callers must NOT fall back to SQLite on this: reads come from Postgres, so a
    SQLite-only row is invisible. Letting this reach the route is the point — an
    honest 500 costs the lawyer a retry, a silent fallback costs them the work.
    """


# Writes get a couple of retries because the failure we actually see in
# production is a single slow request, not a broken database. Before this, one
# 5s timeout was enough to condemn a table to SQLite for the whole process.
_WRITE_ATTEMPTS = 3
_RETRY_SLEEP = 0.4      # seconds, multiplied by the attempt number


def _write(table: str, what: str, fn):
    """Run a write, retrying transient failures.

    Raises MissingTable if the table isn't there (and remembers it), WriteFailed
    for anything else that outlives the retries. Never returns a value that
    means "it failed" — that ambiguity is the bug this exists to remove.
    """
    last: Optional[Exception] = None
    for attempt in range(1, _WRITE_ATTEMPTS + 1):
        try:
            return fn()
        except _supabase.SupabaseError as e:
            if missing_table(e):
                mark_absent(table, e)
                raise MissingTable(f"public.{table} does not exist: {e}") from e
            last = e
            if not e.transient or attempt == _WRITE_ATTEMPTS:
                break
            log.warning("%s on public.%s failed (attempt %d/%d), retrying: %s",
                        what, table, attempt, _WRITE_ATTEMPTS, e)
            time.sleep(_RETRY_SLEEP * attempt)
    raise WriteFailed(f"{what} on public.{table} did not land: {last}") from last


def insert(table: str, row: dict, *, json_cols: tuple[str, ...] = ()) -> Optional[dict]:
    """Write a row to Postgres. Returns the row as stored.

    Returns None for EXACTLY ONE failure: the table does not exist. That is a
    deployment state rather than an error, and it is the only failure where
    Postgres cannot already hold rows from this process — so the caller's SQLite
    fallback is safe there and nowhere else.

    Every other failure raises WriteFailed. It used to return None here too,
    which the caller read as "use SQLite", and it called mark_absent() on the
    way out. One 5s timeout therefore did three things at once: sent this row to
    SQLite, switched READS to SQLite for the rest of the process, and orphaned
    every row already written to Postgres by that same process. Writing nothing
    and saying so is recoverable; a store split down the middle is not.
    """
    payload = dict(row)
    for c in json_cols:
        if c in payload:
            payload[c] = _jsonify(payload[c])
    payload.setdefault("created_at", now())
    payload.setdefault("updated_at", now())

    def attempt() -> dict:
        res = _supabase.upsert_or_raise(table, payload)
        if res:
            return res[0]
        # A 2xx with no representation. `return=representation` should always
        # echo the row, so this is ambiguous rather than a plain failure — ask
        # whether the row is actually there before concluding anything.
        back = _supabase.select(table, params={"id": f"eq.{payload.get('id')}",
                                               "limit": "1"})
        if back:
            return back[0]
        raise _supabase.SupabaseError(
            "upsert returned no row and the row does not read back")

    try:
        return _write(table, "insert", attempt)
    except MissingTable:
        return None


def get(table: str, row_id: str, *, user_id: Optional[str] = None) -> Optional[dict]:
    params: dict[str, str] = {"id": f"eq.{row_id}", "limit": "1"}
    if user_id is not None:
        params["user_id"] = f"eq.{user_id}"
    res = _guard(table, lambda: _supabase.select(table, params=params), default=[])
    return res[0] if res else None


def listing(table: str, *, user_id: Optional[str], limit: int = 100,
            case_id: Optional[str] = None, order: str = "updated_at.desc",
            select: str = "*") -> list[dict]:
    params: dict[str, str] = {"select": select, "order": order, "limit": str(limit)}
    params["user_id"] = "is.null" if user_id is None else f"eq.{user_id}"
    if case_id is not None:
        params["case_id"] = f"eq.{case_id}"
    return _guard(table, lambda: _supabase.select(table, params=params), default=[]) or []


def update(table: str, row_id: str, patch: dict, *, user_id: Optional[str] = None,
           json_cols: tuple[str, ...] = ()) -> Optional[dict]:
    """Patch a row and return it as stored. None means no row matched the filter.

    A failed write RAISES (WriteFailed), and that distinction is the whole point
    of this function. `_supabase.update()` logs HTTP errors and returns [], so
    the old code could not tell a PATCH that never reached the database from one
    that matched nothing — it discarded both and returned `get()`, i.e. the row
    as it was BEFORE the edit. The route then answered 200 carrying the pre-edit
    row, and the draft editor's autosave printed "Saved" over an edit that no
    longer existed anywhere. Losing a lawyer's work is bad; telling them it was
    saved is worse, because it stops them retyping it.

    The returned row comes from the PATCH's own representation, not a follow-up
    read, so what the caller gets back is what the database actually holds.
    """
    payload = {k: v for k, v in patch.items() if v is not None}
    if not payload:
        return get(table, row_id, user_id=user_id)
    for c in json_cols:
        if c in payload:
            payload[c] = _jsonify(payload[c])
    payload["updated_at"] = now()
    params: dict[str, str] = {"id": f"eq.{row_id}"}
    if user_id is not None:
        params["user_id"] = f"eq.{user_id}"
    # Empty here is a real answer — nothing matched the id (or the owner filter),
    # so the caller's 404 is correct. Failures never take this path.
    res = _write(table, "update", lambda: _supabase.update_or_raise(
        table, payload, params=params))
    return res[0] if res else None


def set_field(table: str, row_id: str, field: str, value: Any, *,
              user_id: Optional[str] = None) -> bool:
    """Set one nullable column (used for the case_id link, incl. clearing it)."""
    params: dict[str, str] = {"id": f"eq.{row_id}"}
    if user_id is not None:
        params["user_id"] = f"eq.{user_id}"
    res = _guard(table, lambda: _supabase.update(table, {field: value, "updated_at": now()}, params=params), default=[])
    return bool(res)


def remove(table: str, row_id: str, *, user_id: Optional[str] = None) -> bool:
    params: dict[str, str] = {"id": f"eq.{row_id}"}
    if user_id is not None:
        params["user_id"] = f"eq.{user_id}"
    res = _guard(table, lambda: _supabase.delete(table, params=params), default=[])
    return bool(res)


def search_text(table: str, *, user_id: Optional[str], query: str,
                limit: int = 20) -> list[dict]:
    """Keyword search over the generated tsvector (migration 012)."""
    q = " & ".join(w for w in (query or "").split() if w)
    if not q:
        return []
    params: dict[str, str] = {"select": "*", "search_tsv": f"fts(simple).{q}",
                              "limit": str(limit)}
    params["user_id"] = "is.null" if user_id is None else f"eq.{user_id}"
    return _guard(table, lambda: _supabase.select(table, params=params), default=[]) or []
