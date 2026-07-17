"""Persistence for the Matters diary (cases + hearing logs).

TWO backends behind one set of function signatures:

  • Supabase Postgres (public.cases / public.hearing_logs) — used whenever
    SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY are set (i.e. production). This is
    the DURABLE, cross-device store: a lawyer's diary survives deploys and shows
    up on every device they log in from. Same REST wrapper the rest of the app
    uses (headnote/entitlements/_supabase.py). Tables: migrations/009_matters.sql.

  • Local SQLite (KANOON_CACHE_PATH) — the fallback when Supabase isn't
    configured (local dev), so the flow still works end-to-end with zero setup.

Everything is scoped by user_id (the Supabase auth `sub`, or the local-dev
synthetic id). A case is unique per (user_id, cnr): re-adding the same CNR
refreshes it in place.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH
from headnote.entitlements import _supabase


_CASES = "cases"
_LOGS = "hearing_logs"


def _use_sb() -> bool:
    """Prefer Supabase when it's configured; else fall back to local SQLite."""
    return _supabase._enabled()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ Supabase backend
def _sb_row(r: Optional[dict]) -> Optional[dict]:
    """Normalise a PostgREST row to the shape callers expect (case_json a dict)."""
    if not r:
        return None
    r = dict(r)
    cj = r.get("case_json")
    if isinstance(cj, str):
        try:
            cj = json.loads(cj)
        except Exception:  # noqa: BLE001
            cj = {}
    r["case_json"] = cj or {}
    return r


def _sb_add_case(user_id, case: dict) -> Optional[dict]:
    cnr = case.get("cnr")
    if not cnr:
        raise ValueError("case dict missing 'cnr'")
    payload = {
        "user_id": user_id, "cnr": cnr,
        "case_title": case.get("case_title"), "court_name": case.get("court_name"),
        "case_number": case.get("case_number"), "case_year": case.get("case_year"),
        "stage": case.get("stage"), "next_hearing_date": case.get("next_hearing_date"),
        "case_json": case, "source": case.get("source"), "updated_at": _now(),
    }  # NB: no id / created_at → insert uses defaults, update leaves them intact
    rows = _supabase.upsert(_CASES, payload, on_conflict="user_id,cnr")
    if rows:
        return _sb_row(rows[0])
    hit = _supabase.select(_CASES, params={"user_id": f"eq.{user_id}",
                                           "cnr": f"eq.{cnr}", "limit": "1"})
    return _sb_row(hit[0]) if hit else None


def _sb_get_case(case_id, user_id) -> Optional[dict]:
    rows = _supabase.select(_CASES, params={"id": f"eq.{case_id}",
                                            "user_id": f"eq.{user_id}", "limit": "1"})
    return _sb_row(rows[0]) if rows else None


def _sb_list_cases(user_id, limit: int) -> list[dict]:
    rows = _supabase.select(_CASES, params={"user_id": f"eq.{user_id}",
                                            "order": "updated_at.desc",
                                            "limit": str(limit)})
    return [_sb_row(r) for r in rows]


def _sb_find_by_number(user_id, case_number, case_year, court_name) -> Optional[dict]:
    cn = (case_number or "").replace(" ", "").strip()
    if not cn:
        return None
    rows = _supabase.select(_CASES, params={"user_id": f"eq.{user_id}",
                                            "case_number": f"eq.{cn}",
                                            "order": "updated_at.desc"})
    cands = [_sb_row(r) for r in rows]
    yr = (case_year or "").strip()[-2:]
    if yr:
        cands = [r for r in cands
                 if not (r.get("case_year") or "") or (r.get("case_year") or "")[-2:] == yr]
    if not cands:
        return None
    if court_name:
        court = court_name.strip().lower()
        exact = [r for r in cands if (r.get("court_name") or "").strip().lower() == court]
        if exact:
            return exact[0]
    return cands[0]


def _sb_update_matter_basics(case_id, user_id, court_name, case_title) -> Optional[dict]:
    row = _sb_get_case(case_id, user_id)
    if row is None:
        return None
    court_name = (court_name or "").strip() or None
    case_title = (case_title or "").strip() or None
    if not (court_name or case_title):
        return row
    cj = row["case_json"] or {}
    payload = {"updated_at": _now()}
    if court_name:
        payload["court_name"] = court_name; cj["court_name"] = court_name
    if case_title:
        payload["case_title"] = case_title; cj["case_title"] = case_title
    payload["case_json"] = cj
    _supabase.update(_CASES, payload, params={"id": f"eq.{case_id}", "user_id": f"eq.{user_id}"})
    return _sb_get_case(case_id, user_id)


def _sb_replace_identity(case_id, user_id, case: dict) -> Optional[dict]:
    row = _sb_get_case(case_id, user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    merged = dict(case)
    if cj.get("client"):
        merged["client"] = {**(case.get("client") or {}), **cj["client"]}
    payload = {
        "cnr": merged.get("cnr"), "case_title": merged.get("case_title"),
        "court_name": merged.get("court_name"), "case_number": merged.get("case_number"),
        "case_year": merged.get("case_year"), "stage": merged.get("stage"),
        "next_hearing_date": merged.get("next_hearing_date"),
        "case_json": merged, "source": merged.get("source"), "updated_at": _now(),
    }
    res = _supabase.update(_CASES, payload,
                           params={"id": f"eq.{case_id}", "user_id": f"eq.{user_id}"})
    # conflict on the new (user_id, cnr) → wrapper returns [] → keep the matter as-is
    return _sb_row(res[0]) if res else row


def _sb_delete_case(case_id, user_id) -> bool:
    res = _supabase.delete(_CASES, params={"id": f"eq.{case_id}", "user_id": f"eq.{user_id}"})
    return bool(res)


def _sb_delete_all(user_id) -> int:
    _supabase.delete(_LOGS, params={"user_id": f"eq.{user_id}"})
    res = _supabase.delete(_CASES, params={"user_id": f"eq.{user_id}"})
    return len(res or [])


def _sb_update_client(case_id, user_id, client: dict) -> Optional[dict]:
    row = _sb_get_case(case_id, user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    cj["client"] = {**(cj.get("client") or {}), **(client or {})}
    _supabase.update(_CASES, {"case_json": cj, "updated_at": _now()},
                     params={"id": f"eq.{case_id}", "user_id": f"eq.{user_id}"})
    return _sb_get_case(case_id, user_id)


def _sb_set_next_date(case_id, user_id, next_hearing_date, stage) -> Optional[dict]:
    row = _sb_get_case(case_id, user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    payload = {"updated_at": _now()}
    if next_hearing_date is not None:
        payload["next_hearing_date"] = next_hearing_date; cj["next_hearing_date"] = next_hearing_date
    if stage is not None:
        payload["stage"] = stage; cj["stage"] = stage
    payload["case_json"] = cj
    _supabase.update(_CASES, payload, params={"id": f"eq.{case_id}", "user_id": f"eq.{user_id}"})
    return _sb_get_case(case_id, user_id)


def _sb_log_hearing(case_id, user_id, hearing_date, what_happened,
                    next_hearing_date, stage) -> Optional[dict]:
    row = _sb_get_case(case_id, user_id)
    if row is None:
        return None
    _supabase.upsert(_LOGS, {
        "user_id": user_id, "case_id": case_id, "hearing_date": hearing_date,
        "what_happened": what_happened, "next_hearing_date": next_hearing_date,
        "stage": stage,
    })  # append-only insert (no on_conflict)
    return _sb_set_next_date(case_id, user_id, next_hearing_date, stage)


def _sb_list_hearing_logs(case_id, user_id) -> list[dict]:
    rows = _supabase.select(_LOGS, params={"case_id": f"eq.{case_id}",
                                           "user_id": f"eq.{user_id}",
                                           "order": "created_at.desc"})
    return [{"id": r.get("id"), "hearing_date": r.get("hearing_date"),
             "what_happened": r.get("what_happened"),
             "next_hearing_date": r.get("next_hearing_date"),
             "stage": r.get("stage"), "created_at": r.get("created_at")} for r in rows]


# =============================================================== SQLite backend
_COLS = ("id, user_id, cnr, case_title, court_name, case_number, case_year, "
         "stage, next_hearing_date, case_json, source, created_at, updated_at")


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            id                TEXT PRIMARY KEY,
            user_id           TEXT,
            cnr               TEXT NOT NULL,
            case_title        TEXT,
            court_name        TEXT,
            case_number       TEXT,
            case_year         TEXT,
            stage             TEXT,
            next_hearing_date TEXT,
            case_json         TEXT NOT NULL,
            source            TEXT,
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_user_cnr ON cases(user_id, cnr);
        CREATE INDEX IF NOT EXISTS idx_cases_user    ON cases(user_id);
        CREATE INDEX IF NOT EXISTS idx_cases_updated ON cases(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cases_user_next ON cases(user_id, next_hearing_date);

        CREATE TABLE IF NOT EXISTS hearing_logs (
            id                TEXT PRIMARY KEY,
            user_id           TEXT,
            case_id           TEXT NOT NULL,
            hearing_date      TEXT,
            what_happened     TEXT,
            next_hearing_date TEXT,
            stage             TEXT,
            created_at        TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_hlog_case ON hearing_logs(case_id);
        CREATE INDEX IF NOT EXISTS idx_hlog_user_next ON hearing_logs(user_id, next_hearing_date);
    """)
    conn.commit()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(KANOON_CACHE_PATH, timeout=10)
    try:
        _init_schema(c)
        yield c
    finally:
        c.close()


def _row(r) -> Optional[dict]:
    if not r:
        return None
    return {
        "id": r[0], "user_id": r[1], "cnr": r[2], "case_title": r[3],
        "court_name": r[4], "case_number": r[5], "case_year": r[6],
        "stage": r[7], "next_hearing_date": r[8],
        "case_json": json.loads(r[9] or "{}"),
        "source": r[10], "created_at": r[11], "updated_at": r[12],
    }


def _sq_add_case(user_id, case: dict) -> Optional[dict]:
    cnr = case.get("cnr")
    if not cnr:
        raise ValueError("case dict missing 'cnr'")
    now = _now()
    cid = uuid.uuid4().hex
    payload = json.dumps(case, ensure_ascii=False)
    with _conn() as c:
        c.execute(
            """INSERT INTO cases
                 (id, user_id, cnr, case_title, court_name, case_number, case_year,
                  stage, next_hearing_date, case_json, source, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id, cnr) DO UPDATE SET
                 case_title        = excluded.case_title,
                 court_name        = excluded.court_name,
                 case_number       = excluded.case_number,
                 case_year         = excluded.case_year,
                 stage             = excluded.stage,
                 next_hearing_date = excluded.next_hearing_date,
                 case_json         = excluded.case_json,
                 source            = excluded.source,
                 updated_at        = excluded.updated_at""",
            (cid, user_id, cnr, case.get("case_title"), case.get("court_name"),
             case.get("case_number"), case.get("case_year"), case.get("stage"),
             case.get("next_hearing_date"), payload, case.get("source"), now, now),
        )
        c.commit()
        row = c.execute(
            f"SELECT {_COLS} FROM cases WHERE user_id IS ? AND cnr = ?",
            (user_id, cnr),
        ).fetchone()
    return _row(row)


def _sq_get_case(case_id, user_id) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            f"SELECT {_COLS} FROM cases WHERE id = ? AND user_id IS ?",
            (case_id, user_id),
        ).fetchone()
    return _row(row)


def _sq_list_cases(user_id, limit: int) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM cases WHERE user_id IS ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [_row(r) for r in rows]


def _sq_find_by_number(user_id, case_number, case_year, court_name) -> Optional[dict]:
    cn = (case_number or "").replace(" ", "").strip()
    if not cn:
        return None
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM cases WHERE user_id IS ? "
            "AND REPLACE(COALESCE(case_number,''), ' ', '') = ? "
            "ORDER BY updated_at DESC",
            (user_id, cn),
        ).fetchall()
    cands = [_row(r) for r in rows]
    yr = (case_year or "").strip()[-2:]
    if yr:
        cands = [r for r in cands
                 if not (r.get("case_year") or "") or (r.get("case_year") or "")[-2:] == yr]
    if not cands:
        return None
    if court_name:
        court = court_name.strip().lower()
        exact = [r for r in cands if (r.get("court_name") or "").strip().lower() == court]
        if exact:
            return exact[0]
    return cands[0]


def _sq_update_matter_basics(case_id, user_id, court_name, case_title) -> Optional[dict]:
    row = _sq_get_case(case_id, user_id)
    if row is None:
        return None
    court_name = (court_name or "").strip() or None
    case_title = (case_title or "").strip() or None
    if not (court_name or case_title):
        return row
    cj = row["case_json"] or {}
    if court_name:
        cj["court_name"] = court_name
    if case_title:
        cj["case_title"] = case_title
    with _conn() as c:
        c.execute(
            "UPDATE cases SET court_name = COALESCE(?, court_name), "
            "case_title = COALESCE(?, case_title), case_json = ?, updated_at = ? "
            "WHERE id = ? AND user_id IS ?",
            (court_name, case_title, json.dumps(cj, ensure_ascii=False), _now(),
             case_id, user_id),
        )
        c.commit()
    return _sq_get_case(case_id, user_id)


def _sq_replace_identity(case_id, user_id, case: dict) -> Optional[dict]:
    row = _sq_get_case(case_id, user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    merged = dict(case)
    if cj.get("client"):
        merged["client"] = {**(case.get("client") or {}), **cj["client"]}
    try:
        with _conn() as c:
            c.execute(
                "UPDATE cases SET cnr=?, case_title=?, court_name=?, case_number=?, "
                "case_year=?, stage=?, next_hearing_date=?, case_json=?, source=?, "
                "updated_at=? WHERE id=? AND user_id IS ?",
                (merged.get("cnr"), merged.get("case_title"), merged.get("court_name"),
                 merged.get("case_number"), merged.get("case_year"), merged.get("stage"),
                 merged.get("next_hearing_date"), json.dumps(merged, ensure_ascii=False),
                 merged.get("source"), _now(), case_id, user_id),
            )
            c.commit()
    except sqlite3.IntegrityError:
        return row
    return _sq_get_case(case_id, user_id)


def _sq_delete_all(user_id) -> int:
    with _conn() as c:
        cur = c.execute("DELETE FROM cases WHERE user_id IS ?", (user_id,))
        c.execute("DELETE FROM hearing_logs WHERE user_id IS ?", (user_id,))
        c.commit()
    return cur.rowcount


def _sq_delete_case(case_id, user_id) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM cases WHERE id = ? AND user_id IS ?", (case_id, user_id),
        )
        c.commit()
    return cur.rowcount > 0


def _sq_update_client(case_id, user_id, client: dict) -> Optional[dict]:
    row = _sq_get_case(case_id, user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    cj["client"] = {**(cj.get("client") or {}), **(client or {})}
    with _conn() as c:
        c.execute(
            "UPDATE cases SET case_json = ?, updated_at = ? WHERE id = ? AND user_id IS ?",
            (json.dumps(cj, ensure_ascii=False), _now(), case_id, user_id),
        )
        c.commit()
    return _sq_get_case(case_id, user_id)


def _sq_set_next_date(case_id, user_id, next_hearing_date, stage) -> Optional[dict]:
    row = _sq_get_case(case_id, user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    if next_hearing_date is not None:
        cj["next_hearing_date"] = next_hearing_date
    if stage is not None:
        cj["stage"] = stage
    with _conn() as c:
        c.execute(
            "UPDATE cases SET next_hearing_date = COALESCE(?, next_hearing_date), "
            "stage = COALESCE(?, stage), case_json = ?, updated_at = ? "
            "WHERE id = ? AND user_id IS ?",
            (next_hearing_date, stage, json.dumps(cj, ensure_ascii=False), _now(),
             case_id, user_id),
        )
        c.commit()
    return _sq_get_case(case_id, user_id)


def _sq_log_hearing(case_id, user_id, hearing_date, what_happened,
                    next_hearing_date, stage) -> Optional[dict]:
    row = _sq_get_case(case_id, user_id)
    if row is None:
        return None
    with _conn() as c:
        c.execute(
            "INSERT INTO hearing_logs (id, user_id, case_id, hearing_date, "
            "what_happened, next_hearing_date, stage, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (uuid.uuid4().hex, user_id, case_id, hearing_date, what_happened,
             next_hearing_date, stage, _now()),
        )
        c.commit()
    return _sq_set_next_date(case_id, user_id, next_hearing_date, stage)


def _sq_list_hearing_logs(case_id, user_id) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT id, hearing_date, what_happened, next_hearing_date, stage, created_at "
            "FROM hearing_logs WHERE case_id = ? AND user_id IS ? "
            "ORDER BY created_at DESC",
            (case_id, user_id),
        ).fetchall()
    return [
        {"id": r[0], "hearing_date": r[1], "what_happened": r[2],
         "next_hearing_date": r[3], "stage": r[4], "created_at": r[5]}
        for r in rows
    ]


# ============================================================ public dispatchers
def init_cases_db() -> None:
    """Ensure the local SQLite tables exist (no-op when Supabase is the backend —
    those tables come from migrations/009_matters.sql)."""
    if _use_sb():
        return
    with _conn() as _:
        pass


def add_case(*, user_id: Optional[str], case: dict) -> Optional[dict]:
    """Upsert a normalised case on (user_id, cnr). Returns the stored row."""
    return _sb_add_case(user_id, case) if _use_sb() else _sq_add_case(user_id, case)


def get_case(case_id: str, *, user_id: Optional[str]) -> Optional[dict]:
    return _sb_get_case(case_id, user_id) if _use_sb() else _sq_get_case(case_id, user_id)


def list_cases(*, user_id: Optional[str], limit: int = 100) -> list[dict]:
    return _sb_list_cases(user_id, limit) if _use_sb() else _sq_list_cases(user_id, limit)


def find_case_by_number(*, user_id: Optional[str], case_number: Optional[str],
                        case_year: Optional[str] = None,
                        court_name: Optional[str] = None) -> Optional[dict]:
    """Best-effort lookup of an existing matter by case number (+ optional year and
    court) — dedups diary re-imports so a re-photographed page appends history
    instead of duplicating. Year (last 2 digits) must agree when both carry one;
    an exact court match is preferred, else the most recently touched candidate."""
    if _use_sb():
        return _sb_find_by_number(user_id, case_number, case_year, court_name)
    return _sq_find_by_number(user_id, case_number, case_year, court_name)


def update_matter_basics(case_id: str, *, user_id: Optional[str],
                         court_name: Optional[str] = None,
                         case_title: Optional[str] = None) -> Optional[dict]:
    """Patch a matter's court / cause-title from a fresh diary re-read (only when a
    non-empty value is supplied), so a corrected OCR fixes the board."""
    if _use_sb():
        return _sb_update_matter_basics(case_id, user_id, court_name, case_title)
    return _sq_update_matter_basics(case_id, user_id, court_name, case_title)


def replace_case_identity(case_id: str, *, user_id: Optional[str], case: dict) -> Optional[dict]:
    """Overwrite a matter's identity + fields from a fresh eCourts case while keeping
    the SAME row id, its hearing logs, and any lawyer-entered client. Used when a
    diary 'DY…' matter is resolved to a real CNR. Degrades gracefully on CNR clash."""
    if _use_sb():
        return _sb_replace_identity(case_id, user_id, case)
    return _sq_replace_identity(case_id, user_id, case)


def delete_all_cases(*, user_id: Optional[str]) -> int:
    """Wipe every matter + hearing log for a user (the 'reset demo data' action)."""
    return _sb_delete_all(user_id) if _use_sb() else _sq_delete_all(user_id)


def delete_case(case_id: str, *, user_id: Optional[str]) -> bool:
    return _sb_delete_case(case_id, user_id) if _use_sb() else _sq_delete_case(case_id, user_id)


def update_client(case_id: str, *, user_id: Optional[str], client: dict) -> Optional[dict]:
    """Merge lawyer-entered client details into the matter's case_json.client."""
    if _use_sb():
        return _sb_update_client(case_id, user_id, client)
    return _sq_update_client(case_id, user_id, client)


def set_next_date(case_id: str, *, user_id: Optional[str],
                  next_hearing_date: Optional[str],
                  stage: Optional[str] = None) -> Optional[dict]:
    """Roll a matter's next hearing date / stage forward (mirrored into case_json).
    None values leave the existing value untouched."""
    if _use_sb():
        return _sb_set_next_date(case_id, user_id, next_hearing_date, stage)
    return _sq_set_next_date(case_id, user_id, next_hearing_date, stage)


def log_hearing(case_id: str, *, user_id: Optional[str],
                hearing_date: Optional[str], what_happened: Optional[str],
                next_hearing_date: Optional[str] = None,
                stage: Optional[str] = None) -> Optional[dict]:
    """Record a hearing outcome AND roll the matter's next date/stage, in one place."""
    if _use_sb():
        return _sb_log_hearing(case_id, user_id, hearing_date, what_happened,
                               next_hearing_date, stage)
    return _sq_log_hearing(case_id, user_id, hearing_date, what_happened,
                           next_hearing_date, stage)


def list_hearing_logs(case_id: str, *, user_id: Optional[str]) -> list[dict]:
    if _use_sb():
        return _sb_list_hearing_logs(case_id, user_id)
    return _sq_list_hearing_logs(case_id, user_id)
