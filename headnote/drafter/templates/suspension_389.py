"""Suspension of sentence + bail pending appeal — §430 BNSS (§389 CrPC).

Mostly AUTHOR-tier: his §389 filings (HC_- 389, Apil HC 389/Dhaniram) confirm the
header + title ("आवेदन पत्र अन्तर्गत धारा 389 द.प्र.सं./430 भा.ना.सु.सं.") and the
affidavit, but the grounds body sits behind the affidavit pages — so the GROUNDS
are authored from the standard §389 structure (convicted → appeal pending → was on
bail and did not misuse → arguable grounds + long pendency → suspend sentence and
release on bail pending appeal) in his appeal house-style. reviewed:false.
No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Bhagwan Rama Shinde Gosai v. State of Gujarat (1999) 4 SCC 421", "point": "where sentence is short, suspend rather than let the appeal become infructuous", "verified": False},
    {"case": "Kishori Lal v. Rupa (2004) 7 SCC 638", "point": "relevant considerations for suspension of sentence pending appeal", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _secs(x, sep=" एवं "): return (sep.join(_esc(s) for s in x if str(s).strip()) or "................") if isinstance(x,(list,tuple)) else (_esc(x) if x and str(x).strip() else "................")
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


def _cfg(court):
    if court == "sessions":
        return dict(level="sessions", case_code="आपराधिक अपील क्रमांक",
                    court_default="न्यायालय माननीय सत्र न्यायाधीश महोदय, ............ (म.प्र.)")
    return dict(level="hc", case_code="आपराधिक अपील क्रमांक",
                court_default="माननीय उच्च न्यायालय मध्यप्रदेश, खण्डपीठ ग्वालियर")


def render_hi(a: dict) -> str:
    a = a or {}; c = _cfg(a.get("court") or "hc"); g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "म.प्र. शासन")
    tc = _ph(a.get("trial_court"), "विचारण न्यायालय"); cd = _ph(a.get("conviction_date"), "दोषसिद्धि दिनांक")
    secs = _secs(a.get("sections_convicted")); sent = _ph(a.get("sentence_passed"), "दण्डादेश")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or c["court_default"])
    hdr = render_header({
        "side_label": "अपीलार्थी की ओर से", "court_name": court_name, "case_code": c["case_code"],
        "case_number": a.get("appeal_number") or "", "case_year": a.get("appeal_year") or str(date.today().year),
        "applicant_label": "अपीलार्थी", "applicant_desc": [_ph(a.get("appellant_name"), "अपीलार्थी का नाम")],
        "respondent_label": "प्रतिअपीलार्थी", "respondent_desc": [state],
        "versus": "विरुद्ध", "title_line": "आवेदन पत्र अन्तर्गत धारा 430 भा.ना.सु.सं. (389 दं.प्र.सं.)",
    })
    P = [f'यहकि, अपीलार्थी को विद्वान {tc} द्वारा दिनांक {cd} को धारा {secs} में दोषसिद्ध करते हुये {sent} से '
         f'दण्डित किया गया है, जिसके विरुद्ध अपीलार्थी की आपराधिक अपील माननीय न्यायालय के समक्ष प्रस्तुत/'
         f'लंबित है।']
    facts = _chunks(a.get("facts_narrative"))
    for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    if g.get("on_bail_during_trial", True):
        P.append('यहकि, अपीलार्थी विचारण के दौरान जमानत पर रहा है तथा उसके द्वारा प्रदत्त स्वतंत्रता का कभी '
                 'दुरुपयोग नहीं किया गया; अपीलार्थी के फरार होने अथवा साक्ष्य से छेड़छाड़ की कोई आशंका नहीं है।')
    if g.get("arguable_merit", True):
        P.append('यहकि, प्रस्तुत अपील में विचारणीय एवं सारगर्भित आधार विद्यमान हैं तथा अपील के सफल होने की '
                 'युक्तियुक्त सम्भावना है।')
    if g.get("long_pendency", True):
        P.append('यहकि, अपील के निराकरण में पर्याप्त समय लगना सम्भावित है, ऐसी स्थिति में दण्डादेश निलंबित न '
                 'किये जाने पर अपीलार्थी द्वारा अधिकांश सजा भुगत ली जायेगी और अपील के सफल होने पर वह निरर्थक '
                 'हो जायेगी।')
    if g.get("ready_bond", True):
        P.append('यहकि, अपीलार्थी माननीय न्यायालय द्वारा अधिरोपित समस्त प्रतिभूति बन्धपत्र भरने एवं शर्तों के '
                 'पालन हेतु तत्पर है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           '<p class="cb-prelude">अपीलार्थी की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>अतः माननीय न्यायालय से सादर निवेदन है कि अपील के अन्तिम निराकरण तक '
               'अपीलार्थी के विरुद्ध पारित दण्डादेश को धारा 430 भा.ना.सु.सं. (389 दं.प्र.सं.) के अधीन निलंबित '
               'कर अपीलार्थी को उपयुक्त प्रतिभूति पर जमानत पर रिहा किये जाने का आदेश पारित करने की कृपा '
               'करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("appellant_name"), "अपीलार्थी")}</div><div>— अपीलार्थी</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); c = _cfg(a.get("court") or "hc"); g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "State of M.P.")
    tc = _ph(a.get("trial_court"), "the trial court"); cd = _ph(a.get("conviction_date"), "date of conviction")
    secs = _secs(a.get("sections_convicted"), sep=" and "); sent = _ph(a.get("sentence_passed"), "the sentence")
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "On behalf of the appellant", "court_name": court_name, "case_code": "Criminal Appeal No.",
        "case_number": a.get("appeal_number") or "", "case_year": a.get("appeal_year") or str(date.today().year),
        "applicant_label": "Appellant", "applicant_desc": [_ph(a.get("appellant_name"), "appellant")],
        "respondent_label": "Respondent", "respondent_desc": [state],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 430 BNSS, 2023 (SECTION 389 CrPC, 1973) "
                                          "— SUSPENSION OF SENTENCE & BAIL PENDING APPEAL"})
    P = [f'That the appellant was convicted by the learned {tc} on {cd} under {secs} and sentenced to {sent}, '
         f'against which the appellant\'s criminal appeal is filed / pending before this Hon\'ble Court.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("on_bail_during_trial", True):
        P.append('That the appellant remained on bail during the trial and never misused that liberty; there is '
                 'no apprehension of the appellant absconding or tampering with evidence.')
    if g.get("arguable_merit", True):
        P.append('That the appeal raises arguable and substantial grounds with a reasonable prospect of success.')
    if g.get("long_pendency", True):
        P.append('That the appeal is likely to take considerable time; if the sentence is not suspended, the '
                 'appellant will have undergone most of it and a successful appeal would be rendered '
                 'infructuous.')
    if g.get("ready_bond", True):
        P.append('That the appellant is ready to furnish the bonds and abide by all conditions imposed by this '
                 'Hon\'ble Court.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The appellant most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>It is therefore most respectfully prayed that, pending final disposal '
               'of the appeal, the sentence passed against the appellant be suspended under Section 430 BNSS '
               '(Section 389 CrPC) and the appellant be released on bail on suitable security, in the interest '
               'of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("appellant_name"), "Appellant")}</div><div>— Appellant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("on_bail_during_trial", "विचारण में जमानत पर — दुरुपयोग नहीं", "Was on bail in trial — no misuse", default=True),
    F.toggle("arguable_merit", "अपील में विचारणीय आधार — पैरा", "Arguable grounds — para", default=True),
    F.toggle("long_pendency", "लम्बी पेंडेंसी → सजा भुगत जायेगी", "Long pendency → sentence undergone", default=True),
    F.toggle("ready_bond", "बन्धपत्र हेतु तत्पर — पैरा", "Ready to furnish bonds — para", default=True),
]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर / बैंच", "District / Bench", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("appeal_number", "अपील क्रमांक", "Appeal no.", section="court"),
        F.f("appeal_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("appellant_name", "अपीलार्थी का नाम", "Appellant name", F.NAME, True, "parties"),
        F.f("state_name", "प्रतिअपीलार्थी (राज्य)", "Respondent (State)", section="parties", default="म.प्र. शासन"),
        F.f("trial_court", "विचारण न्यायालय", "Trial court", required=True, section="order",
            hint="जिसने दोषसिद्ध किया — जैसे न्यायिक दण्डाधिकारी / सत्र न्यायालय ____"),
        F.f("conviction_date", "दोषसिद्धि दिनांक", "Date of conviction", F.DATE, True, "order"),
        F.f("sections_convicted", "दोषसिद्धि की धाराएं", "Sections convicted", F.SECTION_LIST, True, "order"),
        F.f("sentence_passed", "पारित दण्डादेश", "Sentence passed", required=True, section="order",
            hint="जैसे: 02 वर्ष का कारावास एवं ____ रु. अर्थदण्ड"),
        F.f("facts_narrative", "अतिरिक्त तथ्य (वैकल्पिक)", "Additional facts (optional)", F.LONGTEXT, section="facts",
            hint="जैसे: आयु/स्वास्थ्य/अवधि भुगती जा चुकी — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec(f"suspension_389:{court}", flds, _TOGGLES,
                        variants={"court": ["hc", "sessions"]}, companions=["vakalatnama", "certified copy of judgment"])


SAMPLE = {
    "court": "hc", "court_city": "ग्वालियर", "appeal_number": "____/2026",
    "appellant_name": "____", "state_name": "म.प्र. शासन",
    "trial_court": "विद्वान न्यायिक दण्डाधिकारी प्रथम श्रेणी ____",
    "conviction_date": "__/__/2026", "sections_convicted": ["323", "325 भा.द.वि."],
    "sentence_passed": "02 वर्ष का कारावास एवं अर्थदण्ड",
    "facts_narrative": (
        "अपीलार्थी वृद्ध एवं अस्वस्थ है तथा परिवार का एकमात्र कमाने वाला सदस्य है; अपीलार्थी पूर्व से ही "
        "दण्डादेश की कुछ अवधि भुगत चुका है।"
    ),
    "court_city_en": "Gwalior", "appellant_name_en": "____", "state_name_en": "State of M.P.",
    "trial_court_en": "the learned JMFC ____", "sections_convicted_en": ["323", "325 IPC"],
    "sentence_passed_en": "2 years' imprisonment and fine",
    "facts_narrative_en": (
        "the appellant is aged and unwell and is the sole breadwinner of the family; the appellant has already "
        "undergone part of the sentence."
    ),
    "grounds": {"on_bail_during_trial": True, "arguable_merit": True, "long_pendency": True, "ready_bond": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="दण्डादेश निलंबन + जमानत पेंडिंग अपील (धारा 430 · 389) — समीक्षा · header/title mirror, "
                           "grounds AUTHORED from framework · द्विभाषी · reviewed: false")
