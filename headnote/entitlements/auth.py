"""Supabase JWT verification + FastAPI dependencies.

Two dependencies are exported:

  - get_current_user : required auth. Raises 401 if no/invalid token.
  - optional_user    : returns CurrentUser or None. Use on endpoints that
                       support anonymous browsing (e.g. /api/health).

Verification strategy
---------------------
Supabase signs JWTs with one of:
  - HS256 (legacy projects): signed with SUPABASE_JWT_SECRET (symmetric).
  - ES256/RS256 (newer projects, default for projects created from 2025):
    signed with a private key; we verify with the public key from JWKS.

We inspect the token's `alg` header at runtime and pick the right path.

JWKS endpoint: `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`
PyJWKClient caches the keys in memory and refreshes as needed.

If neither verification path is available (env vars missing AND JWKS
unreachable), the dependency falls back to "unverified decode" so the
app keeps working with a loud warning in logs.
"""

from __future__ import annotations

import contextvars
import logging
import os
from dataclasses import dataclass
from typing import Optional

import jwt
from jwt import PyJWKClient
from fastapi import Header, HTTPException, status


log = logging.getLogger(__name__)


# Per-request context: lets downstream modules (subscription, gates) see the
# authenticated user's email without threading it through every signature.
# Set by get_current_user / optional_user after the JWT decode succeeds.
current_user_email: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_user_email", default=None,
)


SUPABASE_URL          = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_JWT_SECRET   = os.environ.get("SUPABASE_JWT_SECRET")
SUPABASE_JWT_AUDIENCE = os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")


_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient | None:
    """Lazy-init a JWKS client pointed at the Supabase project's JWKS endpoint.

    PyJWKClient caches downloaded keys; rotating keys takes effect at the
    next cache miss without a process restart.
    """
    global _jwks_client
    if _jwks_client is None and SUPABASE_URL:
        url = f"{SUPABASE_URL}/auth/v1/.well-known/jwks.json"
        try:
            _jwks_client = PyJWKClient(url, cache_keys=True, lifespan=3600)
        except Exception as e:
            log.error("Failed to init JWKS client for %s: %s", url, e)
            return None
    return _jwks_client


@dataclass
class CurrentUser:
    """The authenticated user, derived from a verified Supabase JWT."""
    id: str           # uuid string
    email: str | None
    role: str         # 'authenticated' typically
    raw_claims: dict  # full decoded payload for advanced uses


def _decode_unverified(token: str) -> dict:
    """Last-resort: decode without checking signature. Logs a loud warning.
    Used when no verification path is available — keeps dev/local working."""
    log.warning("auth: decoding JWT without signature verification (NOT for production)")
    try:
        return jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _decode_asymmetric(token: str, alg: str) -> dict:
    """Verify ES256/RS256 token via JWKS public key. Falls back to unverified
    decode if JWKS can't be reached (logged loudly)."""
    client = _get_jwks_client()
    if client is None:
        return _decode_unverified(token)
    try:
        signing_key = client.get_signing_key_from_jwt(token).key
    except Exception as e:
        log.error("JWKS key fetch failed (%s) — falling back to unverified decode", e)
        return _decode_unverified(token)
    return jwt.decode(
        token,
        signing_key,
        algorithms=[alg],
        audience=SUPABASE_JWT_AUDIENCE,
    )


def _decode_hs256(token: str) -> dict:
    """Verify HS256 token with SUPABASE_JWT_SECRET. Falls back to unverified
    if the secret isn't configured."""
    if not SUPABASE_JWT_SECRET:
        return _decode_unverified(token)
    return jwt.decode(
        token,
        SUPABASE_JWT_SECRET,
        algorithms=["HS256"],
        audience=SUPABASE_JWT_AUDIENCE,
    )


def _decode_token(token: str) -> dict:
    """Inspect token header to pick the right verification path, then decode.

    Raises HTTPException(401) on any verification failure.
    """
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Malformed token: {e}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    alg = header.get("alg", "HS256")

    try:
        if alg in ("ES256", "RS256", "ES384", "RS384", "ES512", "RS512"):
            return _decode_asymmetric(token, alg)
        return _decode_hs256(token)
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
    user = _user_from_claims(claims)
    # Expose email to downstream modules (e.g. founder bypass in subscription).
    current_user_email.set((user.email or "").lower() if user.email else None)
    return user


def optional_user(
    authorization: Optional[str] = Header(default=None),
) -> CurrentUser | None:
    """FastAPI dependency: returns user if a valid token is present, else None.

    Use on endpoints that support anonymous browsing (health, public docs).
    """
    token = _extract_bearer(authorization)
    if not token:
        current_user_email.set(None)
        return None
    try:
        claims = _decode_token(token)
        user = _user_from_claims(claims)
        current_user_email.set((user.email or "").lower() if user.email else None)
        return user
    except HTTPException:
        return None
