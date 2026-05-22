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
from headnote.entitlements.plans import PLANS, get_plan
from headnote.entitlements.subscription import change_plan
from headnote.payments import cashfree


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/payments", tags=["payments"])


# Map our plan ids to Cashfree note labels for the order_note field
_SELLABLE_PLANS = {"weekly", "monthly", "yearly"}


# ---------------------------------------------------------------- models

class CreateOrderRequest(BaseModel):
    plan: str = Field(..., description="weekly | monthly | yearly")
    phone: Optional[str] = Field(None, description="10-digit phone for Cashfree (optional)")


class CreateOrderResponse(BaseModel):
    order_id: str
    payment_session_id: str
    payment_url: str
    amount_inr: int
    plan: str
    env: str  # 'sandbox' or 'production'


# ---------------------------------------------------------------- shared logic

def _payment_url_for_session(payment_session_id: str) -> str:
    """Cashfree hosted-checkout URL. The session ID itself contains an `env`
    prefix that determines which page renders. So we use the same payments.cashfree.com
    host for both sandbox and production — Cashfree routes internally."""
    return f"https://payments.cashfree.com/pay/{payment_session_id}"


def _upgrade_from_paid_order(order: dict) -> dict:
    """Given a Cashfree order whose status is PAID, upgrade the user's
    subscription. Idempotent — safe to call from both webhook and /verify.

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
    return sub


# ---------------------------------------------------------------- endpoints

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
            for p in _SELLABLE_PLANS
        },
    }


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

    customer_name = (
        (user.raw_claims or {}).get("user_metadata", {}).get("full_name")
        or (user.raw_claims or {}).get("user_metadata", {}).get("name")
        or (user.email.split("@")[0] if user.email else "Headnote User")
    )

    try:
        order = cashfree.create_order(
            plan_id=body.plan,
            user_id=user.id,
            customer_email=user.email or f"{user.id}@headnote.local",
            customer_name=customer_name,
            customer_phone=(body.phone or "").strip(),
            app_base_url=app_base_url,
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

    return CreateOrderResponse(
        order_id=order_id,
        payment_session_id=session_id,
        payment_url=_payment_url_for_session(session_id),
        amount_inr=cashfree.PLAN_AMOUNTS.get(body.plan, 0),
        plan=body.plan,
        env=os.environ.get("CASHFREE_ENV", "sandbox"),
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
    if (order.get("order_status") or "").upper() == "PAID":
        result = _upgrade_from_paid_order(order)
        upgraded = bool(result)

    return {
        "order_id":  order_id,
        "status":    order.get("order_status"),
        "plan":      plan_id,
        "amount":    order.get("order_amount"),
        "upgraded":  upgraded,
    }
