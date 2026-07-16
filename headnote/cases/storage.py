"""Persistence for CNR case folders.

Mirrors headnote/drafter/storage.py exactly: a SQLite ``cases`` table in the
same file as drafts + the IK cache (KANOON_CACHE_PATH), so one Railway Volume
covers everything and there's ZERO external setup to test locally.

(The per-user `saved_caselaw` shelf uses Supabase, but that needs remote creds
the local dev box doesn't have. Cases live next to drafts in SQLite so the
"add case → draft for this case" flow works end-to-end with no config. A
Supabase mirror can come later for prod multi-device sync — same row shape.)

user_id is the Supabase user.id (or the local-dev synthetic id). A case is
unique per (user_id, cnr): re-adding the same CNR refreshes it in place.
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH


_COLS = ("id, user_id, cnr, case_title, court_name, case_number, case_year, "
         "stage, next_hearing_date, case_json, source, created_at, updated_at")


def _init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS cases (
            id                TEXT PRIMARY KEY,
            user_id           TEXT,                 -- Supabase user.id or NULL
            cnr               TEXT NOT NULL,        -- 16-char eCourts CNR
            case_title        TEXT,
            court_name        TEXT,
            case_number       TEXT,
            case_year         TEXT,
            stage             TEXT,
            next_hearing_date TEXT,
            case_json         TEXT NOT NULL,        -- full normalised case dict
            source            TEXT,                 -- 'mock' | 'ecourtsindia' | ...
            created_at        TEXT NOT NULL,
            updated_at        TEXT NOT NULL
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_cases_user_cnr ON cases(user_id, cnr);
        CREATE INDEX IF NOT EXISTS idx_cases_user    ON cases(user_id);
        CREATE INDEX IF NOT EXISTS idx_cases_updated ON cases(updated_at DESC);
        CREATE INDEX IF NOT EXISTS idx_cases_user_next ON cases(user_id, next_hearing_date);

        -- Per-hearing outcome log (the diary's "what happened today"). Kept as
        -- its own rows (auditable history) rather than buried in case_json.
        CREATE TABLE IF NOT EXISTS hearing_logs (
            id                TEXT PRIMARY KEY,
            user_id           TEXT,
            case_id           TEXT NOT NULL,
            hearing_date      TEXT,          -- the date this outcome is for
            what_happened     TEXT,          -- free text ("witness examined")
            next_hearing_date TEXT,          -- new next date set by the log
            stage             TEXT,          -- optional updated stage
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


def init_cases_db() -> None:
    """Call once at app boot to ensure the cases table exists."""
    with _conn() as _:
        pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def add_case(*, user_id: Optional[str], case: dict) -> Optional[dict]:
    """Upsert a normalised case on (user_id, cnr). Returns the stored row."""
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


def get_case(case_id: str, *, user_id: Optional[str]) -> Optional[dict]:
    with _conn() as c:
        row = c.execute(
            f"SELECT {_COLS} FROM cases WHERE id = ? AND user_id IS ?",
            (case_id, user_id),
        ).fetchone()
    return _row(row)


def list_cases(*, user_id: Optional[str], limit: int = 100) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            f"SELECT {_COLS} FROM cases WHERE user_id IS ? "
            "ORDER BY updated_at DESC LIMIT ?",
            (user_id, limit),
        ).fetchall()
    return [_row(r) for r in rows]


def find_case_by_number(*, user_id: Optional[str], case_number: Optional[str],
                        case_year: Optional[str] = None,
                        court_name: Optional[str] = None) -> Optional[dict]:
    """Best-effort lookup of an existing matter by case number (+ optional year
    and court).

    Used to dedup diary re-imports: re-photographing a page that already has a
    matter should append to its history, not create a duplicate. Case-number
    match ignores whitespace; a year (last two digits) must agree when both
    sides carry one; when a court is given and one candidate's court matches
    exactly we prefer it, else the most recently touched candidate."""
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


def replace_case_identity(case_id: str, *, user_id: Optional[str], case: dict) -> Optional[dict]:
    """Overwrite a matter's identity + fields from a fresh eCourts case dict while
    keeping the SAME row id, its hearing logs, and any lawyer-entered client.

    Used when a diary-sourced matter (pseudo 'DY…' CNR) is resolved to a real
    eCourts CNR — the matter becomes API-refreshable without losing its folder.
    If the resolved CNR already belongs to another of this user's rows the unique
    index would trip, so we degrade gracefully and leave the matter untouched."""
    row = get_case(case_id, user_id=user_id)
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
    return get_case(case_id, user_id=user_id)


def delete_all_cases(*, user_id: Optional[str]) -> int:
    """Wipe every matter + hearing log for a user. Used by the testing-mode reset
    so the onboarding flow restarts clean on each refresh."""
    with _conn() as c:
        cur = c.execute("DELETE FROM cases WHERE user_id IS ?", (user_id,))
        c.execute("DELETE FROM hearing_logs WHERE user_id IS ?", (user_id,))
        c.commit()
    return cur.rowcount


def delete_case(case_id: str, *, user_id: Optional[str]) -> bool:
    with _conn() as c:
        cur = c.execute(
            "DELETE FROM cases WHERE id = ? AND user_id IS ?",
            (case_id, user_id),
        )
        c.commit()
    return cur.rowcount > 0


def update_client(case_id: str, *, user_id: Optional[str], client: dict) -> Optional[dict]:
    """Merge lawyer-entered client details (name/mobile/email/father/age/…) into
    the matter's case_json under `client`. eCourts never supplies these — they're
    entered once per matter and reused for autofill + reminders."""
    row = get_case(case_id, user_id=user_id)
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
    return get_case(case_id, user_id=user_id)


def set_next_date(case_id: str, *, user_id: Optional[str],
                  next_hearing_date: Optional[str],
                  stage: Optional[str] = None) -> Optional[dict]:
    """Roll a matter's next hearing date forward (used by the rolling refresh and
    by hearing-outcome logging). Also mirrors into case_json so drafts/prefill
    see the fresh values."""
    row = get_case(case_id, user_id=user_id)
    if row is None:
        return None
    cj = row["case_json"] or {}
    if next_hearing_date is not None:
        cj["next_hearing_date"] = next_hearing_date
    if stage is not None:
        cj["stage"] = stage
    now = _now()
    with _conn() as c:
        c.execute(
            "UPDATE cases SET next_hearing_date = COALESCE(?, next_hearing_date), "
            "stage = COALESCE(?, stage), case_json = ?, updated_at = ? "
            "WHERE id = ? AND user_id IS ?",
            (next_hearing_date, stage, json.dumps(cj, ensure_ascii=False), now,
             case_id, user_id),
        )
        c.commit()
    return get_case(case_id, user_id=user_id)


def log_hearing(case_id: str, *, user_id: Optional[str],
                hearing_date: Optional[str], what_happened: Optional[str],
                next_hearing_date: Optional[str] = None,
                stage: Optional[str] = None) -> Optional[dict]:
    """Record a hearing outcome AND roll the matter's next date/stage forward,
    in one place. Returns the updated case row."""
    row = get_case(case_id, user_id=user_id)
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
    return set_next_date(case_id, user_id=user_id,
                         next_hearing_date=next_hearing_date, stage=stage)


def list_hearing_logs(case_id: str, *, user_id: Optional[str]) -> list[dict]:
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
