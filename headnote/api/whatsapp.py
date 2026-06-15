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

import asyncio
import logging
import os
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, Response

from headnote.whatsapp import client as wa
from headnote.whatsapp import research as wa_research
from headnote.whatsapp.providers import InboundMessage

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/whatsapp", tags=["whatsapp"])

# Hold strong references to background tasks so Python's GC doesn't collect
# them mid-execution. Without this, asyncio.create_task() returns a Task that
# can be reclaimed before the coroutine finishes — and the user never gets a
# reply. See: https://docs.python.org/3/library/asyncio-task.html#asyncio.create_task
_BG_TASKS: set = set()


def _spawn_bg(coro) -> None:
    """asyncio.create_task with GC-safety + crash logging."""
    task = asyncio.create_task(coro)
    _BG_TASKS.add(task)
    def _on_done(t):
        _BG_TASKS.discard(t)
        if t.cancelled():
            log.warning("wa bg task cancelled")
            return
        exc = t.exception()
        if exc is not None:
            log.error("wa bg task crashed: %r", exc, exc_info=exc)
    task.add_done_callback(_on_done)


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

@router.get("/research-diag")
async def research_diag(q: str = "") -> dict:
    """Diagnostic — runs the situation pipeline for a query and returns
    a slimmed view of the raw response. Used to debug why we're getting
    "no cases" replies.
    """
    if not q:
        q = "Section 138 NI Act recent Supreme Court on territorial jurisdiction of cheque dishonour"

    from headnote.api.app import _api_situation_impl
    from headnote.api.models import SituationRequest
    import time as _time

    out: dict = {"query": q, "stages": {}}
    t0 = _time.time()
    try:
        req = SituationRequest(situation=q, style="practitioner", deep_mode=False, mode="famous")
        out["stages"]["request_built"] = True
    except Exception as exc:
        out["error_stage"] = "request"
        out["error"] = repr(exc)
        return out

    def _record(**_kw): pass

    try:
        result = await asyncio.to_thread(_api_situation_impl, req, _record)
        out["stages"]["pipeline_ran_seconds"] = round(_time.time() - t0, 1)
    except Exception as exc:
        out["error_stage"] = "pipeline"
        out["error"] = repr(exc)
        out["elapsed"] = round(_time.time() - t0, 1)
        return out

    # Cases are nested under response.result.cases (not at top level)
    inner = (result or {}).get("result") or {}
    cases = inner.get("cases") or []
    out["case_count"] = len(cases)
    out["confidence"] = inner.get("confidence")
    out["top_level_keys"] = list((result or {}).keys())
    if cases:
        c0 = cases[0]
        out["case_0_sample"] = {
            "title": c0.get("title"),
            "citation": c0.get("citation"),
            "neutral_citation": c0.get("neutral_citation"),
            "scr_citation": c0.get("scr_citation"),
            "court": c0.get("court"),
            "year": c0.get("year"),
            "official_pdf_url": c0.get("official_pdf_url"),
            "verification_flags": c0.get("verification_flags"),
            "paragraph_anchor": c0.get("paragraph_anchor"),
            "has_practitioner_notes": bool(c0.get("practitioner_notes")),
        }
        # Run the formatter so we see what WhatsApp would actually receive
        from headnote.whatsapp import research as _wa_research
        out["formatted_for_whatsapp"] = _wa_research.format_situation_response(result, query=q)
    return out


@router.get("/twilio/diag")
async def twilio_diag(to: str = "") -> dict:
    """Diagnostic — shows env state and tries an outbound send, returning
    Twilio's exact response. Used to debug why echo isn't reaching users.

    Usage:  GET /api/whatsapp/twilio/diag?to=%2B919876543210
            (URL-encode the +; raw + becomes a space in query strings)
    """
    env = {
        "WA_PROVIDER": os.environ.get("WA_PROVIDER"),
        "TWILIO_ACCOUNT_SID_prefix": (os.environ.get("TWILIO_ACCOUNT_SID", "") or "")[:8] or None,
        "TWILIO_ACCOUNT_SID_set": bool(os.environ.get("TWILIO_ACCOUNT_SID")),
        "TWILIO_AUTH_TOKEN_set": bool(os.environ.get("TWILIO_AUTH_TOKEN")),
        "TWILIO_AUTH_TOKEN_len": len(os.environ.get("TWILIO_AUTH_TOKEN", "") or ""),
        "TWILIO_WA_FROM": os.environ.get("TWILIO_WA_FROM"),
        "TWILIO_SKIP_SIGNATURE_VERIFY": os.environ.get("TWILIO_SKIP_SIGNATURE_VERIFY"),
        "SUPABASE_URL_set": bool(os.environ.get("SUPABASE_URL")),
        "SUPABASE_SERVICE_ROLE_KEY_set": bool(os.environ.get("SUPABASE_SERVICE_ROLE_KEY")),
    }
    if not to:
        return {"env": env, "hint": "add ?to=%2B91XXXXXXXXXX to test an outbound send"}

    try:
        resp = wa.send_text(to, "Headnote diag probe — if you see this, outbound works.", provider="twilio")
        return {"env": env, "send_ok": True, "twilio_response": resp}
    except Exception as exc:  # noqa: BLE001
        return {
            "env": env,
            "send_ok": False,
            "error_type": type(exc).__name__,
            "error": str(exc),
        }


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
    """Dispatch: keywords get a synchronous reply, research queries get an
    immediate ack + a background task that runs the pipeline and sends the
    formatted result when ready.
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
        await _send_reply(
            msg.wa_phone,
            "I can only read text messages right now. Send me a legal research question to try.",
            provider_name,
        )
        return

    text = (msg.body or "").strip()
    upper = text.upper()

    # Keyword routes (fast, synchronous)
    if not text:
        await _send_reply(msg.wa_phone, wa_research._short_query_hint(""), provider_name)
        return

    if upper in {"HELP", "?", "/HELP"}:
        await _send_reply(msg.wa_phone, wa_research.help_message(), provider_name)
        return

    if upper in {"HI", "HELLO", "HEY", "START"}:
        await _send_reply(msg.wa_phone, wa_research._short_query_hint(""), provider_name)
        return

    if upper == "STOP":
        # TODO Phase 3: persist unsubscribe in wa_users
        await _send_reply(
            msg.wa_phone,
            "You won't receive further messages. Reply START to re-enable.",
            provider_name,
        )
        return

    if upper == "LINK":
        # TODO Phase 3: OTP-based linkage to existing paid account
        await _send_reply(
            msg.wa_phone,
            "🔗 Account linking is coming soon. During beta, research is unlimited.",
            provider_name,
        )
        return

    # Too short to be a meaningful query
    if len(text) < 10:
        await _send_reply(msg.wa_phone, wa_research._short_query_hint(text), provider_name)
        return

    # Research path — ack now, work in background. Twilio's webhook ack
    # window is ~10s and a real research call is 60–90s, so we MUST split.
    await _send_reply(
        msg.wa_phone,
        "🔎 Searching the corpus for citations… give me ~60–90 seconds.",
        provider_name,
    )
    log.info("wa bg dispatch: phone=%s len=%d", msg.wa_phone, len(text))
    _spawn_bg(_run_research_and_reply(msg.wa_phone, text, provider_name))


async def _run_research_and_reply(wa_phone: str, query: str, provider_name: str) -> None:
    """Background task — runs the heavy pipeline, sends the formatted result.

    Loud logging at every step so Railway log shows where slow runs go.
    """
    import time as _t
    t0 = _t.time()
    log.info("wa bg START phone=%s len=%d", wa_phone, len(query))
    try:
        reply = await wa_research.run_research(query)
        log.info("wa bg PIPELINE_OK phone=%s elapsed=%.1fs len_reply=%d",
                 wa_phone, _t.time() - t0, len(reply))
    except Exception:  # noqa: BLE001
        log.exception("wa bg PIPELINE_CRASH phone=%s elapsed=%.1fs",
                      wa_phone, _t.time() - t0)
        reply = (
            "⚠️ Sorry — the research engine hit an unexpected error. "
            "Try again in a moment, or send *HELP* for examples."
        )
    try:
        await _send_reply(wa_phone, reply, provider_name)
        log.info("wa bg SENT phone=%s total_elapsed=%.1fs",
                 wa_phone, _t.time() - t0)
    except Exception:  # noqa: BLE001
        log.exception("wa bg SEND_CRASH phone=%s", wa_phone)


async def _send_reply(wa_phone: str, body: str, provider_name: str) -> None:
    """Outbound send + log, swallowing provider errors so we never crash the
    background loop. Errors land in logs."""
    try:
        resp = wa.send_text(wa_phone, body, provider=provider_name)
        out_id = (
            (resp.get("messages") or [{}])[0].get("id")
            or resp.get("sid")
            or ""
        )
        await _log_message(
            wa_phone=wa_phone,
            direction="out",
            msg_type="text",
            body=body[:500],
            meta_msg_id=out_id,
        )
    except wa.WAClientError as exc:
        log.error("send via %s to %s failed: %s", provider_name, wa_phone, exc)
    except Exception:  # noqa: BLE001
        log.exception("unexpected send error to %s", wa_phone)


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
