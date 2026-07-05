"""Production of documents — Section 94 BNSS / §91 CrPC (summons to produce a
document or thing) · Magistrate or Sessions.

Canonical-standard build, mirror-first from Vishnu ji's real §91/§94 filings
(benchmarks: "91 Jitendra rathore" — CCTV/CDR in a §394/dacoity matter; "91
Harisingh Shivhare" — society/bank records in a §138 matter; "91/94 papita
dhakad" — prior complaint copies + inquiry statements in a §302 matter). No LLM
writes any text.

Mirror notes (do NOT "improve"):
  • The ACCUSED files it within the प्रकरण; State is `अभियोगी`, accused `अभियुक्त`
    (a §138 complainant sits in the अभियोगी slot via state_name override).
  • NO crime/order table and NO section labels — paras flow as numbered `यहकि`.
  • The verb is **तलब** (call for / summon); the thing sought is **बांछित दस्तावेज**.
  • Body order: case background → allegation/dispute → the specific documents
    sought + why material → "without these I cannot present a proper defence" →
    prayer to तलब the documents (optionally staying proceedings till produced).
  • No case law in the body (the §91/94 test is materiality for a just decision —
    not a mini-trial); candidates go to CITE_AT_HEARING only.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

# CITE-AT-HEARING only (never in the body). Verify before oral use.
CITE_AT_HEARING = [
    {"case": "State of Orissa v. Debendra Nath Padhi (2005) 1 SCC 568", "point": "scope of §91 at pre-charge stage — production for a just decision", "verified": False},
    {"case": "Nitya Dharmananda v. Gopal Sheelum Reddy (2018) 2 SCC 93", "point": "court's power to summon material documents necessary for a just decision", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _secs(sections, sep=" एवं ") -> str:
    if isinstance(sections, (list, tuple)):
        return sep.join(_esc(s) for s in sections if str(s).strip()) or "................"
    return _esc(sections) if sections and str(sections).strip() else "................"


def _chunks(text) -> list:
    return [x.strip() for x in str(text or "").split("\n\n") if x.strip()]


def _cfg(court):
    if court == "sessions":
        return dict(level="sessions", suffix="सत्रवाद",
                    court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (________)")
    return dict(level="magistrate", suffix="आर.सी.टी.",
                court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (________)")


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "magistrate"
    c = _cfg(court)
    plural = bool(a.get("is_plural", False))
    aw = "प्रार्थीगण" if plural else "प्रार्थी"
    acc = "अभियुक्तगण" if plural else "अभियुक्त"
    state = _esc(a.get("state_name") or "________")
    section_title = a.get("section_title") or "धारा 94 भा.ना.सु.सं. (91 दं.प्र.सं.)"
    ps = _ph(a.get("police_station"), "थाना"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections"))
    custodian = (a.get("custodian") or "").strip()

    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), a.get("state_name") or "") \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])

    hdr = render_header({
        "side_label": "",
        "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or c["suffix"],
        "applicant_label": "अभियोगी", "applicant_desc": [state],
        "respondent_label": acc, "respondent_desc": [_ph(a.get("accused_names"), "अभियुक्तगण के नाम")],
        "versus": "बनाम", "title_line": f"आवेदन पत्र अन्तर्गत {section_title}",
    })

    g = a.get("grounds") or {}
    P = []
    # 1. case background — FIR/charge-sheet/stage
    stage = _esc(a.get("current_stage") or "आरोप विरचन हेतु नियत")
    P.append(f'यहकि, {aw} के विरुद्ध {ps} द्वारा अपराध क्रमांक— {crime} अन्तर्गत धारा {secs} का अपराध '
             f'पंजीवद्ध किया गया, जिसमें अनुसंधान पूर्ण होने के उपरान्त अभियोग पत्र माननीय न्यायालय के समक्ष '
             f'प्रस्तुत किया गया है। उक्त प्रकरण आज दिनांक को {stage} है।')
    # 2. allegation / case facts
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts:
            P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[प्रकरण का आक्षेप एवं वास्तविक तथ्य यहाँ — अभियोजन का कथन तथा वह '
                 'परिस्थिति जिसके कारण नीचे वर्णित दस्तावेज आवश्यक हैं — या अभियोग पत्र/FIR अपलोड कर भरवायें]</span>')
    # 3. the specific documents sought + their relevance
    docs = _chunks(a.get("documents_sought"))
    if docs:
        for ch in docs:
            P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[जिन दस्तावेज/वस्तु को तलब कराना है उनका विवरण एवं प्रासंगिकता — '
                 'जैसे सी.सी.टी.व्ही. फुटेज, सी.डी.आर./कॉल डिटेल, जांच दस्तावेज, बैंक/संस्था अभिलेख आदि]</span>')
    # 3b. material for a just decision (toggle, default on)
    if g.get("material_for_just_decision", True):
        P.append(f'यहकि, उपरोक्त बांछित दस्तावेज प्रकरण के न्यायपूर्ण निराकरण के लिये उचित एवं आवश्यक हैं तथा '
                 f'वर्तमान में {aw} के आधिपत्य में उपलब्ध नहीं हैं।')
    # 4. defence handicap (toggle, default on)
    if g.get("defence_handicap", True):
        P.append(f'यहकि, उपरोक्त दस्तावेजों की अनुपस्थिति में {aw} माननीय न्यायालय के समक्ष अपना युक्तियुक्त '
                 f'बचाव प्रस्तुत करने में असमर्थ है। ऐसी स्थिति में उपरोक्त बांछित दस्तावेज तलब किया जाना '
                 f'न्यायसंगत है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'यहकि, {_esc(cu)}')
    P.append('यहकि, अन्य तर्क वक्त बहस निवेदित किये जावेंगे।')

    src = f'{_esc(custodian)} से ' if custodian else ''
    stay = (' तथा उक्त दस्तावेज प्रस्तुत होने तक प्रकरण की आगामी कार्यवाही स्थगित किये जाने'
            if g.get("stay_till_produced") else '')

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append(f'<p class="cb-prelude">{aw} की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः श्रीमान जी से सादर निवेदन है कि {aw} का यह आवेदन पत्र स्वीकार कर {src}उपरोक्त बांछित '
               f'दस्तावेज को तलब किये जाने{stay} का आदेश पारित करने की कृपा करें।')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{aw}</div><div>— {acc}</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "magistrate"
    c = _cfg(court)
    plural = bool(a.get("is_plural", False))
    aw = "applicants" if plural else "applicant"
    state = _esc(a.get("state_name_en") or "State of ________")
    ps = _ph(a.get("police_station_en") or a.get("police_station"), "police station")
    crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections_en") or a.get("sections"), sep=" and ")
    custodian = (a.get("custodian_en") or a.get("custodian") or "").strip()

    court_name = a.get("court_name_en") or compose_court_name(c["level"], a.get("court_city_en") or a.get("court_city"), a.get("state_name_en") or a.get("state_name") or "________", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Criminal Case",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Prosecution", "applicant_desc": [state],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_names_en") or a.get("accused_names"), "names of the accused")],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 94 BNSS, 2023 "
                                          "(FORMERLY SECTION 91 CrPC, 1973) — FOR PRODUCTION OF DOCUMENTS",
    })
    g = a.get("grounds") or {}
    P = []
    stage = _esc(a.get("current_stage_en") or "fixed for arguments on charge")
    P.append(f'That a crime came to be registered against the {aw} by {ps} in Crime No. {crime} under {secs}; '
             f'investigation being complete, the charge-sheet stands filed before this Hon\'ble Court and the '
             f'matter is presently {stage}.')
    facts = _chunks(a.get("facts_narrative_en") or a.get("facts_narrative"))
    for ch in facts:
        P.append(f'That {_esc(ch)}')
    docs = _chunks(a.get("documents_sought_en") or a.get("documents_sought"))
    for ch in docs:
        P.append(f'That {_esc(ch)}')
    if g.get("material_for_just_decision", True):
        P.append(f'That the documents sought above are necessary and material for a just decision of the case '
                 f'and are not presently in the possession of the {aw}.')
    if g.get("defence_handicap", True):
        P.append(f'That in the absence of the said documents the {aw} cannot present a proper and effective '
                 f'defence; it is therefore just and proper that the said documents be summoned.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'That {_esc(cu)}')
    P.append('That further submissions shall be advanced at the time of hearing.')

    src = f'from {_esc(custodian)} ' if custodian else ''
    stay = (' and that the further proceedings be stayed until the documents are produced'
            if g.get("stay_till_produced") else '')
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append(f'<p class="cb-prelude">The {aw} most respectfully submit as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court '
               f'may be pleased to allow the application and summon {src}the documents sought above{stay}, in '
               f'the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{"Applicants" if plural else "Applicant"} — Accused</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("material_for_just_decision", "न्यायपूर्ण निराकरण हेतु आवश्यक", "Material for a just decision", default=True),
    F.toggle("defence_handicap", "दस्तावेज बिना बचाव असम्भव", "Cannot defend without the documents", default=True),
    F.toggle("stay_till_produced", "प्रस्तुति तक कार्यवाही स्थगित करें", "Stay proceedings till produced", default=False),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("case_type", "प्रकरण प्रकार", "Case type", F.SELECT, section="court",
            options=[{"value": "आर.सी.टी.", "label": "आर.सी.टी. (RCT)"},
                     {"value": "सत्रवाद", "label": "सत्रवाद (Sessions)"},
                     {"value": "विशेष सत्रवाद", "label": "विशेष सत्रवाद"}]),
        F.f("accused_names", "अभियुक्त/प्रार्थी का नाम", "Accused / applicant name(s)", F.NAME, True, "parties", ocr="order"),
        F.f("is_plural", "एक से अधिक अभियुक्त?", "More than one accused?", F.TOGGLE, section="parties", default=False),
        F.f("state_name", "अभियोगी पक्ष (राज्य/परिवादी)", "Prosecution side (State / complainant)", section="parties", default=""),
        F.f("police_station", "पुलिस थाना", "Police station", required=True, section="crime", ocr="order"),
        F.f("crime_number", "अपराध क्रमांक", "Crime no.", required=True, section="crime", ocr="order"),
        F.f("sections", "धाराएं", "Offence sections", F.SECTION_LIST, True, "crime", ocr="order"),
        F.f("current_stage", "प्रकरण की वर्तमान स्थिति", "Current stage", section="crime",
            hint="जैसे: आरोप विरचन हेतु नियत / प्रतिपरीक्षण हेतु नियत"),
        F.f("facts_narrative", "प्रकरण का आक्षेप एवं तथ्य", "Allegation & case facts", F.LONGTEXT, True, "facts",
            ocr="order", hint="अभियोजन का कथन + वह परिस्थिति जिससे दस्तावेज आवश्यक हैं — OCR/वॉइस से"),
        F.f("documents_sought", "तलब किये जाने वाले दस्तावेज + प्रासंगिकता", "Documents sought + relevance", F.LONGTEXT, True, "facts",
            hint="जैसे: सी.सी.टी.व्ही. फुटेज, सी.डी.आर., जांच दस्तावेज, बैंक/संस्था अभिलेख — और वे क्यों आवश्यक हैं"),
        F.f("custodian", "किससे तलब करें (थाना/बैंक/विभाग)", "Summon from whom (PS / bank / dept.)", section="facts",
            hint="रिक्त छोड़ने पर सामान्य 'उपरोक्त बांछित दस्तावेज' रहेगा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    return F.build_spec(f"production:{court}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions"]},
                        companions=["vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court": "sessions", "court_city": "ग्वालियर",
    "case_number": "____/2024", "case_type": "विशेष सत्रवाद",
    "state_name": "म.प्र. राज्य", "accused_names": "क ख ग आदि", "is_plural": True,
    "police_station": "थाना ____, ग्वालियर", "crime_number": "____/2024",
    "sections": ["394 भा.द.वि.", "11/13 डकैती अधिनियम"],
    "current_stage": "आरोप विरचन हेतु नियत",
    "facts_narrative": (
        "अभियोजन के अनुसार फरियादी से दिनांक ____ को सरेराह मोबाइल एवं नगदी छीनी जाना बताया गया है तथा "
        "प्रार्थीगण पर कूटरचित घटना के आधार पर नगद एवं मोबाइल की जप्ती दर्शाई गई है।\n\n"
        "घटना स्थल शहर का अत्यधिक भीड़भाड़ वाला व्यापारिक क्षेत्र है जहाँ शासकीय एवं प्रायवेट सी.सी.टी.व्ही. "
        "कैमरे लगे हुए हैं, किन्तु अभियोजन द्वारा कोई फुटेज अभियोग पत्र के साथ प्रस्तुत नहीं की गई है।"
    ),
    "documents_sought": (
        "घटना स्थल से समाधिया कॉलोनी मार्ग तक लगे शासकीय एवं प्रायवेट सी.सी.टी.व्ही. कैमरों की दिनांक ____ की "
        "फुटेज तथा जप्तशुदा मोबाइल क्रमांक ____ की सी.डी.आर. एवं लोकेशन रिपोर्ट, जो प्रकरण के न्यायपूर्ण "
        "निराकरण हेतु आवश्यक है।"
    ),
    "custodian": "संबंधित पुलिस थाना एवं दूरसंचार कम्पनी",
    # English mirror values (auto-filled by the EN-toggle translator in the product)
    "court_city_en": "Gwalior", "state_name_en": "State of M.P.",
    "accused_names_en": "A B C & ors.",
    "police_station_en": "P.S. ____, Gwalior",
    "sections_en": ["394 IPC", "11/13 Dacoity Act"],
    "current_stage_en": "fixed for arguments on charge",
    "facts_narrative_en": (
        "as per the prosecution, the complainant was robbed of his mobile and cash in broad daylight on ____, "
        "and a fabricated recovery of cash and a mobile has been shown against the applicants.\n\n"
        "the place of occurrence is a busy commercial area covered by government and private CCTV cameras, yet "
        "no footage was filed with the charge-sheet."
    ),
    "documents_sought_en": (
        "the CCTV footage dated ____ from the government and private cameras along the route from the place of "
        "occurrence to Samadhia Colony, and the CDR and location report of the seized mobile No. ____, which "
        "are necessary for a just decision of the case."
    ),
    "custodian_en": "the concerned police station and the telecom company",
    "grounds": {"material_for_just_decision": True, "defence_handicap": True, "stay_till_produced": False},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="दस्तावेज तलब (धारा 94 भा.ना.सु.सं. / 91 दं.प्र.सं.) — समीक्षा · canonical header · "
                           "द्विभाषी · विष्णु जी की §91/§94 फाइलिंग से अक्षरशः · reviewed: false")
