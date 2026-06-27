"""Onboarding endpoints — fire post-signup side-effects.

Right now:
  POST /api/onboarding/welcome-email   — idempotent welcome email send.

Flow
----
Browser → auth.js _saveOnboarding() saves the profile row directly to
Supabase (RLS-protected). Once that succeeds, the frontend calls this
endpoint to trigger our backend-managed side-effects (welcome email,
later: Slack notification, CRM sync, etc.).

Idempotency is critical — the frontend can (and does) call this more than
once per sign-in: Supabase's onAuthStateChange emits both INITIAL_SESSION
and SIGNED_IN on a fresh OAuth redirect, so two near-simultaneous POSTs are
the norm, not an edge case. Dedupe is enforced by an ATOMIC CLAIM on
user_profiles.welcome_sent: a conditional UPDATE that flips the flag
false→true and returns the row only if it wasn't already set. Of two
concurrent callers exactly one wins the claim and is allowed to hit Resend;
the other is told "already_sent". A plain read-then-write check is NOT
enough here — both callers would read false before either writes.
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


def _claim_welcome(user_id: str) -> bool:
    """Atomically claim the welcome-email send for this user.

    Conditional UPDATE: flip welcome_sent false/NULL → true, but only for a
    row where it isn't already true (PostgREST filter ``welcome_sent=not.is.true``,
    i.e. SQL ``welcome_sent IS NOT TRUE``). Because the wrapper sends
    ``Prefer: return=representation``, the response carries the row only when
    the UPDATE actually matched. Under Postgres READ COMMITTED, of two
    concurrent callers exactly one gets a non-empty result — that caller
    "won" and is the only one allowed to send. This is what stops the
    frontend's double-fire from producing two emails.

    Returns True iff this call should proceed to send. If the claim UPDATE
    fails outright (column missing, transient PostgREST error, etc.) we
    SEND ANYWAY — a duplicate welcome is a much better failure mode than
    no welcome at all. Migration 006 adds the welcome_sent column;
    without it every claim used to silently lose, leaving every new user
    without a welcome email."""
    try:
        rows = _supabase.update(
            "user_profiles",
            {"welcome_sent": True},
            params={"id": f"eq.{user_id}", "welcome_sent": "not.is.true"},
        )
        if rows:
            return True
        # UPDATE returned no rows. Two possible reasons:
        #   (a) someone else already claimed and welcome_sent=true → don't send
        #   (b) the row doesn't exist yet OR the column doesn't exist (PostgREST
        #       silently 400s and _supabase.update returns []) → we have NO
        #       evidence of a prior send. Send anyway — a duplicate is better
        #       than the bug we just spent an hour finding.
        # Disambiguate by reading the row back.
        check = _supabase.select(
            "user_profiles",
            params={"id": f"eq.{user_id}", "select": "welcome_sent", "limit": "1"},
        )
        if check and check[0].get("welcome_sent") is True:
            return False                # case (a) — genuinely already sent
        log.warning(
            "welcome-email: claim returned empty but profile.welcome_sent is not True for user=%.8s — "
            "likely missing welcome_sent column. Sending anyway (run migration 006).",
            user_id,
        )
        return True                     # case (b) — fall through to Resend
    except Exception as e:
        log.warning(
            "welcome-email: claim write threw for user=%.8s: %s — sending anyway as fallback",
            user_id, e,
        )
        return True                     # network / schema error — don't block UX


def _release_welcome_claim(user_id: str) -> None:
    """Undo a claim after a failed send so a later call can retry. Best-effort."""
    try:
        _supabase.update(
            "user_profiles",
            {"welcome_sent": False},
            params={"id": f"eq.{user_id}"},
        )
    except Exception as e:
        log.info("welcome-email: claim release skipped (non-fatal): %s", e)


@router.post("/welcome-email", summary="Send the welcome email (idempotent)")
def post_welcome_email(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Triggered by the frontend right after onboarding completes.

    Idempotency: enforced by an atomic claim (see _claim_welcome). The first
    caller to flip welcome_sent wins and sends; everyone else gets
    {"sent": false, "reason": "already_sent"} without contacting Resend.
    Safe to call any number of times, concurrently.

    Failure modes (all return 2xx — never block UX):
      - RESEND_API_KEY missing            → {"sent": false, "reason": "send_failed"}
      - Resend API call fails             → {"sent": false, "reason": "send_failed"}
      - user has no email (shouldn't happen with Google OAuth) → 400
    """
    if not user.email:
        raise HTTPException(
            status_code=400,
            detail="Cannot send welcome email — no email on account.",
        )

    profile = _profile(user.id)

    # Fast path: already sent on an earlier call — skip the write and Resend.
    # (Every later sign-in re-hits this endpoint; this avoids a pointless PATCH.)
    if profile.get("welcome_sent") is True:
        log.info("welcome-email: already sent for user=%.8s — skipping", user.id)
        return {"sent": False, "reason": "already_sent"}

    # Atomic claim — only the winner of the race may contact Resend.
    if not _claim_welcome(user.id):
        log.info("welcome-email: claim lost (concurrent send) for user=%.8s", user.id)
        return {"sent": False, "reason": "already_sent"}

    name = profile.get("name") or ""
    if not name:
        # Fall back to Google profile name from the JWT claims.
        meta = (user.raw_claims or {}).get("user_metadata") or {}
        name = meta.get("full_name") or meta.get("name") or ""

    ok = send_welcome(to_email=user.email, name=name)
    if ok:
        return {"sent": True}

    # Send failed after we claimed — release so a later call can retry.
    _release_welcome_claim(user.id)
    return {"sent": False, "reason": "send_failed"}
