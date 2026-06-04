"""Payments router — Cashfree PG hosted checkout.

Endpoints
---------
POST /api/payments/create-order   auth required. Body {"plan": "weekly|monthly|yearly"}.
                                  Returns {payment_session_id, payment_url, order_id}.
                                  FE redirects browser to payment_url.

POST /api/payments/webhook        no auth. Cashfree calls this server-to-server
                                  after payment. Signature verified; if PAID,
                                  upgrades the subscription.

GET  /api/payments/verify         auth required. ?order_id=xxx. Hits Cashfree to
                                  confirm status; if PAID, upgrades subscription.
                                  Used by /payment-success page (idempotent).

GET  /api/payments/config         public. Returns env (sandbox/production) so the
                                  FE can show the right badge during dev.

Idempotency
-----------
The webhook AND the verify endpoint both call _upgrade_from_paid_order, which
is safe to call multiple times: change_plan() is a PATCH that just re-sets
period_end. Calling it again with the same order_id is a no-op effect-wise.

Auth
----
create-order and verify use the standard CurrentUser dependency.
webhook bypasses that — it's signed by Cashfree, not the user.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements import _supabase
from headnote.entitlements.plans import PLANS, get_plan
from headnote.entitlements.subscription import change_plan
from headnote.payments import cashfree
from headnote.payments import referrals


def _profile_lookup(user_id: str) -> dict:
    """Read this user's row from public.user_profiles. Returns {} on miss."""
    try:
        rows = _supabase.select(
            "user_profiles",
            params={"id": f"eq.{user_id}", "select": "name,phone,referral_code", "limit": "1"},
        )
        return rows[0] if rows else {}
    except Exception as e:
        log.warning("profile lookup failed for user=%.8s: %s", user_id, e)
        return {}


def _normalise_phone(raw: str | None) -> str:
    """Return a 10-digit Indian phone (no country code). Empty string if invalid.
    Accepts: '+91 88156 21916', '+918815621916', '8815621916', '918815621916'."""
    if not raw: return ""
    s = "".join(ch for ch in raw if ch.isdigit())
    if s.startswith("91") and len(s) == 12: s = s[2:]
    if len(s) == 10 and s[0] in "6789": return s
    return ""


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


# Plans the user can buy.
#   - subscription plans flip the single public.subscriptions row (change_plan)
#   - add-on plans grant a permanent, SEPARATE entitlement and must never
#     touch the subscriptions row (single-plan model)
_SUBSCRIPTION_PLANS = {"weekly", "monthly", "yearly"}
_ADDON_PLANS = {"sections"}             # one-time, lifetime unlocks
_SELLABLE_PLANS = _SUBSCRIPTION_PLANS | _ADDON_PLANS


# ---------------------------------------------------------------- models

class CreateOrderRequest(BaseModel):
    plan: str = Field(..., description="weekly | monthly | yearly")
    phone: Optional[str] = Field(None, description="10-digit phone for Cashfree (optional)")
    referral_code: Optional[str] = Field(None, description="Optional partner/publication referral code")


class CreateOrderResponse(BaseModel):
    order_id: str
    payment_session_id: str
    amount_inr: int
    plan: str
    env: str  # 'sandbox' or 'production'
    list_amount_inr: int = 0           # pre-discount list price (== amount_inr when no code)
    discount_inr: int = 0              # >0 if a referral code reduced the price
    referral_code: Optional[str] = None
    referral_kind: Optional[str] = None  # 'distributor' | 'publication' | None


# ---------------------------------------------------------------- shared logic


def _upgrade_from_paid_order(order: dict) -> dict:
    """Given a Cashfree order whose status is PAID, upgrade the user's
    subscription. Idempotent — safe to call from both webhook and /verify.

    Also writes a referral_events ledger row if the order carried a code.
    Idempotent on order_id, so webhook replay is safe.

    Returns the updated subscription dict (or empty dict on failure).
    """
    if (order.get("order_status") or "").upper() != "PAID":
        return {}

    plan_id, user_id = cashfree.extract_tags(order)
    if not (plan_id and user_id):
        log.warning("paid order missing tags: %s", order.get("order_id"))
        return {}
    if plan_id not in _SELLABLE_PLANS:
        log.warning("paid order has unsellable plan: %s", plan_id)
        return {}

    # Add-on purchases (e.g. the ₹99 Section Finder) are NOT subscriptions —
    # they grant a permanent, separate entitlement and must never overwrite
    # the user's single subscriptions row.
    if plan_id in _ADDON_PLANS:
        result = _grant_addon(plan_id, user_id, order)
        _record_referral_event_if_any(order, plan_id, user_id)
        return result

    sub = change_plan(
        user_id,
        plan_id,
        payment_provider="cashfree",
        payment_ref=order.get("order_id"),
    )
    log.info(
        "subscription upgraded via Cashfree: user=%.8s plan=%s order=%s",
        user_id, plan_id, order.get("order_id"),
    )
    _record_referral_event_if_any(order, plan_id, user_id)
    return sub


def _record_referral_event_if_any(order: dict, plan_id: str, user_id: str) -> None:
    """If the order carried a referral_code in its tags, write the commission
    ledger row. Idempotent on order_id — webhook replay just re-upserts."""
    referral_code, list_amount = cashfree.extract_referral_tags(order)
    if not referral_code:
        return
    net_amount = int(round(float(order.get("order_amount") or 0)))
    if list_amount <= 0:
        list_amount = net_amount   # fallback if tag was missing
    discount_inr = max(0, list_amount - net_amount)
    code_info = referrals.lookup_code_snapshot(referral_code)
    if not code_info.get("valid"):
        log.warning(
            "referral code %s on order %s not found at webhook time; skipping ledger write",
            referral_code, order.get("order_id"),
        )
        return
    customer = order.get("customer_details") or {}
    referrals.record_event(
        order_id=order.get("order_id") or "",
        user_id=user_id,
        user_email=customer.get("customer_email") or "",
        code_info=code_info,
        plan_id=plan_id,
        gross_inr=list_amount,
        discount_inr=discount_inr,
        net_inr=net_amount,
    )


def _grant_addon(plan_id: str, user_id: str, order: dict) -> dict:
    """Record a one-time, lifetime add-on entitlement. Idempotent: the upsert
    is keyed on user_id, so re-firing the webhook/verify just merges.

    Currently the only add-on is "sections" → a row in public.sections_unlocks.
    """
    if plan_id != "sections":
        return {}
    payload = {
        "user_id":    user_id,
        "order_id":   order.get("order_id"),
        "source":     "cashfree",
        "amount_inr": int(float(order.get("order_amount") or 0)),
    }
    try:
        result = _supabase.upsert("sections_unlocks", payload, on_conflict="user_id")
        log.info(
            "sections unlock granted: user=%.8s order=%s",
            user_id, order.get("order_id"),
        )
        return result[0] if result else payload
    except Exception:
        log.exception(
            "failed to grant sections unlock user=%.8s order=%s",
            user_id, order.get("order_id"),
        )
        return {}


# ---------------------------------------------------------------- endpoints

@router.get("/customer-info", summary="Get this user's pre-fill data for the checkout confirm modal")
def customer_info(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Returns the data the pricing-page 'Confirm your details' modal needs.

    name + email come from the Google sign-in (Supabase JWT claims).
    phone comes from public.user_profiles (set during onboarding).

    The frontend uses `phone_ok=false` to decide whether to mark the phone
    input as required-and-empty vs pre-filled-and-locked.
    """
    claims = user.raw_claims or {}
    meta   = claims.get("user_metadata") or {}
    name = (
        meta.get("full_name") or meta.get("name")
        or (user.email.split("@")[0] if user.email else "")
    )
    profile = _profile_lookup(user.id)
    if profile.get("name"):
        name = profile["name"]
    phone = _normalise_phone(profile.get("phone"))
    return {
        "name":     name,
        "email":    user.email or "",
        "phone":    phone,           # 10 digits or empty
        "phone_ok": bool(phone),
    }


@router.get("/config", summary="Public payments config (for FE badges)")
def payments_config() -> dict:
    """Returns the public payment config so the pricing page can show
    'Sandbox mode' during testing. Never exposes the secret key."""
    import os
    return {
        "configured": cashfree.is_configured(),
        "env":        os.environ.get("CASHFREE_ENV", "sandbox"),
        "currency":   "INR",
        "plans": {
            p: {
                "amount_inr":   cashfree.PLAN_AMOUNTS.get(p, 0),
                "display_name": get_plan(p).display_name,
            }
            for p in _SUBSCRIPTION_PLANS
        },
    }


@router.get("/validate-referral", summary="Preview a referral code's discount for the checkout page")
def validate_referral(
    code: str,
    plan: Optional[str] = None,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Validate a referral code and (optionally) preview the discounted price
    for a plan. The checkout page calls this when the user types/pastes a
    code, BEFORE they hit Pay, so they see the new price live.

    Never raises 4xx for a bad code — returns `valid=False` with a `message`
    instead, so the FE can show the error inline without try/catch noise.
    """
    info = referrals.lookup_code(code, user.email)
    if not info.get("valid"):
        return {"valid": False, "code": referrals.canonical(code), "message": info.get("reason") or "Invalid code."}

    out: dict = {
        "valid":         True,
        "code":          info["code"],
        "kind":          info["kind"],            # 'distributor' | 'publication'
        "discount_pct":  info["discount_pct"],
        "publication":   info.get("publication_name"),
        "message":       f"{info['discount_pct']:g}% off applied.",
    }
    if plan and plan in _SELLABLE_PLANS:
        list_amount = cashfree.PLAN_AMOUNTS.get(plan, 0)
        net_amount, discount_inr = referrals.apply_discount(list_amount, info["discount_pct"])
        out.update({
            "plan":             plan,
            "list_amount_inr":  list_amount,
            "net_amount_inr":   net_amount,
            "discount_inr":     discount_inr,
        })
    return out


@router.post("/create-order", response_model=CreateOrderResponse,
             summary="Create a Cashfree order and return the payment URL")
def create_order(
    body: CreateOrderRequest,
    user: CurrentUser = Depends(get_current_user),
) -> CreateOrderResponse:
    import os

    if not cashfree.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Payments not configured. Set CASHFREE_APP_ID and CASHFREE_SECRET_KEY.",
        )
    if body.plan not in _SELLABLE_PLANS:
        raise HTTPException(status_code=400, detail=f"plan must be one of {sorted(_SELLABLE_PLANS)}")

    # Where Cashfree should redirect after payment. Always use APP_BASE_URL
    # if set (production: https://headnote.in). Falling back to request origin
    # is unreliable behind a proxy, so we require this env var in prod.
    app_base_url = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")

    # Resolve customer details: profile first, then JWT claims, then email-prefix.
    profile = _profile_lookup(user.id)
    customer_name = (
        profile.get("name")
        or (user.raw_claims or {}).get("user_metadata", {}).get("full_name")
        or (user.raw_claims or {}).get("user_metadata", {}).get("name")
        or (user.email.split("@")[0] if user.email else "Headnote User")
    )

    # Phone: explicit body value wins; fallback to stored profile phone.
    phone = _normalise_phone(body.phone) or _normalise_phone(profile.get("phone"))
    if not phone:
        raise HTTPException(
            status_code=400,
            detail={
                "code":    "phone_required",
                "message": "A valid 10-digit Indian mobile number is required. "
                           "Please confirm your details before continuing to payment.",
            },
        )

    # Persist the validated phone back to the profile so the next checkout
    # pre-fills it. Best-effort — failure here doesn't block payment.
    try:
        _supabase.update(
            "user_profiles",
            {"phone": "+91" + phone},
            params={"id": f"eq.{user.id}"},
        )
    except Exception as e:
        log.info("profile phone update skipped (non-fatal): %s", e)

    # Referral code: validate and compute discounted amount. A bad code is a
    # 400 so the FE can show the error; the user can retry without it.
    list_amount = cashfree.PLAN_AMOUNTS.get(body.plan, 0)
    net_amount = list_amount
    discount_inr = 0
    code_info: dict = {"valid": False}
    if body.referral_code:
        code_info = referrals.lookup_code(body.referral_code, user.email)
        if not code_info.get("valid"):
            raise HTTPException(
                status_code=400,
                detail={"code": "invalid_referral", "message": code_info.get("reason") or "Invalid referral code."},
            )
        net_amount, discount_inr = referrals.apply_discount(list_amount, code_info["discount_pct"])

    try:
        order = cashfree.create_order(
            plan_id=body.plan,
            user_id=user.id,
            customer_email=user.email or f"{user.id}@headnote.local",
            customer_name=customer_name,
            customer_phone=phone,
            app_base_url=app_base_url,
            amount_override=net_amount if code_info.get("valid") else None,
            referral_code=code_info.get("code") if code_info.get("valid") else None,
        )
    except Exception as e:
        log.exception("Cashfree create_order failed for user=%.8s plan=%s", user.id, body.plan)
        raise HTTPException(status_code=502, detail=f"Cashfree error: {e}")

    session_id = order.get("payment_session_id")
    order_id   = order.get("order_id")
    if not (session_id and order_id):
        raise HTTPException(
            status_code=502,
            detail=f"Cashfree returned malformed order: {order}",
        )

    # Stash the attribution now (best-effort). The commission ledger row is
    # written later by the webhook when payment actually succeeds.
    if code_info.get("valid"):
        referrals.record_attribution(
            user_id=user.id,
            user_email=user.email or "",
            code_info=code_info,
            source="checkout",
        )

    return CreateOrderResponse(
        order_id=order_id,
        payment_session_id=session_id,
        amount_inr=net_amount,
        plan=body.plan,
        env=os.environ.get("CASHFREE_ENV", "sandbox"),
        list_amount_inr=list_amount,
        discount_inr=discount_inr,
        referral_code=code_info.get("code") if code_info.get("valid") else None,
        referral_kind=code_info.get("kind") if code_info.get("valid") else None,
    )


@router.post("/webhook", summary="Cashfree server-to-server payment notification")
async def cashfree_webhook(
    request: Request,
    x_webhook_signature: Optional[str] = Header(default=None),
    x_webhook_timestamp: Optional[str] = Header(default=None),
) -> dict:
    """Cashfree posts here after every payment status change. We verify the
    signature, and on PAID events, upgrade the subscription.

    Cashfree retries failed webhooks up to 13 times with exponential backoff,
    so this endpoint MUST be idempotent. It is — change_plan() just re-sets
    the subscription row.
    """
    raw_body = await request.body()

    if not cashfree.verify_webhook_signature(
        raw_body=raw_body,
        timestamp=x_webhook_timestamp or "",
        signature=x_webhook_signature or "",
    ):
        log.warning("Cashfree webhook signature failed; rejecting")
        raise HTTPException(status_code=401, detail="invalid webhook signature")

    import json
    try:
        payload = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"bad JSON: {e}")

    event_type = payload.get("type") or payload.get("event_type") or ""
    data = payload.get("data") or {}
    order = data.get("order") or data  # different shapes across event types
    log.info("Cashfree webhook: event=%s order_id=%s", event_type, order.get("order_id"))

    # Only react to PAYMENT_SUCCESS / ORDER_PAID events. Webhook payload's
    # `order_status` is the canonical state.
    if (order.get("order_status") or "").upper() == "PAID":
        _upgrade_from_paid_order(order)

    # Always 200 — Cashfree retries non-2xx responses for days.
    return {"ok": True}


@router.get("/verify", summary="Verify an order's status and upgrade if paid")
def verify_payment(
    order_id: str,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Called by /payment-success after Cashfree redirects the user back.
    Idempotent — works whether or not the webhook has already fired.

    Returns:
        {"status": "PAID"|"ACTIVE"|"EXPIRED"|..., "plan": "monthly", "upgraded": bool}
    """
    if not cashfree.is_configured():
        raise HTTPException(status_code=503, detail="Payments not configured")

    try:
        order = cashfree.get_order(order_id)
    except Exception as e:
        log.exception("Cashfree get_order(%s) failed", order_id)
        raise HTTPException(status_code=502, detail=f"Cashfree error: {e}")

    plan_id, owner_user_id = cashfree.extract_tags(order)
    # Defence: only let the order's original user verify it. Prevents another
    # logged-in user from triggering an upgrade on someone else's order.
    if owner_user_id and owner_user_id != user.id:
        raise HTTPException(status_code=403, detail="order belongs to another user")

    upgraded = False
    sub = {}
    if (order.get("order_status") or "").upper() == "PAID":
        sub = _upgrade_from_paid_order(order)
        upgraded = bool(sub)

    return {
        "order_id":     order_id,
        "status":       order.get("order_status"),
        "plan":         plan_id,
        "amount":       order.get("order_amount"),
        "upgraded":     upgraded,
        "subscription": sub or None,   # FE uses this to update sidebar immediately
        "display_name": (get_plan(plan_id).display_name if plan_id in PLANS else None),
    }
