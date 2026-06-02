"""Subscription state: read/write the public.subscriptions table.

Public surface:
  - get_active_subscription(user_id) -> dict | None
  - change_plan(user_id, plan, ...)  -> dict   (manual upgrade / admin grant)
  - cancel_subscription(user_id)     -> dict
  - check_and_expire(sub)            -> dict   (auto-downgrade if expired)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from headnote import config
from headnote.entitlements import _supabase
from headnote.entitlements.auth import current_user_email
from headnote.entitlements.plans import PLANS, get_plan


log = logging.getLogger(__name__)


def _synthetic_sub(user_id: str, plan: str) -> dict:
    """Synthetic founder/partner subscription — never persisted, never
    expires. Returned in place of the DB row when the request's email is
    in the hardcoded config whitelists OR the access_grants table."""
    now = datetime.now(timezone.utc)
    duration = PLANS.get(plan, PLANS["founder"]).duration_days
    far_future = now + timedelta(days=duration)
    return {
        "user_id": user_id,
        "plan": plan,
        "status": "active",
        "period_start": now.isoformat(),
        "period_end": far_future.isoformat(),
        "payment_provider": f"{plan}_grant",
        "payment_ref": None,
        "weekly_trial_used": False,
        "cancelled_at": None,
    }


def _founder_sub(user_id: str) -> dict:
    """Back-compat alias — some callers still import this name."""
    return _synthetic_sub(user_id, "founder")


def _activate_paid_grant(user_id: str, plan: str) -> Optional[dict]:
    """One-shot activation of a time-limited comp grant.

    Creates a REAL Supabase `subscriptions` row for `user_id` with the given
    plan and a period_end = now + PLANS[plan].duration_days. After this fires,
    the user has a normal paid-plan subscription that expires on schedule
    (no perpetual access — this is the difference vs founder/partner).

    Returns None (skips activation) if the user already has an active paid
    plan — they don't need the comp; the caller still marks the grant
    consumed so it doesn't keep checking on every sign-in.
    """
    p = PLANS.get(plan)
    if not p:
        return None

    # Skip if user already has a non-demo active subscription.
    try:
        existing = _supabase.select(
            "subscriptions",
            params={"user_id": f"eq.{user_id}", "select": "plan,status", "limit": "1"},
        )
        if existing and existing[0].get("status") == "active":
            cur_plan = existing[0].get("plan")
            if cur_plan in ("weekly", "monthly", "yearly", "founder", "partner"):
                return None
    except Exception:
        # Best-effort check; on any error, proceed with activation rather
        # than silently swallow the grant.
        pass

    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "plan": plan,
        "status": "active",
        "period_start": now.isoformat(),
        "period_end": (now + timedelta(days=p.duration_days)).isoformat(),
        "payment_provider": f"{plan}_comp_grant",
        "weekly_trial_used": False,
        "cancelled_at": None,
    }
    try:
        result = _supabase.upsert("subscriptions", payload, on_conflict="user_id")
        return result[0] if result else payload
    except Exception:
        return None


def get_active_subscription(user_id: str, email: str | None = None) -> dict | None:
    """Return the user's current subscription row, auto-downgrading to Demo
    if the previous plan has expired.

    If no row exists at all (first call, trigger hasn't fired yet), creates
    a Demo row idempotently.

    Founder bypass: if the email (passed explicitly OR read from contextvar)
    is in config.FOUNDER_EMAILS, returns a synthetic founder sub without
    touching the DB. Side effect: founder usage is NOT metered.

    NOTE: the contextvar set by get_current_user does NOT survive across
    sync-dependency → async-endpoint boundaries because FastAPI runs sync
    deps in a thread pool with a copied context. So callers from async
    endpoints MUST pass email= explicitly. Falling back to contextvar for
    sync endpoints that still rely on it.
    """
    if email is None:
        email = current_user_email.get()
    # Resolution order (most-trusted first):
    #   1. hardcoded FOUNDER_EMAILS    → perpetual synthetic founder sub
    #   2. hardcoded PARTNER_EMAILS    → perpetual synthetic partner sub
    #   3. DB founder/partner grant    → perpetual synthetic sub
    #   4. unconsumed yearly/monthly comp (hardcoded OR DB)
    #        → ACTIVATE: create a real Supabase subscription, mark consumed
    #   5. actual subscriptions row    → user's bought plan
    if email:
        e = email.lower()
        if e in config.FOUNDER_EMAILS:
            return _synthetic_sub(user_id, "founder")
        if e in config.PARTNER_EMAILS:
            return _synthetic_sub(user_id, "partner")
        try:
            from headnote.entitlements import grants as _grants
            role = _grants.get_role(e)
            if role in ("founder", "partner"):
                return _synthetic_sub(user_id, role)

            # Time-limited comp grants — one-shot activation to a real sub.
            if not _grants.is_consumed(e):
                comp_plan = None
                if e in config.YEARLY_GRANT_EMAILS:
                    comp_plan = "yearly"
                elif e in config.MONTHLY_GRANT_EMAILS:
                    comp_plan = "monthly"
                elif role in ("yearly", "monthly"):
                    comp_plan = role
                if comp_plan:
                    sub = _activate_paid_grant(user_id, comp_plan)
                    if sub is not None:
                        _grants.mark_consumed(e, comp_plan, user_id)
                        # DB grant rows are one-shot — delete after activation.
                        if role in ("yearly", "monthly"):
                            _grants.remove_grant(e)
                        return sub
                    # _activate_paid_grant returned None — user already has
                    # an active paid plan; mark consumed anyway so we don't
                    # keep checking, and fall through to the DB lookup.
                    _grants.mark_consumed(e, comp_plan, user_id)
                    if role in ("yearly", "monthly"):
                        _grants.remove_grant(e)
        except Exception:
            pass

    rows = _supabase.select(
        "subscriptions",
        params={"user_id": f"eq.{user_id}", "select": "*", "limit": "1"},
    )
    if not rows:
        # Auto-create Demo row. Trigger may not have fired in dev.
        return _create_demo(user_id)
    sub = rows[0]
    return _check_and_expire(sub)


def _create_demo(user_id: str) -> dict:
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "plan": "demo",
        "status": "active",
        "period_start": now.isoformat(),
        "period_end": (now + timedelta(days=PLANS["demo"].duration_days)).isoformat(),
    }
    result = _supabase.upsert("subscriptions", payload, on_conflict="user_id")
    return result[0] if result else payload


def _check_and_expire(sub: dict) -> dict:
    """If subscription period_end has passed, mark as expired and downgrade
    to Demo (with a fresh 14-day window so the user can re-evaluate)."""
    if sub.get("status") != "active":
        return sub
    period_end = _parse_ts(sub.get("period_end"))
    if not period_end or period_end > datetime.now(timezone.utc):
        return sub

    # Expired. Downgrade to Demo.
    if sub.get("plan") == "demo":
        # Demo already, just extend the window so the user keeps a usable trial
        # (their lifetime quotas are already consumed; this only resets day-window).
        new_end = datetime.now(timezone.utc) + timedelta(days=14)
        update = {
            "period_start": datetime.now(timezone.utc).isoformat(),
            "period_end": new_end.isoformat(),
        }
    else:
        update = {
            "plan": "demo",
            "status": "active",
            "period_start": datetime.now(timezone.utc).isoformat(),
            "period_end": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(),
        }
    _supabase.update(
        "subscriptions", update,
        params={"user_id": f"eq.{sub['user_id']}"},
    )
    sub.update(update)
    return sub


def change_plan(
    user_id: str,
    plan: str,
    *,
    duration_days: Optional[int] = None,
    payment_provider: Optional[str] = None,
    payment_ref: Optional[str] = None,
    granted_by_admin: bool = False,
) -> dict:
    """Upgrade/downgrade a user to `plan`. Resets the period window.

    Side effects:
      - Sets period_end = now + plan.duration_days (override with `duration_days`)
      - If plan='weekly', flips weekly_trial_used=true (prevents repurchase)
      - Clears usage meters for the old plan (caller decides; not done here)
    """
    p = get_plan(plan)
    days = duration_days or p.duration_days
    now = datetime.now(timezone.utc)
    payload: dict = {
        "plan": plan,
        "status": "active",
        "period_start": now.isoformat(),
        "period_end": (now + timedelta(days=days)).isoformat(),
        "payment_provider": payment_provider,
        "payment_ref": payment_ref,
        "cancelled_at": None,
        "updated_at": now.isoformat(),
    }
    if plan == "weekly":
        payload["weekly_trial_used"] = True
    result = _supabase.update(
        "subscriptions", payload,
        params={"user_id": f"eq.{user_id}"},
    )
    log.info("change_plan user=%s -> plan=%s by_admin=%s", user_id, plan, granted_by_admin)
    return result[0] if result else payload


def cancel_subscription(user_id: str) -> dict:
    """Mark subscription as cancelled. User keeps access until period_end,
    then auto-downgrades to Demo via _check_and_expire."""
    now = datetime.now(timezone.utc).isoformat()
    payload = {"status": "cancelled", "cancelled_at": now, "updated_at": now}
    result = _supabase.update(
        "subscriptions", payload,
        params={"user_id": f"eq.{user_id}"},
    )
    return result[0] if result else payload


def has_used_weekly_trial(user_id: str) -> bool:
    sub = get_active_subscription(user_id)
    return bool(sub and sub.get("weekly_trial_used"))


def is_admin(user_id: str) -> bool:
    """Check whether the user has an admin_users row."""
    rows = _supabase.select(
        "admin_users",
        params={"user_id": f"eq.{user_id}", "select": "role", "limit": "1"},
    )
    return bool(rows)


# ---------------------------------------------------------------- add-ons

# Subscription tiers that bundle the Section-Finder premium view for free.
_SECTIONS_BUNDLED_PLANS = ("monthly", "yearly", "founder", "partner")


def has_sections_unlock(user_id: str) -> bool:
    """True iff the user bought the one-time, lifetime Section-Finder unlock.

    Reads public.sections_unlocks. Fail-safe: returns False when the table is
    absent or Supabase is unreachable (the _supabase wrapper swallows HTTP
    errors and returns []), so this never 500s the entitlement check.
    """
    if not user_id:
        return False
    try:
        rows = _supabase.select(
            "sections_unlocks",
            params={"user_id": f"eq.{user_id}", "select": "user_id", "limit": "1"},
        )
        return bool(rows)
    except Exception:
        return False


def has_sections_pro(user_id: str, plan_name: str | None) -> bool:
    """Whether the Section-Finder premium view is unlocked for this user —
    either bundled with their subscription tier, or bought as the ₹99 add-on."""
    if plan_name in _SECTIONS_BUNDLED_PLANS:
        return True
    return has_sections_unlock(user_id)


# ---------------------------------------------------------------- helpers

def _parse_ts(s: Optional[str]) -> datetime | None:
    if not s:
        return None
    try:
        # Supabase returns ISO with offset; handle +00:00 and trailing Z.
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
