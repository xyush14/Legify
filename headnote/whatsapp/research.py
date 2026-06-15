"""WhatsApp research adapter — calls the existing situation pipeline
and formats the result for a WhatsApp text reply.

The bot's webhook can't run this synchronously inside the inbound
handler (the research pipeline takes 15–30s and Twilio's webhook
ack timeout is ~10s). Caller is responsible for kicking this off
as a background task after sending an immediate "🔎 Searching…" ack.

PDF attachment lives in Phase 2.5 — for now we ship citations-as-text.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


WA_MAX_BODY = 1500   # WhatsApp text cap is 4096; keep well below so user can re-query
MAX_CASES = 5


async def run_research(query: str) -> str:
    """Run the full Headnote research pipeline and return a WhatsApp-ready text."""
    cleaned = (query or "").strip()
    if len(cleaned) < 10:
        return _short_query_hint(cleaned)

    # Late import — headnote.api.app imports this module via the router,
    # so a module-level import would deadlock. Lazy is the only safe option.
    from headnote.api.app import _api_situation_impl
    from headnote.api.models import SituationRequest

    try:
        req = SituationRequest(
            situation=cleaned,
            style="practitioner",   # compressed chambers-digest format — better for chat
            deep_mode=False,        # fast path; user can ask "deep" later (Phase 3)
            mode="famous",          # leading-cases-first — what advocates expect on first ask
        )
    except Exception as exc:  # validation error (length etc.)
        log.warning("SituationRequest validation failed for %r: %s", cleaned[:80], exc)
        return _short_query_hint(cleaned)

    def _noop_record(**_kwargs: Any) -> None:
        return None

    try:
        result = await asyncio.to_thread(_api_situation_impl, req, _noop_record)
    except Exception as exc:  # noqa: BLE001
        log.exception("situation pipeline crashed for %r", cleaned[:80])
        return (
            "⚠️ Sorry — the research engine hit an error. "
            "Try rephrasing, or send *HELP* for examples."
        )

    return format_situation_response(result, query=cleaned)


def format_situation_response(result: dict, *, query: str = "") -> str:
    """Convert /api/situation response into a WhatsApp text body."""
    cases = result.get("cases") or []
    cases = [c for c in cases if isinstance(c, dict) and c.get("name")]

    if not cases:
        return (
            "I couldn't find precedents matching that query.\n\n"
            "Try rephrasing — include the *statute section*, key facts, "
            "and any specific court (e.g. 'Section 138 NI Act, territorial "
            "jurisdiction, recent SC').\n\n"
            "Send *HELP* for examples."
        )

    lines: list[str] = []
    lines.append(f"📚 *{min(len(cases), MAX_CASES)} relevant case(s)* on your query:")
    lines.append("")

    for i, c in enumerate(cases[:MAX_CASES], 1):
        lines.extend(_render_case(i, c))

    lines.append("─" * 12)
    lines.append("_Powered by Headnote — citation-checked Indian case law._")
    lines.append("_Reply with a refined query for more depth, or *HELP* for examples._")

    body = "\n".join(lines).strip()
    # Hard cap so WhatsApp doesn't truncate mid-citation
    if len(body) > WA_MAX_BODY:
        body = body[: WA_MAX_BODY - 80].rstrip() + "\n\n_(trimmed — reply with a narrower query for full detail)_"
    return body


def _render_case(idx: int, c: dict) -> list[str]:
    """One case → 2–4 lines of WhatsApp text."""
    name = (c.get("name") or "").strip()
    citation = _best_citation(c)
    court = (c.get("court") or "").strip()
    year = c.get("year")
    held = _best_held(c)

    out: list[str] = []
    out.append(f"*{idx}. {name}*")

    meta_parts: list[str] = []
    if citation:
        meta_parts.append(citation)
    elif court or year:
        if court:
            meta_parts.append(court)
        if year:
            meta_parts.append(str(year))
    if meta_parts:
        out.append(f"   _{' · '.join(meta_parts)}_")

    if held:
        out.append(f"   → {held}")

    # Official copy link (SC corpus enrichment, when present)
    pdf_url = c.get("official_pdf_url") or ""
    if pdf_url:
        if pdf_url.startswith("/"):
            pdf_url = "https://headnote.in" + pdf_url
        out.append(f"   📎 Official: {pdf_url}")

    out.append("")
    return out


def _best_citation(c: dict) -> str:
    """Prefer neutral citation, then SCR, then any others."""
    for k in ("neutral_citation", "scr_citation", "citation"):
        v = c.get(k)
        if v and isinstance(v, str) and v.strip():
            return v.strip()
    # multi-citations list
    citations_all = c.get("citations_all") or []
    if citations_all:
        first = citations_all[0]
        if isinstance(first, str):
            return first.strip()
    return ""


def _best_held(c: dict) -> str:
    """Prefer held_line, then stinger, then a trimmed court_quote."""
    for k in ("held_line", "stinger_sentence", "ratio", "one_line_topic"):
        v = c.get(k)
        if v and isinstance(v, str) and v.strip():
            return _trim(v.strip(), 180)
    quote = c.get("court_quote") or ""
    if quote:
        return _trim(quote, 160)
    return ""


def _trim(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s)
    if len(s) <= n:
        return s
    cut = s[:n]
    # break at last word boundary
    sp = cut.rfind(" ")
    if sp > n * 0.6:
        cut = cut[:sp]
    return cut.rstrip(".,;:") + "…"


def _short_query_hint(text: str) -> str:
    if not text:
        return (
            "👋 Welcome to *Headnote* — citation-checked Indian legal research on WhatsApp.\n\n"
            "Send me a research question to begin, for example:\n"
            "• _Section 138 NI Act recent SC on territorial jurisdiction_\n"
            "• _doctrine of part performance latest High Court view_\n"
            "• _bail jurisprudence under PMLA after Vijay Madanlal_\n\n"
            "Send *HELP* anytime for more examples."
        )
    return (
        "Your query looks a bit short. Add the *statute*, key facts, and any "
        "specific court for better results.\n\n"
        "Example: _Section 138 NI Act, complaint where drawee bank, recent SC_\n\n"
        "Send *HELP* for more examples."
    )


def help_message() -> str:
    return (
        "🔎 *Headnote on WhatsApp* — citation-checked Indian case research.\n\n"
        "*How to use:*\n"
        "Send me a natural-language legal research question and I'll return "
        "3–5 cited precedents (case name, citation, 1-line ratio).\n\n"
        "*Examples:*\n"
        "• _Section 138 NI Act recent SC on territorial jurisdiction_\n"
        "• _circumstantial evidence five conditions latest_\n"
        "• _anticipatory bail in economic offences SC view_\n"
        "• _Section 482 CrPC FIR quashing parameters_\n\n"
        "*Tips:*\n"
        "• Include the *statute section* if you know it\n"
        "• Add *recent SC* / *latest HC* to bias by recency\n"
        "• Mention specific court for jurisdictional priors\n\n"
        "*Commands:*\n"
        "*HELP* — show this message\n"
        "*STOP* — stop receiving messages\n\n"
        "_v0.4 beta — sandbox membership lasts 72h._"
    )
