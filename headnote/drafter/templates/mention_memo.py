"""Mention memo — request to mention / urgently list-advance a case.

AUTHOR-tier (a short procedural slip; no Vishnu mirror needed): a one-page memo
requesting the court to take up / advance / urgently list a matter, in his
house-style. reviewed:false. No case law in the body.
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


def _cfg(court):
    return {
        "sessions": dict(level="sessions", court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (म.प्र.)"),
        "magistrate": dict(level="magistrate", court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)"),
        "family": dict(level="family", court_default="न्यायालय माननीय कुटुम्ब न्यायालय, ............ (म.प्र.)"),
    }.get(court, dict(level="hc", court_default="माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर"))


def render_hi(a: dict) -> str:
    a = a or {}; c = _cfg(a.get("court") or "hc"); g = a.get("grounds") or {}
    nd = _ph(a.get("next_date"), "नियत दिनांक")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": a.get("case_code") or "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "", "applicant_label": "आवेदक",
        "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक का नाम")],
        "respondent_label": "अनावेदक", "respondent_desc": [_ph(a.get("respondent_name"), "अनावेदक का नाम")],
        "versus": "बनाम", "title_line": "स्मरण पत्र (अविलम्ब सूचीबद्धता / उल्लेख हेतु)",
    })
    P = [f'यहकि, उपरोक्त प्रकरण माननीय न्यायालय के समक्ष विचाराधीन होकर दिनांक {nd} को नियत है।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[अविलम्ब सुनवाई/उल्लेख की आवश्यकता का कारण — जैसे अन्तरिम आदेश समाप्त हो रहा, '
                 'अत्यावश्यक राहत, नियत तिथि बहुत दूर — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("urgent_relief", True):
        P.append('यहकि, प्रकरण की परिस्थितियाँ अत्यावश्यक होकर शीघ्र सुनवाई की अपेक्षा रखती हैं; विलम्ब से '
                 'आवेदक को अपूरणीय क्षति की सम्भावना है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    rd = a.get("requested_date")
    when = f'दिनांक {_esc(rd)} को ' if rd else 'यथाशीघ्र '
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           '<p class="cb-prelude">आवेदक की ओर से स्मरण पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः माननीय न्यायालय से सादर निवेदन है कि उपरोक्त प्रकरण को {when}'
               f'उल्लेख कर सुनवाई हेतु अग्रिम/सूचीबद्ध किये जाने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदक")}</div><div>— आवेदक</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); c = _cfg(a.get("court") or "hc"); g = a.get("grounds") or {}
    nd = _ph(a.get("next_date"), "the next date")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": a.get("case_code") or "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [_ph(a.get("applicant_name"), "applicant")],
        "respondent_label": "Respondent", "respondent_desc": [_ph(a.get("respondent_name"), "respondent")],
        "versus": "Versus", "title_line": "MENTION MEMO (FOR URGENT LISTING / MENTIONING)"})
    P = [f'That the above matter is pending before this Hon\'ble Court and is fixed for {nd}.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("urgent_relief", True):
        P.append('That the circumstances are urgent and warrant an early hearing; delay is likely to cause '
                 'irreparable prejudice to the applicant.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    rd = a.get("requested_date")
    when = f'on {_esc(rd)} ' if rd else 'at the earliest '
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The applicant most respectfully submits this mention memo as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that the above matter be '
               f'mentioned and taken up / listed for hearing {when}, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "Applicant")}</div><div>— Applicant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("urgent_relief", "अत्यावश्यकता/अपूरणीय क्षति — पैरा", "Urgency / irreparable prejudice — para", default=True),
]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर / बैंच", "District / Bench", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("applicant_name", "आवेदक का नाम", "Applicant name", F.NAME, True, "parties"),
        F.f("respondent_name", "अनावेदक का नाम", "Respondent name", F.NAME, section="parties"),
        F.f("next_date", "वर्तमान नियत दिनांक", "Current next date", F.DATE, section="facts"),
        F.f("requested_date", "अनुरोधित दिनांक (वैकल्पिक)", "Requested date (optional)", F.DATE, section="facts"),
        F.f("facts_narrative", "अविलम्ब सुनवाई का कारण", "Reason for urgency", F.LONGTEXT, True, "facts",
            hint="अन्तरिम आदेश समाप्ति, अत्यावश्यक राहत, नियत तिथि दूर — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec(f"mention_memo:{court}", flds, _TOGGLES,
                        variants={"court": ["hc", "sessions", "magistrate", "family"]}, companions=[])


SAMPLE = {
    "court": "hc", "court_city": "ग्वालियर", "case_number": "____/2026",
    "applicant_name": "____", "respondent_name": "____",
    "next_date": "__/__/2026",
    "facts_narrative": (
        "प्रकरण में पूर्व में पारित अन्तरिम आदेश की अवधि शीघ्र समाप्त हो रही है तथा नियत तिथि अत्यधिक दूर है।\n\n"
        "आवेदक को अविलम्ब राहत की आवश्यकता है, अन्यथा अपूरणीय क्षति होने की सम्भावना है।"
    ),
    "court_city_en": "Gwalior", "applicant_name_en": "____", "respondent_name_en": "____",
    "facts_narrative_en": (
        "the interim order earlier passed in the matter is about to expire and the next date is far away.\n\n"
        "the applicant needs urgent relief, failing which irreparable prejudice is likely."
    ),
    "grounds": {"urgent_relief": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="स्मरण पत्र / Mention Memo — समीक्षा · AUTHORED (कोई mirror नहीं) · द्विभाषी · reviewed: false")
