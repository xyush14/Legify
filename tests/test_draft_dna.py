"""Draft DNA — regression + behaviour tests.

The load-bearing guarantee (docs/DRAFT_DNA_DESIGN.md §7): with no DNA the
authoring prompt and rendered HTML are byte-for-byte identical to pre-DNA. The
rest asserts the two mechanisms actually fire when a StyleProfile is present:
  • Mechanism 1 — the four format slots + style overlay reach the prompt.
  • Mechanism 2 — apply_format rewrites the rendered boilerplate to the
    advocate's own tokens, and is the identity function with no DNA.
"""

import pytest

from headnote.drafter import author
from headnote.drafter import style_profile as SP


# --------------------------------------------------------------------------- #
# §7 golden-master — the no-DNA prompt must be unchanged by the refactor
# --------------------------------------------------------------------------- #
_TYPES = ["bail", "discharge", "recovery_suit", "other_criminal", "maintenance"]
_LANGS = ["hi", "en"]


@pytest.mark.parametrize("dt", _TYPES)
@pytest.mark.parametrize("lang", _LANGS)
def test_no_dna_prompt_is_byte_identical(dt, lang):
    """style=None must fully substitute the slots to today's exact literals, leave
    no template token behind, and equal the no-arg call. inject_skill=False keeps
    the comparison to the house prompt (the skill prefix is fetched separately)."""
    s = author._author_system(dt, lang, inject_skill=False, style=None)

    # every slot token substituted
    for tok in ("{para_prefix}", "{closer}", "{prayer_open}", "{prayer_close}"):
        assert tok not in s, f"{tok} left unsubstituted for {dt}/{lang}"

    # defaults reproduce the original literals verbatim
    assert SP.FORMAT_DEFAULTS["para_prefix"] in s
    assert SP.FORMAT_DEFAULTS["closer"] in s
    assert f'open with "{SP.FORMAT_DEFAULTS["prayer_open"]} …"' in s
    assert f'end with "{SP.FORMAT_DEFAULTS["prayer_close"]}"' in s

    # no-arg == style=None, and no personalization leaked into the no-DNA path
    assert author._author_system(dt, lang, inject_skill=False) == s
    assert "THIS ADVOCATE'S HOUSE STYLE" not in s


def test_format_slots_default_equals_literals():
    assert SP.format_slots(None) == SP.FORMAT_DEFAULTS
    assert SP.format_slots({}) == SP.FORMAT_DEFAULTS


def test_dna_prompt_engages_slots_and_overlay():
    dna = {"format": {"para_prefix": "यह भी कि", "prayer_open": "सविनय निवेदन है कि"},
           "style_prose": "Parity-first, terse."}
    s = author._author_system("bail", "hi", inject_skill=False, style=dna)
    assert "यह भी कि" in s and "{para_prefix}" not in s
    assert "सविनय निवेदन है कि" in s
    assert "THIS ADVOCATE'S HOUSE STYLE" in s


# --------------------------------------------------------------------------- #
# Mechanism 2 — apply_format identity + real-render rewrites
# --------------------------------------------------------------------------- #
def _rendered_bail_html():
    payload = {
        "_doc_type": "bail", "court_level": "sessions",
        "court_name": "न्यायालय माननीय सत्र न्यायाधीश महोदय, ग्वालियर (मध्यप्रदेश)",
        "applicant_label": "आवेदक", "applicant_desc": ["आयुष शिवहरे"],
        "respondent_label": "अनावेदक", "respondent_desc": ["म.प्र. शासन"],
        "title_line": "जमानत आवेदन",
        "paras": [
            {"kind": "fact", "text": "यह कि आवेदक निर्दोष है।"},
            {"kind": "ground", "text": "यह कि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।"},
        ],
        "prayer": "अतः श्रीमान न्यायालय से प्रार्थना है कि आवेदक को जमानत पर रिहा करने की कृपा करें।",
        "needs_verification": True, "signatory_role": "आवेदक",
    }
    return author.render_authored(payload, "hi", source="आयुष शिवहरे निर्दोष")["html"]


def test_apply_format_is_identity_without_dna():
    html = _rendered_bail_html()
    assert SP.apply_format(html, None) == html
    assert SP.apply_format(html, {}) == html
    # an all-default profile is a no-op too
    assert SP.apply_format(html, {"format": {"para_prefix": "यह कि"}}) == html


def test_apply_format_rewrites_real_render():
    html = _rendered_bail_html()
    dna = {"format": {
        "para_prefix": "यह भी कि",
        "prayer_open": "सविनय निवेदन है कि",
        "prayer_close": "… की महती कृपा करें।",
        "closer": "यह कि, शेष तर्क बहस के समय प्रस्तुत किये जावेंगे।",
        "verification": "मैं सत्यापित करता हूँ कि उपरोक्त कथन सत्य हैं।",
        "advocate_block": ["अधिवक्ता विष्णु शिवहरे"],
    }}
    out = SP.apply_format(html, dna, "hi")
    assert "<li>यह भी कि आवेदक निर्दोष" in out                    # prefix on body
    assert "शेष तर्क बहस के समय प्रस्तुत" in out                  # closer swapped
    assert "अन्य तर्क वक्त बहस मौखिक" not in out
    assert "सविनय निवेदन है कि" in out                            # prayer opener
    assert "अतः श्रीमान न्यायालय से प्रार्थना" not in out
    assert "की महती कृपा करें।" in out                            # prayer closer
    assert out.count("की महती कृपा करें।") == 1                   # scoped to prayer
    assert "मैं सत्यापित करता हूँ" in out                         # verification
    assert "समस्त बातें मेरी" not in out                          # default verification gone
    assert "(अधिवक्ता विष्णु शिवहरे) — एडवोकेट" in out            # signature filled


def test_apply_format_never_raises():
    # malformed / partial inputs degrade to the original html, never an exception
    assert SP.apply_format("", {"format": {"para_prefix": "X"}}) == ""
    assert SP.apply_format("<li>यह कि foo", {"format": {"para_prefix": "यह भी कि"}})


# --------------------------------------------------------------------------- #
# helpers — meaningfulness gate + sanitise
# --------------------------------------------------------------------------- #
def test_is_meaningful_gate():
    assert SP._is_meaningful({"format": {"para_prefix": "यह कि"}}) is False   # all default
    assert SP._is_meaningful({"format": {"para_prefix": "यह भी कि"}}) is True
    assert SP._is_meaningful({"style_prose": "x"}) is True
    assert SP._is_meaningful({"format": {}}) is False


def test_sanitize_profile_clamps():
    dirty = {"format": {"para_prefix": "That",
                        "advocate_block": ["A", "B", "C", "D", "E", "F"]},
             "exemplars": [{"text": "यह कि ____"}] * 10}
    clean = SP.sanitize_profile(dirty)
    assert len(clean["format"]["advocate_block"]) == 4
    assert len(clean["exemplars"]) <= 3
