"""Headnote subscription + entitlements layer.

Public surface used by API endpoints:
  - get_current_user(...)  : FastAPI dependency, verifies Supabase JWT
  - check_and_record(...)  : combined gate + meter increment
  - require_feature(...)   : decorator-style gate for boolean features
  - get_user_state(...)    : returns plan + remaining quotas (for /api/me)

Internal modules:
  - plans       : tier definitions (Demo / Weekly / Monthly / Yearly)
  - auth        : JWT verification helpers
  - subscription: Supabase reads/writes for subscriptions table
  - meters      : usage tracking
  - gates       : pre-call limit checks
"""

from headnote.entitlements.auth import get_current_user, optional_user, CurrentUser
from headnote.entitlements.gates import (
    check_and_record,
    require_feature,
    QuotaExceeded,
    FeatureLocked,
)
from headnote.entitlements.plans import PLANS, PlanLimit, get_plan
from headnote.entitlements.state import get_user_state

__all__ = [
    "get_current_user",
    "optional_user",
    "CurrentUser",
    "check_and_record",
    "require_feature",
    "QuotaExceeded",
    "FeatureLocked",
    "PLANS",
    "PlanLimit",
    "get_plan",
    "get_user_state",
]
