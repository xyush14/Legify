"""General affidavit (शपथ पत्र) — a standalone sworn affidavit for any purpose.

AUTHOR-tier utility doc: deponent block + numbered sworn statements (the lawyer
fills) + verification, on the canonical A4 styling. No court-party machinery
(an affidavit has a deponent, not a versus). reviewed:false. No case law.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import doc_page
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


def _doc(a, hi):
    a = a if hi else _overlay_en(a)
    L = ("नाम", "पिता/पति का नाम", "आयु", "व्यवसाय", "निवासी") if hi else ("Name", "Father's/husband's name", "Age", "Occupation", "Residence")
    dep = _ph(a.get("deponent_name"), "शपथकर्ता" if hi else "deponent")
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    authority = a.get("authority")
    purpose = a.get("purpose")
    swear = ("मैं उक्त शपथकर्ता शपथपूर्वक सत्य कथन करता/करती हूँ किः—" if hi
             else "I, the deponent above-named, do solemnly affirm and state as under:—")
    title = "शपथ पत्र" if hi else "AFFIDAVIT"
    stmts = _chunks(a.get("statements"))
    if not stmts:
        stmts = (['[शपथ-कथन यहाँ — प्रत्येक कथन खाली पंक्ति से अलग; "यहकि" स्वतः जुड़ेगा]'] if hi
                 else ['[the sworn statements here — one per blank-line-separated para]'])
    age = _ph(a.get("deponent_age"), "..")
    out = ['<div class="doc-a4">']
    if authority:
        out.append(f'<div style="text-align:center;font-weight:700">{_esc(authority)}</div>')
    out.append(f'<div style="text-align:center;text-decoration:underline;font-weight:700;font-size:14pt;margin:12pt 0">{title}</div>')
    if purpose:
        out.append(f'<p class="cb-prelude" style="text-align:center">{( "विषय: " if hi else "Re: ")}{_esc(purpose)}</p>')
    out.append('<table class="cb-table" style="max-width:64%">'
               f'<tr><td>{L[0]}</td><td>{dep}</td></tr>'
               f'<tr><td>{L[1]}</td><td>{_ph(a.get("deponent_father"), "—")}</td></tr>'
               f'<tr><td>{L[2]}</td><td>{age} {"वर्ष" if hi else "yrs"}</td></tr>'
               f'<tr><td>{L[3]}</td><td>{_ph(a.get("deponent_occupation"), "—")}</td></tr>'
               f'<tr><td>{L[4]}</td><td>{_ph(a.get("deponent_address"), "—")}</td></tr>'
               '</table>')
    out.append(f'<p class="cb-prelude">{swear}</p>')
    out.append('<ol class="cb-paras">')
    for s in stmts:
        s = s.strip()
        for lead in ("यहकि,", "That ", "that "):
            if s.startswith(lead): s = s[len(lead):].strip()
        out.append(f'<li>{("यहकि, " if hi else "That ")}{_esc(s)}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>{("दिनांक: " if hi else "Date: ")}{fd}</div>'
               f'<div>{("स्थान: " if hi else "Place: ")}{_ph(a.get("place"), "—")}</div></div>'
               f'<div class="r"><div style="margin-top:18pt">{("हस्ताक्षर शपथकर्ता" if hi else "Signature of the Deponent")}</div>'
               f'<div>({dep})</div></div></div>')
    out.append(f'<div class="cb-block-label">{("सत्यापन" if hi else "VERIFICATION")}</div>')
    out.append('<p class="cb-prelude">' + (
        "मैं शपथकर्ता शपथपूर्वक सत्यापित करता/करती हूँ कि उपरोक्त शपथ पत्र की समस्त सामग्री मेरे ज्ञान व विश्वास "
        "के आधार पर सत्य व सही है, जिसमें कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।" if hi else
        "I, the deponent, verify that the contents of the above affidavit are true and correct to my knowledge "
        "and belief; nothing is false and nothing has been concealed.") + '</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>{("दिनांक: " if hi else "Date: ")}{fd}</div></div>'
               f'<div class="r"><div style="margin-top:18pt">{("हस्ताक्षर शपथकर्ता" if hi else "Signature of the Deponent")}</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def render_hi(a: dict) -> str: return _doc(a or {}, True)
def render_en(a: dict) -> str: return _doc(a or {}, False)


_TOGGLES = []


def field_spec(court: str = "") -> dict:
    flds = [
        F.f("authority", "समक्ष (न्यायालय/प्राधिकारी) — वैकल्पिक", "Before (court/authority) — optional", section="court",
            hint="जैसे: माननीय न्यायालय ____ / नोटरी पब्लिक — रिक्त भी छोड़ सकते हैं"),
        F.f("purpose", "प्रयोजन (वैकल्पिक)", "Purpose (optional)", section="court", hint="जैसे: पहचान/पता/आय/नाम-परिवर्तन हेतु"),
        F.f("deponent_name", "शपथकर्ता का नाम", "Deponent name", F.NAME, True, "parties"),
        F.f("deponent_father", "पिता/पति का नाम", "Father's/husband's name", F.NAME, section="parties"),
        F.f("deponent_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("deponent_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("deponent_address", "पता", "Address", F.ADDRESS, section="parties"),
        F.f("statements", "शपथ-कथन", "Sworn statements", F.LONGTEXT, True, "facts",
            hint="प्रत्येक कथन खाली पंक्ति से अलग — 'यहकि' स्वतः जुड़ता है"),
        F.f("place", "स्थान", "Place", section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("general_affidavit", flds, _TOGGLES, companions=[])


SAMPLE = {
    "authority": "माननीय न्यायालय ____", "purpose": "तथ्यों के समर्थन हेतु",
    "deponent_name": "____", "deponent_father": "श्री ____", "deponent_age": "35",
    "deponent_occupation": "____", "deponent_address": "____, ग्वालियर (म.प्र.)",
    "statements": (
        "मैं शपथकर्ता उपरोक्त प्रकरण/प्रयोजन से भली-भाँति परिचित हूँ तथा इसके तथ्यों की मुझे पूर्ण जानकारी है।\n\n"
        "इस शपथ पत्र में वर्णित समस्त तथ्य मेरे निजी ज्ञान व विश्वास से सत्य व सही हैं।"
    ),
    "place": "ग्वालियर",
    "authority_en": "the Hon'ble Court ____", "purpose_en": "in support of the facts",
    "deponent_name_en": "____", "deponent_father_en": "Shri ____", "deponent_occupation_en": "____",
    "deponent_address_en": "____, Gwalior (M.P.)", "place_en": "Gwalior",
    "statements_en": (
        "I, the deponent, am well acquainted with the above matter/purpose and have full knowledge of its facts.\n\n"
        "all the facts stated in this affidavit are true and correct to my personal knowledge and belief."
    ),
    "filing_date": "__/06/2026",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="शपथ पत्र / General Affidavit — समीक्षा · AUTHORED utility doc · द्विभाषी · reviewed: false")
