"""Vakalatnama — advocate's authority to appear (वकालतनामा).

Canonical-standard rebuild (supersedes the old-shell version): the standard
authorisation clauses on the canonical header. A FORM (not a grounds application),
so no यहकि facts/grounds — but it shares the canonical court-paper header. Only the
court, party, advocate and date variables fill in. No LLM writes any text; no case law.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


_POWERS_HI = [
    "मेरी/हमारी ओर से माननीय न्यायालय में उपस्थित होना।",
    "प्रकरण में पैरवी, बहस एवं तर्क प्रस्तुत करना।",
    "आवश्यक आवेदन-पत्र, दस्तावेज एवं साक्ष्य प्रस्तुत करना तथा आवश्यकतानुसार वापस लेना।",
    "साक्षियों की मुख्य परीक्षा, प्रतिपरीक्षा एवं पुनःपरीक्षा करना।",
    "प्रकरण से सम्बन्धित राशि, दस्तावेज एवं आदेश/निर्णय की प्रमाणित प्रतिलिपि प्राप्त करना।",
    "मेरे/हमारे निर्देशानुसार समझौता/राजीनामा करना अथवा आवेदन/प्रकरण वापस लेना।",
    "आवश्यकता होने पर मेरी/हमारी ओर से अन्य अधिवक्ता नियुक्त करना।",
]
_POWERS_EN = [
    "to appear before the Hon'ble Court on my/our behalf;",
    "to conduct, plead and argue the case;",
    "to file and, as required, withdraw applications, documents and evidence;",
    "to examine, cross-examine and re-examine witnesses;",
    "to receive money, documents and certified copies of orders/judgment relating to the case;",
    "to compromise or withdraw the application/case as per my/our instructions;",
    "to engage another advocate on my/our behalf if necessary.",
]


def _render(a, *, hi):
    a = a or {}
    state = _esc(a.get("state_name") or (a.get("state_name") or ""))
    role = a.get("party_role") or ("आवेदक" if hi else "Applicant")
    client = _ph(a.get("client_name"), "मुवक्किल का नाम" if hi else "client name")
    adv = _ph(a.get("advocate_name"), "अधिवक्ता का नाम" if hi else "advocate name")
    enrol = a.get("advocate_enrollment") or ""
    court_name = a.get("court_name") or (
        (f"न्यायालय माननीय ________ ({a.get('state_name') or '________'})" if hi else "(name of the Court)"))

    cdesc = (f'{client} पुत्र/पुत्री/पत्नी श्री {_ph(a.get("client_father"), "पिता/पति")}, '
             f'निवासी— <u>{_ph(a.get("client_address"), "पता")}</u> ({state})') if hi else (
             f'{client}, S/D/W-o {_ph(a.get("client_father"), "father/husband")}, '
             f'R/o {_ph(a.get("client_address"), "address")} ({state})')
    resp = [_esc(a.get("opposite_party"))] if a.get("opposite_party") else (
        ['<span class="ph">' + ('विपक्षी (यदि कोई)' if hi else 'opposite party (if any)') + '</span>'])

    hdr = render_header({
        "side_label": "", "court_name": court_name,
        "case_code": ("प्रकरण/अपराध क्रमांक" if hi else "Case/Crime No."), "case_suffix": "",
        "case_number": a.get("case_no") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": role, "applicant_desc": [cdesc],
        "respondent_label": ("विपक्षी" if hi else "Opposite Party"), "respondent_desc": resp,
        "versus": ("बनाम" if hi else "Versus"), "title_line": ("वकालतनामा" if hi else "VAKALATNAMA"),
    })
    out = [hdr, '<div class="doc-body">']
    if hi:
        out.append(f'<p class="cb-prelude">मैं/हम उपरोक्त {_esc(role)}, उपर्युक्त प्रकरण में एतद्द्वारा अधिवक्ता '
                   f'<b>{adv}</b> को अपना अधिवक्ता नियुक्त कर निम्नलिखित अधिकार प्रदान करता/करती हूँ ः—</p>')
    else:
        out.append(f'<p class="cb-prelude">I/We, the above {_esc(role)}, do hereby appoint and authorise Advocate '
                   f'<b>{adv}</b> in the above matter to:—</p>')
    out.append('<ol class="cb-paras">')
    for p in (_POWERS_HI if hi else _POWERS_EN):
        out.append(f'<li>{_esc(p)}</li>')
    out.append('</ol>')
    if hi:
        out.append('<p class="cb-prelude">उपरोक्त अधिवक्ता द्वारा सद्भावपूर्वक किये गये समस्त कृत्य मुझे/हमें '
                   'स्वीकार्य होंगे तथा उनके परिणाम की जिम्मेदारी मुवक्किल की होगी। अधिवक्ता शुल्क के अभाव अथवा अन्य '
                   'उचित कारण से प्रकरण की पैरवी हेतु आबद्ध नहीं रहेंगे।</p>')
        out.append(f'<p class="cb-prelude">स्वीकृत है — अधिवक्ता {adv}'
                   + (f', पंजीयन क्रमांक {_esc(enrol)}' if enrol else '') + '।</p>')
    else:
        out.append('<p class="cb-prelude">All acts done in good faith by the said advocate shall be binding on me/us, '
                   'and the consequences shall be the client\'s responsibility. The advocate shall not be bound to '
                   'appear in the absence of fee or for other just cause.</p>')
        out.append(f'<p class="cb-prelude">Accepted — Advocate {adv}'
                   + (f', Enrolment No. {_esc(enrol)}' if enrol else '') + '.</p>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>{"स्थान" if hi else "Place"}: {_ph(a.get("place"), "________")}</div>')
    out.append(f'<div>{"दिनांक" if hi else "Date"}: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div>')
    out.append(f'<div style="margin-top:10pt">{"हस्ताक्षर मुवक्किल" if hi else "Signature of Client"}</div>'
               f'<div>({client})</div></div>')
    out.append(f'<div class="r"><div>{"हस्ताक्षर अधिवक्ता" if hi else "Signature of Advocate"}</div>'
               f'<div>({adv})</div>'
               + (f'<div>{"पंजीयन क्रमांक" if hi else "Enrolment No."}— {_esc(enrol)}</div>' if enrol else '')
               + '</div></div>')
    out.append('</div>')
    return "\n".join(out)


def render_hi(a: dict) -> str:
    return _render(a, hi=True)


def render_en(a: dict) -> str:
    a = dict(a or {})
    for _k in list(a):  # overlay any *_en value onto its base key → English-aware render
        if _k.endswith("_en") and a[_k] not in (None, ""):
            a[_k[:-3]] = a[_k]
    return _render(a, hi=False)


def field_spec(court: str = "") -> dict:
    flds = [
        F.f("court_name", "न्यायालय का नाम", "Court name", required=True, section="court"),
        F.f("case_no", "प्रकरण/अपराध क्रमांक", "Case/Crime no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("party_role", "पक्षकार की हैसियत", "Party role", section="parties",
            hint="आवेदक / प्रार्थी / अभियुक्त / वादी / प्रतिवादी"),
        F.f("client_name", "मुवक्किल का नाम", "Client name", F.NAME, True, "parties"),
        F.f("client_father", "पिता/पति का नाम", "Father/husband", F.NAME, section="parties"),
        F.f("client_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("opposite_party", "विपक्षी (वैकल्पिक)", "Opposite party (optional)", F.LONGTEXT, section="parties"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, True, "filing"),
        F.f("advocate_enrollment", "अधिवक्ता पंजीयन क्रमांक", "Advocate enrolment no.", section="filing"),
        F.f("place", "स्थान", "Place", section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.f("state_name", "राज्य", "State", section="parties", hint="मामले का राज्य (रिक्त रखने पर स्थान रिक्त)"))
    return F.build_spec("vakalatnama:any", flds, [], companions=["court-fee / welfare-stamp where applicable"])


SAMPLE = {
    "court_name": "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ग्वालियर (म.प्र.)",
    "court_name_en": "Court of the Judicial Magistrate First Class, Gwalior (M.P.)",
    "case_no": "", "case_year": "2026", "party_role": "आवेदक", "party_role_en": "Applicant",
    "client_name": "क ख", "client_name_en": "K. B.", "client_father": "य र", "client_father_en": "Y. R.",
    "client_address": "________, ग्वालियर", "client_address_en": "________, Gwalior",
    "opposite_party": "म.प्र. शासन", "opposite_party_en": "State of M.P.",
    "advocate_name": "____", "advocate_enrollment": "एम.पी./____/____", "advocate_enrollment_en": "MP/____/____",
    "place": "ग्वालियर", "place_en": "Gwalior", "filing_date": "__/__/2026",
    "state_name": "म.प्र.", "state_name_en": "M.P.",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="वकालतनामा — समीक्षा · canonical header · मानक प्राधिकार-खण्ड · द्विभाषी · "
                           "(प्रपत्र — कोई विधिक मत नहीं) · reviewed: false")
