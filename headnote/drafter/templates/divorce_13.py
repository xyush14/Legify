"""Divorce — §13 Hindu Marriage Act (Family Court).

AUTHOR-tier (no Vishnu §13 filing in the corpus): drafted from the §13 framework
in his Family-Court house-style (कुटुम्ब न्यायालय, आवेदक/अनावेदिका, यहकि, prayer).
Grounds are toggle-driven (cruelty §13(1)(ia) / desertion §13(1)(ib) / adultery
§13(1)(i)) + the statutory no-collusion/condonation averment. reviewed:false.
No case law in the body (Samar Ghosh etc. → CITE_AT_HEARING).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Samar Ghosh v. Jaya Ghosh (2007) 4 SCC 511", "point": "illustrative categories of mental cruelty", "verified": False},
    {"case": "Naveen Kohli v. Neelu Kohli (2006) 4 SCC 558", "point": "sustained cruelty / irretrievable breakdown context", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_CD = "न्यायालय माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय ............ (म.प्र.)"


def render_hi(a: dict) -> str:
    a = a or {}; g = a.get("grounds") or {}
    pl = _esc(a.get("applicant_label") or "आवेदक"); rl = _esc(a.get("respondent_label") or "अनावेदिका")
    my = _ph(a.get("marriage_year"), "वर्ष ____"); mp = _ph(a.get("marriage_place"), "विवाह स्थान")
    court_name = a.get("court_name") or compose_court_name("family", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "हि.वि.अधि.", "applicant_label": pl,
        "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक का नाम")],
        "respondent_label": rl, "respondent_desc": [_ph(a.get("respondent_name"), "अनावेदिका का नाम")],
        "versus": "बनाम",
        "title_line": "आवेदन पत्र अन्तर्गत धारा 13 हिन्दू विवाह अधिनियम वास्ते विवाह विच्छेद बावत्",
    })
    P = [f'यहकि, {pl} का विवाह {rl} के साथ {my} में हिन्दू रीति-रिवाज एवं विधि-विधान से {mp} में सम्पन्न हुआ था।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[विवाह-पश्चात् के तथ्य — क्रूरता/परित्याग/व्यभिचार के विशिष्ट उदाहरण, '
                 'तिथियों सहित — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("cruelty", True):
        P.append(f'यहकि, {rl} द्वारा {pl} के साथ निरन्तर ऐसा क्रूरतापूर्ण आचरण किया गया जिससे {pl} के मन में '
                 f'यह उचित आशंका उत्पन्न हो गई है कि {rl} के साथ रहना {pl} के लिये हानिकारक एवं अहितकर है — '
                 f'जो धारा 13(1)(ia) हि.वि.अधि. के अधीन क्रूरता की श्रेणी में आता है।')
    if g.get("desertion", False):
        P.append(f'यहकि, {rl} द्वारा बिना किसी उचित कारण के याचिका प्रस्तुति के पूर्व कम से कम दो वर्ष की '
                 f'निरन्तर अवधि से {pl} का अभित्यजन (desertion) किया गया है — जो धारा 13(1)(ib) हि.वि.अधि. के '
                 f'अधीन आधार है।')
    if g.get("adultery", False):
        P.append(f'यहकि, विवाह के पश्चात् {rl} द्वारा {pl} से भिन्न किसी व्यक्ति के साथ स्वेच्छया लैंगिक '
                 f'सम्बन्ध स्थापित किया गया — जो धारा 13(1)(i) हि.वि.अधि. के अधीन आधार है।')
    if g.get("no_collusion", True):
        P.append(f'यहकि, प्रस्तुत याचिका {pl} द्वारा सद्भावपूर्वक प्रस्तुत की जा रही है; पक्षकारों के मध्य कोई '
                 f'दुस्सन्धि (collusion) नहीं है और न ही {pl} द्वारा उपरोक्त आचरण का माफीकरण (condonation) किया '
                 f'गया है।')
    if g.get("jurisdiction", True):
        P.append('यहकि, पक्षकारों का विवाह एवं अन्तिम साथ निवास माननीय न्यायालय की अधिकारिता क्षेत्र में रहा '
                 'है, अतः माननीय न्यायालय को प्रकरण का श्रवणाधिकार है।')
    if g.get("no_other", True):
        P.append(f'यहकि, {pl} द्वारा इस सम्बन्ध में अन्य कोई याचिका किसी न्यायालय में प्रस्तुत अथवा लंबित नहीं है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           f'<p class="cb-prelude">{pl} की ओर से याचिका निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः माननीय न्यायालय से सादर निवेदन है कि {pl} एवं {rl} के मध्य '
               f'सम्पन्न विवाह को विवाह-विच्छेद (decree of divorce) की डिक्री द्वारा विघटित किये जाने की कृपा '
               f'करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदक")}</div><div>— {pl}</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    pl = _esc(a.get("applicant_label_en") or "Petitioner"); rl = _esc(a.get("respondent_label_en") or "Respondent")
    my = _ph(a.get("marriage_year"), "year ____"); mp = _ph(a.get("marriage_place"), "place of marriage")
    court_name = a.get("court_name") or compose_court_name("family", a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": pl, "applicant_desc": [_ph(a.get("applicant_name"), "petitioner")],
        "respondent_label": rl, "respondent_desc": [_ph(a.get("respondent_name"), "respondent")],
        "versus": "Versus", "title_line": "PETITION UNDER SECTION 13 OF THE HINDU MARRIAGE ACT, 1955 "
                                          "— FOR DIVORCE"})
    P = [f'That the {pl} was married to the {rl} in {my} according to Hindu rites and ceremonies at {mp}.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("cruelty", True):
        P.append(f'That the {rl} has so consistently treated the {pl} with cruelty as to cause a reasonable '
                 f'apprehension that it is harmful to live with the {rl} — a ground under Section 13(1)(ia) HMA.')
    if g.get("desertion", False):
        P.append(f'That the {rl} has deserted the {pl} for a continuous period of at least two years immediately '
                 f'preceding the petition, without reasonable cause — a ground under Section 13(1)(ib) HMA.')
    if g.get("adultery", False):
        P.append(f'That after the marriage the {rl} had voluntary sexual intercourse with a person other than '
                 f'the {pl} — a ground under Section 13(1)(i) HMA.')
    if g.get("no_collusion", True):
        P.append(f'That this petition is presented in good faith; there is no collusion between the parties and '
                 f'the {pl} has not condoned the conduct complained of.')
    if g.get("jurisdiction", True):
        P.append('That the marriage and the last residence of the parties fall within the jurisdiction of this '
                 'Hon\'ble Court.')
    if g.get("no_other", True):
        P.append(f'That the {pl} has not filed any other petition in this regard in any court.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           f'<p class="cb-prelude">The {pl} most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that the marriage between the '
               f'{pl} and the {rl} be dissolved by a decree of divorce, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "Petitioner")}</div><div>— {pl}</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("cruelty", "क्रूरता §13(1)(ia)", "Cruelty §13(1)(ia)", default=True),
    F.toggle("desertion", "अभित्यजन §13(1)(ib) (2 वर्ष)", "Desertion §13(1)(ib) (2 yrs)", default=False),
    F.toggle("adultery", "व्यभिचार §13(1)(i)", "Adultery §13(1)(i)", default=False),
    F.toggle("no_collusion", "कोई दुस्सन्धि/माफीकरण नहीं", "No collusion / condonation", default=True),
    F.toggle("jurisdiction", "श्रवणाधिकार पैरा", "Jurisdiction para", default=True),
    F.toggle("no_other", "अन्य कोई याचिका नहीं", "No other petition", default=True),
]


def field_spec(court: str = "family") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → कुटुम्ब न्यायालय"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("applicant_name", "आवेदक का नाम", "Petitioner name", F.NAME, True, "parties"),
        F.f("applicant_label", "आवेदक पक्ष का पद", "Petitioner label", section="parties", default="आवेदक",
            hint="आवेदक (पति) / आवेदिका (पत्नी)"),
        F.f("respondent_name", "अनावेदिका/अनावेदक का नाम", "Respondent name", F.NAME, True, "parties"),
        F.f("respondent_label", "अनावेदक पक्ष का पद", "Respondent label", section="parties", default="अनावेदिका"),
        F.f("marriage_year", "विवाह वर्ष", "Year of marriage", section="facts"),
        F.f("marriage_place", "विवाह स्थान", "Place of marriage", section="facts"),
        F.f("facts_narrative", "विवाह-पश्चात् तथ्य", "Post-marriage facts", F.LONGTEXT, True, "facts",
            hint="क्रूरता/परित्याग/व्यभिचार के विशिष्ट उदाहरण, तिथियों सहित — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_type", "प्रकरण प्रकार", "Case type", section="court", hint="जैसे आर.सी.टी. / सत्रवाद — शीर्षक का प्रकरण-कोड"))
    return F.build_spec("divorce_13", flds, _TOGGLES, companions=["vakalatnama", "marriage proof"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2026", "case_type": "हि.वि.अधि.",
    "applicant_name": "____", "applicant_label": "आवेदक",
    "respondent_name": "श्रीमती ____", "respondent_label": "अनावेदिका",
    "marriage_year": "2018", "marriage_place": "ग्राम ____, जिला ग्वालियर",
    "facts_narrative": (
        "विवाह के कुछ समय पश्चात् से ही अनावेदिका का आचरण आवेदक एवं उसके परिजनों के प्रति क्रूरतापूर्ण रहा तथा "
        "वह आये दिन झगड़ा कर मानसिक प्रताड़ना देती रही।\n\n"
        "अनावेदिका द्वारा आवेदक पर झूठे प्रकरण दर्ज कराने की धमकियाँ दी गईं तथा अन्ततः वह बिना किसी उचित कारण "
        "के आवेदक का घर छोड़कर चली गई।"
    ),
    "court_city_en": "Gwalior", "applicant_name_en": "____", "respondent_name_en": "Smt. ____",
    "applicant_label_en": "Petitioner (husband)", "respondent_label_en": "Respondent (wife)",
    "marriage_place_en": "Vill. ____, Distt. Gwalior",
    "facts_narrative_en": (
        "shortly after the marriage the respondent's conduct towards the petitioner and his family was cruel and "
        "she caused mental harassment by frequent quarrels.\n\n"
        "the respondent threatened to implicate the petitioner in false cases and ultimately left the "
        "petitioner's home without any reasonable cause."
    ),
    "grounds": {"cruelty": True, "desertion": False, "adultery": False, "no_collusion": True,
                "jurisdiction": True, "no_other": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="विवाह विच्छेद §13 HMA — समीक्षा · AUTHORED from §13 framework (कोई mirror नहीं) · "
                           "द्विभाषी · grounds toggle-driven · reviewed: false")
