"""Cashfree Payments Gateway integration.

Config (set as Railway env vars — never in code):
  CASHFREE_APP_ID        app-id from Cashfree → Developers → API keys
  CASHFREE_SECRET_KEY    secret key from same page
  CASHFREE_ENV           "production" or "sandbox"  (default: "sandbox")
  CASHFREE_WEBHOOK_SECRET  webhook signing secret (set in Cashfree dashboard)

API version: 2023-08-01
Docs: https://docs.cashfree.com/reference/pg-new-apis-endpoint
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import uuid
from typing import Optional

import httpx


log = logging.getLogger(__name__)

_APP_ID       = os.environ.get("CASHFREE_APP_ID", "")
_SECRET_KEY   = os.environ.get("CASHFREE_SECRET_KEY", "")
_WEBHOOK_SEC  = os.environ.get("CASHFREE_WEBHOOK_SECRET", "")
_ENV          = os.environ.get("CASHFREE_ENV", "sandbox")
_BASE_URL     = (
    "https://api.cashfree.com"
    if _ENV == "production"
    else "https://sandbox.cashfree.com"
)
_API_VERSION  = "2023-08-01"

PLAN_AMOUNTS: dict[str, int] = {
    "weekly":  120,
    "monthly": 499,
    "yearly":  4999,
}
_PLAN_LABELS: dict[str, str] = {
    "weekly":  "Headnote Weekly Trial (7 days)",
    "monthly": "Headnote Monthly Subscription",
    "yearly":  "Headnote Yearly Subscription",
}


def _headers() -> dict:
    return {
        "x-client-id":     _APP_ID,
        "x-client-secret": _SECRET_KEY,
        "x-api-version":   _API_VERSION,
        "Content-Type":    "application/json",
    }


def is_configured() -> bool:
    return bool(_APP_ID and _SECRET_KEY)


def create_order(
    *,
    plan_id: str,
    user_id: str,
    customer_email: str,
    customer_name: str,
    customer_phone: str,
    app_base_url: str,
) -> dict:
    """Create a Cashfree payment order.

    Returns the full Cashfree order object.
    `payment_session_id` in the response is what the JS SDK needs.
    Raises httpx.HTTPStatusError on Cashfree API errors.
    """
    amount = PLAN_AMOUNTS.get(plan_id)
    if amount is None:
        raise ValueError(f"Unknown plan_id: {plan_id!r}")

    order_id = f"hn_{uuid.uuid4().hex[:16]}"
    # Cashfree replaces {order_id} in return_url with the actual order_id
    return_url = f"{app_base_url}/payments/return?order_id={order_id}"

    # Cashfree requires a real 10-digit phone. We never default this to a
    # dummy ("9999999999") anymore — the caller MUST collect it via the
    # pricing-page confirm modal so the customer's actual phone reaches
    # Cashfree (used for UPI, OTP, refunds, receipts).
    phone = (customer_phone or "").strip().replace(" ", "").replace("-", "")
    if phone.startswith("+91"):
        phone = phone[3:]
    if phone.startswith("91") and len(phone) == 12:
        phone = phone[2:]
    if not (phone.isdigit() and len(phone) == 10 and phone[0] in "6789"):
        raise ValueError(
            "Cashfree requires a valid 10-digit Indian phone number "
            "(starting with 6/7/8/9). Got: " + repr(customer_phone)
        )

    payload = {
        "order_id":       order_id,
        "order_amount":   float(amount),
        "order_currency": "INR",
        "customer_details": {
            "customer_id":    user_id[:50],
            "customer_name":  (customer_name or "Headnote User")[:50],
            "customer_email": customer_email,
            "customer_phone": phone,
        },
        "order_meta": {
            "return_url": return_url,
        },
        "order_note": _PLAN_LABELS.get(plan_id, f"Headnote {plan_id}"),
        "order_tags": {
            "plan_id": plan_id,
            "user_id": user_id,
        },
    }

    with httpx.Client(timeout=15.0) as client:
        resp = client.post(
            f"{_BASE_URL}/pg/orders",
            json=payload,
            headers=_headers(),
        )
    resp.raise_for_status()
    data = resp.json()
    log.info(
        "cashfree: order created order_id=%s plan=%s user=%.8s env=%s",
        order_id, plan_id, user_id, _ENV,
    )
    return data


def get_order(order_id: str) -> dict:
    """Fetch a single order's status from Cashfree."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            f"{_BASE_URL}/pg/orders/{order_id}",
            headers=_headers(),
        )
    resp.raise_for_status()
    return resp.json()


def get_order_payments(order_id: str) -> list[dict]:
    """Fetch payment attempts for an order."""
    with httpx.Client(timeout=10.0) as client:
        resp = client.get(
            f"{_BASE_URL}/pg/orders/{order_id}/payments",
            headers=_headers(),
        )
    resp.raise_for_status()
    return resp.json()


def verify_webhook_signature(raw_body: bytes, timestamp: str, signature: str) -> bool:
    """Verify a Cashfree webhook.

    Cashfree v2023-08-01 signing scheme:
        signed_payload = timestamp + raw_request_body   (string concat, no separator)
        signature      = base64(HMAC-SHA256(secret, signed_payload))

    The webhook secret is configured in Cashfree dashboard → Developers →
    Webhooks. Until it's set, we fall back to CASHFREE_SECRET_KEY which is
    Cashfree's default signing key. If neither is configured we skip the
    check in dev mode (loud log) so local development isn't blocked.
    """
    secret = _WEBHOOK_SEC or _SECRET_KEY
    if not secret:
        log.warning("Cashfree webhook secret not configured; skipping signature check (dev mode)")
        return True
    if not signature or not timestamp:
        return False

    message = (timestamp.encode() + raw_body)
    expected_bytes = hmac.new(secret.encode(), message, hashlib.sha256).digest()
    expected = base64.b64encode(expected_bytes).decode()
    return hmac.compare_digest(expected, signature)


def extract_tags(order: dict) -> tuple[Optional[str], Optional[str]]:
    """Return (plan_id, user_id) from order tags (set at create time)."""
    tags = order.get("order_tags") or {}
    plan_id = tags.get("plan_id")
    user_id = tags.get("user_id") or (order.get("customer_details") or {}).get("customer_id")
    return plan_id, user_id
