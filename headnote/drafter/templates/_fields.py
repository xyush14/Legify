"""Input-field schema — the per-client variables a lawyer fills/edits for an
application, PLUS the toggles & optional bits ("what more can change").

Every builder exposes `field_spec(...)` → a declarative schema the form UI renders
and validates against. The schema's `key`s are the SAME keys the document render
(`render_hi`/`render_en`) reads, so the form and the draft stay in lock-step.

A field carries: type · required · section (UI group) · hint · `ocr` (which scan
auto-fills it: fir/cheque/order) · `auto` (derived, never typed: custody days,
the §138 cause-of-action date, …) · `options` (for select) · `depends` (show only
when a toggle is on). Toggles are the conditional grounds / optional sections — the
"what more can be changed" beyond the obvious client variables.
"""
from __future__ import annotations

# ---- field types the form UI understands ----
TEXT, NAME, DATE, NUMBER, MONEY, ADDRESS, SECTION_LIST, LONGTEXT, SELECT, TABLE = (
    "text", "name", "date", "number", "money", "address",
    "section_list", "longtext", "select", "table",
)
TOGGLE = "toggle"

# ---- UI section groups (ordered) ----
# NOTE: every id here must have a matching label in the editor's SECTION_LABELS
# (static/draft-template.html); the editor groups fields by each field's own
# `section`, so an id missing a label would render with its raw string.
SECTION_ORDER = [
    ("court",      {"hi": "न्यायालय",        "en": "Court"}),
    ("parties",    {"hi": "पक्षकार",          "en": "Parties"}),
    ("applicant",  {"hi": "आवेदक",            "en": "Applicant"}),
    ("respondent", {"hi": "प्रत्यर्थी",        "en": "Respondent"}),
    ("crime",      {"hi": "अपराध / प्रकरण",   "en": "Crime / Matter"}),
    ("custody",    {"hi": "निरोध एवं विवेचना", "en": "Custody / Investigation"}),
    ("order",      {"hi": "विवादित आदेश",     "en": "Impugned Order"}),
    ("conviction", {"hi": "दोषसिद्धि विवरण",   "en": "Conviction Details"}),
    ("marriage",   {"hi": "विवाह एवं परिवार",  "en": "Marriage & Family"}),
    ("income",     {"hi": "आय एवं भरण-पोषण",  "en": "Income & Maintenance"}),
    ("facts",      {"hi": "तथ्य",             "en": "Facts"}),
    ("grounds",    {"hi": "आधार / विकल्प",    "en": "Grounds / Options"}),
    ("filing",     {"hi": "दाखिल",            "en": "Filing"}),
]


def f(key, hi, en, type=TEXT, required=False, section="parties", *,
      hint="", ocr=None, options=None, default=None, depends=None, auto=False):
    """One input field. `ocr`=scan that fills it; `auto`=derived (not typed);
    `depends`=toggle key that must be ON; `options`=[{value,label}] for select."""
    return {
        "key": key, "label": {"hi": hi, "en": en}, "type": type,
        "required": required, "section": section, "hint": hint,
        "ocr": ocr, "options": options, "default": default,
        "depends": depends, "auto": auto,
    }


def toggle(key, hi, en, default=False, *, hint=""):
    """A conditional ground / optional section the lawyer switches on or off."""
    return {"key": key, "label": {"hi": hi, "en": en}, "type": TOGGLE,
            "default": default, "hint": hint}


def custom_grounds(hi="अतिरिक्त आधार (प्रति पंक्ति एक)",
                   en="Additional grounds (one per line)"):
    """The lawyer's free-text case-specific grounds. EVERY render already reads
    `a.get("custom_grounds")` as a list and appends one `यह कि …` para per entry;
    this exposes the field so that escape-hatch is reachable from the form.
    `to_data` splits the textarea on newlines back into that list."""
    return f("custom_grounds", hi, en, LONGTEXT, section="grounds",
             hint="प्रत्येक आधार नई पंक्ति में — ज्यों-का-त्यों 'यह कि' पैरा बनेगा")


# Keys declared as free text that EVERY render() nevertheless iterates as a list,
# one paragraph per entry (see custom_grounds above). The declared type alone can't
# tell us: the field is a textarea to the lawyer and a list to the document.
LIST_TEXT_KEYS = {"custom_grounds"}


def coerce_value(key, value, ftype=None):
    """One field's raw value → the shape `render_hi`/`render_en` actually expects.

    Three different producers write into the data dict — the editor form, the OCR
    auto-fill, and the LLM field-extractor — and only the form naturally produces
    the right types. A string where a render iterates a list is not a Python type
    error: `for c in "15 दिन"` silently yields one CHARACTER per pass, so the
    document rendered a numbered `यह कि` paragraph per letter. Coerce at the entry
    point rather than trusting the producer.
    """
    if ftype == TOGGLE:
        return value in (True, "true", "on", 1, "1")
    if ftype == TABLE:
        # renders call row.get(...) per row; a bare string raises AttributeError → 500
        return value if isinstance(value, list) and all(isinstance(r, dict) for r in value) else []
    if ftype == SECTION_LIST or key in LIST_TEXT_KEYS:
        if isinstance(value, list):
            return [str(x).strip() for x in value if str(x).strip()]
        if value is None:
            return []
        # commas for a section list ("420, 380"); newlines for one-ground-per-line
        raw = str(value)
        parts = raw.replace(",", "\n").splitlines() if ftype == SECTION_LIST else raw.splitlines()
        return [p.strip() for p in parts if p.strip()]
    return value


def coerce_data(data, spec):
    """Apply `coerce_value` across a data dict using `spec`'s own declared types."""
    types = {fl["key"]: fl.get("type") for fl in (spec or {}).get("fields", [])}
    types.update({tg["key"]: TOGGLE for tg in (spec or {}).get("toggles", [])})
    return {k: coerce_value(k, v, types.get(k)) for k, v in (data or {}).items()}


def build_spec(doc_type, fields, toggles=None, *, variants=None, companions=None):
    """Assemble the schema the API/UI consumes: fields grouped into ordered
    sections, the toggle set, the forum variants, and the auto-attached companions."""
    used = {fld["section"] for fld in fields}
    sections = [{"id": sid, "label": lbl,
                 "fields": [fl["key"] for fl in fields if fl["section"] == sid]}
                for sid, lbl in SECTION_ORDER if sid in used]
    return {
        "type": doc_type,
        "sections": sections,
        "fields": fields,
        "toggles": toggles or [],
        "variants": variants or {},      # e.g. court: [magistrate, sessions, hc]
        "companions": companions or [],  # auto-attached docs (affidavit, vakalatnama…)
    }
