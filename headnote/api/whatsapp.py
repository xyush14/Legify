"""WhatsApp webhook routes — receive + dispatch.

Spec: docs/WHATSAPP_BOT_PRD.md §6, §8 (F1.x).

Two parallel webhook paths, one per provider:

  /api/whatsapp/webhook         — Meta Cloud API (JSON, X-Hub-Signature-256)
  /api/whatsapp/twilio/webhook  — Twilio (form-encoded, X-Twilio-Signature)

Each route parses its own provider's wire format, normalizes to an
InboundMessage, then runs through the SAME _handle_inbound_message()
dispatch (echo bot at Phase 1; research pipeline at Phase 2).

Reply provider matches inbound provider — a Twilio-received message
replies via Twilio, regardless of WA_PROVIDER env default. This means
both channels can run side-by-side (useful while migrating).
"""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response

from headnote.whatsapp import client as wa
from headnote.whatsapp.providers import InboundMessage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])


# ════════════════════════════════════════════════════════════════ Meta routes

@router.get("/webhook")
async def meta_verify(request: Request) -> Response:
    """Meta's initial webhook verification handshake.

    Meta sends ?hub.mode=subscribe&hub.verify_token=<X>&hub.challenge=<Y>.
    We echo hub.challenge as plain text if hub.verify_token matches.
    """
    q = request.query_params
    expected = os.environ.get("WA_VERIFY_TOKEN", "")
    if q.get("hub.mode") == "subscribe" and q.get("hub.verify_token") == expected and expected:
        return Response(content=q.get("hub.challenge", ""), media_type="text/plain")
    raise HTTPException(status_code=403, detail="verify token mismatch")


@router.post("/webhook")
async def meta_inbound(request: Request) -> dict[str, str]:
    raw = await request.body()
    provider = wa.provider_for("meta")
    provider.verify_signature(raw, dict(request.headers), str(request.url))
    messages = provider.parse_webhook(raw, request.headers.get("content-type", ""))
    for msg in messages:
        await _handle_inbound_message(msg, provider_name="meta")
    return {"status": "ok"}


# ════════════════════════════════════════════════════════════════ Twilio routes

@router.post("/twilio/webhook")
async def twilio_inbound(request: Request) -> Response:
    """Twilio webhook endpoint.

    Twilio doesn't use a GET handshake — you just paste this URL into the
    sandbox config and it starts POSTing inbound messages.
    """
    raw = await request.body()
    provider = wa.provider_for("twilio")
    # signature verification uses the public URL; allow override for proxies
    public_url = os.environ.get("TWILIO_WEBHOOK_URL") or str(request.url)
    provider.verify_signature(raw, dict(request.headers), public_url)
    messages = provider.parse_webhook(raw, request.headers.get("content-type", ""))
    for msg in messages:
        await _handle_inbound_message(msg, provider_name="twilio")
    # Twilio likes an empty 200 (or TwiML); empty is fine.
    return Response(status_code=200)


# ════════════════════════════════════════════════════════════════ dispatch

async def _handle_inbound_message(msg: InboundMessage, *, provider_name: str) -> None:
    """Common dispatch — log, dedupe, route to intent handler, reply.

    Phase 1 = echo bot. Phase 2 replaces _handle_text() with research.
    """
    inserted = await _log_message(
        wa_phone=msg.wa_phone,
        direction="in",
        msg_type=msg.msg_type,
        body=(msg.body or "")[:500] if msg.body else None,
        meta_msg_id=msg.provider_msg_id,
    )
    if not inserted:
        log.info("dedupe hit on provider_msg_id=%s — skipping", msg.provider_msg_id)
        return

    if msg.msg_type != "text":
        reply = "I can only read text messages right now. Send me a legal research question to try."
    else:
        reply = _handle_text(msg.wa_phone, msg.body)

    try:
        resp = wa.send_text(msg.wa_phone, reply, provider=provider_name)
        # Meta returns {"messages": [{"id": ...}]}; Twilio returns {"sid": ...}
        out_id = (
            (resp.get("messages") or [{}])[0].get("id")
            or resp.get("sid")
            or ""
        )
        await _log_message(
            wa_phone=msg.wa_phone,
            direction="out",
            msg_type="text",
            body=reply[:500],
            meta_msg_id=out_id,
        )
    except wa.WAClientError as exc:
        log.error("failed to send reply via %s to %s: %s", provider_name, msg.wa_phone, exc)


def _handle_text(wa_phone: str, body: str) -> str:
    """Phase 1: echo bot. Phase 2 will dispatch to the research pipeline."""
    text = (body or "").strip()
    if not text:
        return "Send a legal research question to begin — e.g. 'section 138 NI Act recent SC on territorial jurisdiction'."
    return (
        "Headnote echo (Phase 1): " + text[:200] +
        "\n\nResearch pipeline lands in Phase 2."
    )


# ════════════════════════════════════════════════════════════════ DB log

async def _log_message(
    *,
    wa_phone: str | None,
    direction: str,
    msg_type: str,
    body: str | None,
    meta_msg_id: str | None,
    user_id: str | None = None,
) -> bool:
    """Insert into wa_messages via Supabase REST.

    Returns False on dedupe-conflict (unique idx on meta_msg_id),
    True otherwise. Never raises — bot must keep working on DB outage.
    """
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not (base and key):
        log.warning("supabase not configured — skipping wa_messages log")
        return True

    url = f"{base}/rest/v1/wa_messages"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=minimal,resolution=ignore-duplicates",
    }
    row = {
        "wa_phone": wa_phone,
        "direction": direction,
        "msg_type": msg_type,
        "body": body,
        "meta_msg_id": meta_msg_id,
        "user_id": user_id,
    }
    try:
        async with httpx.AsyncClient(timeout=8.0) as ac:
            r = await ac.post(url, headers=headers, json=row)
        if r.status_code in (200, 201):
            return True
        if r.status_code == 409:
            return False
        log.warning("wa_messages insert: %s %s", r.status_code, r.text[:200])
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("wa_messages insert failed: %s", exc)
        return True
