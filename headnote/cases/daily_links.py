"""Signed, expiring links for the daily cause-list loop.

Each day a lawyer gets a WhatsApp + email link that opens their cause list for ONE
date WITHOUT logging in: they print it, and in the evening upload the marked-up
sheet from the same link. The link is a STATELESS HMAC-signed token (no DB row) —
it carries the user_id + date + expiry, signed with a server secret. Verifying it
grants access ONLY to that user's cause list for that one date.

Why stateless: no table to provision/clean, links self-expire, and a leaked link
exposes exactly one lawyer's one day — never the whole account.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import time
from typing import Optional

from headnote import config


def _secret() -> bytes:
    s = (config.ADMIN_TOKEN
         or os.environ.get("SUPABASE_JWT_SECRET")
         or os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
         or "dev-insecure-daily-link-secret")
    return s.encode()


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def _b64d(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def make_token(user_id: str, date_iso: str, *, ttl_days: int = 4) -> str:
    """Sign a {user_id, date, expiry} token. `date_iso` is YYYY-MM-DD."""
    payload = {"u": user_id, "d": date_iso, "x": int(time.time()) + ttl_days * 86400}
    body = _b64e(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64e(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}"


def verify_token(token: str) -> Optional[dict]:
    """Return {user_id, date} if the token is well-formed, correctly signed and
    unexpired; else None. Constant-time signature check."""
    try:
        body, sig = (token or "").split(".", 1)
        expect = _b64e(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(_b64d(body))
        if int(payload.get("x", 0)) < int(time.time()):
            return None
        uid, date = payload.get("u"), payload.get("d")
        if not (uid and date):
            return None
        return {"user_id": uid, "date": date}
    except Exception:  # noqa: BLE001 — any malformed token is simply invalid
        return None
