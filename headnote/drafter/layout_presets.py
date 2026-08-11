"""Choosable page layouts for a draft — the style rail on the drafting screen.

An advocate does not want ONE house format imposed on him. Court practice varies
by State and by forum: a district court in Madhya Pradesh files on 8.5x14 legal
paper, most High Courts want double spacing and a wide binding margin, and an
English commercial filing wants A4 in a serif face. So the drafting screen offers
the layout as a CHOICE he can see, the way a slide tool offers designs, instead of
burying it in a settings page.

Four sources feed that rail, in descending authority:

  1. `own`        — his captured Draft DNA. His real filings, measured. Always
                    first when he has it, because nothing beats his own paper.
  2. `reference:` — the format of a document he attached for THIS draft. Beats a
                    preset because he chose it deliberately for this matter, and
                    deliberately does NOT overwrite his saved DNA (see
                    `capture_reference`).
  3. the presets  — the four below. Real, distinct court layouts, not decoration.
  4. `standard`   — the conservative A4 floor, identical to
                    `layout_template.standard_template`.

Everything here returns the SAME layout dict shape the rest of Draft DNA speaks
(`{"page": {...}, "roles": {...}}`), so a chosen preset flows into
`render_into_layout` with no special case: the .docx is built by exactly the same
code whether the layout came from his own filing or from this rail.

Nothing here is language-specific. The typeface comes from
`layout_template.default_font_for(lang)`, so the same four presets serve an
English filing in Chennai and a Marathi one in Pune.
"""
from __future__ import annotations

import copy
from typing import Optional

from headnote.drafter import layout_template as LT

# ---------------------------------------------------------------------------
# Per-preset deltas. Each is applied ON TOP of `standard_template(font)` so a
# preset can never accidentally drop a role — it only overrides what it means to
# change. `page` is merged; `roles` is merged per role.
# ---------------------------------------------------------------------------
_PRESETS: list[dict] = [
    {
        "id": "standard",
        "name_en": "Standard court format",
        "name_hi": "सामान्य कोर्ट फॉर्मेट",
        "note_en": "A4, one-inch margins, one-and-a-half spacing. Accepted everywhere.",
        "note_hi": "A4, एक इंच मार्जिन, डेढ़ लाइन स्पेस। हर न्यायालय में स्वीकार्य।",
        "page": {},
        "roles": {},
    },
    {
        "id": "legal_district",
        "name_en": "Legal 8.5×14 — district practice",
        "name_hi": "लीगल 8.5×14 — जिला न्यायालय",
        "note_en": "The tall legal sheet district courts in MP, UP, Bihar and "
                   "Rajasthan file on, with a wide left margin for the file tag.",
        "note_hi": "म.प्र., उ.प्र., बिहार व राजस्थान के जिला न्यायालयों की लम्बी "
                   "लीगल शीट, फाइल टैग हेतु चौड़ा बायाँ मार्जिन।",
        "page": {"width": 8.5, "height": 14.0, "margin_left": 1.25,
                 "margin_right": 0.75, "margin_top": 1.0, "margin_bottom": 1.0},
        "roles": {},
    },
    {
        "id": "hc_double",
        "name_en": "High Court — double spaced",
        "name_hi": "उच्च न्यायालय — दोहरा स्पेस",
        "note_en": "Double spacing and a wide binding margin, as most High Court "
                   "registries require for paper-book filings.",
        "note_hi": "दोहरा स्पेस व चौड़ा बाइंडिंग मार्जिन — अधिकांश उच्च न्यायालय "
                   "रजिस्ट्री की पेपर-बुक शर्त।",
        "page": {"width": 8.27, "height": 11.69, "margin_left": 1.5,
                 "margin_right": 0.75, "margin_top": 1.0, "margin_bottom": 1.0},
        "roles": {
            "intro":  {"line_spacing": 2.0},
            "ground": {"line_spacing": 2.0},
            "prayer": {"line_spacing": 2.0},
        },
    },
    {
        "id": "compact",
        "name_en": "Compact — long pleadings",
        "name_hi": "सघन — लम्बे अभिवचन",
        "note_en": "Tighter spacing and slightly smaller type, for a long "
                   "written statement or a bulky annexure set.",
        "note_hi": "लम्बे जवाबदावा या भारी संलग्नकों हेतु सघन स्पेस व थोड़ा छोटा टाइप।",
        "page": {"width": 8.27, "height": 11.69, "margin_left": 1.0,
                 "margin_right": 0.85, "margin_top": 0.85, "margin_bottom": 0.85},
        "roles": {
            "intro":  {"line_spacing": 1.15, "size": 12},
            "ground": {"line_spacing": 1.15, "size": 12},
            "prayer": {"line_spacing": 1.15, "size": 12},
            "court":  {"size": 14},
        },
    },
]

PRESET_IDS = tuple(p["id"] for p in _PRESETS)


def _merge(base: dict, delta: dict) -> dict:
    out = copy.deepcopy(base)
    out["page"] = {**out.get("page", {}), **(delta.get("page") or {})}
    roles = out.setdefault("roles", {})
    for role, fmt in (delta.get("roles") or {}).items():
        roles[role] = {**(roles.get(role) or {}), **fmt}
    return out


def build(preset_id: str, lang: str = "hi") -> Optional[dict]:
    """A preset id → a full layout dict `render_into_layout` can consume."""
    spec = next((p for p in _PRESETS if p["id"] == preset_id), None)
    if spec is None:
        return None
    return _merge(LT.standard_template(LT.default_font_for(lang)), spec)


def catalogue(lang: str = "hi", *, own: Optional[dict] = None) -> list[dict]:
    """The rail, in the order it should be shown.

    `own` is his captured Draft DNA when he has one; it leads, because his own
    filed paper outranks anything we could offer him.
    """
    items: list[dict] = []
    if own and own.get("roles"):
        items.append({
            "id": "own",
            "name_en": "Your own format",
            "name_hi": "आपका अपना फॉर्मेट",
            "note_en": "Measured from your filed drafts.",
            "note_hi": "आपके फाइल किए ड्राफ्ट से लिया गया।",
            "is_own": True,
            "page": own.get("page") or {},
            "font": LT.template_primary_font(own),
            "roles": own.get("roles") or {},
        })
    for spec in _PRESETS:
        tpl = build(spec["id"], lang)
        items.append({
            "id": spec["id"],
            "name_en": spec["name_en"], "name_hi": spec["name_hi"],
            "note_en": spec["note_en"], "note_hi": spec["note_hi"],
            "is_own": False,
            "page": tpl["page"],
            "font": LT.template_primary_font(tpl),
            "roles": tpl["roles"],
        })
    return items


# ---------------------------------------------------------------------------
# REFERENCE DOCUMENT — "make it look like this one"
# ---------------------------------------------------------------------------
def capture_reference(data: bytes, *, lang: str = "hi") -> Optional[dict]:
    """A document he attached → a layout for THIS draft.

    Deliberately NOT saved as his Draft DNA. A reference is a decision about one
    matter ("file this the way the senior filed that one"); silently rewriting the
    format of every future draft from a single attachment would be a much larger,
    unasked-for change — and he has an explicit place to set his own format.

    Roles his reference does not contain fall back to standard court format in the
    reference's own typeface, so the result is always a complete document rather
    than a half-formatted one.
    """
    tpl = LT.capture_layout(data)
    if not tpl or not tpl.get("roles"):
        return None
    font = LT.template_primary_font(tpl)
    merged = LT.standard_template(font)
    merged["page"] = {**merged.get("page", {}), **(tpl.get("page") or {})}
    for role, fmt in (tpl.get("roles") or {}).items():
        merged["roles"][role] = {**(merged["roles"].get(role) or {}), **fmt}
    merged["n_drafts"] = tpl.get("n_drafts")
    return merged


# ---------------------------------------------------------------------------
# A layout arriving from the browser must be treated as untrusted input.
# ---------------------------------------------------------------------------
_PAGE_KEYS = ("width", "height", "margin_left", "margin_right",
              "margin_top", "margin_bottom", "default_tab")
_FMT_NUM = ("left_indent", "right_indent", "first_line_indent",
            "space_before", "space_after", "line_spacing", "size")
_ALIGNS = {"LEFT", "RIGHT", "CENTER", "JUSTIFY"}
_MAX_TABS = 12


def sanitise(layout: dict, lang: str = "hi") -> Optional[dict]:
    """Keep only the keys we render, with values in a sane physical range.

    The rail lets the browser hand back a captured layout, so this is the guard:
    a page 900 inches wide, a negative margin or a stray key would otherwise reach
    python-docx and either raise or emit a file Word refuses to open.
    """
    if not isinstance(layout, dict):
        return None
    roles_in = layout.get("roles")
    if not isinstance(roles_in, dict) or not roles_in:
        return None

    def num(v, lo, hi):
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            return None
        return float(v) if lo <= float(v) <= hi else None

    page_in = layout.get("page") if isinstance(layout.get("page"), dict) else {}
    page = {}
    for k in _PAGE_KEYS:
        v = num(page_in.get(k), 0.0, 48.0)
        if v is not None:
            page[k] = v
    # a sheet smaller than a postcard is not a filing
    if not (3.0 <= page.get("width", 8.27) <= 24.0 and 3.0 <= page.get("height", 11.69) <= 36.0):
        return None

    roles = {}
    for role, fmt in roles_in.items():
        if role not in LT.standard_template("x")["roles"] or not isinstance(fmt, dict):
            continue
        out = {}
        if fmt.get("align") in _ALIGNS:
            out["align"] = fmt["align"]
        out["bold"] = bool(fmt.get("bold"))
        for k in _FMT_NUM:
            hi = 6.0 if k in ("left_indent", "right_indent", "first_line_indent") else 200.0
            v = num(fmt.get(k), -6.0 if k == "first_line_indent" else 0.0, hi)
            if v is not None:
                out[k] = v
        if isinstance(fmt.get("size"), (int, float)) and not 4 <= fmt["size"] <= 72:
            out.pop("size", None)
        font = fmt.get("font")
        if isinstance(font, str) and 0 < len(font) <= 64:
            out["font"] = font
        tabs = []
        for t in (fmt.get("tabs") or [])[:_MAX_TABS]:
            if not isinstance(t, dict):
                continue
            pos = num(t.get("pos"), 0.0, 24.0)
            if pos is not None:
                tabs.append({"pos": pos, "align": t.get("align") if t.get("align") in _ALIGNS else "LEFT"})
        out["tabs"] = tabs
        roles[role] = out
    if not roles:
        return None

    base = LT.standard_template(LT.default_font_for(lang))
    base["page"] = {**base["page"], **page}
    for role, fmt in roles.items():
        base["roles"][role] = {**(base["roles"].get(role) or {}), **fmt}
    return base


def resolve(*, layout_id: Optional[str], layout: Optional[dict],
            user_id: Optional[str], lang: str) -> tuple[Optional[dict], str]:
    """What the export should actually render into → (template, how).

    `how` is the word the screen and the file both report, so they can never
    disagree about whose format the advocate is holding:
      "own" · "reference" · the preset id · "standard"
    """
    if isinstance(layout, dict) and layout:
        clean = sanitise(layout, lang)
        if clean:
            return clean, "reference"
    if layout_id == "own" or not layout_id:
        tpl = None
        if user_id:
            try:
                from headnote.drafter import style_profile as SP
                tpl = SP.load_layout(user_id)
            except Exception:
                tpl = None
        if tpl and tpl.get("roles"):
            return tpl, "own"
        if layout_id == "own":
            # He asked for his own format and it is gone. Say "standard" rather
            # than "own" — the header is what the screen tells him he is holding.
            return LT.standard_template(LT.default_font_for(lang)), "standard"
        return None, ""
    built = build(layout_id, lang)
    if built:
        return built, layout_id
    return None, ""
