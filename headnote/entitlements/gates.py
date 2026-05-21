"""Gate functions: the pre-call check + post-call increment.

API endpoints use this pattern:

    from headnote.entitlements import check_and_record, get_current_user

    @router.post("/api/situation")
    def api_situation(
        body: SomeModel,
        user: CurrentUser = Depends(get_current_user),
    ):
        with check_and_record(user.id, "deep_search", endpoint="situation") as record:
            result = do_the_work(body)
            record(cost_paise=result.meta["cost_paise"], model=result.meta["model"])
            return result

The context manager:
  - reads current usage, checks against plan limit
  - raises QuotaExceeded (mapped to 402) if exhausted
  - on `__exit__` (no exception), increments the meter and writes the event

If you want JUST the gate check without metering (e.g. to decide whether to
show a feature in the UI), use `can_use_feature(user_id, feature)`.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Callable, Optional

from fastapi import HTTPException, status

from headnote.entitlements import meters
from headnote.entitlements.plans import get_limit, is_feature_unlocked, period_key_for
from headnote.entitlements.subscription import get_active_subscription


log = logging.getLogger(__name__)


# ---------------------------------------------------------------- exceptions

class QuotaExceeded(HTTPException):
    """Raised when a user has hit their plan's limit for a feature."""

    def __init__(self, feature: str, plan: str, used: int, limit: int):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code":    "quota_exceeded",
                "feature": feature,
                "plan":    plan,
                "used":    used,
                "limit":   limit,
                "message": _quota_msg(feature, plan, used, limit),
                "upgrade_to": _suggest_upgrade(plan),
            },
        )


class FeatureLocked(HTTPException):
    """Raised when a feature is not available on the current plan at all."""

    def __init__(self, feature: str, plan: str):
        super().__init__(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "code":    "feature_locked",
                "feature": feature,
                "plan":    plan,
                "message": _locked_msg(feature, plan),
                "upgrade_to": _suggest_upgrade(plan, for_feature=feature),
            },
        )


# ---------------------------------------------------------------- checks

def can_use_feature(user_id: str, feature: str, email: str | None = None) -> dict:
    """Read-only check: can this user use `feature` right now?

    Returns:
        {"allowed": bool, "reason": str|None, "used": int, "limit": int|None,
         "plan": str, "use_haiku": bool}

    `use_haiku=True` signals the soft-cap was crossed — caller should
    downgrade Sonnet→Haiku for the model call.

    Pass email= from CurrentUser to ensure the founder bypass kicks in
    even when called from async endpoints (where the contextvar set by
    get_current_user doesn't propagate).
    """
    sub = get_active_subscription(user_id, email=email) or {}
    plan = sub.get("plan", "demo")

    lim = get_limit(plan, feature)
    if lim is None:
        # Feature not listed on plan → treat as unlimited (no gate).
        return {"allowed": True, "reason": None, "used": 0, "limit": None,
                "plan": plan, "use_haiku": False, "remaining": None}

    if lim.limit == 0:
        # Explicitly locked (e.g. hindi_export on Demo).
        return {"allowed": False, "reason": "feature_locked", "used": 0,
                "limit": 0, "plan": plan, "use_haiku": False, "remaining": 0}

    if lim.limit is None:
        # Unlimited, but soft_cap may apply.
        used = meters.get_used(user_id, feature, period_key_for(lim.period))
        use_haiku = bool(lim.soft_cap and used >= lim.soft_cap)
        return {"allowed": True, "reason": None, "used": used, "limit": None,
                "plan": plan, "use_haiku": use_haiku, "remaining": None}

    used = meters.get_used(user_id, feature, period_key_for(lim.period))
    remaining = max(0, lim.limit - used)
    if used >= lim.limit:
        return {"allowed": False, "reason": "quota_exceeded", "used": used,
                "limit": lim.limit, "plan": plan, "use_haiku": False,
                "remaining": 0}

    # Soft cap check (drafts on Monthly cross 80 → Haiku downgrade)
    use_haiku = bool(lim.soft_cap and used >= lim.soft_cap)
    return {"allowed": True, "reason": None, "used": used, "limit": lim.limit,
            "plan": plan, "use_haiku": use_haiku, "remaining": remaining}


def require_feature(user_id: str, feature: str) -> None:
    """Raise FeatureLocked if `feature` isn't unlocked on this user's plan.

    Use for boolean features (export_pdf, hindi_export) that don't have
    a numeric limit. Idempotent — does not increment any counter.
    """
    sub = get_active_subscription(user_id) or {}
    plan = sub.get("plan", "demo")
    if not is_feature_unlocked(plan, feature):
        raise FeatureLocked(feature, plan)


# ---------------------------------------------------------------- combined manager

@contextmanager
def check_and_record(
    user_id: str,
    feature: str,
    *,
    endpoint: Optional[str] = None,
    email: Optional[str] = None,
):
    """Gate + meter context manager.

    On entry:
      - resolves the user's plan + limit for `feature`
      - if at/over limit, raises QuotaExceeded
      - exposes a `record(...)` callable inside the block

    On exit (no exception):
      - increments the meter
      - records a usage_event row (if `record` was called with cost details)

    Pass email= from CurrentUser so the founder bypass works in async
    endpoints (the contextvar set by get_current_user doesn't propagate
    from sync deps into async handlers via FastAPI's thread pool).
    """
    check = can_use_feature(user_id, feature, email=email)
    if not check["allowed"]:
        if check["reason"] == "feature_locked":
            raise FeatureLocked(feature, check["plan"])
        raise QuotaExceeded(
            feature, check["plan"], check["used"], check["limit"] or 0,
        )

    event_data = {"cost_paise": 0, "model": None}

    def record(cost_paise: int = 0, model: Optional[str] = None) -> None:
        event_data["cost_paise"] = int(cost_paise)
        event_data["model"] = model

    # Expose use_haiku flag too for caller to inspect
    yield record

    # Success path — increment.
    plan_name = check["plan"]
    lim = get_limit(plan_name, feature)
    if lim is None or lim.limit == 0:
        # Untracked / locked feature — record event only.
        meters.record_event(
            user_id, feature,
            cost_paise=event_data["cost_paise"],
            model=event_data["model"],
            endpoint=endpoint,
        )
        return

    period_key = period_key_for(lim.period)
    try:
        meters.increment(user_id, feature, period_key)
    except Exception as e:
        log.warning("meter increment failed user=%s feature=%s: %s", user_id, feature, e)

    meters.record_event(
        user_id, feature,
        cost_paise=event_data["cost_paise"],
        model=event_data["model"],
        endpoint=endpoint,
    )


# ---------------------------------------------------------------- messages

def _quota_msg(feature: str, plan: str, used: int, limit: int) -> str:
    feature_display = {
        "deep_search":   "Deep Search",
        "draft":         "drafting",
        "judgment_read": "Judgment reads",
        "export_pdf":    "PDF export",
        "hindi_export":  "Hindi PDF export",
    }.get(feature, feature)
    return (
        f"You've used {used}/{limit} {feature_display} for the current period on the "
        f"{plan.capitalize()} plan. Upgrade for more."
    )


def _locked_msg(feature: str, plan: str) -> str:
    feature_display = {
        "export_pdf":    "PDF export",
        "hindi_export":  "Hindi PDF export",
    }.get(feature, feature)
    return f"{feature_display} is not available on the {plan.capitalize()} plan. Upgrade to unlock."


def _suggest_upgrade(current_plan: str, *, for_feature: Optional[str] = None) -> str:
    """Suggest the cheapest plan that unlocks `for_feature`, or the next tier up."""
    if for_feature == "hindi_export":
        return "monthly"
    if current_plan == "demo":
        return "weekly"
    if current_plan == "weekly":
        return "monthly"
    if current_plan == "monthly":
        return "yearly"
    return "yearly"
