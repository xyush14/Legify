"""Writ petition — Articles 226/227 of the Constitution (High Court).

AUTHOR-tier (no Vishnu writ in the corpus; HC-Rules format differs most from his
trial-court style — FLAG for Vishnu's review). Focused petition: facts (impugned
action/order) -> grounds (illegality / arbitrariness / breach of right + no
efficacious alternative remedy) -> prayer (certiorari to quash + mandamus). The
full HC-Rules synopsis/index/list-of-dates is added by the advocate. reviewed:false.
No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Whirlpool Corp. v. Registrar of Trade Marks (1998) 8 SCC 1", "point": "writ maintainable despite alternative remedy (fundamental right / natural justice / jurisdiction)", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_HC = "माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर"


def render_hi(a: dict) -> str:
    a = a or {}; g = a.get("grounds") or {}
    art = _esc(a.get("articles") or "226/227")
    court_name = a.get("court_name") or compose_court_name("hc", a.get("court_city"), a.get("state_name") or "") \
        if a.get("court_city") else (a.get("court_name") or _HC)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": a.get("case_code") or "रिट याचिका क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "याचिकाकर्ता", "applicant_desc": [_ph(a.get("petitioner_name"), "याचिकाकर्ता का नाम")],
        "respondent_label": "प्रत्यर्थीगण", "respondent_desc": [_ph(a.get("respondent_name"), "प्रत्यर्थीगण (राज्य/प्राधिकारी)")],
        "versus": "बनाम", "title_line": f"रिट याचिका अन्तर्गत अनुच्छेद {art} भारत का संविधान",
    })
    P = []
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[तथ्य — याचिकाकर्ता का परिचय, प्रत्यर्थी द्वारा पारित विवादित आदेश/कार्यवाही '
                 'एवं उससे हुई व्यथा — खाली पंक्ति से अलग पैरा]</span>')
    P.append('<span class="cb-head">याचिका के आधार ः—</span>')
    grounds = _chunks(a.get("grounds_narrative"))
    if grounds:
        for ch in grounds: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[आधार — विवादित आदेश विधि-विरुद्ध/मनमाना/अधिकारिता-रहित कैसे है — खाली पंक्ति से अलग]</span>')
    if g.get("violates_rights", True):
        P.append('यहकि, विवादित आदेश/कार्यवाही याचिकाकर्ता के संवैधानिक एवं विधिक अधिकारों का उल्लंघन करती है '
                 'तथा नैसर्गिक न्याय के सिद्धान्तों के विपरीत है।')
    if g.get("no_alt_remedy", True):
        P.append('यहकि, याचिकाकर्ता के पास अन्य कोई सक्षम एवं प्रभावी वैकल्पिक उपचार उपलब्ध नहीं है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    relief = _esc(a.get("relief_sought") or "विवादित आदेश को अभिखण्डित (quash) किया जावे तथा प्रत्यर्थीगण को समुचित निर्देश दिया जावे")
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           '<p class="cb-prelude">याचिकाकर्ता की ओर से रिट याचिका निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः माननीय न्यायालय से सादर निवेदन है कि उपयुक्त रिट/आदेश/निर्देश '
               f'जारी कर {relief} जाने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("petitioner_name"), "याचिकाकर्ता")}</div><div>— याचिकाकर्ता</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    art = _esc(a.get("articles") or "226/227")
    court_name = a.get("court_name") or compose_court_name("hc", a.get("court_city"), a.get("state_name") or "", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": a.get("case_code") or "Writ Petition No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Petitioner", "applicant_desc": [_ph(a.get("petitioner_name"), "petitioner")],
        "respondent_label": "Respondents", "respondent_desc": [_ph(a.get("respondent_name"), "respondents (State/authority)")],
        "versus": "Versus", "title_line": f"WRIT PETITION UNDER ARTICLES {art} OF THE CONSTITUTION OF INDIA"})
    P = []
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    P.append('<span class="cb-head">GROUNDS:—</span>')
    for ch in _chunks(a.get("grounds_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("violates_rights", True):
        P.append('That the impugned order/action violates the petitioner\'s constitutional and legal rights and '
                 'is contrary to the principles of natural justice.')
    if g.get("no_alt_remedy", True):
        P.append('That the petitioner has no other efficacious alternative remedy available.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    relief = _esc(a.get("relief_sought_en") or a.get("relief_sought") or "quash the impugned order and issue appropriate directions to the respondents")
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The petitioner most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may '
               f'be pleased to issue an appropriate writ/order/direction to {relief}, in the interest of '
               f'justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("petitioner_name"), "Petitioner")}</div><div>— Petitioner</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("violates_rights", "अधिकारों का उल्लंघन / नैसर्गिक न्याय", "Violates rights / natural justice", default=True),
    F.toggle("no_alt_remedy", "कोई वैकल्पिक उपचार नहीं", "No alternative remedy", default=True),
]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "बैंच / जिला", "Bench / District", section="court", hint="लोकेशन से स्वतः → HC बैंच"),
        F.f("state_name", "राज्य", "State", section="court", hint="मामले का राज्य (रिक्त → स्थान रिक्त)"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "याचिका क्रमांक", "Petition no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("articles", "अनुच्छेद", "Article(s)", section="court", default="226/227"),
        F.f("petitioner_name", "याचिकाकर्ता का नाम", "Petitioner name", F.NAME, True, "parties"),
        F.f("respondent_name", "प्रत्यर्थीगण (राज्य/प्राधिकारी)", "Respondents (State/authority)", F.NAME, True, "parties"),
        F.f("facts_narrative", "तथ्य (विवादित आदेश/कार्यवाही)", "Facts (impugned order/action)", F.LONGTEXT, True, "facts",
            ocr="order", hint="परिचय + विवादित आदेश + व्यथा — खाली पंक्ति से अलग पैरा"),
        F.f("grounds_narrative", "याचिका के आधार", "Grounds", F.LONGTEXT, section="grounds",
            hint="आदेश विधि-विरुद्ध/मनमाना कैसे है — खाली पंक्ति से अलग पैरा"),
        F.f("relief_sought", "मांगा गया अनुतोष", "Relief sought", F.LONGTEXT, section="grounds",
            hint="जैसे: विवादित आदेश अभिखण्डित करें / परमादेश जारी करें"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_code", "प्रकरण कोड", "Case code", section="court", hint="जैसे एम.सी.आर.सी. / सी.आर.ए. / सी.आर.आर. / डब्ल्यू.पी."))
    return F.build_spec("writ_petition", flds, _TOGGLES, companions=["affidavit", "vakalatnama", "annexures (impugned order)"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2026", "articles": "226/227",
    "petitioner_name": "____", "respondent_name": "म.प्र. राज्य व अन्य",
    "facts_narrative": (
        "याचिकाकर्ता एक विधि-पालक नागरिक है, जिसके विरुद्ध प्रत्यर्थी क्रमांक—__ द्वारा दिनांक ____ को विवादित "
        "आदेश पारित किया गया।\n\n"
        "उक्त आदेश याचिकाकर्ता को बिना सुनवाई का अवसर दिये, मनमाने ढंग से पारित किया गया है।"
    ),
    "grounds_narrative": (
        "विवादित आदेश सक्षम अधिकारिता के अभाव एवं विधि के विरुद्ध पारित होने से अस्थिर है।"
    ),
    "relief_sought": "विवादित आदेश दिनांक ____ को अभिखण्डित (quash) किया जावे",
    "court_city_en": "Gwalior", "petitioner_name_en": "____", "respondent_name_en": "State of M.P. & ors.",
    "facts_narrative_en": (
        "the petitioner is a law-abiding citizen against whom respondent no. __ passed the impugned order dated ____.\n\n"
        "the said order was passed arbitrarily, without affording the petitioner an opportunity of hearing."
    ),
    "grounds_narrative_en": "the impugned order is unsustainable, being without jurisdiction and contrary to law.",
    "relief_sought_en": "quash the impugned order dated ____",
    "grounds": {"violates_rights": True, "no_alt_remedy": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="रिट याचिका अनुच्छेद 226/227 — समीक्षा · AUTHORED (कोई mirror नहीं — HC प्रारूप; "
                           "विष्णु जी की समीक्षा आवश्यक) · द्विभाषी · reviewed: false")
