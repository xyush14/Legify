"""Serve the V2 canonical engine THROUGH the existing universal editor
(static/draft-template.html) — keep the live UI, swap the engine.

The editor calls GET /api/draft/template-schema/{id} (drives the form) and
POST /api/draft/render-template {doc_type, fields, lang} (the live preview). This
module maps a per-court canonical "template id" → the reviewed `field_spec`
(flattened to the editor's {label_hi,label_en,type,section} shape, with toggles
appended as checkbox fields) and → the full filing BUNDLE (Index + Application +
Affidavit …) as self-contained HTML. No new UI; all V1 features (OCR, translate,
live-preview, PDF/print/WhatsApp) keep working unchanged.
"""
from __future__ import annotations

import inspect

from headnote.drafter.bundle import module_for, assemble
from headnote.drafter.templates._doc_header import HEADER_CSS

# editor "template id" (what /draft/template/{id} loads) → (canonical type, court, bail_type)
CANONICAL_MAP = {
    "bail_hc": ("bail", "hc", "regular"),
    "bail_sessions": ("bail", "sessions", "regular"),
    "bail_magistrate": ("bail", "magistrate", "regular"),
    "anticipatory_bail": ("bail", "sessions", "anticipatory"),
    "anticipatory_bail_hc": ("bail", "hc", "anticipatory"),
    "quashing": ("quashing", "hc", "regular"),
    "revision_hc": ("revision", "hc", "regular"),
    "revision_sessions": ("revision", "sessions", "regular"),
    "appeal_hc": ("appeal", "hc", "regular"),
    "appeal_sessions": ("appeal", "sessions", "regular"),
    "discharge_sessions": ("discharge", "sessions", "regular"),
    "discharge_magistrate": ("discharge", "magistrate", "regular"),
    "production_magistrate": ("production", "magistrate", "regular"),
    "production_sessions": ("production", "sessions", "regular"),
    "reply_magistrate": ("reply", "magistrate", "regular"),
    "reply_sessions": ("reply", "sessions", "regular"),
    "reply_hc": ("reply", "hc", "regular"),
    "complaint_156": ("complaint_156", "magistrate", "regular"),
    "default_bail": ("default_bail", "magistrate", "regular"),
    "recall_311": ("recall_311", "sessions", "regular"),
    "supurdgi": ("supurdgi", "magistrate", "regular"),
    "exemption_205": ("exemption_205", "magistrate", "regular"),
    "compounding": ("compounding", "magistrate", "regular"),
    "restitution_9": ("restitution_9", "family", "regular"),
    "statement_178": ("statement_178", "magistrate", "regular"),
    "ni_138_dismiss": ("ni_138_dismiss", "magistrate", "regular"),
    "suspension_389": ("suspension_389", "hc", "regular"),
    "mention_memo": ("mention_memo", "hc", "regular"),
    "divorce_13": ("divorce_13", "family", "regular"),
    "general_affidavit": ("general_affidavit", "any", "regular"),
    "legal_notice": ("legal_notice", "any", "regular"),
    "production_warrant": ("production_warrant", "magistrate", "regular"),
    "writ_petition": ("writ_petition", "hc", "regular"),
    "habeas_corpus": ("habeas_corpus", "hc", "regular"),
    "stay_petition": ("stay_petition", "hc", "regular"),
    "transfer_petition": ("transfer_petition", "hc", "regular"),
    "mact_166": ("mact_166", "any", "regular"),
    "maintenance": ("maintenance", "family", "regular"),
    "dv": ("dv", "magistrate", "regular"),
    "cheque_138": ("cheque", "magistrate", "regular"),
    "parivad": ("parivad", "magistrate", "regular"),
    "vakalatnama": ("vakalatnama", "any", "regular"),
}

LABELS = {
    "bail_hc": {"en": "Regular Bail — High Court", "hi": "नियमित जमानत — उच्च न्यायालय"},
    "bail_sessions": {"en": "Regular Bail — Sessions", "hi": "नियमित जमानत — सत्र न्यायालय"},
    "bail_magistrate": {"en": "Bail — Magistrate", "hi": "जमानत — मजिस्ट्रेट"},
    "anticipatory_bail": {"en": "Anticipatory Bail — Sessions", "hi": "अग्रिम जमानत — सत्र न्यायालय"},
    "anticipatory_bail_hc": {"en": "Anticipatory Bail — High Court", "hi": "अग्रिम जमानत — उच्च न्यायालय"},
    "quashing": {"en": "Quashing Petition (S.528 / 482)", "hi": "अभिखण्डन याचिका (धारा 528)"},
    "revision_hc": {"en": "Criminal Revision — High Court", "hi": "पुनरीक्षण — उच्च न्यायालय"},
    "revision_sessions": {"en": "Criminal Revision — Sessions", "hi": "पुनरीक्षण — सत्र न्यायालय"},
    "appeal_hc": {"en": "Appeal against Conviction — HC", "hi": "दोषसिद्धि अपील — उच्च न्यायालय"},
    "appeal_sessions": {"en": "Appeal against Conviction — Sessions", "hi": "दोषसिद्धि अपील — सत्र न्यायालय"},
    "discharge_sessions": {"en": "Discharge (S.250/227) — Sessions", "hi": "उन्मोचन (धारा 250/227) — सत्र"},
    "discharge_magistrate": {"en": "Discharge (S.262/239) — Magistrate", "hi": "उन्मोचन (धारा 262/239) — मजिस्ट्रेट"},
    "production_magistrate": {"en": "Production of Documents (S.94/91) — Magistrate", "hi": "दस्तावेज तलब (धारा 94/91) — मजिस्ट्रेट"},
    "production_sessions": {"en": "Production of Documents (S.94/91) — Sessions", "hi": "दस्तावेज तलब (धारा 94/91) — सत्र"},
    "reply_magistrate": {"en": "Reply / जबाव — Magistrate", "hi": "जबाव — मजिस्ट्रेट"},
    "reply_sessions": {"en": "Reply / जबाव — Sessions", "hi": "जबाव — सत्र न्यायालय"},
    "reply_hc": {"en": "Reply / जबाव — High Court", "hi": "जबाव — उच्च न्यायालय"},
    "complaint_156": {"en": "FIR Direction to Police (S.175(3)/156(3))", "hi": "पुलिस को FIR निर्देश (धारा 175(3)/156(3))"},
    "default_bail": {"en": "Default / Statutory Bail (S.187(3)/167(2))", "hi": "अनिवार्य/डिफॉल्ट जमानत (धारा 187(3)/167(2))"},
    "recall_311": {"en": "Recall / Re-examine Witness (S.348/311)", "hi": "साक्षी पुनः-परीक्षण (धारा 348/311)"},
    "supurdgi": {"en": "Interim Custody / सुपुर्दगी (S.497/503·451/457)", "hi": "सुपुर्दगी — अन्तरिम custody (धारा 497/503·451/457)"},
    "exemption_205": {"en": "Dispense Personal Attendance (S.228/205)", "hi": "व्यक्तिगत उपस्थिति से छूट (धारा 228/205)"},
    "compounding": {"en": "Compounding on Compromise (S.359/320)", "hi": "अपराध शमन — राजीनामा (धारा 359/320)"},
    "restitution_9": {"en": "Restitution of Conjugal Rights (S.9 HMA)", "hi": "दाम्पत्य पुर्नस्थापना (धारा 9 हि.वि.अ.)"},
    "statement_178": {"en": "Record Statement before Court (S.178)", "hi": "दस्तयावी बयान — कथन न्यायालय के समक्ष (धारा 178)"},
    "ni_138_dismiss": {"en": "§138 NI — Notice-not-served objection (accused)", "hi": "§138 NI — सूचना तामील आपत्ति (अभियुक्त)"},
    "suspension_389": {"en": "Suspend Sentence + Bail Pending Appeal (S.430/389)", "hi": "दण्डादेश निलंबन + जमानत (धारा 430/389)"},
    "mention_memo": {"en": "Mention Memo (Urgent Listing)", "hi": "स्मरण पत्र (अविलम्ब सूचीबद्धता)"},
    "divorce_13": {"en": "Divorce (S.13 HMA)", "hi": "विवाह विच्छेद (धारा 13 हि.वि.अ.)"},
    "general_affidavit": {"en": "General Affidavit (शपथ पत्र)", "hi": "शपथ पत्र (सामान्य)"},
    "legal_notice": {"en": "Legal / Demand Notice", "hi": "विधिक सूचना पत्र"},
    "production_warrant": {"en": "Jail Production Warrant (S.302/267)", "hi": "उत्पादन वारंट (धारा 302/267)"},
    "writ_petition": {"en": "Writ Petition (Art. 226/227)", "hi": "रिट याचिका (अनुच्छेद 226/227)"},
    "habeas_corpus": {"en": "Habeas Corpus (Art. 226)", "hi": "बन्दी प्रत्यक्षीकरण (अनुच्छेद 226)"},
    "stay_petition": {"en": "Stay Application (HC I.A.)", "hi": "स्थगन आवेदन (उच्च न्यायालय)"},
    "transfer_petition": {"en": "Criminal Transfer Petition (S.447/407)", "hi": "आपराधिक स्थानान्तरण (धारा 447/407)"},
    "mact_166": {"en": "Motor Accident Claim (S.166 MV Act)", "hi": "मोटर दुर्घटना दावा (धारा 166)"},
    "maintenance": {"en": "Maintenance (S.144 / 125)", "hi": "भरण-पोषण (धारा 144 / 125)"},
    "dv": {"en": "Domestic Violence (S.12 PWDVA)", "hi": "घरेलू हिंसा (धारा 12)"},
    "cheque_138": {"en": "Cheque Dishonour Complaint (S.138)", "hi": "चेक बाउंस परिवाद (धारा 138)"},
    "parivad": {"en": "Private Complaint (S.223 / 200)", "hi": "परिवाद पत्र (धारा 223)"},
    "vakalatnama": {"en": "Vakalatnama", "hi": "वकालतनामा"},
}

_SECTION_FIX = {"crime": "fir"}   # map our section ids onto the editor's SECTION_LABELS


def is_canonical(tid: str) -> bool:
    return tid in CANONICAL_MAP


def _spec(tid: str) -> dict:
    t, court, bt = CANONICAL_MAP[tid]
    mod = module_for(t)
    n = len(inspect.signature(mod.field_spec).parameters)
    if n >= 2:
        return mod.field_spec(court, bt)
    if n == 1:
        return mod.field_spec(court)
    return mod.field_spec()


def schema(tid: str) -> dict:
    """Canonical field_spec → the editor's template-schema shape."""
    spec = _spec(tid)
    fields = []
    for f in spec.get("fields", []):
        if f.get("auto"):
            continue   # derived (court name, custody days, §138 cause date) — never typed
        fields.append({
            "key": f["key"], "label_en": f["label"]["en"], "label_hi": f["label"]["hi"],
            "type": f.get("type", "text"), "required": bool(f.get("required")),
            "hint": f.get("hint", ""), "section": _SECTION_FIX.get(f.get("section", "matter"), f.get("section", "matter")),
            "options": f.get("options") or None,   # select dropdown choices
            "default": f.get("default"),           # pre-fill (e.g. discharge case-type)
            "depends": f.get("depends") or None,    # show only when this toggle is ON
        })
    for tg in spec.get("toggles", []):
        fields.append({
            "key": tg["key"], "label_en": tg["label"]["en"], "label_hi": tg["label"]["hi"],
            "type": "toggle", "required": False, "section": "grounds",
            "default": bool(tg.get("default")),
        })
    lab = LABELS.get(tid, {"en": tid, "hi": tid})
    return {"id": tid, "label_en": lab["en"], "label_hi": lab["hi"],
            "deterministic": True, "fields": fields}


def to_data(tid: str, fields: dict) -> dict:
    """Flat editor fields → canonical data dict (toggles→grounds, lists, court)."""
    t, court, bt = CANONICAL_MAP[tid]
    spec = _spec(tid)
    toggle_keys = {tg["key"] for tg in spec.get("toggles", [])}
    list_keys = {f["key"] for f in spec.get("fields", []) if f.get("type") == "section_list"}
    data, grounds = {}, {}
    for k, v in (fields or {}).items():
        if k in toggle_keys:
            grounds[k] = v in (True, "true", "on", 1, "1")
        elif k in list_keys:
            data[k] = [x.strip() for x in str(v or "").split(",") if x.strip()]
        else:
            data[k] = v
    # default-on toggles when the form hasn't sent them yet
    for tg in spec.get("toggles", []):
        grounds.setdefault(tg["key"], bool(tg.get("default")))
    data["grounds"] = grounds
    if court and court != "any":
        data["court"] = court
    if bt:
        data["bail_type"] = bt
    return data


def document(tid: str, fields: dict, lang: str = "hi") -> str:
    """The full filing bundle as ONE self-contained HTML string (canonical CSS
    inlined so it renders correctly inside the existing editor's preview pane)."""
    t, _court, _bt = CANONICAL_MAP[tid]
    b = assemble(module_for(t), to_data(tid, fields))
    body = b["html_hi"] if lang == "hi" else b["html_en"]
    # Inline the canonical CSS + lay the bundle out as separate A4 sheets with a
    # gap, and neutralise the host editor's own white "sheet" so they don't nest
    # or touch (the overlap). `:has` scopes the host override to bundle previews.
    extra = (
        ".v2-bundle{display:flex;flex-direction:column;align-items:center;gap:26px;width:100%}"
        ".v2-bundle .doc-a4{margin:0;flex:0 0 auto}"
        "#doc-page:has(.v2-bundle),.doc-page:has(.v2-bundle){background:transparent!important;"
        "box-shadow:none!important;border:0!important;padding:0!important;max-width:none!important}"
    )
    return f"<style>{HEADER_CSS}\n{extra}</style>\n<div class=\"v2-bundle\">{body}</div>"
