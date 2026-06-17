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
from headnote.whatsapp import drafting as wa_drafting
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

@router.get("/e2e")
async def e2e_test(to: str = "", q: str = "", bg: int = 0) -> dict:
    """End-to-end test: runs the SAME path the webhook runs, returns
    the full trace, and (if to=+phone given) actually sends the result
    via Twilio. Use to debug "ghosted messages" without needing the
    Railway log access.

    Usage:
      GET /api/whatsapp/e2e?q=section+138+NI+Act
        → run research synchronously, return formatted body (no send)
      GET /api/whatsapp/e2e?to=%2B917000362336&q=section+138+NI+Act&bg=0
        → run sync + send to that phone (returns trace)
      GET /api/whatsapp/e2e?to=%2B917000362336&q=section+138+NI+Act&bg=1
        → spawn bg task identical to webhook's (returns spawn confirmation;
          bg task delivers to WhatsApp when done)
    """
    import io, logging as _logging, time as _t

    if not q:
        q = "Section 138 NI Act recent SC on territorial jurisdiction"

    # Capture log output from the wa modules during this run
    log_buf = io.StringIO()
    handler = _logging.StreamHandler(log_buf)
    handler.setLevel(_logging.DEBUG)
    handler.setFormatter(_logging.Formatter("%(asctime)s %(name)s %(levelname)s %(message)s"))
    root = _logging.getLogger()
    prior_level = root.level
    root.addHandler(handler)
    root.setLevel(_logging.DEBUG)

    trace: dict = {"query": q, "to": to or None, "bg": bool(bg)}
    t0 = _t.time()
    try:
        if bg and to:
            _spawn_bg(_run_research_and_reply(to, q, "twilio"))
            await asyncio.sleep(0.05)  # let it start
            trace["spawned"] = True
            trace["bg_tasks_in_flight"] = len(_BG_TASKS)
        else:
            # Sync path — run research, optionally send
            reply = await wa_research.run_research(q)
            trace["research_elapsed_seconds"] = round(_t.time() - t0, 1)
            trace["reply_preview"] = (reply or "")[:300]
            trace["reply_len"] = len(reply or "")
            if to:
                t_send = _t.time()
                try:
                    resp = wa.send_text(to, reply, provider="twilio")
                    trace["send_ok"] = True
                    trace["send_elapsed_seconds"] = round(_t.time() - t_send, 1)
                    trace["twilio_sid"] = resp.get("sid")
                    trace["twilio_status"] = resp.get("status")
                except Exception as exc:
                    trace["send_ok"] = False
                    trace["send_error_type"] = type(exc).__name__
                    trace["send_error"] = str(exc)[:500]
    except Exception as exc:
        trace["fatal_error_type"] = type(exc).__name__
        trace["fatal_error"] = str(exc)[:500]
    finally:
        root.removeHandler(handler)
        root.setLevel(prior_level)
        trace["total_elapsed_seconds"] = round(_t.time() - t0, 1)
        trace["captured_logs"] = log_buf.getvalue().splitlines()[-80:]
    return trace


@router.get("/draft/{token}/pdf")
async def draft_pdf(token: str) -> Response:
    """Serve a draft as PDF via a short-lived (24h) token. Public — no
    Supabase auth needed. The token IS the auth (~160 bits of entropy)."""
    pdf_bytes, err = await wa_drafting.render_pdf_for_token(token)
    if err or not pdf_bytes:
        raise HTTPException(status_code=404, detail=err or "Draft not found")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": 'inline; filename="headnote-bail-draft.pdf"'},
    )


@router.get("/draft/{token}/view")
async def draft_view(token: str) -> Response:
    """In-browser viewer for a draft. Shows the rendered HTML with
    Download PDF + (later) Edit-on-canvas buttons. Public via the same
    short-lived token. Phase 4a — preview-only; canvas editor lands in 4b.
    """
    html, err = await wa_drafting.render_html_for_token(token)
    if err or not html:
        raise HTTPException(status_code=404, detail=err or "Draft not found")

    page = _wrap_viewer_html(html, token)
    return Response(content=page, media_type="text/html; charset=utf-8")


def _wrap_viewer_html(inner: str, token: str) -> str:
    """Self-contained viewer page — Kruti Dev font embedded, Download PDF
    button, link back to Headnote. No JS frameworks, no Supabase login."""
    return f"""<!doctype html>
<html lang="hi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Headnote — Bail Draft</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;500;600&family=Tiro+Devanagari+Hindi:ital@0;1&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<style>
  @font-face {{
    font-family: 'KrutiDev010';
    src: url('/static/fonts/KrutiDev010.ttf') format('truetype');
    font-display: swap;
  }}
  :root {{
    --bg: #fdfcf9; --paper: #ffffff; --ink: #0c0c0a;
    --muted: #6b6960; --line: rgba(12,12,10,0.12); --gold: #b8924e;
  }}
  * {{ box-sizing: border-box; }}
  html, body {{
    margin: 0; background: var(--bg); color: var(--ink);
    font-family: 'Inter', -apple-system, sans-serif;
  }}
  .topbar {{
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 20px; border-bottom: 1px solid var(--line);
    background: var(--paper); position: sticky; top: 0; z-index: 10;
  }}
  .topbar .brand {{ font-weight: 600; }}
  .topbar .actions {{ display: flex; gap: 10px; }}
  .btn {{
    display: inline-flex; align-items: center; gap: 6px;
    padding: 8px 16px; border-radius: 8px; border: 1px solid var(--ink);
    background: var(--ink); color: var(--paper); text-decoration: none;
    font-size: 14px; font-weight: 500; cursor: pointer;
  }}
  .btn--ghost {{ background: var(--paper); color: var(--ink); }}
  .doc-wrap {{ max-width: 800px; margin: 28px auto; padding: 0 16px; }}
  .doc {{
    background: var(--paper); padding: 30mm 22mm; min-height: 270mm;
    border: 1px solid var(--line); border-radius: 4px;
    box-shadow: 0 2px 10px rgba(0,0,0,0.04);
    font-family: 'Tiro Devanagari Hindi', 'Noto Sans Devanagari', serif;
    font-size: 13pt; line-height: 1.75; color: var(--ink);
  }}
  .doc h1, .doc h2, .doc h3 {{ font-weight: 600; }}
  .doc table {{ width: 100%; border-collapse: collapse; margin: 12px 0; }}
  .doc table td, .doc table th {{
    padding: 6px 8px; border: 1px solid #888; vertical-align: top;
  }}
  .doc .center {{ text-align: center; }}
  .doc .right {{ text-align: right; }}
  .footer {{
    text-align: center; margin: 30px 0; color: var(--muted); font-size: 12px;
  }}
  .footer a {{ color: var(--gold); }}
  @media (max-width: 640px) {{
    .doc {{ padding: 18mm 12mm; font-size: 11pt; }}
    .topbar {{ padding: 12px 14px; }}
    .topbar .brand {{ font-size: 14px; }}
    .btn {{ padding: 6px 12px; font-size: 13px; }}
  }}
</style>
</head>
<body>
<div class="topbar">
  <div class="brand">📘 Headnote — Bail Draft</div>
  <div class="actions">
    <a href="/api/whatsapp/draft/{token}/pdf" download="headnote-bail-draft.pdf" class="btn">📄 Download PDF</a>
  </div>
</div>
<div class="doc-wrap">
  <div class="doc">{inner}</div>
  <div class="footer">
    Generated via WhatsApp on Headnote · this link expires in 24 hours ·
    <a href="https://headnote.in">headnote.in</a>
  </div>
</div>
</body>
</html>
"""


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

    # ───────── Drafting flow takes priority if a session is active ─────────
    if await _handle_drafting(msg.wa_phone, text, provider_name):
        return

    # Keyword routes (fast, synchronous)
    if not text:
        await _send_reply(msg.wa_phone, wa_research._short_query_hint(""), provider_name)
        return

    if upper in {"HELP", "?", "/HELP"}:
        await _send_reply(msg.wa_phone, wa_research.help_message(), provider_name)
        return

    if upper in {"HI", "HELLO", "HEY", "START"}:
        # Welcome message now includes the Draft option
        await _send_reply(msg.wa_phone, _welcome_message(), provider_name)
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


# ════════════════════════════════════════════════════════════════ drafting flow

def _welcome_message() -> str:
    return (
        "👋 Welcome to *Headnote* — citation-checked Indian legal work on WhatsApp.\n\n"
        "What can I help with?\n\n"
        "🔎 *Research* — just send a legal question, e.g.\n"
        "   _Section 138 NI Act recent SC on territorial jurisdiction_\n\n"
        "📝 *Draft* — type *DRAFT BAIL* to start a bail application (§439)\n\n"
        "Send *HELP* for examples."
    )


async def _handle_drafting(wa_phone: str, text: str, provider_name: str) -> bool:
    """Handle a message as part of a drafting flow.

    Returns True if consumed by drafting (caller stops). False = no draft
    action; caller proceeds to research / keyword routes.
    """
    session = await wa_drafting.load_session(wa_phone)
    intent = wa_drafting.detect_intent(text)

    if intent and intent.get("action") == "cancel":
        if session:
            await wa_drafting.delete_session(wa_phone)
            await _send_reply(
                wa_phone,
                "✅ Draft cancelled. Send *DRAFT BAIL* to start over, or send any legal research question.",
                provider_name,
            )
        else:
            await _send_reply(wa_phone, "No active draft to cancel.", provider_name)
        return True

    if intent and intent.get("action") == "restart":
        await wa_drafting.delete_session(wa_phone)
        session = None

    if intent and intent.get("action") == "start":
        story_id = intent["story_id"]
        slots = wa_drafting.SLOTS_BY_STORY.get(story_id) or ()
        if not slots:
            await _send_reply(wa_phone, "That draft type isn't supported yet. Try *DRAFT BAIL*.", provider_name)
            return True
        first_key = slots[0].key
        await wa_drafting.save_session(
            wa_phone, story_id=story_id, next_slot=first_key, answers={},
        )
        await _send_reply(wa_phone, wa_drafting.first_prompt_for(story_id), provider_name)
        return True

    if intent and intent.get("action") == "ask_what":
        await _send_reply(wa_phone, wa_drafting.what_to_draft_prompt(), provider_name)
        return True

    if session:
        await _advance_drafting_session(session, text, provider_name)
        return True

    return False


async def _advance_drafting_session(session: dict, text: str, provider_name: str) -> None:
    """Apply the user's answer to the current slot; prompt next or finalize."""
    wa_phone = session["wa_phone"]
    story_id = session["story_id"]
    current_slot_key = session["next_slot"]

    if current_slot_key in ("review", "done"):
        await wa_drafting.delete_session(wa_phone)
        await _send_reply(
            wa_phone,
            "Draft already done. Type *DRAFT BAIL* to start a new one.",
            provider_name,
        )
        return

    slot = wa_drafting.slot_by_key(story_id, current_slot_key)
    if not slot:
        log.error("unknown slot %s for story %s", current_slot_key, story_id)
        await wa_drafting.delete_session(wa_phone)
        await _send_reply(
            wa_phone,
            "⚠️ Draft session error. Send *DRAFT BAIL* to start over.",
            provider_name,
        )
        return

    answers = dict(session.get("answers") or {})
    answers[slot.key] = wa_drafting.apply_answer(slot, text)
    next_key = wa_drafting.next_slot_after(story_id, current_slot_key)

    if next_key:
        await wa_drafting.save_session(
            wa_phone, story_id=story_id, next_slot=next_key, answers=answers,
        )
        next_slot = wa_drafting.slot_by_key(story_id, next_key)
        if next_slot:
            await _send_reply(wa_phone, next_slot.prompt, provider_name)
        return

    # Final slot answered → finalize in background
    await _send_reply(
        wa_phone,
        "🛠️ Generating your bail application — this takes ~15 seconds. Hang on.",
        provider_name,
    )
    log.info("wa drafting FINALIZE phone=%s story=%s", wa_phone, story_id)
    _spawn_bg(_finalize_and_send(wa_phone, dict(session, answers=answers), provider_name))


async def _finalize_and_send(wa_phone: str, session: dict, provider_name: str) -> None:
    try:
        result = await wa_drafting.finalize_draft(wa_phone, session)
    except Exception:
        log.exception("wa drafting FINALIZE_CRASH phone=%s", wa_phone)
        await _try_send_with_fallback(
            wa_phone,
            "⚠️ Couldn't generate the draft. Try sending *DRAFT BAIL* again.",
            provider_name,
        )
        return

    await wa_drafting.delete_session(wa_phone)

    pdf_url    = result.get("pdf_url")
    canvas_url = result.get("canvas_url")
    summary    = result.get("summary_line") or ""

    lines = [
        "📎 *Your bail application is ready.*",
        "",
        summary,
        "",
        f"📄 PDF: {pdf_url}" if pdf_url else "",
        f"✏️ Edit & download .docx: {canvas_url}" if canvas_url else "",
        "",
        "_Links expire in 24 hours. Save the PDF locally before then._",
        "",
        "Need another? Send *DRAFT BAIL*, or any research question.",
    ]
    reply = "\n".join(l for l in lines if l is not None)
    await _try_send_with_fallback(wa_phone, reply, provider_name)


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
    # Send with size-aware retry — Twilio caps WhatsApp at 1600 chars; if
    # the formatter slipped past that we retry truncated rather than ghost.
    sent = await _try_send_with_fallback(wa_phone, reply, provider_name)
    log.info("wa bg SENT phone=%s ok=%s total_elapsed=%.1fs",
             wa_phone, sent, _t.time() - t0)


async def _try_send_with_fallback(wa_phone: str, body: str, provider_name: str) -> bool:
    """Attempt full send; on Twilio size-error retry truncated. Returns True on any successful send."""
    try:
        await _send_reply(wa_phone, body, provider_name)
        return True
    except Exception:  # noqa: BLE001
        log.exception("wa primary send failed; trying truncated fallback")

    # Fallback: aggressive truncation
    truncated = body[:1400].rstrip() + "\n\n_(response trimmed — reply with a narrower query for more)_"
    try:
        await _send_reply(wa_phone, truncated, provider_name)
        return True
    except Exception:
        log.exception("wa truncated send failed; trying minimal fallback")

    # Last resort — at least tell the user something
    try:
        await _send_reply(
            wa_phone,
            "⚠️ Your research result was generated but couldn't be delivered "
            "(message too long or carrier error). Please reply with a narrower "
            "query, or send *HELP* for examples.",
            provider_name,
        )
        return True
    except Exception:
        log.exception("wa minimal fallback also failed; user will see nothing")
        return False


async def _send_reply(wa_phone: str, body: str, provider_name: str) -> bool:
    """Outbound send + log. Returns True on success, False on failure (and logs).

    Callers wrapping this in fallback logic depend on the return value, so we
    don't double-swallow — exceptions still bubble for callers that prefer
    to handle them; but the success/failure is also surfaced as a bool.
    """
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
        return True
    except wa.WAClientError as exc:
        log.error("send via %s to %s failed: %s", provider_name, wa_phone, exc)
        raise
    except Exception:
        log.exception("unexpected send error to %s", wa_phone)
        raise


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
