"""§138 NI Act — accused-side objection: statutory demand notice not served →
complaint not maintainable (proviso (b) to §138 not satisfied).

Canonical build, mirror-first from Vishnu ji's real "138 (B)" filing — the accused
contends the post-office record shows delivery to a branch office (not receipt by
the accused), and no document proves the accused received the mandatory notice, so
the §138 cause of action is not made out. The accused-side counterpart to the
cheque complaint (cheque_138.py is complainant-side). No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "C.C. Alavi Haji v. Palapetty Muhammed (2007) 6 SCC 555", "point": "deemed service of notice — contest both ways at hearing", "verified": False},
    {"case": "Subodh S. Salaskar v. Jayprakash M. Shah (2008) 13 SCC 689", "point": "strict compliance with §138 proviso timelines", "verified": False},
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
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), a.get("state_name") or "") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "परिवाद क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "एन.आई.एक्ट", "applicant_label": "परिवादी",
        "applicant_desc": [_ph(a.get("complainant_name"), "परिवादी का नाम")],
        "respondent_label": "अभियुक्त", "respondent_desc": [_ph(a.get("accused_name"), "अभियुक्त का नाम")],
        "versus": "बनाम",
        "title_line": "आवेदन पत्र अन्तर्गत धारा 138 परक्राम्य लिखित अधिनियम (सूचना-पत्र तामील न होने बाबत्)",
    })
    P = ['यहकि, परिवादी द्वारा माननीय न्यायालय के समक्ष मिथ्या तथ्यों के आधार पर एक परिवाद पत्र प्रस्तुत किया '
         'गया है, जिसमें प्रार्थी को तलब किया जाकर प्रार्थी जमानत पर है तथा प्रकरण अपराध विवरण/आरोप हेतु नियत है।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[सूचना-पत्र तामील का दोष — पोस्ट आँफिस दस्तावेज में प्रार्थी द्वारा नोटिस '
                 'प्राप्ति का कोई उल्लेख नहीं, ब्रांच आँफिस में डिलीवरी आदि — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("notice_not_served", True):
        P.append('यहकि, परिवादी द्वारा धारा 138 परक्राम्य लिखित अधिनियम के परन्तुक (ख) के अधीन विधिमान्य '
                 'सूचना-पत्र प्रार्थी को कभी तामील नहीं कराया गया, न ही अभिलेख पर ऐसा कोई दस्तावेज है जिससे यह '
                 'प्रकट हो कि प्रार्थी द्वारा उक्त सूचना-पत्र प्राप्त किया गया हो।')
    if g.get("not_maintainable", True):
        P.append('यहकि, अनिवार्य मांग-सूचना की विधिमान्य तामील के अभाव में धारा 138 के आवश्यक अवयव पूर्ण नहीं '
                 'होते, अतः प्रार्थी के विरुद्ध प्रस्तुत परिवाद विधितः चलने योग्य नहीं है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           '<p class="cb-prelude">प्रार्थी/अभियुक्त की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि अनिवार्य सूचना-पत्र की तामील के '
               'अभाव में प्रस्तुत परिवाद को निरस्त कर प्रार्थी को आरोप से उन्मोचित/दोषमुक्त किये जाने की कृपा '
               'करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("accused_name"), "प्रार्थी")}</div><div>— अभियुक्त</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), a.get("state_name") or "", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Complaint No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Complainant", "applicant_desc": [_ph(a.get("complainant_name"), "complainant")],
        "respondent_label": "Accused", "respondent_desc": [_ph(a.get("accused_name"), "accused")],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 138 OF THE NI ACT "
                                          "(NON-SERVICE OF THE STATUTORY NOTICE)"})
    P = ['That the complainant has filed a complaint on false grounds, in which the applicant was summoned, is '
         'on bail, and the matter is fixed for notice of accusation / charge.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("notice_not_served", True):
        P.append('That the complainant never validly served on the applicant the statutory demand notice '
                 'required under the proviso (b) to Section 138 NI Act, and there is no document on record to '
                 'show that the applicant received the said notice.')
    if g.get("not_maintainable", True):
        P.append('That in the absence of valid service of the mandatory demand notice, the essential '
                 'ingredients of Section 138 are not made out, and the complaint is not maintainable against '
                 'the applicant.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The applicant / accused most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>It is therefore most respectfully prayed that, in the absence of '
               'service of the mandatory notice, the complaint be dismissed and the applicant discharged / '
               'acquitted, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("accused_name"), "Applicant")}</div><div>— Accused</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("notice_not_served", "विधिमान्य सूचना तामील नहीं — पैरा", "Statutory notice not served — para", default=True),
    F.toggle("not_maintainable", "परिवाद चलने योग्य नहीं — पैरा", "Complaint not maintainable — para", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("state_name", "राज्य", "State", section="court", hint="मामले का राज्य (रिक्त → स्थान रिक्त)"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "परिवाद क्रमांक", "Complaint no.", required=True, section="court", ocr="order"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("complainant_name", "परिवादी का नाम", "Complainant name", F.NAME, True, "parties"),
        F.f("accused_name", "प्रार्थी/अभियुक्त का नाम", "Accused name", F.NAME, True, "parties"),
        F.f("facts_narrative", "सूचना-पत्र तामील का दोष", "Notice-service defect", F.LONGTEXT, True, "facts",
            ocr="order", hint="पोस्ट आँफिस दस्तावेज, ब्रांच डिलीवरी, प्राप्ति का अभाव — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    flds.append(F.f("case_type", "प्रकरण प्रकार", "Case type", section="court", hint="जैसे आर.सी.टी. / सत्रवाद — शीर्षक का प्रकरण-कोड"))
    return F.build_spec("ni_138_dismiss", flds, _TOGGLES, companions=["vakalatnama"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2017", "case_type": "एन.आई.एक्ट",
    "complainant_name": "____", "accused_name": "श्रीमती ____",
    "facts_narrative": (
        "परिवादी द्वारा प्रकरण के साथ प्रस्तुत पोस्ट आँफिस दस्तावेज में दिनांक ____ को भेजा गया आइटम ब्रांच "
        "आँफिस में डिलीवर्ड होना दर्शाया गया है, किन्तु उसमें प्रार्थी द्वारा सूचना-पत्र प्राप्त किये जाने का "
        "कोई उल्लेख नहीं है।\n\n"
        "परिवादी द्वारा नोटिस की तामील की पुष्टि हेतु पोस्ट आँफिस में कोई आवेदन प्रस्तुत किया जाना भी नहीं "
        "दर्शाया गया है; वास्तविकता में प्रार्थी द्वारा उक्त सूचना-पत्र प्राप्त नहीं किया गया।"
    ),
    "court_city_en": "Gwalior", "complainant_name_en": "____", "accused_name_en": "Smt. ____",
    "facts_narrative_en": (
        "the post-office document filed with the complaint shows the item sent on ____ as 'delivered' to a "
        "branch office, but bears no endorsement of the applicant having received the notice.\n\n"
        "the complainant has not shown any application to the post office to ascertain service; in fact the "
        "applicant never received the said notice."
    ),
    "grounds": {"notice_not_served": True, "not_maintainable": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="§138 NI — सूचना तामील आपत्ति (accused-side) — समीक्षा · द्विभाषी · "
                           "विष्णु जी की 138(B) फाइलिंग से अक्षरशः · reviewed: false")
