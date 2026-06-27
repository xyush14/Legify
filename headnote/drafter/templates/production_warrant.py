"""Jail production warrant — produce an accused lodged in custody before the Court
— §302 BNSS (§267 CrPC).

AUTHOR-tier short application: requests the Court to issue a production warrant to
the jail to produce an accused (lodged in another jail / another case) on the next
date. reviewed:false. No case law in the body.
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
    if court == "sessions":
        return dict(level="sessions", court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (म.प्र.)")
    return dict(level="magistrate", court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)")


def render_hi(a: dict) -> str:
    a = a or {}; c = _cfg(a.get("court") or "magistrate")
    state = _esc(a.get("state_name") or "म.प्र. राज्य")
    acc = _ph(a.get("accused_name"), "अभियुक्त का नाम"); jail = _ph(a.get("jail_name"), "जेल का नाम")
    nd = _ph(a.get("next_date"), "नियत दिनांक")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "", "applicant_label": "अभियोगी", "applicant_desc": [state],
        "respondent_label": "अभियुक्त", "respondent_desc": [acc],
        "versus": "बनाम",
        "title_line": "आवेदन पत्र वास्ते उत्पादन वारंट अन्तर्गत धारा 302 भा.ना.सु.सं. (267 दं.प्र.सं.)",
    })
    P = [f'यहकि, उपरोक्त प्रकरण माननीय न्यायालय के समक्ष विचाराधीन होकर दिनांक {nd} को {_esc(a.get("stage") or "सुनवाई")} '
         f'हेतु नियत है।',
         f'यहकि, अभियुक्त {acc} वर्तमान में {jail} में '
         f'{_esc(a.get("custody_reason") or "अन्य प्रकरण के सम्बन्ध में")} निरुद्ध है।']
    facts = _chunks(a.get("facts_narrative"))
    for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    P.append(f'यहकि, उक्त अभियुक्त की उपस्थिति प्रकरण की सुनवाई हेतु आवश्यक है, जिसके लिये {jail} को उत्पादन '
             f'वारंट जारी किया जाना आवश्यक है।')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           '<p class="cb-prelude">प्रार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि {jail} के अधीक्षक के नाम उत्पादन '
               f'वारंट जारी कर अभियुक्त {acc} को दिनांक {nd} को माननीय न्यायालय के समक्ष प्रस्तुत कराये जाने का '
               f'आदेश पारित करने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("advocate_name"), "अधिवक्ता")}</div>'
               '<div>द्वारा अभिभाषक</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); c = _cfg(a.get("court") or "magistrate")
    state = _esc(a.get("state_name") or "State of M.P.")
    acc = _ph(a.get("accused_name"), "the accused"); jail = _ph(a.get("jail_name"), "the jail")
    nd = _ph(a.get("next_date"), "the next date")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Prosecution", "applicant_desc": [state],
        "respondent_label": "Accused", "respondent_desc": [acc],
        "versus": "Versus", "title_line": "APPLICATION FOR A PRODUCTION WARRANT UNDER SECTION 302 BNSS "
                                          "(SECTION 267 CrPC)"})
    P = [f'That the matter is pending before this Hon\'ble Court and is fixed for {_esc(a.get("stage_en") or a.get("stage") or "hearing")} on {nd}.',
         f'That the accused {acc} is presently lodged in {jail} {_esc(a.get("custody_reason_en") or a.get("custody_reason") or "in connection with another case")}.']
    for ch in _chunks(a.get("facts_narrative_en") or a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    P.append(f'That the presence of the said accused is necessary for the hearing, for which a production '
             f'warrant needs to be issued to {jail}.')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The applicant most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that a production warrant be '
               f'issued to the Superintendent of {jail} to produce the accused {acc} before this Hon\'ble Court '
               f'on {nd}, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("advocate_name"), "advocate")}</div><div>Through Counsel</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = []


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("accused_name", "अभियुक्त का नाम", "Accused name", F.NAME, True, "parties"),
        F.f("state_name", "अभियोगी पक्ष", "Prosecution side", section="parties", default="म.प्र. राज्य"),
        F.f("jail_name", "जेल / उपकारागृह", "Jail name", required=True, section="facts"),
        F.f("custody_reason", "निरुद्धि का कारण (अन्य प्रकरण)", "Reason in custody (other case)", section="facts"),
        F.f("stage", "प्रकरण की स्थिति", "Stage", section="facts", hint="जैसे: साक्ष्य / आरोप"),
        F.f("next_date", "नियत दिनांक", "Next date", F.DATE, required=True, section="facts"),
        F.f("facts_narrative", "अतिरिक्त तथ्य (वैकल्पिक)", "Additional facts (optional)", F.LONGTEXT, section="facts"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec(f"production_warrant:{court}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions"]}, companions=[])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2026", "accused_name": "____", "state_name": "म.प्र. राज्य",
    "jail_name": "केन्द्रीय जेल ____", "custody_reason": "अन्य अपराध प्रकरण क्रमांक ____ के सम्बन्ध में",
    "stage": "साक्ष्य", "next_date": "__/__/2026",
    "facts_narrative": "",
    "court_city_en": "Gwalior", "accused_name_en": "____", "state_name_en": "State of M.P.",
    "jail_name_en": "Central Jail ____", "custody_reason_en": "in connection with Crime Case No. ____",
    "stage_en": "evidence",
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="उत्पादन वारंट (धारा 302 · 267) — समीक्षा · AUTHORED · द्विभाषी · reviewed: false")
