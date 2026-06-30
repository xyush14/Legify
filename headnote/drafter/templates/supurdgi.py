"""सुपुर्दगी — interim custody of seized property — §497/§503 BNSS (§451/§457 CrPC).

Canonical build, mirror-first from Vishnu ji's real §451/457 filing (benchmark:
"451, 457 Dinesh Singh" — release of a seized Bolero pick-up in an Excise §34(2)
matter). The owner applies for interim custody (सुपुर्दगी) of the seized
property pending trial. No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Sunderbhai Ambalal Desai v. State of Gujarat (2002) 10 SCC 283", "point": "seized property should not languish at the PS — grant interim custody", "verified": False},
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
    ps = _ph(a.get("police_station"), "आरक्षी केन्द्र"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections")); prop = _ph(a.get("property_desc"), "जप्तशुदा वाहन/सम्पत्ति का विवरण")
    seiz = _ph(a.get("seizure_date"), "जप्ती दिनांक")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "सुपुर्दगी", "applicant_label": "आवेदक",
        "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक का नाम")],
        "respondent_label": "अनावेदक", "respondent_desc": [f'{state} द्वारा {ps}'],
        "versus": "बनाम", "title_line": "आवेदन पत्र अन्तर्गत धारा 497/503 भा.ना.सु.सं. (451/457 दं.प्र.सं.)",
    })
    P = [f'यहकि, प्रार्थी {prop} का पंजीकृत स्वामी है।',
         f'यहकि, प्रार्थी की उक्त सम्पत्ति को {ps} द्वारा अपराध क्रमांक— {crime} अन्तर्गत धारा {secs} में दिनांक '
         f'{seiz} को जप्त कर थाने पर खड़ा/सुरक्षित कर लिया गया है, जिसके सम्बन्ध में अभियोग पत्र माननीय न्यायालय '
         f'के समक्ष प्रस्तुत किया जा चुका है।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[प्रार्थी का सम्पत्ति से सम्बन्ध एवं झूठा फँसाये जाने/स्वामित्व का आधार — '
                 'खाली पंक्ति से अलग पैरा]</span>')
    if g.get("deteriorating", True):
        P.append('यहकि, उक्त सम्पत्ति थाने पर खुले में खड़ी रहने से निरन्तर क्षतिग्रस्त एवं मूल्यह्रासित हो रही '
                 'है; उसे थाने पर रखे रहने से कोई प्रयोजन सिद्ध नहीं होता तथा आवश्यक होने पर उसका मूल्यांकन/'
                 'फोटोग्राफी कराई जा सकती है।')
    if g.get("ready_security", True):
        P.append('यहकि, प्रार्थी माननीय न्यायालय द्वारा अधिरोपित प्रतिभूति/मुचलका प्रस्तुत करने, सम्पत्ति को '
                 'अन्तरित/विक्रय न करने तथा आवश्यकता पड़ने पर न्यायालय के समक्ष प्रस्तुत करने हेतु तत्पर है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय महोदय,</p>',
           '<p class="cb-prelude">आवेदक की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि उपरोक्त जप्तशुदा {prop} को धारा '
               f'497/503 भा.ना.सु.सं. (451/457 दं.प्र.सं.) के अधीन उपयुक्त प्रतिभूति पर प्रार्थी को अन्तरिम '
               f'सुपुर्दगी पर दिये जाने का आदेश पारित करने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदक")}</div><div>— आवेदक</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "State of M.P.")
    ps = _ph(a.get("police_station"), "police station"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections"), sep=" and "); prop = _ph(a.get("property_desc"), "the seized property")
    seiz = _ph(a.get("seizure_date"), "date of seizure")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [_ph(a.get("applicant_name"), "applicant")],
        "respondent_label": "Respondent", "respondent_desc": [f'{state} through {ps}'],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTIONS 497/503 BNSS, 2023 "
                                          "(SECTIONS 451/457 CrPC, 1973) — FOR INTERIM CUSTODY"})
    P = [f'That the applicant is the registered owner of {prop}.',
         f'That the said property was seized by {ps} in Crime No. {crime} under {secs} on {seiz} and is lying '
         f'at the police station; the charge-sheet stands filed before this Hon\'ble Court.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("deteriorating", True):
        P.append('That the property, lying in the open at the police station, is continuously deteriorating and '
                 'losing value; no purpose is served by its retention, and it can be valued / photographed if '
                 'required.')
    if g.get("ready_security", True):
        P.append('That the applicant is ready to furnish the security / bond imposed by this Hon\'ble Court, not '
                 'to alienate or transfer the property, and to produce it before the Court whenever required.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The applicant most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that the seized {prop} be '
               f'released to the applicant on interim custody (supurdgi) under Sections 497/503 BNSS '
               f'(451/457 CrPC) on suitable security, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "Applicant")}</div><div>— Applicant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("deteriorating", "थाने पर क्षति/मूल्यह्रास — पैरा", "Deteriorating at PS — para", default=True),
    F.toggle("ready_security", "प्रतिभूति हेतु तत्पर — पैरा", "Ready to furnish security — para", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("applicant_name", "आवेदक (स्वामी) का नाम", "Applicant (owner) name", F.NAME, True, "parties"),
        F.f("state_name", "अनावेदक राज्य", "Respondent State", section="parties", default="म.प्र. राज्य"),
        F.f("police_station", "आरक्षी केन्द्र / पुलिस थाना", "Police station", required=True, section="crime"),
        F.f("crime_number", "अपराध क्रमांक", "Crime no.", required=True, section="crime", ocr="order"),
        F.f("sections", "धाराएं", "Offence sections", F.SECTION_LIST, True, "crime", ocr="order"),
        F.f("property_desc", "जप्तशुदा सम्पत्ति का विवरण", "Description of seized property", required=True, section="facts",
            hint="जैसे: बुलेरो पिकअप क्रमांक एम.पी.07 ___"),
        F.f("seizure_date", "जप्ती दिनांक", "Date of seizure", F.DATE, section="facts"),
        F.f("facts_narrative", "स्वामित्व / झूठा फँसाव का आधार", "Ownership / false-implication grounds", F.LONGTEXT, True, "facts",
            hint="प्रार्थी का सम्पत्ति से सम्बन्ध, पूर्व विक्रय/अनुबन्ध आदि — खाली पंक्ति से अलग"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_type", "प्रकरण प्रकार", "Case type", section="court", hint="जैसे आर.सी.टी. / सत्रवाद — शीर्षक का प्रकरण-कोड"))
    return F.build_spec("supurdgi", flds, _TOGGLES, companions=["vakalatnama", "supurdgi bond"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2023", "case_type": "सुपुर्दगी",
    "applicant_name": "____ सिंह", "state_name": "म.प्र. राज्य",
    "police_station": "आरक्षी केन्द्र ____, ग्वालियर", "crime_number": "____/2021",
    "sections": ["34(2) आबकारी अधिनियम"], "property_desc": "बुलेरो पिकअप क्रमांक— एम.पी.07 जी.ए. ____",
    "seizure_date": "__/__/2021",
    "facts_narrative": (
        "प्रार्थी का उक्त वाहन प्रकरण में झूठा फँसाया गया है; विवेचना में यह तथ्य आया है कि प्रार्थी ने "
        "घटना दिनांक के पूर्व ही वाहन को अनुबन्ध-विक्रय कर दिया था।"
    ),
    "court_city_en": "Gwalior", "applicant_name_en": "____ Singh", "state_name_en": "State of M.P.",
    "police_station_en": "P.S. ____, Gwalior", "sections_en": ["34(2) Excise Act"],
    "property_desc_en": "Bolero pick-up No. MP-07-GA-____",
    "facts_narrative_en": (
        "the applicant's vehicle has been falsely implicated; even the investigation reveals that the applicant "
        "had sold the vehicle under an agreement prior to the date of the alleged offence."
    ),
    "grounds": {"deteriorating": True, "ready_security": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="सुपुर्दगी / अन्तरिम custody (धारा 497/503 · 451/457) — समीक्षा · द्विभाषी · "
                           "विष्णु जी की 451/457 फाइलिंग से अक्षरशः · reviewed: false")
