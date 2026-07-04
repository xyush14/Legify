"""Persistence for recorded consultations.

Mirrors headnote/cases/storage.py exactly: a SQLite ``consultations`` table in
the same file as drafts + cases + the IK cache (KANOON_CACHE_PATH), so one
Railway Volume covers everything and there's ZERO external setup to test
locally.

A consultation is the artifact of one recorded lawyer–client conversation:
the raw transcript plus the structured report (facts / issues / next steps)
generated from it. Audio itself is NEVER persisted — we keep only the text,
matching the "voice data not retained" privacy claim on /api/draft/transcribe.

user_id is the Supabase user.id (or the local-dev synthetic id). Optionally a
consultation links to a matter (case_id) so it sits alongside the CNR folder.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH


_COLS = ("id, user_id, case_id, title, matter_type, parties, court, lang, "
         "duration_sec, consent, transcript, report_json, created_at, updated_at")


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS consultations (
            id            TEXT PRIMARY KEY,
            user_id       TEXT,                 -- Supabase user.id or NULL
            case_id       TEXT,                 -- optional link to a matter
            title         TEXT,                 -- e.g. "Sunita Verma vs Rakesh Verma"
            matter_type   TEXT,                 -- drafter doc_type hint (maintenance…)
            parties       TEXT,                 -- freeform party line
            court         TEXT,
            lang          TEXT,                 -- transcript language (hi/en/…)
            duration_sec  INTEGER,
            consent       INTEGER,              -- 1 = lawyer acknowledged consent
            transcript    TEXT,                 -- raw STT text
            report_json   TEXT NOT NULL,        -- structured report dict
            created_at    TEXT NOT NULL,
            updated_at    TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_consult_user    ON consultations(user_id);
        CREATE INDEX IF NOT EXISTS idx_consult_case    ON consultations(case_id);
        CREATE INDEX IF NOT EXISTS idx_consult_updated ON consultations(updated_at DESC);
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


def init_consultations_db() -> None:
    """Call once at app boot to ensure the consultations table exists."""
    with _conn() as _:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row(r) -> Optional[dict]:
    if not r:
        return None
    return {
        "id": r[0], "user_id": r[1], "case_id": r[2], "title": r[3],
        "matter_type": r[4], "parties": r[5], "court": r[6], "lang": r[7],
        "duration_sec": r[8], "consent": bool(r[9]),
        "transcript": r[10] or "",
        "report": json.loads(r[11] or "{}"),
        "created_at": r[12], "updated_at": r[13],
    }


def add_consultation(
    *,
    user_id: Optional[str],
    title: str,
    report: dict,
    transcript: str = "",
    case_id: Optional[str] = None,
    matter_type: Optional[str] = None,
    parties: Optional[str] = None,
    court: Optional[str] = None,
    lang: str = "hi",
    duration_sec: int = 0,
    consent: bool = False,
) -> dict:
    """Store a freshly-generated consultation report. Returns the stored row."""
    now = _now()
    cid = uuid.uuid4().hex
    with _conn() as c:
        c.execute(
            """INSERT INTO consultations
                 (id, user_id, case_id, title, matter_type, parties, court, lang,
                  duration_sec, consent, transcript, report_json, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (cid, user_id, case_id, title, matter_type, parties, court, lang,
             int(duration_sec or 0), 1 if consent else 0,
             transcript, json.dumps(report, ensure_ascii=False), now, now),
        )
        c.commit()
        row = c.execute(
            f"SELECT {_COLS} FROM consultations WHERE id = ?", (cid,)
        ).fetchone()
    return _row(row)


def get_consultation(consult_id: str, *, user_id: Optional[str]) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            f"SELECT {_COLS} FROM consultations WHERE id = ? AND user_id IS ?",
            (consult_id, user_id),
        ).fetchone()
    return _row(row)


def list_consultations(*, user_id: Optional[str], limit: int = 100) -> list[dict]:
    """Newest first. Drops the heavy transcript from list payloads (kept on GET)."""
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM consultations WHERE user_id IS ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    out = []
    for r in rows:
        row = _row(r)
        if row:
            row.pop("transcript", None)
            out.append(row)
    return out


def delete_consultation(consult_id: str, *, user_id: Optional[str]) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM consultations WHERE id = ? AND user_id IS ?",
            (consult_id, user_id),
        )
        c.commit()
    return cur.rowcount > 0
