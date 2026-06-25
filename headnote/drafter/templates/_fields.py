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
SECTION_ORDER = [
    ("court",   {"hi": "न्यायालय",        "en": "Court"}),
    ("parties", {"hi": "पक्षकार",          "en": "Parties"}),
    ("crime",   {"hi": "अपराध / प्रकरण",   "en": "Crime / Matter"}),
    ("facts",   {"hi": "तथ्य",             "en": "Facts"}),
    ("grounds", {"hi": "आधार / विकल्प",    "en": "Grounds / Options"}),
    ("filing",  {"hi": "दाखिल",            "en": "Filing"}),
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
