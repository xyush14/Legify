"""Private complaint — §223 BNSS / §200 CrPC (परिवाद पत्र) before the JMFC.

Canonical-standard builder mirrored VERBATIM from his filed परिवाद (benchmark:
"Parivad — Priyanka boudh" — a forgery / false-evidence private complaint, §§192-471
IPC). Canonical header + यहकि facts + prima-facie / jurisdiction / no-other-proceeding
recitals + cognizance-summon-punish prayer + witness list. Bilingual. No LLM text.

Mirror notes (decoded — do not "improve"):
  • परिवादी (complainant) vs आरोपीगण (accused — may be several, numbered); parties by बनाम.
    Case line `प्रकरण क्रमांक— ___/<yr> परिवाद पत्र` (suffix). JMFC.
  • Title = the alleged offence: `परिवाद पत्र अन्तर्गत धारा <secs>`.
  • Salutation `माननीय न्यायालय,` → `परिवादी की ओर से परिवाद पत्र निम्न प्रकार प्रस्तुत है ः—`.
  • Facts = यहकि paras (the complaint narrative). Then the three closing recitals:
    prima-facie offence made out · jurisdiction (श्रवणाधिकार) · no other proceeding pending.
  • Prayer flows direct: take cognizance · register offence under §<secs> · summon the accused
    by शक्ति-पत्र (process) · award maximum punishment · grant the complainant compensation.
  • Companions: §200 examination of complainant on oath · list of witnesses (साक्ष्य सूची) ·
    documents/annexures · vakalatnama. (§202 inquiry / §156(3) reference where applicable.)
  • No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Priyanka Srivastava v. State of U.P. (2015) 6 SCC 287",
     "point": "§156(3)/private complaint must be supported by an affidavit; checks frivolous complaints.", "verified": False},
    {"case": "Pepsi Foods Ltd. v. Special Judicial Magistrate (1998) 5 SCC 749",
     "point": "Summoning is a serious matter — magistrate must apply mind, not act mechanically.", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _secs(sections, sep) -> str:
    if isinstance(sections, (list, tuple)):
        items = [_esc(s) for s in sections if str(s).strip()]
        return sep.join(items) if items else "________"
    return _esc(sections) if sections and str(sections).strip() else "________"


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name") or "________")
    name = a.get("complainant_name") or ""
    sec_str = _secs(a.get("offence_sections"), ", ")
    ps = _ph(a.get("police_station"), "थाना")
    # Route through the pan-India chokepoint — blanks (____) when city/state unknown,
    # never MP. (Do not reintroduce a hardcoded "(म.प्र.)" fallback — feedback_court_location.)
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), state)
    fem = a.get("complainant_is_woman", True)
    cw = "परिवादिया" if fem else "परिवादी"

    cdesc = (f'{"श्रीमती " if fem else ""}{_ph(name, "नाम")} '
             + (f'पत्नी श्री {_ph(a.get("complainant_spouse"), "पति")}, ' if fem and a.get("complainant_spouse") else
                f'पुत्र/पुत्री श्री {_ph(a.get("complainant_father"), "पिता")}, ')
             + f'आयु— {_ph(a.get("complainant_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("complainant_occupation"), "व्यवसाय")},')
    cdesc2 = f'निवासी— <u>{_ph(a.get("complainant_address"), "पता")}</u> ({state})'

    acc = []
    if (a.get("accused_desc") or "").strip():
        for ln in [x.strip() for x in a["accused_desc"].split("\n") if x.strip()]:
            acc.append(_esc(ln))
    else:
        acc.append('<span class="ph">[आरोपीगण — क्रमवार]</span>')
    if a.get("accused_address"):
        acc.append(f'निवासीगण— <u>{_esc(a.get("accused_address"))}</u> ({state})')

    hdr = render_header({
        "side_label": "", "court_name": court_name,
        "case_code": "प्रकरण क्रमांक", "case_suffix": "परिवाद पत्र",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": cw, "applicant_desc": [cdesc, cdesc2],
        "respondent_label": "आरोपीगण", "respondent_desc": acc,
        "versus": "बनाम", "title_line": f"परिवाद पत्र अन्तर्गत धारा {sec_str}",
    })

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append(f'<p class="cb-prelude">{cw} की ओर से परिवाद पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            out.append(f'<li>यहकि, {_esc(ch)}</li>')
    else:
        out.append('<li><span class="ph">[परिवाद का कथानक — आरोपीगण का '
                   'कृत्य, घटनाक्रम, पुलिस में शिकायत एवं निष्क्रियता — यहाँ]</span></li>')
    out.append(f'<li>यहकि, आरोपीगण के विरुद्ध प्रथम दृष्टया धारा {sec_str} का अपराध बनता है।</li>')
    out.append(f'<li>यहकि, {cw} का निवास स्थान आरक्षी केन्द्र {ps} के क्षेत्राधिकार में होने से माननीय न्यायालय '
               f'को इस परिवाद का श्रवणाधिकार एवं क्षेत्राधिकार प्राप्त है।</li>')
    out.append(f'<li>यहकि, {cw} द्वारा उक्त घटना के सम्बन्ध में भारतवर्ष के किसी भी थाने अथवा न्यायालय में आज '
               f'दिनांक तक इस परिवाद के अतिरिक्त अन्य कोई कार्यवाही नहीं की गई है और न ही कोई प्रकरण लंबित है।</li>')
    out.append('</ol>')

    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः श्रीमान जी से निवेदन है कि {cw} का परिवाद पत्र स्वीकार कर आरोपीगण के विरुद्ध धारा {sec_str} के '
               f'तहत अपराध का संज्ञान लेकर आरोपीगण को शक्ति-पत्र (समन) से तलब कर, विचारण उपरान्त अधिकतम दण्ड से '
               f'दण्डित कर {cw} को आरोपीगण से प्रतिकर दिलाये जाने का आदेश पारित करने की कृपा करें।')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांकः— {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{"प्रार्थिया" if fem else "प्रार्थी"}</div>'
               f'<div>{"श्रीमती " if fem else ""}{_ph(name, "नाम")} — {cw}</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('<div class="cb-note">साथ संलग्न: धारा 223 भा.ना.सु.सं. (200 दं.प्र.सं.) परिवादी का शपथ-कथन · '
               'साक्ष्य सूची · सम्बन्धित दस्तावेज (एनेक्जर) · वकालतनामा।</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name_en") or a.get("state_name") or "________")
    name = _ph(a.get("complainant_name_en") or a.get("complainant_name"), "complainant")
    sec_str = _secs(a.get("offence_sections_en") or a.get("offence_sections"), ", ")
    ps = _ph(a.get("police_station_en") or a.get("police_station"), "police station")

    cdesc = (f'{name}, '
             + (f'W/o {_ph(a.get("complainant_spouse_en") or a.get("complainant_spouse"), "husband")}, '
                if a.get("complainant_spouse_en") or a.get("complainant_spouse")
                else f'S/D-o {_ph(a.get("complainant_father_en") or a.get("complainant_father"), "father")}, ')
             + f'aged {_ph(a.get("complainant_age"), "..")} years, R/o '
             + f'{_ph(a.get("complainant_address_en") or a.get("complainant_address"), "address")} ({state})')
    acc = []
    src = a.get("accused_desc_en") or a.get("accused_desc") or ""
    if src.strip():
        for ln in [x.strip() for x in src.split("\n") if x.strip()]:
            acc.append(_esc(ln))
    else:
        acc.append('[Accused — serially]')
    if a.get("accused_address_en") or a.get("accused_address"):
        acc.append(f'all R/o {_ph(a.get("accused_address_en") or a.get("accused_address"), "")} ({state})')

    hdr = render_header({
        "side_label": "", "court_name": a.get("court_name_en") or compose_court_name(
            "magistrate", a.get("court_city_en") or a.get("court_city"), state, lang="en"),
        "case_code": "Case No.", "case_suffix": "(Private Complaint)",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Complainant", "applicant_desc": [cdesc],
        "respondent_label": "Accused", "respondent_desc": acc,
        "versus": "Versus", "title_line": f"PRIVATE COMPLAINT UNDER SECTION 223 BNSS (200 CrPC) — §§ {sec_str}",
    })
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THIS HON\'BLE COURT,</p>')
    out.append('<p class="cb-prelude">The complainant most respectfully submits as under:—</p>')
    out.append('<ol class="cb-paras">')
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            out.append(f'<li>That {_esc(ch)}</li>')
    else:
        out.append('<li>[The complaint narrative — the accused\'s acts, the sequence of events, the police '
                   'complaint and inaction — here.]</li>')
    out.append(f'<li>That a prima-facie offence under §§ {sec_str} is made out against the accused.</li>')
    out.append(f'<li>That the complainant resides within the jurisdiction of Police Station {ps}, and this Hon\'ble '
               f'Court has jurisdiction to try this complaint.</li>')
    out.append('<li>That the complainant has not initiated any other proceeding on these facts at any police '
               'station or court, nor is any matter pending.</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may be '
               f'pleased to take cognizance of the offence under §§ {sec_str}, summon the accused by process, and on '
               f'trial award the maximum punishment and grant the complainant compensation.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Complainant</div><div>{name} — Complainant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")}) — Advocate</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("complainant_is_woman", "परिवादी महिला है (परिवादिया/श्रीमती)", "Complainant is a woman", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः)", "Court name (auto)", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("complainant_name", "परिवादी का नाम", "Complainant name", F.NAME, True, "parties"),
        F.f("complainant_spouse", "पति/पत्नी का नाम (यदि लागू)", "Spouse name (if applicable)", F.NAME, section="parties"),
        F.f("complainant_father", "पिता का नाम", "Father's name", F.NAME, section="parties"),
        F.f("complainant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("complainant_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("complainant_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("accused_desc", "आरोपीगण (क्रमवार — एक पंक्ति प्रति आरोपी)", "Accused (one per line)", F.LONGTEXT, True, "parties"),
        F.f("accused_address", "आरोपीगण का पता", "Accused address", F.ADDRESS, section="parties"),
        F.f("offence_sections", "अपराध की धाराएँ", "Offence sections", F.SECTION_LIST, True, "crime"),
        F.f("police_station", "आरक्षी केन्द्र (क्षेत्राधिकार)", "Police station (jurisdiction)", section="crime"),
        F.f("facts_narrative", "परिवाद का कथानक", "Complaint narrative", F.LONGTEXT, True, "facts"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.f("state_name", "राज्य", "State", section="parties", hint="मामले का राज्य (रिक्त रखने पर स्थान रिक्त)"))
    return F.build_spec("parivad:magistrate", flds, _TOGGLES,
                        companions=["§223 BNSS examination of complainant on oath", "witness list (साक्ष्य सूची)",
                                    "documents / annexures", "vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court_name": "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ग्वालियर (म.प्र.)",
    "court_name_en": "Court of the Judicial Magistrate First Class, Gwalior (M.P.)",
    "case_number": "", "case_year": "2024", "complainant_is_woman": True,
    "complainant_name": "क ख", "complainant_name_en": "K.", "complainant_spouse": "अतुल गौतम", "complainant_spouse_en": "Atul",
    "complainant_age": "26", "complainant_occupation": "गृहकार्य",
    "complainant_address": "बी—56, विवेक नगर, ठाटीपुर, ग्वालियर", "complainant_address_en": "B-56, Vivek Nagar, Thatipur, Gwalior",
    "state_name": "म.प्र.", "state_name_en": "M.P.",
    "accused_desc": ("अतुल गौतम पुत्र श्री ग सिंह, आयु— 30 वर्ष, असिस्टेन्ट ब्रांच मैनेजर — आरोपी क्र.1\n"
                      "अविनाश गौतम पुत्र श्री ग सिंह, आयु— 33 वर्ष, प्रायवेट नौकरी — आरोपी क्र.2\n"
                      "रोहित राठौर पुत्र श्री भ सिंह, प्रोपराईटर (कंस्ट्रक्शन) — आरोपी क्र.3"),
    "accused_desc_en": ("Atul, S/o G., aged 30, Asst. Branch Manager — Accused No. 1\n"
                         "Avinash, S/o G., aged 33, private service — Accused No. 2\n"
                         "Rohit, S/o B., proprietor (construction) — Accused No. 3"),
    "accused_address": "विवेक नगर, ठाटीपुर, ग्वालियर", "accused_address_en": "Vivek Nagar, Thatipur, Gwalior",
    "offence_sections": ["420 भा.द.वि.", "465 भा.द.वि.", "467 भा.द.वि.", "468 भा.द.वि.", "471 भा.द.वि.", "120बी भा.द.वि."],
    "offence_sections_en": ["420 IPC", "465 IPC", "467 IPC", "468 IPC", "471 IPC", "120B IPC"],
    "police_station": "ठाटीपुर", "police_station_en": "Thatipur",
    "facts_narrative": (
        "परिवादी, आरोपी क्रमांक—01 की वैध विवाहिता पत्नी है; दहेज प्रताड़ना के सम्बन्ध में परिवार न्यायालय एवं सत्र "
        "न्यायालय में प्रकरण लंबित हैं।\n\n"
        "आरोपीगण ने मिलकर परिवादी के नाम से कूटरचित नौकरी-अनुबन्ध एवं वेतन-पर्ची तैयार कर, परिवादी के स्कैन किये "
        "हुये हस्ताक्षर लगाकर, धारा 24 हि.वि.अधि. के आवेदन के जबाव के साथ परिवार न्यायालय में मिथ्या साक्ष्य के रूप "
        "में प्रस्तुत की।\n\n"
        "परिवादी ने उक्त कम्पनी में कभी नौकरी नहीं की; आरोपीगण ने आरोपी क्र.1 को लाभ दिलाने हेतु षड्यन्त्रपूर्वक "
        "कूटरचित दस्तावेज तैयार किये। पुलिस थाना ठाटीपुर एवं पुलिस अधीक्षक कार्यालय में शिकायत के बाद भी कोई "
        "कार्यवाही नहीं हुई।"
    ),
    "facts_narrative_en": (
        "the complainant is the legally wedded wife of Accused No. 1; matters relating to dowry cruelty are pending "
        "before the Family and Sessions Courts.\n\n"
        "the accused jointly fabricated a forged employment-contract and salary-slip in the complainant's name, affixed "
        "her scanned signatures, and filed them as false evidence with the reply to her §24 HMA application in the "
        "Family Court.\n\n"
        "the complainant never worked at the said company; the accused forged the documents in conspiracy to benefit "
        "Accused No. 1. Despite complaints to P.S. Thatipur and the SP office, no action was taken."
    ),
    "filing_date": "16/02/2024", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="परिवाद पत्र — धारा 223 भा.ना.सु.सं. (200 दं.प्र.सं.) — समीक्षा · canonical header · परिवादी/"
                           "आरोपीगण · संज्ञान-समन-दण्ड प्रार्थना · द्विभाषी · विष्णु जी की Priyanka boudh फाइलिंग से अक्षरशः · reviewed: false")
