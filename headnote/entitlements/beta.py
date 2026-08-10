"""V2 beta allowlist — who can see /home, /research and /draft-dna today.

This is deliberately SEPARATE from access grants (entitlements/grants.py).
A grant answers "what plan is this user on"; beta answers "can this user see
the new surfaces yet". Keeping them apart means:

  * adding a tester never touches billing, quotas or price;
  * a paying user who is not a tester keeps the exact /app they have today;
  * removing someone from the beta cannot accidentally cancel a subscription.

Resolution order (most-trusted first):
  1. config.V2_PUBLIC          → everyone, the day V2 ships (one env var)
  2. config.FOUNDER_EMAILS     → founders are always in the beta
  3. config.BETA_EMAILS        → root tier, survives a DB reset
  4. beta_testers table        → added/revoked from /admin, no deploy

Fails CLOSED: if the SQLite file is unreachable we fall back to the config
tiers only. A tester briefly losing access is a far better failure than the
whole user base being let into an unfinished surface.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status

from headnote import config
from headnote.entitlements.auth import CurrentUser, get_current_user


def _conn() -> sqlite3.Connection:
    """Lazy connection. Lives in FEEDBACK_DB alongside access_grants so the
    beta list survives restarts on the same volume and needs no new path."""
    c = sqlite3.connect(config.FEEDBACK_DB, timeout=10)
    c.execute(
        """
        CREATE TABLE IF NOT EXISTS beta_testers (
            email    TEXT PRIMARY KEY,
            notes    TEXT,
            added_by TEXT,
            added_at TEXT NOT NULL
        )
        """
    )
    c.commit()
    return c


def is_beta(email: Optional[str]) -> bool:
    """True iff this user may see the V2 surfaces. Case-insensitive."""
    if config.V2_PUBLIC:
        return True
    if not email:
        return False
    e = email.strip().lower()
    if not e:
        return False
    if e in config.FOUNDER_EMAILS or e in config.BETA_EMAILS:
        return True
    try:
        c = _conn()
        row = c.execute(
            "SELECT 1 FROM beta_testers WHERE email = ?", (e,)
        ).fetchone()
        c.close()
        return row is not None
    except Exception:
        # Fail closed — config tiers already returned True above if allowed.
        return False


def require_beta(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """FastAPI dependency: 403 unless the caller is a V2 beta tester.

    Use on endpoints that ONLY the V2 surfaces call, e.g.

        @router.get("/api/home")
        def home(user: CurrentUser = Depends(require_beta)):
            ...

    Never put this on an endpoint the old /app also calls — that would lock
    existing users out of features they already pay for. The response body
    carries code="not_in_beta" so the frontend can tell this apart from a
    quota 402 or an auth 401.
    """
    if not is_beta(user.email):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "not_in_beta",
                "message": "This is part of the Headnote V2 private beta.",
            },
        )
    return user


def add_tester(email: str, *, notes: str = "", added_by: str = "") -> dict:
    """Add (or update) a tester. Returns the stored row."""
    if not email or "@" not in email:
        raise ValueError("email must be a valid address")
    e = email.strip().lower()
    now = datetime.now(timezone.utc).isoformat()
    c = _conn()
    c.execute(
        "INSERT OR REPLACE INTO beta_testers (email, notes, added_by, added_at) "
        "VALUES (?, ?, ?, ?)",
        (e, notes.strip() or None, added_by.strip() or None, now),
    )
    c.commit()
    c.close()
    return {
        "email": e, "notes": notes.strip(), "added_by": added_by.strip(),
        "added_at": now, "source": "db",
    }


def remove_tester(email: str) -> bool:
    """Delete a DB tester row. Returns True iff a row was deleted.

    Config-tier entries (BETA_EMAILS / FOUNDER_EMAILS) are NOT removable this
    way — they are managed in code/env on purpose.
    """
    if not email:
        return False
    e = email.strip().lower()
    try:
        c = _conn()
        cur = c.execute("DELETE FROM beta_testers WHERE email = ?", (e,))
        c.commit()
        c.close()
        return cur.rowcount > 0
    except Exception:
        return False


def list_testers() -> list[dict]:
    """Every tester, config tier first then DB rows (newest first)."""
    out: list[dict] = []
    for e in sorted(config.FOUNDER_EMAILS):
        out.append({"email": e, "notes": "founder — implicit",
                    "added_by": "config", "added_at": "", "source": "config"})
    for e in sorted(config.BETA_EMAILS):
        out.append({"email": e, "notes": "", "added_by": "config",
                    "added_at": "", "source": "config"})
    try:
        c = _conn()
        rows = c.execute(
            "SELECT email, notes, added_by, added_at "
            "FROM beta_testers ORDER BY added_at DESC"
        ).fetchall()
        c.close()
        for r in rows:
            out.append({
                "email": r[0], "notes": r[1] or "", "added_by": r[2] or "",
                "added_at": r[3], "source": "db",
            })
    except Exception:
        pass
    return out
