"""Stay application — stay of an impugned order / proceedings pending the main
matter (High Court I.A.). AUTHOR-tier (HC — FLAG for Vishnu). reviewed:false.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = []


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _ov(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


def _doc(a, hi):
    a = a if hi else _ov(a); g = a.get("grounds") or {}
    main = _ph(a.get("main_matter"), "मुख्य प्रकरण" if hi else "the main matter")
    cn = a.get("court_name") or (compose_court_name("hc", a.get("court_city"), "म.प्र." if hi else "M.P.", lang=("hi" if hi else "en")) if a.get("court_city") else ("माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर" if hi else "High Court of M.P., Bench at Gwalior"))
    hdr = render_header({
        "side_label": "", "court_name": cn, "case_code": (a.get("case_code") or ("I.A. क्रमांक" if hi else "I.A. No.")),
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": ("आवेदक" if hi else "Applicant"), "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक" if hi else "applicant")],
        "respondent_label": ("अनावेदक" if hi else "Respondent"), "respondent_desc": [_ph(a.get("respondent_name"), "अनावेदक" if hi else "respondent")],
        "versus": ("बनाम" if hi else "Versus"),
        "title_line": (f"स्थगन आवेदन ({main} में) — विवादित आदेश/कार्यवाही के स्थगन हेतु" if hi else f"APPLICATION FOR STAY (in {main})"),
    })
    P = [(f'यहकि, उपरोक्त {main} माननीय न्यायालय के समक्ष विचाराधीन/लंबित है।' if hi else f'That {main} is pending before this Hon\'ble Court.')]
    for ch in _chunks(a.get("facts_narrative")): P.append((f'यहकि, {_esc(ch)}' if hi else f'That {_esc(ch)}'))
    if not _chunks(a.get("facts_narrative")):
        P.append(('<span class="ph">[विवादित आदेश/कार्यवाही का विवरण एवं स्थगन क्यों आवश्यक — खाली पंक्ति से अलग]</span>' if hi
                  else '<span class="ph">[the impugned order/proceedings and why a stay is needed]</span>'))
    if g.get("prima_facie", True):
        P.append(('यहकि, आवेदक के पक्ष में प्रथम दृष्टया सुदृढ़ प्रकरण है, सुविधा का संतुलन आवेदक के पक्ष में है, '
                  'तथा स्थगन न दिये जाने पर आवेदक को अपूरणीय क्षति होगी।' if hi else
                  'That the applicant has a strong prima facie case, the balance of convenience is in the '
                  'applicant\'s favour, and irreparable injury will result if a stay is not granted.'))
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append((f'यहकि, {_esc(cu)}' if hi else f'That {_esc(cu)}'))
    what = _ph(a.get("stay_of"), "विवादित आदेश/आगामी कार्यवाही" if hi else "the impugned order / further proceedings")
    pray = (f'अतः माननीय न्यायालय से सादर निवेदन है कि {main} के अन्तिम निराकरण तक {what} के '
            f'क्रियान्वयन/संचालन पर रोक (स्थगन) प्रदान करने की कृपा करें।' if hi else
            f'It is therefore most respectfully prayed that, pending final disposal of {main}, the operation of '
            f'{what} be stayed, in the interest of justice.')
    out = [hdr, '<div class="doc-body">', f'<p class="cb-prelude">{("माननीय न्यायालय," if hi else "MAY IT PLEASE THE COURT,")}</p>',
           f'<p class="cb-prelude">{("आवेदक की ओर से स्थगन आवेदन निम्न प्रकार प्रस्तुत है ः—" if hi else "The applicant most respectfully submits as under:—")}</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>{pray}</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>{("दिनांक: " if hi else "Date: ")}{_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदक" if hi else "Applicant")}</div>'
               f'<div>— {("आवेदक" if hi else "Applicant")}</div><div style="margin-top:10pt">{("द्वारा अभिभाषक" if hi else "Through Counsel")}</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता" if hi else "advocate")})</div></div></div></div>')
    return "\n".join(out)


def render_hi(a: dict) -> str: return _doc(a or {}, True)
def render_en(a: dict) -> str: return _doc(a or {}, False)

_TOGGLES = [F.toggle("prima_facie", "प्रथम दृष्टया प्रकरण/संतुलन/क्षति", "Prima facie / balance / injury", default=True)]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "बैंच / जिला", "Bench / District", section="court", hint="लोकेशन से स्वतः → न्यायालय"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "आई.ए. / प्रकरण क्रमांक", "I.A. / case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("main_matter", "मुख्य प्रकरण (रिट/अपील/पुनरीक्षण क्रमांक)", "Main matter (W.P./Appeal/Revision no.)", required=True, section="court"),
        F.f("applicant_name", "आवेदक का नाम", "Applicant name", F.NAME, True, "parties"),
        F.f("respondent_name", "अनावेदक का नाम", "Respondent name", F.NAME, section="parties"),
        F.f("facts_narrative", "विवादित आदेश/कार्यवाही + कारण", "Impugned order/proceedings + reason", F.LONGTEXT, True, "facts",
            hint="क्या स्थगित करना है एवं क्यों — खाली पंक्ति से अलग पैरा"),
        F.f("stay_of", "किसका स्थगन", "Stay of what", section="facts", hint="जैसे: विवादित आदेश दिनांक ____ / आगामी कार्यवाही"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("stay_petition", flds, _TOGGLES, companions=["affidavit", "vakalatnama"])


SAMPLE = {
    "court_city": "ग्वालियर", "main_matter": "रिट याचिका क्रमांक ____/2026",
    "applicant_name": "____", "respondent_name": "म.प्र. राज्य व अन्य",
    "facts_narrative": "प्रत्यर्थी द्वारा पारित विवादित आदेश दिनांक ____ के आधार पर आवेदक के विरुद्ध कार्यवाही की जा रही है, जिससे आवेदक को अपूरणीय क्षति की आशंका है।",
    "stay_of": "विवादित आदेश दिनांक ____",
    "court_city_en": "Gwalior", "main_matter_en": "W.P. No. ____/2026",
    "applicant_name_en": "____", "respondent_name_en": "State of M.P. & ors.",
    "facts_narrative_en": "action is being taken against the applicant pursuant to the impugned order dated ____, threatening irreparable injury to the applicant.",
    "stay_of_en": "the impugned order dated ____",
    "grounds": {"prima_facie": True}, "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="स्थगन आवेदन (HC I.A.) — समीक्षा · AUTHORED (विष्णु जी समीक्षा आवश्यक) · द्विभाषी · reviewed: false")
