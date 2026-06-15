"""Bolna voice-agent sales integration.

Two surfaces:
  1. Tool endpoints  — Bolna's agent invokes these mid-conversation when the
     lawyer agrees to a CTA (book_demo / send_whatsapp / start_trial / mark_dnd).
  2. Webhook        — Bolna posts call lifecycle events here (call_started,
     call_ended, transcript_ready) so we can persist the call record.

Plus one admin endpoint (POST /api/bolna/dial) that triggers an outbound call
from a lead list. Skip lists are honored.

CTA outcomes flow back into the existing WhatsApp pipeline (no new send path).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from typing import Any, Literal, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from headnote.entitlements._supabase import select, update, upsert
from headnote.whatsapp.client import send_text as wa_send_text

log = logging.getLogger("headnote.bolna")
router = APIRouter(prefix="/api/bolna", tags=["bolna"])

BOLNA_WEBHOOK_SECRET = os.environ.get("BOLNA_WEBHOOK_SECRET", "")
BOLNA_API_KEY = os.environ.get("BOLNA_API_KEY", "")
BOLNA_AGENT_ID = os.environ.get("BOLNA_AGENT_ID", "")
# /call is at the root; /v2/agent is versioned — keep the base and append per endpoint.
BOLNA_API_BASE = os.environ.get("BOLNA_API_BASE", "https://api.bolna.ai")


def _require_bolna_auth(authorization: str = Header(default="")) -> None:
    """Tool endpoints are public-facing — gate them on the shared secret that
    Bolna sends via api_token in tools_params (Authorization: Bearer <secret>).
    """
    if not BOLNA_WEBHOOK_SECRET:
        log.warning("BOLNA_WEBHOOK_SECRET not set — tool auth bypassed (dev only)")
        return
    expected = f"Bearer {BOLNA_WEBHOOK_SECRET}"
    if not hmac.compare_digest(authorization, expected):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid tool auth")


# ----- WhatsApp templates the agent can dispatch ---------------------------

def _env(key: str, default: str) -> str:
    return os.environ.get(key, default)


def _templates() -> dict[str, str]:
    demo_url    = _env("HEADNOTE_DEMO_URL",    "https://headnote.ai/demo")
    trial_url   = _env("HEADNOTE_TRIAL_URL",   "https://headnote.ai/trial")
    pricing_url = _env("HEADNOTE_PRICING_URL", "https://headnote.ai/pricing")
    monthly     = _env("HEADNOTE_MONTHLY_PRICE", "999")
    annual      = _env("HEADNOTE_ANNUAL_PRICE",  "9999")
    saving_pct  = _env("HEADNOTE_PRICE_LOWER_BY", "60")
    return {
        "demo": (
            f"Namaste! 👋 Headnote ka demo video yahaan hai:\n\n"
            f"🎥 {demo_url}\n\n"
            f"Pricing details: {pricing_url}\n\n"
            f"14-day free trial start karna ho toh reply karein *TRIAL*."
        ),
        "overview": (
            f"Namaste! 👋 Headnote ka short overview:\n\n"
            f"• IK citations ko automatic court-ready format mein convert karta hai\n"
            f"• AI-assisted petition/notice drafter\n"
            f"• WhatsApp pe direct research bot\n\n"
            f"Aaram se dekhein — koi pressure nahi: {demo_url}"
        ),
        "pricing": (
            f"Headnote pricing:\n\n"
            f"💼 Monthly: ₹{monthly}/month\n"
            f"💼 Annual: ₹{annual}/year (save 2 months)\n\n"
            f"~{saving_pct}% cheaper than Manupatra/SCC Online for the\n"
            f"citation + drafter combo.\n\n"
            f"14-day free trial: {trial_url}"
        ),
        "trial": (
            f"Aapka 14-day free trial start ho gaya! 🎉\n\n"
            f"Activation link: {trial_url}\n\n"
            f"WhatsApp pe direct research bhi try kar sakte hain — bas yahaan question type karein."
        ),
    }


# ----- Tool I/O schemas ----------------------------------------------------

class BookDemoRequest(BaseModel):
    name: str
    phone: str
    when_preference: str = Field(description="Free-text time pref from lawyer, e.g. 'kal subah' or 'after 5pm Friday'")
    call_id: Optional[str] = None


class SendWhatsappRequest(BaseModel):
    phone: str
    template: Literal["demo", "overview", "pricing", "trial"]
    call_id: Optional[str] = None


class StartTrialRequest(BaseModel):
    phone: str
    name: Optional[str] = None
    call_id: Optional[str] = None


class MarkDndRequest(BaseModel):
    phone: str
    reason: Literal["not_interested", "wrong_person", "hostile", "out_of_market", "duplicate"]
    call_id: Optional[str] = None


class ToolResponse(BaseModel):
    ok: bool
    message: str  # spoken back to the lawyer by the agent
    data: dict[str, Any] = Field(default_factory=dict)


# ----- Helpers -------------------------------------------------------------

def _normalize_phone(phone: str) -> str:
    """+91-prefixed E.164. Accepts 10-digit, 91-prefixed, or +91-prefixed."""
    digits = "".join(ch for ch in phone if ch.isdigit())
    if len(digits) == 10:
        digits = "91" + digits
    return "+" + digits


def _verify_bolna_signature(body: bytes, signature: str) -> bool:
    if not BOLNA_WEBHOOK_SECRET:
        # Dev-only fallback. Set BOLNA_WEBHOOK_SECRET in prod env.
        log.warning("BOLNA_WEBHOOK_SECRET not set — webhook signature check skipped (dev only)")
        return True
    expected = hmac.new(BOLNA_WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def _upsert_lead(phone: str, **fields: Any) -> None:
    payload = {"phone": phone, **{k: v for k, v in fields.items() if v is not None}}
    upsert("leads", payload, on_conflict="phone")


def _link_outcome_to_call(call_id: Optional[str], outcome: str) -> None:
    if not call_id:
        return
    update("bolna_calls", {"outcome": outcome}, params={"call_id": f"eq.{call_id}"})


# ----- Tool endpoints (Bolna calls these mid-conversation) -----------------

@router.post("/tools/book_demo", response_model=ToolResponse, dependencies=[Depends(_require_bolna_auth)])
def tool_book_demo(req: BookDemoRequest) -> ToolResponse:
    """The agent calls this when the lawyer agrees to a demo with the advocate.

    Current behaviour: persist the request + send WhatsApp confirmation;
    founder books the actual calendar slot. Cal.com / Google Calendar
    integration goes in once we pick one.
    """
    phone = _normalize_phone(req.phone)
    _upsert_lead(
        phone=phone, name=req.name, status="demo_booked",
        notes=f"Demo requested via Bolna: {req.when_preference}",
    )
    _link_outcome_to_call(req.call_id, "booked_demo")

    advocate = _env("HEADNOTE_ADVOCATE_NAME", "the senior advocate")
    confirmation = (
        f"✅ Demo confirmed!\n\n"
        f"{advocate} will call you for a 15-min demo.\n"
        f"Your preference: {req.when_preference}\n\n"
        f"Detailed confirmation will follow shortly."
    )
    try:
        wa_send_text(to=phone, body=confirmation)
    except Exception as e:
        log.exception("WhatsApp confirmation failed for %s: %s", phone, e)

    log.info("Demo booked phone=%s when=%s", phone, req.when_preference)
    return ToolResponse(
        ok=True,
        message=(
            f"Demo confirm ho gaya, {req.name}ji. {advocate}ji aapko call "
            f"karenge {req.when_preference}. WhatsApp pe bhi confirmation bhej di hai."
        ),
        data={"phone": phone, "when": req.when_preference},
    )


@router.post("/tools/send_whatsapp", response_model=ToolResponse, dependencies=[Depends(_require_bolna_auth)])
def tool_send_whatsapp(req: SendWhatsappRequest) -> ToolResponse:
    phone = _normalize_phone(req.phone)
    body = _templates()[req.template]
    try:
        wa_send_text(to=phone, body=body)
    except Exception as e:
        log.exception("WhatsApp send failed phone=%s template=%s: %s", phone, req.template, e)
        return ToolResponse(
            ok=False,
            message="WhatsApp bhejne mein chhoti si issue aayi, team ko inform kar dungi.",
            data={"error": str(e)},
        )

    _upsert_lead(phone=phone, status="interested",
                 notes=f"WhatsApp '{req.template}' sent via Bolna")
    _link_outcome_to_call(req.call_id, "sent_whatsapp")
    log.info("WhatsApp sent phone=%s template=%s", phone, req.template)
    return ToolResponse(
        ok=True,
        message="WhatsApp bhej di! Aap check karein. Aur kuch poochna ho toh main yahaan hoon.",
        data={"phone": phone, "template": req.template},
    )


@router.post("/tools/start_trial", response_model=ToolResponse, dependencies=[Depends(_require_bolna_auth)])
def tool_start_trial(req: StartTrialRequest) -> ToolResponse:
    phone = _normalize_phone(req.phone)
    body = _templates()["trial"]
    try:
        wa_send_text(to=phone, body=body)
    except Exception as e:
        log.exception("Trial WhatsApp failed phone=%s: %s", phone, e)
        return ToolResponse(
            ok=False,
            message="Trial link bhejne mein issue aayi, team check karegi.",
            data={"error": str(e)},
        )

    _upsert_lead(phone=phone, name=req.name, status="trial_started",
                 notes="Trial started via Bolna call")
    _link_outcome_to_call(req.call_id, "trial_started")
    log.info("Trial started phone=%s", phone)
    return ToolResponse(
        ok=True,
        message=(
            "Bahut badhiya! Trial link WhatsApp pe bhej di hai. 14 din free hai, "
            "koi card nahi chahiye. Kuch poochna ho toh wahin se reply karein."
        ),
        data={"phone": phone},
    )


@router.post("/tools/mark_dnd", response_model=ToolResponse, dependencies=[Depends(_require_bolna_auth)])
def tool_mark_dnd(req: MarkDndRequest) -> ToolResponse:
    phone = _normalize_phone(req.phone)
    upsert("dnd_list",
           {"phone": phone, "reason": req.reason, "marked_by": "bolna_agent"},
           on_conflict="phone")
    _upsert_lead(phone=phone, status="dnd")
    _link_outcome_to_call(req.call_id, "dnd")
    log.info("DND marked phone=%s reason=%s", phone, req.reason)
    return ToolResponse(
        ok=True,
        message="Theek hai, samay dene ke liye dhanyavaad. Aapka din shubh ho.",
        data={"phone": phone, "reason": req.reason},
    )


# ----- Webhook (Bolna -> us, call lifecycle events) ------------------------

class BolnaWebhookPayload(BaseModel):
    event: Literal["call_started", "call_ended", "call_failed", "transcript_ready"]
    call_id: str
    phone: Optional[str] = None
    status: Optional[str] = None
    duration_seconds: Optional[int] = None
    transcript: Optional[str] = None
    summary: Optional[str] = None
    recording_url: Optional[str] = None
    outcome: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)


@router.post("/webhook")
async def bolna_webhook(
    request: Request,
    x_bolna_signature: str = Header(default=""),
) -> dict[str, Any]:
    raw = await request.body()
    if not _verify_bolna_signature(raw, x_bolna_signature):
        log.warning("Invalid Bolna webhook signature")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid signature")

    try:
        payload = BolnaWebhookPayload.model_validate_json(raw)
    except Exception as e:
        log.exception("Bad Bolna webhook payload: %s", e)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid payload")

    phone = _normalize_phone(payload.phone) if payload.phone else None

    if payload.event == "call_started":
        upsert("bolna_calls", {
            "call_id": payload.call_id,
            "phone": phone or "",
            "direction": "outbound",
            "status": "in_progress",
        }, on_conflict="call_id")
        if phone:
            _upsert_lead(phone=phone, status="contacted",
                         last_call_id=payload.call_id)
        return {"ok": True}

    # call_ended / call_failed / transcript_ready
    updates = {
        "status": payload.status or ("completed" if payload.event == "call_ended" else "failed"),
        "duration_seconds": payload.duration_seconds,
        "transcript": payload.transcript,
        "summary": payload.summary,
        "recording_url": payload.recording_url,
        "outcome": payload.outcome,
    }
    updates = {k: v for k, v in updates.items() if v is not None}
    if updates:
        update("bolna_calls", updates, params={"call_id": f"eq.{payload.call_id}"})
    log.info("Bolna webhook event=%s call_id=%s", payload.event, payload.call_id)
    return {"ok": True}


# ----- Admin: outbound dial trigger ----------------------------------------

class DialRequest(BaseModel):
    phone: str
    name: str
    practice_area: Optional[str] = None
    city: Optional[str] = None
    court: Optional[str] = None
    source: Optional[str] = None
    agent_id: Optional[str] = None


@router.post("/dial")
async def dial_lead(req: DialRequest) -> dict[str, Any]:
    """Trigger an outbound Bolna call. Skips DND list. Bolna's call_id flows
    back through /webhook so we can stitch transcripts to leads."""
    if not BOLNA_API_KEY:
        raise HTTPException(503, "BOLNA_API_KEY not configured")
    agent_id = req.agent_id or BOLNA_AGENT_ID
    if not agent_id:
        raise HTTPException(503, "BOLNA_AGENT_ID not configured")

    phone = _normalize_phone(req.phone)

    if select("dnd_list", params={"phone": f"eq.{phone}", "select": "phone"}):
        return {"ok": False, "skipped": True, "reason": "on_dnd_list", "phone": phone}

    _upsert_lead(
        phone=phone, name=req.name,
        practice_area=req.practice_area, city=req.city,
        court=req.court, source=req.source, status="new",
    )

    async with httpx.AsyncClient(timeout=30.0) as client:
        # /call is at root (not under /v2) per Bolna API reference.
        resp = await client.post(
            f"{BOLNA_API_BASE.rstrip('/')}/call",
            headers={
                "Authorization": f"Bearer {BOLNA_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "agent_id": agent_id,
                "recipient_phone_number": phone,
                "user_data": {
                    "name": req.name,
                    "practice_area": req.practice_area or "general practice",
                    "city": req.city or "",
                    "court": req.court or "",
                    "source": req.source or "outbound_campaign",
                },
            },
        )

    if resp.status_code >= 300:
        log.error("Bolna dial failed phone=%s status=%s body=%s",
                  phone, resp.status_code, resp.text)
        raise HTTPException(502, f"bolna dial failed: {resp.status_code}")

    data = resp.json()
    return {"ok": True, "call_id": data.get("call_id") or data.get("id"), "phone": phone}
