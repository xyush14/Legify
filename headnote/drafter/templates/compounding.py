"""Compounding of offence on compromise — §359 BNSS (§320 CrPC).

Build from his §320(2) idiom (benchmark: "320 HC rajinama" — the §320(2)
compounding application he files with a settlement; here as a STANDALONE
trial-court compounding) + the framework. The complainant, having amicably
settled, applies to compound a compoundable offence so the accused is acquitted.
No case law in the body (the test is statutory compoundability + a voluntary
settlement); the settlement-quashing route (Gian Singh etc.) lives in quashing.py.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Gian Singh v. State of Punjab (2012) 10 SCC 303", "point": "settlement of private/personal disputes (for §482 quashing, distinct from §320)", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _secs(x, sep=" एवं "): return (sep.join(_esc(s) for s in x if str(s).strip()) or "................") if isinstance(x,(list,tuple)) else (_esc(x) if x and str(x).strip() else "................")
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_CD = "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)"


def render_hi(a: dict) -> str:
    a = a or {}; g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "म.प्र. राज्य")
    secs = _secs(a.get("sections"))
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "आर.सी.टी.", "applicant_label": "फरियादी/आवेदक",
        "applicant_desc": [_ph(a.get("complainant_name"), "फरियादी का नाम")],
        "respondent_label": "आरोपी", "respondent_desc": [_ph(a.get("accused_name"), "आरोपी का नाम")],
        "versus": "बनाम", "title_line": "आवेदन पत्र अन्तर्गत धारा 359 भा.ना.सु.सं. (320 दं.प्र.सं.)",
    })
    P = [f'यहकि, उपरोक्त प्रकरण {state} द्वारा आरोपी के विरुद्ध धारा {secs} में माननीय न्यायालय के समक्ष '
         f'विचाराधीन है, जिसमें फरियादी अभियोजन साक्षी है।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[पक्षकारों के मध्य आपसी राजीनामा/समझौते का विवरण — सम्बन्ध, विवाद कैसे '
                 'सुलझा — खाली पंक्ति से अलग पैरा]</span>')
    P.append(f'यहकि, प्रकरण में वर्णित धारा {secs} का अपराध दण्ड प्रक्रिया संहिता की धारा 320 '
             f'(भा.ना.सु.सं. की धारा 359) के अधीन शमनीय (compoundable) अपराध की श्रेणी में आता है।')
    if g.get("no_objection", True):
        P.append('यहकि, फरियादी को आरोपी के विरुद्ध उक्त प्रकरण में अभियोजन चलाये जाने में कोई आपत्ति नहीं है '
                 'तथा फरियादी आरोपी के साथ उक्त अपराध का शमन (राजीनामा) करना चाहता है।')
    if g.get("voluntary", True):
        P.append('यहकि, उक्त राजीनामा फरियादी द्वारा स्वेच्छा से, बिना किसी दबाव, भय अथवा प्रलोभन के किया गया '
                 'है; इससे किसी तृतीय पक्ष के हित प्रभावित नहीं होते।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय महोदय,</p>',
           '<p class="cb-prelude">फरियादी/आवेदक की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि धारा 359 भा.ना.सु.सं. (320 '
               f'दं.प्र.सं.) के अधीन उक्त अपराध के शमन (राजीनामा) की अनुमति प्रदान कर आरोपी को दोषमुक्त किये '
               f'जाने का आदेश पारित करने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("complainant_name"), "फरियादी")}</div><div>— फरियादी/आवेदक</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "State of M.P.")
    secs = _secs(a.get("sections"), sep=" and ")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Complainant", "applicant_desc": [_ph(a.get("complainant_name"), "complainant")],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_name"), "accused")],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 359 BNSS, 2023 (SECTION 320 CrPC, 1973) "
                                          "— FOR COMPOUNDING"})
    P = [f'That the matter is pending against the accused under {secs} before this Hon\'ble Court, in which the '
         f'complainant is a prosecution witness.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    P.append(f'That the offence under {secs} is compoundable under Section 320 CrPC (Section 359 BNSS).')
    if g.get("no_objection", True):
        P.append('That the complainant has no objection to the compounding and wishes to compound the offence '
                 'with the accused.')
    if g.get("voluntary", True):
        P.append('That the compromise has been arrived at voluntarily, without any pressure, fear or '
                 'inducement, and no third-party interest is affected.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The complainant most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that under Section 359 BNSS '
               f'(Section 320 CrPC) the compounding of the offence be permitted and the accused be acquitted, in '
               f'the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("complainant_name"), "Complainant")}</div><div>— Complainant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("no_objection", "फरियादी को आपत्ति नहीं — पैरा", "Complainant has no objection — para", default=True),
    F.toggle("voluntary", "स्वेच्छिक राजीनामा — पैरा", "Voluntary compromise — para", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("complainant_name", "फरियादी/आवेदक का नाम", "Complainant name", F.NAME, True, "parties"),
        F.f("accused_name", "आरोपी का नाम", "Accused name", F.NAME, True, "parties"),
        F.f("state_name", "राज्य", "State", section="parties", default="म.प्र. राज्य"),
        F.f("sections", "शमनीय धाराएं", "Compoundable sections", F.SECTION_LIST, True, "crime", ocr="order"),
        F.f("facts_narrative", "राजीनामा का विवरण", "Settlement details", F.LONGTEXT, True, "facts",
            hint="पक्षकारों का सम्बन्ध, विवाद कैसे सुलझा — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("compounding", flds, _TOGGLES, companions=["राजीनामा/compromise deed", "vakalatnama"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2024", "case_type": "आर.सी.टी.",
    "complainant_name": "____", "accused_name": "____", "state_name": "म.प्र. राज्य",
    "sections": ["323", "504", "506 भा.द.वि."],
    "facts_narrative": (
        "फरियादी एवं आरोपी एक ही मोहल्ले के निवासी एवं परिचित हैं; मामूली कहासुनी से उपजे विवाद को गणमान्य "
        "व्यक्तियों की मध्यस्थता से आपस में सुलझा लिया गया है तथा अब दोनों पक्षों के मध्य कोई विवाद शेष नहीं है।"
    ),
    "court_city_en": "Gwalior", "complainant_name_en": "____", "accused_name_en": "____",
    "state_name_en": "State of M.P.", "sections_en": ["323", "504", "506 IPC"],
    "facts_narrative_en": (
        "the complainant and the accused are neighbours and acquaintances; the dispute arising from a minor "
        "altercation has been amicably resolved through the mediation of respectable persons, and no dispute "
        "now survives between the parties."
    ),
    "grounds": {"no_objection": True, "voluntary": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="अपराध शमन / Compounding (धारा 359 · 320) — समीक्षा · द्विभाषी · trial-court compounding "
                           "(HC settlement-quashing → quashing.py) · reviewed: false")
