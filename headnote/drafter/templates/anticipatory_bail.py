"""Anticipatory Bail Application — Section 482 BNSS / Section 438 CrPC.

Pre-arrest bail before the Sessions Court / High Court. A deterministic builder
reproducing — verbatim — the structure and language of Vishnu ji's real filed
anticipatory application (benchmark: "438__ 482 - Krishna ojha", a §482 BNSS /
438 CrPC matter). The fixed legal language is hard-coded from his filing; only
client variables + the facts/apprehension narrative fill in. No LLM writes any
text.

Verbatim notes from the source filing (do not "improve" these):
  - Title is `<क्रम> जमानत आवेदन पत्र अन्तर्गत धारा 482 भा.ना.सु.सं./438 दं.प्र.सं.`
    — he does NOT write "अग्रिम" in the title; section is BNSS/CrPC with a slash.
  - Grounds open with `यहकि,` (solid); parties separated by `बनाम`; party label
    sits to the RIGHT of the descriptor.
  - The ≤7-year ground cites **Arnesh Kumar** and **Satender Kumar Antil** BY NAME
    in the body — this is reproduced verbatim from his filing (he files it), so
    it is kept in the body (gated to the ≤7yr toggle), NOT moved to cite-at-hearing.
  - Prayer flows directly ("अतः…") with NO "प्रार्थना" heading and asks the court
    to call the case diary ("केस डायरी मय कैफियत तलब कर") and release on
    "उचित अग्रिम प्रतिभूति".

Same render contract + CSS classes as the other /draft/* templates.
"""
from __future__ import annotations

from datetime import date
from typing import Optional


# ----------------------------------------------------------- helpers

HINDI_ORDINAL = ["", "प्रथम", "द्वितीय", "तृतीय", "चतुर्थ", "पंचम", "षष्ठ", "सप्तम"]


def _esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], placeholder: str = "............") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{placeholder}</span>'


def _sections_str(sections) -> str:
    if isinstance(sections, (list, tuple)):
        return ", ".join(_esc(s) for s in sections if str(s).strip()) or "..............."
    return _esc(sections) if sections and str(sections).strip() else "..............."


def _ordinal_hi(n: int) -> str:
    return HINDI_ORDINAL[n] if 0 < n < len(HINDI_ORDINAL) else f"{n}वाँ"


# ----------------------------------------------------------- candidate judgments
# The ≤7-year ground in render_hi reproduces Vishnu ji's verbatim in-body citation
# of the first two. Listed here too for the hearing. Verify on Indian Kanoon / SCC.
CITE_AT_HEARING = [
    {"case": "Arnesh Kumar v. State of Bihar (2014) 8 SCC 273",
     "point": "Arrest not automatic for offences punishable up to 7 years (§35 BNSS / §41A CrPC). [cited in body — from Vishnu ji's filing]",
     "verified": False},
    {"case": "Satender Kumar Antil v. CBI (2022) 10 SCC 51",
     "point": "Bail categories & guidelines; bail the rule. [cited in body — from Vishnu ji's filing]",
     "verified": False},
    {"case": "Gurbaksh Singh Sibbia v. State of Punjab (1980) 2 SCC 565",
     "point": "Anticipatory bail to be interpreted liberally; no rigid limits.",
     "verified": False},
    {"case": "Sushila Aggarwal v. State (NCT of Delhi) (2020) 5 SCC 1",
     "point": "Anticipatory bail need not be time-bound; can continue till trial.",
     "verified": False},
]


# ----------------------------------------------------------- main render (Hindi)

def render_hi(a: dict) -> str:
    a = a or {}

    # ---- court header ----
    court_name = a.get("court_name") or "न्यायालय माननीय प्रधान सत्र न्यायाधीश महोदय, ............ (म.प्र.)"
    case_number = a.get("case_number") or ""
    case_year = a.get("case_year") or str(date.today().year)

    # ---- section (BNSS-first, CrPC after a slash — his house style) ----
    section_title = a.get("section_title") or "धारा 482 भा.ना.सु.सं./438 दं.प्र.सं."
    app_number = int(a.get("application_number") or 1)
    app_number_hi = _ordinal_hi(app_number)

    # ---- applicant ----
    name = a.get("applicant_name") or ""
    father = a.get("applicant_father") or ""
    age = a.get("applicant_age") or ""
    occupation = a.get("applicant_occupation") or ""
    address = a.get("applicant_address") or ""

    # ---- non-applicant / FIR ----
    state_name = a.get("state_name") or "म.प्र."
    ps_name = a.get("police_station") or ""
    district = a.get("district") or ""
    fir_number = a.get("fir_number") or ""
    sections = a.get("sections") or []

    # ---- narrative ----
    facts_narrative = a.get("facts_narrative") or ""
    apprehension_reason = a.get("apprehension_reason") or ""
    co_accused_note = a.get("co_accused_note") or ""   # parity (case-specific)

    # ---- antecedents (criminal record) — list of dict rows, else a 'निल' row ----
    antecedents = a.get("antecedents") or []

    # ---- grounds (reviewed toggles; always default ON, conditionals OFF) ----
    g = a.get("grounds") or {}
    custom_grounds = a.get("custom_grounds") or []

    # ---- signature ----
    filing_date = a.get("filing_date") or date.today().strftime("%d/%m/%Y")
    advocate_name = a.get("advocate_name") or ""

    sec_str = _sections_str(sections)
    out: list[str] = ['<div class="bail-doc bail-doc--hi">']

    # --- HEADER ---
    out.append('<div class="bd-header">')
    out.append(f'<h1 class="bd-court">{_esc(court_name)}</h1>')
    caseno = f'{_ph(case_number, ".........")}'
    if case_year:
        caseno += f'/{_esc(case_year)}'
    out.append(f'<div class="bd-caseno">प्रकरण क्रमांक— {caseno}</div>')
    out.append('</div>')

    # --- PARTIES (descriptor left, label to the RIGHT — his format) ---
    out.append('<div class="bd-parties">')
    out.append(
        f'<div class="bd-party"><div class="bd-party-detail">'
        f'{_ph(name, "नाम")} पुत्र श्री {_ph(father, "पिता का नाम")}, '
        f'आयु— {_ph(age, "..")} वर्ष, व्यवसाय— {_ph(occupation, "व्यवसाय")}, '
        f'निवासी— {_ph(address, "पता")}, जिला {_ph(district, "जिला")} ({_esc(state_name)})'
        f'</div><span class="bd-party-dots">———</span>'
        f'<span class="bd-party-label">आवेदक</span></div>'
    )
    out.append('<div class="bd-versus">बनाम</div>')
    out.append(
        f'<div class="bd-party"><div class="bd-party-detail">'
        f'{_esc(state_name)} शासन द्वारा पुलिस थाना {_ph(ps_name, "थाना")} '
        f'जिला {_ph(district, "जिला")} ({_esc(state_name)})'
        f'</div><span class="bd-party-dots">———</span>'
        f'<span class="bd-party-label">अनावेदक</span></div>'
    )
    out.append('</div>')

    # --- APPLICATION TITLE (no "अग्रिम" in the title — verbatim) ---
    out.append(
        f'<h2 class="bd-app-title">{_esc(app_number_hi)} जमानत आवेदन पत्र '
        f'अन्तर्गत {_esc(section_title)}</h2>'
    )

    # --- "no other application pending" recital (flows under the title) ---
    recital = (
        'आवेदक का इस आशय का अन्य कोई आवेदन माननीय उच्च न्यायालय या अन्य किसी '
        'न्यायालय में न तो लंबित है और ना ही निरस्त हुआ है।'
    )
    if co_accused_note.strip():
        recital += f' {_esc(co_accused_note)}'
    out.append(f'<p class="bd-prelude">{recital}</p>')

    # --- antecedents table (आपराधिक रिकॉर्ड) ---
    out.append(_render_antecedents_hi(antecedents))

    # --- salutation + prelude ---
    out.append('<p class="bd-prelude">माननीय न्यायालय,</p>')
    out.append('<p class="bd-prelude">आवेदक की ओर से प्रार्थना पत्र निम्न प्रकार प्रस्तुत है ः—</p>')

    # ============= NUMBERED PARAGRAPHS =============
    out.append('<ol class="bd-paras">')

    # 1 — FIR registration + apprehension of arrest
    appr_tail = (f' तथा {_esc(apprehension_reason)}' if apprehension_reason.strip() else '')
    out.append(
        f'<li><p>यहकि, पुलिस थाना {_ph(ps_name, "थाना")} जिला {_ph(district, "जिला")} में '
        f'एक झूठा अपराध, अपराध क्रमांक— {_ph(fir_number, "..../....")} अन्तर्गत धारा {sec_str} '
        f'का पंजीवद्ध कर लिया है, जिसमें पुलिस द्वारा प्रार्थी को गिरफ्तार करने हेतु '
        f'प्रयास किया जा रहा है, जिससे प्रार्थी की गिरफ्तारी की युक्तियुक्त आशंका '
        f'उत्पन्न हो गई है{appr_tail}।</p></li>'
    )

    # 2 — innocence / false implication
    out.append(
        '<li><p>यहकि, प्रार्थी का किसी अपराध या अपराधी से कोई सम्बन्ध व सरोकार '
        'नहीं है। प्रार्थी को मिथ्या आधारों पर उक्त प्रकरण में झूठा संलिप्त किया '
        'गया है।</p></li>'
    )

    # 3 — facts narrative (allegation vs reality — case-specific)
    if facts_narrative.strip():
        for chunk in [c.strip() for c in facts_narrative.split("\n\n") if c.strip()]:
            out.append(f'<li><p>यहकि, {_esc(chunk)}</p></li>')
    else:
        out.append(
            '<li><p class="ph">[प्रकरण के तथ्य यहाँ लिखें — अभियोजन का आक्षेप एवं '
            'वास्तविकता, झूठा फँसाये जाने का कारण — या FIR अपलोड कर AI से भरवायें]</p></li>'
        )

    # 4 — parity (conditional)
    if g.get("parity") and co_accused_note.strip():
        out.append(
            f'<li><p>यहकि, {_esc(co_accused_note)} प्रार्थी का प्रकरण सहअभियुक्त से '
            f'भिन्न नहीं है, अतः समानता के सिद्धान्त पर प्रार्थी भी जमानत का अधिकारी '
            f'है।</p></li>'
        )

    # 5 — breadwinner (conditional)
    if g.get("sole_breadwinner"):
        out.append(
            '<li><p>यहकि, प्रार्थी अपने परिवार का भरण पोषण करने वाला व्यक्ति है। '
            'प्रार्थी को यदि गिरफ्तार किया गया तो उसके परिवार की आर्थिक स्थिति '
            'दयनीय हो जावेगी।</p></li>'
        )

    # 6 — permanent resident / no flight (always)
    if g.get("respected_resident", True):
        out.append(
            '<li><p>यहकि, प्रार्थी उपरोक्त वर्णित पते का स्थाई निवासी है, जमानत का '
            'लाभ दिया जाने पर प्रार्थी के कहीं भागकर जाने की एवं अभियोजन साक्ष्य को '
            'प्रभावित किये जाने की कोई संभावना नहीं है।</p></li>'
        )

    # 7 — offence ≤ 7 yr — Arnesh Kumar + Satender Antil (verbatim, in body)
    if g.get("offence_upto_7yr"):
        out.append(
            '<li><p>यहकि, प्रार्थी के विरुद्ध पंजीवद्ध अपराध 07 वर्ष से अधिक के '
            'कारावास से दण्डनीय नहीं है। ऐसी स्थिति में अर्नेश कुमार बनाम बिहार '
            'राज्य (2014) 8 एस.सी.सी. 273 एवं सतेन्द्र कुमार अंटिल बनाम सेन्ट्रल '
            'ब्यूरो ऑफ इन्वेस्टिगेशन (2022) 10 एस.सी.सी. 51 के न्यायदृष्टान्त के '
            'अनुसार प्रार्थी जमानत का अधिकारी है।</p></li>'
        )

    if g.get("medical"):
        out.append(f'<li><p>यहकि, प्रार्थी {_esc(g.get("medical"))}</p></li>')

    for custom in custom_grounds:
        if custom and str(custom).strip():
            out.append(f'<li><p>यहकि, {_esc(custom)}</p></li>')

    # 8 — delay + undertaking to comply (always)
    out.append(
        '<li><p>यहकि, प्रार्थी के प्रकरण में समय लगने की संभावना से इन्कार नहीं '
        'किया जा सकता। प्रार्थी अग्रिम जमानत पर रिहा किया जाता है तो न्यायालय '
        'द्वारा दी गई शर्तों का विधिवत पालन करता रहेगा तथा प्रत्येक पेशी पर '
        'माननीय न्यायालय के समक्ष उपस्थित रहेगा।</p></li>'
    )

    # 9 — closer (always)
    out.append('<li><p>यहकि, शेष तर्क बहस के समय मौखिक रूप से निवेदित होंगे।</p></li>')
    out.append('</ol>')

    # --- PRAYER (flows directly; NO heading — verbatim) ---
    out.append('<div class="bd-prayer">')
    out.append(
        f'<p>अतः श्रीमान न्यायालय से प्रार्थना है कि प्रार्थी की ओर से प्रस्तुत आवेदन '
        f'पत्र स्वीकार कर पुलिस थाना {_ph(ps_name, "थाना")} जिला {_ph(district, "जिला")} '
        f'से सम्बन्धित अपराध क्रमांक— {_ph(fir_number, "..../....")} की केस डायरी मय '
        f'कैफियत तलब कर प्रार्थी को उचित अग्रिम प्रतिभूति पर रिहा किये जाने का आदेश '
        f'प्रदान करने की कृपा करें।</p>'
    )
    out.append('</div>')

    # --- SIGNATURE ---
    out.append('<div class="bd-sig">')
    out.append('<div class="bd-sig-left">')
    out.append(f'<div>दिनांकः— {_ph(filing_date, "...........")}</div>')
    out.append('</div>')
    out.append('<div class="bd-sig-right">')
    out.append('<div>प्रार्थी</div>')
    out.append(f'<div class="bd-sig-name">{_ph(name, "आवेदक का नाम")} — आवेदक</div>')
    out.append('<div class="bd-sig-advocate">द्वारा अभिभाषक</div>')
    out.append(f'<div class="bd-sig-advname">({_ph(advocate_name, "अभिभाषक का नाम")}) — एडवोकेट</div>')
    out.append('</div>')
    out.append('</div>')

    out.append('</div>')  # /.bail-doc
    return "\n".join(out)


def _render_antecedents_hi(rows: list) -> str:
    """आपराधिक रिकॉर्ड का विवरण — a 'निल' row when none supplied."""
    out = ['<p class="bd-prelude">आवेदक के परिजन द्वारा दी गई जानकारी के आधार पर '
           'आपराधिक रिकॉर्ड का विवरण ः—</p>']
    out.append('<table class="bd-table">')
    out.append('<tr><th>क्र.</th><th>अप.क्र.</th><th>धारा</th><th>थाना</th>'
               '<th>जिला</th><th>परिणाम</th></tr>')
    if rows:
        for i, r in enumerate(rows, 1):
            out.append(
                f'<tr><td>{i}</td><td>{_esc(r.get("crime_no",""))}</td>'
                f'<td>{_esc(r.get("sections",""))}</td><td>{_esc(r.get("ps",""))}</td>'
                f'<td>{_esc(r.get("district",""))}</td><td>{_esc(r.get("result",""))}</td></tr>'
            )
    else:
        out.append('<tr><td>1</td><td>निल</td><td>निल</td><td>निल</td>'
                   '<td>निल</td><td>निल</td></tr>')
    out.append('</table>')
    return "\n".join(out)


# ----------------------------------------------------------- main render (English)

def render_en(a: dict) -> str:
    """English anticipatory bail — mirrors render_hi for HC English benches."""
    a = a or {}
    court_name = a.get("court_name") or "(name of the Court)"
    name = a.get("applicant_name") or ""
    father = a.get("applicant_father") or ""
    age = a.get("applicant_age") or ""
    occupation = a.get("applicant_occupation") or ""
    address = a.get("applicant_address") or ""
    district = a.get("district") or ""
    state_name = a.get("state_name") or "M.P."
    ps_name = a.get("police_station") or ""
    fir_number = a.get("fir_number") or ""
    sections = a.get("sections") or []
    case_number = a.get("case_number") or ""
    case_year = a.get("case_year") or str(date.today().year)
    app_number = int(a.get("application_number") or 1)
    app_ord = ["", "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH"][min(app_number, 5)]
    facts_narrative = a.get("facts_narrative") or ""
    apprehension_reason = a.get("apprehension_reason") or ""
    co_accused_note = a.get("co_accused_note") or ""
    g = a.get("grounds") or {}
    custom_grounds = a.get("custom_grounds") or []
    filing_date = a.get("filing_date") or date.today().strftime("%d/%m/%Y")
    advocate_name = a.get("advocate_name") or ""
    sec_str = _sections_str(sections)

    out = ['<div class="bail-doc bail-doc--en">']
    out.append('<div class="bd-header">')
    out.append(f'<h1 class="bd-court">{_esc(court_name)}</h1>')
    caseno = f'{_ph(case_number, "....")}'
    if case_year:
        caseno += f' of {_esc(case_year)}'
    out.append(f'<div class="bd-caseno">Case No. {caseno}</div>')
    out.append('</div>')

    out.append('<div class="bd-parties">')
    out.append(
        f'<div class="bd-party"><div class="bd-party-detail">'
        f'{_ph(name, "name")}, S/o {_ph(father, "father")}, aged about {_ph(age, "..")} years, '
        f'occupation {_ph(occupation, "occupation")}, R/o {_ph(address, "address")}, '
        f'District {_ph(district, "district")} ({_esc(state_name)})</div>'
        f'<span class="bd-party-dots">———</span>'
        f'<span class="bd-party-label">Applicant</span></div>'
    )
    out.append('<div class="bd-versus">Versus</div>')
    out.append(
        f'<div class="bd-party"><div class="bd-party-detail">State of {_esc(state_name)} '
        f'through Police Station {_ph(ps_name, "police station")}, District '
        f'{_ph(district, "district")}</div>'
        f'<span class="bd-party-dots">———</span>'
        f'<span class="bd-party-label">Respondent</span></div>'
    )
    out.append('</div>')

    out.append(
        f'<h2 class="bd-app-title">{app_ord} APPLICATION FOR ANTICIPATORY BAIL UNDER '
        f'SECTION 482 BNSS, 2023 (FORMERLY SECTION 438 CrPC, 1973)</h2>'
    )
    out.append('<p class="bd-prelude">That no similar application is pending or has been rejected '
               'before this Hon\'ble Court or before the Hon\'ble Supreme Court of India.</p>')
    out.append('<p class="bd-prelude">May it please the Court,</p>')
    out.append('<p class="bd-prelude">The applicant most respectfully submits as under:—</p>')
    out.append('<ol class="bd-paras">')

    appr_tail = (f', inasmuch as {_esc(apprehension_reason)}' if apprehension_reason.strip() else '')
    out.append(f'<li><p>That a false case, Crime No. {_ph(fir_number, "..../....")} under {sec_str}, '
               f'has been registered against the applicant at Police Station '
               f'{_ph(ps_name, "police station")}, District {_ph(district, "district")}, in which the '
               f'police are seeking to arrest the applicant, giving rise to a reasonable apprehension '
               f'of arrest{appr_tail}.</p></li>')
    out.append('<li><p>That the applicant has no connection with any offence or offender and has been '
               'falsely implicated on baseless grounds.</p></li>')
    if facts_narrative.strip():
        for chunk in [c.strip() for c in facts_narrative.split("\n\n") if c.strip()]:
            out.append(f'<li><p>That {_esc(chunk)}</p></li>')
    else:
        out.append('<li><p class="ph">[State the facts — the allegation vs. the reality and the '
                   'reason for the false implication.]</p></li>')
    if g.get("parity") and co_accused_note.strip():
        out.append(f'<li><p>That {_esc(co_accused_note)} The applicant\'s case is not distinguishable '
                   f'from that of the co-accused; on the principle of parity the applicant too is '
                   f'entitled to bail.</p></li>')
    if g.get("sole_breadwinner"):
        out.append('<li><p>That the applicant is the breadwinner of his family; his arrest would '
                   'reduce the family to dire economic distress.</p></li>')
    if g.get("respected_resident", True):
        out.append('<li><p>That the applicant is a permanent resident of the abovementioned address; '
                   'there is no apprehension of flight or of tampering with prosecution evidence.</p></li>')
    if g.get("offence_upto_7yr"):
        out.append('<li><p>That the alleged offence is not punishable with imprisonment exceeding '
                   'seven years, and, per Arnesh Kumar v. State of Bihar (2014) 8 SCC 273 and Satender '
                   'Kumar Antil v. CBI (2022) 10 SCC 51, the applicant is entitled to bail.</p></li>')
    if g.get("medical"):
        out.append(f'<li><p>That the applicant {_esc(g.get("medical"))}</p></li>')
    for c in custom_grounds:
        if c and str(c).strip():
            out.append(f'<li><p>That {_esc(c)}</p></li>')
    out.append('<li><p>That the trial is likely to take time; if released on anticipatory bail the '
               'applicant shall duly abide by all conditions imposed by the Court and attend on every '
               'date of hearing.</p></li>')
    out.append('<li><p>That further arguments shall be advanced orally at the time of hearing.</p></li>')
    out.append('</ol>')

    out.append('<div class="bd-prayer">')
    out.append(f'<p>It is therefore most respectfully prayed that this Hon\'ble Court may be pleased to '
               f'allow the application, call for the case diary in Crime No. {_ph(fir_number, "..../....")} '
               f'at P.S. {_ph(ps_name, "police station")}, and direct that the applicant be released on '
               f'anticipatory bail on suitable security, in the event of his arrest.</p></div>')

    out.append('<div class="bd-sig"><div class="bd-sig-left">')
    out.append(f'<div>Date: {_ph(filing_date, "..........")}</div></div>')
    out.append('<div class="bd-sig-right"><div>Applicant</div>'
               f'<div class="bd-sig-name">{_ph(name, "applicant")} — Applicant</div>'
               '<div class="bd-sig-advocate">Through Counsel</div>'
               f'<div class="bd-sig-advname">({_ph(advocate_name, "advocate")}) — Advocate</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- benchmark sample
# Genericised, illustrative example (NOT a real client) for the review page —
# modelled on the structure of the "Krishna ojha" §482 filing.
SAMPLE = {
    "court_name": "न्यायालय माननीय प्रधान सत्र न्यायाधीश महोदय, ग्वालियर (म.प्र.)",
    "case_number": "", "case_year": "2026",
    "section_title": "धारा 482 भा.ना.सु.सं./438 दं.प्र.सं.",
    "application_number": 1,
    "applicant_name": "क ख ग", "applicant_father": "य र ल",
    "applicant_age": "19", "applicant_occupation": "विद्यार्थी",
    "applicant_address": "____, गिर्द",
    "state_name": "म.प्र.", "police_station": "____", "district": "ग्वालियर",
    "fir_number": "____/2026",
    "sections": ["110", "296(बी)", "115(2)", "351(2) भा.न्या.सं."],
    "facts_narrative": (
        "प्रार्थी के विरुद्ध यह आक्षेप लगाया गया है कि प्रार्थी ने सहअभियुक्त के साथ "
        "मिलकर मारपीट की है, जबकि वास्तविकता यह है कि फरियादी द्वारा ही प्रार्थी की "
        "मारपीट की गयी और अपने बचाव हेतु यह झूठा अपराध पंजीवद्ध कराया गया है। प्रथम "
        "सूचना रिपोर्ट में प्रार्थी के नाम का कोई उल्लेख नहीं है।"
    ),
    "apprehension_reason": "",
    "co_accused_note": (
        "प्रकरण के सहअभियुक्त ____ का अग्रिम जमानत आवेदन माननीय न्यायालय द्वारा "
        "स्वीकार किया जा चुका है।"
    ),
    "antecedents": [],
    "grounds": {
        "parity": True, "sole_breadwinner": True,
        "respected_resident": True, "offence_upto_7yr": True,
    },
    "filing_date": "23/06/2026", "advocate_name": "____",
}


# ----------------------------------------------------------- review page

def review_page_html(data: Optional[dict] = None) -> str:
    """Read-only sample render for advocate sign-off (no JS)."""
    from headnote.drafter.templates._review_shell import review_shell
    banner = (
        '<b>समीक्षा — धारा 482 भा.ना.सु.सं./438 दं.प्र.सं. अग्रिम जमानत आवेदन</b>'
        '<small>नमूना (काल्पनिक उदाहरण) · संरचना विष्णु जी की वास्तविक §482 फाइलिंग से अक्षरशः · '
        'केवल चर परिवर्तनीय · ≤7 वर्ष आधार में अर्नेश कुमार/सतेन्द्र अंटिल उद्धरण उनकी फाइलिंग से · '
        'समीक्षा हेतु प्रस्ताव (reviewed: false)</small>'
    )
    return review_shell(
        page_title="अग्रिम जमानत आवेदन (धारा 482) — समीक्षा",
        banner_html=banner,
        doc_html=render_hi(data if data is not None else SAMPLE),
    )
