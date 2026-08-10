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
import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH
from headnote import pgstore

log = logging.getLogger(__name__)

_PG = "consultations"  # public.consultations — durable backend (migration 012)


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
    if pgstore.ready(_PG):
        row = pgstore.insert(_PG, {
            "id": cid, "user_id": user_id, "case_id": case_id, "title": title,
            "matter_type": matter_type, "parties": parties, "court": court,
            "lang": lang, "duration_sec": int(duration_sec or 0),
            "consent": bool(consent), "transcript": transcript,
            "report_json": report or {},
        }, json_cols=("report_json",))
        if row:
            return _pg_row(row)
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


def _pg_row(d: Optional[dict]) -> Optional[dict]:
    """Normalise a Postgres row to the shape the SQLite path returns."""
    if not d:
        return None
    out = dict(d)
    out["report_json"] = pgstore.parse_json(out.get("report_json"))
    out["report"] = out["report_json"]
    out["consent"] = bool(out.get("consent"))
    return out


def get_consultation(consult_id: str, *, user_id: Optional[str]) -> Optional[dict]:
    if pgstore.ready(_PG):
        return _pg_row(pgstore.get(_PG, consult_id, user_id=user_id))
    with _conn() as c:
        row = c.execute(
            f"SELECT {_COLS} FROM consultations WHERE id = ? AND user_id IS ?",
            (consult_id, user_id),
        ).fetchone()
    return _row(row)


def list_consultations(*, user_id: Optional[str], limit: int = 100,
                       case_id: Optional[str] = None) -> list[dict]:
    """Newest first. Drops the heavy transcript from list payloads (kept on GET).
    Pass case_id to return only recordings filed under that matter."""
    if pgstore.ready(_PG):
        out = []
        for r in pgstore.listing(_PG, user_id=user_id, limit=limit, case_id=case_id,
                                 order="created_at.desc"):
            row = _pg_row(r)
            if row:
                row.pop("transcript", None)
                out.append(row)
        return out
    where = "user_id IS ?"
    params: list = [user_id]
    if case_id is not None:
        where += " AND case_id = ?"
        params.append(case_id)
    params.append(limit)
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM consultations WHERE {where} "
            "ORDER BY updated_at DESC LIMIT ?",
            tuple(params),
        ).fetchall()
    out = []
    for r in rows:
        row = _row(r)
        if row:
            row.pop("transcript", None)
            out.append(row)
    return out


def counts_by_case(user_id: Optional[str], case_ids: list[str]) -> dict[str, int]:
    """How many recordings sit in each of these matters, in ONE grouped query.
    See documents.counts_by_case — same reason, same shape."""
    ids = [str(c) for c in case_ids if c]
    if not ids:
        return {}
    if pgstore.ready(_PG):
        return {cid: len(list_consultations(user_id=user_id, case_id=cid, limit=100))
                for cid in ids}
    try:
        marks = ",".join("?" for _ in ids)
        with _conn() as c:
            rows = c.execute(
                f"SELECT case_id, COUNT(*) FROM consultations "
                f"WHERE user_id IS ? AND case_id IN ({marks}) GROUP BY case_id",
                tuple([user_id] + ids),
            ).fetchall()
        return {str(r[0]): int(r[1]) for r in rows if r[0]}
    except Exception as e:  # noqa: BLE001
        log.warning("bulk recording count failed: %s", e)
        return {}


def update_consultation(
    consult_id: str, *, user_id: Optional[str],
    title: Optional[str] = None, report: Optional[dict] = None,
) -> Optional[dict]:
    """Patch a consultation's lawyer-edited fields and return the updated row.

    The recorder's report is machine-extracted, so the lawyer MUST be able to
    correct a mis-heard fact, fix a party name, tick off an action item, or
    resolve a "confirm before pleading" flag — otherwise the memo is untrustable
    work-product. The client sends back the whole edited `report` dict (already
    the shape the UI renders); we store it and re-derive the denormalised
    title/matter_type/court columns so the list view stays in sync.
    """
    row = get_consultation(consult_id, user_id=user_id)
    if row is None:
        return None
    rep = report if isinstance(report, dict) else row.get("report") or {}
    new_title = (title or rep.get("title") or row.get("title") or "Consultation").strip()
    if pgstore.ready(_PG):
        return _pg_row(pgstore.update(_PG, consult_id, {
            "report_json": rep, "title": new_title,
            "matter_type": rep.get("matter_type"), "court": rep.get("court"),
        }, user_id=user_id, json_cols=("report_json",)))
    with _conn() as c:
        c.execute(
            "UPDATE consultations SET title = ?, matter_type = ?, court = ?, "
            "report_json = ?, updated_at = ? WHERE id = ? AND user_id IS ?",
            (new_title, rep.get("matter_type") or row.get("matter_type"),
             rep.get("court") or row.get("court"),
             json.dumps(rep, ensure_ascii=False), _now(), consult_id, user_id),
        )
        c.commit()
        stored = c.execute(
            f"SELECT {_COLS} FROM consultations WHERE id = ?", (consult_id,)
        ).fetchone()
    return _row(stored)


def set_consultation_case(consult_id: str, *, case_id: Optional[str],
                          user_id: Optional[str]) -> bool:
    """Attach (or detach) a consultation to a case folder."""
    if pgstore.ready(_PG):
        return pgstore.set_field(_PG, consult_id, "case_id", case_id, user_id=user_id)
    with _conn() as c:
        cur = c.execute(
            "UPDATE consultations SET case_id = ? WHERE id = ? AND user_id IS ?",
            (case_id, consult_id, user_id),
        )
        c.commit()
    return cur.rowcount > 0


def delete_consultation(consult_id: str, *, user_id: Optional[str]) -> bool:
    if pgstore.ready(_PG):
        return pgstore.remove(_PG, consult_id, user_id=user_id)
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM consultations WHERE id = ? AND user_id IS ?",
            (consult_id, user_id),
        )
        c.commit()
    return cur.rowcount > 0
