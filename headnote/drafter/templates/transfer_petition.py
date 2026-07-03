"""Criminal transfer petition — §447 BNSS (§407 CrPC, High Court) / §448 (§408,
Sessions): transfer a case from one court to another. AUTHOR-tier. reviewed:false.
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
    sessions = (a.get("court") or "hc") == "sessions"
    fromc = _ph(a.get("from_court"), "वर्तमान न्यायालय" if hi else "the present court")
    toc = _ph(a.get("to_court"), "वांछित न्यायालय" if hi else "the desired court")
    title = (("स्थानान्तरण आवेदन अन्तर्गत धारा 448 भा.ना.सु.सं. (408 दं.प्र.सं.)" if sessions else
              "स्थानान्तरण आवेदन अन्तर्गत धारा 447 भा.ना.सु.सं. (407 दं.प्र.सं.)") if hi else
             ("TRANSFER APPLICATION UNDER SECTION 448 BNSS (408 CrPC)" if sessions else
              "TRANSFER APPLICATION UNDER SECTION 447 BNSS (407 CrPC)"))
    lvl = "sessions" if sessions else "hc"
    cn = a.get("court_name") or (compose_court_name(lvl, a.get("court_city"), a.get("state_name") or "", lang=("hi" if hi else "en")) if a.get("court_city") else
        (("न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (________)" if sessions else "माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर") if hi else
         ("Court of the Sessions Judge, ............ (________)" if sessions else "High Court of M.P., Bench at Gwalior")))
    hdr = render_header({
        "side_label": "", "court_name": cn, "case_code": (a.get("case_code") or ("स्थानान्तरण आवेदन क्रमांक" if hi else "Transfer Appln. No.")),
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": ("आवेदक" if hi else "Applicant"), "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक" if hi else "applicant")],
        "respondent_label": ("अनावेदक" if hi else "Respondent"), "respondent_desc": [_esc(a.get("state_name") or ("म.प्र. राज्य" if hi else "State of M.P."))],
        "versus": ("बनाम" if hi else "Versus"), "title_line": title,
    })
    case = _ph(a.get("case_details"), "प्रकरण क्रमांक/धाराएं" if hi else "case no./sections")
    P = [(f'यहकि, {case} वर्तमान में {fromc} के समक्ष विचाराधीन है, जिसमें आवेदक पक्षकार है।' if hi else
          f'That {case} is pending before {fromc}, in which the applicant is a party.')]
    for ch in _chunks(a.get("facts_narrative")): P.append((f'यहकि, {_esc(ch)}' if hi else f'That {_esc(ch)}'))
    if not _chunks(a.get("facts_narrative")):
        P.append(('<span class="ph">[स्थानान्तरण के कारण — पक्षपात की युक्तियुक्त आशंका / निष्पक्ष विचारण संभव नहीं / सुविधा — खाली पंक्ति से अलग]</span>' if hi
                  else '<span class="ph">[grounds for transfer — reasonable apprehension of bias / fair trial not possible / convenience]</span>'))
    if g.get("fair_trial", True):
        P.append(('यहकि, उपरोक्त परिस्थितियों में आवेदक को {fromc} में निष्पक्ष विचारण की युक्तियुक्त आशंका है, '
                  'अतः न्यायहित में प्रकरण का स्थानान्तरण आवश्यक है।'.replace("{fromc}", fromc) if hi else
                  f'That in these circumstances the applicant entertains a reasonable apprehension that a fair '
                  f'trial is not possible before {fromc}; transfer is therefore necessary in the interest of justice.'))
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append((f'यहकि, {_esc(cu)}' if hi else f'That {_esc(cu)}'))
    pray = (f'अतः माननीय न्यायालय से सादर निवेदन है कि उपरोक्त प्रकरण को {fromc} से स्थानान्तरित कर {toc} में '
            f'विचारण/निराकरण हेतु अन्तरित किये जाने की कृपा करें।' if hi else
            f'It is therefore most respectfully prayed that the said case be transferred from {fromc} to {toc} '
            f'for trial/disposal, in the interest of justice.')
    out = [hdr, '<div class="doc-body">', f'<p class="cb-prelude">{("माननीय न्यायालय," if hi else "MAY IT PLEASE THE COURT,")}</p>',
           f'<p class="cb-prelude">{("आवेदक की ओर से स्थानान्तरण आवेदन निम्न प्रकार प्रस्तुत है ः—" if hi else "The applicant most respectfully submits as under:—")}</p>', '<ol class="cb-paras">']
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

_TOGGLES = [F.toggle("fair_trial", "निष्पक्ष विचारण की आशंका — पैरा", "Fair-trial apprehension — para", default=True)]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "बैंच / जिला", "Bench / District", section="court", hint="लोकेशन से स्वतः → न्यायालय"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "आवेदन क्रमांक", "Application no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("applicant_name", "आवेदक का नाम", "Applicant name", F.NAME, True, "parties"),
        F.f("state_name", "अनावेदक (राज्य/विपक्षी)", "Respondent (State/opposite)", section="parties", default=""),
        F.f("case_details", "स्थानान्तरित प्रकरण (क्रमांक/धाराएं)", "Case to transfer (no./sections)", required=True, section="facts"),
        F.f("from_court", "वर्तमान न्यायालय (जिससे)", "Present court (from)", required=True, section="facts"),
        F.f("to_court", "वांछित न्यायालय (जिसमें)", "Desired court (to)", required=True, section="facts"),
        F.f("facts_narrative", "स्थानान्तरण के कारण", "Grounds for transfer", F.LONGTEXT, True, "facts",
            hint="पक्षपात की आशंका / निष्पक्ष विचारण असंभव / सुविधा — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_code", "प्रकरण कोड", "Case code", section="court", hint="जैसे एम.सी.आर.सी. / सी.आर.ए. / सी.आर.आर. / डब्ल्यू.पी."))
    return F.build_spec(f"transfer_petition:{court}", flds, _TOGGLES,
                        variants={"court": ["hc", "sessions"]}, companions=["affidavit", "vakalatnama"])


SAMPLE = {
    "court": "hc", "court_city": "ग्वालियर", "applicant_name": "____", "state_name": "म.प्र. राज्य",
    "case_details": "प्रकरण क्रमांक ____/2025, धारा ____",
    "from_court": "न्यायिक दण्डाधिकारी प्रथम श्रेणी ____", "to_court": "अन्य सक्षम न्यायालय ____",
    "facts_narrative": "आवेदक को वर्तमान न्यायालय में निष्पक्ष विचारण की युक्तियुक्त आशंका है, क्योंकि ____।",
    "court_city_en": "Gwalior", "applicant_name_en": "____", "state_name_en": "State of M.P.",
    "case_details_en": "Case No. ____/2025, u/s ____",
    "from_court_en": "the JMFC ____", "to_court_en": "another competent court ____",
    "facts_narrative_en": "the applicant has a reasonable apprehension that a fair trial is not possible before the present court because ____.",
    "grounds": {"fair_trial": True}, "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="आपराधिक स्थानान्तरण आवेदन (धारा 447/448 · 407/408) — समीक्षा · AUTHORED · द्विभाषी · reviewed: false")
