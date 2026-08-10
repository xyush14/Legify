"""The junior's note + the one door — the deterministic half of V2 Draft.

Everything under test here runs with no model, no network and no quota, which is
the whole point: these checks are meant to fire on every draft including the
never-fail skeleton floor. So the tests are exact rather than tolerant.
"""
from datetime import date

import pytest

from headnote.drafter import onedoor, preflight as pf


# --------------------------------------------------------------------------- helpers

def _draft(**over):
    """A well-formed Hindi bail application, as the engine actually emits one."""
    html = (
        '<div class="cb-doc">'
        '<p style="text-align:center">न्यायालय श्रीमान अपर सत्र न्यायाधीश महोदय, भोपाल (म.प्र.)</p>'
        '<p style="text-align:center">जमानत आवेदन क्रमांक 214 / 2026</p>'
        '<p>रमेश वर्मा पुत्र मोहनलाल वर्मा</p><p>..... आवेदक</p><p>विरुद्ध</p>'
        '<p>म.प्र. राज्य द्वारा थाना कोतवाली</p><p>..... अनावेदक</p>'
        '<p>धारा 483 बी.एन.एस.एस. (439 दं.प्र.सं.) के अंतर्गत जमानत आवेदन</p>'
        '<ol><li>यह कि आवेदक दिनांक 12.03.2025 से न्यायिक अभिरक्षा में निरुद्ध है।</li>'
        '<li>यह कि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।</li></ol>'
        '<div class="cb-prayer"><p>अतः प्रार्थना है कि आवेदक को जमानत का लाभ प्रदान करने '
        'की कृपा करें।</p></div></div>'
    )
    out = {"ok": True, "doc_type": "bail", "html_hi": html}
    out.update(over)
    return out


def _by_id(res):
    return {c["id"]: c for c in res["checks"]}


# --------------------------------------------------------------------------- shape

def test_review_returns_every_check_and_never_raises():
    res = pf.review(_draft(), brief="FIR 12.03.2025")
    ids = _by_id(res)
    for want in ("closer", "prayer", "cause_title", "code_date", "blanks",
                 "ungrounded", "cite_at_hearing", "companions"):
        assert want in ids, want
    assert res["ok"] is True
    assert res["counts"]["ok"] + res["counts"]["amber"] == len(res["checks"])


def test_amber_items_come_first_because_the_rail_is_read_top_down():
    res = pf.review(_draft(ungrounded=["सुरेश"], companions=["शपथ पत्र"]))
    sev = [c["severity"] for c in res["checks"]]
    assert sev == sorted(sev, key=lambda s: 0 if s == "amber" else 1)


def test_review_of_garbage_degrades_instead_of_raising():
    assert pf.review(None)["ok"] is True          # no draft text → one amber, no crash
    assert pf.review({"doc_type": 5, "html_hi": 7})["ok"] in (True, False)


def test_a_clean_draft_has_no_amber_at_all():
    res = pf.review(_draft(), brief="FIR दिनांक 12.03.2025")
    assert res["counts"]["amber"] == 0, [c["title"] for c in res["checks"]
                                        if c["severity"] == "amber"]


# --------------------------------------------------------------------------- closer

def test_closer_detected_and_missing():
    assert pf.review(_draft())["checks"] and _by_id(pf.review(_draft()))["closer"]["severity"] == "ok"
    d = _draft()
    d["html_hi"] = d["html_hi"].replace("यह कि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।",
                                        "यह कि आवेदक निर्दोष है।")
    assert _by_id(pf.review(d))["closer"]["severity"] == "amber"


def test_closer_is_recognised_in_english_too():
    res = pf.review({"ok": True, "doc_type": "bail",
                     "html_en": "<p>Further arguments will be advanced at the time of hearing.</p>"})
    assert _by_id(res)["closer"]["severity"] == "ok"


# --------------------------------------------------------------------------- prayer

def test_prayer_must_name_the_relief():
    d = _draft()
    d["html_hi"] = d["html_hi"].replace("जमानत का लाभ प्रदान करने", "उचित आदेश पारित करने")
    c = _by_id(pf.review(d))["prayer"]
    assert c["severity"] == "amber" and "relief" in c["title"]


def test_a_missing_prayer_block_is_called_out_as_such():
    res = pf.review({"ok": True, "doc_type": "bail",
                     "html_hi": "<p>न्यायालय सत्र न्यायाधीश</p><p>आवेदक</p><p>अनावेदक</p>"})
    assert _by_id(res)["prayer"]["title"] == "No prayer block found"


def test_a_type_with_no_named_relief_only_asserts_the_prayer_exists():
    res = pf.review({"ok": True, "doc_type": "vakalatnama",
                     "html_hi": "<p>न्यायालय</p><p>आवेदक</p><p>अनावेदक</p>"
                                "<p>अतः निवेदन है।</p>"})
    assert _by_id(res)["prayer"] == {"id": "prayer", "severity": "ok",
                                     "title": "Prayer present", "detail": ""}


# --------------------------------------------------------------------------- cause title

def test_two_different_courts_in_one_document_is_amber():
    res = pf.review({"ok": True, "doc_type": "bail", "html_hi":
                     "<p>न्यायालय अपर सत्र न्यायाधीश, भोपाल</p>"
                     "<p>न्यायालय मुख्य न्यायिक मजिस्ट्रेट, विदिशा</p>"
                     "<p>आवेदक</p><p>अनावेदक</p>"})
    c = _by_id(res)["cause_title"]
    assert c["severity"] == "amber" and "one court" in c["title"]


def test_a_repeated_identical_court_line_is_not_a_disagreement():
    res = pf.review({"ok": True, "doc_type": "bail", "html_hi":
                     "<p>न्यायालय अपर सत्र न्यायाधीश, भोपाल</p>"
                     "<p>न्यायालय अपर सत्र न्यायाधीश, भोपाल</p>"
                     "<p>आवेदक</p><p>अनावेदक</p><p>अतः प्रार्थना है कि जमानत दी जावे।</p>"})
    assert _by_id(res)["cause_title"]["severity"] == "ok"


def test_no_court_named_at_all():
    res = pf.review({"ok": True, "doc_type": "bail", "html_hi": "<p>आवेदक</p><p>अनावेदक</p>"})
    assert _by_id(res)["cause_title"]["title"] == "No court is named"


def test_a_missing_respondent_side_is_named_precisely():
    res = pf.review({"ok": True, "doc_type": "bail",
                     "html_hi": "<p>न्यायालय सत्र न्यायाधीश भोपाल</p><p>आवेदक रमेश</p>"})
    assert _by_id(res)["cause_title"]["title"] == "The respondent side is not designated"


# --------------------------------------------------------------------------- code / FIR date

def test_the_changeover_date_is_the_statutory_one():
    assert pf.NEW_CODES_FROM == date(2024, 7, 1)


def test_pre_changeover_fir_with_new_code_numbering_is_amber():
    d = _draft()
    d["html_hi"] = d["html_hi"].replace("दिनांक 12.03.2025", "दिनांक 05.01.2024") \
                               .replace("(439 दं.प्र.सं.)", "")
    c = _by_id(pf.review(d, brief="FIR 05.01.2024"))["code_date"]
    assert c["severity"] == "amber" and "Old-code" in c["title"]
    assert "05.01.2024" in c["detail"]


def test_post_changeover_fir_with_only_old_code_numbering_is_amber():
    res = pf.review({"ok": True, "doc_type": "bail", "html_hi":
                     "<p>न्यायालय सत्र न्यायाधीश भोपाल</p><p>आवेदक</p><p>अनावेदक</p>"
                     "<p>धारा 439 दं.प्र.सं. के अंतर्गत</p>"
                     "<p>अतः प्रार्थना है कि जमानत दी जावे।</p>"},
                    brief="FIR दिनांक 09.09.2025")
    c = _by_id(res)["code_date"]
    assert c["severity"] == "amber" and "New-code" in c["title"]


def test_no_date_anywhere_is_amber_and_says_which_numbering_was_used():
    res = pf.review({"ok": True, "doc_type": "bail", "html_hi":
                     "<p>न्यायालय सत्र न्यायाधीश</p><p>आवेदक</p><p>अनावेदक</p>"
                     "<p>अतः प्रार्थना है कि जमानत दी जावे।</p>"})
    c = _by_id(res)["code_date"]
    assert c["severity"] == "amber" and "BNSS" in c["detail"]


def test_a_type_that_does_not_turn_on_the_changeover_is_not_flagged():
    res = pf.review({"ok": True, "doc_type": "recovery_suit", "html_hi":
                     "<p>न्यायालय व्यवहार न्यायाधीश</p><p>वादी</p><p>प्रतिवादी</p>"
                     "<p>अतः प्रार्थना है कि वसूली की डिक्री दी जावे।</p>"})
    assert _by_id(res)["code_date"]["severity"] == "ok"


def test_code_sensitive_list_tracks_the_drafting_pipeline():
    """preflight keeps its own copy so it has no import cost; if from_prompt's list
    moves and this one doesn't, the FIR-date check silently stops firing."""
    from headnote.drafter import from_prompt
    assert pf.CODE_SENSITIVE == from_prompt._CODE_SENSITIVE


@pytest.mark.parametrize("raw,expect", [
    ("12.03.2026", date(2026, 3, 12)),
    ("5/1/24", date(2024, 1, 5)),
    ("31-12-1999", date(1999, 12, 31)),
    ("32.13.2020", None),          # invalid → None, never a confident conclusion
    ("no date here", None),
])
def test_parse_dmy(raw, expect):
    assert pf.parse_dmy(raw) == expect


def test_earliest_date_ignores_ocr_noise_outside_a_plausible_window():
    assert pf.earliest_date("01.01.1899 and 12.03.2025") == date(2025, 3, 12)


# --------------------------------------------------------------------------- blanks

def test_a_dotted_leader_before_a_designation_is_not_a_blank():
    """"..... आवेदक" is how an Indian cause title is formatted. Counting it would
    put an amber line on every correctly drafted document."""
    assert _by_id(pf.review(_draft()))["blanks"]["severity"] == "ok"


def test_a_real_dotted_slot_is_counted():
    d = _draft()
    d["html_hi"] = d["html_hi"].replace("क्रमांक 214 / 2026", "क्रमांक ............... / 2026")
    c = _by_id(pf.review(d))["blanks"]
    assert c["severity"] == "amber" and c["title"].startswith("1 blank")


def test_underscore_slots_and_placeholder_spans_are_both_counted():
    res = pf.review({"ok": True, "doc_type": "bail", "html_hi":
                     '<p>न्यायालय ______</p><p>आवेदक</p><p>अनावेदक</p>'
                     '<p><span class="ph">____</span></p>'
                     '<p>अतः प्रार्थना है कि जमानत दी जावे।</p>'})
    assert _by_id(res)["blanks"]["title"].startswith("3 blank")


def test_blanks_wording_never_calls_the_advocates_own_template_an_error():
    d = _draft()
    d["html_hi"] = d["html_hi"].replace("214 / 2026", "___ / 2026")
    assert "invented" in _by_id(pf.review(d))["blanks"]["detail"]


# --------------------------------------------------------------------------- zero fabrication

def test_ungrounded_terms_are_named_not_silently_dropped():
    c = _by_id(pf.review(_draft(ungrounded=["सुरेश", "₹4,50,000"])))["ungrounded"]
    assert c["severity"] == "amber"
    assert "सुरेश" in c["title"] and "₹4,50,000" in c["title"]


def test_ungrounded_list_is_truncated_with_a_count():
    c = _by_id(pf.review(_draft(ungrounded=list("abcde"))))["ungrounded"]
    assert "+2 more" in c["title"]


def test_held_back_authority_is_surfaced_so_it_is_not_lost():
    c = _by_id(pf.review(_draft(cite_at_hearing=["Satender Kumar Antil v. CBI (2022)"])))
    assert c["cite_at_hearing"]["severity"] == "amber"
    assert "Antil" in c["cite_at_hearing"]["detail"]


def test_companions_are_listed():
    c = _by_id(pf.review(_draft(companions=["शपथ पत्र", "vakalatnama"])))["companions"]
    assert c["severity"] == "amber" and "vakalatnama" in c["detail"]


def test_pipeline_warnings_land_in_the_same_rail():
    res = pf.review(_draft(warnings=["Application type inferred with low confidence."]))
    assert any(c["id"].startswith("pipeline_") and c["severity"] == "amber"
               for c in res["checks"])


def test_an_empty_draft_is_reported_as_such_and_not_as_passing_checks():
    res = pf.review({"ok": True, "doc_type": "bail"})
    assert _by_id(res)["empty"]["severity"] == "amber"


# --------------------------------------------------------------------------- plain()

def test_plain_turns_block_tags_into_line_breaks():
    """Without this the court line and the case-number line fuse, and every
    line-oriented check sees one long sentence."""
    assert pf.plain("<p>न्यायालय</p><p>आवेदन</p>").split("\n") == ["न्यायालय", "आवेदन"]


def test_plain_unescapes_entities_and_strips_markers():
    assert pf.plain('<span class="ung">R&amp;D</span>') == "R&D"


# ===========================================================================
# the one door — instant skeleton, questions, two-source merge
# ===========================================================================

def test_skeleton_is_a_full_document_shape_with_no_model_call():
    s = onedoor.instant_skeleton("रमेश वर्मा की जमानत, धारा 420, थाना कोतवाली")
    roles = [r for r, _ in s["blocks"]]
    for want in ("court", "caseno", "applicant", "versus", "respondent",
                 "section_heading", "ground", "prayer", "dateline", "advocate"):
        assert want in roles, want
    assert s["doc_type"] == "bail"
    assert s["format"] == "standard"          # anonymous → no captured layout


def test_skeleton_blocks_use_only_roles_the_layout_engine_knows():
    """These blocks are what render_into_layout consumes; an unknown role would
    silently come out in a default format."""
    from headnote.drafter import layout_template as LT
    s = onedoor.instant_skeleton("जमानत आवेदन")
    assert {r for r, _ in s["blocks"]} <= set(LT.ROLES)


def test_skeleton_carries_the_page_geometry_the_browser_draws_to_scale():
    s = onedoor.instant_skeleton("bail", lang="en")
    for k in ("width", "height", "margin_left", "margin_top"):
        assert isinstance(s["page"][k], (int, float))
    assert s["roles"]["court"]["align"] == "CENTER"


def test_skeleton_never_guesses_a_court():
    s = onedoor.instant_skeleton("जमानत का आवेदन बनाओ")
    court = next(t for r, t in s["blocks"] if r == "court")
    assert set(court) == {"_"}, court


def test_skeleton_uses_the_answered_court_when_there_is_one():
    s = onedoor.instant_skeleton("जमानत", answers={"court": "Sessions Court, Bhopal"})
    assert next(t for r, t in s["blocks"] if r == "court") == "Sessions Court, Bhopal"


@pytest.mark.parametrize("lang,font,place,through", [
    ("hi", "Nirmala UI", "स्थान", "द्वारा अभिभाषक"),
    ("en", "Times New Roman", "Place", "Through Counsel"),
    ("mr", "Nirmala UI", "स्थळ", "द्वारा अधिवक्ता"),
    ("gu", "Nirmala UI", "સ્થળ", "મારફતે વકીલ"),
])
def test_skeleton_speaks_each_advocates_own_language(lang, font, place, through):
    s = onedoor.instant_skeleton("bail application", lang=lang)
    assert s["font"] == font
    dateline = [t for r, t in s["blocks"] if r == "dateline"][0]
    assert dateline.split(":")[0] == place
    assert next(t for r, t in s["blocks"] if r == "sig_by") == through


def test_a_language_with_no_reviewed_vocabulary_falls_back_to_english_not_hindi():
    """A Madras filing carrying a Hindi सत्यापन heading is a defective document."""
    s = onedoor.instant_skeleton("bail application", lang="ta")
    text = " ".join(t for _, t in s["blocks"])
    assert "Place" in text and "Through Counsel" in text
    assert "स्थान" not in text and "द्वारा अभिभाषक" not in text


def test_script_lang_honours_an_explicit_indic_code_the_engine_cannot_author_in():
    """resolve_lang collapses everything to hi|en; routing labels through it is
    what would hand a Marathi advocate Hindi wording."""
    assert onedoor.script_lang("जामीन अर्ज", "mr") == "mr"
    assert onedoor.detect_lang("जामीन अर्ज", "mr") in ("hi", "en")
    assert onedoor.script_lang("रमेश की जमानत", "auto") == "hi"
    assert onedoor.script_lang("Bail for Ramesh", "auto") == "en"


def test_the_zero_cost_classifier_recognises_bail_in_four_more_scripts():
    for brief in ("जामीन अर्ज", "જામીન અરજી", "ஜாமீன் மனு", "জামিন আবেদন"):
        assert onedoor.classify_fast(brief) == "bail", brief


# --------------------------------------------------------------------------- questions

def test_questions_are_capped_at_one_round_of_two_and_always_skippable():
    q = onedoor.questions_for("रमेश वर्मा की जमानत, धारा 420")
    assert len(q["questions"]) == 2
    assert [x["id"] for x in q["questions"]] == ["court", "bail_stage"]
    assert q["skippable"] is True


def test_nothing_is_asked_when_the_brief_already_answers_it():
    q = onedoor.questions_for("Bail for Ramesh in the Sessions Court, first bail application")
    assert q["questions"] == []


def test_the_court_question_disappears_once_answered():
    q = onedoor.questions_for("रमेश की जमानत", answers={"court": "Sessions Court"})
    assert [x["id"] for x in q["questions"]] == ["bail_stage"]


def test_first_vs_successive_is_only_asked_for_the_bail_family():
    q = onedoor.questions_for("वसूली का वाद बनाओ 5 लाख का")
    assert [x["id"] for x in q["questions"]] == ["court"]
    assert q["questions"][0]["options"][0]["value"] == "Civil Court"


def test_a_question_never_asks_for_something_that_can_stay_a_visible_blank():
    """His address, his enrolment number and the case number are all blanks he can
    see and fill. Only court and first-vs-successive change the document."""
    ids = {x["id"] for x in onedoor.questions_for("जमानत")["questions"]}
    assert ids <= {"court", "bail_stage"}


# --------------------------------------------------------------------------- two-source rule

def test_facts_sources_are_labelled_and_a_format_source_is_never_merged():
    merged = onedoor.merge_brief("रमेश की जमानत", facts_texts=["FIR text here"], lang="hi")
    assert "रमेश की जमानत" in merged
    assert "संलग्न दस्तावेज़ से तथ्य" in merged and "FIR text here" in merged


def test_multiple_facts_sources_are_numbered_so_the_engine_can_tell_them_apart():
    merged = onedoor.merge_brief("x", facts_texts=["a", "b"], lang="en")
    assert "attached document 1" in merged and "attached document 2" in merged


def test_answers_become_facts_the_engine_can_use():
    merged = onedoor.merge_brief("जमानत", answers={"court": "Sessions Court, Bhopal",
                                                   "bail_stage": "successive"}, lang="hi")
    assert "Sessions Court, Bhopal" in merged
    assert "निरस्त" in merged           # the successive-disclosure duty is stated


def test_an_unexpected_answer_key_is_ignored_not_smuggled_into_the_draft():
    merged = onedoor.merge_brief("जमानत", answers={"secret": "invent this fact"}, lang="hi")
    assert "invent this fact" not in merged


def test_matter_context_is_a_silent_noop_without_both_ids():
    assert onedoor.matter_context(None, "u1") == ""
    assert onedoor.matter_context("m1", None) == ""


def test_short_title_trims_and_never_returns_empty():
    assert onedoor.short_title("  a\n b  ") == "a b"
    assert onedoor.short_title("") == "Draft"
    assert len(onedoor.short_title("x" * 200)) == 64
