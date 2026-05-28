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


Role = Literal["founder", "partner"]


def _conn() -> sqlite3.Connection:
    """Lazy connection to the access-grants DB (lives in FEEDBACK_DB so it
    shares the same SQLite file as feedback / drafts — no extra path config)."""
    c = sqlite3.connect(config.FEEDBACK_DB, timeout=10)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS access_grants (
            email      TEXT PRIMARY KEY,
            role       TEXT NOT NULL CHECK (role IN ('founder', 'partner')),
            notes      TEXT,
            granted_by TEXT,
            granted_at TEXT NOT NULL
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
    if role not in ("founder", "partner"):
        raise ValueError("role must be 'founder' or 'partner'")
    e = email.strip().lower()
    if e in config.FOUNDER_EMAILS or e in config.PARTNER_EMAILS:
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
    """All hardcoded config entries (founders + partners) — read-only in the
    UI. Returned in the same shape as list_grants() with source='config'."""
    out: list[dict] = []
    for e in sorted(config.FOUNDER_EMAILS):
        out.append({
            "email": e, "role": "founder", "notes": "",
            "granted_by": "config", "granted_at": "", "source": "config",
        })
    for e in sorted(config.PARTNER_EMAILS):
        out.append({
            "email": e, "role": "partner", "notes": "",
            "granted_by": "config", "granted_at": "", "source": "config",
        })
    return out
