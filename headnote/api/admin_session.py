"""Password sign-in for the admin console, and the one shared bearer check.

Why this exists
---------------
Every /admin/* route used to demand `Authorization: Bearer <ADMIN_TOKEN>`,
and the four admin HTML pages each prompted for that raw token and parked it
in localStorage. That works for one operator with a terminal. It does not
work for the thing actually asked for: a co-founder or a colleague opening
the console on their own phone. You cannot WhatsApp somebody a root token
and call it a login.

So this module adds a human door — email + password — that mints a signed,
expiring session token. The session token is then accepted everywhere the
raw ADMIN_TOKEN is accepted, which is why `verify_admin_bearer` below is
imported by admin.py, admin_v2.py and partners_admin.py instead of each
keeping its own copy of the check. One gate, three doors.

The design decisions worth knowing
----------------------------------
* **No new secret.** Sessions are signed with ADMIN_TOKEN, which already
  exists and is already the root credential. A separate signing key would be
  one more thing to set, one more thing to forget, and would buy nothing:
  anyone holding ADMIN_TOKEN can already do everything a session can.

* **The password is never in this file.** See config.ADMIN_PASSWORD. The
  repo is public.

* **Fails closed.** No ADMIN_TOKEN → no signing key → sessions cannot be
  minted or verified, and the console says password sign-in is unavailable.
  No ADMIN_PASSWORD → login always refuses. There is no default password.

* **Stateless.** The token carries its own expiry and signature; nothing is
  stored server-side. This machine has one SQLite volume and a habit of
  being restarted, and a session table would mean everyone gets logged out
  on every deploy. The cost is that an individual session cannot be revoked
  early — rotating ADMIN_TOKEN invalidates all of them at once, which is
  the honest emergency lever and is documented on the console itself.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from fastapi import HTTPException, status

from headnote import config

log = logging.getLogger(__name__)

_TOKEN_PREFIX = "hns1"


# ---------------------------------------------------------------- helpers

def _b64e(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64d(txt: str) -> bytes:
    pad = "=" * (-len(txt) % 4)
    return base64.urlsafe_b64decode(txt + pad)


def _signing_key() -> Optional[bytes]:
    """ADMIN_TOKEN doubles as the session signing key. None = feature off."""
    tok = (config.ADMIN_TOKEN or "").strip()
    return tok.encode("utf-8") if tok else None


def _sign(payload_b64: str, key: bytes) -> str:
    return _b64e(hmac.new(key, payload_b64.encode("ascii"), hashlib.sha256).digest())


# ---------------------------------------------------------------- login

def password_login_available() -> bool:
    """True when both halves of the human door are configured."""
    return bool(_signing_key()) and bool(config.ADMIN_EMAIL) and bool(config.ADMIN_PASSWORD)


def check_credentials(email: str, password: str) -> bool:
    """Constant-time credential check. False unless BOTH halves match.

    compare_digest on both fields, and both comparisons always run, so a
    wrong email and a wrong password take the same time and leak nothing
    about which half was wrong.
    """
    if not password_login_available():
        return False
    email_ok = hmac.compare_digest(
        (email or "").strip().lower(), config.ADMIN_EMAIL or "",
    )
    pass_ok = hmac.compare_digest(password or "", config.ADMIN_PASSWORD or "")
    return email_ok and pass_ok


def issue_session(email: str, *, ttl_days: Optional[int] = None) -> tuple[str, int]:
    """Mint a signed session token. Returns (token, expiry_epoch_seconds)."""
    key = _signing_key()
    if not key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ADMIN_TOKEN is not set, so admin sessions cannot be signed.",
        )
    days = ttl_days if ttl_days is not None else config.ADMIN_SESSION_DAYS
    exp = int(time.time()) + int(days) * 86400
    payload = {"e": (email or "").strip().lower(), "exp": exp}
    payload_b64 = _b64e(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{_TOKEN_PREFIX}.{payload_b64}.{_sign(payload_b64, key)}", exp


def verify_session(token: str) -> Optional[str]:
    """Return the signed-in email, or None if the token is bad or expired.

    Never raises: callers treat None as "not a session" and fall through to
    the raw-token path.
    """
    key = _signing_key()
    if not key or not token or not token.startswith(_TOKEN_PREFIX + "."):
        return None
    try:
        _, payload_b64, sig = token.split(".", 2)
    except ValueError:
        return None
    # Signature first — never parse a payload we have not authenticated.
    if not hmac.compare_digest(sig, _sign(payload_b64, key)):
        return None
    try:
        payload = json.loads(_b64d(payload_b64))
    except Exception:
        return None
    if int(payload.get("exp") or 0) <= int(time.time()):
        return None
    email = payload.get("e")
    return email if isinstance(email, str) and email else None


# ---------------------------------------------------------------- brute-force throttle

# In-memory, per-process, keyed by client IP. One machine runs this app, so a
# process-local counter is the real thing and not an approximation. It is
# deliberately not persisted: a restart clearing a lockout is acceptable, a
# restart locking out the founder during an outage is not.
_FAILURES: dict[str, list[float]] = {}
_MAX_FAILURES = 8
_WINDOW_SECONDS = 900.0     # 15 minutes


def note_failure(client_ip: str) -> None:
    now = time.time()
    hits = [t for t in _FAILURES.get(client_ip, []) if now - t < _WINDOW_SECONDS]
    hits.append(now)
    _FAILURES[client_ip] = hits


def clear_failures(client_ip: str) -> None:
    _FAILURES.pop(client_ip, None)


def seconds_locked_out(client_ip: str) -> int:
    """0 if this IP may attempt a login, else seconds until it may retry."""
    now = time.time()
    hits = [t for t in _FAILURES.get(client_ip, []) if now - t < _WINDOW_SECONDS]
    _FAILURES[client_ip] = hits
    if len(hits) < _MAX_FAILURES:
        return 0
    return max(1, int(_WINDOW_SECONDS - (now - min(hits))))


# ---------------------------------------------------------------- the shared gate

def verify_admin_bearer(authorization: Optional[str]) -> Optional[str]:
    """Return an actor label for a valid credential, or None.

    Accepts either the raw ADMIN_TOKEN (actor "ops", used by cron jobs and
    curl) or a console session token (actor = the signed-in email). Returns
    None rather than raising so each router can keep its own error shape.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(None, 1)[1].strip()
    if not token:
        return None
    root = (config.ADMIN_TOKEN or "").strip()
    if root and hmac.compare_digest(token, root):
        return "ops"
    email = verify_session(token)
    return email if email else None


def require_admin_bearer(authorization: Optional[str]) -> str:
    """verify_admin_bearer, but raises the standard admin errors.

    This is the single implementation behind admin.py, admin_v2.py and
    partners_admin.py, which previously each had their own byte-for-byte
    copy of this check.
    """
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Admin routes are disabled: ADMIN_TOKEN env var is not set. "
                "Add it to .env (e.g. `ADMIN_TOKEN=<random-long-string>`) "
                "and restart."
            ),
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'Authorization: Bearer <token>' header. Sign in at /admin.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    actor = verify_admin_bearer(authorization)
    if not actor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not a valid admin token or session. Sign in again at /admin.",
        )
    return actor
