"""OTPless ↔ Supabase auth bridge.

Flow
----
1. Frontend opens the OTPless widget (loaded from otpless.com SDK in
   static/index.html). User completes Truecaller / WhatsApp / SMS OTP.
2. OTPless SDK fires `window.otpless(user)` with a short-lived token in
   `user.token`. The frontend POSTs that token to /api/auth/otpless-exchange.
3. THIS endpoint:
     a. Verifies the OTPless token against OTPless's /verify-token API
        (server-side, so the client cannot spoof the phone).
     b. Extracts phone (+91…) and optional email from the response.
     c. Finds or creates a row in Supabase auth.users via the admin API.
        Phone is the unique key. We synthesize an email
        (otpless+<phone>@auth.headnote.in) so Supabase's email-based magic
        link path can mint a session.
     d. Calls Supabase admin /generate_link → returns an action_link with a
        hashed_token. This is the official Supabase pattern for bridging
        external auth — we hand the token_hash to the frontend, which calls
        supabase.auth.verifyOtp() to materialize a normal Supabase session
        (access + refresh tokens, all RLS works, JWT verified by our
        existing get_current_user dependency).
4. Frontend stores the session, onAuthStateChange fires, app reveals.

Why not mint our own JWT signed with SUPABASE_JWT_SECRET?
--------------------------------------------------------
You can — but you lose refresh token issuance (supabase-js's setSession
requires a refresh_token to round-trip). The magic-link bridge above lets
Supabase issue both tokens normally, so token refresh, sign-out, and
session persistence all Just Work via the standard SDK paths.

Env vars expected
-----------------
OTPLESS_CLIENT_ID         from otpless.com dashboard
OTPLESS_CLIENT_SECRET     from otpless.com dashboard
OTPLESS_VERIFY_URL        defaults to https://user-auth.otpless.app/auth/v1/userInfo
                          (override if OTPless changes the endpoint)
SUPABASE_URL              already set
SUPABASE_SERVICE_ROLE_KEY already set
OTPLESS_SYNTHETIC_EMAIL_DOMAIN  defaults to auth.headnote.in — used for the
                                synthetic email when the user logs in by
                                phone only (no email channel).

If OTPLESS_CLIENT_ID / SECRET aren't set, /api/auth/otpless-exchange
returns 503 with a clear message so misconfiguration surfaces early.
"""

from __future__ import annotations

import json as _json
import logging
import os
from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["auth"])


OTPLESS_VERIFY_URL = os.environ.get(
    "OTPLESS_VERIFY_URL",
    "https://user-auth.otpless.app/auth/v1/userInfo",
)
SYNTHETIC_EMAIL_DOMAIN = os.environ.get(
    "OTPLESS_SYNTHETIC_EMAIL_DOMAIN", "auth.headnote.in"
)


# ---------------------------------------------------------------- models

class OtplessExchangeIn(BaseModel):
    otpless_token: str = Field(..., min_length=10, max_length=4096,
                               description="Token from window.otpless(user).token")


class OtplessExchangeOut(BaseModel):
    """Returned to the frontend. The FE calls supabase.auth.verifyOtp with
    these to materialize a real Supabase session."""
    token_hash: str
    email:      str       # synthetic if user signed in by phone only
    user_id:    str
    is_new:     bool      # True if this exchange created the auth.users row
    phone:      Optional[str] = None
    name:       Optional[str] = None


# ---------------------------------------------------------------- OTPless side

def _verify_otpless_token(otpless_token: str) -> dict:
    """Call OTPless's /userInfo with the short-lived client token.
    Returns the parsed response on success; raises HTTPException on failure.

    OTPless response (current shape):
        {
          "identities": [
            {"identityType": "MOBILE", "identityValue": "+919876543210",
             "channel": "WHATSAPP", "isVerified": true, ...}
          ],
          "name": "Optional",
          "email": "optional@example.com",
          "token": "...",
          ...
        }
    """
    client_id     = os.environ.get("OTPLESS_CLIENT_ID", "")
    client_secret = os.environ.get("OTPLESS_CLIENT_SECRET", "")
    if not (client_id and client_secret):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "OTPless sign-in is not configured on this deploy. "
                "Set OTPLESS_CLIENT_ID and OTPLESS_CLIENT_SECRET env vars."
            ),
        )

    try:
        r = httpx.post(
            OTPLESS_VERIFY_URL,
            headers={
                "Content-Type": "application/json",
                "clientId":     client_id,
                "clientSecret": client_secret,
            },
            content=_json.dumps({"token": otpless_token}),
            timeout=8.0,
        )
    except httpx.HTTPError as e:
        log.error("OTPless verify network error: %s", e)
        raise HTTPException(status_code=502, detail="Could not reach OTPless. Try again.")

    if r.status_code != 200:
        log.warning("OTPless verify returned %s: %s", r.status_code, r.text[:200])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="OTPless rejected the token. Please sign in again.",
        )

    try:
        return r.json() or {}
    except Exception as e:
        log.exception("OTPless response not JSON: %s", e)
        raise HTTPException(status_code=502, detail="OTPless returned a malformed response.")


def _extract_identity(otpless_user: dict) -> tuple[str, str, str]:
    """Pull (phone, email, name) from the OTPless response. Phone is the
    canonical identifier; email may be empty if user signed in via SMS/
    WhatsApp/Truecaller only."""
    phone = ""
    email = (otpless_user.get("email") or "").strip().lower()
    name  = (otpless_user.get("name")  or "").strip()

    for ident in otpless_user.get("identities") or []:
        itype = (ident.get("identityType") or "").upper()
        ivalue = (ident.get("identityValue") or "").strip()
        if itype in ("MOBILE", "PHONE") and ivalue:
            phone = ivalue
        if itype == "EMAIL" and ivalue and not email:
            email = ivalue.lower()
        if not name and ident.get("name"):
            name = ident["name"].strip()

    if not phone and not email:
        raise HTTPException(
            status_code=400,
            detail="OTPless response carried neither phone nor email.",
        )
    return phone, email, name


# ---------------------------------------------------------------- Supabase side

def _supabase_admin_headers() -> dict[str, str]:
    base = os.environ.get("SUPABASE_URL")
    key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (base and key):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Supabase admin API not configured (SUPABASE_URL / SERVICE_ROLE_KEY missing).",
        )
    return {"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def _find_user(*, phone: str = "", email: str = "") -> dict:
    """Find an auth.users row by phone or email. Returns {} on miss.

    Supabase's /auth/v1/admin/users endpoint does NOT honour an `?email=`
    filter parameter — it paginates the full user list and silently ignores
    unknown params. So we MUST list and filter in Python with strict
    equality. (A prior version of this returned users[0] from a 'filtered'
    list, which actually returned the first user globally — that's how an
    'advocate.mansi.singh@gmail.com' lookup matched 'sumitrpcs@gmail.com'.)

    Paginates up to 10 pages × 1000 users = 10k user cap, which is well
    above our current scale; bump if needed.
    """
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not base:
        return {}
    needle_email = (email or "").strip().lower()
    needle_phone_digits = "".join(ch for ch in (phone or "") if ch.isdigit())

    url = f"{base}/auth/v1/admin/users"
    per_page = 1000
    for page in range(1, 11):                # cap at 10 pages = 10k users
        try:
            r = httpx.get(
                url, headers=_supabase_admin_headers(),
                params={"page": str(page), "per_page": str(per_page)},
                timeout=8.0,
            )
            r.raise_for_status()
            data = r.json() or {}
        except httpx.HTTPError as e:
            log.warning("supabase admin users list page=%d failed: %s", page, e)
            return {}

        users = data.get("users") or []
        if not users:
            return {}
        for u in users:
            u_email = (u.get("email") or "").strip().lower()
            if needle_email and u_email == needle_email:
                return u
            if needle_phone_digits:
                u_phone_digits = "".join(ch for ch in (u.get("phone") or "") if ch.isdigit())
                if u_phone_digits and u_phone_digits == needle_phone_digits:
                    return u
        # Supabase returns up to per_page; if fewer, we've reached the end.
        if len(users) < per_page:
            return {}
    return {}


def _create_user(*, phone: str, email: str, name: str) -> dict:
    """Create an auth.users row with phone + email both confirmed.

    Supabase rejects duplicate phone/email at the DB layer, so this is
    only called after _find_user returned empty.
    """
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    url  = f"{base}/auth/v1/admin/users"
    payload: dict = {
        "email":          email,
        "email_confirm":  True,
        "user_metadata":  {"full_name": name, "auth_via": "otpless"},
        "app_metadata":   {"provider": "otpless"},
    }
    if phone:
        payload["phone"]         = phone
        payload["phone_confirm"] = True
    try:
        r = httpx.post(url, headers=_supabase_admin_headers(),
                       content=_json.dumps(payload), timeout=8.0)
        r.raise_for_status()
        return r.json() or {}
    except httpx.HTTPError as e:
        log.exception("supabase admin user create failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Could not create user: {e}")


def _generate_magic_link(email: str) -> str:
    """Ask Supabase to issue a magic-link token for `email`. We return only
    the `hashed_token` — the FE passes it to supabase.auth.verifyOtp() to
    materialize a normal session (with refresh_token, all the trimmings).

    Reference: https://supabase.com/docs/reference/api/generatelink
    """
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    url  = f"{base}/auth/v1/admin/generate_link"
    try:
        r = httpx.post(
            url,
            headers=_supabase_admin_headers(),
            content=_json.dumps({"type": "magiclink", "email": email}),
            timeout=8.0,
        )
        r.raise_for_status()
        data = r.json() or {}
    except httpx.HTTPError as e:
        log.exception("supabase admin generate_link failed: %s", e)
        raise HTTPException(status_code=502, detail=f"Could not mint session token: {e}")

    # The response shape varies slightly across Supabase versions; the
    # hashed_token lives under `properties.hashed_token` on recent ones
    # and `hashed_token` at the top level on older ones.
    token_hash = (
        (data.get("properties") or {}).get("hashed_token")
        or data.get("hashed_token")
        or ""
    )
    if not token_hash:
        log.error("generate_link returned no hashed_token. Body: %s", str(data)[:300])
        raise HTTPException(status_code=502, detail="Supabase returned no token. Try again.")
    return token_hash


# ---------------------------------------------------------------- endpoint

@router.post(
    "/otpless-exchange",
    response_model=OtplessExchangeOut,
    summary="Exchange an OTPless token for a Supabase session",
)
def otpless_exchange(body: OtplessExchangeIn) -> OtplessExchangeOut:
    """Public endpoint — no Bearer required. Auth is the OTPless token itself.

    Flow as documented at the top of the file. Returns the values the FE
    needs to call supabase.auth.verifyOtp() and finalize the sign-in.
    """
    otpless_user = _verify_otpless_token(body.otpless_token)
    phone, email, name = _extract_identity(otpless_user)

    # Synthesize an email when the user only verified by phone. The synthetic
    # email is invisible to the user — it exists only so Supabase's email-
    # based magic-link path can mint tokens. Keep the format stable so we
    # find the same user on re-login.
    if not email:
        # Strip + and spaces for a clean local-part. +91 9876543210 → 919876543210
        local = "".join(ch for ch in phone if ch.isdigit())
        email = f"otpless+{local}@{SYNTHETIC_EMAIL_DOMAIN}"

    existing = _find_user(phone=phone, email=email)
    if existing:
        user = existing
        is_new = False
    else:
        user = _create_user(phone=phone, email=email, name=name)
        is_new = True

    user_id = (user.get("id") or "").strip()
    if not user_id:
        log.error("OTPless exchange: user record has no id: %s", str(user)[:300])
        raise HTTPException(status_code=502, detail="User created but no id returned.")

    # generate_link works against the canonical email Supabase stored, which
    # may differ in case from what we sent. Use the value Supabase returned.
    canonical_email = (user.get("email") or email).lower()
    token_hash = _generate_magic_link(canonical_email)

    log.info(
        "otpless_exchange: %s user=%.8s phone=%s",
        "created" if is_new else "matched", user_id, phone or "(none)",
    )
    return OtplessExchangeOut(
        token_hash=token_hash,
        email=canonical_email,
        user_id=user_id,
        is_new=is_new,
        phone=phone or None,
        name=name or None,
    )
