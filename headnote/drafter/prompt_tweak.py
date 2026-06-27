"""Prompt-based tweaks — the lawyer types a natural-language change; we apply it as a
STRUCTURED PATCH to the deterministic template (NOT free-text generation).

Why this is safe (preserves the zero-hallucination moat):
  The prompt NEVER rewrites the boilerplate, the fixed reviewed grounds, the sections,
  or the citations. An intent-router (LLM — DeepSeek at runtime) maps the request to a
  small, constrained PATCH, validated against the type's `field_spec`:
    • set     — known field VALUES (names, ages, dates, amounts, facts)
    • toggles — flip known reviewed-ground switches on/off
    • variant — switch a known variant (court / bail_type)
    • add_grounds — the lawyer's OWN extra ground, captured verbatim and FLAGGED
                    (goes into custom_grounds; never the verified reviewed set)
  `apply_patch()` then re-renders deterministically. The LLM only turns the knobs;
  the legal language stays template-/lawyer-sourced. Anything the router can't map to
  a known knob is reported back, not silently invented.

Runtime wiring:  POST /api/draft/tweak {type, data, prompt}
    → router (DeepSeek, ROUTER_SYSTEM) emits PATCH JSON
    → validate_patch() against field_spec  → apply_patch()  → re-render.
"""
from __future__ import annotations

import copy
import json
import re
from typing import Optional


# ---------------------------------------------------------------------------
# 1) Apply a validated patch to the data dict — deterministic, key-checked.
# ---------------------------------------------------------------------------
def apply_patch(data: dict, patch: dict, spec: dict) -> tuple[dict, list[str]]:
    """Return (new_data, changelog). Only touches keys/toggles/variants that exist
    in `spec` (the builder's field_spec); unknown knobs are skipped + logged."""
    data = copy.deepcopy(data or {})
    log: list[str] = []
    field_keys = {f["key"] for f in spec.get("fields", [])}
    toggle_keys = {t["key"] for t in spec.get("toggles", [])}
    variants = spec.get("variants", {})

    for k, v in (patch.get("set") or {}).items():
        if k in field_keys:
            data[k] = v
            log.append(f"set {k} = {v!r}")
        else:
            log.append(f"⚠ ignored unknown field '{k}'")

    if patch.get("toggles"):
        data.setdefault("grounds", {})
        for k, v in patch["toggles"].items():
            if k in toggle_keys:
                data["grounds"][k] = bool(v)
                log.append(f"toggle {k} → {'ON' if v else 'OFF'}")
            else:
                log.append(f"⚠ ignored unknown toggle '{k}'")

    for k, v in (patch.get("variant") or {}).items():
        allowed = variants.get(k)
        if allowed and v in allowed:
            data[k] = v
            log.append(f"variant {k} → {v}")
        else:
            log.append(f"⚠ ignored variant '{k}={v}' (allowed: {allowed})")

    for gtext in (patch.get("add_grounds") or []):
        if str(gtext).strip():
            data.setdefault("custom_grounds", []).append(str(gtext).strip())
            log.append(f"+ lawyer ground (flagged): “{str(gtext).strip()[:60]}…”")

    if patch.get("note"):
        log.append(f"note: {patch['note']}")
    return data, log


def validate_patch(patch: dict, spec: dict) -> dict:
    """Strip anything not in the spec — the router output is never trusted blindly."""
    field_keys = {f["key"] for f in spec.get("fields", [])}
    toggle_keys = {t["key"] for t in spec.get("toggles", [])}
    variants = spec.get("variants", {})
    return {
        "set": {k: v for k, v in (patch.get("set") or {}).items() if k in field_keys},
        "toggles": {k: bool(v) for k, v in (patch.get("toggles") or {}).items() if k in toggle_keys},
        "variant": {k: v for k, v in (patch.get("variant") or {}).items()
                    if k in variants and v in variants[k]},
        "add_grounds": [str(g).strip() for g in (patch.get("add_grounds") or []) if str(g).strip()],
        "note": patch.get("note", ""),
    }


# ---------------------------------------------------------------------------
# 2) The LLM intent-router prompt (DeepSeek at runtime emits the PATCH JSON).
# ---------------------------------------------------------------------------
ROUTER_SYSTEM = """You convert an Indian advocate's natural-language tweak request into a
STRUCTURED PATCH for a court-draft template. You do NOT write legal text, boilerplate,
sections, or citations — those are fixed and verified. You only decide which template
knobs to turn. Output ONLY valid JSON:

{"set": {<field_key>: <value>}, "toggles": {<toggle_key>: true|false},
 "variant": {<variant_key>: <value>}, "add_grounds": ["<the lawyer's extra ground, in their words>"],
 "note": "<anything you could not map to a knob>"}

Rules:
- Only use field_key / toggle_key / variant_key that appear in the SCHEMA below.
- Prefer an existing TOGGLE over add_grounds when the request matches a reviewed ground.
- Put genuinely new substantive grounds the lawyer asks for in add_grounds, phrased
  plainly in court Hindi — they will be FLAGGED as lawyer-added and advocate-reviewed.
- NEVER invent case citations or change the fixed paragraphs. If unsure, use "note".
SCHEMA: {schema}
CURRENT VALUES (for reference): {data}
"""


def _router_system(spec: dict, data: dict) -> str:
    schema = {
        "fields": [{"key": f["key"], "type": f["type"], "label": f["label"]["en"]} for f in spec.get("fields", [])],
        "toggles": [{"key": t["key"], "label": t["label"]["en"]} for t in spec.get("toggles", [])],
        "variants": spec.get("variants", {}),
    }
    return ROUTER_SYSTEM.replace("{schema}", json.dumps(schema, ensure_ascii=False)) \
                        .replace("{data}", json.dumps({k: v for k, v in (data or {}).items()
                                                       if not isinstance(v, (list, dict))}, ensure_ascii=False))


def router_messages(spec: dict, data: dict, prompt: str) -> list[dict]:
    """Build the chat messages for the runtime LLM router (DeepSeek)."""
    return [{"role": "system", "content": _router_system(spec, data)},
            {"role": "user", "content": prompt}]


def run_router(spec: dict, data: dict, prompt: str) -> dict:
    """Call the LLM intent-router (DeepSeek → Groq fallback; never Claude) and
    return a validated PATCH. Raises on any LLM/parse failure so the caller can
    fall back to parse_heuristic()."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
    raw, _meta = _call_deepseek_or_groq(
        _router_system(spec, data), prompt, max_tokens=500, claude_model="claude-sonnet-4-6")
    return validate_patch(parse_json_response(raw), spec)


def tweak(spec: dict, data: dict, prompt: str, *, use_llm: bool = True) -> dict:
    """End-to-end: prompt → PATCH → apply. LLM router with heuristic fallback.
    Returns {patch, data, changelog, source}. The legal text is never generated —
    only known knobs are turned + the lawyer's own ground captured (flagged)."""
    source = "heuristic"
    patch = None
    if use_llm:
        try:
            patch = run_router(spec, data, prompt)
            source = "llm"
        except Exception:
            patch = None
    if patch is None:
        patch = parse_heuristic(prompt, spec)
    new_data, log = apply_patch(data, patch, spec)
    return {"patch": patch, "data": new_data, "changelog": log, "source": source}


# ---------------------------------------------------------------------------
# 3) Heuristic intent-parser — a keyword fallback (and offline/demo path).
#    Production uses the LLM router above; this catches the common asks with no
#    network and guarantees the structured-patch contract is exercised.
# ---------------------------------------------------------------------------
def parse_heuristic(prompt: str, spec: dict) -> dict:
    p = (prompt or "").lower()
    toggle_keys = {t["key"] for t in spec.get("toggles", [])}
    variants = spec.get("variants", {})
    patch = {"set": {}, "toggles": {}, "variant": {}, "add_grounds": [], "note": ""}

    def has(*words): return any(w in p for w in words)

    # variant: court
    if "court" in variants:
        if has("high court", "hc", "उच्च न्यायालय"): patch["variant"]["court"] = "hc"
        elif has("sessions", "sessions court", "सत्र"): patch["variant"]["court"] = "sessions"
        elif has("magistrate", "jmfc", "मजिस्ट्रेट", "दण्डाधिकारी"): patch["variant"]["court"] = "magistrate"
    # variant: bail_type
    if "bail_type" in variants and has("anticipatory", "pre-arrest", "अग्रिम"):
        patch["variant"]["bail_type"] = "anticipatory"

    # toggles (only those the type actually has)
    def tog(key, *words):
        if key in toggle_keys and has(*words): patch["toggles"][key] = True
    tog("breadwinner", "breadwinner", "sole earner", "only earner", "कमाने वाला", "एकमात्र")
    tog("parity", "parity", "co-accused", "coaccused", "समानता", "सहअभियुक्त")
    tog("offence_upto_7yr", "7 year", "seven year", "≤7", "arnesh", "अर्नेश", "सात वर्ष")
    tog("trial_delay", "delay", "long custody", "years in jail", "विलंब", "देरी", "निरुद्ध")
    tog("standard_of_living", "standard of living", "lifestyle", "जीवन-स्तर", "जीवन स्तर")
    tog("dowry_cruelty", "dowry", "cruelty", "दहेज", "क्रूरता")
    tog("no_prima_facie", "no prima facie", "no evidence", "प्रथम दृष्टया")
    tog("family_member_principle", "family member", "relative", "पारिवारिक सदस्य")
    tog("is_company", "company", "firm", "कम्पनी", "फर्म")
    tog("why_revisable", "interlocutory", "intermediate", "अन्तरवर्ती", "मध्यवर्ती")
    # appeal-against-conviction grounds
    tog("sentence_excessive", "excessive", "disproportionate", "reduce the sentence", "reduce sentence",
        "अत्यधिक", "अनुपातहीन", "दण्ड कम")
    tog("clean_image", "clean image", "clean record", "no antecedent", "stigmat", "स्वच्छ छवि", "सीनियर सिटीजन")
    tog("fine_deposited", "refund the fine", "fine refund", "refund of fine", "जुर्माना वापस", "अर्थदण्ड वापस")
    tog("evidence_ignored", "no evidence", "evidence not led", "evidence not produced", "साक्ष्य प्रस्तुत नहीं", "साक्ष्य नहीं")
    tog("pw_contradictions", "contradict", "contradiction", "विरोधाभास")
    tog("issues_not_proved", "not proved", "issues not proved", "प्रमाणित नहीं")
    # DV §12 relief toggles
    tog("custody", "custody", "children", "child custody", "अभिरक्षा", "संतान")
    tog("compensation", "compensation", "प्रतिकर")
    tog("monetary_relief", "monetary relief", "maintenance relief", "मौद्रिक")
    tog("protection_order", "protection order", "संरक्षा आदेश")
    tog("residence_order", "residence order", "निवास आदेश")
    tog("streedhan", "streedhan", "stridhan", "स्त्रीधन", "dowry articles")
    tog("residence_right", "right to reside", "shared household", "साझा गृहस्थी")
    # quashing basis
    tog("abuse_of_process", "abuse of process", "no prima facie", "quash on merits", "प्रक्रिया का दुरुपयोग", "प्रथम दृष्टया अपराध नहीं")
    tog("victim_consenting", "victim consent", "prosecutrix consent", "स्वेच्छा से सहमत")
    tog("compromise_voluntary", "voluntary compromise", "राजीनामा", "settlement")

    # set a few obvious values
    m = re.search(r"(\d{2,3})\s*(?:year|yr|वर्ष|साल)", p)
    if m:
        for k in ("applicant_age", "petitioner_age", "revisionist_age"):
            if k in {f["key"] for f in spec.get("fields", [])}:
                patch["set"][k] = m.group(1); break
    if has("woman", "female", "lady", "महिला", "प्रार्थिनी"):
        patch["note"] = "applicant is a woman — review the statutory-leniency proviso (§480 BNSS)"

    # explicit add-ground requests
    for mm in re.finditer(r"(?:add (?:a )?ground|add (?:a )?para|ground that|यह आधार(?: भी)?(?: जोड़[ेैं]*)?)\s*[:\-—]?\s*(.+)",
                          prompt or "", re.I):
        g = mm.group(1).strip()
        g = re.sub(r"^(?:that|कि|जोड़[ेैं]*\s*कि?)\s*[:\-—]?\s*", "", g, flags=re.I).strip().rstrip(".")
        if g:
            patch["add_grounds"].append(g)
    return validate_patch(patch, spec)
