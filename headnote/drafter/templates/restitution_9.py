"""Restitution of conjugal rights — §9 Hindu Marriage Act (Family Court).

Canonical build, mirror-first from Vishnu ji's real §9 HMA petition (benchmark:
"dhara 9 Kamlesh baghel"). The petitioner seeks an order that the respondent
resume cohabitation, the respondent having withdrawn from the society of the
petitioner without reasonable cause. A scaffold: the marriage narrative is
case-specific (lawyer fills); the template carries the canonical Family-Court
header, the §9 idiom and the fixed willing-to-cohabit / jurisdiction grounds.
No case law in the body.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Samar Ghosh v. Jaya Ghosh (2007) 4 SCC 511", "point": "mental cruelty (defensive — if desertion/cruelty pleaded against)", "verified": False},
]


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_CD = "न्यायालय माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय ............ (म.प्र.)"


def render_hi(a: dict) -> str:
    a = a or {}; g = a.get("grounds") or {}
    pl = _esc(a.get("applicant_label") or "आवेदक"); rl = _esc(a.get("respondent_label") or "अनावेदिका")
    my = _ph(a.get("marriage_year"), "वर्ष ____"); mp = _ph(a.get("marriage_place"), "विवाह स्थान")
    court_name = a.get("court_name") or compose_court_name("family", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "हि.वि.अधि.", "applicant_label": pl,
        "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक का नाम")],
        "respondent_label": rl, "respondent_desc": [_ph(a.get("respondent_name"), "अनावेदिका का नाम")],
        "versus": "बनाम",
        "title_line": "आवेदन पत्र अन्तर्गत धारा 9 हिन्दू विवाह अधिनियम वास्ते वैवाहिक सम्बन्धों की पुर्नस्थापना बावत्",
    })
    P = [f'यहकि, {pl} का विवाह {rl} के साथ {my} में हिन्दू रीति-रिवाज से {mp} में सम्पन्न हुआ था।']
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[विवाह के पश्चात् के तथ्य — अनावेदिका का आचरण, सहवास त्याग, संतान, '
                 'समझाइश के प्रयास — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("willing_cohabit", True):
        P.append(f'यहकि, {rl} द्वारा बिना किसी उचित एवं विधिसम्मत कारण के {pl} का सहवास एवं समाज त्याग दिया '
                 f'गया है, जबकि {pl} आज भी {rl} के साथ वैवाहिक जीवन का निर्वाह करने हेतु तत्पर एवं तैयार है।')
    if g.get("jurisdiction", True):
        P.append(f'यहकि, पक्षकारों का विवाह एवं अन्तिम साथ निवास माननीय न्यायालय की अधिकारिता क्षेत्र में रहा '
                 f'है, अतः माननीय न्यायालय को प्रकरण का श्रवणाधिकार है।')
    if g.get("no_other", True):
        P.append(f'यहकि, {pl} द्वारा इस सम्बन्ध में अन्य कोई आवेदन/प्रकरण किसी न्यायालय में प्रस्तुत अथवा '
                 f'लंबित नहीं है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय न्यायालय,</p>',
           f'<p class="cb-prelude">{pl} की ओर से आवेदन निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः माननीय न्यायालय से सादर निवेदन है कि {rl} को {pl} के साथ '
               f'वैवाहिक सम्बन्धों की पुर्नस्थापना (restitution of conjugal rights) हेतु आदेशित किये जाने की '
               f'कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदक")}</div><div>— {pl}</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    pl = _esc(a.get("applicant_label_en") or "Petitioner"); rl = _esc(a.get("respondent_label_en") or "Respondent")
    my = _ph(a.get("marriage_year"), "year ____"); mp = _ph(a.get("marriage_place"), "place of marriage")
    court_name = a.get("court_name") or compose_court_name("family", a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": pl, "applicant_desc": [_ph(a.get("applicant_name"), "petitioner")],
        "respondent_label": rl, "respondent_desc": [_ph(a.get("respondent_name"), "respondent")],
        "versus": "Versus", "title_line": "PETITION UNDER SECTION 9 OF THE HINDU MARRIAGE ACT, 1955 "
                                          "— FOR RESTITUTION OF CONJUGAL RIGHTS"})
    P = [f'That the {pl} was married to the {rl} in {my} according to Hindu rites and ceremonies at {mp}.']
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("willing_cohabit", True):
        P.append(f'That the {rl} has withdrawn from the society of the {pl} without any reasonable or lawful '
                 f'cause, whereas the {pl} is even now ready and willing to live with the {rl} and to discharge '
                 f'all marital obligations.')
    if g.get("jurisdiction", True):
        P.append('That the marriage and the last residence of the parties fall within the jurisdiction of this '
                 'Hon\'ble Court, which has jurisdiction to entertain the petition.')
    if g.get("no_other", True):
        P.append(f'That the {pl} has not filed any other petition / proceeding in this regard in any court, nor '
                 f'is any such matter pending.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           f'<p class="cb-prelude">The {pl} most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that the {rl} be directed to '
               f'restitution of conjugal rights with the {pl}, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "Petitioner")}</div><div>— {pl}</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


_TOGGLES = [
    F.toggle("willing_cohabit", "बिना उचित कारण त्याग + तत्पर — पैरा", "Withdrawal w/o cause + willing — para", default=True),
    F.toggle("jurisdiction", "श्रवणाधिकार पैरा", "Jurisdiction para", default=True),
    F.toggle("no_other", "अन्य कोई प्रकरण नहीं — पैरा", "No other proceeding — para", default=True),
]


def field_spec(court: str = "family") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → कुटुम्ब न्यायालय"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("applicant_name", "आवेदक का नाम", "Petitioner name", F.NAME, True, "parties"),
        F.f("applicant_label", "आवेदक पक्ष का पद", "Petitioner label", section="parties", default="आवेदक",
            hint="आवेदक (पति) / आवेदिका (पत्नी)"),
        F.f("respondent_name", "अनावेदिका/अनावेदक का नाम", "Respondent name", F.NAME, True, "parties"),
        F.f("respondent_label", "अनावेदक पक्ष का पद", "Respondent label", section="parties", default="अनावेदिका"),
        F.f("marriage_year", "विवाह वर्ष", "Year of marriage", section="facts"),
        F.f("marriage_place", "विवाह स्थान", "Place of marriage", section="facts"),
        F.f("facts_narrative", "विवाह-पश्चात् तथ्य", "Post-marriage facts", F.LONGTEXT, True, "facts",
            hint="अनावेदिका का आचरण, सहवास त्याग, संतान, समझाइश — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("restitution_9", flds, _TOGGLES, companions=["vakalatnama", "marriage proof"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2023", "case_type": "हि.वि.अधि.",
    "applicant_name": "____", "applicant_label": "आवेदक",
    "respondent_name": "श्रीमती ____", "respondent_label": "अनावेदिका",
    "marriage_year": "2006", "marriage_place": "ग्राम ____, जिला ग्वालियर",
    "facts_narrative": (
        "विवाह के पश्चात् कुछ समय तक दाम्पत्य जीवन सामान्य रहा तथा पक्षकारों से संतानें उत्पन्न हुईं।\n\n"
        "अनावेदिका बिना किसी उचित कारण के आवेदक से पृथक रहने की जिद करने लगी और अन्ततः समस्त सामान सहित मायके "
        "चली गई; आवेदक द्वारा अनेक प्रयास एवं समझाइश के बाद भी अनावेदिका साथ रहने हेतु तैयार नहीं हुई।"
    ),
    "court_city_en": "Gwalior", "applicant_name_en": "____", "respondent_name_en": "Smt. ____",
    "applicant_label_en": "Petitioner (husband)", "respondent_label_en": "Respondent (wife)",
    "marriage_place_en": "Vill. ____, Distt. Gwalior",
    "facts_narrative_en": (
        "after the marriage the matrimonial life was normal for some time and children were born to the parties.\n\n"
        "the respondent, without any reasonable cause, began insisting on living separately and ultimately left "
        "for her parental home with all her belongings; despite the petitioner's repeated efforts and persuasion "
        "she has not been willing to resume cohabitation."
    ),
    "grounds": {"willing_cohabit": True, "jurisdiction": True, "no_other": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="दाम्पत्य पुर्नस्थापना §9 HMA — समीक्षा · द्विभाषी · विष्णु जी की धारा 9 फाइलिंग "
                           "से अक्षरशः · reviewed: false")
