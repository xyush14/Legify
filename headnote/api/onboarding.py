"""Onboarding endpoints — fire post-signup side-effects.

Right now:
  POST /api/onboarding/welcome-email   — idempotent welcome email send.

Flow
----
Browser → auth.js _saveOnboarding() saves the profile row directly to
Supabase (RLS-protected). Once that succeeds, the frontend calls this
endpoint to trigger our backend-managed side-effects (welcome email,
later: Slack notification, CRM sync, etc.).

Idempotency is critical — the frontend can call this multiple times
(reload, network retry). user_profiles.welcome_sent is the dedupe flag.
If the column doesn't exist yet the endpoint still works; it just won't
remember it sent already (which is annoying but not destructive).
"""

from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException

from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements import _supabase
from headnote.email import send_welcome


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/onboarding", tags=["onboarding"])


def _profile(user_id: str) -> dict:
    """Read the user_profiles row. Returns {} on miss."""
    try:
        rows = _supabase.select(
            "user_profiles",
            params={
                "id":     f"eq.{user_id}",
                "select": "name,phone,welcome_sent",
                "limit":  "1",
            },
        )
        return rows[0] if rows else {}
    except Exception as e:
        log.warning("onboarding: profile lookup failed for user=%.8s: %s", user_id, e)
        return {}


def _mark_welcome_sent(user_id: str) -> None:
    """Best-effort flag write so we don't resend on the next call. If the
    column doesn't exist in the schema, this fails silently — the endpoint
    is still idempotent enough at the Resend side (same recipient + tag)."""
    try:
        _supabase.update(
            "user_profiles",
            {"welcome_sent": True},
            params={"id": f"eq.{user_id}"},
        )
    except Exception as e:
        log.info("onboarding: welcome_sent flag write skipped (non-fatal): %s", e)


@router.post("/welcome-email", summary="Send the welcome email (idempotent)")
def post_welcome_email(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Triggered by the frontend right after onboarding completes.

    Idempotency: if user_profiles.welcome_sent is true, returns
    {"sent": false, "reason": "already_sent"} without contacting Resend.
    Safe to call multiple times.

    Failure modes (all return 2xx — never block UX):
      - RESEND_API_KEY missing            → {"sent": false, "reason": "no_provider"}
      - Resend API call fails             → {"sent": false, "reason": "send_failed"}
      - user has no email (shouldn't happen with Google OAuth) → 400
    """
    if not user.email:
        raise HTTPException(
            status_code=400,
            detail="Cannot send welcome email — no email on account.",
        )

    profile = _profile(user.id)
    if profile.get("welcome_sent") is True:
        log.info("welcome-email: already sent for user=%.8s — skipping", user.id)
        return {"sent": False, "reason": "already_sent"}

    name = profile.get("name") or ""
    if not name:
        # Fall back to Google profile name from the JWT claims.
        meta = (user.raw_claims or {}).get("user_metadata") or {}
        name = meta.get("full_name") or meta.get("name") or ""

    ok = send_welcome(to_email=user.email, name=name)
    if ok:
        _mark_welcome_sent(user.id)
        return {"sent": True}
    return {"sent": False, "reason": "send_failed"}
