"""Criminal Revision — §438 & §442 BNSS / §397 & §401 CrPC (पुनरीक्षण याचिका).

Canonical-standard builder mirrored VERBATIM from his revision filing (benchmark:
"Revision HC Vikrant singh" — a §126(2) / §19(4) Family-Courts maintenance-order
revision at the High Court). Canonical header + section-labelled body + bilingual.
No LLM writes any text.

Mirror notes:
  • पुनरीक्षणकर्ता (revisionist) vs प्रतिपुनरीक्षणकर्ता (respondent); the revisionist files.
  • Long title NAMES the impugned order: "… विरुद्ध आदेश दिनांक <date> न्यायालय <court>
    द्वारा प्रकरण क्रमांक <no> में <what was decided/rejected>" (optionally सहपठित a
    related provision, e.g. §19(4) Family Courts Act / §126(2) CrPC).
  • Recital: this is the FIRST revision + no other revision pending (one-revision bar)
    + filed WITHIN 90 DAYS of the order (limitation).
  • SECTION LABELS used (unlike discharge): प्रकरण का संक्षिप्त विवरण ः— / पुनरीक्षण याचिका के आधार ः—.
  • Grounds attack legality/propriety (NOT a re-appreciation of evidence); prayer =
    अपास्त (set aside) / modify the impugned order. HC adds an इन्डेक्स + annexure of the order.
  • `why_revisable` toggle = the "intermediate, not interlocutory" averment for
    charge/discharge-order revisions (§397(2) bar); off for final orders (maintenance).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

HINDI_ORDINAL = ["", "प्रथम", "द्वितीय", "तृतीय", "चतुर्थ", "पंचम"]
EN_ORDINAL = ["", "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH"]

CITE_AT_HEARING = [
    {"case": "Amit Kapoor v. Ramesh Chander (2012) 9 SCC 460", "point": "revision/quashing of a charge — uncontroverted-allegations test", "verified": False},
    {"case": "Madhu Limaye v. State of Maharashtra (1977) 4 SCC 551", "point": "charge/discharge order is intermediate, not interlocutory — revisable", "verified": False},
    {"case": "Amar Nath v. State of Haryana (1977) 4 SCC 137", "point": "restricted meaning of 'interlocutory order' (§397(2))", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _ord_hi(n):
    return HINDI_ORDINAL[n] if 0 < n < len(HINDI_ORDINAL) else f"{n}वाँ"


def _cfg(court):
    if court == "sessions":
        return dict(level="sessions", case_code="पुनरीक्षण क्रमांक", case_code_en="Criminal Revision")
    return dict(level="hc", case_code="पुनरीक्षण याचिका क्रमांक", case_code_en="Cr.R.")


def _para_list(facts, grounds):
    out = ['<ol class="cb-paras">']
    out.append('<li class="cb-head">प्रकरण का संक्षिप्त विवरण ः—</li>')
    for p in facts:
        out.append(f'<li>{p}</li>')
    out.append('<li class="cb-head">पुनरीक्षण याचिका के आधार ः—</li>')
    for p in grounds:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    return "\n".join(out)


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "hc"
    c = _cfg(court)
    appno = int(a.get("application_number") or 1)
    state = _esc(a.get("state_name") or "म.प्र.")
    section_title = a.get("section_title") or "धारा 438, 442 भा.ना.सु.सं. (397, 401 दं.प्र.सं.)"
    allied = a.get("allied_section") or ""        # e.g. "धारा 19(4) कुटुम्ब न्यायालय अधिनियम"
    court_below = _ph(a.get("court_below"), "विचारण न्यायालय")
    order_date = _ph(a.get("order_date"), "..........")
    case_below = _ph(a.get("case_below_no"), "..../....")
    order_subject = _ph(a.get("order_subject"), "आवेदन/प्रकरण का निराकरण")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), state) \
        if a.get("court_city") else (a.get("court_name") or "माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर")
    name = a.get("revisionist_name") or ""

    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": c["case_code"],
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "पुनरीक्षणकर्ता",
        "applicant_desc": [
            f'{_ph(name, "नाम")} पुत्र श्री {_ph(a.get("revisionist_father"), "पिता")}, '
            f'आयु— {_ph(a.get("revisionist_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("revisionist_occupation"), "व्यवसाय")},',
            f'निवासी— <u>{_ph(a.get("revisionist_address"), "पता")}</u> ({state})'],
        "respondent_label": "प्रतिपुनरीक्षणकर्ता",
        "respondent_desc": [_ph(a.get("respondent_desc"), "प्रत्यर्थी का विवरण")],
        "versus": "विरुद्ध", "title_line": f"{_ord_hi(appno)} पुनरीक्षण याचिका अन्तर्गत {section_title}",
    })

    allied_p = f' सहपठित {_esc(allied)}' if allied else ''
    out = [hdr, '<div class="doc-body">']
    out.append(f'<p class="cb-prelude" style="text-align:center">{allied_p.strip() and allied_p+" " or ""}विरुद्ध आदेश '
               f'दिनांक {order_date}, न्यायालय {court_below} द्वारा प्रकरण क्रमांक— {case_below} में {order_subject}।</p>')
    out.append(f'<p class="cb-prelude">पुनरीक्षणकर्ता की ओर से यह {_ord_hi(appno)} पुनरीक्षण याचिका है; उक्त के '
               f'अतिरिक्त अन्य कोई पुनरीक्षण याचिका माननीय उच्चतम न्यायालय अथवा माननीय उच्च न्यायालय में न तो '
               f'विचाराधीन है और न ही निराकृत की गई है।</p>')
    out.append('<p class="cb-prelude">पुनरीक्षणकर्ता की ओर से पुनरीक्षण याचिका निम्न प्रकार प्रस्तुत है ः—</p>')

    facts = []
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            facts.append(f'यहकि, {_esc(ch)}')
    else:
        facts.append('<span class="ph">[विचारण न्यायालय ने क्या किया '
                     '— प्रकरण/आवेदन व विवादित आदेश का संक्षिप्त विवरण यहाँ]</span>')
    facts.append(f'यहकि, उपरोक्त आदेश दिनांक {order_date} से व्यथित होकर पुनरीक्षणकर्ता, आदेश दिनांक से 90 दिवस '
                 f'के अन्दर, निम्नलिखित आधारों पर यह पुनरीक्षण याचिका माननीय न्यायालय के समक्ष प्रस्तुत कर रहा है।')

    g = a.get("grounds") or {}
    G = [f'यहकि, विचारण न्यायालय द्वारा पारित आदेश दिनांक {order_date} विधि के विपरीत एवं अनुचित होने से '
         f'अपास्त किये जाने योग्य है।']
    if g.get("why_revisable"):
        G.append('यहकि, विवादित आदेश अन्तरवर्ती (interlocutory) आदेश न होकर मध्यवर्ती आदेश है, जिससे '
                 'पक्षकार के सारवान अधिकार प्रभावित होते हैं; अतः धारा 397(2)/438(2) का वर्जन लागू नहीं होता '
                 'तथा यह आदेश पुनरीक्षणीय है।')
    if (a.get("grounds_narrative") or "").strip():
        for ch in [x.strip() for x in a["grounds_narrative"].split("\n\n") if x.strip()]:
            G.append(f'यहकि, {_esc(ch)}')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'यहकि, {_esc(cu)}')
    G.append('यहकि, अन्य आधार वक्त बहस, अभिलेख उपलब्ध होने पर, मौखिक रूप से निवेदित किये जावेंगे।')

    out.append(_para_list(facts, G))
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः माननीय न्यायालय से निवेदन है कि पुनरीक्षणकर्ता की ओर से प्रस्तुत पुनरीक्षण याचिका स्वीकार '
               f'कर विचारण न्यायालय {court_below} द्वारा प्रकरण क्रमांक— {case_below} में पारित आदेश दिनांक '
               f'{order_date} को अपास्त करने की कृपा करें।')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>प्रार्थी</div><div>{_ph(name, "नाम")} — पुनरीक्षणकर्ता</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('<div class="cb-note">साथ संलग्न (उच्च न्यायालय): इन्डेक्स · विवादित आदेश की प्रमाणित प्रति '
               '(एनेक्जर ए-1) · वकालतनामा। (विलम्ब होने पर धारा 5 परिसीमा अधिनियम का विलम्ब-क्षमा आवेदन।)</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "hc"
    c = _cfg(court)
    appno = int(a.get("application_number") or 1)
    state = _esc(a.get("state_name_en") or "M.P.")
    allied = a.get("allied_section_en") or a.get("allied_section") or ""
    court_below = _ph(a.get("court_below_en") or a.get("court_below"), "trial court")
    order_date = _ph(a.get("order_date"), "..........")
    case_below = _ph(a.get("case_below_no"), "..../....")
    order_subject = _ph(a.get("order_subject_en") or a.get("order_subject"), "the matter")
    name = _ph(a.get("revisionist_name_en") or a.get("revisionist_name"), "revisionist")
    court_name = a.get("court_name_en") or compose_court_name(c["level"], a.get("court_city_en") or a.get("court_city"), state, lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": c["case_code_en"],
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Revisionist",
        "applicant_desc": [f'{name}, S/o {_ph(a.get("revisionist_father_en") or a.get("revisionist_father"), "father")}, '
                           f'aged {_ph(a.get("revisionist_age"), "..")} yrs, R/o '
                           f'{_ph(a.get("revisionist_address_en") or a.get("revisionist_address"), "address")} ({state})'],
        "respondent_label": "Respondent",
        "respondent_desc": [_ph(a.get("respondent_desc_en") or a.get("respondent_desc"), "respondent")],
        "versus": "Versus",
        "title_line": f'{EN_ORDINAL[appno] if appno < len(EN_ORDINAL) else appno} CRIMINAL REVISION UNDER '
                      f'SECTIONS 438 & 442 BNSS, 2023 (SECTIONS 397 & 401 CrPC)',
    })
    g = a.get("grounds") or {}
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    gn = a.get("grounds_narrative_en") or a.get("grounds_narrative") or ""
    out = [hdr, '<div class="doc-body">']
    out.append(f'<p class="cb-prelude" style="text-align:center">'
               + (f'r/w {_esc(allied)}, ' if allied else '')
               + f'against the order dated {order_date} passed by {court_below} in Case No. {case_below} '
               f'{order_subject}.</p>')
    out.append('<p class="cb-prelude">That this is the first revision; no other revision is pending or has been '
               'decided before the Hon\'ble Supreme Court or this Hon\'ble Court; it is filed within 90 days of the order.</p>')
    out.append('<p class="cb-prelude">The revisionist most respectfully submits as under:—</p>')
    facts = []
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            facts.append(f'That {_esc(ch)}')
    else:
        facts.append('[Brief facts — what the court below did and the impugned order.]')
    facts.append(f'That, aggrieved by the order dated {order_date}, the revisionist files this revision within '
                 f'90 days on the following grounds.')
    G = [f'That the order dated {order_date} is contrary to law and improper and is liable to be set aside.']
    if g.get("why_revisable"):
        G.append('That the impugned order is an intermediate (not interlocutory) order affecting substantive '
                 'rights; the bar of §397(2)/§438(2) does not apply and the order is revisable.')
    if gn.strip():
        for ch in [x.strip() for x in gn.split("\n\n") if x.strip()]:
            G.append(f'That {_esc(ch)}')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'That {_esc(cu)}')
    G.append('That further grounds shall be urged orally when the record is available.')
    body = ['<ol class="cb-paras">', '<li class="cb-head">BRIEF FACTS:—</li>']
    for p in facts:
        body.append(f'<li>{p}</li>')
    body.append('<li class="cb-head">GROUNDS OF REVISION:—</li>')
    for p in G:
        body.append(f'<li>{p}</li>')
    body.append('</ol>')
    out.append("\n".join(body))
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may '
               f'be pleased to allow the revision and set aside the order dated {order_date} passed by {court_below} '
               f'in Case No. {case_below}.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Revisionist</div><div>{name}</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("why_revisable", "विवादित आदेश मध्यवर्ती है (आरोप/उन्मोचन — §397(2) वर्जन नहीं)",
             "Impugned order is intermediate (charge/discharge — §397(2) bar n/a)", default=False),
]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः)", "Court name (auto)", required=True, section="court", auto=True),
        F.f("case_number", "पुनरीक्षण क्रमांक", "Revision no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("revisionist_name", "पुनरीक्षणकर्ता का नाम", "Revisionist name", F.NAME, True, "parties"),
        F.f("revisionist_father", "पिता का नाम", "Father", F.NAME, section="parties"),
        F.f("revisionist_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("revisionist_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("revisionist_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("respondent_desc", "प्रत्यर्थी का विवरण", "Respondent (full descriptor)", F.LONGTEXT, True, "parties"),
        F.f("court_below", "विवादित आदेश का न्यायालय", "Court that passed the order", required=True, section="order", ocr="order"),
        F.f("case_below_no", "अधीनस्थ प्रकरण क्रमांक", "Case no. below", required=True, section="order", ocr="order"),
        F.f("order_date", "विवादित आदेश दिनांक", "Impugned order date", F.DATE, True, "order", ocr="order"),
        F.f("order_subject", "आदेश में क्या तय हुआ", "What the order decided/rejected", F.LONGTEXT, True, "order"),
        F.f("allied_section", "सहपठित प्रावधान (यदि कोई)", "Allied provision (if any)", section="order",
            hint="जैसे §19(4) कुटुम्ब न्यायालय अधिनियम / §126(2)"),
        F.f("facts_narrative", "प्रकरण का संक्षिप्त विवरण", "Brief facts", F.LONGTEXT, True, "facts", ocr="order"),
        F.f("grounds_narrative", "पुनरीक्षण के आधार", "Grounds of revision", F.LONGTEXT, True, "grounds"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec(f"revision:{court}", flds, _TOGGLES,
                        variants={"court": ["hc", "sessions"]},
                        companions=["index (इन्डेक्स)", "certified copy of impugned order (annexure)",
                                    "vakalatnama", "§5 condonation app (if time-barred)"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court": "hc", "court_city": "ग्वालियर", "court_city_en": "Gwalior",
    "state_name": "म.प्र.", "state_name_en": "M.P.", "case_number": "____", "case_year": "2025",
    "revisionist_name": "क ख", "revisionist_name_en": "K.", "revisionist_father": "महेन्द्र",
    "revisionist_father_en": "Mahendra", "revisionist_age": "36", "revisionist_occupation": "मजदूरी",
    "revisionist_address": "____, इन्दौर", "revisionist_address_en": "____, Indore",
    "respondent_desc": "श्रीमती य र पत्नी श्री क ख, निवासी— ____, ग्वालियर (म.प्र.)",
    "respondent_desc_en": "Smt. Y., W/o K., R/o ____, Gwalior (M.P.)",
    "court_below": "प्रधान न्यायाधीश, कुटुम्ब न्यायालय, ग्वालियर",
    "court_below_en": "Principal Judge, Family Court, Gwalior",
    "case_below_no": "____/2024", "order_date": "11.04.2025",
    "order_subject": "आवेदन पत्र अन्तर्गत धारा 126(2) दं.प्र.सं. (एकपक्षीय आदेश की पुनर्श्रवण) को निरस्त किया गया",
    "order_subject_en": "rejecting the application under §126(2) CrPC (to set aside the ex-parte order)",
    "allied_section": "धारा 19(4) कुटुम्ब न्यायालय अधिनियम", "allied_section_en": "§19(4) Family Courts Act",
    "facts_narrative": (
        "विचारण न्यायालय द्वारा पुनरीक्षणकर्ता को एकपक्षीय घोषित कर अनावेदिका के धारा 125 दं.प्र.सं. के आवेदन "
        "का निराकरण किया गया, जिसे पुनर्श्रवण हेतु पुनरीक्षणकर्ता ने धारा 126(2) का आवेदन प्रस्तुत किया।\n\n"
        "नियत दिनांक को पुनरीक्षणकर्ता अपरिहार्य कारणवश उपस्थित नहीं हो सका; अधिवक्ता उपस्थित होने से पूर्व ही "
        "आवेदन निरस्त कर दिया गया।"
    ),
    "facts_narrative_en": (
        "the court below decided the respondent's §125 CrPC application ex-parte; the revisionist moved a §126(2) "
        "application to set it aside.\n\n"
        "on the fixed date he could not appear for unavoidable reasons, and the application was dismissed before "
        "his counsel reached the court."
    ),
    "grounds_narrative": (
        "पुनरीक्षणकर्ता की अनुपस्थिति अपरिहार्य थी एवं अधिवक्ता उपस्थित हो गये थे; ऐसी स्थिति में बिना सुनवाई "
        "अवसर दिये कठोर आदेश पारित किया जाना अनुचित है।\n\n"
        "आवेदन निरस्त होने से पुनरीक्षणकर्ता मूल दावे में अपना पक्ष रखने से वंचित होकर न्याय से वंचित हो जाएगा।"
    ),
    "grounds_narrative_en": (
        "the revisionist's absence was unavoidable and counsel had appeared; passing a harsh order without an "
        "opportunity of hearing is improper.\n\n"
        "the dismissal deprives the revisionist of the chance to contest the main claim and of justice."
    ),
    "grounds": {"why_revisable": False},
    "filing_date": "__/05/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="पुनरीक्षण (धारा 438-442 · 397-401) — समीक्षा · canonical header · खण्ड-शीर्षक · "
                           "द्विभाषी · विष्णु जी की Vikrant singh §126(2)/§19(4) फाइलिंग से अक्षरशः · reviewed: false")
