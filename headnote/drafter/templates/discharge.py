"""Discharge — Section 262 BNSS / §239 CrPC (Magistrate) · §250 / §227 (Sessions).

Canonical-standard rebuild of his §239 discharge (benchmark: "239__ 498 - Arvind
sharma", a 498A / Dowry-Prohibition matter): canonical header + the point-wise body
reproduced VERBATIM from his filing + bilingual. No LLM writes any text.

Mirror notes (do NOT "improve"):
  • The accused FILES it; the State is `अभियोगी`, the accused `अभियुक्तगण`.
  • NO crime/order table and NO section labels here — discharge paras just flow as
    numbered `यहकि` (unlike his HC bail). Faithfulness > forced consistency.
  • The family-member-principle ground cites settled law GENERICALLY
    ("माननीय सर्वोच्च न्यायालय एवं माननीय उच्च न्यायालय द्वारा पारित न्यायदृष्टान्तों…")
    — NO case name in the body. The discharge TEST is grave-suspicion / ingredients
    not made out at face value; never argue credibility (that is trial).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

# CITE-AT-HEARING only (never in the body). Verify before oral use.
CITE_AT_HEARING = [
    {"case": "Union of India v. Prafulla Kumar Samal (1979) 3 SCC 4", "point": "grave-suspicion test; sift & weigh, not a mini-trial", "verified": False},
    {"case": "Sajjan Kumar v. CBI (2010) 9 SCC 368", "point": "reaffirms the discharge standard", "verified": False},
    {"case": "Kahkashan Kausar v. State of Bihar (2022) 6 SCC 599", "point": "498A omnibus allegations against relatives — no offence", "verified": False},
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


def _cfg(court):
    if court == "sessions":
        return dict(level="sessions", sec="250", crpc="227",
                    court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (________)")
    return dict(level="magistrate", sec="262", crpc="239",
                court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (________)")


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "magistrate"
    c = _cfg(court)
    plural = bool(a.get("is_plural", True))
    aw = "प्रार्थीगण" if plural else "प्रार्थी"        # applicant word in body
    acc = "अभियुक्तगण" if plural else "अभियुक्त"        # accused label
    state = _esc(a.get("state_name") or "________")
    section_title = a.get("section_title") or f"धारा {c['sec']} भा.ना.सु.सं. ({c['crpc']} दं.प्र.सं.)"
    ps = _ph(a.get("police_station"), "थाना"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections"))

    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), state) \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])

    hdr = render_header({
        "side_label": "",  # the accused applies within the प्रकरण — no side-line
        "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "आर.सी.टी.",
        "applicant_label": "अभियोगी", "applicant_desc": [f'{state} राज्य'],
        "respondent_label": acc, "respondent_desc": [_ph(a.get("accused_names"), "अभियुक्तगण के नाम")],
        "versus": "बनाम", "title_line": f"आवेदन पत्र अन्तर्गत {section_title}",
    })

    g = a.get("grounds") or {}
    allegation = a.get("offence_allegation") or (f"{aw} द्वारा फरियादिया से दहेज की मांग करते हुये "
                                                 f"शारीरिक व मानसिक रूप से प्रताड़ित किया जाता है")
    P = []
    P.append(f'यहकि, {aw} के विरुद्ध {ps} द्वारा अपराध क्रमांक— {crime} अन्तर्गत धारा {secs} के तहत '
             f'फरियादी की रिपोर्ट पर से दर्ज किया गया है, जिसमें अनुसंधान पूर्ण होने के उपरान्त अभियोग '
             f'पत्र माननीय न्यायालय के समक्ष प्रस्तुत किया गया है। उक्त प्रकरण आज दिनांक को आरोप तर्क हेतु नियत है।')
    P.append(f'यहकि, उपरोक्त प्रकरण में फरियादी द्वारा अपनी रिपोर्ट में {aw} के विरुद्ध आरोप लगाया है '
             f'कि {_esc(allegation)}।')
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[प्रकरण के वास्तविक तथ्य '
                 'यहाँ — आरोपी का फरियादिया से सम्बन्ध, पृथक निवास, झूठा फँसाये जाने का कारण — या अभियोग '
                 'पत्र/FIR अपलोड कर भरवायें]</span>')
    if g.get("no_dowry_demand", True):
        P.append(f'यहकि, {aw} द्वारा फरियादिया से कभी भी दहेज की मांग को लेकर शारीरिक एवं मानसिक प्रताड़ना '
                 f'नहीं की गई है। फरियादिया द्वारा द्वेषपूर्ण भाव से {aw} को उक्त प्रकरण में झूठा फँसाया गया है।')
    if g.get("family_member_principle", True):
        P.append('यहकि, माननीय सर्वोच्च न्यायालय एवं माननीय उच्च न्यायालय द्वारा पारित न्यायदृष्टान्तों में '
                 'स्पष्ट रूप से अभिनिर्धारित किया गया है कि केवल पारिवारिक सदस्य होने के आधार पर असत्य रूप से '
                 'आरोपी बनाये गये पारिवारिक सदस्यों के विरुद्ध धारा 498ए भा.द.वि. एवं घरेलू हिंसा का अपराध '
                 'निर्मित नहीं होता है।')
    if g.get("no_prima_facie", True):
        P.append(f'यहकि, फरियादिया द्वारा {aw} के विरुद्ध लगाये गये समस्त आक्षेप मिथ्या व बनावटी हैं। {aw} '
                 f'के विरुद्ध प्रथम दृष्टया अभिलेख पर ऐसी कोई साक्ष्य विद्यमान नहीं है जिससे यह प्रमाणित होता '
                 f'हो कि फरियादिया द्वारा लगाये गये आरोप सत्य हैं।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'यहकि, {_esc(cu)}')
    P.append(f'यहकि, उपरोक्त स्थिति में {aw} को उक्त प्रकरण से उन्मुक्त किया जाना न्यायोचित एवं न्यायसंगत है।')
    P.append('यहकि, अन्य तर्क वक्त बहस निवेदित किये जावेंगे।')

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append(f'<p class="cb-prelude">{aw}/{acc} की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः माननीय न्यायालय से सादर निवेदन है कि {aw} का यह आवेदन पत्र स्वीकार कर {aw} को उक्त '
               f'प्रकरण में वर्णित धारा {secs} से उन्मोचित (discharge) किये जाने की कृपा करें।')
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
    plural = bool(a.get("is_plural", True))
    state = _esc(a.get("state_name_en") or a.get("state_name") or "________")
    acc = "Accused" if not plural else "Accused (applicants)"
    # English render prefers *_en values (filled by the EN-toggle translate-fields in
    # the live product); falls back to the entered value so nothing breaks.
    ps = _ph(a.get("police_station_en") or a.get("police_station"), "police station"); crime = _ph(a.get("crime_number"), "..../....")
    secs = _secs(a.get("sections_en") or a.get("sections"), sep=" and ")
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    court_name = a.get("court_name_en") or compose_court_name(c["level"], a.get("court_city_en") or a.get("court_city"), state, lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Criminal Case",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Prosecution", "applicant_desc": [f'State of {state}'],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_names_en") or a.get("accused_names"), "names of the accused")],
        "versus": "Versus", "title_line": f"APPLICATION FOR DISCHARGE UNDER SECTION {c['sec']} BNSS, 2023 "
                                          f"(FORMERLY SECTION {c['crpc']} CrPC, 1973)",
    })
    g = a.get("grounds") or {}
    P = []
    P.append(f'That the applicants have been charge-sheeted by {ps} in Crime No. {crime} under {secs} on a '
             f'report of the complainant; investigation being complete, the charge-sheet stands filed and the '
             f'matter is fixed today for arguments on charge.')
    P.append('That the complainant has alleged against the applicants ' + _esc(a.get("offence_allegation_en")
             or "cruelty and harassment in connection with a demand for dowry") + '.')
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            P.append(f'That in truth, {_esc(ch)}')
    if g.get("no_dowry_demand", True):
        P.append('That the applicants never subjected the complainant to any cruelty over a demand for dowry; '
                 'she has, out of malice, falsely implicated them.')
    if g.get("family_member_principle", True):
        P.append('That the Hon\'ble Supreme Court and High Court have authoritatively held that merely being a '
                 'family member does not make out an offence under Section 498A IPC or the DV Act against '
                 'relatives arrayed without specific allegations.')
    if g.get("no_prima_facie", True):
        P.append('That all the allegations are false and concocted, and there is no prima-facie material on '
                 'record to establish that they are true.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'That {_esc(cu)}')
    P.append('That in the facts and circumstances, it is just and proper that the applicants be discharged.')
    P.append('That further arguments shall be advanced at the time of hearing.')
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append('<p class="cb-prelude">The applicants/accused most respectfully submit as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court '
               f'may be pleased to allow the application and discharge the applicants from the offences under '
               f'{secs}, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Applicants — Accused</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("no_dowry_demand", "कोई दहेज मांग/क्रूरता नहीं (498A)", "No dowry demand / cruelty (498A)", default=True),
    F.toggle("family_member_principle", "केवल पारिवारिक सदस्य — अपराध नहीं (498A)", "Mere family-member — no offence (498A)", default=True),
    F.toggle("no_prima_facie", "प्रथम दृष्टया कोई साक्ष्य नहीं", "No prima-facie material", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("case_type", "प्रकरण प्रकार", "Case type", F.SELECT, section="court", default="आर.सी.टी.",
            options=[{"value": "आर.सी.टी.", "label": "आर.सी.टी. (RCT)"}, {"value": "सत्र प्रकरण", "label": "सत्र प्रकरण"}]),
        F.f("accused_names", "अभियुक्तगण के नाम", "Accused name(s)", F.NAME, True, "parties", ocr="order"),
        F.f("is_plural", "एक से अधिक अभियुक्त?", "More than one accused?", F.TOGGLE, section="parties", default=True),
        F.f("state_name", "राज्य", "State", section="parties", default=""),
        F.f("police_station", "पुलिस थाना", "Police station", required=True, section="crime", ocr="order"),
        F.f("crime_number", "अपराध क्रमांक", "Crime no.", required=True, section="crime", ocr="order"),
        F.f("sections", "धाराएं", "Offence sections", F.SECTION_LIST, True, "crime", ocr="order"),
        F.f("offence_allegation", "फरियादी का आरोप", "Complainant's allegation", F.LONGTEXT, section="facts"),
        F.f("facts_narrative", "बचाव के वास्तविक तथ्य", "Defence facts", F.LONGTEXT, section="facts",
            ocr="order", hint="पृथक निवास, सम्बन्ध, झूठा फँसाव — OCR/वॉइस से"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    return F.build_spec(f"discharge:{court}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions"]},
                        companions=["vakalatnama", "§94/§91 production application (if documents sought)"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court": "magistrate", "court_city": "ग्वालियर",
    "case_number": "____/2021", "case_type": "आर.सी.टी.",
    "state_name": "म.प्र.", "accused_names": "क ख ग आदि", "is_plural": True,
    "police_station": "महिला थाना ____, ग्वालियर", "crime_number": "____/2021",
    "sections": ["498ए भा.द.वि.", "3/4 दहेज प्रतिषेध अधिनियम"],
    "facts_narrative": (
        "वास्तविकता यह है कि प्रार्थीगण फरियादिया के जेठ एवं जेठानी हैं तथा विवाह के पूर्व से ही अपने "
        "बच्चों सहित सहअभियुक्त से पृथक निवास करते हैं; प्रार्थीगण द्वारा कभी कोई दहेज मांग नहीं की गई।\n\n"
        "फरियादिया एवं उसके पति के मध्य आपसी मतभेद के कारण विवाद रहता था; प्रार्थीगण द्वारा समझौते का "
        "प्रयास किया गया, किन्तु द्वेषवश प्रार्थीगण को मिथ्या रूप से आलिप्त कर दिया गया।"
    ),
    # English values (in the product these are auto-filled by the EN-toggle translator)
    "court_city_en": "Gwalior", "state_name_en": "M.P.",
    "accused_names_en": "A B C & ors.",
    "police_station_en": "Mahila Thana ____, Gwalior",
    "sections_en": ["498A IPC", "3/4 Dowry Prohibition Act"],
    "offence_allegation_en": "cruelty and harassment in connection with a demand for dowry",
    "facts_narrative_en": (
        "the applicants are the complainant's elder brother-in-law and his wife and, since before the "
        "marriage, have lived separately from the co-accused with their own children; no demand for "
        "dowry was ever made by the applicants.\n\n"
        "there were ongoing disputes between the complainant and her husband; the applicants tried to "
        "mediate, but out of malice they have been falsely implicated in the present case."
    ),
    "grounds": {"no_dowry_demand": True, "family_member_principle": True, "no_prima_facie": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="उन्मोचन (धारा 262/239 · 250/227) — समीक्षा · canonical header · द्विभाषी · "
                           "विष्णु जी की Arvind Sharma §239/498A फाइलिंग से अक्षरशः · reviewed: false")
