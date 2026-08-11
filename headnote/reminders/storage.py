"""The reminder send log — the double-send guard, and the proof it went out.

TWO BACKENDS behind one set of signatures, copying headnote/cases/storage.py
rather than headnote/pgstore.py, and that choice is deliberate: pgstore is gated
behind config.PG_CHILD_TABLES, which is OFF in production and must stay off until
its backfill has run. A reminder log routed through pgstore would therefore sit
on the single Fly volume today. This is a consent record about a third party, so
it follows `cases` onto Postgres wherever Supabase is configured.

  • Supabase Postgres (public.client_reminders) — migrations/014_client_reminders.sql
  • Local SQLite (KANOON_CACHE_PATH) — so dev works with no setup

Everything is scoped by user_id.
"""

from __future__ import annotations

import logging
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator, Optional

from headnote.config import KANOON_CACHE_PATH
from headnote.entitlements import _supabase

log = logging.getLogger(__name__)

_TABLE = "client_reminders"

SENT, FAILED = "sent", "failed"

# Channels. See migrations/014 for what each one means and why 'self' is recorded.
CH_TEMPLATE, CH_TEXT, CH_SELF = "whatsapp_template", "whatsapp_text", "self"


# Set once, the first time Postgres tells us public.client_reminders is not there.
# From that moment every read AND write in this process uses SQLite, because a
# store split down the middle is worse than a store in the wrong place: reads that
# went to Postgres while writes went to SQLite would show the lawyer an empty
# history and let him message the same client a second time.
_pg_absent = False
_pg_probed = False


def _use_sb() -> bool:
    """Postgres when Supabase is configured AND migration 014 has been applied.

    The migration is a separate manual step (paste 014 into the Supabase SQL
    editor), so between deploying this code and running it the table does not
    exist. Falling back rather than failing means reminders work from the day the
    code ships; they just live on the local volume until 014 runs.

    The probe is not optional. `_supabase.select()` logs HTTP errors and returns
    [], so a table that is missing is indistinguishable from one that is empty —
    and without asking directly, reads would answer "no reminders sent" out of
    Postgres while writes were landing in SQLite. That combination shows the
    lawyer an empty history and lets him message the same client twice, which is
    the one failure this module exists to prevent.
    """
    global _pg_probed
    if not _supabase._enabled():
        return False
    if not _pg_probed:
        _pg_probed = True
        try:
            _supabase._send("GET", _TABLE, params={"select": "id", "limit": "1"},
                            timeout=5.0)
        except Exception as e:  # noqa: BLE001 — unreachable or absent → local store
            _mark_pg_absent(e)
    return not _pg_absent


def _mark_pg_absent(err: Exception) -> None:
    global _pg_absent
    if not _pg_absent:
        _pg_absent = True
        log.warning(
            "public.client_reminders is not there (%s) — logging reminders to the "
            "local store for now. Run migrations/014_client_reminders.sql to make "
            "the send log durable and cross-device.", str(err)[:160])


def _missing_table(e: Exception) -> bool:
    s = str(e).lower()
    return ("pgrst205" in s or "42p01" in s or "does not exist" in s
            or "could not find the table" in s)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================ SQLite backend

def _init(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS client_reminders (
            id TEXT PRIMARY KEY,
            user_id TEXT,
            case_id TEXT NOT NULL,
            hearing_date TEXT NOT NULL,
            client_name TEXT,
            to_phone TEXT NOT NULL,
            consent_at_send INTEGER NOT NULL DEFAULT 0,
            channel TEXT NOT NULL,
            lang TEXT,
            body TEXT,
            status TEXT NOT NULL DEFAULT 'sent',
            provider TEXT,
            provider_msg_id TEXT,
            error TEXT,
            created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_cr_user_date
            ON client_reminders(user_id, hearing_date DESC);
        CREATE INDEX IF NOT EXISTS idx_cr_case
            ON client_reminders(user_id, case_id, created_at DESC);
        """
    )
    # The double-send guard, mirroring the partial unique index in migration 014.
    # SQLite supports partial indexes from 3.8.0, so the constraint is enforced in
    # both stores rather than only in production — otherwise a dev run would
    # cheerfully send twice and the guard would look like it worked.
    conn.execute(
        """CREATE UNIQUE INDEX IF NOT EXISTS idx_cr_once
             ON client_reminders(user_id, case_id, hearing_date)
             WHERE status = 'sent'"""
    )
    conn.commit()


@contextmanager
def _conn() -> Iterator[sqlite3.Connection]:
    c = sqlite3.connect(KANOON_CACHE_PATH, timeout=10)
    c.row_factory = sqlite3.Row
    try:
        _init(c)
        yield c
    finally:
        c.close()


def _norm(r) -> dict:
    d = dict(r)
    d["consent_at_send"] = bool(d.get("consent_at_send"))
    return d


# ============================================================ writes


def record(*, user_id: Optional[str], case_id: str, hearing_date: str,
           to_phone: str, channel: str, status: str = SENT,
           client_name: Optional[str] = None, consent_at_send: bool = False,
           lang: Optional[str] = None, body: Optional[str] = None,
           provider: Optional[str] = None, provider_msg_id: Optional[str] = None,
           error: Optional[str] = None) -> Optional[dict]:
    """Write one send (or one failure) to the log.

    Returns the stored row, or None if the unique guard refused it because a
    successful reminder for this client-matter-hearing already exists. The caller
    treats None as "already reminded" — that is not an error, it is the guard
    doing its job, and it is why the check is a database constraint rather than a
    read-then-write in the service layer, which two clicks in quick succession
    would race straight through.
    """
    row = {
        "user_id": user_id,
        "case_id": case_id,
        "hearing_date": hearing_date,
        "client_name": client_name,
        "to_phone": to_phone,
        "consent_at_send": bool(consent_at_send),
        "channel": channel,
        "lang": lang,
        "body": body,
        "status": status,
        "provider": provider,
        "provider_msg_id": provider_msg_id,
        "error": error,
        "created_at": _now(),
    }
    if _use_sb():
        try:
            # insert_or_raise, NOT upsert_or_raise: an upsert merges duplicates,
            # which would turn the guard's rejection into an overwrite of the
            # original record and let the second message go out.
            res = _supabase.insert_or_raise(_TABLE, row)
            return res[0] if res else None
        except Exception as e:  # noqa: BLE001
            # A unique violation here means "already reminded" and is expected.
            if _is_duplicate(e):
                return None
            # The migration has not been run yet — switch this process to SQLite
            # and fall through, rather than failing a send that already went out.
            if _missing_table(e):
                _mark_pg_absent(e)
            else:
                # A real write failure. It must NOT be reported as a successful
                # send: the whole point of the log is that the lawyer can trust
                # "reminded" to mean reminded.
                log.warning("reminder log write failed for case %s: %s", case_id, e)
                raise
    row["id"] = uuid.uuid4().hex
    try:
        with _conn() as c:
            c.execute(
                """INSERT INTO client_reminders
                     (id, user_id, case_id, hearing_date, client_name, to_phone,
                      consent_at_send, channel, lang, body, status, provider,
                      provider_msg_id, error, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (row["id"], user_id, case_id, hearing_date, client_name, to_phone,
                 1 if consent_at_send else 0, channel, lang, body, status, provider,
                 provider_msg_id, error, row["created_at"]),
            )
            c.commit()
        return row
    except sqlite3.IntegrityError:
        return None


def _is_duplicate(e: Exception) -> bool:
    """PostgREST/Postgres signal for a unique-index violation."""
    s = str(e).lower()
    return "23505" in s or "duplicate key" in s or "already exists" in s


def set_provider_msg_id(row: dict, provider_msg_id: str) -> None:
    """Attach the provider's message id to a row already written.

    Bookkeeping only — the message has gone by the time this runs, so a failure
    here is logged and swallowed by the caller rather than turned into a failed
    send the lawyer would retry.
    """
    rid = (row or {}).get("id")
    if not (rid and provider_msg_id):
        return
    if _use_sb():
        _supabase.update(_TABLE, {"provider_msg_id": provider_msg_id},
                         params={"id": f"eq.{rid}"})
        return
    with _conn() as c:
        c.execute("UPDATE client_reminders SET provider_msg_id = ? WHERE id = ?",
                  (provider_msg_id, rid))
        c.commit()


def mark_failed(row: dict, *, user_id: Optional[str], error: str) -> None:
    """Flip a claimed row from 'sent' to 'failed'.

    THIS IS THE MOST IMPORTANT WRITE IN THE MODULE. A send claims its slot in the
    log BEFORE calling the provider, so that two simultaneous clicks cannot both
    message the same client. If the provider then refuses, the claim must be
    released — otherwise the guard keeps that client locked out and the lawyer is
    shown "reminded" for someone who was never told, which is the one lie this
    feature must not tell. The partial unique index is scoped to status='sent'
    precisely so that flipping the status here frees the slot for a retry.
    """
    rid = (row or {}).get("id")
    if not rid:
        return
    if _use_sb():
        _supabase.update_or_raise(
            _TABLE, {"status": FAILED, "error": (error or "")[:2000]},
            params={"id": f"eq.{rid}"})
        return
    with _conn() as c:
        c.execute("UPDATE client_reminders SET status = ?, error = ? WHERE id = ?",
                  (FAILED, (error or "")[:2000], rid))
        c.commit()


# ============================================================ reads


def sent_dates_for(*, user_id: Optional[str], case_ids: list[str],
                   hearing_date: str) -> set[str]:
    """Which of these matters have ALREADY had a successful reminder for this date.

    One query for the whole board, not one per matter: the panel opens over a full
    day's docket and an N-query check is how a Home screen gets slow.
    """
    if not case_ids:
        return set()
    if _use_sb():
        rows = _supabase.select(_TABLE, params={
            "select": "case_id",
            "user_id": f"eq.{user_id}",
            "hearing_date": f"eq.{hearing_date}",
            "status": f"eq.{SENT}",
            "case_id": f"in.({','.join(case_ids)})",
            "limit": "1000",
        }) or []
        return {str(r.get("case_id")) for r in rows if r.get("case_id")}
    marks = ",".join("?" for _ in case_ids)
    with _conn() as c:
        rows = c.execute(
            f"""SELECT case_id FROM client_reminders
                 WHERE user_id IS ? AND hearing_date = ? AND status = ?
                   AND case_id IN ({marks})""",
            (user_id, hearing_date, SENT, *case_ids),
        ).fetchall()
    return {r["case_id"] for r in rows}


def history_for_matter(*, user_id: Optional[str], case_id: str,
                       limit: int = 50) -> list[dict]:
    """Every reminder ever sent on this matter, newest first — what the case folder
    shows so the lawyer can see the client was told, and when."""
    if _use_sb():
        rows = _supabase.select(_TABLE, params={
            "select": "*", "user_id": f"eq.{user_id}", "case_id": f"eq.{case_id}",
            "order": "created_at.desc", "limit": str(limit)}) or []
        return [_norm(r) for r in rows]
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM client_reminders
                 WHERE user_id IS ? AND case_id = ?
                 ORDER BY created_at DESC LIMIT ?""",
            (user_id, case_id, limit),
        ).fetchall()
    return [_norm(r) for r in rows]


def recent(*, user_id: Optional[str], limit: int = 100) -> list[dict]:
    if _use_sb():
        rows = _supabase.select(_TABLE, params={
            "select": "*", "user_id": f"eq.{user_id}",
            "order": "created_at.desc", "limit": str(limit)}) or []
        return [_norm(r) for r in rows]
    with _conn() as c:
        rows = c.execute(
            """SELECT * FROM client_reminders WHERE user_id IS ?
                 ORDER BY created_at DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    return [_norm(r) for r in rows]
