"""सुझाव — the drafting suggestion rail (a senior's eye on every draft).

Given the current draft text + its doc_type, return structured suggestions the
editor renders beside the document:

  • sections   — is the charging section right? BNSS↔CrPC pair mismatches, a
                 criminal code cited in a civil pleading, the expected provision
                 for this matter type. Pure regex/lookup — zero LLM, zero cost.
  • missing    — mandatory skeleton points not yet pleaded, each with a ready
                 house-style para the advocate can insert with one click (this is
                 the ONE LLM call here; degrades gracefully to [] when offline).
  • limitation — the clock for this matter type (static per-type map).
  • companions — law-mandated papers to file alongside (from the type brief).
  • authorities— the verified body whitelist + curated cite-at-hearing
                 candidates, each labelled so nothing unverified reads as safe.

The same discipline as the drafter itself: suggestions only — nothing is ever
auto-inserted, and no citation the guard doesn't know survives into a suggested
para. The advocate is the gate.
"""
from __future__ import annotations

import re

from headnote.drafter import author

# ---------------------------------------------------------------------------
# limitation clocks — only types with a clean, confident rule. Everything else
# omits the card rather than risk a wrong period on an advocate's screen.
# ---------------------------------------------------------------------------
LIMITATION = {
    "revision": {
        "hi": "पुनरीक्षण की मियाद — आक्षेपित आदेश से 90 दिन; विलम्ब पर धारा 5 लिमिटेशन एक्ट का आवेदन साथ लगाएँ।",
        "en": "Revision — 90 days from the impugned order; add a §5 Limitation Act condonation application if late."},
    "appeal": {
        "hi": "अपील की मियाद — सत्र न्यायालय में 30 दिन / उच्च न्यायालय में 60 दिन; विलम्ब पर धारा 5 कंडोनेशन आवेदन।",
        "en": "Appeal — 30 days (Sessions) / 60 days (High Court) from the judgment; §5 condonation if late."},
    "cheque_138": {
        "hi": "परिवाद की मियाद — वाद कारण (15-दिन अवधि की समाप्ति) से 1 माह (धारा 142)।",
        "en": "Complaint within 1 month of the cause of action — day 16 after the demand notice (§142 NI Act)."},
    "default_bail": {
        "hi": "समय-संवेदनशील — यह अधिकार चालान प्रस्तुत होने से पहले ही उपयोग करना अनिवार्य है; आज ही दाखिल करें।",
        "en": "Time-critical — the right must be exercised BEFORE the charge-sheet is filed; file today."},
    "recovery_suit": {
        "hi": "मियाद — सामान्यतः वाद कारण से 3 वर्ष; plaint में मियाद का para अनिवार्य है।",
        "en": "Limitation — generally 3 years from the cause of action; the plaint must carry a limitation para."},
    "specific_performance": {
        "hi": "मियाद (अनुच्छेद 54) — अनुपालन हेतु नियत तिथि से 3 वर्ष; तिथि नियत न हो तो इनकार की सूचना से।",
        "en": "Art. 54 — 3 years from the date fixed for performance, or from refusal where none is fixed."},
    "declaration_suit": {
        "hi": "मियाद (अनुच्छेद 58) — वाद का अधिकार पहली बार उत्पन्न होने से 3 वर्ष।",
        "en": "Art. 58 — 3 years from when the right to sue first accrues."},
    "consumer_complaint": {
        "hi": "मियाद — वाद कारण से 2 वर्ष (धारा 69); पर्याप्त कारण पर विलम्ब-क्षमा संभव।",
        "en": "2 years from the cause of action (§69 CPA 2019); condonation possible on sufficient cause."},
    "written_statement": {
        "hi": "समय-सीमा — समन की तामील से 30 दिन, अधिकतम 90 दिन (आदेश 8 नियम 1)।",
        "en": "30 days from service of summons, outer limit 90 days (Order VIII Rule 1)."},
    "injunction_suit": {
        "hi": "हस्तक्षेप जारी रहने तक वाद कारण निरंतर — पर विलम्ब balance of convenience के विरुद्ध जाता है; शीघ्र दाखिल करें।",
        "en": "Continuing cause while interference continues — but delay cuts against balance of convenience; file promptly."},
}

_TAG = re.compile(r"<[^>]+>")


def _plain(text: str) -> str:
    return _TAG.sub(" ", text or "").replace("&nbsp;", " ")


# ---------------------------------------------------------------------------
# sections check — pure lookup + the existing guards
# ---------------------------------------------------------------------------
_FIRST_NUM = re.compile(r"\d{1,3}")


def _sections_check(doc_type: str, plain: str, lang: str) -> list[dict]:
    out: list[dict] = []
    b = author.brief_for(doc_type)
    expected = (b.get("section_hi") or "").strip()
    if expected:
        m = _FIRST_NUM.search(expected)
        # probe "धारा 483" / "आदेश 7" / "section 12" — a bare digit elsewhere is not a match
        present = bool(m) and bool(re.search(
            r"(?:धारा|आदेश|section|order|s\.)\s*" + re.escape(m.group(0)) + r"(?!\d)",
            plain, re.IGNORECASE))
        if present:
            out.append({"state": "ok", "text": expected,
                        "detail": "सही प्रावधान draft में मौजूद है" if lang == "hi"
                                  else "the governing provision is present"})
        else:
            out.append({"state": "info",
                        "text": ("अपेक्षित: " if lang == "hi" else "Expected: ") + expected,
                        "detail": "इस प्रकार के आवेदन का शीर्ष प्रावधान draft में नहीं दिखा"
                                  if lang == "hi" else
                                  "the governing provision for this matter type was not found in the draft"})
    for w in author.guard_sections([plain]):
        out.append({"state": "flag", "text": w, "detail": ""})
    if doc_type in author.CIVIL_TYPES and (
            re.search(author._BNSS_TOKEN, plain) or re.search(author._CRPC_TOKEN, plain, re.IGNORECASE)):
        out.append({"state": "flag",
                    "text": "व्यवहार (civil) प्रारूप में बी.एन.एस.एस./दं.प्र.सं. का उल्लेख है"
                            if lang == "hi" else "This civil pleading cites BNSS/CrPC",
                    "detail": "civil pleading में आपराधिक संहिता का स्थान नहीं — हटाएँ या पृथक् परिवाद की सलाह दें"
                              if lang == "hi" else "criminal codes have no place in a civil pleading — remove"})
    return out


# ---------------------------------------------------------------------------
# missing skeleton points — the one LLM call; degrades to [] offline
# ---------------------------------------------------------------------------
_MISSING_SYSTEM = """You are the reviewing senior in an Indian litigation advocate's office (any State/UT).
You are given (a) the MANDATORY checklist of paragraphs this document type must carry, and (b) the advocate's
CURRENT draft. Find checklist points that are genuinely ABSENT from the draft. Output ONLY valid JSON:
{"missing": [{"point": "<the absent point, short, in %LANG%>",
              "why": "<one line: the consequence of leaving it out, in %LANG%>",
              "para": "<a ready-to-insert paragraph in formal court %LANG%, beginning 'यह कि,' for Hindi>"}]}

Rules — absolute:
- At most 4 items, most damaging first. If nothing material is missing, return {"missing": []}.
- A point is missing only if truly absent — a differently-worded para that covers it counts as present.
- The para uses ONLY facts already in the draft; every unknown value is a ____ blank. Never invent facts.
- NEVER put any case citation in a para. No judgment names, no SCC/AIR references. Statute sections are fine.
- Match the draft's register (formal Hindi in Devanagari, or formal English)."""


def _missing_points(doc_type: str, plain: str, lang: str) -> tuple[list[dict], str]:
    """Return (missing_items, note). Items whose para smells like a citation are dropped
    (the guard is biased to drop). On any LLM failure returns ([], offline-note)."""
    b = author.brief_for(doc_type)
    skeleton = [s for s in (b.get("skeleton") or []) if not s.startswith("[")]
    if not skeleton or not plain.strip():
        return [], ""
    try:
        from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
        user = ("MANDATORY CHECKLIST for {label}:\n{sk}\n\nCURRENT DRAFT:\n{draft}".format(
            label=b.get("label_en") or doc_type,
            sk="\n".join(f"  {i+1}. {s}" for i, s in enumerate(skeleton)),
            draft=plain[:6000]))
        raw, _meta = _call_deepseek_or_groq(
            _MISSING_SYSTEM.replace("%LANG%", "Hindi" if lang == "hi" else "English"),
            user, max_tokens=1400, claude_model="claude-haiku-4-5", json_mode=True)
        items = (parse_json_response(raw) or {}).get("missing") or []
    except Exception:
        return [], ("सुझाव सीमित हैं — छूटे बिंदुओं की जाँच अभी उपलब्ध नहीं" if lang == "hi"
                    else "Suggestions limited — the missing-points check is unavailable right now")
    clean: list[dict] = []
    for it in items[:4]:
        if not isinstance(it, dict):
            continue
        point = str(it.get("point") or "").strip()
        para = str(it.get("para") or "").strip()
        if not point:
            continue
        if para and author._CITE_TOKEN.search(para):
            para = ""      # a citation slipped into a suggested para → strip the insert, keep the point
        clean.append({"point": point, "why": str(it.get("why") or "").strip(), "para": para})
    return clean, ""


# ---------------------------------------------------------------------------
# the public entry point
# ---------------------------------------------------------------------------
def suggest_for(doc_type: str, text: str, lang: str = "hi", use_llm: bool = True) -> dict:
    doc_type = (doc_type or "").strip() or "other_criminal"
    lang = "en" if (lang or "").strip().lower() == "en" else "hi"
    plain = _plain(text)
    b = author.brief_for(doc_type)
    fam = author.family_for(doc_type)

    missing, note = (_missing_points(doc_type, plain, lang) if use_llm else ([], ""))

    authorities = (
        [{"case": c["case"], "point": c["point"], "verified": True}
         for c in author.VERIFIED_CITATIONS.get(fam, [])] +
        [{"case": c["case"], "point": c["point"], "verified": False}
         for c in (b.get("cite_candidates") or [])]
    )
    lim = LIMITATION.get(doc_type)
    return {
        "ok": True,
        "doc_type": doc_type,
        "label_hi": b.get("label_hi") or "", "label_en": b.get("label_en") or "",
        "court": b.get("court") or "",
        "sections": _sections_check(doc_type, plain, lang),
        "missing": missing,
        "missing_note": note,
        "limitation": (lim.get(lang) if lim else None),
        "companions": list(b.get("companions") or []),
        "authorities": authorities,
    }
