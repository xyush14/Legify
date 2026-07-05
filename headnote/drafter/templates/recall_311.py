"""Recall / re-examine a witness — §348 BNSS (§311 CrPC).

Canonical build, mirror-first from Vishnu ji's real §311 filing (benchmark:
"311 Megh singh" — recall PWs for further cross-examination where contradictions
/ omissions were not put). A scaffold: the WHICH-witness-and-why is case-specific
(lawyer fills); the template carries the canonical header, the §311 idiom and the
fixed just-decision / no-delay grounds. No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Vijay Kumar v. State of U.P. (2011) 8 SCC 136", "point": "§311 — recall to enable a just decision, not to fill gaps", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


def _cfg(court):
    if court == "sessions":
        return dict(level="sessions", court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (________)")
    return dict(level="magistrate", court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (________)")


def render_hi(a: dict) -> str:
    a = a or {}
    c = _cfg(a.get("court") or "sessions"); g = a.get("grounds") or {}
    plural = bool(a.get("is_plural", True))
    aw = "प्रार्थीगण" if plural else "प्रार्थी"; acc = "अभियुक्तगण" if plural else "अभियुक्त"
    state = _esc(a.get("state_name") or "________ शासन")
    wit = _ph(a.get("witnesses"), "अ.सा.—01 आदि")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), a.get("state_name") or "") \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "", "applicant_label": "अभियोगी", "applicant_desc": [state],
        "respondent_label": acc, "respondent_desc": [_ph(a.get("accused_names"), "अभियुक्तगण")],
        "versus": "बनाम", "title_line": "आवेदन पत्र अन्तर्गत धारा 348 भा.ना.सु.सं. (311 दं.प्र.सं.)",
    })
    P = [f'यहकि, {aw} का प्रकरण माननीय न्यायालय के समक्ष विचाराधीन होकर साक्ष्य हेतु नियत है।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[किन साक्षियों को पुनः बुलाना है तथा क्यों — मुख्य परीक्षण के कौन से '
                 'विरोधाभास/लोप प्रतिपरीक्षण में नहीं आये — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("just_decision", True):
        P.append(f'यहकि, उपरोक्त साक्षी {wit} को {aw} की ओर से पुनः प्रतिपरीक्षण हेतु बुलाया जाना प्रकरण के '
                 f'न्यायपूर्ण निराकरण के लिये आवश्यक है।')
    if g.get("no_delay", True):
        P.append(f'यहकि, यह आवेदन प्रकरण को विलम्बित करने अथवा किसी पक्ष को अनुचित लाभ पहुँचाने के उद्देश्य से '
                 f'प्रस्तुत नहीं किया गया है; इससे विपक्षी को कोई प्रतिकूल प्रभाव नहीं पड़ेगा।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय महोदय,</p>',
           f'<p class="cb-prelude">{aw} की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि साक्षी {wit} को धारा 348 '
               f'भा.ना.सु.सं. (311 दं.प्र.सं.) के अधीन पुनः प्रतिपरीक्षण हेतु बुलाये जाने का आदेश पारित करने की '
               f'कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{aw}</div><div>— {acc}</div><div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a)
    c = _cfg(a.get("court") or "sessions"); g = a.get("grounds") or {}
    plural = bool(a.get("is_plural", True))
    aw = "applicants" if plural else "applicant"
    state = _esc(a.get("state_name") or "________")
    wit = _ph(a.get("witnesses"), "PW-1 etc.")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), a.get("state_name") or "", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Prosecution", "applicant_desc": [state],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_names"), "the accused")],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 348 BNSS, 2023 (SECTION 311 CrPC, 1973)",
    })
    P = ['That the matter is pending before this Hon\'ble Court and is fixed for evidence.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("just_decision", True):
        P.append(f'That recalling the witness(es) {wit} for further cross-examination on behalf of the {aw} is '
                 f'necessary for a just decision of the case.')
    if g.get("no_delay", True):
        P.append('That this application is not made to delay the proceedings or to gain any undue advantage, '
                 'and no prejudice will be caused to the opposite party.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           f'<p class="cb-prelude">The {aw} most respectfully submit as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that the witness(es) {wit} '
               f'be recalled for further cross-examination under Section 348 BNSS (Section 311 CrPC), in the '
               f'interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{"Applicants" if plural else "Applicant"} — Accused</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("just_decision", "न्यायपूर्ण निराकरण हेतु आवश्यक", "Necessary for a just decision", default=True),
    F.toggle("no_delay", "विलम्ब का उद्देश्य नहीं — पैरा", "Not to delay — para", default=True),
]


def field_spec(court: str = "sessions") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("accused_names", "अभियुक्त/प्रार्थी का नाम", "Accused / applicant name(s)", F.NAME, True, "parties"),
        F.f("is_plural", "एक से अधिक अभियुक्त?", "More than one accused?", F.TOGGLE, section="parties", default=True),
        F.f("state_name", "अभियोगी पक्ष", "Prosecution side", section="parties", default=""),
        F.f("witnesses", "किन साक्षियों को पुनः बुलाना है", "Which witness(es) to recall", required=True, section="facts",
            hint="जैसे: अ.सा.—01 एवं अ.सा.—02"),
        F.f("facts_narrative", "पुनः बुलाने का कारण", "Why recall", F.LONGTEXT, True, "facts",
            hint="मुख्य परीक्षण के कौन से विरोधाभास/लोप प्रतिपरीक्षण में नहीं आये — खाली पंक्ति से अलग"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_type", "प्रकरण प्रकार", "Case type", section="court", hint="जैसे आर.सी.टी. / सत्रवाद — शीर्षक का प्रकरण-कोड"))
    return F.build_spec(f"recall_311:{court}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions"]}, companions=["vakalatnama"])


SAMPLE = {
    "court": "sessions", "court_city": "ग्वालियर", "case_number": "____/2022", "case_type": "सत्रवाद",
    "accused_names": "____ आदि", "is_plural": True, "state_name": "म.प्र. शासन",
    "witnesses": "अ.सा.—01 एवं अ.सा.—02",
    "facts_narrative": (
        "अभियोजन साक्षी अ.सा.—01 एवं अ.सा.—02 के मुख्य परीक्षण में अनेक दस्तावेज प्रदर्श कराये गये, किन्तु "
        "दौराने प्रतिपरीक्षण मुख्य परीक्षण के समस्त कथन एवं दस्तावेज खण्डित नहीं किये जा सके।\n\n"
        "मुख्य परीक्षण में आये विरोधाभास एवं लोप के सम्बन्ध में प्रतिपरीक्षण शेष रह गया है, जिसके लिये उक्त "
        "साक्षियों को पुनः बुलाया जाना आवश्यक है।"
    ),
    "court_city_en": "Gwalior", "state_name_en": "State of M.P.",
    "accused_names_en": "____ & ors.", "witnesses_en": "PW-1 and PW-2",
    "facts_narrative_en": (
        "in the examination-in-chief of PW-1 and PW-2 several documents were exhibited, but in cross-examination "
        "the chief and the documents could not be fully challenged.\n\n"
        "cross-examination on the contradictions and omissions in the chief remains incomplete, for which the "
        "said witnesses need to be recalled."
    ),
    "grounds": {"just_decision": True, "no_delay": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="साक्षी पुनः-परीक्षण (धारा 348 भा.ना.सु.सं. / 311 दं.प्र.सं.) — समीक्षा · द्विभाषी · "
                           "विष्णु जी की 311 फाइलिंग से अक्षरशः · reviewed: false")
