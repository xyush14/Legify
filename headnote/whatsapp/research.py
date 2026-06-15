"""WhatsApp research adapter — calls the existing situation pipeline
and formats the result for a WhatsApp text reply.

The bot's webhook can't run this synchronously inside the inbound
handler (the research pipeline takes 15-60s and Twilio's webhook ack
timeout is ~10s). Caller is responsible for kicking this off as a
background task after sending an immediate "🔎 Searching…" ack.

Response shape from _api_situation_impl():
    {
        "result": {                      # ← cases live here, NOT at top level
            "cases": [...],
            "internal_reasoning": {...},
            "confidence": "high|med|low",
            "style": "practitioner|journal",
        },
        "raw": str,                      # raw LLM string (debug)
        "dropped_hallucinations": [...], # cases that failed existence check
        "meta": {...},                   # cost / timings / verification report
    }

Each case dict:
    {
        "case_id": "...",
        "title": "...",                  # ← case name (NOT 'name')
        "citation": "...",
        "court": "...",
        "year": 2024,
        "kanoon_doc_id": "...",
        "kanoon_url": "https://indiankanoon.org/doc/...",
        "fame_indicator": "leading|notable|...",
        "outcome": "...",
        "relevance_scores": {"total": 12, ...},
        "relevance_explanation": "1-2 sentence why-this-fits",
        "bns_note": "...",
        "quotable_phrase": "...",
        "paragraph_anchor": "(Paras X-Y)",
        "practitioner_notes": {
            "one_line_topic": "very tight summary",
            "gist": "1-paragraph summary",
            "quotable_phrase": "...",
            "cross_refs": [...]
        },
        # SC corpus enrichment (when re-anchored):
        "neutral_citation": "2014INSC382",
        "scr_citation": "[2013] 7 S.C.R. 165",
        "official_pdf_url": "/api/judgment/pdf/sc:...",
        "official_doc_id": "sc:2013_7_165_178",
        "is_official_copy": true,
        # verification flags
        "verification_flags": ["quote_unverified"],
    }

PDF memo attachment is Phase 2.5 — citations-as-text for now.
"""
from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

log = logging.getLogger(__name__)


WA_MAX_BODY = 3500   # WhatsApp's hard cap is 4096; reserve ~600 chars for safety
MAX_CASES = 5


# ════════════════════════════════════════════════════════════════ public API

async def run_research(query: str) -> str:
    """Full pipeline → WhatsApp text. Top-level entry from the webhook handler."""
    cleaned = (query or "").strip()
    if len(cleaned) < 10:
        return _short_query_hint(cleaned)

    # Late import — headnote.api.app imports this module via the router,
    # so a module-level import would deadlock.
    from headnote.api.app import _api_situation_impl
    from headnote.api.models import SituationRequest

    try:
        req = SituationRequest(
            situation=cleaned,
            style="practitioner",
            deep_mode=False,
            mode="famous",
        )
    except Exception as exc:
        log.warning("SituationRequest validation failed for %r: %s", cleaned[:80], exc)
        return _short_query_hint(cleaned)

    def _noop_record(**_kw: Any) -> None:
        return None

    try:
        response = await asyncio.to_thread(_api_situation_impl, req, _noop_record)
    except Exception:
        log.exception("situation pipeline crashed for %r", cleaned[:80])
        return (
            "⚠️ Sorry — the research engine hit an error. "
            "Try rephrasing, or send *HELP* for examples."
        )

    return format_situation_response(response, query=cleaned)


def format_situation_response(response: dict, *, query: str = "") -> str:
    """Convert the raw _api_situation_impl envelope into a WhatsApp body."""
    if not isinstance(response, dict):
        return "⚠️ Pipeline returned an unexpected response. Try again in a moment."

    result = response.get("result") or {}
    cases = result.get("cases") or []
    cases = [c for c in cases if isinstance(c, dict) and (c.get("title") or c.get("name"))]

    if not cases:
        # Fallback: surface "dropped" cases if they exist (cases the LLM cited
        # that failed strict verification — still real, just flagged)
        dropped = response.get("dropped_hallucinations") or []
        if dropped:
            return _no_clean_cases_message(dropped, query)
        return _no_cases_message(query)

    meta = response.get("meta") or {}
    confidence = result.get("confidence") or ""

    lines: list[str] = []
    lines.append(f"📚 *{min(len(cases), MAX_CASES)} Indian cases* matching your query:")
    lines.append("")

    for i, c in enumerate(cases[:MAX_CASES], 1):
        lines.extend(_render_case(i, c))

    lines.append("─" * 16)

    # Inline meta line — judges respect this
    cost_inr = meta.get("cost_inr")
    model = meta.get("model", "")
    if cost_inr is not None:
        lines.append(f"_Model: {model} · query cost ₹{cost_inr:.2f} · confidence {confidence or 'med'}_")
    else:
        lines.append("_Powered by Headnote — citation-checked Indian case research._")

    lines.append("_Reply with a refined query, or *HELP* for examples._")

    body = "\n".join(lines).strip()
    if len(body) > WA_MAX_BODY:
        body = body[: WA_MAX_BODY - 80].rstrip() + "\n\n_(trimmed — narrow your query for full detail)_"
    return body


# ════════════════════════════════════════════════════════════════ case rendering

def _render_case(idx: int, c: dict) -> list[str]:
    """One case → 4-7 lines of WhatsApp text."""
    out: list[str] = []

    # Case name — prefer 'title' (real pipeline) over 'name' (legacy fallback)
    name = (c.get("title") or c.get("name") or "").strip()
    out.append(f"*{idx}. {name}*")

    # Citation line — prefer official court-accepted forms
    citation = _best_citation(c)
    court = (c.get("court") or "").strip()
    year = c.get("year")

    meta_parts: list[str] = []
    if citation:
        meta_parts.append(citation)
    if court and (not citation or court.lower() not in citation.lower()):
        meta_parts.append(court)
    if year and (not citation or str(year) not in citation):
        meta_parts.append(str(year))
    if meta_parts:
        out.append(f"   _{' · '.join(meta_parts)}_")

    # 1-line summary — prefer practitioner notes (tightest)
    summary = _best_summary(c)
    if summary:
        out.append(f"   → {summary}")

    # Paragraph anchor (boosts credibility, lets lawyers locate the relevant passage)
    anchor = (c.get("paragraph_anchor") or "").strip()
    if anchor:
        out.append(f"   📍 {anchor}")

    # Quotable phrase — verbatim text from the judgment
    quote = _best_quote(c)
    if quote:
        out.append(f"   💬 _“{quote}”_")

    # Links — official PDF first, then IK fallback
    link_lines = _link_lines(c)
    out.extend(link_lines)

    # Verification flag — transparent about anything unverified
    flags = c.get("verification_flags") or []
    if "quote_unverified" in flags:
        out.append("   ⚠️ _Quote paraphrased by AI — verify against the official judgment before citing._")

    out.append("")
    return out


def _best_citation(c: dict) -> str:
    """Prefer court-accepted neutral citation, then SCR, then any other."""
    for k in ("neutral_citation", "scr_citation", "citation"):
        v = c.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    cits = c.get("citations_all") or []
    if cits and isinstance(cits[0], str):
        return cits[0].strip()
    return ""


def _best_summary(c: dict) -> str:
    """Tightest meaningful summary, in preference order."""
    pn = c.get("practitioner_notes") or {}
    candidates = [
        pn.get("one_line_topic"),
        pn.get("gist"),
        c.get("relevance_explanation"),
        c.get("held_line"),
        c.get("stinger_sentence"),
        c.get("holding"),
    ]
    for v in candidates:
        if isinstance(v, str) and v.strip():
            return _trim(v.strip(), 200)
    return ""


def _best_quote(c: dict) -> str:
    """Verbatim quote — practitioner_notes.quotable_phrase preferred."""
    pn = c.get("practitioner_notes") or {}
    for v in (pn.get("quotable_phrase"), c.get("quotable_phrase"), c.get("court_quote")):
        if isinstance(v, str) and v.strip():
            return _trim(v.strip(), 180)
    return ""


def _link_lines(c: dict) -> list[str]:
    """Official PDF (court-accepted) preferred over IK URL."""
    lines: list[str] = []
    pdf_url = (c.get("official_pdf_url") or "").strip()
    if pdf_url:
        if pdf_url.startswith("/"):
            pdf_url = "https://headnote.in" + pdf_url
        lines.append(f"   ⚖️ Official PDF: {pdf_url}")
        return lines  # don't dilute with IK link when we have the official source

    ik_url = (c.get("kanoon_url") or "").strip()
    if ik_url:
        lines.append(f"   🔗 {ik_url}")
    return lines


# ════════════════════════════════════════════════════════════════ fallback messages

def _no_cases_message(query: str) -> str:
    return (
        "I couldn't find precedents matching that query.\n\n"
        "Try rephrasing — include the *statute section*, key facts, and any "
        "specific court (e.g. 'Section 138 NI Act, territorial jurisdiction, recent SC').\n\n"
        "Send *HELP* for examples."
    )


def _no_clean_cases_message(dropped: list[dict], query: str) -> str:
    # We have cases but they all failed strict verification
    n = len([d for d in dropped if isinstance(d, dict)])
    return (
        f"I found ~{n} cases the AI cited, but couldn't fully verify them against "
        "the corpus (most likely because the LLM cited cases not in our official "
        "source layer).\n\n"
        "Try a more specific query — include the *statute section*, key facts, "
        "and any specific court.\n\n"
        "Send *HELP* for examples."
    )


def _short_query_hint(text: str) -> str:
    if not text:
        return (
            "👋 Welcome to *Headnote* — citation-checked Indian legal research on WhatsApp.\n\n"
            "Send me a research question to begin. For example:\n"
            "• _Section 138 NI Act recent SC on territorial jurisdiction_\n"
            "• _bail jurisprudence under PMLA after Vijay Madanlal_\n"
            "• _doctrine of part performance latest High Court view_\n\n"
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
        "Send a natural-language legal question and I'll return 3–5 cited "
        "precedents (case name, citation, ratio, official PDF link when available).\n\n"
        "*Examples:*\n"
        "• _Section 138 NI Act recent SC on territorial jurisdiction_\n"
        "• _circumstantial evidence five conditions latest_\n"
        "• _anticipatory bail in economic offences SC view_\n"
        "• _Section 482 CrPC FIR quashing parameters_\n"
        "• _Section 420/406 IPC overlap with NI Act 138_\n\n"
        "*Tips for better results:*\n"
        "• Include the *statute section* if you know it\n"
        "• Add *recent SC* / *latest HC* to bias by recency\n"
        "• Mention the specific court for jurisdictional priors\n"
        "• Be specific about the *fact pattern*\n\n"
        "*Commands:*\n"
        "*HELP* — show this message\n"
        "*STOP* — stop receiving messages\n\n"
        "_v0.4 beta — sandbox membership lasts 72h._"
    )


# ════════════════════════════════════════════════════════════════ helpers

def _trim(s: str, n: int) -> str:
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) <= n:
        return s
    cut = s[:n]
    sp = cut.rfind(" ")
    if sp > n * 0.6:
        cut = cut[:sp]
    return cut.rstrip(".,;:") + "…"
