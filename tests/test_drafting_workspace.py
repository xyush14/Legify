"""The /draft workspace: recognition, extraction, the page, the junior's note,
the AI top-up's grounding, saving, and the repaired model chain.

The briefs below are written the way district advocates actually write them —
Hindi, English and Hinglish, lowercase, "s/o", "r/o", "@", Hindi full stops —
and every name in them is fictional.
"""
from __future__ import annotations

import re

import pytest

from headnote.drafter import amounts as AM
from headnote.drafter import geo_in as GEO
from headnote.drafter import intake as IN
from headnote.drafter import template_adapter as TA
from headnote.drafter import workspace as WS

# --------------------------------------------------------------------------- briefs
BRIEFS = [
    ("bail_sessions", "जमानत आवेदन। आवेदक रामकुमार पुत्र श्यामलाल, उम्र 32 वर्ष, निवासी ग्राम बरई, थाना कोतवाली, जिला ग्वालियर। अपराध क्रमांक 145/2025, धारा 420, 406 भारतीय न्याय संहिता। आवेदक दिनांक 10/03/2025 से न्यायिक अभिरक्षा में है। आवेदक का कोई आपराधिक रिकॉर्ड नहीं है। न्यायालय सत्र न्यायाधीश ग्वालियर।"),
    ("bail_sessions", "bail application for Ramkumar s/o Shyamlal age 32 r/o village Barai thana Kotwali district Gwalior, FIR 145/2025 u/s 420, 406 BNS, in jail since 10/03/2025, sessions court Gwalior, first bail"),
    ("bail_sessions", "mere client sunil yadav s/o ramesh yadav ki jamanat lagani hai, thana padav gwalior, fir no 88/2024 dhara 379 ipc, magistrate se jamanat khariz ho gayi hai 05/08/2024 ko, 12/07/2024 se jail me hai"),
    ("anticipatory_bail", "Anticipatory bail for Mohan Singh s/o Late Hari Singh, 45, farmer, r/o Village Kheda, PS Civil Lines, District Morena. He apprehends arrest in a false case u/s 323, 294, 506 IPC."),
    ("bail_hc", "second bail application in High Court for accused Raju @ Rajesh s/o Kallu, Crime No. 210/2023 u/s 302, 34 IPC PS Kampoo Gwalior, bail rejected by Sessions Court Gwalior on 05/01/2024"),
    ("cheque_138", "138 complaint - my client Agrawal Traders through proprietor Suresh Agrawal s/o Mahesh Agrawal r/o Lashkar Gwalior against Vinod Sharma s/o Kailash Sharma r/o Morar Gwalior. cheque no 456789 dated 01/06/2025 of Rs 2,50,000 drawn on SBI Morar branch dishonoured on 10/06/2025 for insufficient funds. legal notice sent on 20/06/2025"),
    ("legal_notice", "draft a legal notice for my client Ramesh Kumar to Sunil Traders for cheque bounce of Rs. 50000"),
    ("maintenance", "भरण पोषण का आवेदन पत्नी सीता देवी पुत्री रामलाल उम्र 28 वर्ष निवासी इंदौर, पति राजेश कुमार पुत्र मोहनलाल, पति की आय 40000 रुपये प्रतिमाह, विवाह दिनांक 12/05/2018, दहेज के लिए प्रताड़ित किया, 15000 रुपये प्रतिमाह भरण पोषण चाहिए, कुटुम्ब न्यायालय इंदौर"),
    ("supurdgi", "थाना सिरोल में जब्त मोटरसाइकिल MP07 AB 1234 की सुपुर्दगी हेतु आवेदन, आवेदक दिनेश पुत्र बाबूलाल, अपराध क्रमांक 55/2025 धारा 281 भा.न्या.सं."),
    ("discharge_sessions", "discharge application in sessions case for accused Pappu s/o Ramcharan, crime no 12/2022 u/s 307 IPC PS Bijoli district Gwalior"),
    ("recovery_suit", "recovery suit — plaintiff Anil Jain s/o Sohanlal Jain gave loan of Rs 3 lakh to defendant Pramod Gupta s/o Hari Gupta on 15/02/2023, not returned despite demand, civil court Bhopal"),
    ("divorce_13", "divorce petition by husband Amit Verma against wife Neha Verma on ground of cruelty, marriage on 10/12/2019 at Jabalpur"),
    ("quashing", "petition u/s 482 CrPC to quash FIR 77/2024 u/s 498A, 406 IPC PS Mahila Thana Bhopal, compromise between parties"),
    ("default_bail", "default bail 167(2) for Kallu s/o Bhura, arrested on 01/01/2025, 90 days over, chargesheet not filed, crime no 5/2025 u/s 8/20 NDPS Act PS Gohad Bhind"),
    ("bail_sessions", "मुल्जिम अरविन्द कुमार पुत्र स्व. रामनरेश निवासी मोहल्ला कटरा थाना कोतवाली नगर जनपद प्रतापगढ़ उ.प्र. की जमानत प्रार्थना पत्र, मु.अ.स. 312/2025 धारा 115(2), 352, 351(3) बीएनएस, दिनांक 02/08/2025 से जिला कारागार में निरुद्ध"),
    ("bail_magistrate", "JMFC court Patna mein bail application for Bablu Kumar s/o Shiv Shankar Prasad, PS Gardanibagh case no 45/2025 u/s 303(2) BNS, arrested 20.07.2025"),
    ("anticipatory_bail_hc", "anticipatory bail before Rajasthan High Court Jaipur bench for Mahendra Meena s/o Ramphool Meena r/o Dausa, FIR 101/2025 PS Lalsot u/s 318(4) BNS, sessions court rejected anticipatory bail on 14/08/2025"),
    ("appeal_hc", "criminal appeal against judgment of conviction dated 18/07/2025 by Additional Sessions Judge Morena, appellant Ramesh Gurjar s/o Nathu Gurjar convicted u/s 307, 34 IPC sentenced 7 years"),
    ("complaint_156", "application u/s 175(3) BNSS because police station Gola Ka Mandir is not registering FIR of my client Priya Sharma against Vikas Tomar for harassment"),
    ("habeas_corpus", "habeas corpus petition by father Ramlal for his daughter Anjali illegally detained by in-laws at Datia"),
    ("eviction_suit", "eviction suit against tenant Mohd Salim from my shop at Sarafa Bazar Ujjain, rent Rs 8000 per month not paid for 10 months"),
    ("vakalatnama", "वकालतनामा — पक्षकार श्रीमती कमला बाई पत्नी स्व. गोविन्द सिंह, निवासी ग्राम पिपरौआ तहसील डबरा जिला ग्वालियर"),
]


@pytest.mark.parametrize("expected,brief", BRIEFS)
def test_the_right_reviewed_document_is_recognised(expected, brief):
    assert IN.recognise(brief)["tid"] == expected


def test_recognition_needs_no_model_and_is_fast():
    import time
    t = time.time()
    for _e, b in BRIEFS:
        IN.recognise(b)
    assert (time.time() - t) / len(BRIEFS) < 0.1


def test_a_brief_with_nothing_legal_in_it_is_not_guessed():
    r = IN.recognise("please help me with this")
    assert r["tid"] is None and r["level"] == "unsure"


def test_a_notice_about_a_cheque_is_a_notice_and_a_complaint_mentioning_a_notice_is_a_complaint():
    assert IN.recognise("draft a legal notice for cheque bounce of Rs 50000")["tid"] == "legal_notice"
    assert IN.recognise("138 complaint; legal notice sent on 20/06/2025; cheque dishonoured")["tid"] == "cheque_138"


def test_a_court_that_refused_is_the_court_below_not_the_forum():
    r = IN.recognise("bail for Ramu, bail rejected by magistrate")
    assert r["tid"] == "bail_sessions"
    assert IN.recognise("bail for Ramu, rejected by sessions court")["tid"] == "bail_hc"


# --------------------------------------------------------------------------- extraction
def _x(i: int, **kw) -> dict:
    exp, brief = BRIEFS[i]
    return IN.intake(brief, **kw)


def test_hindi_bail_facts_land_in_their_own_fields():
    f = _x(0)["fields"]
    assert f["applicant_name"] == "रामकुमार" and f["applicant_father"] == "श्यामलाल"
    assert f["applicant_age"] == "32"
    assert f["police_station"] == "कोतवाली" and f["district"] == "ग्वालियर"
    assert f["fir_number"] == "145/2025" and f["arrest_date"] == "10/03/2025"
    assert f["sections"] == ["420", "406 भा.न्या.सं."]
    assert f["court_city"] == "ग्वालियर" and f["state_name"] == "मध्यप्रदेश"
    assert "आपराधिक रिकॉर्ड" in f["custom_grounds"]


def test_a_sentence_final_danda_does_not_hide_a_place():
    # "ग्वालियर।" — the danda sits inside the Devanagari block
    assert [p.en for _s, _e, p in GEO.find_places("न्यायालय सत्र न्यायाधीश ग्वालियर।")] == ["Gwalior"]
    assert _x(0)["evidence"]["court_city"]["source"] == "brief"


def test_english_values_become_hindi_only_with_a_spelling_check():
    r = _x(2)
    assert r["lang"] == "hi"
    assert r["fields"]["applicant_name"] == "सुनील यादव"
    assert "applicant_name" in r["converted"]
    assert r["evidence"]["applicant_name"]["source"] == "converted"


def test_dates_are_labelled_by_their_own_words_not_the_next_dates():
    f = _x(2)["fields"]
    assert f["arrest_date"] == "12/07/2024"
    assert f["prior_order_date"] == "05/08/2024"
    assert f["prior_mag_rejected"] is True


def test_cheque_complaint_timeline_is_read_whole():
    f = _x(5)["fields"]
    assert f["complainant_name"] == "Agrawal Traders through proprietor Suresh Agrawal"
    assert f["complainant_father"] == "Mahesh Agrawal"
    assert f["accused_name"] == "Vinod Sharma" and f["accused_father"] == "Kailash Sharma"
    assert (f["cheque_date"], f["dishonour_date"], f["notice_date"]) == ("01/06/2025", "10/06/2025", "20/06/2025")
    assert f["amount"] == "Rs. 2,50,000"
    assert f["cheque_no"] == "456789"
    # a complainant firm is not "the accused is a company"
    assert "is_company" not in f


def test_hindi_notice_served_date_is_read_without_ai():
    b = "चेक बाउंस परिवाद — चेक दिनांक 01/07/2025, अनादरित दिनांक 08/07/2025, सूचना पत्र दिनांक 20/07/2025, सूचना तामील दिनांक 24/07/2025"
    f = IN.intake(b)["fields"]
    assert (f["cheque_date"], f["dishonour_date"], f["notice_date"], f["notice_known_date"]) == \
        ("01/07/2025", "08/07/2025", "20/07/2025", "24/07/2025")


def test_the_wife_and_the_husband_go_to_the_right_sides():
    f = _x(7)["fields"]
    assert f["petitioner_name"] == "सीता देवी" and f["respondent_name"] == "राजेश कुमार"
    assert f["petitioner_address"] == "इंदौर"
    assert f["respondent_income"] == "₹40,000" and f["amount_sought"] == "₹15,000"
    d = IN.intake("wife Sunita Devi wants divorce from husband Ravi Kumar, family court Kanpur Nagar")["fields"]
    assert d["applicant_name"] == "Sunita Devi" and d["respondent_name"] == "Ravi Kumar"


def test_aliases_co_accused_and_a_second_act():
    b = ("Bail for Sonu @ Sanjay Kewat s/o Late Ramesh Kewat age 22 yrs r/o Ward no 12 Bhitarwar Distt Gwalior (MP) "
         "Crime no 234/24 u/s 294, 323, 506, 34 IPC and 3(1)(r) SC/ST Act, PS Bhitarwar. Co-accused already granted bail.")
    r = IN.intake(b)
    f = r["fields"]
    assert r["lang"] == "en" and f["applicant_name"] == "Sonu @ Sanjay Kewat"
    assert f["applicant_father"] == "Ramesh Kewat" and f["applicant_age"] == "22"
    assert "उर्फ" in IN.intake(b, lang="hi")["fields"]["applicant_name"]
    assert f["parity"] is True
    assert f["sections"][-1].startswith("3(1)(r)")


def test_uttar_pradesh_district_jail_is_not_a_district():
    f = _x(14)["fields"]
    assert f["district"] == "प्रतापगढ़" and f["state_name"] == "उत्तर प्रदेश"
    assert f["arrest_date"] == "02/08/2025"
    assert "मुल्जिम" not in f["applicant_name"]


def test_a_sessions_conviction_goes_to_the_high_court_with_its_particulars():
    f = _x(17)["fields"]
    assert f["convicting_court"].startswith("Additional Sessions Judge")
    assert f["sentence_passed"] == "7 years"
    assert "appellant_age" not in f            # "7 years" is the sentence, not his age


def test_the_procedural_section_is_not_an_offence():
    f = _x(12)["fields"]
    assert f["fir_sections"] == ["498A", "406 IPC"]
    assert f["police_station"] == "Mahila Thana"


def test_bank_names_never_decide_the_state():
    assert GEO.find_state("चेक पंजाब नेशनल बैंक, इंदौर") is None
    assert GEO.find_state("Bank of Maharashtra, Pune branch") is None
    assert GEO.find_state("resident of Jaipur, Rajasthan") == "rajasthan"


def test_a_place_in_two_states_gives_no_state():
    for name in ("Aurangabad", "Bilaspur", "Pratapgarh", "Hamirpur"):
        assert GEO.lookup(name).state is None


def test_mp_in_a_registration_number_is_not_madhya_pradesh():
    assert GEO.find_state("motorcycle MP07 AB 1234") is None


def test_nothing_in_the_brief_means_nothing_in_the_form():
    r = IN.intake("", tid="bail_sessions")
    assert r["fields"] == {}


# --------------------------------------------------------------------------- amounts
@pytest.mark.parametrize("n,hi,en", [
    (112080, "एक लाख बारह हजार अस्सी रुपये", "Rupees One Lakh Twelve Thousand Eighty"),
    (75000, "पचहत्तर हजार रुपये", "Rupees Seventy Five Thousand"),
    (12345678, "एक करोड़ तेईस लाख पैंतालीस हजार छह सौ अठहत्तर रुपये",
     "Rupees One Crore Twenty Three Lakh Forty Five Thousand Six Hundred Seventy Eight"),
])
def test_amount_in_words(n, hi, en):
    assert AM.words(n, "hi") == hi and AM.words(n, "en") == en


def test_indian_grouping_and_parsing():
    assert AM.group(11208000) == "1,12,08,000"
    assert AM.parse("₹ 1,12,080/-") == 112080 and AM.parse("2.5 lakh") == 250000 and AM.parse("nil") is None


def test_amount_words_follow_the_amount_but_never_his_own_words():
    f, ev = WS.derive("cheque_138", {"amount": "₹75,000"}, {}, "hi")
    assert f["amount_words"] == "पचहत्तर हजार रुपये" and ev["amount_words"]["source"] == "computed"
    f["amount"] = "₹1,12,080"
    f, ev = WS.derive("cheque_138", f, ev, "hi")
    assert f["amount_words"] == "एक लाख बारह हजार अस्सी रुपये"
    f2, _ = WS.derive("cheque_138", {"amount": "₹75,000", "amount_words": "मेरे शब्द"}, {}, "hi")
    assert f2["amount_words"] == "मेरे शब्द"


# --------------------------------------------------------------------------- the page
@pytest.mark.parametrize("tid", sorted(TA.CANONICAL_MAP))
def test_every_reviewed_type_renders_empty_and_carries_no_one_advocates_town(tid):
    for lang in ("hi", "en"):
        html = WS.preview(tid, {}, lang)["html"]
        assert "〔" not in html
        for leak in ("ग्वालियर", "Gwalior", "म.प्र.", "मध्यप्रदेश", "Madhya Pradesh"):
            assert leak not in html, (tid, lang, leak)


def test_empty_particulars_are_chips_on_screen_and_blanks_in_the_file():
    pv = WS.preview("bail_sessions", {"applicant_name": "रामकुमार"}, "hi")["html"]
    assert 'data-k="applicant_father"' in pv and 'data-k="applicant_name"' not in pv
    printed = TA.document("bail_sessions", WS.export_fields("bail_sessions", {"applicant_name": "रामकुमार"}), "hi")
    assert "पुत्र श्री __________" in printed
    assert "व्यवसाय— व्यवसाय" not in printed


def test_optional_case_number_is_not_shown_as_missing():
    pv = WS.preview("bail_sessions", {}, "hi")["html"]
    assert 'data-k="case_number"' not in pv


def test_no_default_puts_gwalior_on_a_patna_filing():
    place = [f for s in WS.schema("cheque_138")["sections"] for f in s["fields"] if f["key"] == "place"][0]
    assert place["default"] is None


def test_parties_are_grouped_by_side_with_labels_that_say_whose():
    secs = WS.schema("cheque_138")["sections"]
    labels = [s["label"] for s in secs]
    assert labels[:2] == ["Complainant", "Accused"]
    accused = [f["label"] for f in secs[1]["fields"]]
    assert "Accused's address" in accused


# --------------------------------------------------------------------------- the junior's note
def test_138_limitation_is_worked_out():
    from datetime import date
    f = {"cheque_date": "01/06/2025", "dishonour_date": "10/06/2025", "notice_date": "20/06/2025",
         "notice_known_date": "25/06/2025"}
    notes = WS.checks("cheque_138", f, "hi", {}, today=date(2025, 7, 1))
    text = " ".join(n["text"] for n in notes)
    assert "10/07/2025" in text and "09/08/2025" in text          # cause of action, last day to file
    late = WS.checks("cheque_138", {**f, "notice_date": "20/07/2025"}, "hi", {}, today=date(2025, 7, 1))
    assert any(n["level"] == "fix" and "30 days" in n["text"] for n in late)


def test_ipc_is_questioned_only_against_the_fir_date_never_the_arrest():
    f = {"sections": ["379 IPC"], "arrest_date": "12/08/2024", "fir_number": "88/2024"}
    assert not any("after 1 July 2024" in n["text"] for n in WS.checks("bail_sessions", f, "hi", {}))
    f2 = {"sections": ["379 IPC"], "fir_date": "12/08/2024"}
    assert any("after 1 July 2024" in n["text"] for n in WS.checks("bail_sessions", f2, "hi", {}))


def test_a_successive_bail_must_disclose_the_refusal():
    notes = WS.checks("bail_sessions", {"prior_mag_rejected": True}, "hi", {})
    keys = {n.get("key") for n in notes if "successive" in n["text"]}
    assert {"prior_court", "prior_order_date"} <= keys


def test_converted_spellings_are_one_note_not_many():
    ev = {"applicant_name": {"source": "converted"}, "applicant_father": {"source": "converted"}}
    notes = WS.checks("bail_sessions", {"applicant_name": "सुनील", "applicant_father": "रमेश"}, "hi", ev)
    assert sum("check the spelling" in n["text"] for n in notes) == 1


# --------------------------------------------------------------------------- the AI top-up is grounded
def test_ai_values_not_in_the_brief_are_dropped(monkeypatch):
    brief = "bail for Ramkumar s/o Shyamlal, FIR 145/2025, thana Kotwali, arrested 10/03/2025"
    invented = {"applicant_name": "Ramkumar", "applicant_occupation": "Farmer", "arrest_date": "11/03/2025",
                "fir_number": "145/2025", "applicant_age": "40", "not_a_field": "x",
                "facts_narrative": "On 10/03/2025 the applicant was arrested in FIR 145/2025 and has 3 children."}

    def fake(system, user, **kw):
        import json
        return json.dumps(invented), {"model": "stub"}

    monkeypatch.setattr("headnote.llm.client._call_deepseek_or_groq", fake)
    res = WS.enrich(brief, "bail_sessions", "en", {})
    kept = res["fields"]
    assert kept.get("applicant_name") == "Ramkumar" and kept.get("fir_number") == "145/2025"
    for bad in ("applicant_occupation", "arrest_date", "applicant_age", "not_a_field"):
        assert bad not in kept
    assert "facts_narrative" not in kept           # "3" is not in the brief


def test_ai_never_overwrites_a_filled_field(monkeypatch):
    monkeypatch.setattr("headnote.llm.client._call_deepseek_or_groq",
                        lambda s, u, **k: ('{"applicant_name": "Someone Else"}', {"model": "stub"}))
    res = WS.enrich("bail for Someone Else", "bail_sessions", "en", {"applicant_name": "Ramkumar"})
    assert "applicant_name" not in res["fields"]


# --------------------------------------------------------------------------- the model chain
def test_groq_fallback_no_longer_asks_for_a_retired_model(monkeypatch):
    from headnote.llm import client
    monkeypatch.delenv("GROQ_FALLBACK_MODEL", raising=False)
    assert "llama" not in client.groq_fallback_model()
    assert client._groq_is_reasoner(client.groq_fallback_model())


def test_gemini_sits_between_deepseek_and_groq(monkeypatch):
    from headnote.llm import client
    calls = []

    def ds(*a, **k):
        calls.append("deepseek")
        raise RuntimeError("no key")

    def gm(*a, **k):
        calls.append("gemini")
        return "ok", {"model": "gemini:x"}

    def gq(*a, **k):
        calls.append("groq")
        return "groq", {"model": "groq:x"}

    monkeypatch.setattr(client, "_call_deepseek_fallback", ds)
    monkeypatch.setattr(client, "_call_gemini_fallback", gm)
    monkeypatch.setattr(client, "_call_groq_fallback", gq)
    text, meta = client._call_deepseek_or_groq("s", "u", max_tokens=10)
    assert (text, calls) == ("ok", ["deepseek", "gemini"])

    def gm_fail(*a, **k):
        calls.append("gemini")
        raise RuntimeError("503")

    calls.clear()
    monkeypatch.setattr(client, "_call_gemini_fallback", gm_fail)
    assert client._call_deepseek_or_groq("s", "u", max_tokens=10)[0] == "groq"
    assert calls == ["deepseek", "gemini", "groq"]


# --------------------------------------------------------------------------- matter → brief
def test_a_state_prosecution_matter_names_the_accused_as_the_applicant():
    row = {"case_number": "45", "case_year": "2024", "court_name": "Sessions Court Gwalior",
           "case_json": {"petitioner_name": "State of MP", "respondent_name": "Ramesh Kumar",
                         "police_station": "Kampoo", "fir_number": "210", "fir_year": "2023",
                         "sections": ["Indian Penal Code (I.P.C.), 1860", "Sections 302, 34"]}}
    brief = WS.matter_brief(row)
    assert "Accused: Ramesh Kumar" in brief and "u/s 302, 34 IPC" in brief
    f = IN.intake(brief, tid="bail_sessions", lang="hi")["fields"]
    assert f["applicant_name"] == "रमेश कुमार" and f["fir_number"] == "210/2023"
    assert f["sections"] == ["302", "34 भा.द.वि."] and f["state_name"] == "मध्यप्रदेश"


# --------------------------------------------------------------------------- the API
@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from headnote.api.app import app
    return TestClient(app)


def _as(user_id: str):
    from headnote.entitlements import CurrentUser
    return lambda: CurrentUser(id=user_id, email=f"{user_id}@example.test", role="authenticated", raw_claims={})


def test_intake_and_render_are_open_and_deterministic(client):
    j = client.post("/api/drafting/intake", json={"brief": BRIEFS[1][1]}).json()
    assert j["tid"] == "bail_sessions" and j["progress"]["missing"] == []
    assert j["fields"]["applicant_name"] == "Ramkumar"
    r = client.post("/api/drafting/render", json={"tid": "bail_sessions", "fields": j["fields"], "lang": "en"})
    assert r.status_code == 200 and "Ramkumar" in r.json()["html"]
    assert client.post("/api/drafting/render", json={"tid": "nope"}).status_code == 404


def test_intake_never_overwrites_what_he_typed(client):
    j = client.post("/api/drafting/intake", json={"brief": BRIEFS[1][1], "tid": "bail_sessions",
                                                   "fields": {"applicant_name": "Mine"},
                                                   "locked": ["applicant_name"]}).json()
    assert j["fields"]["applicant_name"] == "Mine" and "applicant_name" not in j["added"]


def test_save_and_reopen_belongs_to_its_author(client):
    from headnote.api.app import app
    from headnote.entitlements.auth import get_current_user
    app.dependency_overrides[get_current_user] = _as("u-alpha")
    try:
        s = client.post("/api/drafting/save", json={"tid": "bail_sessions", "fields": {"applicant_name": "Ramkumar"},
                                                     "brief": "bail for Ramkumar", "lang": "hi"})
        assert s.status_code == 200
        did = s.json()["draft_id"]
        back = client.get(f"/api/drafting/draft/{did}").json()
        assert back["fields"]["applicant_name"] == "Ramkumar" and back["brief"] == "bail for Ramkumar"
        app.dependency_overrides[get_current_user] = _as("u-beta")
        assert client.get(f"/api/drafting/draft/{did}").status_code == 404
        assert client.post("/api/drafting/save", json={"draft_id": did, "tid": "bail_sessions",
                                                        "fields": {}}).status_code == 404
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_word_export_prints_filing_blanks_not_field_names(client):
    import io
    import zipfile
    from headnote.api.app import app
    from headnote.entitlements.auth import get_current_user
    app.dependency_overrides[get_current_user] = _as("u-docx")
    try:
        r = client.post("/api/drafting/docx", json={"tid": "bail_sessions", "lang": "hi",
                                                     "fields": {"applicant_name": "रामकुमार"}, "layout_id": "legal_district"})
        assert r.status_code == 200
        xml = zipfile.ZipFile(io.BytesIO(r.content)).read("word/document.xml").decode("utf-8")
        text = re.sub(r"<[^>]+>", "", xml)
        assert "रामकुमार" in text and "व्यवसाय— व्यवसाय" not in text and "__________" in text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


def test_old_template_links_open_the_workspace(client):
    r = client.get("/draft/template/bail_sessions", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "/draft?type=bail_sessions"


def test_a_court_line_from_one_court_never_heads_another():
    j = IN.intake(BRIEFS[1][1], tid="bail_sessions")["fields"]
    assert "court_name" not in j                      # the engine's own field on bail
    carried = {**j, "court_name": "Court of the Sessions Judge, Gwalior (Madhya Pradesh)"}
    html = WS.preview("bail_hc", WS.derive("bail_hc", carried, {}, "en")[0], "en")["html"]
    assert "Sessions Judge" not in re.search(r'class="hdr-court"[^>]*>(.*?)</div>', html).group(1)


def test_english_typed_on_a_hindi_document_is_pointed_out():
    notes = WS.checks("bail_sessions", {"applicant_occupation": "Farmer"}, "hi", {})
    assert any("Typed in English on a Hindi document" in n["text"] for n in notes)


def test_a_change_request_that_switches_a_ground_actually_switches_it(client, monkeypatch):
    from headnote.api.app import app
    from headnote.entitlements.auth import get_current_user
    from headnote.drafter import prompt_tweak
    monkeypatch.setattr(prompt_tweak, "run_router", lambda spec, data, prompt: {"toggles": {"breadwinner": True}})
    app.dependency_overrides[get_current_user] = _as("u-tweak")
    try:
        r = client.post("/api/draft/template-tweak", json={"doc_type": "bail_sessions", "fields": {"applicant_name": "Ram"},
                                                            "prompt": "he is the only earning member", "lang": "hi"})
        assert r.status_code == 200
        assert r.json()["fields"].get("breadwinner") is True
    finally:
        app.dependency_overrides.pop(get_current_user, None)
