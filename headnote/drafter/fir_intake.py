"""FIR → bail intake: the shared brain behind "Draft from FIR".

An FIR OCR result (`ocr.ocr_fir_pages`) is mapped to the bail template's own
slot keys here, in ONE place, so every surface — the web drafter, the WhatsApp
bot — fills a bail application from the same logic.

Two functions:

• `fir_ocr_to_bail_slots(extracted, lang)` — the pure field mapping. FIR fields
  the applicant particulars, police station, crime no., sections, arrest date,
  and the prosecution narrative in the draft's language.

• `confirm_fields(doc_type, slots, lang)` — turns those slots into the CONFIRM
  step the UI shows before anything is written into the draft. Every value that
  came off the FIR is flagged `found` (amber — machine-read, needs the advocate's
  eye); required fields the FIR can't supply are flagged `missing` so the UI can
  prompt for them. Nothing here is ever silently trusted — the advocate is the
  gate (zero-fabrication).

The field keys and labels are pulled from the canonical bail `field_spec` (via
`template_adapter.schema`) so this stays in lock-step with the render: a field
renamed in the template can never drift out of sync with the confirm step.
"""
from __future__ import annotations

from typing import Any


def fir_ocr_to_bail_slots(extracted: dict, lang: str = "hi") -> dict[str, Any]:
    """Map an FIR OCR result (from `ocr_fir_pages`) → bail-template slot dict.

    `lang` selects which narrative ('hi'/'en') fills `facts_narrative`; it falls
    back to whichever narrative the OCR did return. Court/jurisdiction is NOT
    inferred here — the filing court is the advocate's call, never guessed.
    """
    out: dict[str, Any] = {}
    accused = extracted.get("accused_details") or []
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
    # Prosecution story → the facts para. Prefer the draft language's narrative,
    # fall back to the other one so a Hindi-only FIR still fills an EN draft.
    narrative = (
        (extracted.get("narrative_hi") if lang != "en" else extracted.get("narrative_en"))
        or extracted.get("narrative_en") or extracted.get("narrative_hi")
        or extracted.get("narrative")
    )
    if narrative and str(narrative).strip():
        out["facts_narrative"] = str(narrative).strip()
    return out


# Fields the FIR can never legitimately supply — the advocate must decide them.
# The filing court in particular is never derived from the FIR's incident
# district (the incident district ≠ the chosen forum), only suggested.
_JURISDICTION_KEYS = {"court_city", "court_name"}


def confirm_fields(doc_type: str, slots: dict[str, Any], lang: str = "hi") -> list[dict]:
    """Build the confirm-step field list from the canonical bail schema.

    Each entry: {key, label, type, required, section, value, source, status,
    suggestion}. `status` drives the UI:
      • "found"   — value came off the FIR → show amber, advocate confirms
      • "missing" — required, FIR couldn't supply it → prompt the advocate
      • "empty"   — optional and unfilled → offer as an add
    `court_city` gets the FIR's district as a non-binding `suggestion` (one-tap
    accept in the UI) but is never pre-filled — jurisdiction stays the
    advocate's decision.
    """
    from headnote.drafter import template_adapter as TA

    schema = TA.schema(doc_type)
    label_key = "label_hi" if lang != "en" else "label_en"
    out: list[dict] = []
    for f in schema.get("fields", []):
        if f.get("type") == "toggle":
            continue  # grounds/toggles are decided later, not part of the FIR confirm
        key = f["key"]
        raw = slots.get(key)
        has_value = raw not in (None, "", [], {})
        if has_value and key not in _JURISDICTION_KEYS:
            status, source = "found", "fir"
        elif f.get("required"):
            status, source = "missing", ""
        else:
            status, source = "empty", ""
        entry = {
            "key": key,
            "label": f.get(label_key) or f.get("label_en") or key,
            "type": f.get("type", "text"),
            "required": bool(f.get("required")),
            "section": f.get("section", ""),
            "value": raw if (has_value and key not in _JURISDICTION_KEYS) else "",
            "source": source,
            "status": status,
        }
        if key == "court_city" and slots.get("district"):
            entry["suggestion"] = slots["district"]  # offer the FIR district, don't assume it
        out.append(entry)
    return out
