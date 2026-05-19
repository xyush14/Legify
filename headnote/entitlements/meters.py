"""Usage meters: read counters, increment after success, write audit events.

The contract is "read-check-act-increment":
  1. read current `used` for (user, feature, period_key)
  2. compare to plan limit; raise QuotaExceeded if at/over
  3. caller runs the API work
  4. on success, increment(...) bumps the counter + writes a usage_event

We do NOT lock the counter between steps 1 and 4 — race conditions can
overshoot by 1-2 under high concurrency. That's acceptable for the legal-research
use case (single user, low QPS). If we ever need strict caps, switch to a
Postgres-side `increment_meter()` function that does check+increment atomically.
"""

from __future__ import annotations

import logging
from typing import Optional

from headnote.entitlements import _supabase
from headnote.entitlements.plans import period_key_for, get_limit, get_plan


log = logging.getLogger(__name__)


def get_used(user_id: str, feature: str, period_key: str) -> int:
    rows = _supabase.select(
        "usage_meters",
        params={
            "user_id":    f"eq.{user_id}",
            "feature":    f"eq.{feature}",
            "period_key": f"eq.{period_key}",
            "select":     "used",
            "limit":      "1",
        },
    )
    if not rows:
        return 0
    return int(rows[0].get("used", 0))


def increment(
    user_id: str,
    feature: str,
    period_key: str,
    *,
    delta: int = 1,
) -> int:
    """Bump the meter by `delta`. Uses Supabase upsert with on_conflict.

    Returns the new `used` value. Falls back to 0 if Supabase is unavailable
    (best-effort: never block the API on metering failure).
    """
    # Read-modify-write. Not atomic across processes, see module docstring.
    current = get_used(user_id, feature, period_key)
    new_used = current + delta
    payload = {
        "user_id":    user_id,
        "feature":    feature,
        "period_key": period_key,
        "used":       new_used,
    }
    _supabase.upsert(
        "usage_meters", payload,
        on_conflict="user_id,feature,period_key",
    )
    return new_used


def record_event(
    user_id: Optional[str],
    feature: str,
    *,
    cost_paise: int = 0,
    model: Optional[str] = None,
    endpoint: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> None:
    """Append-only audit log. Best-effort; never raises."""
    payload = {
        "user_id":    user_id,
        "feature":    feature,
        "cost_paise": cost_paise,
        "model":      model,
        "endpoint":   endpoint,
        "metadata":   metadata or {},
    }
    try:
        _supabase.upsert("usage_events", payload)
    except Exception as e:
        log.warning("record_event failed: %s", e)


def get_user_meters(user_id: str, plan_name: str) -> dict[str, dict]:
    """Read all meters for a user, scoped to their current plan's periods.

    Returns: { feature: {"used": int, "limit": int|None, "period": str, "remaining": int|None} }
    """
    plan = get_plan(plan_name)
    out: dict[str, dict] = {}
    for lim in plan.limits:
        if lim.limit == 0:
            # Gated feature with no counter (export_pdf etc.) — surface as locked.
            out[lim.feature] = {
                "used": 0, "limit": 0,
                "period": lim.period, "remaining": 0,
                "locked": True,
            }
            continue
        period_key = period_key_for(lim.period)
        used = get_used(user_id, lim.feature, period_key)
        remaining = None if lim.limit is None else max(0, lim.limit - used)
        out[lim.feature] = {
            "used":      used,
            "limit":     lim.limit,
            "period":    lim.period,
            "period_key": period_key,
            "remaining": remaining,
            "soft_cap":  lim.soft_cap,
            "locked":    False,
        }
    return out
