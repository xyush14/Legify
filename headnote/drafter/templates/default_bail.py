"""Default / statutory bail — §187(3) BNSS proviso (§167(2) CrPC) — release on the
prosecution's failure to file the charge-sheet within the statutory 60/90 days.

AUTHOR-tier build (Vishnu ji has no §187/§167(2) filing in the corpus, so this is
NOT a mirror): the structure, grounds and sections are authored from the trained
knowledge layer (skill `legal-frameworks.md`: merits-INDEPENDENT, indefeasible &
a fundamental right) IN his bail house-style (बन्दी की ओर से · यहकि · बनाम ·
prayer flow). reviewed:false — pending Vishnu's sign-off.

INVARIANT: no case law in the body. The argument rests on the STATUTE (the
proviso to §187(3) / §167(2)) — the leading judgments (Bikramjit Singh, Rakesh
Kumar Paul, Uday Mohanlal Acharya, Sanjay Dutt) are listed in CITE_AT_HEARING
(verified:false) for oral use, NEVER written into the document.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

# CITE-AT-HEARING only (never in the body). Verify + confirm apposite before oral use.
CITE_AT_HEARING = [
    {"case": "Bikramjit Singh v. State of Punjab (2020) 12 SCC 327", "point": "default bail is an indefeasible right & part of Art. 21", "verified": False},
    {"case": "Rakesh Kumar Paul v. State of Assam (2017) 15 SCC 67", "point": "pro-liberty computation of the 60/90-day period", "verified": False},
    {"case": "Uday Mohanlal Acharya v. State of Maharashtra (2001) 5 SCC 453", "point": "right must be availed before the charge-sheet is filed", "verified": False},
    {"case": "Sanjay Dutt v. State (II) (1994) 5 SCC 410", "point": "right is enforceable only until the challan is filed", "verified": False},
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


def _overlay_en(a: dict) -> dict:
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""):
            a[k[:-3]] = a[k]
    return a


def _cfg(court):
    if court == "sessions":
        return dict(level="sessions", court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (म.प्र.)")
    return dict(level="magistrate", court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)")


def _period(a) -> str:
    return "90" if str(a.get("statutory_period") or "60").strip().startswith("90") else "60"


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    c = _cfg(a.get("court") or "magistrate")
    g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "म.प्र.")
    ps = _ph(a.get("police_station"), "थाना"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections"))
    days = _period(a)
    bracket = ("10 वर्ष से कम कारावास" if days == "60" else "मृत्यु/आजीवन कारावास अथवा 10 वर्ष या उससे अधिक कारावास")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), state) \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])

    hdr = render_header({
        "side_label": "बन्दी की ओर से",
        "court_name": court_name, "case_code": "अपराध क्रमांक",
        "case_number": a.get("crime_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "",
        "applicant_label": "आवेदक", "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक का नाम")],
        "respondent_label": "अनावेदक", "respondent_desc": [f'{state} शासन जर्ये {ps}'],
        "versus": "बनाम",
        "title_line": "जमानत आवेदन पत्र अन्तर्गत धारा 187(3) भा.ना.सु.सं. (167(2) दं.प्र.सं.)",
    })

    P = []
    P.append(f'यहकि, आवेदक को {ps} द्वारा अपराध क्रमांक— {crime} अन्तर्गत धारा {secs} में दिनांक '
             f'{_ph(a.get("arrest_date"), "गिरफ्तारी दिनांक")} को गिरफ्तार किया गया था, तभी से आवेदक '
             f'न्यायिक अभिरक्षा में निरुद्ध है।')
    P.append(f'यहकि, प्रकरण की धाराएं {bracket} से दण्डनीय होने से, भारतीय नागरिक सुरक्षा संहिता की धारा '
             f'187(3) (दं.प्र.सं. की धारा 167(2)) के अधीन अनुसंधान पूर्ण कर अभियोग पत्र {days} दिवस की '
             f'अवधि में प्रस्तुत किया जाना अनिवार्य था।')
    P.append(f'यहकि, आवेदक की अभिरक्षा/गिरफ्तारी दिनांक से उक्त {days} दिवस की विहित अवधि '
             f'{("दिनांक " + _esc(a.get("period_expired_date")) + " को ") if a.get("period_expired_date") else ""}'
             f'व्यतीत हो चुकी है, किन्तु अनुसंधान एजेन्सी द्वारा आज दिनांक तक माननीय न्यायालय के समक्ष '
             f'अभियोग पत्र/अंतिम प्रतिवेदन प्रस्तुत नहीं किया गया है।')
    if g.get("fundamental_right", True):
        P.append('यहकि, विहित अवधि में अभियोग पत्र प्रस्तुत न होने पर आवेदक को धारा 187(3) के परन्तुक के अधीन '
                 'जमानत पर रिहा होने का अपराजेय (indefeasible) विधिक अधिकार अर्जित हो चुका है, जो संविधान के '
                 'अनुच्छेद 21 का अंग है तथा अपराध की गम्भीरता या गुणदोष के आधार पर पराजित नहीं होता।')
    if g.get("before_chargesheet", True):
        P.append('यहकि, आवेदक द्वारा यह अधिकार अभियोग पत्र प्रस्तुत होने के पूर्व ही माननीय न्यायालय के समक्ष '
                 'प्रस्तुत किया जा रहा है।')
    if g.get("ready_to_furnish", True):
        P.append('यहकि, आवेदक माननीय न्यायालय द्वारा अधिरोपित समस्त प्रतिभूति बन्धपत्र भरने एवं समस्त शर्तों '
                 'के पालन हेतु तत्पर एवं तैयार है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'यहकि, {_esc(cu)}')
    P.append('यहकि, उपरोक्त परिस्थितियों में आवेदक को धारा 187(3) भा.ना.सु.सं. के अधीन अनिवार्य/स्वतःकृत '
             'जमानत पर रिहा किया जाना न्यायोचित एवं न्यायसंगत है।')

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append('<p class="cb-prelude">आवेदक/बन्दी की ओर से जमानत आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि आवेदक को धारा 187(3) '
               'भा.ना.सु.सं. (167(2) दं.प्र.सं.) के अधीन अनिवार्य जमानत पर, उपयुक्त प्रतिभूति बन्धपत्र पर रिहा '
               'किये जाने का आदेश पारित करने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदक")}</div><div>— बन्दी आवेदक</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = _overlay_en(a)
    c = _cfg(a.get("court") or "magistrate")
    g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "M.P.")
    ps = _ph(a.get("police_station"), "police station"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections"), sep=" and ")
    days = _period(a)
    bracket = ("imprisonment of less than 10 years" if days == "60"
               else "death / imprisonment for life or imprisonment of 10 years or more")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), state, lang="en")
    hdr = render_header({
        "side_label": "On behalf of the detenu", "court_name": court_name, "case_code": "Crime No.",
        "case_number": a.get("crime_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [_ph(a.get("applicant_name"), "applicant")],
        "respondent_label": "Respondent", "respondent_desc": [f'State of {state} through {ps}'],
        "versus": "Versus",
        "title_line": "APPLICATION FOR DEFAULT BAIL UNDER SECTION 187(3) BNSS, 2023 "
                      "(PROVISO TO SECTION 167(2) CrPC, 1973)",
    })
    P = []
    P.append(f'That the applicant was arrested by {ps} in Crime No. {crime} under {secs} on '
             f'{_ph(a.get("arrest_date"), "date of arrest")} and has remained in judicial custody since.')
    P.append(f'That the offences being punishable with {bracket}, the investigation was required to be '
             f'completed and the charge-sheet filed within {days} days as mandated by Section 187(3) BNSS '
             f'(Section 167(2) CrPC).')
    P.append(f'That the statutory period of {days} days from the applicant\'s arrest '
             f'{("expired on " + _esc(a.get("period_expired_date")) + " and ") if a.get("period_expired_date") else "has "}'
             f'has elapsed, yet the investigating agency has not filed the charge-sheet / final report before '
             f'this Hon\'ble Court till date.')
    if g.get("fundamental_right", True):
        P.append('That on such default the applicant has accrued an indefeasible statutory right to be released '
                 'on bail under the proviso to Section 187(3), which is part of the fundamental right under '
                 'Article 21 and is not defeated by the gravity or merits of the offence.')
    if g.get("before_chargesheet", True):
        P.append('That the applicant is asserting this right before the filing of the charge-sheet.')
    if g.get("ready_to_furnish", True):
        P.append('That the applicant is ready and willing to furnish the bail bonds and abide by all conditions '
                 'imposed by this Hon\'ble Court.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'That {_esc(cu)}')
    P.append('That in the aforesaid circumstances the applicant is entitled to be released on default / '
             'statutory bail under Section 187(3) BNSS.')
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append('<p class="cb-prelude">The applicant / detenu most respectfully submits as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court '
               'may be pleased to release the applicant on default bail under Section 187(3) BNSS (Section '
               '167(2) CrPC) on suitable bail bonds, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{_ph(a.get("applicant_name"), "Applicant")}</div><div>— Detenu/Applicant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("fundamental_right", "अपराजेय अधिकार (अनुच्छेद 21) पैरा", "Indefeasible-right (Art. 21) para", default=True),
    F.toggle("before_chargesheet", "अभियोग पत्र से पूर्व — पैरा", "Before charge-sheet — para", default=True),
    F.toggle("ready_to_furnish", "बन्धपत्र भरने हेतु तत्पर — पैरा", "Ready to furnish bonds — para", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("applicant_name", "आवेदक (बन्दी) का नाम", "Applicant (detenu) name", F.NAME, True, "parties", ocr="fir"),
        F.f("state_name", "राज्य", "State", section="parties", default="म.प्र."),
        F.f("police_station", "पुलिस थाना", "Police station", required=True, section="crime", ocr="fir"),
        F.f("crime_number", "अपराध क्रमांक", "Crime no.", required=True, section="crime", ocr="fir"),
        F.f("sections", "धाराएं", "Offence sections", F.SECTION_LIST, True, "crime", ocr="fir"),
        F.f("arrest_date", "गिरफ्तारी दिनांक", "Date of arrest", F.DATE, True, "crime", ocr="fir"),
        F.f("statutory_period", "विहित अवधि", "Statutory period", F.SELECT, section="grounds", default="60",
            options=[{"value": "60", "label": "60 दिन (10 वर्ष से कम)"},
                     {"value": "90", "label": "90 दिन (मृत्यु/आजीवन/10 वर्ष+)"}]),
        F.f("period_expired_date", "अवधि समाप्ति दिनांक (वैकल्पिक)", "Period-expiry date (optional)", F.DATE, section="grounds"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec(f"default_bail:{court}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions"]},
                        companions=["vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court": "magistrate", "court_city": "ग्वालियर", "case_year": "2026",
    "applicant_name": "____", "state_name": "म.प्र.",
    "police_station": "थाना ____, ग्वालियर", "crime_number": "____/2026",
    "sections": ["420", "406 भा.द.वि."], "arrest_date": "__/__/2026",
    "statutory_period": "60", "period_expired_date": "",
    "court_city_en": "Gwalior", "state_name_en": "M.P.",
    "applicant_name_en": "____", "police_station_en": "P.S. ____, Gwalior",
    "sections_en": ["420", "406 IPC"],
    "grounds": {"fundamental_right": True, "before_chargesheet": True, "ready_to_furnish": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="अनिवार्य/डिफॉल्ट जमानत (धारा 187(3) / 167(2)) — समीक्षा · AUTHORED from §187 framework "
                           "(कोई mirror नहीं) · body = statute-only, judgments → CITE_AT_HEARING · reviewed: false")
