"""Habeas corpus — Article 226 (High Court): produce an illegally detained person.

AUTHOR-tier (HC format — FLAG for Vishnu's review). reviewed:false. No case law.
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
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_HC = "माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर"


def _doc(a, hi):
    a = a if hi else _overlay_en(a); g = a.get("grounds") or {}
    det = _ph(a.get("detenu_name"), "बन्दी का नाम" if hi else "detenu's name")
    cn = a.get("court_name") or (compose_court_name("hc", a.get("court_city"), "म.प्र." if hi else "M.P.", lang=("hi" if hi else "en")) if a.get("court_city") else (_HC if hi else "High Court of M.P., Bench at Gwalior"))
    hdr = render_header({
        "side_label": "", "court_name": cn, "case_code": ("बन्दी प्रत्यक्षीकरण क्रमांक" if hi else "W.P. (Habeas Corpus) No."),
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": ("याचिकाकर्ता" if hi else "Petitioner"), "applicant_desc": [_ph(a.get("petitioner_name"), "याचिकाकर्ता" if hi else "petitioner")],
        "respondent_label": ("प्रत्यर्थीगण" if hi else "Respondents"), "respondent_desc": [_ph(a.get("respondent_name"), "राज्य/निरोधक प्राधिकारी" if hi else "State/detaining authority")],
        "versus": ("बनाम" if hi else "Versus"),
        "title_line": ("बन्दी प्रत्यक्षीकरण याचिका अन्तर्गत अनुच्छेद 226 भारत का संविधान" if hi else "WRIT PETITION (HABEAS CORPUS) UNDER ARTICLE 226 OF THE CONSTITUTION"),
    })
    P = []
    rel = _ph(a.get("relation"), "सम्बन्ध" if hi else "relation")
    P.append((f'यहकि, बन्दी {det} याचिकाकर्ता का {rel} है तथा याचिकाकर्ता को प्रकरण की सम्पूर्ण जानकारी है।'
              if hi else f'That the detenu {det} is the {rel} of the petitioner, who is fully acquainted with the facts.'))
    for ch in _chunks(a.get("facts_narrative")): P.append((f'यहकि, {_esc(ch)}' if hi else f'That {_esc(ch)}'))
    if g.get("illegal_detention", True):
        P.append(('यहकि, उक्त बन्दी को प्रत्यर्थीगण द्वारा बिना किसी विधिक प्राधिकार/विधि-सम्मत प्रक्रिया का पालन '
                  'किये अवैध रूप से निरुद्ध/अभिरक्षा में रखा गया है तथा निरोध के आधार भी सूचित नहीं किये गये।'
                  if hi else 'That the detenu has been illegally detained by the respondents without any legal '
                  'authority or due procedure, and the grounds of detention have not been communicated.'))
    if not _chunks(a.get("facts_narrative")):
        P.append(('<span class="ph">[निरोध का विवरण — कब, कहाँ, किसके द्वारा — खाली पंक्ति से अलग पैरा]</span>' if hi
                  else '<span class="ph">[details of the detention — when, where, by whom]</span>'))
    pre = ('माननीय न्यायालय,' if hi else 'MAY IT PLEASE THE COURT,')
    op = ('याचिकाकर्ता की ओर से बन्दी प्रत्यक्षीकरण याचिका निम्न प्रकार प्रस्तुत है ः—' if hi else 'The petitioner most respectfully submits as under:—')
    pray = (f'अतः माननीय न्यायालय से सादर निवेदन है कि प्रत्यर्थीगण को आदेशित किया जावे कि वे बन्दी {det} को '
            f'माननीय न्यायालय के समक्ष प्रस्तुत करें तथा अवैध निरोध से मुक्त किया जावे।' if hi else
            f'It is therefore most respectfully prayed that the respondents be directed to produce the detenu '
            f'{det} before this Hon\'ble Court and that the detenu be set at liberty from illegal detention.')
    out = [hdr, '<div class="doc-body">', f'<p class="cb-prelude">{pre}</p>', f'<p class="cb-prelude">{op}</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>{pray}</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>{("दिनांक: " if hi else "Date: ")}{_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("petitioner_name"), "याचिकाकर्ता" if hi else "Petitioner")}</div>'
               f'<div>— {("याचिकाकर्ता" if hi else "Petitioner")}</div><div style="margin-top:10pt">{("द्वारा अभिभाषक" if hi else "Through Counsel")}</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता" if hi else "advocate")})</div></div></div></div>')
    return "\n".join(out)


def render_hi(a: dict) -> str: return _doc(a or {}, True)
def render_en(a: dict) -> str: return _doc(a or {}, False)

_TOGGLES = [F.toggle("illegal_detention", "अवैध निरोध — पैरा", "Illegal detention — para", default=True)]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "बैंच / जिला", "Bench / District", section="court", hint="लोकेशन से स्वतः → HC बैंच"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "याचिका क्रमांक", "Petition no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("petitioner_name", "याचिकाकर्ता का नाम", "Petitioner name", F.NAME, True, "parties"),
        F.f("detenu_name", "बन्दी का नाम", "Detenu's name", F.NAME, True, "parties"),
        F.f("relation", "याचिकाकर्ता से सम्बन्ध", "Relation to petitioner", section="parties"),
        F.f("respondent_name", "प्रत्यर्थीगण (राज्य/प्राधिकारी)", "Respondents (State/authority)", F.NAME, True, "parties"),
        F.f("facts_narrative", "निरोध का विवरण", "Details of detention", F.LONGTEXT, True, "facts",
            hint="कब, कहाँ, किसके द्वारा, अवैधता कैसे — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("habeas_corpus", flds, _TOGGLES, companions=["affidavit", "vakalatnama"])


SAMPLE = {
    "court_city": "ग्वालियर", "petitioner_name": "____", "detenu_name": "____", "relation": "पुत्र",
    "respondent_name": "म.प्र. राज्य व अन्य",
    "facts_narrative": "बन्दी को प्रत्यर्थीगण द्वारा दिनांक ____ को बिना किसी विधिक आधार के अभिरक्षा में ले लिया गया तथा आज दिनांक तक अवैध रूप से निरुद्ध रखा गया है।",
    "court_city_en": "Gwalior", "petitioner_name_en": "____", "detenu_name_en": "____", "relation_en": "son",
    "respondent_name_en": "State of M.P. & ors.",
    "facts_narrative_en": "the detenu was taken into custody by the respondents on ____ without any legal basis and has been illegally detained till date.",
    "grounds": {"illegal_detention": True}, "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="बन्दी प्रत्यक्षीकरण अनुच्छेद 226 — समीक्षा · AUTHORED (HC; विष्णु जी समीक्षा आवश्यक) · द्विभाषी · reviewed: false")
