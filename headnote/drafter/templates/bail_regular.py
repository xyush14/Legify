"""Regular bail — Section 483 BNSS / Section 439 CrPC (Sessions; §480/437 Magistrate).

His #1 filing type (208 in the corpus). Same treatment as cheque_138: the canonical
pixel-exact header (`_doc_header.render_header`) + the point-wise body reproduced
**verbatim from his real filed §483 bail** (benchmark: "439 _ 34(2)" / Ankul Kanjar) +
**bilingual** (Hindi primary, English mirror). No LLM writes any text.

His verbatim skeleton: title + "no other application pending" recital · आपराधिक रिकॉर्ड
(antecedents) table · P1 FIR particulars + arrest + judicial custody · P2 prior §480
Magistrate bail rejected (successive) · P3 innocence/false implication · [facts] ·
[parity] · breadwinner · [≤7yr Antil] · not death/life (triable) · permanent resident /
no flight · trial delay + will comply · closer → prayer (केस डायरी मय कैफियत तलब कर …
उचित प्रतिभूति) → sig (—बन्दी आवेदक).

§480 Magistrate variant: same body, court = JMFC, title धारा 480, drop the prior-§480 para.
HC successive: adds the prior-bail-history table + the Zeba-Khan disclosure block (TODO).
No case law in the body except his own verbatim in-body cite for the ≤7yr toggle.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page


def _esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], placeholder: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{placeholder}</span>'


def _sections(s) -> str:
    if isinstance(s, (list, tuple)):
        return ", ".join(_esc(x) for x in s if str(x).strip()) or "________"
    return _esc(s) if s and str(s).strip() else "________"


def _custody_phrase(arrest: Optional[str]) -> str:
    """Approximate custody duration from arrest date to today, in court Hindi."""
    if not arrest:
        return "काफी समय"
    for fmt in ("%d.%m.%Y", "%d-%m-%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(str(arrest).strip(), fmt).date()
            days = (date.today() - d).days
            if days >= 365:
                return f"लगभग {days // 365} वर्ष से अधिक"
            if days >= 30:
                return f"लगभग {days // 30} माह"
            return f"{max(days, 0)} दिन"
        except ValueError:
            continue
    return "काफी समय"


CITE_AT_HEARING = [
    {"case": "Satender Kumar Antil v. CBI (2022) 10 SCC 51",
     "point": "Bail categories & guidelines; bail the rule. [his ≤7yr toggle cites this in body]",
     "verified": False},
    {"case": "Sanjay Chandra v. CBI (2012) 1 SCC 40",
     "point": "Bail is the rule, jail the exception; pre-trial detention not punitive.",
     "verified": False},
    {"case": "Prasanta Kumar Sarkar v. Ashis Chatterjee (2010) 14 SCC 496",
     "point": "The structural factors a bail court weighs.", "verified": False},
]


def _antecedents_hi(rows):
    out = ['<p class="cb-prelude">आपराधिक रिकॉर्ड का विवरण ः—</p>',
           '<table class="cb-table"><tr><th>क्र.</th><th>अप.क्र.</th><th>धारा</th>'
           '<th>थाना</th><th>जिला</th><th>परिणाम</th></tr>']
    if rows:
        for i, r in enumerate(rows, 1):
            out.append(f'<tr><td>{i}</td><td>{_esc(r.get("crime_no",""))}</td>'
                       f'<td>{_esc(r.get("sections",""))}</td><td>{_esc(r.get("ps",""))}</td>'
                       f'<td>{_esc(r.get("district",""))}</td><td>{_esc(r.get("result",""))}</td></tr>')
    else:
        out.append('<tr><td>1</td><td>निल</td><td>निल</td><td>निल</td><td>निल</td><td>निल</td></tr>')
    out.append('</table>')
    return "\n".join(out)


# =====================================================================  HINDI

def render_hi(a: dict) -> str:
    a = a or {}
    today = date.today()
    is_magistrate = (a.get("section") or "483") == "480"
    sec_title = "धारा 480 भा.ना.सु.सं. (437 दं.प्र.सं.)" if is_magistrate else "धारा 483 भा.ना.सु.सं. (439 दं.प्र.सं.)"
    default_court = ("न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, ............ (________)"
                     if is_magistrate else "न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (________)")
    app_ord = a.get("application_ordinal") or "प्रथम"

    ps = _ph(a.get("police_station"), "थाना")
    district = _ph(a.get("district"), "जिला")
    state = a.get("state_name") or "________"
    fir = _ph(a.get("fir_number"), "..../....")
    secs = _sections(a.get("sections"))
    arrest = _ph(a.get("arrest_date"), "..........")
    custody_court = a.get("custody_court") or "जे.एम.एफ.सी."
    occupation = a.get("applicant_occupation") or "मजदूरी"

    hdr = render_header({
        "side_label": a.get("side_label") or "बन्दी की ओर से",
        "court_name": a.get("court_name") or default_court,
        "case_code": "प्रकरण क्रमांक", "case_number": a.get("case_number") or "",
        "case_year": a.get("case_year") or str(today.year), "case_suffix": "जमानत आवेदन",
        "applicant_label": "आवेदक",
        "applicant_desc": [
            f'{_ph(a.get("applicant_name"), "नाम")} पुत्र श्री {_ph(a.get("applicant_father"), "पिता")},',
            f'आयु— {_ph(a.get("applicant_age"), "..")} वर्ष, व्यवसाय— {_esc(occupation)},',
            f'निवासी— <u>{_ph(a.get("applicant_address"), "पता")}</u>,',
            f'थाना {ps} जिला {district} ({_esc(state)})',
        ],
        "respondent_label": "अनावेदक",
        "respondent_desc": [
            f'{_esc(state)} शासन द्वारा पुलिस थाना {ps}',
            f'जिला {district} ({_esc(state)})',
        ],
        "versus": "बनाम",
        "title_line": f"{_esc(app_ord)} जमानत आवेदन पत्र अन्तर्गत {sec_title}",
    })

    g = a.get("grounds") or {}
    facts = a.get("facts_narrative") or ""
    co_accused = a.get("co_accused_note") or ""

    P = []
    P.append(
        f'यहकि, पुलिस थाना {ps} जिला {district} द्वारा प्रार्थी के विरुद्ध एक अपराध, अपराध '
        f'क्रमांक— {fir} अन्तर्गत धारा {secs} का मिथ्या आधारों पर पंजीवद्ध कर लिया है, जिसमें '
        f'प्रार्थी को गिरफ़तार कर दिनांक {arrest} को माननीय {_esc(custody_court)} न्यायालय के '
        f'समक्ष प्रस्तुत कर न्यायिक अभिरक्षा में भेजा गया है।'
    )
    if not is_magistrate and a.get("prior_480_rejected", True):
        P.append(
            f'यहकि, प्रार्थी का धारा 480 भा.ना.सु.सं. का आवेदन माननीय न्यायिक दण्डाधिकारी '
            f'प्रथम श्रेणी {_ph(a.get("magistrate_city"), "________")} '
            f'द्वारा दिनांक {_ph(a.get("prior_480_date"), "..........")} को निरस्त किया जा '
            f'चुका है।'
        )
    P.append(
        'यहकि, प्रार्थी द्वारा कोई अपराध कारित नहीं किया गया है, न ही प्रार्थी का किसी अपराध '
        'से प्रत्यक्ष अथवा परोक्ष सम्बन्ध है। प्रार्थी को मिथ्या तथ्यों के आधार पर आरोपी बनाया '
        'गया है।'
    )
    if facts.strip():
        for chunk in [c.strip() for c in facts.split("\n\n") if c.strip()]:
            P.append(f'यहकि, {_esc(chunk)}')
    if g.get("parity") and co_accused.strip():
        P.append(
            f'यहकि, प्रकरण के सहअभियुक्त {_esc(co_accused)} प्रार्थी का प्रकरण सहअभियुक्त से '
            f'भिन्न नहीं है; समानता के सिद्धान्त पर प्रार्थी भी जमानत का पात्र है।'
        )
    if g.get("breadwinner", True):
        P.append(
            f'यहकि, प्रार्थी पेशे से {_esc(occupation)} है तथा अपने परिवार का भरण पोषण करने '
            f'वाला एकमात्र व्यक्ति है। प्रार्थी को यदि कारागार में और अधिक समय तक रखा गया तो '
            f'उसके भविष्य एवं परिवार के भरण पोषण पर विपरीत प्रभाव पड़ेगा।'
        )
    if g.get("long_custody") and a.get("arrest_date"):
        P.append(
            f'यहकि, प्रार्थी दिनांक {arrest} से न्यायिक अभिरक्षा में निरुद्ध है तथा उसे निरोध '
            f'में रहते हुये {_custody_phrase(a.get("arrest_date"))} का समय हो चुका है।'
        )
    if g.get("offence_upto_7yr"):
        P.append(
            'यहकि, प्रार्थी के विरुद्ध पंजीवद्ध अपराध 07 वर्ष से अधिक के कारावास से दण्डनीय '
            'नहीं है; ऐसी स्थिति में सतेन्द्र कुमार अंटिल बनाम सेन्ट्रल ब्यूरो ऑफ '
            'इन्वेस्टिगेशन (2022) 10 एस.सी.सी. 51 के न्यायदृष्टान्त के अनुसार प्रार्थी जमानत '
            'का अधिकारी है।'
        )
    if g.get("woman_sick"):
        P.append(
            'यहकि, प्रार्थिनी महिला/अस्वस्थ/वृद्ध होने के कारण विशेष रियायत की पात्र है।'
        )
    for c in (a.get("custom_grounds") or []):
        if c and str(c).strip():
            P.append(f'यहकि, {_esc(c)}')
    P.append(
        'यहकि, प्रार्थी पर अधिरोपित अपराध आजीवन कारावास एवं मृत्यु दण्ड से दण्डनीय न होकर '
        'माननीय न्यायालय के समक्ष विचारण योग्य है।'
    )
    P.append(
        'यहकि, प्रार्थी उपरोक्त पते का स्थाई निवासी है; जमानत का लाभ दिया जाने पर प्रार्थी के '
        'कहीं भाग कर जाने की एवं अभियोजन साक्ष्य को प्रभावित किये जाने की कोई संभावना नहीं है।'
    )
    P.append(
        'यहकि, प्रार्थी के प्रकरण में समय लगने की संभावना से इंकार नहीं किया जा सकता। प्रार्थी '
        'जमानत पर रिहा किया जाता है तो न्यायालय द्वारा अधिरोपित शर्तों का विधिवत पालन करता '
        'रहेगा तथा प्रत्येक पेशी पर माननीय न्यायालय के समक्ष उपस्थित रहेगा।'
    )
    P.append('यहकि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।')

    out = [hdr, '<div class="doc-body">']
    out.append(
        '<p class="cb-prelude">आवेदक का इस आशय का अन्य कोई आवेदन माननीय उच्च न्यायालय या '
        'अन्य किसी न्यायालय में न तो लंबित है और ना ही निरस्त हुआ है।</p>'
    )
    out.append(_antecedents_hi(a.get("antecedents") or []))
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append('<p class="cb-prelude">प्रार्थी की ओर से प्रार्थना पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(
        f'अतः श्रीमान न्यायालय से प्रार्थना है कि प्रार्थी की ओर से प्रस्तुत आवेदन पत्र '
        f'स्वीकार कर पुलिस थाना {ps} जिला {district} से अपराध क्रमांक— {fir} की केस डायरी मय '
        f'कैफियत तलब कर प्रार्थी को उचित प्रतिभूति पर रिहा किये जाने का आदेश प्रदान करने की '
        f'कृपा करें।'
    )
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांक: {_ph(a.get("filing_date"), today.strftime("%d/%m/%Y"))}</div></div>')
    out.append('<div class="r"><div>प्रार्थी</div>')
    out.append(f'<div>{_ph(a.get("applicant_name"), "आवेदक का नाम")} — बन्दी आवेदक</div>')
    out.append('<div style="margin-top:10pt">द्वारा अभिभाषक</div>')
    out.append(f'<div>({_ph(a.get("advocate_name"), "अभिभाषक")}) — एडवोकेट</div>')
    out.append('</div></div>')
    out.append('</div>')
    return "\n".join(out)


# ===================================================================  ENGLISH

def render_en(a: dict) -> str:
    a = a or {}
    today = date.today()
    is_magistrate = (a.get("section") or "483") == "480"
    sec_title = ("SECTION 480 BNSS, 2023 (SECTION 437 CrPC)" if is_magistrate
                 else "SECTION 483 BNSS, 2023 (SECTION 439 CrPC)")
    app_ord = a.get("application_ordinal_en") or "FIRST"
    ps = _ph(a.get("police_station"), "P.S.")
    district = _ph(a.get("district"), "district")
    state = a.get("state_name") or "________"
    fir = _ph(a.get("fir_number"), "..../....")
    secs = _sections(a.get("sections"))
    arrest = _ph(a.get("arrest_date"), "..........")
    occupation_en = a.get("applicant_occupation_en") or "a daily-wage labourer"

    hdr = render_header({
        "side_label": "On behalf of the Applicant",
        "court_name": a.get("court_name_en") or a.get("court_name") or (
            "Court of the Judicial Magistrate First Class, ............ (________)" if is_magistrate
            else "Court of the Sessions Judge, ............ (________)"),
        "case_code": "Bail Application", "case_number": a.get("case_number") or "",
        "case_year": a.get("case_year") or str(today.year),
        "applicant_label": "Applicant",
        "applicant_desc": [
            f'{_ph(a.get("applicant_name"), "name")}, S/o {_ph(a.get("applicant_father"), "father")},',
            f'aged {_ph(a.get("applicant_age"), "..")} yrs, occupation {_esc(a.get("applicant_occupation") or "labour")},',
            f'R/o <u>{_ph(a.get("applicant_address"), "address")}</u>,',
            f'P.S. {ps}, District {district} ({_esc(state)})',
        ],
        "respondent_label": "Respondent",
        "respondent_desc": [f'State of {_esc(state)} through Police Station {ps},', f'District {district}'],
        "versus": "Versus",
        "title_line": f"{app_ord} APPLICATION FOR BAIL UNDER {sec_title}",
    })

    g = a.get("grounds") or {}
    facts = a.get("facts_narrative") or ""
    co_accused = a.get("co_accused_note_en") or a.get("co_accused_note") or ""

    P = []
    P.append(f'That Police Station {ps}, District {district}, has registered a false case, Crime '
             f'No. {fir} under {secs}, against the applicant, who was arrested and remanded to '
             f'judicial custody on {arrest}.')
    if not is_magistrate and a.get("prior_480_rejected", True):
        P.append(f'That the applicant\'s bail application under Section 480 BNSS was rejected by the '
                 f'learned JMFC, {_ph(a.get("magistrate_city"), "____")}, on '
                 f'{_ph(a.get("prior_480_date"), "..........")}.')
    P.append('That the applicant has committed no offence and has no connection, direct or indirect, '
             'with any offence; he has been falsely implicated.')
    if facts.strip():
        for chunk in [c.strip() for c in facts.split("\n\n") if c.strip()]:
            P.append(f'That {_esc(chunk)}')
    if g.get("parity") and co_accused.strip():
        P.append(f'That {_esc(co_accused)} The applicant\'s case is not distinguishable from that of '
                 f'the co-accused; on parity, he too is entitled to bail.')
    if g.get("breadwinner", True):
        P.append('That the applicant is the sole breadwinner of his family; continued incarceration '
                 'would gravely prejudice his future and his family\'s sustenance.')
    if g.get("long_custody") and a.get("arrest_date"):
        P.append(f'That the applicant has been in judicial custody since {arrest} and his continued '
                 f'detention is no longer necessary.')
    if g.get("offence_upto_7yr"):
        P.append('That the alleged offence is not punishable with imprisonment exceeding seven years '
                 'and, per Satender Kumar Antil v. CBI (2022) 10 SCC 51, the applicant is entitled to bail.')
    for c in (a.get("custom_grounds") or []):
        if c and str(c).strip():
            P.append(f'That {_esc(c)}')
    P.append('That the offence alleged is not punishable with death or imprisonment for life and is '
             'triable by this Hon\'ble Court.')
    P.append('That the applicant is a permanent resident of the above address; there is no apprehension '
             'of flight or of tampering with prosecution evidence.')
    P.append('That the trial is likely to take time; if released, the applicant shall abide by all '
             'conditions imposed and attend on every date of hearing.')
    P.append('That further arguments shall be advanced orally at the time of hearing.')

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">That no other bail application of the applicant is pending or '
               'has been rejected before the Hon\'ble High Court or any other court.</p>')
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append('<p class="cb-prelude">The applicant most respectfully submits as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'It is therefore most respectfully prayed that this Hon\'ble Court may be pleased to '
               f'allow the application, call for the case diary in Crime No. {fir} at P.S. {ps}, and '
               f'release the applicant on bail on such terms as the Court deems fit.')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), today.strftime("%d/%m/%Y"))}</div></div>')
    out.append('<div class="r"><div>Applicant</div>')
    out.append(f'<div>{_ph(a.get("applicant_name"), "applicant")} — Applicant (in custody)</div>')
    out.append('<div style="margin-top:10pt">Through Counsel</div>')
    out.append(f'<div>({_ph(a.get("advocate_name"), "advocate")}) — Advocate</div>')
    out.append('</div></div>')
    out.append('</div>')
    return "\n".join(out)


# =====================================================================  SAMPLE
SAMPLE = {
    "section": "483",
    "court_name": "न्यायालय माननीय सत्र न्यायाधीश महोदय, ग्वालियर (म.प्र.)",
    "court_name_en": "Court of the Sessions Judge, Gwalior (M.P.)",
    "case_number": "", "case_year": "2025", "application_ordinal": "प्रथम",
    "applicant_name": "क ख", "applicant_father": "____", "applicant_age": "21",
    "applicant_occupation": "मजदूरी", "applicant_occupation_en": "a daily-wage labourer",
    "applicant_address": "ग्राम ____, बरई तिघरा", "police_station": "पनिहार",
    "district": "ग्वालियर", "state_name": "म.प्र.",
    "fir_number": "119/2025", "sections": ["34(2) आबकारी अधिनियम"],
    "arrest_date": "10.12.2025", "custody_court": "जे.एम.एफ.सी.",
    "prior_480_rejected": True, "magistrate_city": "ग्वालियर", "prior_480_date": "10.12.2025",
    "grounds": {"breadwinner": True, "parity": False, "long_custody": False, "offence_upto_7yr": False},
    "antecedents": [],
    "filing_date": "12/12/2025", "advocate_name": "____",
}


# =====================================================================  review
def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    banner = (
        '<b>समीक्षा — प्रथम जमानत आवेदन पत्र अन्तर्गत धारा 483 भा.ना.सु.सं. (439 दं.प्र.सं.) — regular bail</b><br>'
        'नमूना (काल्पनिक) · संरचना विष्णु जी की वास्तविक §483 बेल फाइलिंग से अक्षरशः · canonical header + '
        'point-wise body + आपराधिक रिकॉर्ड तालिका · द्विभाषी (हिन्दी + English) · कोई AI-लिखित पाठ नहीं · '
        'समीक्षा हेतु प्रस्ताव (reviewed: false) · नीचे: हिन्दी प्रति, फिर अंग्रेजी प्रति।'
    )
    return doc_page([render_hi(d), render_en(d)], banner=banner)
