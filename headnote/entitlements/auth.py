"""Supabase JWT verification + FastAPI dependencies.

Two dependencies are exported:

  - get_current_user : required auth. Raises 401 if no/invalid token.
  - optional_user    : returns CurrentUser or None. Use on endpoints that
                       support anonymous browsing (e.g. /api/health).

Verification strategy
---------------------
Supabase signs JWTs with the project's JWT_SECRET using HS256 by default.
We verify locally — no network round-trip per request. The secret is set
in Railway as SUPABASE_JWT_SECRET (find it in Supabase Dashboard →
Settings → API → JWT Settings → JWT Secret).

If the secret is not configured, the dependency falls back to "unverified
decode" mode: it parses the token but does not check the signature. This
is for local development only — production MUST set SUPABASE_JWT_SECRET.
A warning logs on every request in unverified mode so it surfaces loudly.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional

import jwt
from fastapi import Header, HTTPException, status


log = logging.getLogger(__name__)


SUPABASE_JWT_SECRET = os.environ.get("SUPABASE_JWT_SECRET")
SUPABASE_JWT_AUDIENCE = os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")


@dataclass
class CurrentUser:
    """The authenticated user, derived from a verified Supabase JWT."""
    id: str           # uuid string
    email: str | None
    role: str         # 'authenticated' typically
    raw_claims: dict  # full decoded payload for advanced uses


def _decode_token(token: str) -> dict:
    """Decode and verify a Supabase JWT. Returns the claims dict.

    Raises HTTPException(401) on any failure.
    """
    if not SUPABASE_JWT_SECRET:
        log.warning(
            "auth: SUPABASE_JWT_SECRET not set — decoding without signature verification. "
            "DO NOT run this configuration in production."
        )
        try:
            return jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {e}",
                headers={"WWW-Authenticate": "Bearer"},
            )

    try:
        return jwt.decode(
            token,
            SUPABASE_JWT_SECRET,
            algorithms=["HS256"],
            audience=SUPABASE_JWT_AUDIENCE,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token expired. Sign in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _user_from_claims(claims: dict) -> CurrentUser:
    user_id = claims.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token missing sub claim",
        )
    return CurrentUser(
        id=user_id,
        email=claims.get("email"),
        role=claims.get("role", "authenticated"),
        raw_claims=claims,
    )


def _extract_bearer(authorization: Optional[str]) -> Optional[str]:
    if not authorization:
        return None
    parts = authorization.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    return parts[1].strip() or None


# ---------------------------------------------------------------- dependencies

def get_current_user(
    authorization: Optional[str] = Header(default=None),
) -> CurrentUser:
    """FastAPI dependency: requires a valid Supabase JWT.

    Usage:
        @router.post("/api/situation")
        def api_situation(user: CurrentUser = Depends(get_current_user), ...):
            ...
    """
    token = _extract_bearer(authorization)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'Authorization: Bearer <token>' header",
            headers={"WWW-Authenticate": "Bearer"},
        )
    claims = _decode_token(token)
    return _user_from_claims(claims)


def optional_user(
    authorization: Optional[str] = Header(default=None),
) -> CurrentUser | None:
    """FastAPI dependency: returns user if a valid token is present, else None.

    Use on endpoints that support anonymous browsing (health, public docs).
    """
    token = _extract_bearer(authorization)
    if not token:
        return None
    try:
        claims = _decode_token(token)
        return _user_from_claims(claims)
    except HTTPException:
        return None
