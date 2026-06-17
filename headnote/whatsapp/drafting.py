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


BAIL_FIELDS: tuple[tuple[str, str, str], ...] = (
    # (key, label_for_template, transform)
    ("court_name",        "Court",            "raw"),
    ("applicant_name",    "Applicant name",   "raw"),
    ("applicant_father",  "Father's name",    "raw"),
    ("applicant_address", "Address",          "raw"),
    ("police_station",    "Police station",   "raw"),
    ("district",          "District",         "raw"),
    ("fir_number",        "FIR no & year",    "raw"),
    ("sections",          "Sections",         "list"),
    ("arrest_date",       "Date of arrest",   "raw"),
)

# Field labels that the parser will recognise (lowercase, alternative spellings)
_FIELD_ALIASES: dict[str, str] = {
    # court_name
    "court": "court_name", "court name": "court_name",
    # applicant_name
    "applicant name": "applicant_name", "applicant": "applicant_name",
    "name": "applicant_name", "accused": "applicant_name",
    "accused name": "applicant_name",
    # applicant_father
    "father": "applicant_father", "father name": "applicant_father",
    "father's name": "applicant_father", "fathers name": "applicant_father",
    "s/o": "applicant_father", "son of": "applicant_father",
    # applicant_address
    "address": "applicant_address", "applicant address": "applicant_address",
    "residence": "applicant_address",
    # police_station
    "police station": "police_station", "ps": "police_station",
    "p.s": "police_station", "p.s.": "police_station", "thana": "police_station",
    # district
    "district": "district", "dist": "district",
    # fir_number
    "fir no": "fir_number", "fir number": "fir_number", "fir": "fir_number",
    "fir no & year": "fir_number", "fir no and year": "fir_number",
    "crime no": "fir_number", "crime number": "fir_number",
    # sections
    "sections": "sections", "section": "sections", "u/s": "sections",
    "sections charged": "sections", "charged under": "sections",
    "offence sections": "sections",
    # arrest_date
    "arrest date": "arrest_date", "date of arrest": "arrest_date",
    "arrest": "arrest_date", "gir": "arrest_date",
}


def single_message_template_for(story_id: str, *, variant: str = "sessions") -> str:
    """Return the multi-line template the bot sends; lawyer fills + replies."""
    if story_id == "bail_application":
        kind = "High Court Bail (§439 — successive)" if variant == "hc" \
               else "Regular Bail Application (§483 BNSS / §439 CrPC)"
        court_example = "High Court of Madhya Pradesh, Jabalpur" if variant == "hc" \
                        else "Sessions Court, Bhopal"
        return (
            f"📝 *{kind}* — fill the template below.\n\n"
            "Copy this whole block, fill values after the colon, send back as *ONE message*:\n\n"
            "```\n"
            f"Court: {court_example}\n"
            "Applicant name: \n"
            "Father's name: \n"
            "Address: \n"
            "Police station: \n"
            "District: \n"
            "FIR no & year: \n"
            "Sections: \n"
            "Arrest date: \n"
            "```\n\n"
            "💡 *Faster:* skip typing entirely — just *upload the FIR photo* "
            "and I'll extract everything automatically.\n\n"
            + ("📑 *HC bail tip:* upload the *Sessions Court order* (rejection) "
               "if you have it — adds prior-bail history to your draft.\n\n"
               if variant == "hc" else "")
            + "Type *CANCEL* anytime to abort."
        )
    return "Template not configured for this draft type."


def parse_single_message_reply(text: str) -> dict[str, Any]:
    """Parse a multi-line 'key: value' reply into the bail answers dict.

    Forgiving — accepts numbered prefixes (1.), bullet points (-), and a wide
    set of label aliases. Unknown lines are ignored.
    """
    out: dict[str, Any] = {}
    import re as _re
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # strip leading bullet / number markers
        line = _re.sub(r"^[\-\*•]\s*", "", line)
        line = _re.sub(r"^\d+[\.\)]\s*", "", line)
        line = line.strip("` ").rstrip()
        if ":" not in line:
            continue
        label, _, value = line.partition(":")
        label_norm = label.strip().lower()
        value = value.strip(" `_*")
        if not value:
            continue
        key = _FIELD_ALIASES.get(label_norm)
        if not key:
            # try collapsing whitespace, dropping punctuation
            squashed = _re.sub(r"[^a-z ]", "", label_norm).strip()
            key = _FIELD_ALIASES.get(squashed)
        if not key:
            continue
        # Transform per field
        if key == "sections":
            out[key] = [
                p.strip() for p in _re.split(r"[,;/]| and ", value) if p.strip()
            ]
        else:
            out[key] = value
    return out


# Backward compat: still expose a slot list for the per-field flow if ever needed
BAIL_439_SLOTS: tuple[Slot, ...] = tuple(
    Slot(key=k, prompt=f"*{label}*?", transform=t) for k, label, t in BAIL_FIELDS
)

SLOTS_BY_STORY: dict[str, tuple[Slot, ...]] = {
    "bail_application": BAIL_439_SLOTS,
}


def _bail_static_defaults(variant: str = "sessions") -> dict[str, Any]:
    base: dict[str, Any] = {
        "bail_section": "439",
        "side_label": "बंदी की ओर से",
        "case_label": "विविध आपराधिक प्रकरण क्रमांक",
        "state_name": "मध्यप्रदेश",
    }
    if variant == "hc":
        base["application_number"] = 2     # successive
    else:
        base["application_number"] = 1
    return base


STATIC_DEFAULTS: dict[str, dict[str, Any]] = {
    "bail_application": _bail_static_defaults("sessions"),
}


# ════════════════════════════════════════════════════════════════ intent detection

# Phrases that start a new draft session. Each value: (story_id, variant)
# variant: 'sessions' (default §439 Sessions) or 'hc' (High Court successive bail)
DRAFT_TRIGGERS: dict[str, tuple[str, str]] = {
    # Sessions / first bail
    "draft bail":           ("bail_application", "sessions"),
    "bail draft":           ("bail_application", "sessions"),
    "bail application":     ("bail_application", "sessions"),
    "draft 439":            ("bail_application", "sessions"),
    "439 bail":             ("bail_application", "sessions"),
    "draft regular bail":   ("bail_application", "sessions"),
    "regular bail":         ("bail_application", "sessions"),
    "draft sessions bail":  ("bail_application", "sessions"),
    "sessions bail":        ("bail_application", "sessions"),
    "ज़मानत":               ("bail_application", "sessions"),
    "जमानत":                ("bail_application", "sessions"),

    # High Court / successive bail
    "draft hc bail":        ("bail_application", "hc"),
    "draft high court bail":("bail_application", "hc"),
    "high court bail":      ("bail_application", "hc"),
    "hc bail":              ("bail_application", "hc"),
    "draft 439 hc":         ("bail_application", "hc"),
    "successive bail":      ("bail_application", "hc"),
}

# Generic single-word "draft" → ask what to draft
GENERIC_DRAFT_KEYWORDS = {"draft", "drafting", "/draft"}


def detect_intent(text: str) -> dict[str, Any] | None:
    """Returns one of:
      {"action": "ask_what"}
      {"action": "start", "story_id": "...", "variant": "sessions"|"hc"}
      {"action": "cancel"}
      {"action": "restart"}
      None
    """
    if not text:
        return None
    norm = " ".join(text.lower().split())

    if norm in ("cancel", "stop draft", "cancel draft", "/cancel"):
        return {"action": "cancel"}
    if norm in ("restart", "restart draft", "/restart"):
        return {"action": "restart"}

    # Specific draft triggers — prefer LONGEST match to avoid 'bail' eating 'hc bail'
    matches = [
        (trigger, story_id, variant)
        for trigger, (story_id, variant) in DRAFT_TRIGGERS.items()
        if trigger == norm or trigger in norm
    ]
    if matches:
        matches.sort(key=lambda m: -len(m[0]))
        _t, story_id, variant = matches[0]
        return {"action": "start", "story_id": story_id, "variant": variant}

    if norm in GENERIC_DRAFT_KEYWORDS:
        return {"action": "ask_what"}

    return None


def first_prompt_for(story_id: str, *, variant: str = "sessions") -> str:
    """Bot's opening message: the SINGLE-MESSAGE template the lawyer fills."""
    return single_message_template_for(story_id, variant=variant)


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
    from urllib.parse import quote as _quote
    safe_phone = _quote(wa_phone, safe="")   # the "+" in "+91..." must be %2B
    url = f"{base}/rest/v1/wa_draft_sessions?wa_phone=eq.{safe_phone}&select=*"
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
    from urllib.parse import quote as _quote
    safe_phone = _quote(wa_phone, safe="")
    url = f"{base}/rest/v1/wa_draft_sessions?wa_phone=eq.{safe_phone}"
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
    template renderer expects. Variant ('hc' vs default) is stored inside
    collected as __variant so we don't need an extra DB column."""
    variant = "sessions"
    if isinstance(collected, dict):
        variant = collected.get("__variant", "sessions") or "sessions"
    if story_id == "bail_application":
        base = dict(_bail_static_defaults(variant))
    else:
        base = dict(STATIC_DEFAULTS.get(story_id) or {})
    base.update(collected or {})
    # __variant is internal — strip before passing to renderer
    base.pop("__variant", None)
    return base


REQUIRED_FIELDS_BY_STORY: dict[str, tuple[str, ...]] = {
    # arrest_date is optional — bail can be sought pre-arrest too
    "bail_application": (
        "court_name", "applicant_name", "applicant_father", "applicant_address",
        "police_station", "district", "fir_number", "sections",
    ),
}

# Human-readable labels for the "missing fields" prompt
FIELD_LABELS: dict[str, str] = {
    "court_name":        "Court",
    "applicant_name":    "Applicant name",
    "applicant_father":  "Father's name",
    "applicant_address": "Address",
    "police_station":    "Police station",
    "district":          "District",
    "fir_number":        "FIR no & year",
    "sections":          "Sections",
    "arrest_date":       "Date of arrest",
}


def missing_required(story_id: str, answers: dict) -> list[str]:
    req = REQUIRED_FIELDS_BY_STORY.get(story_id) or ()
    out: list[str] = []
    for k in req:
        v = answers.get(k)
        if v is None:
            out.append(k); continue
        if isinstance(v, str) and not v.strip():
            out.append(k); continue
        if isinstance(v, list) and not v:
            out.append(k); continue
    return out


def gap_prompt(missing_keys: list[str]) -> str:
    """Tight follow-up asking only for the fields the lawyer hasn't given yet."""
    lines = [FIELD_LABELS.get(k, k) + ": " for k in missing_keys]
    return (
        "Almost there. Just need a few more fields. Reply with this short block:\n\n"
        "```\n" + "\n".join(lines) + "```\n\n"
        "Or send another doc to auto-fill, or *CANCEL* to abort."
    )


# ════════════════════════════════════════════════════════════════ OCR mapping

def _fir_ocr_to_bail_slots(extracted: dict) -> dict[str, Any]:
    """Map an FIR OCR result (from ocr_fir_pages) → bail-template slot dict."""
    out: dict[str, Any] = {}
    accused = (extracted.get("accused_details") or [])
    if accused:
        first = accused[0] if isinstance(accused[0], dict) else {}
        if first.get("name"):
            out["applicant_name"] = first["name"]
        if first.get("relative"):
            out["applicant_father"] = first["relative"]
        if first.get("address"):
            out["applicant_address"] = first["address"]
    if extracted.get("police_station"):
        out["police_station"] = extracted["police_station"]
    if extracted.get("district"):
        out["district"] = extracted["district"]
    if extracted.get("state"):
        out["state_name"] = extracted["state"]
    full_fir = extracted.get("fir_number_full") or extracted.get("fir_number")
    if full_fir:
        out["fir_number"] = str(full_fir)
    secs = extracted.get("sections")
    if secs:
        out["sections"] = secs if isinstance(secs, list) else [secs]
    if extracted.get("arrest_date"):
        out["arrest_date"] = extracted["arrest_date"]
    return out


def _bail_order_ocr_to_bail_slots(extracted: dict) -> dict[str, Any]:
    """Map a Sessions/Magistrate bail-order OCR (for HC successive bail) → slots.

    Phase-4a-MVP: opportunistic mapping. The schema varies per case so we lift
    whatever common fields we can; lawyer fills the rest via the gap prompt.
    """
    out: dict[str, Any] = {}
    accused = extracted.get("accused") or extracted.get("applicants") or []
    if isinstance(accused, list) and accused:
        first = accused[0] if isinstance(accused[0], dict) else {}
        if first.get("name"):
            out["applicant_name"] = first["name"]
        if first.get("father") or first.get("relative"):
            out["applicant_father"] = first.get("father") or first.get("relative")
    if extracted.get("police_station"):
        out["police_station"] = extracted["police_station"]
    if extracted.get("district"):
        out["district"] = extracted["district"]
    crime = extracted.get("crime_no") or extracted.get("fir_number")
    if crime:
        out["fir_number"] = str(crime)
    if extracted.get("sections"):
        out["sections"] = extracted["sections"] if isinstance(extracted["sections"], list) else [extracted["sections"]]
    return out


async def ocr_for_draft(media_urls: list[str], *, variant: str = "sessions") -> dict[str, Any]:
    """Download Twilio media + run the right OCR + map to bail slots.

    Returns the extracted slot dict (possibly empty on failure).
    """
    if not media_urls:
        return {}
    from headnote.whatsapp.providers import twilio as _twi
    from headnote.drafter.ocr import ocr_fir_pages, ocr_bail_order_pages

    pages: list[tuple[bytes, str]] = []
    for u in media_urls[:6]:                       # cap pages
        try:
            data, ct = await asyncio.to_thread(_twi.download_media, u)
            if not ct or ct == "application/octet-stream":
                ct = "image/jpeg"                  # WhatsApp images
            pages.append((data, ct))
        except Exception:
            log.exception("twilio download_media failed for %s", u[:80])
    if not pages:
        return {}

    try:
        if variant == "hc":
            parsed = await asyncio.to_thread(ocr_bail_order_pages, pages)
            return _bail_order_ocr_to_bail_slots(parsed)
        else:
            parsed = await asyncio.to_thread(ocr_fir_pages, pages)
            return _fir_ocr_to_bail_slots(parsed)
    except Exception:
        log.exception("OCR failed (variant=%s)", variant)
        return {}


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
