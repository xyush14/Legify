"""Field-type coercion — the guard against the character-by-character grounds bug.

A production Hindi bail application came back with 28 numbered `यह कि` paragraphs,
one per LETTER of the advocate's own sentence "15 दिन से न्यायिक अभिरक्षा में".

Cause: three producers write into the draft data dict — the editor form, the OCR
auto-fill and the LLM field-extractor — but only the form produced the right types.
`custom_grounds` is a textarea to the lawyer and a LIST to every render(), and
`for c in "15 दिन"` is not a Python error: it silently yields one character per
pass. `to_data` split the string correctly; `from_prompt` → `extract_fields` →
`apply_patch` bypassed `to_data` entirely, so the LLM's raw string reached render.

These tests pin the coercion at the shared chokepoint so any new producer is safe.
"""
from __future__ import annotations

import re

import pytest

from headnote.drafter.prompt_tweak import apply_patch, validate_patch
from headnote.drafter.template_adapter import _spec, to_data
from headnote.drafter.templates import bail_regular
from headnote.drafter.templates._fields import (
    LONGTEXT, SECTION_LIST, TABLE, TOGGLE, coerce_data, coerce_value,
)

SPEC = _spec("bail_magistrate")
# the exact value production's extractor returned for this prompt
REAL_GROUND = "15 दिन से न्यायिक अभिरक्षा में"


def _grounds(html: str) -> list[str]:
    return [g.strip() for g in re.findall(r"यहकि,\s*([^<]{1,120})", html)]


# --- the unit: coerce_value ------------------------------------------------
def test_custom_grounds_string_becomes_one_entry_not_characters():
    assert coerce_value("custom_grounds", REAL_GROUND, LONGTEXT) == [REAL_GROUND]


def test_custom_grounds_splits_on_newlines_one_ground_per_line():
    assert coerce_value("custom_grounds", "पहला आधार\nदूसरा आधार", LONGTEXT) == [
        "पहला आधार", "दूसरा आधार",
    ]


def test_custom_grounds_already_a_list_is_preserved():
    assert coerce_value("custom_grounds", ["a", "b"], LONGTEXT) == ["a", "b"]


def test_custom_grounds_blank_and_none_become_empty_list():
    assert coerce_value("custom_grounds", "", LONGTEXT) == []
    assert coerce_value("custom_grounds", None, LONGTEXT) == []
    assert coerce_value("custom_grounds", "  \n \n ", LONGTEXT) == []


def test_section_list_splits_on_commas_and_newlines():
    assert coerce_value("sections", "420 भादंसं, 380", SECTION_LIST) == ["420 भादंसं", "380"]
    assert coerce_value("sections", "420\n380", SECTION_LIST) == ["420", "380"]


def test_table_field_rejects_a_bare_string():
    # renders call row.get(...) per row — a string used to raise AttributeError → 500
    assert coerce_value("co_accused", "Ramesh", TABLE) == []
    rows = [{"name": "Ramesh"}]
    assert coerce_value("co_accused", rows, TABLE) == rows


def test_toggle_accepts_the_form_and_json_truthy_spellings():
    for truthy in (True, "true", "on", 1, "1"):
        assert coerce_value("trial_delay", truthy, TOGGLE) is True
    for falsy in (False, "false", "off", 0, "", None):
        assert coerce_value("trial_delay", falsy, TOGGLE) is False


def test_plain_text_values_are_never_touched():
    assert coerce_value("applicant_name", "रामेश्वर", "name") == "रामेश्वर"
    assert coerce_value("fir_number", "123/2025", "text") == "123/2025"


def test_coerce_data_uses_the_specs_own_declared_types():
    out = coerce_data(
        {"custom_grounds": REAL_GROUND, "sections": "420, 380", "applicant_name": "रामेश्वर"},
        SPEC,
    )
    assert out["custom_grounds"] == [REAL_GROUND]
    assert out["sections"] == ["420", "380"]
    assert out["applicant_name"] == "रामेश्वर"


# --- the chokepoint: validate_patch (LLM extractor + tweak router) --------
def test_validate_patch_coerces_the_llms_string_values():
    v = validate_patch({"set": {"custom_grounds": REAL_GROUND, "sections": "420, 380"}}, SPEC)
    assert v["set"]["custom_grounds"] == [REAL_GROUND]
    assert v["set"]["sections"] == ["420", "380"]


def test_validate_patch_still_strips_unknown_keys():
    v = validate_patch({"set": {"not_a_field": "x", "applicant_name": "रामेश्वर"}}, SPEC)
    assert "not_a_field" not in v["set"]
    assert v["set"]["applicant_name"] == "रामेश्वर"


def test_apply_patch_add_grounds_survives_a_raw_string_already_in_data():
    # an older saved draft / OCR autofill can leave custom_grounds as a string;
    # .append on it used to raise AttributeError
    data, _log = apply_patch(
        {"custom_grounds": REAL_GROUND},
        validate_patch({"add_grounds": ["नया आधार"]}, SPEC),
        SPEC,
    )
    assert data["custom_grounds"] == [REAL_GROUND, "नया आधार"]


# --- the regression, end to end on the real render ------------------------
def test_rendered_bail_application_has_no_single_character_grounds():
    """The exact production reproduction: extractor string → render."""
    patch = validate_patch({"set": {"custom_grounds": REAL_GROUND}}, SPEC)
    data, _ = apply_patch({}, patch, SPEC)
    html = bail_regular.render_hi(dict(data, court="magistrate", bail_type="regular"))

    grounds = _grounds(html)
    assert [g for g in grounds if len(g) == 1] == [], "grounds split into characters"
    assert any(REAL_GROUND in g for g in grounds), "the advocate's ground went missing"


def test_english_render_is_equally_protected():
    patch = validate_patch({"set": {"custom_grounds": "in custody for 15 days"}}, SPEC)
    data, _ = apply_patch({}, patch, SPEC)
    html = bail_regular.render_en(dict(data, court="magistrate", bail_type="regular"))
    paras = [p.strip() for p in re.findall(r"That\s+([^<]{1,120})", html)]
    assert [p for p in paras if len(p) == 1] == []
    assert any("in custody for 15 days" in p for p in paras)


def test_to_data_and_validate_patch_agree_on_shape():
    """The form path and the LLM path must produce the same data shape — they
    diverging is what let this bug exist in only one of them."""
    from_form = to_data("bail_magistrate", {"custom_grounds": REAL_GROUND, "sections": "420, 380"})
    from_llm, _ = apply_patch(
        {}, validate_patch({"set": {"custom_grounds": REAL_GROUND, "sections": "420, 380"}}, SPEC), SPEC
    )
    for key in ("custom_grounds", "sections"):
        assert from_form[key] == from_llm[key], f"{key} differs between form and LLM paths"
