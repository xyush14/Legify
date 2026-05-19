"""Admin v2: user/subscription management endpoints.

These supplement the bearer-token-guarded admin.py with user-facing admin
flows. Auth is dual-mode:
  - either Authorization: Bearer <ADMIN_TOKEN>  (legacy, ops scripts)
  - or a Supabase JWT for a user listed in public.admin_users (UI flow)

Endpoints:
  GET    /admin/v2/users                    List users + their subscription
  GET    /admin/v2/users/{user_id}          One user's full state
  POST   /admin/v2/users/{user_id}/grant    Manually upgrade a user to a plan
  POST   /admin/v2/users/{user_id}/cancel   Cancel a user's subscription
  GET    /admin/v2/usage                    Aggregate usage stats (7/30/90 days)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from headnote import config
from headnote.entitlements import _supabase
from headnote.entitlements.auth import optional_user
from headnote.entitlements.plans import PLANS
from headnote.entitlements.state import get_user_state
from headnote.entitlements.subscription import change_plan, cancel_subscription, is_admin


router = APIRouter(prefix="/admin/v2", tags=["admin"])


# ---------------------------------------------------------------- dual auth

def _admin_guard(
    authorization: Optional[str] = Header(default=None),
    user=Depends(optional_user),
) -> str:
    """Allow either Bearer ADMIN_TOKEN OR a JWT for an admin_users row.

    Returns the actor id (admin user id, or 'ops' for token-based access).
    """
    # Bearer ADMIN_TOKEN path
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1].strip()
        if config.ADMIN_TOKEN and token == config.ADMIN_TOKEN:
            return "ops"
    # JWT path
    if user and is_admin(user.id):
        return user.id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required.",
    )


# ---------------------------------------------------------------- models

class GrantRequest(BaseModel):
    plan: str
    duration_days: Optional[int] = None
    note: Optional[str] = None


# ---------------------------------------------------------------- endpoints

@router.get("/users", summary="List users + their subscriptions")
def list_users(
    actor: str = Depends(_admin_guard),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    plan: Optional[str] = Query(None, description="Filter to one plan"),
) -> dict:
    """Returns a paginated list of users with subscription state and recent usage.

    Combines auth.users (via Supabase admin API) with subscriptions table.
    """
    params: dict[str, str] = {
        "select":  "*",
        "order":   "updated_at.desc",
        "limit":   str(limit),
        "offset":  str(offset),
    }
    if plan:
        params["plan"] = f"eq.{plan}"

    subs = _supabase.select("subscriptions", params=params)
    return {"users": subs, "count": len(subs)}


@router.get("/users/{user_id}", summary="Full state for one user")
def get_user(user_id: str, actor: str = Depends(_admin_guard)) -> dict:
    state = get_user_state(user_id)

    # Last 50 events for context
    events = _supabase.select(
        "usage_events",
        params={
            "user_id": f"eq.{user_id}",
            "select":  "*",
            "order":   "created_at.desc",
            "limit":   "50",
        },
    )
    state["recent_events"] = events
    return state


@router.post("/users/{user_id}/grant", summary="Manually upgrade a user")
def grant_plan(
    user_id: str,
    body: GrantRequest,
    actor: str = Depends(_admin_guard),
) -> dict:
    if body.plan not in PLANS:
        raise HTTPException(400, f"Unknown plan: {body.plan}")
    updated = change_plan(
        user_id,
        body.plan,
        duration_days=body.duration_days,
        payment_provider="manual",
        payment_ref=f"granted_by:{actor}",
        granted_by_admin=True,
    )
    return {"ok": True, "subscription": updated, "granted_by": actor}


@router.post("/users/{user_id}/cancel", summary="Cancel a user's subscription")
def cancel_user(user_id: str, actor: str = Depends(_admin_guard)) -> dict:
    sub = cancel_subscription(user_id)
    return {"ok": True, "subscription": sub, "cancelled_by": actor}


@router.get("/usage", summary="Aggregate usage stats")
def aggregate_usage(
    actor: str = Depends(_admin_guard),
    days: int = Query(7, ge=1, le=90),
) -> dict:
    """Returns per-feature totals + per-user top consumers."""
    from datetime import datetime, timezone, timedelta

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    events = _supabase.select(
        "usage_events",
        params={
            "select":     "user_id,feature,cost_paise,model",
            "created_at": f"gte.{since}",
            "limit":      "5000",
        },
    )

    by_feature: dict[str, dict] = {}
    by_user: dict[str, int] = {}
    total_paise = 0
    for ev in events:
        f = ev.get("feature", "?")
        c = int(ev.get("cost_paise", 0) or 0)
        total_paise += c
        bf = by_feature.setdefault(f, {"calls": 0, "cost_paise": 0})
        bf["calls"] += 1
        bf["cost_paise"] += c
        if ev.get("user_id"):
            by_user[ev["user_id"]] = by_user.get(ev["user_id"], 0) + c

    top_users = sorted(by_user.items(), key=lambda x: -x[1])[:20]

    return {
        "window_days":     days,
        "total_calls":     len(events),
        "total_cost_inr":  round(total_paise / 100, 2),
        "by_feature":      by_feature,
        "top_users":       [{"user_id": u, "cost_paise": c} for u, c in top_users],
    }
