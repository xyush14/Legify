"""Legal / demand notice — an advocate's notice to the opposite party.

AUTHOR-tier utility doc: a letter (To / Subject / under-instructions / facts /
demand / comply-within-N-days-or-legal-action / yours faithfully) on the
canonical A4 styling. Not a court filing. reviewed:false. No case law.
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
    days = _ph(a.get("compliance_days"), "15")
    client = _ph(a.get("client_name"), "मुवक्किल" if hi else "my client")
    out = ['<div class="doc-a4">']
    out.append(f'<div style="text-align:right">{("दिनांक: " if hi else "Date: ")}{_ph(a.get("notice_date"), date.today().strftime("%d/%m/%Y"))}</div>')
    out.append(f'<div style="text-align:center;text-decoration:underline;font-weight:700;font-size:13pt;margin:6pt 0">'
               + (("पंजीकृत डाक ए.डी. से" if a.get("by_rpad", True) else "") + " विधिक सूचना पत्र" if hi
                  else (("BY REGISTERED A.D. — " if a.get("by_rpad", True) else "") + "LEGAL NOTICE")) + '</div>')
    out.append(f'<p class="cb-prelude">{("सेवा में," if hi else "To,")}</p>')
    out.append(f'<p class="cb-prelude" style="margin-left:18pt">{_ph(a.get("recipient_name"), "प्राप्तकर्ता का नाम" if hi else "recipient name")}'
               f'<br>{_ph(a.get("recipient_address"), "पता" if hi else "address")}</p>')
    if a.get("subject"):
        out.append(f'<p class="cb-prelude">{("विषय: " if hi else "Subject: ")}<b>{_esc(a.get("subject"))}</b></p>')
    out.append(f'<p class="cb-prelude">{("महोदय," if hi else "Sir/Madam,")}</p>')
    lead = (f'मेरे मुवक्किल {client} के निर्देशानुसार आपको यह विधिक सूचना पत्र प्रेषित कर सूचित किया जाता है किः—'
            if hi else
            f'Under instructions from and on behalf of {client}, I hereby serve upon you this legal notice as under:—')
    out.append(f'<p class="cb-prelude">{lead}</p>')
    P = _chunks(a.get("facts_narrative")) or (['[शिकायत/तथ्य — आपके एवं मुवक्किल के मध्य का विवाद, खाली पंक्ति से अलग पैरा]'] if hi
                                              else ['[the grievance / facts of the dispute, one per blank-line para]'])
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{("यहकि, " if hi else "That ")}{_esc(p)}</li>')
    out.append('</ol>')
    demand = a.get("demand")
    if demand:
        out.append(f'<p class="cb-prelude"><b>{("मांग: " if hi else "Demand: ")}</b>{_esc(demand)}</p>')
    warn = (f'अतः आपको सूचित किया जाता है कि इस सूचना की प्राप्ति से {days} दिवस के भीतर उपरोक्त मांग की पूर्ति '
            f'करें, अन्यथा मेरे मुवक्किल आपके विरुद्ध समुचित सिविल एवं/अथवा आपराधिक विधिक कार्यवाही करने हेतु '
            f'बाध्य होंगे, जिसका समस्त व्यय, हानि एवं परिणाम आपके ऊपर होगा। इस सूचना की एक प्रति कार्यालय में '
            f'सुरक्षित रखी गई है।' if hi else
            f'You are therefore called upon to comply with the above demand within {days} days of receipt of '
            f'this notice, failing which my client shall be constrained to initiate appropriate civil and/or '
            f'criminal proceedings against you, entirely at your risk as to costs and consequences. A copy of '
            f'this notice is retained in my office.')
    out.append(f'<p class="cb-prelude">{warn}</p>')
    out.append(f'<div class="cb-sig"><div class="l"></div>'
               f'<div class="r"><div>{("भवदीय," if hi else "Yours faithfully,")}</div>'
               f'<div style="margin-top:14pt">({_ph(a.get("advocate_name"), "अधिवक्ता" if hi else "advocate")}) — '
               + ("एडवोकेट" if hi else "Advocate") + '</div>'
               f'<div>{_ph(a.get("advocate_address"), "अधिवक्ता पता" if hi else "advocate address")}</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def render_hi(a: dict) -> str: return _doc(a or {}, True)
def render_en(a: dict) -> str: return _doc(a or {}, False)


_TOGGLES = [
    F.toggle("by_rpad", "पंजीकृत डाक ए.डी. से", "By Registered A.D.", default=True),
]


def field_spec(court: str = "") -> dict:
    flds = [
        F.f("client_name", "मुवक्किल का नाम", "Client name", F.NAME, True, "parties"),
        F.f("recipient_name", "प्राप्तकर्ता का नाम", "Recipient name", F.NAME, True, "parties"),
        F.f("recipient_address", "प्राप्तकर्ता का पता", "Recipient address", F.ADDRESS, section="parties"),
        F.f("subject", "विषय", "Subject", section="court"),
        F.f("facts_narrative", "शिकायत / तथ्य", "Grievance / facts", F.LONGTEXT, True, "facts",
            hint="विवाद का विवरण — प्रत्येक पैरा खाली पंक्ति से अलग"),
        F.f("demand", "मांग (क्या चाहिए)", "Demand (what is sought)", F.LONGTEXT, section="facts"),
        F.f("compliance_days", "अनुपालन अवधि (दिन)", "Compliance period (days)", F.NUMBER, section="facts", default="15"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("advocate_address", "अधिवक्ता का पता", "Advocate address", F.ADDRESS, section="filing"),
        F.f("notice_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("legal_notice", flds, _TOGGLES, companions=[])


SAMPLE = {
    "client_name": "____", "recipient_name": "____", "recipient_address": "____, ग्वालियर (म.प्र.)",
    "subject": "____ के सम्बन्ध में विधिक सूचना", "compliance_days": "15",
    "facts_narrative": (
        "मेरे मुवक्किल एवं आपके मध्य ____ के सम्बन्ध में लेन-देन/अनुबन्ध हुआ था, जिसके अनुसार आप पर मेरे "
        "मुवक्किल की ____ राशि/दायित्व शेष है।\n\n"
        "बार-बार मांग करने के बाद भी आपके द्वारा उक्त दायित्व की पूर्ति नहीं की गई है।"
    ),
    "demand": "उपरोक्त राशि ब्याज सहित मेरे मुवक्किल को अदा करें।",
    "advocate_name": "____", "advocate_address": "____, ग्वालियर",
    "client_name_en": "____", "recipient_name_en": "____", "recipient_address_en": "____, Gwalior (M.P.)",
    "subject_en": "Legal notice regarding ____",
    "facts_narrative_en": (
        "there was a transaction/agreement between my client and you regarding ____, under which a sum/obligation "
        "of ____ remains due from you to my client.\n\n"
        "despite repeated demands you have failed to discharge the said obligation."
    ),
    "demand_en": "Pay the said amount with interest to my client.",
    "advocate_name_en": "____", "advocate_address_en": "____, Gwalior",
    "grounds": {"by_rpad": True},
    "notice_date": "__/06/2026",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="विधिक सूचना / Legal Notice — समीक्षा · AUTHORED utility doc (letter) · द्विभाषी · reviewed: false")
