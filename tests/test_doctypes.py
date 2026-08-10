"""Document ontology — the tripwire for "every draft comes out as a court application".

The bug these tests pin: asking for an application to a police station returned a court
application, because the engine had exactly one document shape. Two halves matter equally
and both are tested here:

  A. NON-COURT documents must come out in their own shape — no cause-title, no विरुद्ध,
     no case number, no court प्रार्थना, no सत्यापन on a letter to an officer.
  B. COURT filings must be COMPLETELY unaffected. A police station is named as a FACT in
     most criminal filings ("FIR 123/2025, थाना कोतवाली"), so the routing must not
     mistake a mention for an addressee. A bail application rendered as a letter to the
     SHO would be a far worse bug than the one being fixed.
"""
from __future__ import annotations

import html as _html
import re

import pytest

from headnote.drafter import author_parts as AP
from headnote.drafter import doctypes as DT
from headnote.drafter import from_prompt as FP
from headnote.drafter import layout_template as LT


def _text(html: str) -> str:
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


# Markers that only ever belong in a document filed before a judge. Their presence in a
# letter to an officer is the bug.
COURT_ARTEFACTS = (
    "विरुद्ध", "बनाम", "Versus",
    "अनावेदक", "प्रकरण क्रमांक", "एम.सी.आर.सी.",
    "श्रीमान न्यायालय से प्रार्थना",
    "सत्यापन",
    "द्वारा अभिभाषक",
)


# ===========================================================================
# A) Resolution
# ===========================================================================

@pytest.mark.parametrize("forum,instrument,expected", [
    ("court", "application", DT.COURT_FILING),
    ("court", "petition", DT.COURT_FILING),
    ("tribunal", "application", DT.COURT_FILING),
    ("police", "application", DT.AUTHORITY_APPLICATION),
    ("police", "complaint", DT.AUTHORITY_APPLICATION),
    ("executive", "representation", DT.AUTHORITY_APPLICATION),
    ("registrar", "application", DT.AUTHORITY_APPLICATION),
    ("institution", "representation", DT.AUTHORITY_APPLICATION),
    ("private_party", "notice", DT.NOTICE),
    ("private_party", "application", DT.NOTICE),   # no forum to move → still a notice
    ("none", "deed", DT.DEED),
    ("court", "deed", DT.DEED),                    # instrument-dominant
    ("none", "affidavit", DT.AFFIDAVIT),
    ("court", "affidavit", DT.AFFIDAVIT),          # filed in a case, still a deponent block
])
def test_family_resolution(forum, instrument, expected):
    assert DT.resolve_family(forum, instrument) == expected


@pytest.mark.parametrize("forum,instrument", [
    ("", ""), ("garbage", "garbage"), ("court", ""), ("", "application"),
    (None, None),
])
def test_unknown_axes_fall_back_to_the_court_filing(forum, instrument):
    """A classifier that says nothing about the forum must change nothing. This is
    what makes the whole feature additive rather than a rewrite of live behaviour."""
    assert DT.resolve_family(forum, instrument) == DT.COURT_FILING
    assert DT.is_court_family(DT.resolve_family(forum, instrument))


# ===========================================================================
# B) THE REGRESSION GUARD — court filings must not be rerouted
# ===========================================================================

COURT_PROMPTS = [
    "bail application FIR 123/2025 thana kotwali gwalior, sole breadwinner",
    "जमानत आवेदन, अपराध क्रमांक 45/2025, थाना कोतवाली ग्वालियर",
    "anticipatory bail application, SHO thana kotwali ne notice diya",
    "discharge application, police station kotwali, chargesheet filed",
    "supurdgi application before magistrate for vehicle seized by thana kotwali",
    "recovery suit against the defendant, bank ko paisa dena tha",
    "written statement, plaintiff ne collector ko application diya tha",
    "criminal revision against the order of the magistrate",
    "maintenance application under 125 crpc against husband",
]


@pytest.mark.parametrize("prompt", COURT_PROMPTS)
def test_court_prompts_keep_the_court_shape(prompt):
    """A police station or an officer named as a FACT must never make the document a
    letter. This is the guard that keeps the live, paying court path safe."""
    forum, instrument = FP._heuristic_shape(prompt)
    assert forum == "court", f"{prompt!r} was rerouted off the court path as {forum!r}"
    assert DT.is_court_family(DT.resolve_family(forum, instrument))


@pytest.mark.parametrize("doc_type", [
    "bail", "anticipatory_bail", "discharge", "revision", "appeal", "quashing",
    "maintenance", "supurdgi", "complaint_156", "recovery_suit", "written_statement",
    "vakalatnama", "parivad", "habeas_corpus",
])
def test_blank_forum_on_a_court_only_type_stays_court(doc_type):
    """When the classifier returns a court-only doc_type but omits the forum, we must
    NOT fall through to keyword guessing on the raw text — the type already settled it."""
    forum, _ = FP._resolve_shape_axes({}, "थाना प्रभारी को आवेदन देना है", doc_type)
    assert forum == "court"


def test_an_explicit_police_forum_is_believed_even_for_a_court_type():
    """The mirror of the rule above: if the model explicitly says the advocate is
    writing to the police, we draft that letter — and warn — rather than silently
    converting it into a court application. Drafting what was NOT asked for is the
    failure mode that loses the advocate's trust."""
    forum, instrument = FP._resolve_shape_axes(
        {"forum_type": "police", "instrument": "application"}, "…", "supurdgi")
    assert (forum, instrument) == ("police", "application")
    assert DT.resolve_family(forum, instrument) == DT.AUTHORITY_APPLICATION

    note = FP._forum_mismatch_warning("supurdgi", DT.AUTHORITY_APPLICATION, "en")
    assert "Magistrate" in note, "the advocate must be told the court can also be moved"
    assert FP._forum_mismatch_warning("supurdgi", DT.COURT_FILING, "en") == ""


@pytest.mark.parametrize("matter,expect", [
    ("थाना प्रभारी को जब्त मोटरसाइकिल की सुपुर्दगी हेतु आवेदन", "supurdgi"),
    ("application to the SHO for release of vehicle seized in crime no. 145/2026", "supurdgi"),
    ("थाना पुलिस अधीक्षक को — पुलिस रिपोर्ट दर्ज नहीं कर रही", "complaint_156"),
    ("complaint to the SP, police refusing to register the FIR", "complaint_156"),
    ("अग्रिम जमानत की आशंका, थाना प्रभारी को पत्र", "anticipatory_bail"),
    # the way an advocate ACTUALLY writes it — describing the seizure, never using the
    # word सुपुर्दगी. This exact phrasing is what slipped through in production.
    ("थाना प्रभारी को आवेदन — मोटरसाइकिल MP07AB1234 अपराध क्रमांक 145/2026 में जब्त की गई है",
     "supurdgi"),
    ("application to the SHO — my client's vehicle was seized in crime no. 145/2026",
     "supurdgi"),
    ("थाना प्रभारी को चरित्र प्रमाण-पत्र हेतु आवेदन", ""),
    ("to the collector for mutation of land records", ""),
    ("बैंक को ऋण निपटान हेतु पत्र", ""),
])
def test_the_note_fires_off_the_advocates_own_words(matter, expect):
    """Found by running the real thing against production: for a supurdgi letter the
    classifier correctly returns doc_type=`authority_application` (it IS a letter to an
    office), so keying the note on doc_type alone meant it never fired on the exact case
    it was written for. It must read the relief from the brief too."""
    assert FP._relief_from_text(matter) == expect
    note = FP._forum_mismatch_warning("authority_application", DT.AUTHORITY_APPLICATION,
                                      "hi", matter)
    assert bool(note) is bool(expect), f"note={note!r} for {matter!r}"


def test_the_note_never_fires_on_a_court_filing():
    """A bail application filed in court must not be told that bail needs a court."""
    for matter in ("जमानत आवेदन, अपराध क्रमांक 145/2026",
                   "supurdgi application before the magistrate"):
        assert FP._forum_mismatch_warning("bail", DT.COURT_FILING, "hi", matter) == ""


NON_COURT_PROMPTS = [
    ("draft an application to the police station for release of my vehicle", "police"),
    ("थाना प्रभारी को गाड़ी छुड़ाने का आवेदन लिखो", "police"),
    ("application to the SHO for return of seized documents", "police"),
    ("कलेक्टर को अतिक्रमण हटाने का आवेदन", "executive"),
    ("to the collector for mutation of land records", "executive"),
    ("to the bank for loan settlement letter", "institution"),
    ("किरायानामा बनाना है मकान का", "none"),
    ("draft a rent agreement for my shop", "none"),
    ("वसूली का लीगल नोटिस भेजना है", "private_party"),
]


@pytest.mark.parametrize("prompt,forum", NON_COURT_PROMPTS)
def test_non_court_prompts_leave_the_court_shape(prompt, forum):
    got_forum, got_instrument = FP._heuristic_shape(prompt)
    assert got_forum == forum, f"{prompt!r} → {got_forum!r}"
    assert not DT.is_court_family(DT.resolve_family(got_forum, got_instrument))


# ===========================================================================
# C) THE ACTUAL BUG — what the police-station application renders as
# ===========================================================================

POLICE_PAYLOAD = {
    "addressee": ["थाना प्रभारी महोदय,", "पुलिस थाना कोतवाली,", "जिला ग्वालियर (म.प्र.)"],
    "subject": "जब्तशुदा मोटरसाइकिल क्रमांक MP07 AB 1234 की सुपुर्दगी हेतु आवेदन",
    "reference": "अपराध क्रमांक 145/2026",
    "salutation": "महोदय,",
    "body": ["निवेदन है कि आवेदक उपरोक्त वाहन का पंजीकृत स्वामी है।"],
    "request": "अतः आपसे निवेदन है कि वाहन सुपुर्दगी पर प्रदान करने की कृपा करें।",
    "applicant_name": "रामकिशोर",
    "applicant_desc": ["निवासी 12 नई सड़क, ग्वालियर"],
    "signed_by": "applicant",
    "enclosures": ["आर.सी. की छायाप्रति"],
}


def test_authority_application_carries_no_court_artefacts():
    html = AP.render_parts(POLICE_PAYLOAD, DT.AUTHORITY_APPLICATION, "hi")["html"]
    present = [a for a in COURT_ARTEFACTS if a in html]
    assert not present, f"court artefacts leaked into a letter to the police: {present}"


def test_authority_application_carries_the_parts_it_must():
    txt = _text(AP.render_parts(POLICE_PAYLOAD, DT.AUTHORITY_APPLICATION, "hi")["html"])
    for required in ("सेवा में", "विषय", "संदर्भ", "महोदय", "अतः आपसे निवेदन है कि",
                     "संलग्न", "आवेदक"):
        assert required in txt, f"missing required part: {required}"


@pytest.mark.parametrize("family,payload", [
    (DT.NOTICE, {"sender_block": ["अधिवक्ता क.ख.ग"], "notice_date": "08.08.2026",
                 "addressee": ["श्री मोहन शर्मा"], "subject": "वसूली",
                 "through_clause": "मेरे मुवक्किल के निर्देशानुसार",
                 "paras": ["आपने ₹2,00,000 उधार लिए।"], "demand": "15 दिवस में भुगतान करें",
                 "consequence": "अन्यथा विधिक कार्यवाही", "advocate_name": "क.ख.ग"}),
    (DT.DEED, {"title_line": "किरायानामा", "deed_date": "08.08.2026",
               "first_party": ["श्री अशोक"], "second_party": ["श्री विनोद"],
               "recitals": ["जबकि प्रथम पक्ष स्वामी है।"], "operative": "अतः यह विलेख साक्षी है कि —",
               "clauses": ["किराया ₹8,000 प्रतिमाह।"], "witnesses": ["1. ____", "2. ____"]}),
])
def test_other_non_court_families_carry_no_cause_title(family, payload):
    html = AP.render_parts(payload, family, "hi")["html"]
    for artefact in ("विरुद्ध", "बनाम", "अनावेदक", "श्रीमान न्यायालय से प्रार्थना"):
        assert artefact not in html, f"{family}: {artefact} leaked in"


def test_a_deed_always_carries_witnesses():
    """A deed executed without witnesses is defective, so the renderer emits the block
    even when the model forgot it."""
    html = AP.render_parts({"title_line": "इकरारनामा", "clauses": ["____"]}, DT.DEED, "hi")["html"]
    assert DT.label("witnesses", "hi") in html


def test_an_affidavit_leads_with_the_deponent_not_a_cause_title():
    html = AP.render_parts(
        {"title_line": "शपथ पत्र", "deponent_block": "मैं, सीता देवी, शपथपूर्वक कथन करती हूँ कि —",
         "paras": ["मैं उपरोक्त पते की निवासी हूँ।"], "verification": "कथन सत्य हैं।"},
        DT.AFFIDAVIT, "hi")["html"]
    assert "शपथपूर्वक कथन" in html
    for artefact in ("विरुद्ध", "बनाम", "अनावेदक"):
        assert artefact not in html


def test_render_parts_refuses_the_court_family():
    """A misrouted court filing must fail loudly here rather than be rendered as a
    letter — `author.render_authored` owns that family."""
    with pytest.raises(ValueError):
        AP.render_parts({}, DT.COURT_FILING, "hi")


# ===========================================================================
# D) Zero fabrication — the promise does not weaken off the court path
# ===========================================================================

def test_facts_not_in_the_brief_are_flagged_on_the_parts_path():
    brief = "थाना कोतवाली को आवेदन, मोटरसाइकिल MP07 AB 1234 जब्त"
    payload = dict(POLICE_PAYLOAD)
    payload["body"] = ["आवेदक सुरेश कुमार पुत्र रमेश ने दिनांक 15.03.2024 को ₹85,000 चुकाये।"]
    out = AP.render_parts(payload, DT.AUTHORITY_APPLICATION, "hi", source=brief)
    assert out["ungrounded"], "an invented fact was not flagged"
    assert "<mark" in out["html"], "an invented fact was not marked in the document"
    assert out["warnings"]


def test_grounded_facts_are_not_flagged():
    brief = ("थाना कोतवाली ग्वालियर को आवेदन, आवेदक रामकिशोर, "
             "मोटरसाइकिल MP07 AB 1234, अपराध क्रमांक 145/2026")
    out = AP.render_parts(POLICE_PAYLOAD, DT.AUTHORITY_APPLICATION, "hi", source=brief)
    assert not out["ungrounded"], f"grounded facts were wrongly flagged: {out['ungrounded']}"


# ===========================================================================
# E) Universality — labels must never fall back to Hindi
# ===========================================================================

@pytest.mark.parametrize("lang", ["en", "ta", "te", "kn", "ml", "or", "pa", "as"])
@pytest.mark.parametrize("key", ["to", "subject", "sir", "request_open", "applicant",
                                 "affidavit", "witnesses", "verification"])
def test_unpinned_languages_fall_back_to_english_never_hindi(lang, key):
    """A Chennai or Kolkata document carrying a Devanagari-Hindi heading is defective in
    a way an English heading is not. See memory → feedback_universal_not_one_user."""
    got = DT.label(key, lang)
    assert got, f"{key} has no label at all for {lang}"
    assert got == DT.label(key, "en"), f"{key}/{lang} resolved to {got!r}, not English"
    assert not re.search(r"[ऀ-ॿ]", got), f"{key}/{lang} fell back to Devanagari: {got!r}"


@pytest.mark.parametrize("lang", ["hi", "mr", "gu"])
def test_pinned_languages_use_their_own_words(lang):
    assert DT.label("applicant", lang) != DT.label("applicant", "en")


@pytest.mark.parametrize("lang", ["mr", "gu", "ta"])
def test_injected_labels_follow_the_advocates_language(lang):
    """Scoped to the wording the RENDERER injects — the body prose comes from the model
    and is the model's job. What must never happen is Headnote itself stamping Hindi
    labels onto a Marathi, Gujarati or Tamil document."""
    payload = {k: v for k, v in POLICE_PAYLOAD.items() if k not in ("body", "request")}
    payload["body"] = ["..."]
    payload["request"] = "..."
    out = AP.render_parts(payload, DT.AUTHORITY_APPLICATION, lang)["html"]
    for key in ("to", "place", "date", "applicant", "enclosures", "yours"):
        assert DT.label(key, lang) in out, f"{key} not rendered in {lang}"
        if DT.label(key, lang) != DT.label(key, "hi"):
            assert DT.label(key, "hi") not in out, (
                f"the Hindi {key} label leaked into a {lang} document")


# ===========================================================================
# F) The floor, and the layout contract
# ===========================================================================

@pytest.mark.parametrize("family", [DT.AUTHORITY_APPLICATION, DT.NOTICE,
                                    DT.AFFIDAVIT, DT.DEED])
def test_the_floor_is_the_right_shape_not_a_court_skeleton(family):
    """When every engine is down the advocate still gets the CORRECT blank document.
    Falling back to the court skeleton here would reproduce the original bug at
    exactly the moment we can least afford it."""
    out = AP.floor_document(family, "hi", "थाना प्रभारी को गाड़ी छुड़ाने का आवेदन")
    assert out["ok"] and out["mode"] == "skeleton"
    assert out["html"]
    for artefact in ("विरुद्ध", "बनाम", "अनावेदक", "श्रीमान न्यायालय से प्रार्थना"):
        assert artefact not in out["html"], f"{family} floor emitted {artefact}"
    # the advocate's own words are never thrown away
    assert "गाड़ी" in out["html"]


@pytest.mark.parametrize("family", [DT.AUTHORITY_APPLICATION, DT.NOTICE,
                                    DT.AFFIDAVIT, DT.DEED])
def test_every_dna_role_the_parts_engine_emits_has_a_base_format(family):
    """`render_into_layout` looks each role up in the standard template for its base
    format. A role with no entry silently falls to a flat justified default, which is
    how an address block would end up formatted as body text in the .docx."""
    payload = AP.floor_payload(family, "hi")
    blocks = AP.blocks_from_parts(payload, family, "hi")
    assert blocks, f"{family} produced no DNA blocks"
    roles = LT.standard_template("Nirmala UI")["roles"]
    missing = sorted({r for r, _ in blocks} - set(roles))
    assert not missing, f"{family} emits roles with no base format: {missing}"


def test_capture_vocabulary_is_untouched():
    """The new roles are RENDER formats only. Adding them to `ROLES` would change what
    the labeller tags an advocate's own filed .docx with — i.e. it would alter Draft
    DNA capture, which is a separate, already-validated contract (132 real drafts)."""
    for role in ("addressee", "subject", "reference", "salutation", "enclosures", "witness"):
        assert role in LT.standard_template("Nirmala UI")["roles"]
        assert role not in LT.ROLES


def test_every_family_declares_a_parts_grammar():
    for family in DT.FAMILIES:
        parts = DT.parts_for(family)
        assert parts, f"{family} has no parts"
        assert all(req in ("req", "opt", "cond") for _, req in parts)
    # and every family except the court one describes itself to the model
    for family in DT.FAMILIES:
        if family != DT.COURT_FILING:
            assert DT.family_brief(family), f"{family} has no brief for the drafting model"
