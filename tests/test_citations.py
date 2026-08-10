"""Tests for the citation gate.

The cases below are not invented: they are the exact failures measured against
live engines on a real UP gang-chart आख्या this session. If the gate stops
passing these, a cheap translation model is no longer safe to ship behind it.
"""
from __future__ import annotations

from headnote.drafter.i18n import citations as C

HI = ("दिनांक 11.10.25 को अभियुक्त गण कुन्ना उर्फ पुन्नन पुत्र खालिद के द्वारा पुलिस पार्टी पर "
      "जान से मारने की नीयत से फायर करना। थाना को0नगर मु0नगर पर मु0अ0सं0 359/25 धारा "
      "109(1) बीएनएस व 3/4/25/28 आर्मस एक्ट पंजीकृत किया गया। आरोप पत्र – 394/25 "
      "दि0 24.12.2025 को मा० न्यायालय में प्रेषित किया गया।")


# --- extraction ---------------------------------------------------------------
def test_extracts_every_citation_class():
    got = set(C.extract(HI))
    for want in {"11.10.25", "359/25", "109(1)", "3/4/25/28", "394/25", "24.12.2025"}:
        assert want in got, f"{want} not extracted from {got}"


def test_year_inside_a_date_is_not_a_separate_citation():
    """24.12.2025 must not also yield '12/2025' or a bare '2025'."""
    got = C.extract("आरोप पत्र दि0 24.12.2025 को प्रेषित।")
    assert got == ["24.12.2025"], got


def test_devanagari_digits_normalise_to_latin():
    assert "109(1)" in C.extract("धारा १०९(१) बीएनएस")


def test_devanagari_subclause_is_caught():
    assert "2(ख)" in C.extract("अधिनियम 1986 की धारा 2(ख) के अन्तर्गत")


def test_money_is_a_citation():
    assert any("120000" in c or "1,20,000" in c for c in C.extract("क्षतिपूर्ति ₹ 1,20,000 अदा"))


# --- the real measured failures ----------------------------------------------
def test_mayura_dropping_the_chargesheet_number_is_caught():
    """Measured: Mayura translated this paragraph and lost 394/25 entirely."""
    bad = ("On 11.10.25 the accused fired at the police party. A case was registered at "
           "PS Kotwali Nagar under 359/25, 109(1) BNS and 3/4/25/28 Arms Act. The "
           "charge sheet was submitted to the Court on 24.12.2025.")
    rep = C.verify(HI, bad, target_lang="en")
    assert not rep.ok
    assert "394/25" in rep.missing
    assert "394/25" in rep.reason()


def test_sarvam_105b_answering_in_the_wrong_language_is_caught():
    """Measured: asked for English twice, returned fluent Hindi with 6/6 citations.

    Every citation survives, so a citation-only check passes it. The script
    check is what stops it reaching a user.
    """
    hindi_out = ("दिनांक 11.10.25 को अभियुक्त द्वारा फायर किया गया। मु0अ0सं0 359/25 धारा "
                 "109(1) बीएनएस व 3/4/25/28 आर्म्स एक्ट। आरोप पत्र 394/25 दिनांक 24.12.2025।")
    assert C.verify(HI, hindi_out).ok, "citations alone should pass — that is the trap"
    rep = C.verify(HI, hindi_out, target_lang="en")
    assert not rep.ok and "Devanagari" in rep.wrong_script


def test_statute_substitution_is_caught():
    """Cow Slaughter Act silently becoming the Gangsters Act is not a wording choice."""
    src = "मु0अ0सं0 355/25 धारा 3/5/8 गौवध अधिनियम व 318(4) बीएनएस"
    bad = "Case Crime No. 355/25 u/s 3/5/8 Gangsters Act and 318(4) BNS"
    rep = C.verify(src, bad, target_lang="en")
    assert "cow_slaughter" in rep.statutes_lost


# --- good translations must pass ---------------------------------------------
def test_a_faithful_english_translation_passes():
    good = ("On 11.10.25 the accused Kunna @ Punnan s/o Khalid fired at the police party "
            "with intent to kill. Case Crime No. 359/25 under Section 109(1) BNS read "
            "with Sections 3/4/25/28 Arms Act was registered at PS Kotwali Nagar. "
            "Charge-sheet No. 394/25 dated 24.12.2025 was filed before the Court.")
    rep = C.verify(HI, good, target_lang="en")
    assert rep.ok, rep.reason()


def test_reflowed_numbering_still_passes():
    """मु0अ0सं0 359/25 -> 'Case Crime No. 359/25' changes words, not the number."""
    assert C.verify("मु0अ0सं0 359/25", "Case Crime No. 359/25", target_lang="en").ok


def test_hindi_target_passes_and_latin_output_is_flagged():
    src = "Charge-sheet No. 394/25 dated 24.12.2025 was filed."
    assert C.verify(src, "आरोप पत्र संख्या 394/25 दिनांक 24.12.2025 प्रेषित।", target_lang="hi").ok
    rep = C.verify(src, "Charge-sheet No. 394/25 dated 24.12.2025 filed.", target_lang="hi")
    assert "Latin" in rep.wrong_script


def test_guard_wrapper_returns_ok_and_reason():
    ok, why = C.guard("धारा 109(1)", "under Section 109(1)", target_lang="en")
    assert ok and why == ""
    ok, why = C.guard("धारा 109(1) व 394/25", "under Section 109(1)", target_lang="en")
    assert not ok and "394/25" in why


def test_empty_translation_reports_everything_missing():
    rep = C.verify(HI, "", target_lang="en")
    assert not rep.ok and len(rep.missing) >= 6
