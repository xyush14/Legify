"""Prompt-first drafting — the "describe your matter → get a draft" front door.

One freeform prompt (Hindi / English / Hinglish) → a court-ready draft, the best we
can produce:

  1. CLASSIFY  — a cheap LLM call maps the prompt to a doc_type (+ court + bail_type).
  2. ROUTE:
       • a DETERMINISTIC type we have a template for (the moat — bail, anticipatory,
         discharge, revision, appeal, maintenance, dv, quashing, §138, vakalatnama,
         parivad) → extract the fields from the prompt and render the VERBATIM,
         zero-hallucination canonical template. Unfilled fields render as the usual
         placeholders for the advocate to complete in the editor.
       • anything else (a long-tail criminal application, ANY civil matter) → hand to
         the house-style LLM authoring engine (author.py), which writes in Vishnu ji's
         idiom under the verified-citation guard.

This reuses the proven pieces: prompt_tweak's validated PATCH machinery for field
extraction, the canonical template modules for the deterministic render, and author.py
for authoring. The frontend gets back `data` for canonical types so the existing editor
can pick up where the prompt left off.
"""
from __future__ import annotations

import json

from headnote.drafter import author


def _finalize(result: dict) -> dict:
    """Add `page_hi` / `page_en` — the draft wrapped in a standalone A4 page (canonical
    header CSS + Devanagari font) so the frontend can drop it straight into an iframe."""
    from headnote.drafter.templates._doc_header import doc_page
    hi = (result.get("html_hi") or "").strip()
    en = (result.get("html_en") or "").strip()
    result["page_hi"] = doc_page([hi]) if hi else ""
    result["page_en"] = doc_page([en]) if en else ""
    return result


# ---------------------------------------------------------------------------
# 1) Classifier — prompt → {doc_type, court, bail_type, confidence}.
# ---------------------------------------------------------------------------
CLASSIFY_SYSTEM = """You are the intake router for an Indian litigation drafting tool (Madhya Pradesh trial
courts + High Court). Read the advocate's description of what they want to draft — it may be in Hindi, English
or Hinglish — and classify it. Output ONLY valid JSON, no prose:
{"doc_type": "<one key below>", "court": "magistrate"|"sessions"|"hc"|"family"|"", "bail_type": "regular"|"anticipatory"|"", "confidence": 0.0-1.0, "reason": "<short>"}

doc_type keys (pick the SINGLE best fit):
  bail               regular bail after arrest/custody (BNSS §483/§480; CrPC §439/§437)
  anticipatory_bail  pre-arrest / apprehension of arrest (BNSS §482; CrPC §438; "अग्रिम")
  default_bail       statutory bail — charge-sheet not filed in 60/90 days (BNSS §187; §167(2))
  discharge          discharge from charge (BNSS §250/§262; §227/§239)
  revision           criminal revision against an order (BNSS §438-442; §397-401)
  appeal             appeal against conviction (BNSS §415; §374)
  quashing           quash an FIR / proceeding — HC inherent power (BNSS §528; §482 CrPC)
  maintenance        wife/child maintenance (BNSS §144; §125 CrPC); भरण-पोषण
  dv                 domestic violence reliefs (§12 PWDVA); व्यथित महिला
  cheque_138         cheque dishonour (§138 NI Act) — complaint OR defence
  vakalatnama        vakalatnama / memo of appearance
  parivad            private complaint (परिवाद)
  other_criminal     any OTHER criminal application/petition with no specific key
  other_civil        any CIVIL matter — suit, written statement, injunction, recovery, declaration, partition, eviction, consumer, etc.

Rules:
- "anticipatory" / "pre-arrest" / "अग्रिम" / "गिरफ्तारी की आशंका" → anticipatory_bail, NOT bail.
- quashing / "FIR रद्द" / "कार्यवाही निरस्त करने" → quashing, court=hc.
- maintenance / भरण-पोषण / monthly maintenance from husband → maintenance, court=family.
- Clearly civil (money recovery, property, contract, injunction, partition, eviction, consumer, written
  statement, declaration, specific performance) → other_civil.
- Criminal but no specific key fits → other_criminal.
- Set court only when clear from the text; otherwise "".
"""


def classify(matter: str, lang: str = "hi") -> dict:
    """Map a freeform matter description to {doc_type, court, bail_type, confidence}.
    Falls back to a safe heuristic if the LLM is unavailable."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    try:
        raw, _meta = _call_deepseek_or_groq(
            CLASSIFY_SYSTEM, matter.strip(), max_tokens=200, claude_model="claude-haiku-4-5")
        out = parse_json_response(raw)
        dt = (out.get("doc_type") or "").strip()
        if dt not in _VOCAB:
            dt = _heuristic_type(matter)
        return {
            "doc_type": dt,
            "court": (out.get("court") or "").strip(),
            "bail_type": (out.get("bail_type") or "").strip(),
            "confidence": float(out.get("confidence") or 0.5),
            "reason": out.get("reason") or "",
        }
    except Exception:
        return {"doc_type": _heuristic_type(matter), "court": "", "bail_type": "",
                "confidence": 0.3, "reason": "heuristic (LLM unavailable)"}


_VOCAB = {
    "bail", "anticipatory_bail", "default_bail", "discharge", "revision", "appeal",
    "quashing", "maintenance", "dv", "cheque_138", "vakalatnama", "parivad",
    "other_criminal", "other_civil",
}


def _heuristic_type(matter: str) -> str:
    p = (matter or "").lower()

    def has(*w):
        return any(x in p for x in w)
    if has("anticipatory", "pre-arrest", "अग्रिम", "गिरफ्तारी की आशंका", "गिरफ्तारी की आश"):
        return "anticipatory_bail"
    if has("quash", "fir रद्द", "कार्यवाही निरस्त", "528", "482"):
        return "quashing"
    if has("maintenance", "भरण", "125", "144 bnss", "गुजारा"):
        return "maintenance"
    if has("domestic violence", "घरेलू हिंसा", "pwdva", "व्यथित"):
        return "dv"
    if has("cheque", "138", "चेक", "dishonour", "dishonor"):
        return "cheque_138"
    if has("discharge", "उन्मोचन", "227", "239", "250", "262"):
        return "discharge"
    if has("revision", "पुनरीक्षण", "397", "438"):
        return "revision"
    if has("appeal", "अपील", "conviction", "415", "374"):
        return "appeal"
    if has("vakalatnama", "वकालतनामा"):
        return "vakalatnama"
    if has("परिवाद", "private complaint"):
        return "parivad"
    if has("bail", "जमानत", "483", "480", "439", "437"):
        return "bail"
    if has("suit", "recovery", "injunction", "वाद", "वसूली", "व्यादेश", "declaration", "partition",
           "eviction", "बेदखली", "specific performance", "written statement", "जवाबदावा", "consumer"):
        return "other_civil"
    return "other_criminal"


# ---------------------------------------------------------------------------
# 2) Deterministic routing — classifier type → canonical template module.
# ---------------------------------------------------------------------------
# doc_type → (module_key, default_court, bail_type)
_DETERMINISTIC = {
    "bail":              ("bail", "sessions", "regular"),
    "anticipatory_bail": ("bail", "sessions", "anticipatory"),
    "discharge":         ("discharge", "sessions", ""),
    "revision":          ("revision", "sessions", ""),
    "appeal":            ("appeal", "sessions", ""),
    "maintenance":       ("maintenance", "family", ""),
    "dv":                ("dv", "magistrate", ""),
    "quashing":          ("quashing", "hc", ""),
    "cheque_138":        ("cheque_138", "magistrate", ""),
    "vakalatnama":       ("vakalatnama", "sessions", ""),
    "parivad":           ("parivad", "magistrate", ""),
}


def _module(key: str):
    """Resolve a canonical template module (mirrors app._draft_module)."""
    from headnote.drafter.templates import (  # noqa: F401  local import — heavy
        bail, cheque_138, discharge, maintenance, revision, appeal, dv, quashing,
        parivad, vakalatnama,
    )
    return {
        "bail": bail, "cheque_138": cheque_138, "discharge": discharge,
        "maintenance": maintenance, "revision": revision, "appeal": appeal,
        "dv": dv, "quashing": quashing, "parivad": parivad, "vakalatnama": vakalatnama,
    }.get(key)


def _spec(mod, key: str, court: str, bail_type: str) -> dict:
    if key == "bail":
        return mod.field_spec(court, bail_type)
    if key in ("discharge", "revision", "appeal"):
        return mod.field_spec(court)
    return mod.field_spec()


# ---------------------------------------------------------------------------
# 3) One-shot field extraction (origination) — prompt → validated field values.
# ---------------------------------------------------------------------------
EXTRACT_SYSTEM = """You extract structured field VALUES from an Indian advocate's description of a matter, to
PRE-FILL a court-draft form. Output ONLY valid JSON:
{"set": {<field_key>: <value>}, "toggles": {<toggle_key>: true}, "variant": {<variant_key>: <value>}}

Rules:
- Use ONLY field_key / toggle_key / variant_key that appear in the SCHEMA below.
- Extract EVERY value the description gives: names, father/husband name, age, occupation, address, district,
  police station, FIR/crime number, case number, year, sections, dates (arrest/order/filing), amounts.
- For a "section_list" field, return an array of the section strings as given.
- Turn a toggle ON only if the description clearly supports that ground.
- DO NOT invent values. Omit any field the description doesn't mention — a blank renders as a placeholder.
- Keep values in the language the advocate used (Hindi stays Hindi).
SCHEMA: {schema}
"""


def extract_fields(spec: dict, matter: str) -> tuple[dict, list[str]]:
    """Prompt → validated PATCH → applied onto empty data. Reuses prompt_tweak's
    key-checked apply/validate so nothing outside the spec is ever set."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    from headnote.drafter.prompt_tweak import validate_patch, apply_patch
    schema = {
        "fields": [{"key": f["key"], "type": f.get("type"), "label": (f.get("label") or {}).get("en")}
                   for f in spec.get("fields", [])],
        "toggles": [{"key": t["key"], "label": (t.get("label") or {}).get("en")} for t in spec.get("toggles", [])],
        "variants": spec.get("variants", {}),
    }
    system = EXTRACT_SYSTEM.replace("{schema}", json.dumps(schema, ensure_ascii=False))
    raw, _meta = _call_deepseek_or_groq(system, matter.strip(), max_tokens=900, claude_model="claude-haiku-4-5")
    patch = validate_patch(parse_json_response(raw), spec)
    return apply_patch({}, patch, spec)


# ---------------------------------------------------------------------------
# 4) Orchestrate — the public entry point.
# ---------------------------------------------------------------------------
def draft_from_prompt(matter: str, lang: str = "hi") -> dict:
    """Freeform prompt → best-effort court-ready draft. Returns a unified result:
      {ok, mode: "canonical"|"authored", doc_type, court, confidence, html_hi,
       html_en, data?, cite_at_hearing, companions, warnings, title, meta}
    """
    matter = (matter or "").strip()
    if not matter:
        return {"ok": False, "error": "empty prompt"}

    cls = classify(matter, lang)
    dt = cls["doc_type"]

    # --- deterministic (canonical template) path — the moat ---
    if dt in _DETERMINISTIC:
        key, def_court, bail_type = _DETERMINISTIC[dt]
        court = cls.get("court") or def_court
        if key == "cheque_138":            # cheque is magistrate-only here
            court = "magistrate"
        if key == "quashing":
            court = "hc"
        if key == "maintenance":
            court = "family"
        try:
            mod = _module(key)
            spec = _spec(mod, key, court, bail_type)
            data, log = extract_fields(spec, matter)
            data["court"] = court
            if bail_type:
                data["bail_type"] = bail_type
            html_hi = mod.render_hi(data)
            html_en = mod.render_en(data) if hasattr(mod, "render_en") else ""
            cite = list(getattr(mod, "CITE_AT_HEARING", []) or [])
            return _finalize({
                "ok": True, "mode": "canonical", "doc_type": dt, "court": court,
                "bail_type": bail_type, "confidence": cls["confidence"],
                "html_hi": html_hi, "html_en": html_en,
                "data": data, "changelog": log,
                "cite_at_hearing": cite,
                "companions": spec.get("companions") or [],
                "warnings": [],
                "title": author.brief_for(dt if dt in author.TYPE_BRIEFS else "other_criminal")["label_hi"],
                "reason": cls.get("reason", ""),
            })
        except Exception as e:  # canonical path failed → fall through to authoring
            cls["reason"] = f"canonical render failed ({type(e).__name__}); authored instead"

    # --- authored (house-style LLM) path — long tail + civil + anything else ---
    author_type = dt if dt in author.TYPE_BRIEFS else (
        "other_civil" if dt == "other_civil" else "other_criminal")
    result = author.author_document(matter, author_type, lang, court=cls.get("court") or "")
    result.update({
        "court": cls.get("court") or author.brief_for(author_type).get("court"),
        "confidence": cls["confidence"],
        "html_hi": result["html"] if lang != "en" else "",
        "html_en": result["html"] if lang == "en" else "",
        "reason": cls.get("reason", ""),
        "classified_as": dt,
    })
    return _finalize(result)
