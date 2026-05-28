"""DB-backed access grants — the runtime store the admin dashboard writes to.

Hardcoded whitelists in `config.py` (FOUNDER_EMAILS, PARTNER_EMAILS) are the
ROOT TIER — they survive even a full DB reset and are how the original team
keeps access. This module persists ADDITIONAL grants made via the admin UI
(e.g. "give wadhwapublishingco@gmail.com partner access for 1 year") to a
small SQLite table so they survive normal restarts and can be revoked from
the UI without a code commit.

Resolution order (entitlements/subscription.py):
  1. config.FOUNDER_EMAILS  → plan = "founder"
  2. config.PARTNER_EMAILS  → plan = "partner"
  3. grants table           → plan = stored role
  4. subscriptions table    → user's actual plan
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Literal, Optional

from headnote import config


Role = Literal["founder", "partner", "yearly", "monthly"]
_VALID_ROLES = ("founder", "partner", "yearly", "monthly")


def _conn() -> sqlite3.Connection:
    """Lazy connection to the access-grants DB (lives in FEEDBACK_DB so it
    shares the same SQLite file as feedback / drafts — no extra path config)."""
    c = sqlite3.connect(config.FEEDBACK_DB, timeout=10)
    # NOTE: no CHECK constraint on `role` — Python validates the role list,
    # which lets us add new role types (yearly, monthly) without a SQLite
    # ALTER (CHECK constraints can't be modified in place).
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS access_grants (
            email      TEXT PRIMARY KEY,
            role       TEXT NOT NULL,
            notes      TEXT,
            granted_by TEXT,
            granted_at TEXT NOT NULL
        )
        """
    )
    # One-shot schema migration: the original release shipped this table with
    # a CHECK (role IN ('founder','partner')) constraint that blocks the new
    # yearly/monthly roles. Detect it and rebuild the table without CHECK —
    # idempotent: only fires when the old schema is present.
    row = c.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='access_grants'"
    ).fetchone()
    if row and row[0] and "CHECK" in row[0].upper():
        c.executescript(
            """
            CREATE TABLE _access_grants_new (
                email      TEXT PRIMARY KEY,
                role       TEXT NOT NULL,
                notes      TEXT,
                granted_by TEXT,
                granted_at TEXT NOT NULL
            );
            INSERT INTO _access_grants_new (email, role, notes, granted_by, granted_at)
                SELECT email, role, notes, granted_by, granted_at FROM access_grants;
            DROP TABLE access_grants;
            ALTER TABLE _access_grants_new RENAME TO access_grants;
            """
        )
    # Tracks one-shot consumption of time-limited grants (yearly/monthly)
    # AND hardcoded YEARLY_GRANT_EMAILS / MONTHLY_GRANT_EMAILS in config.
    # Founder/partner grants are perpetual and NEVER consumed — they fire on
    # every sign-in via the synthetic-sub path.
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS consumed_grants (
            email          TEXT PRIMARY KEY,
            plan           TEXT NOT NULL,
            user_id        TEXT NOT NULL,
            activated_at   TEXT NOT NULL
        )
        """
    )
    c.commit()
    return c


def get_role(email: Optional[str]) -> Optional[Role]:
    """Return the access role for `email` from the DB grants table, or None.

    Does NOT consult the hardcoded config.FOUNDER_EMAILS / PARTNER_EMAILS —
    that's the caller's responsibility (they're checked first as root tier).
    Match is case-insensitive.
    """
    if not email:
        return None
    e = email.strip().lower()
    if not e:
        return None
    try:
        c = _conn()
        row = c.execute(
            "SELECT role FROM access_grants WHERE email = ?", (e,)
        ).fetchone()
        c.close()
        if row and row[0] in ("founder", "partner"):
            return row[0]  # type: ignore[return-value]
    except Exception:
        pass
    return None


def list_grants() -> list[dict]:
    """All DB-stored grants, newest first. Excludes hardcoded config entries
    (the caller composes those separately for the admin UI)."""
    try:
        c = _conn()
        rows = c.execute(
            "SELECT email, role, notes, granted_by, granted_at "
            "FROM access_grants ORDER BY granted_at DESC"
        ).fetchall()
        c.close()
        return [
            {
                "email": r[0],
                "role": r[1],
                "notes": r[2] or "",
                "granted_by": r[3] or "",
                "granted_at": r[4],
                "source": "db",
            }
            for r in rows
        ]
    except Exception:
        return []


def add_grant(
    email: str, role: Role, *, notes: str = "", granted_by: str = ""
) -> dict:
    """Insert / update a grant. Returns the stored row.

    Refuses to overwrite a hardcoded entry: if the email is in
    config.FOUNDER_EMAILS or PARTNER_EMAILS already, raises ValueError —
    those are root-tier and managed via the code config, not the UI.
    """
    if not email or "@" not in email:
        raise ValueError("email must be a valid address")
    if role not in _VALID_ROLES:
        raise ValueError(f"role must be one of {_VALID_ROLES}")
    e = email.strip().lower()
    hardcoded = (
        config.FOUNDER_EMAILS | config.PARTNER_EMAILS
        | config.YEARLY_GRANT_EMAILS | config.MONTHLY_GRANT_EMAILS
    )
    if e in hardcoded:
        raise ValueError(
            f"{e} is already granted access via the hardcoded config "
            f"(root tier). To change its role, edit headnote/config.py."
        )
    now = datetime.now(timezone.utc).isoformat()
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO access_grants "
        "(email, role, notes, granted_by, granted_at) VALUES (?, ?, ?, ?, ?)",
        (e, role, notes.strip() or None, granted_by.strip() or None, now),
    )
    c.commit()
    c.close()
    return {
        "email": e, "role": role, "notes": notes.strip(),
        "granted_by": granted_by.strip(), "granted_at": now, "source": "db",
    }


def remove_grant(email: str) -> bool:
    """Delete a DB grant. Returns True iff a row was deleted. Hardcoded
    entries are NOT removed (and the caller can't address them this way)."""
    if not email:
        return False
    e = email.strip().lower()
    try:
        c = _conn()
        cur = c.execute("DELETE FROM access_grants WHERE email = ?", (e,))
        c.commit()
        c.close()
        return cur.rowcount > 0
    except Exception:
        return False


def list_hardcoded() -> list[dict]:
    """All hardcoded config entries (founders + partners + yearly/monthly
    grants) — read-only in the UI. Returned in the same shape as list_grants()
    with source='config'."""
    out: list[dict] = []
    for e in sorted(config.FOUNDER_EMAILS):
        out.append({"email": e, "role": "founder", "notes": "",
                    "granted_by": "config", "granted_at": "", "source": "config"})
    for e in sorted(config.PARTNER_EMAILS):
        out.append({"email": e, "role": "partner", "notes": "",
                    "granted_by": "config", "granted_at": "", "source": "config"})
    for e in sorted(config.YEARLY_GRANT_EMAILS):
        out.append({"email": e, "role": "yearly", "notes": "1-year comp grant",
                    "granted_by": "config", "granted_at": "", "source": "config"})
    for e in sorted(config.MONTHLY_GRANT_EMAILS):
        out.append({"email": e, "role": "monthly", "notes": "1-month comp grant",
                    "granted_by": "config", "granted_at": "", "source": "config"})
    return out


# ===================================================================== #
# Consumption tracking for time-limited (yearly/monthly) grants.        #
# Founder/partner grants are perpetual and NEVER consumed.              #
# ===================================================================== #

def is_consumed(email: str) -> bool:
    """True iff this email's time-limited grant has already been activated
    (i.e. a real subscription row was created for them at first sign-in)."""
    if not email:
        return False
    e = email.strip().lower()
    try:
        c = _conn()
        row = c.execute(
            "SELECT 1 FROM consumed_grants WHERE email = ?", (e,)
        ).fetchone()
        c.close()
        return row is not None
    except Exception:
        return False


def mark_consumed(email: str, plan: str, user_id: str) -> None:
    """Record that the grant for `email` has been activated to a real
    subscription. Future sign-ins by the same email won't re-fire."""
    if not email or not plan or not user_id:
        return
    e = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()
    try:
        c = _conn()
        c.execute(
            "INSERT OR REPLACE INTO consumed_grants "
            "(email, plan, user_id, activated_at) VALUES (?, ?, ?, ?)",
            (e, plan, user_id, now),
        )
        c.commit()
        c.close()
    except Exception:
        pass
