"""Dispense with personal attendance — §228 BNSS (§205 CrPC).

Canonical build, mirror-first from Vishnu ji's real §205 filing (benchmark:
"205 JMFC senior Cancer" — accused exempted from personal appearance due to
age / illness / caregiving for a disabled child). The accused seeks exemption,
appearing through counsel. No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Bhaskar Industries Ltd. v. Bhiwani Denim (2001) 7 SCC 401", "point": "Magistrate may dispense with personal attendance where appropriate", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_CD = "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (________)"


def render_hi(a: dict) -> str:
    a = a or {}; g = a.get("grounds") or {}
    plural = bool(a.get("is_plural", False))
    aw = "प्रार्थीगण" if plural else "प्रार्थी"; acc = "आरोपीगण" if plural else "आरोपी"
    state = _esc(a.get("state_name") or "________")
    stage = _esc(a.get("current_stage") or "विचाराधीन होकर साक्ष्य हेतु नियत")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), a.get("state_name") or "") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "आर.सी.टी.", "applicant_label": "अभियोगी", "applicant_desc": [state],
        "respondent_label": acc, "respondent_desc": [_ph(a.get("accused_names"), "आरोपी का नाम")],
        "versus": "बनाम", "title_line": "आवेदन पत्र अन्तर्गत धारा 228 भा.ना.सु.सं. (205 दं.प्र.सं.)",
    })
    P = [f'यहकि, {aw} के विरुद्ध उक्त प्रकरण माननीय न्यायालय के समक्ष {stage} है।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[व्यक्तिगत उपस्थिति में असमर्थता का कारण — बीमारी/वृद्धावस्था/दूरी/'
                 'आश्रित की देखभाल आदि — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("counsel_represents", True):
        P.append(f'यहकि, {aw} द्वारा प्रकरण की पैरवी हेतु अभिभाषक नियुक्त किया गया है जो प्रत्येक नियत दिनांक '
                 f'पर {aw} की ओर से उपस्थित रहेंगे; ऐसी स्थिति में {aw} की प्रत्येक तिथि पर व्यक्तिगत उपस्थिति '
                 f'आवश्यक नहीं है।')
    if g.get("undertaking", True):
        P.append(f'यहकि, {aw} यह वचनबद्धता देता है कि वह अपनी पहचान विवादित नहीं करेगा, आवश्यकता पड़ने पर '
                 f'माननीय न्यायालय के समक्ष व्यक्तिगत रूप से उपस्थित होगा तथा प्रकरण में अनावश्यक विलम्ब नहीं '
                 f'करेगा।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय महोदय,</p>',
           f'<p class="cb-prelude">{aw}/{acc} की ओर से आवेदन पत्र निम्नानुसार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि धारा 228 भा.ना.सु.सं. (205 '
               f'दं.प्र.सं.) के अधीन {aw} को व्यक्तिगत उपस्थिति से छूट प्रदान कर अभिभाषक के माध्यम से उपस्थिति '
               f'की अनुमति प्रदान करने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{aw}</div><div>— {acc}</div><div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    plural = bool(a.get("is_plural", False))
    aw = "applicants" if plural else "applicant"
    state = _esc(a.get("state_name") or "________")
    stage = _esc(a.get("current_stage_en") or "pending and fixed for evidence")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), a.get("state_name") or "", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Prosecution", "applicant_desc": [state],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_names"), "the accused")],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 228 BNSS, 2023 (SECTION 205 CrPC, 1973)"})
    P = [f'That the case against the {aw} is {stage} before this Hon\'ble Court.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("counsel_represents", True):
        P.append(f'That the {aw} have engaged counsel who shall appear on their behalf on every date; the '
                 f'personal presence of the {aw} on each date is therefore not necessary.')
    if g.get("undertaking", True):
        P.append(f'That the {aw} undertake not to dispute identity, to appear in person whenever required by '
                 f'this Hon\'ble Court, and not to cause any delay.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           f'<p class="cb-prelude">The {aw} most respectfully submit as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that under Section 228 BNSS '
               f'(Section 205 CrPC) the {aw} be exempted from personal attendance and permitted to appear '
               f'through counsel, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{"Applicants" if plural else "Applicant"} — Accused</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("counsel_represents", "अभिभाषक उपस्थित रहेंगे — पैरा", "Counsel will appear — para", default=True),
    F.toggle("undertaking", "पहचान/उपस्थिति की वचनबद्धता", "Undertaking (identity/appear)", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("accused_names", "आरोपी/प्रार्थी का नाम", "Accused / applicant name(s)", F.NAME, True, "parties"),
        F.f("is_plural", "एक से अधिक आरोपी?", "More than one accused?", F.TOGGLE, section="parties", default=False),
        F.f("state_name", "अभियोगी पक्ष", "Prosecution side", section="parties", default=""),
        F.f("current_stage", "प्रकरण की वर्तमान स्थिति", "Current stage", section="court",
            hint="जैसे: साक्ष्य हेतु नियत / आरोप विरचन हेतु नियत"),
        F.f("facts_narrative", "उपस्थिति में असमर्थता का कारण", "Reason for inability to attend", F.LONGTEXT, True, "facts",
            hint="बीमारी/वृद्धावस्था/दूरी/आश्रित की देखभाल — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_type", "प्रकरण प्रकार", "Case type", section="court", hint="जैसे आर.सी.टी. / सत्रवाद — शीर्षक का प्रकरण-कोड"))
    return F.build_spec(f"exemption_205:{court}", flds, _TOGGLES,
                        companions=["vakalatnama"])


SAMPLE = {
    "court_city": "शिवपुरी", "case_number": "____/2023", "case_type": "आर.सी.टी.",
    "accused_names": "____ आदि", "is_plural": True, "state_name": "म.प्र. राज्य",
    "current_stage": "विचाराधीन होकर साक्ष्य हेतु नियत",
    "facts_narrative": (
        "प्रार्थी 68 वर्ष की आयु के होकर कैंसर से पीड़ित हैं तथा प्रार्थिया पैरालाइसिस से ग्रसित होकर इलाजरत हैं।\n\n"
        "प्रार्थीगण का 10 वर्षीय पुत्र गम्भीर रूप से विकलांग है, जिसकी 24 घण्टे देखभाल आवश्यक है; इस कारण "
        "प्रार्थीगण प्रत्येक तिथि पर न्यायालय में व्यक्तिगत रूप से उपस्थित होने में असमर्थ हैं।"
    ),
    "court_city_en": "Shivpuri", "accused_names_en": "____ & ors.", "state_name_en": "State of M.P.",
    "current_stage_en": "pending and fixed for evidence",
    "facts_narrative_en": (
        "the applicant, aged 68, is suffering from cancer, and the applicant's wife is undergoing treatment for "
        "paralysis.\n\n"
        "the applicants' 10-year-old son is severely disabled and needs round-the-clock care; the applicants are "
        "therefore unable to attend court in person on every date."
    ),
    "grounds": {"counsel_represents": True, "undertaking": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="व्यक्तिगत उपस्थिति से छूट (धारा 228 · 205) — समीक्षा · द्विभाषी · "
                           "विष्णु जी की 205 फाइलिंग से अक्षरशः · reviewed: false")
