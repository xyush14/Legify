"""Plan definitions: limits, pricing, feature flags.

The single source of truth for what each tier gets. The /api/me endpoint
exposes the relevant slice of this to the frontend so the UI can decide
what to gate without duplicating the rules.

Period semantics
----------------
- "lifetime"  : never resets. Used for Demo. Reset only on plan upgrade.
- "day"       : resets at UTC midnight.
- "week"      : ISO week (YYYY-Www), resets Monday 00:00 UTC.
- "month"     : YYYY-MM, resets on 1st of month UTC.
- "year"      : YYYY, resets Jan 1 UTC.

When a user upgrades plan, all meters for the previous plan are cleared
(see subscription.change_plan).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


PlanName = Literal["demo", "weekly", "monthly", "yearly"]
Period = Literal["lifetime", "day", "week", "month", "year"]


@dataclass(frozen=True)
class PlanLimit:
    """A single feature limit on a plan. None = unlimited."""
    feature: str
    limit: int | None              # None = unlimited (no gate, no metering)
    period: Period
    soft_cap: int | None = None    # past this, downgrade Sonnet → Haiku (drafts only)


@dataclass(frozen=True)
class Plan:
    """A subscription tier."""
    name: PlanName
    display_name: str
    price_inr: int
    duration_days: int
    first_time_only: bool = False    # Weekly tier: can only buy once
    limits: list[PlanLimit] = field(default_factory=list)
    features: dict[str, bool | str] = field(default_factory=dict)


# ---------------------------------------------------------------- Plan definitions

# Features (string-keyed bool/enum flags). Centralised here so frontend stays in sync.
#   export_pdf       : can download English PDF of drafts / digests
#   hindi_export     : can export Hindi PDF
#   history          : "session" | "7_days" | "unlimited"
#   support          : "docs" | "email" | "whatsapp"
#   custom_letterhead: Yearly-only branding upload
#   priority_queue   : Yearly-only LLM queue priority


DEMO = Plan(
    name="demo",
    display_name="Demo",
    price_inr=0,
    duration_days=14,
    limits=[
        PlanLimit("deep_search",   3,    "lifetime"),
        PlanLimit("draft",         2,    "lifetime"),
        PlanLimit("judgment_read", 10,   "day"),
        PlanLimit("export_pdf",    0,    "lifetime"),  # gated, count always 0
        PlanLimit("hindi_export",  0,    "lifetime"),
    ],
    features={
        "export_pdf":        False,
        "hindi_export":      False,
        "history":           "session",
        "support":           "docs",
        "custom_letterhead": False,
        "priority_queue":    False,
    },
)


WEEKLY = Plan(
    name="weekly",
    display_name="Weekly Trial",
    price_inr=120,
    duration_days=7,
    first_time_only=True,
    limits=[
        PlanLimit("deep_search",   15,   "week"),
        PlanLimit("draft",         30,   "week"),
        PlanLimit("judgment_read", None, "week"),   # unlimited
        PlanLimit("export_pdf",    None, "week"),
        PlanLimit("hindi_export",  0,    "week"),    # still gated
    ],
    features={
        "export_pdf":        True,
        "hindi_export":      False,
        "history":           "7_days",
        "support":           "email",
        "custom_letterhead": False,
        "priority_queue":    False,
    },
)


MONTHLY = Plan(
    name="monthly",
    display_name="Monthly",
    price_inr=499,
    duration_days=30,
    limits=[
        PlanLimit("deep_search",   100,  "month"),
        PlanLimit("draft",         None, "month",  soft_cap=80),  # >80 = silent Haiku downgrade
        PlanLimit("judgment_read", None, "month"),
        PlanLimit("export_pdf",    None, "month"),
        PlanLimit("hindi_export",  None, "month"),
    ],
    features={
        "export_pdf":        True,
        "hindi_export":      True,
        "history":           "unlimited",
        "support":           "email",
        "custom_letterhead": False,
        "priority_queue":    False,
    },
)


YEARLY = Plan(
    name="yearly",
    display_name="Yearly",
    price_inr=4999,
    duration_days=365,
    limits=[
        PlanLimit("deep_search",   1500, "year",  soft_cap=1200),
        PlanLimit("draft",         None, "year",  soft_cap=1000),
        PlanLimit("judgment_read", None, "year"),
        PlanLimit("export_pdf",    None, "year"),
        PlanLimit("hindi_export",  None, "year"),
    ],
    features={
        "export_pdf":        True,
        "hindi_export":      True,
        "history":           "unlimited",
        "support":           "whatsapp",
        "custom_letterhead": True,
        "priority_queue":    True,
    },
)


PLANS: dict[str, Plan] = {
    "demo":    DEMO,
    "weekly":  WEEKLY,
    "monthly": MONTHLY,
    "yearly":  YEARLY,
}


def get_plan(name: str) -> Plan:
    """Look up a plan by name. Falls back to Demo on unknown name (defensive)."""
    return PLANS.get(name, DEMO)


def get_limit(plan_name: str, feature: str) -> PlanLimit | None:
    """Find the limit row for (plan, feature). Returns None if the feature is
    not listed on the plan (treated as "not gated, unlimited use")."""
    plan = get_plan(plan_name)
    for lim in plan.limits:
        if lim.feature == feature:
            return lim
    return None


def is_feature_unlocked(plan_name: str, feature: str) -> bool:
    """Quick check for boolean feature flags (export_pdf, hindi_export, etc.)."""
    plan = get_plan(plan_name)
    val = plan.features.get(feature)
    return bool(val)


def period_key_for(period: Period, now=None) -> str:
    """Bucket key used in usage_meters.period_key. Same period_key under the
    same period type means "same bucket" (so the counter increments)."""
    from datetime import datetime, timezone
    now = now or datetime.now(timezone.utc)
    if period == "lifetime":
        return "lifetime"
    if period == "day":
        return now.strftime("%Y-%m-%d")
    if period == "week":
        # ISO week: 2026-W21
        iso = now.isocalendar()
        return f"{iso.year}-W{iso.week:02d}"
    if period == "month":
        return now.strftime("%Y-%m")
    if period == "year":
        return now.strftime("%Y")
    return "lifetime"
