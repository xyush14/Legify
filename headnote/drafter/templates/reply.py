"""Reply / जबाव — a respondent's para-wise answer to the opposite party's
application (bail, maintenance §125, DV §12, §311, claim, etc.).

Canonical-standard build, mirror-first from Vishnu ji's real जबाव filings
(benchmarks: "Jawav DV 12" / "Jawav 125 shyamsunder" / "Jawav 311"). A reply is
inherently a SCAFFOLD: the rebuttal is case-specific (it answers each numbered
para of the other side's application), so the lawyer supplies the responses; the
template supplies the canonical header, the verbatim जबाव idiom, and the fixed
opening / prayer.

Mirror notes (do NOT "improve"):
  • The respondent (अनावेदक / प्रत्यर्थी) files it; the original mover keeps their
    label (आवेदिका / आवेदक / परिवादी / व्यथित).
  • Title: `जबाव आवेदन पत्र अन्तर्गत <provision/Act>` (or just `जबाव` + what's replied to).
  • Opening: `अनावेदक की ओर से जबाव निम्न प्रकार प्रस्तुत है ः—`.
  • Each response is a `यहकि,` para that REFERENCES the application's पद क्रमांक and
    admits/denies it (`… असत्य होने से अस्वीकार है। वास्तविकता यह है कि …`). The lawyer
    writes the substance; we add the यहकि lead and the numbering frame.
  • Optional `विशेष निवेदन ः—` block (extra grounds the respondent highlights).
  • Prayer: accept the reply and DISMISS the applicant's application.
  • No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = []  # a reply argues facts on the record; citations (if any) at hearing.


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _chunks(text) -> list:
    return [x.strip() for x in str(text or "").split("\n\n") if x.strip()]


def _strip_lead(s: str) -> str:
    # avoid a double "यहकि," if the lawyer typed it; we add our own lead.
    s = s.strip()
    for lead in ("यहकि,", "यह कि,", "यहकि", "That ", "that "):
        if s.startswith(lead):
            return s[len(lead):].strip()
    return s


def _cfg(court):
    return {
        "sessions": dict(level="sessions", court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (म.प्र.)"),
        "hc":       dict(level="hc",       court_default="माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर"),
        "family":   dict(level="family",   court_default="न्यायालय माननीय कुटुम्ब न्यायालय, ............ (म.प्र.)"),
    }.get(court, dict(level="magistrate", court_default="न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)"))


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    c = _cfg(a.get("court") or "magistrate")
    g = a.get("grounds") or {}
    app_label = _esc(a.get("applicant_label") or "आवेदिका")
    res_label = _esc(a.get("respondent_label") or "अनावेदक")
    replying_to = _esc(a.get("replying_to") or "आवेदन पत्र")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])

    hdr = render_header({
        "side_label": "",
        "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "",
        "applicant_label": app_label, "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक का नाम")],
        "respondent_label": res_label, "respondent_desc": [_ph(a.get("respondent_name"), "अनावेदक का नाम")],
        "versus": "बनाम", "title_line": f"जबाव आवेदन पत्र अन्तर्गत {replying_to}",
    })

    P = []
    resp = _chunks(a.get("responses"))
    if resp:
        for ch in resp:
            P.append(f'यहकि, {_esc(_strip_lead(ch))}')
    else:
        P.append('<span class="ph">[विपक्षी आवेदन के प्रत्येक पद का उत्तर — प्रत्येक उत्तर खाली पंक्ति से अलग; '
                 'जैसे "आवेदन पत्र के पद क्रमांक—02 में वर्णित तथ्य असत्य होने से अस्वीकार है। वास्तविकता यह है कि …" '
                 '— "यहकि" स्वतः जुड़ जाएगा]</span>')
    if g.get("deny_prayer", True):
        P.append('यहकि, आवेदन पत्र की प्रार्थना मिथ्या एवं विधि विरुद्ध होने से अस्वीकार है।')
    special = _chunks(a.get("special_submission"))
    if special:
        P.append('<span class="cb-head">विशेष निवेदन ः—</span>')
        for ch in special:
            P.append(f'यहकि, {_esc(_strip_lead(ch))}')

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय महोदय,</p>')
    out.append(f'<p class="cb-prelude">{res_label} की ओर से जबाव निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः माननीय न्यायालय से सादर निवेदन है कि {res_label} का यह जबाव '
               f'स्वीकार कर {app_label} द्वारा प्रस्तुत {replying_to} निरस्त किये जाने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{_ph(a.get("respondent_name"), "अनावेदक")}</div><div>— {res_label}</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    c = _cfg(a.get("court") or "magistrate")
    g = a.get("grounds") or {}
    app_label = _esc(a.get("applicant_label_en") or "Applicant")
    res_label = _esc(a.get("respondent_label_en") or "Non-applicant")
    replying_to = _esc(a.get("replying_to_en") or a.get("replying_to") or "the application")
    court_name = a.get("court_name_en") or compose_court_name(c["level"], a.get("court_city_en") or a.get("court_city"), "M.P.", lang="en")

    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": app_label, "applicant_desc": [_ph(a.get("applicant_name_en") or a.get("applicant_name"), "applicant's name")],
        "respondent_label": res_label, "respondent_desc": [_ph(a.get("respondent_name_en") or a.get("respondent_name"), "non-applicant's name")],
        "versus": "Versus", "title_line": f"REPLY TO {replying_to.upper()}",
    })
    P = []
    for ch in _chunks(a.get("responses_en") or a.get("responses")):
        P.append(f'That {_esc(_strip_lead(ch))}')
    if g.get("deny_prayer", True):
        P.append('That the prayer of the application, being false and contrary to law, is denied.')
    special = _chunks(a.get("special_submission_en") or a.get("special_submission"))
    if special:
        P.append('<span class="cb-head">SPECIAL SUBMISSION:—</span>')
        for ch in special:
            P.append(f'That {_esc(_strip_lead(ch))}')
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append(f'<p class="cb-prelude">The {res_label} most respectfully submits this reply as under:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may '
               f'be pleased to accept this reply and dismiss {replying_to} filed by the {app_label}, in the '
               f'interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>{_ph(a.get("respondent_name_en") or a.get("respondent_name"), "Non-applicant")}</div>'
               f'<div>— {res_label}</div><div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("deny_prayer", "प्रार्थना अस्वीकार पैरा जोड़ें", "Add 'prayer denied' para", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("case_type", "प्रकरण प्रकार (वैकल्पिक)", "Case type (optional)", section="court"),
        F.f("replying_to", "किसका जबाव (धारा/अधिनियम)", "Replying to (provision / Act)", required=True, section="court",
            hint="जैसे: धारा 12 घरेलू हिंसा अधिनियम / धारा 125 दं.प्र.सं. / जमानत आवेदन पत्र"),
        F.f("applicant_name", "आवेदक/विपक्षी का नाम", "Applicant (opposite) name", F.NAME, True, "parties"),
        F.f("applicant_label", "आवेदक पक्ष का पद", "Applicant label", section="parties", default="आवेदिका",
            hint="आवेदिका / आवेदक / परिवादी / व्यथिता"),
        F.f("respondent_name", "अनावेदक (जबाव देने वाला) का नाम", "Respondent (replying) name", F.NAME, True, "parties"),
        F.f("respondent_label", "अनावेदक पक्ष का पद", "Respondent label", section="parties", default="अनावेदक",
            hint="अनावेदक / प्रत्यर्थी / अभियुक्त"),
        F.f("responses", "पद-वार जबाव", "Para-wise reply", F.LONGTEXT, True, "facts",
            ocr="order", hint="प्रत्येक पद का उत्तर खाली पंक्ति से अलग — विपक्षी आवेदन OCR/वॉइस से भर सकते हैं; 'यहकि' स्वतः जुड़ता है"),
        F.f("special_submission", "विशेष निवेदन (वैकल्पिक)", "Special submission (optional)", F.LONGTEXT, section="facts",
            hint="अतिरिक्त आधार जो हाईलाइट करना है — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec(f"reply:{court}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions", "hc", "family"]},
                        companions=["vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court": "magistrate", "court_city": "ग्वालियर",
    "case_number": "____/2021", "replying_to": "धारा 12 घरेलू हिंसा अधिनियम",
    "applicant_name": "श्रीमती ____", "applicant_label": "व्यथिता/आवेदिका",
    "respondent_name": "____ व अन्य", "respondent_label": "अनावेदकगण",
    "responses": (
        "पद क्रमांक—01 कानून का विषय होने से जबाव की आवश्यकता नहीं है।\n\n"
        "आवेदन पत्र के पद क्रमांक—02 में विवाह होना स्वीकार है, परन्तु दान-दहेज दिया जाना पूर्णतः अस्वीकार है। "
        "वास्तविकता यह है कि विवाह बिना किसी दान-दहेज के साधारण रूप से सम्पन्न हुआ था।\n\n"
        "आवेदन पत्र के पद क्रमांक—03 असत्य एवं मनगढ़ंत होने से अस्वीकार है। वास्तविकता यह है कि आवेदिका स्वयं "
        "अपनी इच्छा से समस्त स्त्रीधन सहित मायके में निवास कर रही है; अनावेदक के आधिपत्य में कोई स्त्रीधन नहीं है।"
    ),
    "special_submission": (
        "आवेदिका द्वारा इसी तथ्य पर पृथक से धारा 125 दं.प्र.सं. का प्रकरण भी प्रस्तुत किया गया है जिसमें "
        "भरण-पोषण राशि स्वीकृत हो चुकी है; अतः वर्तमान प्रकरण में पुनः वही अनुतोष देय नहीं है।"
    ),
    "court_city_en": "Gwalior",
    "replying_to_en": "the application under Section 12 of the PWDV Act",
    "applicant_name_en": "Smt. ____", "respondent_name_en": "____ & ors.",
    "applicant_label_en": "Aggrieved/Applicant", "respondent_label_en": "Non-applicants",
    "responses_en": (
        "Para 1 being a matter of law needs no reply.\n\n"
        "the factum of marriage in para 2 is admitted, but the giving of any dowry is wholly denied; in truth "
        "the marriage was solemnised simply, without any dowry.\n\n"
        "para 3 is false and concocted and is denied; in truth the applicant is residing at her parental home "
        "of her own accord along with all her stridhan, none of which is in the respondents' possession."
    ),
    "special_submission_en": (
        "the applicant has also filed a separate proceeding under Section 125 CrPC on the same facts in which "
        "maintenance already stands granted; the same relief is therefore not payable again here."
    ),
    "grounds": {"deny_prayer": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="जबाव / Reply — समीक्षा · canonical header · द्विभाषी · विष्णु जी की जबाव फाइलिंग "
                           "से अक्षरशः idiom · reviewed: false")
