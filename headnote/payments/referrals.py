"""Referral-code lookup, validation, and event ledger.

Used by the Cashfree payments router to:
  1. validate a code at create-order time (apply discount, stash attribution)
  2. write a referral_events row at webhook PAID time (commission ledger)
  3. expose a public GET /api/payments/validate-referral preview endpoint

Design notes
------------
* Codes are canonicalized to UPPERCASE on lookup. Stored uppercase in the
  table by convention — admins should insert codes uppercase too.
* `commission_pct` is snapshotted from partners.commission_pct at event-write
  time so future rate changes don't retroactively alter historical payouts.
* `applies_to` (first_order | all_orders) is metadata-only in v1; the helper
  applies the discount unconditionally if the code is otherwise valid.
  Enforce it later by checking the user's prior `payments` rows.
* Self-referral guard: the buyer's email must not match the partner's
  contact_email or any partner_employee.email for that code.
"""
from __future__ import annotations

import logging
from typing import Optional

from headnote.entitlements import _supabase

log = logging.getLogger(__name__)


_INVALID = {
    "valid":            False,
    "reason":           "Invalid code.",
    "code":             "",
    "kind":             None,
    "discount_pct":     0.0,
    "commission_pct":   0.0,
    "partner_id":       None,
    "employee_id":      None,
    "publication_name": None,
    "applies_to":       "first_order",
}


def _reject(reason: str) -> dict:
    out = dict(_INVALID)
    out["reason"] = reason
    return out


def canonical(code: str | None) -> str:
    """Trim, uppercase, collapse internal whitespace. Empty -> ''."""
    if not code:
        return ""
    return "".join(code.upper().split())


def lookup_code(code: str | None, buyer_email: str | None) -> dict:
    """Validate a referral code for use by `buyer_email`.

    Returns a dict with `valid: True` and full code/partner info if the code
    can be applied, or `valid: False` with a short user-facing `reason`.

    Never raises — returns `valid=False` on any DB error so a referral lookup
    hiccup never blocks a paid checkout.
    """
    canon = canonical(code)
    if not canon:
        return _reject("No code provided.")

    try:
        # Embed partner + employee in one round-trip via PostgREST resource embedding.
        rows = _supabase.select(
            "referral_codes",
            params={
                "code": f"eq.{canon}",
                "select": (
                    "code,kind,partner_id,employee_id,publication_name,"
                    "discount_pct,applies_to,active,expires_at,"
                    "partners(id,contact_email,commission_pct,status),"
                    "partner_employees(id,email,status)"
                ),
                "limit": "1",
            },
        )
    except Exception as e:
        log.warning("referral lookup failed for code=%s: %s", canon, e)
        return _reject("Could not verify the code right now.")

    if not rows:
        return _reject("Code not recognised.")

    row = rows[0]
    if not row.get("active"):
        return _reject("Code is no longer active.")

    expires_at = row.get("expires_at")
    if expires_at:
        from datetime import datetime, timezone
        try:
            dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if dt < datetime.now(timezone.utc):
                return _reject("Code has expired.")
        except Exception:
            pass  # malformed timestamp -> treat as not expired

    partner = row.get("partners") or {}
    employee = row.get("partner_employees") or {}
    kind = row.get("kind")

    # Distributor partners must still be active for their codes to work.
    if kind == "distributor" and partner.get("status") not in (None, "active"):
        return _reject("This partner code is paused.")

    # Self-referral guard: a user can't redeem a code that belongs to them.
    if buyer_email:
        buyer_norm = buyer_email.strip().lower()
        partner_email = (partner.get("contact_email") or "").strip().lower()
        employee_email = (employee.get("email") or "").strip().lower()
        if buyer_norm and buyer_norm in (partner_email, employee_email):
            return _reject("You cannot use your own referral code.")

    commission_pct = 0.0
    if kind == "distributor":
        # snapshot the partner's current commission rate for the ledger
        try:
            commission_pct = float(partner.get("commission_pct") or 0.0)
        except (TypeError, ValueError):
            commission_pct = 0.0

    try:
        discount_pct = float(row.get("discount_pct") or 0.0)
    except (TypeError, ValueError):
        discount_pct = 0.0

    return {
        "valid":            True,
        "reason":           "",
        "code":             canon,
        "kind":             kind,
        "discount_pct":     discount_pct,
        "commission_pct":   commission_pct,
        "partner_id":       row.get("partner_id"),
        "employee_id":      row.get("employee_id"),
        "publication_name": row.get("publication_name"),
        "applies_to":       row.get("applies_to") or "first_order",
    }


def lookup_code_snapshot(code: str | None) -> dict:
    """Fetch a code's ownership + commission info without validity checks.

    Used by the Cashfree webhook to write a referral_events row even if the
    code has been deactivated between checkout and payment confirmation —
    the sale was made under the code, so the partner still earns.

    Returns the same shape as `lookup_code` with `valid=True` if the row
    exists; otherwise `valid=False`.
    """
    canon = canonical(code)
    if not canon:
        return _reject("No code provided.")
    try:
        rows = _supabase.select(
            "referral_codes",
            params={
                "code": f"eq.{canon}",
                "select": (
                    "code,kind,partner_id,employee_id,publication_name,"
                    "discount_pct,applies_to,"
                    "partners(commission_pct)"
                ),
                "limit": "1",
            },
        )
    except Exception as e:
        log.warning("referral snapshot fetch failed for code=%s: %s", canon, e)
        return _reject("Could not load code.")
    if not rows:
        return _reject("Code not found.")
    row = rows[0]
    partner = row.get("partners") or {}
    try:
        commission_pct = float(partner.get("commission_pct") or 0.0) if row.get("kind") == "distributor" else 0.0
    except (TypeError, ValueError):
        commission_pct = 0.0
    try:
        discount_pct = float(row.get("discount_pct") or 0.0)
    except (TypeError, ValueError):
        discount_pct = 0.0
    return {
        "valid":            True,
        "reason":           "",
        "code":             canon,
        "kind":             row.get("kind"),
        "discount_pct":     discount_pct,
        "commission_pct":   commission_pct,
        "partner_id":       row.get("partner_id"),
        "employee_id":      row.get("employee_id"),
        "publication_name": row.get("publication_name"),
        "applies_to":       row.get("applies_to") or "first_order",
    }


def apply_discount(gross_inr: int, discount_pct: float) -> tuple[int, int]:
    """Given the list-price amount and a discount percentage, return
    (net_amount_inr, discount_amount_inr) — both whole rupees, rounded.

    Cashfree's order_amount is float-INR but we keep our internal numbers
    in whole rupees to avoid float drift in the ledger. Net is always >= 1.
    """
    if discount_pct <= 0:
        return gross_inr, 0
    discount_pct = max(0.0, min(100.0, float(discount_pct)))
    discount_inr = int(round(gross_inr * discount_pct / 100.0))
    net_inr = max(1, gross_inr - discount_inr)
    discount_inr = gross_inr - net_inr   # re-derive so they always sum
    return net_inr, discount_inr


def record_attribution(
    *,
    user_id: str,
    user_email: str,
    code_info: dict,
    source: str = "checkout",
) -> None:
    """Best-effort write to referral_attributions. Silent on failure —
    a missed attribution row should never block a checkout."""
    if not code_info.get("valid"):
        return
    try:
        _supabase.upsert(
            "referral_attributions",
            {
                "user_id":     user_id,
                "user_email":  user_email or "",
                "code":        code_info["code"],
                "partner_id":  code_info.get("partner_id"),
                "employee_id": code_info.get("employee_id"),
                "source":      source,
            },
        )
    except Exception as e:
        log.warning("referral_attributions write failed: %s", e)


def record_event(
    *,
    order_id: str,
    user_id: str | None,
    user_email: str | None,
    code_info: dict,
    plan_id: str,
    gross_inr: int,
    discount_inr: int,
    net_inr: int,
) -> None:
    """Idempotent write to referral_events. Keyed on order_id (UNIQUE) so
    Cashfree webhook replay just upserts the same row.

    commission_pct is snapshotted from code_info (which read it off the
    partner at code-validation time) — that's the authoritative number for
    this payout regardless of future tier changes."""
    if not code_info.get("valid"):
        return
    try:
        commission_pct = float(code_info.get("commission_pct") or 0.0)
        commission_inr = int(round(net_inr * commission_pct / 100.0))
        _supabase.upsert(
            "referral_events",
            {
                "order_id":         order_id,
                "user_id":          user_id,
                "user_email":       user_email or "",
                "code":             code_info["code"],
                "partner_id":       code_info.get("partner_id"),
                "employee_id":      code_info.get("employee_id"),
                "plan_id":          plan_id,
                "gross_amount_inr": gross_inr,
                "discount_inr":     discount_inr,
                "net_amount_inr":   net_inr,
                "commission_pct":   commission_pct,
                "commission_inr":   commission_inr,
                "payout_status":    "pending" if commission_inr > 0 else "none",
            },
            on_conflict="order_id",
        )
        log.info(
            "referral_event written: order=%s code=%s gross=%s net=%s commission=%s",
            order_id, code_info["code"], gross_inr, net_inr, commission_inr,
        )
    except Exception as e:
        log.warning("referral_events write failed for order=%s: %s", order_id, e)
