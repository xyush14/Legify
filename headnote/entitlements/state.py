"""User state aggregator: feeds /api/me — the single endpoint the frontend
calls to learn what plan the user is on, what they've used, and what's locked.

Shape returned (stable, breaks frontend if changed):

{
  "user": {"id": "...", "email": "..."},
  "is_admin": false,
  "subscription": {
    "plan": "monthly",
    "display_name": "Monthly",
    "status": "active",
    "period_start": "2026-05-19T...",
    "period_end":   "2026-06-19T...",
    "weekly_trial_used": false,
    "price_inr": 499,
  },
  "limits": {
    "deep_search":   {"used": 7, "limit": 100, "period": "month", "remaining": 93, "locked": false},
    "draft":         {"used": 12, "limit": null, "period": "month", "remaining": null, "locked": false},
    "judgment_read": {"used": 4, "limit": null, "period": "month", "remaining": null, "locked": false},
    "export_pdf":    {"used": 0, "limit": null, "period": "month", "remaining": null, "locked": false},
    "hindi_export":  {"used": 0, "limit": null, "period": "month", "remaining": null, "locked": false},
  },
  "features": {
    "export_pdf": true, "hindi_export": true, "history": "unlimited",
    "support": "email", "custom_letterhead": false, "priority_queue": false,
  },
  "available_upgrades": ["yearly"],
}
"""

from __future__ import annotations

from headnote.entitlements.meters import get_user_meters
from headnote.entitlements.plans import PLANS, get_plan
from headnote.entitlements.subscription import get_active_subscription, is_admin


def get_user_state(user_id: str, email: str | None = None) -> dict:
    sub = get_active_subscription(user_id) or {}
    plan_name = sub.get("plan", "demo")
    plan = get_plan(plan_name)

    return {
        "user": {"id": user_id, "email": email},
        "is_admin": is_admin(user_id),
        "subscription": {
            "plan":              plan_name,
            "display_name":      plan.display_name,
            "status":            sub.get("status", "active"),
            "period_start":      sub.get("period_start"),
            "period_end":        sub.get("period_end"),
            "weekly_trial_used": bool(sub.get("weekly_trial_used")),
            "price_inr":         plan.price_inr,
        },
        "limits":   get_user_meters(user_id, plan_name),
        "features": dict(plan.features),
        "available_upgrades": _available_upgrades(plan_name, bool(sub.get("weekly_trial_used"))),
    }


def _available_upgrades(current: str, weekly_used: bool) -> list[str]:
    """Which paid plans can this user buy right now?

    Weekly is suppressed if already used. Current plan + lower plans are excluded.
    """
    ladder = ["demo", "weekly", "monthly", "yearly"]
    try:
        idx = ladder.index(current)
    except ValueError:
        idx = 0
    out = [p for p in ladder[idx + 1:]]
    if weekly_used and "weekly" in out:
        out.remove("weekly")
    return out
