"""WhatsApp drafting flow — Phase 4a MVP for bail §439.

Conversational slot collection: lawyer says `DRAFT BAIL`, bot asks for
each required slot in turn, then generates the draft via the existing
storage + stories engine, renders PDF, hosts at a token URL, and sends
the PDF link + canvas link back via WhatsApp.

NO LLM IN THE FLOW — everything is deterministic slot-fill.
PDF generation reuses the existing weasyprint path that the web app uses.

Spec: docs/WHATSAPP_BOT_PRD.md (Phase 4 — to be added).
Migration: migrations/007_whatsapp_drafting.sql.
"""
from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════ slot schemas

@dataclass(frozen=True)
class Slot:
    key: str                          # answers dict key
    prompt: str                       # what the bot asks
    transform: str = "raw"            # 'raw' | 'list' (split on commas)


BAIL_439_SLOTS: tuple[Slot, ...] = (
    Slot("court_name",
         "*Which court* will hear this application?\n"
         "Reply with court name + city, e.g. _Sessions Court, Bhopal_"),
    Slot("applicant_name",
         "*Full name of the applicant* (accused)?"),
    Slot("applicant_father",
         "*Father's name* of the applicant?"),
    Slot("applicant_address",
         "*Permanent address* of the applicant?\n_(House no, locality, city)_"),
    Slot("police_station",
         "*Police station* where the FIR is registered?"),
    Slot("district",
         "*District* of the police station?"),
    Slot("fir_number",
         "*FIR number* and year? e.g. _234/2024_"),
    Slot("sections",
         "*Sections charged* in the FIR? e.g. _420, 406 IPC_\n"
         "_(or just type 'unknown' if you don't have them)_",
         transform="list"),
    Slot("arrest_date",
         "*Date of arrest* (DD/MM/YYYY)? Type _unknown_ if not arrested yet."),
)

# Map story_id → ordered slots
SLOTS_BY_STORY: dict[str, tuple[Slot, ...]] = {
    "bail_application": BAIL_439_SLOTS,
}

# Static defaults to merge into the final answers dict (template fields the
# bail renderer needs that we don't ask in chat — they have placeholders).
STATIC_DEFAULTS: dict[str, dict[str, Any]] = {
    "bail_application": {
        "bail_section": "439",          # §439 CrPC / §483 BNSS
        "application_number": 1,        # 1st bail (vs. successive)
        "side_label": "बंदी की ओर से",
        "case_label": "विविध आपराधिक प्रकरण क्रमांक",
        "state_name": "मध्यप्रदेश",      # default; overridden if district hints otherwise
    },
}


# ════════════════════════════════════════════════════════════════ intent detection

# Phrases that start a new draft session
DRAFT_TRIGGERS = {
    # bail
    "draft bail": "bail_application",
    "bail draft": "bail_application",
    "bail application": "bail_application",
    "draft 439": "bail_application",
    "draft regular bail": "bail_application",
    "regular bail": "bail_application",
    "439 bail": "bail_application",
    "ज़मानत": "bail_application",
    "जमानत": "bail_application",
}

# Generic single-word "draft" → ask what to draft
GENERIC_DRAFT_KEYWORDS = {"draft", "drafting", "/draft"}


def detect_intent(text: str) -> dict[str, str] | None:
    """Returns {"action": "ask_what", "story_id": None}    → ask "what do you want to draft?"
              {"action": "start",    "story_id": "bail_application"} → start that draft
              {"action": "cancel"}                          → cancel any active draft
              {"action": "restart"}                         → restart active draft
              None                                          → not a draft intent
    """
    if not text:
        return None
    norm = " ".join(text.lower().split())

    # Cancel / restart take priority
    if norm in ("cancel", "stop draft", "cancel draft", "/cancel"):
        return {"action": "cancel"}
    if norm in ("restart", "restart draft", "/restart"):
        return {"action": "restart"}

    # Specific draft triggers
    for trigger, story_id in DRAFT_TRIGGERS.items():
        if trigger == norm or trigger in norm:
            return {"action": "start", "story_id": story_id}

    # Generic "draft" with nothing else
    if norm in GENERIC_DRAFT_KEYWORDS:
        return {"action": "ask_what"}

    return None


def first_prompt_for(story_id: str) -> str:
    """The bot's opening message after a draft is started."""
    slots = SLOTS_BY_STORY.get(story_id) or ()
    if not slots:
        return "I don't have that template yet. Try *DRAFT BAIL* for now."
    intro_by_story = {
        "bail_application": (
            "📝 Starting a *Regular Bail Application* (§483 BNSS / §439 CrPC).\n\n"
            "I'll ask you a few quick questions — under 2 minutes. "
            "Type *CANCEL* anytime to abort.\n\n"
        ),
    }
    intro = intro_by_story.get(story_id, "📝 Starting a draft.\n\n")
    return intro + slots[0].prompt


def what_to_draft_prompt() -> str:
    return (
        "📝 *What would you like to draft?*\n\n"
        "Available now:\n"
        "• *DRAFT BAIL* — Regular Bail Application (§439)\n\n"
        "_(Anticipatory bail, discharge, and more coming soon.)_"
    )


# ════════════════════════════════════════════════════════════════ session storage (Supabase)

def _sb_base() -> tuple[str, str] | None:
    base = os.environ.get("SUPABASE_URL", "").rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not (base and key):
        return None
    return base, key


def _sb_headers(key: str, *, prefer: str = "return=representation") -> dict[str, str]:
    return {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": prefer,
    }


async def load_session(wa_phone: str) -> Optional[dict]:
    cfg = _sb_base()
    if not cfg:
        return None
    base, key = cfg
    url = f"{base}/rest/v1/wa_draft_sessions?wa_phone=eq.{wa_phone}&select=*"
    try:
        async with httpx.AsyncClient(timeout=6.0) as ac:
            r = await ac.get(url, headers=_sb_headers(key))
        if r.status_code != 200:
            log.warning("load_session: %s %s", r.status_code, r.text[:200])
            return None
        rows = r.json() or []
        if not rows:
            return None
        row = rows[0]
        # Expire silently if past TTL
        exp = row.get("expires_at")
        if exp and time.time() > _ts(exp):
            await delete_session(wa_phone)
            return None
        return row
    except Exception:
        log.exception("load_session failed")
        return None


async def save_session(wa_phone: str, *, story_id: str, next_slot: str,
                       answers: dict, draft_id: Optional[str] = None) -> None:
    cfg = _sb_base()
    if not cfg:
        return
    base, key = cfg
    url = f"{base}/rest/v1/wa_draft_sessions"
    row = {
        "wa_phone": wa_phone,
        "story_id": story_id,
        "next_slot": next_slot,
        "answers": answers,
        "draft_id": draft_id,
        # updated_at auto-set via NOW() default? We're upserting so set it explicitly:
        "updated_at": _now_iso(),
    }
    headers = _sb_headers(key, prefer="resolution=merge-duplicates,return=minimal")
    headers["Prefer"] = "resolution=merge-duplicates,return=minimal"
    try:
        async with httpx.AsyncClient(timeout=6.0) as ac:
            r = await ac.post(url + "?on_conflict=wa_phone", headers=headers, json=row)
        if r.status_code not in (200, 201, 204):
            log.warning("save_session: %s %s", r.status_code, r.text[:200])
    except Exception:
        log.exception("save_session failed")


async def delete_session(wa_phone: str) -> None:
    cfg = _sb_base()
    if not cfg:
        return
    base, key = cfg
    url = f"{base}/rest/v1/wa_draft_sessions?wa_phone=eq.{wa_phone}"
    try:
        async with httpx.AsyncClient(timeout=6.0) as ac:
            await ac.delete(url, headers=_sb_headers(key, prefer="return=minimal"))
    except Exception:
        log.exception("delete_session failed")


# ════════════════════════════════════════════════════════════════ token storage

def _make_token() -> str:
    """Short URL-safe token. 22 chars of base32(uuid) is plenty of entropy."""
    return secrets.token_urlsafe(16)


async def mint_token(*, draft_id: str, wa_phone: str) -> Optional[str]:
    cfg = _sb_base()
    if not cfg:
        return None
    base, key = cfg
    token = _make_token()
    url = f"{base}/rest/v1/wa_draft_tokens"
    row = {"token": token, "draft_id": draft_id, "wa_phone": wa_phone}
    try:
        async with httpx.AsyncClient(timeout=6.0) as ac:
            r = await ac.post(url, headers=_sb_headers(key, prefer="return=minimal"), json=row)
        if r.status_code not in (200, 201, 204):
            log.warning("mint_token: %s %s", r.status_code, r.text[:200])
            return None
        return token
    except Exception:
        log.exception("mint_token failed")
        return None


async def resolve_token(token: str) -> Optional[dict]:
    """Returns {draft_id, wa_phone} if token valid + unexpired, else None."""
    cfg = _sb_base()
    if not cfg:
        return None
    base, key = cfg
    url = f"{base}/rest/v1/wa_draft_tokens?token=eq.{token}&select=*"
    try:
        async with httpx.AsyncClient(timeout=6.0) as ac:
            r = await ac.get(url, headers=_sb_headers(key))
        if r.status_code != 200:
            return None
        rows = r.json() or []
        if not rows:
            return None
        row = rows[0]
        if time.time() > _ts(row.get("expires_at", "")):
            return None
        return row
    except Exception:
        log.exception("resolve_token failed")
        return None


# ════════════════════════════════════════════════════════════════ slot transitions

def next_slot_after(story_id: str, current: str) -> Optional[str]:
    slots = SLOTS_BY_STORY.get(story_id) or ()
    keys = [s.key for s in slots]
    if current not in keys:
        return keys[0] if keys else None
    idx = keys.index(current)
    return keys[idx + 1] if idx + 1 < len(keys) else None


def slot_by_key(story_id: str, key: str) -> Optional[Slot]:
    for s in SLOTS_BY_STORY.get(story_id) or ():
        if s.key == key:
            return s
    return None


def apply_answer(slot: Slot, raw: str) -> Any:
    text = (raw or "").strip()
    if slot.transform == "list":
        if text.lower() in ("unknown", "skip", "-"):
            return []
        return [p.strip() for p in text.replace(";", ",").split(",") if p.strip()]
    return text


def build_full_answers(story_id: str, collected: dict) -> dict:
    """Merge static defaults + collected answers into the final dict the
    template renderer expects."""
    base = dict(STATIC_DEFAULTS.get(story_id) or {})
    base.update(collected or {})
    return base


# ════════════════════════════════════════════════════════════════ finalize draft

import asyncio  # noqa: E402  (kept here so the file is self-contained at the bottom)


async def finalize_draft(wa_phone: str, session: dict) -> dict:
    """Create the persistent draft row, mint a token, return URLs the
    bot can send back to the lawyer.

    Returns: {draft_id, pdf_url, canvas_url, summary_line}
    """
    from headnote.drafter import storage

    story_id = session.get("story_id") or "bail_application"
    answers = build_full_answers(story_id, session.get("answers") or {})

    # Create persistent draft. user_id=None — WhatsApp drafts have no Supabase
    # user yet (Phase 3 LINK flow will associate them).
    draft = await asyncio.to_thread(
        storage.create_draft,
        story_id=story_id,
        template_version=1,
        user_id=None,
        lang="hi",
        answers=answers,
        title=_draft_title(story_id, answers),
    )
    draft_id = draft.id

    token = await mint_token(draft_id=draft_id, wa_phone=wa_phone)
    if not token:
        log.error("mint_token returned None for draft %s", draft_id)

    base = os.environ.get("PUBLIC_BASE_URL", "https://headnote.in").rstrip("/")
    pdf_url    = f"{base}/api/whatsapp/draft/{token}/pdf" if token else None
    canvas_url = f"{base}/api/whatsapp/draft/{token}/view" if token else None

    summary = _draft_summary_line(story_id, answers)

    return {
        "draft_id": draft_id,
        "pdf_url": pdf_url,
        "canvas_url": canvas_url,
        "summary_line": summary,
    }


def _draft_title(story_id: str, answers: dict) -> str:
    if story_id == "bail_application":
        nm = (answers.get("applicant_name") or "applicant").split()[0]
        fir = answers.get("fir_number") or ""
        return f"Bail § 439 — {nm}" + (f" — FIR {fir}" if fir else "")
    return f"WhatsApp draft — {story_id}"


def _draft_summary_line(story_id: str, answers: dict) -> str:
    if story_id == "bail_application":
        nm = answers.get("applicant_name") or "applicant"
        fir = answers.get("fir_number") or "—"
        ps = answers.get("police_station") or "—"
        sections = answers.get("sections") or []
        if isinstance(sections, list):
            sec_str = ", ".join(sections) if sections else "—"
        else:
            sec_str = str(sections)
        return f"{nm} · FIR {fir} · PS {ps} · u/s {sec_str}"
    return story_id


async def render_pdf_for_token(token: str) -> tuple[bytes | None, str | None]:
    """Resolve token → fetch draft → render HTML → PDF bytes.

    Returns (pdf_bytes, error_msg). Exactly one of the two is non-None.
    """
    tok = await resolve_token(token)
    if not tok:
        return None, "Token expired or invalid"

    draft_id = tok["draft_id"]

    from headnote.drafter import storage, stories
    from headnote.api.pdf import _render_pdf

    try:
        draft = await asyncio.to_thread(storage.get_draft, draft_id)
    except Exception:
        log.exception("storage.get_draft failed for %s", draft_id)
        return None, "Draft lookup failed"
    if draft is None:
        return None, "Draft not found"

    try:
        html = await asyncio.to_thread(
            stories.render_story, draft.story_id, draft.lang or "hi", draft.answers or {}
        )
    except Exception:
        log.exception("render_story failed for %s", draft_id)
        return None, "Render failed"

    # Wrap the document HTML in a minimum page wrapper that weasyprint expects.
    # The bail render returns the inner doc fragment; the PDF endpoint normally
    # gets a full page with #doc-page. We synthesize that wrapper here.
    full_html = _wrap_html_for_pdf(html)

    try:
        pdf_bytes = await asyncio.to_thread(_render_pdf, full_html)
    except Exception:
        log.exception("PDF render failed for %s", draft_id)
        return None, "PDF render failed"

    return pdf_bytes, None


def _wrap_html_for_pdf(inner: str) -> str:
    return (
        "<!doctype html><html><head><meta charset='utf-8'>"
        "<style>"
        "body { font-family: 'Tiro Devanagari Hindi', 'Noto Serif Devanagari', "
        "'Times New Roman', serif; font-size: 12pt; line-height: 1.7; "
        "color: #0c0c0a; margin: 0; padding: 0; }"
        "#doc-page { padding: 25mm 22mm; }"
        "h1, h2, h3 { font-weight: 600; }"
        "table { width: 100%; border-collapse: collapse; }"
        "table td, table th { padding: 4pt 6pt; vertical-align: top; "
        "border: 1px solid #888; }"
        "p { margin: 0.5em 0; }"
        ".center { text-align: center; }"
        ".right { text-align: right; }"
        "</style></head><body>"
        f"<div id='doc-page'>{inner}</div>"
        "</body></html>"
    )


async def render_html_for_token(token: str) -> tuple[str | None, str | None]:
    """Resolve token → fetch draft → render HTML preview (no PDF conversion)."""
    tok = await resolve_token(token)
    if not tok:
        return None, "Token expired or invalid"

    draft_id = tok["draft_id"]
    from headnote.drafter import storage, stories

    try:
        draft = await asyncio.to_thread(storage.get_draft, draft_id)
    except Exception:
        log.exception("storage.get_draft failed for %s", draft_id)
        return None, "Draft lookup failed"
    if draft is None:
        return None, "Draft not found"

    try:
        html = await asyncio.to_thread(
            stories.render_story, draft.story_id, draft.lang or "hi", draft.answers or {}
        )
    except Exception:
        log.exception("render_story failed for %s", draft_id)
        return None, "Render failed"

    return html, None


# ════════════════════════════════════════════════════════════════ helpers

def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()


def _ts(iso: str) -> float:
    """Parse an ISO timestamp → unix seconds. Returns 0 on failure."""
    try:
        from datetime import datetime
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0.0
