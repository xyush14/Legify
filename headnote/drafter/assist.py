"""
Personal-Assist auto-router.

A lawyer drops a freeform request ("I need an RFA", "जमानत का आवेदन",
"recovery of money order 37") and we answer instantly:

  1. If the request maps to a LIVE fillable /draft/<type> page, return that
     clean shareable link — zero LLM, zero humans.
  2. Otherwise run the guarded prompt-drafter engine (draft_from_prompt) to
     author a court-ready draft on the spot. That engine keeps the ONE hard
     rule intact — verified-citation whitelist + CITE_AT_HEARING guard, so no
     fabricated case law is ever emitted — and its output is author-tier
     (a proposal for advocate review).

The PAGE_REGISTRY below is the single source of truth for the live pages; it
also feeds the intake page's examples and (later) the /app tile row.
"""

from __future__ import annotations

from typing import Optional


# --------------------------------------------------------------- registry
# Each entry: the clean route, bilingual title, court tier, and the alias
# keywords (lowercased EN + Hindi substrings) that map a request to it.
# Order matters — more specific entries first (rfa before generic "appeal").

PAGE_REGISTRY: list[dict] = [
    {
        "id": "rfa",
        "url": "/draft/rfa",
        "title_en": "Regular First Appeal (§96 / Order XLI CPC)",
        "title_hi": "नियमित प्रथम अपील (धारा 96 / आदेश 41 सी.पी.सी.)",
        "tier": "author",
        "keywords": [
            "rfa", "regular first appeal", "first appeal", "civil appeal",
            "section 96", "order 41", "order xli", "appeal from decree",
            "प्रथम अपील", "नियमित अपील", "सिविल अपील", "डिक्री के विरुद्ध अपील",
        ],
    },
    {
        "id": "defamation",
        "url": "/draft/defamation",
        "title_en": "Civil Defamation (damages + injunction)",
        "title_hi": "मानहानि (सिविल) — क्षतिपूर्ति व निषेधाज्ञा",
        "tier": "author",
        "keywords": [
            "defamation", "defamatory", "libel", "slander", "damages for reputation",
            "cease and desist", "मानहानि", "अपमान", "बदनामी",
        ],
    },
    {
        "id": "maintenance",
        "url": "/draft/maintenance",
        "title_en": "Maintenance (§144 BNSS / §125 CrPC)",
        "title_hi": "भरण-पोषण (धारा 144 बी.एन.एस.एस. / 125 दं.प्र.सं.)",
        "tier": "author",
        "keywords": [
            "maintenance", "section 125", "125 crpc", "144 bnss", "rajnesh",
            "interim maintenance", "wife maintenance", "भरण", "भरण-पोषण",
            "भरण पोषण", "गुजारा", "गुजारा भत्ता",
        ],
    },
    {
        "id": "recovery",
        "url": "/draft/recovery",
        "title_en": "Recovery of Money (Order XXXVII CPC summary suit)",
        "title_hi": "धन-वसूली (आदेश 37 सी.पी.सी. संक्षिप्त वाद)",
        "tier": "author",
        "keywords": [
            "recovery", "recovery of money", "money suit", "order 37", "order xxxvii",
            "summary suit", "loan recovery", "outstanding payment", "recovery notice",
            "वसूली", "धन वसूली", "धन-वसूली", "रकम वसूली", "पैसे की वसूली", "ऋण वसूली",
        ],
    },
    {
        "id": "rent",
        "url": "/draft/rent",
        "title_en": "Rent Agreement / Lease Deed",
        "title_hi": "किरायानामा / पट्टा विलेख",
        "tier": "author",
        "keywords": [
            "rent agreement", "lease deed", "lease", "tenancy", "rental agreement",
            "किराया", "किरायानामा", "किरायेदारी", "पट्टा", "लीज",
        ],
    },
    {
        "id": "bail",
        "url": "/draft/bail",
        "title_en": "Regular Bail (§483 BNSS / §439 CrPC)",
        "title_hi": "नियमित जमानत (धारा 483 बी.एन.एस.एस. / 439 दं.प्र.सं.)",
        "tier": "reviewed",
        "keywords": [
            "regular bail", "bail application", "bail app", "483 bnss", "439 crpc",
            "जमानत", "नियमित जमानत", "जमानत आवेदन", "बेल",
        ],
    },
    {
        "id": "discharge",
        "url": "/draft/discharge",
        "title_en": "Discharge (§262 BNSS / §239 CrPC)",
        "title_hi": "उन्मोचन / डिस्चार्ज (धारा 262 बी.एन.एस.एस. / 239 दं.प्र.सं.)",
        "tier": "reviewed",
        "keywords": [
            "discharge", "262 bnss", "239 crpc", "227 crpc", "discharge application",
            "उन्मोचन", "डिस्चार्ज", "आरोपमुक्त",
        ],
    },
]

# doc_type keys (from from_prompt.classify) → a live page, when we have one.
# Lets a request the classifier understands but the alias matcher missed still
# land on the nicer fillable page instead of an authored one-off.
DOCTYPE_TO_PAGE: dict[str, str] = {
    "regular_bail": "bail",
    "regular_bail_hc": "bail",
    "discharge_227": "discharge",
    "maintenance_125": "maintenance",
    "defamation": "defamation",
    "recovery_suit": "recovery",
    "summary_suit": "recovery",
    "rent_agreement": "rent",
    "first_appeal": "rfa",
    "regular_first_appeal": "rfa",
}


def _page_payload(entry: dict, matched_by: str) -> dict:
    return {
        "kind": "page",
        "id": entry["id"],
        "url": entry["url"],
        "title_en": entry["title_en"],
        "title_hi": entry["title_hi"],
        "tier": entry["tier"],
        "matched_by": matched_by,
    }


def match_page(prompt: str) -> Optional[dict]:
    """Cheap, LLM-free alias match: first registry entry whose keyword is a
    substring of the (lowercased) request. None if nothing matches."""
    p = " " + (prompt or "").lower().strip() + " "
    if not p.strip():
        return None
    for entry in PAGE_REGISTRY:
        for kw in entry["keywords"]:
            if kw in p:
                return entry
    return None


def _page_by_id(page_id: str) -> Optional[dict]:
    for entry in PAGE_REGISTRY:
        if entry["id"] == page_id:
            return entry
    return None


def route_request(prompt: str, lang: str = "auto") -> dict:
    """Route a freeform assist request.

    Returns either:
      {kind: "page",     url, title_en, title_hi, tier, matched_by}
      {kind: "authored", mode, doc_type, title, page_hi, page_en,
                         cite_at_hearing, companions, warnings, confidence}
      {kind: "error",    error}
    """
    prompt = (prompt or "").strip()
    if not prompt:
        return {"kind": "error", "error": "empty request"}

    # 1) Fast path — alias match to a live page.
    hit = match_page(prompt)
    if hit:
        return _page_payload(hit, "alias")

    # 2) Guarded engine — classify + draft (canonical | house-style authored).
    #    Import lazily so the registry/matcher import without the LLM stack.
    from headnote.drafter.from_prompt import draft_from_prompt

    res = draft_from_prompt(prompt, lang)
    if not res.get("ok", True) and res.get("error"):
        return {"kind": "error", "error": res["error"]}

    # 2a) If the classifier understood a type we have a nicer page for, prefer it.
    page_id = DOCTYPE_TO_PAGE.get((res.get("doc_type") or "").strip())
    if page_id:
        entry = _page_by_id(page_id)
        if entry:
            return _page_payload(entry, "classified")

    # 2b) Otherwise hand back the authored draft.
    return {
        "kind": "authored",
        "mode": res.get("mode", "authored"),
        "doc_type": res.get("doc_type", ""),
        "title": res.get("title", ""),
        "court": res.get("court", ""),
        "confidence": res.get("confidence"),
        "page_hi": res.get("page_hi", ""),
        "page_en": res.get("page_en", ""),
        "cite_at_hearing": res.get("cite_at_hearing", []) or [],
        "companions": res.get("companions", []) or [],
        "warnings": res.get("warnings", []) or [],
    }
