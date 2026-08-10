"""Persistence for note sheets + per-hearing preparation state.

Same two-backend contract as headnote/cases/storage.py:
  • Supabase Postgres (public.note_sheets) when SUPABASE_URL is configured —
    durable and cross-device, so a sheet prepared on the laptop is on the phone.
  • Local SQLite (KANOON_CACHE_PATH) otherwise, so local dev works with no setup.

Everything is scoped by user_id. One sheet per (user, case, hearing_date).

The prep block (purpose / prepared / assignee / board item / override) rides
inside the case's own case_json under "prep", so it is saved by the existing
cases storage and needs no schema change.
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
from headnote.cases import storage as cases_storage

_TABLE = "note_sheets"

# fields the lawyer (or the junior) can set on a prep block
_PREP_FIELDS = ("purpose", "purpose_manual", "prepared", "assignee",
                "item", "time", "override")


def _use_sb() -> bool:
    return _supabase._enabled()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ prep (on the case)

def get_prep(case: dict) -> dict:
    """Read the prep block off a case row. Always a dict."""
    cj = case.get("case_json") or {}
    if isinstance(cj, str):
        try:
            cj = json.loads(cj)
        except Exception:  # noqa: BLE001
            cj = {}
    prep = cj.get("prep") or {}
    return prep if isinstance(prep, dict) else {}


def set_prep(case_id: str, user_id: str, patch: dict) -> Optional[dict]:
    """Merge `patch` into the case's prep block and persist it.

    Only the known prep fields are accepted, so a stray key can never be written
    into the matter. Returns the updated case row, or None if it isn't the
    user's matter.
    """
    prep = {k: v for k, v in (patch or {}).items() if k in _PREP_FIELDS}
    if not prep:
        return cases_storage.get_case(case_id, user_id=user_id)
    return cases_storage.merge_prep(case_id, user_id=user_id, prep=prep)


# ============================================================ Supabase backend

def _sb_row(r: Optional[dict]) -> Optional[dict]:
    if not r:
        return None
    out = dict(r)
    sj = out.get("sheet_json")
    if isinstance(sj, str):
        try:
            out["sheet_json"] = json.loads(sj)
        except Exception:  # noqa: BLE001
            out["sheet_json"] = {}
    out["sheet_json"] = out.get("sheet_json") or {}
    return out


def _sb_get(case_id: str, user_id: str, hearing_date: str) -> Optional[dict]:
    rows = _supabase.select(_TABLE, params={
        "user_id": f"eq.{user_id}", "case_id": f"eq.{case_id}",
        "hearing_date": f"eq.{hearing_date}", "limit": "1"})
    return _sb_row(rows[0]) if rows else None


def _sb_save(case_id: str, user_id: str, hearing_date: str, sheet: dict,
             source: str, engine: Optional[str]) -> Optional[dict]:
    payload = {"user_id": user_id, "case_id": case_id, "hearing_date": hearing_date,
               "source": source, "sheet_json": sheet, "ocr_engine": engine,
               "updated_at": _now()}
    rows = _supabase.upsert(_TABLE, payload, on_conflict="user_id,case_id,hearing_date")
    return _sb_row(rows[0]) if rows else None


def _sb_list_for_date(user_id: str, hearing_date: str) -> list[dict]:
    rows = _supabase.select(_TABLE, params={
        "user_id": f"eq.{user_id}", "hearing_date": f"eq.{hearing_date}"})
    return [_sb_row(r) for r in rows]


def _sb_delete(case_id: str, user_id: str, hearing_date: str) -> bool:
    _supabase.delete(_TABLE, params={
        "user_id": f"eq.{user_id}", "case_id": f"eq.{case_id}",
        "hearing_date": f"eq.{hearing_date}"})
    return True


# ============================================================ SQLite backend

def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS note_sheets (
            id            TEXT PRIMARY KEY,
            user_id       TEXT,
            case_id       TEXT NOT NULL,
            hearing_date  TEXT NOT NULL,
            source        TEXT NOT NULL DEFAULT 'junior',
            sheet_json    TEXT NOT NULL,
            ocr_engine    TEXT,
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_ns_unique
            ON note_sheets(user_id, case_id, hearing_date);
        CREATE INDEX IF NOT EXISTS idx_ns_user_date
            ON note_sheets(user_id, hearing_date);
    """)
    conn.commit()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(KANOON_CACHE_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        _init_schema(c)
        yield c
    finally:
        c.close()


def _sq_row(r: Optional[sqlite3.Row]) -> Optional[dict]:
    if not r:
        return None
    out = dict(r)
    try:
        out["sheet_json"] = json.loads(out.get("sheet_json") or "{}")
    except Exception:  # noqa: BLE001
        out["sheet_json"] = {}
    return out


def _sq_get(case_id: str, user_id: str, hearing_date: str) -> Optional[dict]:
    with _conn() as c:
        r = c.execute(
            "SELECT * FROM note_sheets WHERE user_id=? AND case_id=? AND hearing_date=?",
            (user_id, case_id, hearing_date)).fetchone()
        return _sq_row(r)


def _sq_save(case_id: str, user_id: str, hearing_date: str, sheet: dict,
             source: str, engine: Optional[str]) -> Optional[dict]:
    now = _now()
    with _conn() as c:
        existing = c.execute(
            "SELECT id, created_at FROM note_sheets WHERE user_id=? AND case_id=? AND hearing_date=?",
            (user_id, case_id, hearing_date)).fetchone()
        if existing:
            c.execute("""UPDATE note_sheets
                            SET sheet_json=?, source=?, ocr_engine=?, updated_at=?
                          WHERE id=?""",
                      (json.dumps(sheet, ensure_ascii=False), source, engine, now, existing["id"]))
        else:
            c.execute("""INSERT INTO note_sheets
                         (id, user_id, case_id, hearing_date, source, sheet_json,
                          ocr_engine, created_at, updated_at)
                         VALUES (?,?,?,?,?,?,?,?,?)""",
                      (uuid.uuid4().hex, user_id, case_id, hearing_date, source,
                       json.dumps(sheet, ensure_ascii=False), engine, now, now))
        c.commit()
    return _sq_get(case_id, user_id, hearing_date)


def _sq_list_for_date(user_id: str, hearing_date: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            "SELECT * FROM note_sheets WHERE user_id=? AND hearing_date=?",
            (user_id, hearing_date)).fetchall()
        return [_sq_row(r) for r in rows]


def _sq_delete(case_id: str, user_id: str, hearing_date: str) -> bool:
    with _conn() as c:
        c.execute("DELETE FROM note_sheets WHERE user_id=? AND case_id=? AND hearing_date=?",
                  (user_id, case_id, hearing_date))
        c.commit()
    return True


# ============================================================ public API

def get_sheet(case_id: str, user_id: str, hearing_date: str) -> Optional[dict]:
    if _use_sb():
        return _sb_get(case_id, user_id, hearing_date)
    return _sq_get(case_id, user_id, hearing_date)


def save_sheet(case_id: str, user_id: str, hearing_date: str, sheet: dict,
               *, source: str = "junior", engine: Optional[str] = None) -> Optional[dict]:
    if _use_sb():
        return _sb_save(case_id, user_id, hearing_date, sheet, source, engine)
    return _sq_save(case_id, user_id, hearing_date, sheet, source, engine)


def list_for_date(user_id: str, hearing_date: str) -> dict[str, dict]:
    """All sheets for a date, keyed by case_id — one query for the whole board."""
    rows = _sb_list_for_date(user_id, hearing_date) if _use_sb() \
        else _sq_list_for_date(user_id, hearing_date)
    return {str(r["case_id"]): r for r in rows if r}


def latest_for_case(case_id: str, user_id: str) -> Optional[dict]:
    """The most recent sheet for a matter, whatever hearing it was written for.

    Courts adjourn: a sheet prepared for the 12th must not vanish because the
    hearing moved to the 23rd. Callers use this as a fallback and tell the lawyer
    which date it came from.
    """
    if _use_sb():
        rows = _supabase.select(_TABLE, params={
            "user_id": f"eq.{user_id}", "case_id": f"eq.{case_id}",
            "order": "updated_at.desc", "limit": "1"})
        return _sb_row(rows[0]) if rows else None
    with _conn() as c:
        r = c.execute("""SELECT * FROM note_sheets WHERE user_id=? AND case_id=?
                         ORDER BY updated_at DESC LIMIT 1""",
                      (user_id, case_id)).fetchone()
        return _sq_row(r)


def delete_sheet(case_id: str, user_id: str, hearing_date: str) -> bool:
    if _use_sb():
        return _sb_delete(case_id, user_id, hearing_date)
    return _sq_delete(case_id, user_id, hearing_date)
