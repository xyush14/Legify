"""§156(3) CrPC / §175(3) BNSS — Magistrate's direction to the police to register
an FIR and investigate a cognizable offence (the police having refused).

Canonical build, mirror-first from Vishnu ji's real §156(3) filing (benchmark:
"156(3) Hariram dhakad" — §420 cheating, SDM-directed FIR not registered by the
PS). No LLM writes any text.

Mirror notes (do NOT "improve"):
  • Filed as a परिवाद पत्र; आवेदक (complainant) बनाम आरोपी (accused).
  • Body flows as numbered `यहकि`: complainant/offence facts → approached the
    police but no FIR was registered → the act is a cognizable offence u/s X →
    jurisdiction + no-other-complaint averments → prayer to DIRECT the SHO to
    register the FIR and investigate.
  • Priyanka Srivastava v. State of U.P. (2015) 6 SCC 287 makes a SUPPORTING
    AFFIDAVIT mandatory — so the bundle is [application, शपथपत्र] (the affidavit
    swears the facts true and that no other complaint is pending).
  • No case law in the body; candidates in CITE_AT_HEARING.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Priyanka Srivastava v. State of U.P. (2015) 6 SCC 287", "point": "§156(3) application MUST be supported by an affidavit", "verified": False},
    {"case": "Lalita Kumari v. Govt. of U.P. (2014) 2 SCC 1", "point": "registration of FIR is mandatory where information discloses a cognizable offence", "verified": False},
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


_CD = "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)"


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    g = a.get("grounds") or {}
    ps = _ph(a.get("police_station"), "पुलिस थाना")
    secs = _secs(a.get("sections"))
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)

    hdr = render_header({
        "side_label": "",
        "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "परिवाद पत्र",
        "applicant_label": "आवेदक", "applicant_desc": [_ph(a.get("complainant_name"), "आवेदक का नाम")],
        "respondent_label": "आरोपी", "respondent_desc": [_ph(a.get("accused_name"), "आरोपी का नाम")],
        "versus": "बनाम", "title_line": "आवेदन पत्र अन्तर्गत धारा 175(3) भा.ना.सु.सं. (156(3) दं.प्र.सं.)",
    })

    P = []
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts:
            P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[प्रकरण के तथ्य — आवेदक का परिचय तथा आरोपी द्वारा कारित संज्ञेय अपराध का '
                 'विवरण — खाली पंक्ति से अलग पैरा]</span>')
    # police approached but no FIR (the §156(3) trigger)
    pol = _chunks(a.get("police_inaction"))
    if pol:
        for ch in pol:
            P.append(f'यहकि, {_esc(ch)}')
    elif g.get("police_approached", True):
        P.append(f'यहकि, आवेदक द्वारा उपरोक्त संज्ञेय अपराध की सूचना {ps} को लिखित रूप में दी गई, किन्तु आज '
                 f'दिनांक तक {ps} द्वारा कोई प्रथम सूचना रिपोर्ट पंजीवद्ध नहीं की गई और न ही कोई कार्यवाही की गई।')
    if g.get("cognizable_offence", True):
        P.append(f'यहकि, आरोपी द्वारा किया गया उपरोक्त कृत्य धारा {secs} के तहत दण्डनीय होकर संज्ञेय अपराध की '
                 f'श्रेणी में आता है, जिसकी विवेचना किया जाना आवश्यक है।')
    if g.get("jurisdiction", True):
        P.append(f'यहकि, उपरोक्त अपराध {ps} क्षेत्रान्तर्गत घटित हुआ है, अतः माननीय न्यायालय को उक्त प्रकरण '
                 f'का श्रवणाधिकार है।')
    if g.get("no_other_complaint", True):
        P.append('यहकि, आवेदक द्वारा उक्त घटना के सम्बन्ध में भारतवर्ष के किसी भी थाने अथवा न्यायालय में आज '
                 'दिनांक तक इस परिवाद के अतिरिक्त अन्य कोई कार्यवाही नहीं की गई है और न ही कोई प्रकरण लंबित है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'यहकि, {_esc(cu)}')
    report = ' तथा अनुसंधान पश्चात् पुलिस रिपोर्ट माननीय न्यायालय के समक्ष प्रस्तुत करे' if g.get("investigation_and_report", True) else ''

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append('<p class="cb-prelude">आवेदक की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः श्रीमान जी से सादर निवेदन है कि {ps} को इस आशय का निर्देश देने की कृपा करें कि वह आरोपी '
               f'के विरुद्ध धारा {secs} की प्रथम सूचना रिपोर्ट पंजीवद्ध कर{report}।')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{_ph(a.get("complainant_name"), "आवेदक")}</div><div>— आवेदक</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- AFFIDAVIT (HI)
def render_affidavit_hi(a: dict) -> str:
    a = a or {}
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    dep = _ph(a.get("complainant_name"), "शपथकर्ता")
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "परिवाद पत्र",
        "applicant_label": "आवेदक", "applicant_desc": [dep],
        "respondent_label": "आरोपी", "respondent_desc": [_ph(a.get("accused_name"), "आरोपी")],
        "versus": "बनाम", "title_line": "शपथ पत्र",
    })
    out = [hdr, '<div class="doc-body">']
    out.append('<table class="cb-table" style="max-width:62%">'
               f'<tr><td>नाम</td><td>{dep}</td></tr>'
               f'<tr><td>पिता/पति का नाम</td><td>{_ph(a.get("complainant_father"), "पिता")}</td></tr>'
               f'<tr><td>आयु</td><td>{_ph(a.get("complainant_age"), "..")} वर्ष</td></tr>'
               f'<tr><td>व्यवसाय</td><td>{_ph(a.get("complainant_occupation"), "व्यवसाय")}</td></tr>'
               f'<tr><td>निवासी</td><td>{_ph(a.get("complainant_address"), "पता")}</td></tr>'
               '</table>')
    out.append('<p class="cb-prelude">मैं उक्त शपथकर्ता शपथपूर्वक सत्य कथन करता/करती हूँ किः—</p>')
    out.append('<ol class="cb-paras">')
    out.append('<li>यहकि, मुझ शपथकर्ता द्वारा माननीय न्यायालय के समक्ष एक आवेदन पत्र अन्तर्गत धारा 175(3) '
               'भा.ना.सु.सं. (156(3) दं.प्र.सं.) प्रस्तुत किया गया है।</li>')
    out.append('<li>यहकि, उक्त आवेदन पत्र में वर्णित समस्त तथ्य मेरे निजी ज्ञान व विश्वास से सत्य व सही हैं; '
               'इसमें कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।</li>')
    out.append('<li>यहकि, उक्त घटना के सम्बन्ध में शपथकर्ता द्वारा भारतवर्ष के किसी भी थाने अथवा न्यायालय में '
               'आज दिनांक तक अन्य कोई परिवाद/प्रकरण प्रस्तुत अथवा लंबित नहीं है; यह परिवाद प्रथम बार प्रस्तुत '
               'किया जा रहा है।</li>')
    out.append('<li>यहकि, उक्त तथ्यों के समर्थन में यह शपथ पत्र प्रस्तुत है।</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>दिनांक: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">हस्ताक्षर शपथकर्ता</div>'
               f'<div>({dep})</div></div></div>')
    out.append('<div class="cb-block-label">सत्यापन</div>')
    out.append('<p class="cb-prelude">मैं शपथकर्ता शपथपूर्वक सत्यापित करता/करती हूँ कि शपथ पत्र के पद क्रमांक '
               '1 लगायत 4 में दी गई जानकारी मेरे ज्ञान व विश्वास के आधार पर सत्य व सही है, जिसमें कुछ भी असत्य '
               'नहीं है और न ही कुछ छिपाया गया है।</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>दिनांक: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">हस्ताक्षर सत्यापनकर्ता</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def _overlay_en(a: dict) -> dict:
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""):
            a[k[:-3]] = a[k]
    return a


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = _overlay_en(a)
    g = a.get("grounds") or {}
    ps = _ph(a.get("police_station"), "police station")
    secs = _secs(a.get("sections"), sep=" and ")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Complaint No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Complainant", "applicant_desc": [_ph(a.get("complainant_name"), "complainant")],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_name"), "accused")],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 175(3) BNSS, 2023 "
                                          "(FORMERLY SECTION 156(3) CrPC, 1973)",
    })
    P = []
    for ch in _chunks(a.get("facts_narrative")):
        P.append(f'That {_esc(ch)}')
    pol = _chunks(a.get("police_inaction"))
    if pol:
        for ch in pol:
            P.append(f'That {_esc(ch)}')
    elif g.get("police_approached", True):
        P.append(f'That the complainant gave written information of the said cognizable offence to {ps}, but no '
                 f'FIR has been registered and no action has been taken till date.')
    if g.get("cognizable_offence", True):
        P.append(f'That the aforesaid act of the accused is punishable under {secs} and is a cognizable offence '
                 f'warranting investigation.')
    if g.get("jurisdiction", True):
        P.append(f'That the offence was committed within the jurisdiction of {ps}, and this Hon\'ble Court has '
                 f'jurisdiction to entertain the matter.')
    if g.get("no_other_complaint", True):
        P.append('That the complainant has not filed any other complaint or proceeding in respect of this '
                 'incident in any police station or court, nor is any such matter pending.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'That {_esc(cu)}')
    report = ' and submit a police report after investigation' if g.get("investigation_and_report", True) else ''
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append('<p class="cb-prelude">The complainant most respectfully submits as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may '
               f'be pleased to direct {ps} to register an FIR against the accused under {secs}{report}, in the '
               f'interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{_ph(a.get("complainant_name"), "Complainant")}</div><div>— Complainant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def render_affidavit_en(a: dict) -> str:
    a = _overlay_en(a)
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "M.P.", lang="en")
    dep = _ph(a.get("complainant_name"), "deponent")
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Complaint No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Complainant", "applicant_desc": [dep],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_name"), "accused")],
        "versus": "Versus", "title_line": "AFFIDAVIT",
    })
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">I, the deponent above-named, do solemnly affirm and state as under:—</p>')
    out.append('<ol class="cb-paras">')
    out.append('<li>That the deponent has filed an application under Section 175(3) BNSS (formerly Section '
               '156(3) CrPC) before this Hon\'ble Court.</li>')
    out.append('<li>That all the facts stated in the said application are true and correct to the deponent\'s '
               'personal knowledge and belief; nothing material has been concealed or stated falsely.</li>')
    out.append('<li>That in respect of this incident the deponent has not filed any other complaint or '
               'proceeding in any police station or court, nor is any such matter pending; this complaint is '
               'being filed for the first time.</li>')
    out.append('<li>That this affidavit is filed in support of the said facts.</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>Date: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">Signature of the Deponent</div>'
               f'<div>({dep})</div></div></div>')
    out.append('<div class="cb-block-label">VERIFICATION</div>')
    out.append('<p class="cb-prelude">I, the deponent, verify that the contents of paras 1 to 4 are true and '
               'correct to my knowledge and belief; nothing is false and nothing has been concealed.</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>Date: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">Signature of the Verifier</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- BUNDLE
def bundle(a: dict, lang: str = "hi"):
    """[Application, Affidavit] — the affidavit is mandatory (Priyanka Srivastava)."""
    a = a or {}
    hi = lang == "hi"
    g = a.get("grounds") or {}
    R = render_hi if hi else render_en
    AFF = render_affidavit_hi if hi else render_affidavit_en
    sheets, labels = [R(a)], ["परिवाद / आवेदन" if hi else "Application"]
    if g.get("with_affidavit", True):
        sheets.append(AFF(a)); labels.append("शपथ पत्र" if hi else "Affidavit")
    return sheets, labels


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("police_approached", "पुलिस से सम्पर्क — FIR नहीं हुई", "Police approached — no FIR", default=True),
    F.toggle("cognizable_offence", "संज्ञेय अपराध की श्रेणी पैरा", "Cognizable-offence para", default=True),
    F.toggle("jurisdiction", "श्रवणाधिकार पैरा", "Jurisdiction para", default=True),
    F.toggle("no_other_complaint", "अन्य कोई परिवाद नहीं — पैरा", "No other complaint — para", default=True),
    F.toggle("investigation_and_report", "अनुसंधान + पुलिस रिपोर्ट की प्रार्थना", "Investigate + report prayer", default=True),
    F.toggle("with_affidavit", "शपथ पत्र संलग्न (अनिवार्य)", "Attach affidavit (mandatory)", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("complainant_name", "आवेदक (परिवादी) का नाम", "Complainant name", F.NAME, True, "parties"),
        F.f("complainant_father", "पिता/पति का नाम", "Father's/husband's name", F.NAME, section="parties"),
        F.f("complainant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("complainant_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("complainant_address", "पता", "Address", F.ADDRESS, section="parties"),
        F.f("accused_name", "आरोपी का नाम", "Accused name", F.NAME, True, "parties"),
        F.f("police_station", "पुलिस थाना (जहाँ FIR दर्ज हो)", "Police station (to register FIR)", required=True, section="crime"),
        F.f("sections", "अपराध की धाराएं", "Offence sections", F.SECTION_LIST, True, "crime"),
        F.f("facts_narrative", "प्रकरण के तथ्य (संज्ञेय अपराध)", "Facts (cognizable offence)", F.LONGTEXT, True, "facts",
            ocr="order", hint="आवेदक का परिचय + आरोपी द्वारा कारित अपराध — खाली पंक्ति से अलग पैरा"),
        F.f("police_inaction", "पुलिस को सूचना / निष्क्रियता", "Police approached / inaction", F.LONGTEXT, section="facts",
            hint="कब-कब आवेदन दिया, रजिस्टर्ड डाक, कोई कार्यवाही नहीं — रिक्त छोड़ने पर मानक पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_type", "प्रकरण प्रकार", "Case type", section="court", hint="जैसे आर.सी.टी. / सत्रवाद — शीर्षक का प्रकरण-कोड"))
    return F.build_spec("complaint_156", flds, _TOGGLES, companions=["affidavit (mandatory)", "vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2026",
    "complainant_name": "____ धाकड़", "complainant_father": "स्व. श्री ____",
    "complainant_age": "70", "complainant_occupation": "कृषि",
    "complainant_address": "ग्राम ____, जिला ग्वालियर (म.प्र.)",
    "accused_name": "____ सिंह", "police_station": "थाना ____, ग्वालियर",
    "sections": ["420 भा.द.वि."],
    "facts_narrative": (
        "आवेदक उपरोक्त पते पर अपने परिवार सहित निवास करता है तथा आरोपी आवेदक के परिवार का सदस्य है।\n\n"
        "आरोपी द्वारा अवैध लाभ प्राप्त करने के उद्देश्य से आवेदक को राजस्व अपील में मृत दर्शाते हुए कूटरचित "
        "दस्तावेज प्रस्तुत किये गये, जबकि आवेदक जीवित है — यह कृत्य छल की श्रेणी में आता है।"
    ),
    "police_inaction": (
        "अनुविभागीय अधिकारी के आदेश दिनांक ____ के परिपालन में आवेदक द्वारा थाना ____ में लिखित आवेदन एवं "
        "रजिस्टर्ड डाक से सूचना दी गई, किन्तु थाने द्वारा आज दिनांक तक कोई प्रथम सूचना रिपोर्ट पंजीवद्ध नहीं की गई।"
    ),
    "court_city_en": "Gwalior",
    "complainant_name_en": "____ Dhakad", "complainant_father_en": "Late Shri ____",
    "complainant_occupation_en": "agriculture", "complainant_address_en": "Vill. ____, Distt. Gwalior (M.P.)",
    "accused_name_en": "____ Singh", "police_station_en": "P.S. ____, Gwalior",
    "sections_en": ["420 IPC"],
    "facts_narrative_en": (
        "the complainant resides at the above address with his family and the accused is a member of the "
        "complainant's family.\n\n"
        "with a view to gaining illegal advantage, the accused filed forged documents in a revenue appeal "
        "showing the complainant as dead, whereas the complainant is alive — an act amounting to cheating."
    ),
    "police_inaction_en": (
        "in compliance with the SDM's order dated ____, the complainant gave a written application and sent "
        "information by registered post to P.S. ____, but no FIR has been registered till date."
    ),
    "grounds": {"police_approached": True, "cognizable_offence": True, "jurisdiction": True,
                "no_other_complaint": True, "investigation_and_report": True, "with_affidavit": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    bundle_hi, _ = bundle(d, "hi")
    bundle_en, _ = bundle(d, "en")
    return doc_page(bundle_hi + bundle_en,
                    banner="§156(3) / §175(3) पुलिस को FIR निर्देश — समीक्षा · आवेदन + शपथ पत्र · द्विभाषी · "
                           "विष्णु जी की Hariram §420 फाइलिंग से अक्षरशः · reviewed: false")
