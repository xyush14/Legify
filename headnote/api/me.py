"""GET /api/me — the frontend's one-stop endpoint for user state.

Returns the user's plan, usage counters, feature flags, and admin status.
The frontend calls this once on app load (after auth) and again whenever
a gated action 402s, so the upgrade modal can show fresh numbers.

Auth: required. Returns 401 if no/invalid Bearer token.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from headnote.entitlements import get_current_user, get_user_state, CurrentUser
from headnote.entitlements.plans import PLANS


router = APIRouter(tags=["entitlements"])


@router.get("/api/me", summary="Current user state (plan, usage, features)")
def get_me(user: CurrentUser = Depends(get_current_user)) -> dict:
    return get_user_state(user.id, email=user.email)


@router.get("/api/plans", summary="Public plan catalogue")
def list_plans() -> dict:
    """Public — returns all plan tiers + their limits + features. Used by
    the pricing page and upgrade modals. No auth required."""
    return {
        "plans": [
            {
                "name":            p.name,
                "display_name":    p.display_name,
                "price_inr":       p.price_inr,
                "duration_days":   p.duration_days,
                "first_time_only": p.first_time_only,
                "limits": [
                    {
                        "feature":  lim.feature,
                        "limit":    lim.limit,
                        "period":   lim.period,
                        "soft_cap": lim.soft_cap,
                    }
                    for lim in p.limits
                ],
                "features": dict(p.features),
            }
            for p in PLANS.values()
        ],
    }
