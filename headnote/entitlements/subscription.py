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


def _founder_sub(user_id: str) -> dict:
    """Synthetic founder subscription — never persisted, never expires.
    Returned in place of the DB row when the request's email is in
    config.FOUNDER_EMAILS."""
    now = datetime.now(timezone.utc)
    far_future = now + timedelta(days=PLANS["founder"].duration_days)
    return {
        "user_id": user_id,
        "plan": "founder",
        "status": "active",
        "period_start": now.isoformat(),
        "period_end": far_future.isoformat(),
        "payment_provider": "founder_grant",
        "payment_ref": None,
        "weekly_trial_used": False,
        "cancelled_at": None,
    }


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
    if email and email.lower() in config.FOUNDER_EMAILS:
        return _founder_sub(user_id)

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
