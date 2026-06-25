"""Maintenance — Section 144 BNSS / §125 CrPC (कुटुम्ब न्यायालय / Family Court).

Canonical-standard rebuild, mirrored VERBATIM from his §144 filing (benchmark:
"125 -144 Ankita sahu"). Canonical header + point-wise body + सत्यापन + bilingual.
No LLM writes any text.

Mirror notes:
  • Family court — the WIFE files: applicant `आवेदिका` (+ minor children → आवेदकगण,
    सरपरस्त माता); respondent `अनावेदक` (husband). NO side-line, NO FIR/crime table,
    NO section labels (flows as numbered `यहकि`, like discharge).
  • His fixed closing scaffolding (verbatim): neglect (`भूखों मरने के लिये असहाय…`),
    inability to maintain (`स्वयं… कोई व्यवसाय नहीं जानती…`), husband's income
    (`अन्य किसी के भरण पोषण का भार नहीं…`), amount, jurisdiction
    (`श्रवणाधिकार एवं विचाराधिकार`). Prayer = maintenance FROM DATE OF APPLICATION
    (Rajnesh v. Neha). `सत्यापन` block signed प्रार्थिनी.
  • Companions (separate docs): the **Rajnesh Affidavit of Assets & Liabilities**
    (mandatory), interim-maintenance app, §13 Family Courts Act advocate-appointment.
  • English render prefers `*_en` values + `" and "` joiner (no Hindi bleed).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Rajnesh v. Neha (2021) 2 SCC 324", "point": "assets-affidavit (both parties); maintenance from date of application; quantum criteria", "verified": False},
    {"case": "Chaturbhuj v. Sita Bai (2008) 2 SCC 316", "point": "‘unable to maintain herself’ — not destitute; husband's means", "verified": False},
    {"case": "Bhuwan Mohan Singh v. Meena (2015) 6 SCC 353", "point": "object is social justice; able-bodied husband must provide", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name") or "म.प्र.")
    children = a.get("children") or []
    plural = bool(children) or bool(a.get("is_plural"))
    aw = "आवेदकगण" if plural else "आवेदिका"        # applicant word (wife / wife+children)
    section_title = a.get("section_title") or "धारा 144 भा.ना.सु.सं. (125 दं.प्र.सं.)"
    court_name = a.get("court_name") or compose_court_name(
        "family", a.get("court_city"), state) if a.get("court_city") else \
        (a.get("court_name") or "न्यायालय माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय, ............ (म.प्र.)")

    wife = _ph(a.get("petitioner_name"), "आवेदिका का नाम")
    husband = _ph(a.get("respondent_name"), "पति का नाम")
    wife_block = (f'श्रीमती {wife} पत्नी श्री {husband}, पुत्री श्री {_ph(a.get("petitioner_father"), "पिता")}, '
                  f'आयु— {_ph(a.get("petitioner_age"), "..")} वर्ष, व्यवसाय— {_esc(a.get("petitioner_occupation") or "कुछ नहीं")}, '
                  f'हाल निवासी पिता का घर {_ph(a.get("petitioner_address"), "पता")}')
    desc_lines = [wife_block]
    if children:
        desc_lines = [f'आवेदक क्र. 1 — {wife_block}'] + [
            f'आवेदक क्र. {i} — {_ph(ch.get("name"), "नाम")}, आयु— {_ph(str(ch.get("age") or ""), "..")} वर्ष, '
            f'नाबालिग, सरपरस्त माता {wife}' for i, ch in enumerate(children, start=2)]

    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": "मु.फौ.", "applicant_label": aw, "applicant_desc": desc_lines,
        "respondent_label": "अनावेदक",
        "respondent_desc": [f'{husband} पुत्र श्री {_ph(a.get("respondent_father"), "पिता")},',
                            f'आयु— {_ph(a.get("respondent_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("respondent_occupation"), "व्यवसाय")},',
                            f'निवासी— {_ph(a.get("respondent_address"), "पता")}'],
        "versus": "बनाम", "title_line": f"आवेदन पत्र अन्तर्गत {section_title}",
    })

    g = a.get("grounds") or {}
    amt = _ph(a.get("amount_sought"), "₹________")
    mdate = f'दिनांक {_esc(a.get("marriage_date"))} को' if a.get("marriage_date") else 'दिनांक ......... को'
    mplace = f'{_esc(a.get("marriage_place"))} में' if a.get("marriage_place") else '......... में'
    P = []
    P.append(f'यहकि, आवेदिका का विवाह अनावेदक के साथ हिन्दू रीति-रिवाज एवं विधि-विधान से {mdate} {mplace} '
             f'सम्पन्न हुआ था तथा आवेदिका अनावेदक की विधिवत विवाहिता पत्नी है।')
    if children:
        P.append('यहकि, उपरोक्त विवाह से आवेदकगण क्रमांक 2 आदि का जन्म हुआ, जो वर्तमान में नाबालिग होकर '
                 'आवेदिका (माता) के संरक्षण एवं भरण पोषण में हैं।')
    if g.get("dowry_cruelty", True):
        P.append('यहकि, विवाह के पश्चात् अनावेदक एवं उसके परिजनों द्वारा आवेदिका से दहेज की मांग को लेकर '
                 'समय-समय पर शारीरिक एवं मानसिक रूप से प्रताड़ित किया जाता रहा।')
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[क्रूरता/उपेक्षा/परित्याग के '
                 'वास्तविक तथ्य यहाँ — ससुराल से निकाला जाना, मायके में निवास आदि, दिनांकवार]</span>')
    P.append('यहकि, अनावेदक एवं ससुरालीजन द्वारा आवेदिका की उपेक्षा कर भूखों मरने के लिये असहाय स्थिति में '
             'छोड़ रखा है तथा आवेदिका के भरण पोषण की कोई व्यवस्था नहीं की गई है।')
    P.append('यहकि, आवेदिका स्वयं धन अर्जित करने से सम्बन्धित कोई व्यवसाय नहीं जानती है, न ही उसकी आय का कोई '
             'साधन है, इस कारण आवेदिका स्वयं का भरण पोषण करने में असमर्थ है तथा असहाय स्थिति में अपने माता-पिता '
             'के घर निवास कर रही है।')
    occ = a.get("respondent_occupation"); inc = a.get("respondent_income")
    occ_p = f'अनावेदक {_esc(occ)} करता है, ' if occ else 'अनावेदक '
    inc_p = f'जिससे उसे {_esc(inc)} प्रतिमाह आय प्राप्त होती है' if inc else 'जिससे उसे पर्याप्त मासिक आय प्राप्त होती है'
    P.append(f'यहकि, {occ_p}{inc_p}। अनावेदक पर अन्य किसी के भरण पोषण का भार नहीं है तथा अनावेदक आर्थिक रूप '
             f'से सक्षम होकर भी जानबूझकर आवेदिका की उपेक्षा कर रहा है।')
    if g.get("standard_of_living"):
        P.append('यहकि, आवेदिका अच्छे परिवेश में रही है, जिस कारण आवेदिका के भरण पोषण हेतु अत्याधिक रुपयों '
                 'की आवश्यकता पड़ती है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'यहकि, {_esc(cu)}')
    P.append(f'यहकि, वर्तमान महँगाई एवं अनावेदक की आय को दृष्टिगत रखते हुये आवेदिका को प्रतिमाह भरण पोषण, '
             f'किराया, चिकित्सा आदि हेतु {amt} रुपये की आवश्यकता है; उक्त राशि अनावेदक से दिलाया जाना न्यायोचित '
             f'एवं न्यायसंगत है।')
    P.append(f'यहकि, आवेदिका वर्तमान में {_ph(a.get("petitioner_address"), "पता")} में नगर निगम सीमाओं के '
             f'अन्दर निवास कर रही है, जिस कारण माननीय न्यायालय को प्रस्तुत आवेदन पत्र का श्रवणाधिकार एवं '
             f'विचाराधिकार प्राप्त है।')

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append(f'<p class="cb-prelude">{aw} की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः माननीय न्यायालय से सादर निवेदन है कि {aw} का यह आवेदन पत्र स्वीकार कर आवेदिका को {amt} '
               f'रुपये प्रतिमाह भरण पोषण राशि आवेदन प्रस्तुत करने की दिनांक से अनावेदक से दिलाये जाने तथा वाद-व्यय '
               f'भी दिलाये जाने का आदेश पारित करने की कृपा करें।')
    out.append('</p></div>')
    out.append('<div class="cb-block-label">सत्यापन</div>')
    out.append(f'<p class="cb-prelude">मैं श्रीमती {wife} पत्नी श्री {husband}, पुत्री श्री '
               f'{_ph(a.get("petitioner_father"), "पिता")} शपथपूर्वक सत्यापित करती हूँ कि उपरोक्त आवेदन पत्र '
               f'के पद क्रमांक 01 लगायत अन्तिम में वर्णित समस्त तथ्य मेरे निजी ज्ञान व विश्वास के आधार पर तथा '
               f'इन्हीं पदों में वर्णित कानूनी अंश मेरे अभिभाषक द्वारा दी गई कानूनी जानकारी के आधार पर सत्य व '
               f'सही है। इसमें कुछ भी असत्य वर्णित नहीं है न ही कुछ छिपाया गया है।</p>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>स्थान: {_ph(a.get("court_city"), "स्थान")}</div>'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>प्रार्थिनी</div><div>श्रीमती {wife} — आवेदिका</div></div></div>')
    out.append('<div class="cb-note">साथ संलग्न: (1) सम्पत्ति एवं दायित्वों का शपथपत्र '
               '(अनिवार्य); (2) अंतरिम भरण-पोषण आवेदन; (3) धारा 13 कुटुम्ब न्यायालय '
               'अधिनियम — अभिभाषक नियुक्ति आवेदन; (4) वकालतनामा।</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name_en") or "M.P.")
    children = a.get("children") or []
    plural = bool(children) or bool(a.get("is_plural"))
    aw = "Petitioners" if plural else "Petitioner"
    court_name = a.get("court_name_en") or compose_court_name("family", a.get("court_city_en") or a.get("court_city"), state, lang="en")
    wife = _ph(a.get("petitioner_name_en") or a.get("petitioner_name"), "petitioner")
    husband = _ph(a.get("respondent_name_en") or a.get("respondent_name"), "husband")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Misc. Criminal Case (Maint.)",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": aw,
        "applicant_desc": [f'Smt. {wife}, W/o {husband}, D/o {_ph(a.get("petitioner_father_en") or a.get("petitioner_father"), "father")}, '
                           f'aged {_ph(a.get("petitioner_age"), "..")} yrs, occupation nil, residing at her father\'s house '
                           f'{_ph(a.get("petitioner_address_en") or a.get("petitioner_address"), "address")}'
                           + (' (with minor children, through their mother as guardian)' if children else '')],
        "respondent_label": "Respondent",
        "respondent_desc": [f'{husband}, S/o {_ph(a.get("respondent_father_en") or a.get("respondent_father"), "father")}, '
                            f'occupation {_ph(a.get("respondent_occupation_en") or a.get("respondent_occupation"), "occupation")}, '
                            f'R/o {_ph(a.get("respondent_address_en") or a.get("respondent_address"), "address")}'],
        "versus": "Versus", "title_line": "PETITION UNDER SECTION 144 OF THE BNSS, 2023 "
                                          "(FORMERLY SECTION 125 CrPC, 1973) FOR MAINTENANCE",
    })
    g = a.get("grounds") or {}
    amt = _ph(a.get("amount_sought"), "Rs. ________")
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    inc = a.get("respondent_income_en") or a.get("respondent_income")
    occ = a.get("respondent_occupation_en") or a.get("respondent_occupation")
    P = []
    mdate = (f'on {_esc(a.get("marriage_date"))} ' if a.get("marriage_date") else 'on ......... ') + \
            (f'at {_esc(a.get("marriage_place_en") or a.get("marriage_place"))} ' if a.get("marriage_place") else 'at ......... ')
    P.append(f'That the petitioner was married to the respondent {mdate}according to Hindu rites and is his '
             f'legally wedded wife.')
    if children:
        P.append('That minor children were born of the said wedlock, in the care and custody of the petitioner-mother.')
    if g.get("dowry_cruelty", True):
        P.append('That after the marriage the respondent and his family subjected the petitioner to physical and '
                 'mental cruelty over a demand for dowry.')
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            P.append(f'That {_esc(ch)}')
    P.append('That the respondent and his family have neglected the petitioner and left her in a helpless '
             'condition with no provision for maintenance.')
    P.append('That the petitioner knows no trade by which to earn and has no source of income, and is thus unable '
             'to maintain herself; she resides helplessly at her parents\' home.')
    means = (f'works as {_esc(occ)} and ' if occ else '') + (f'earns {_esc(inc)} per month' if inc else 'has sufficient monthly income')
    P.append(f'That the respondent {means}; he has no other dependant and, though capable, wilfully neglects the petitioner.')
    if g.get("standard_of_living"):
        P.append('That the petitioner enjoyed a good standard of living and requires maintenance consistent with it.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            P.append(f'That {_esc(cu)}')
    P.append(f'That, having regard to the cost of living and the respondent\'s income, the petitioner requires '
             f'{amt} per month towards maintenance, rent and medical needs, and it is just and proper that the '
             f'said sum be granted from the respondent.')
    P.append(f'That the petitioner resides at {_ph(a.get("petitioner_address_en") or a.get("petitioner_address"), "address")} '
             f'within the municipal limits and the jurisdiction of this Hon\'ble Court, which has jurisdiction to '
             f'hear and decide the petition.')
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MOST RESPECTFULLY SHEWETH:—</p>')
    out.append('<ol class="cb-paras">')
    for p in P:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may '
               f'be pleased to allow the petition and direct the respondent to pay {amt} per month as maintenance '
               f'to the {aw.lower()} from the date of the application, together with the costs of litigation.</p></div>')
    out.append('<div class="cb-block-label">VERIFICATION</div>')
    out.append(f'<p class="cb-prelude">I, Smt. {wife}, W/o {husband}, verify that the facts in paragraphs 1 to the '
               f'last are true to my knowledge and belief and the legal portions on the advice of my counsel; '
               f'nothing false has been stated nor anything material concealed.</p>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Place: {_ph(a.get("court_city_en") or a.get("court_city"), "place")}</div>'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Petitioner</div><div>Smt. {wife} — Petitioner</div></div></div>')
    out.append('<div class="cb-note">Enclosed: (1) Affidavit of Assets &amp; Liabilities (mandatory); '
               '(2) interim-maintenance application; (3) §13 Family Courts Act counsel-appointment '
               'application; (4) vakalatnama.</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("dowry_cruelty", "दहेज मांग + क्रूरता", "Dowry demand + cruelty", default=True),
    F.toggle("standard_of_living", "सम्मानजनक जीवन-स्तर का दावा", "Standard-of-living claim", default=False),
    F.toggle("is_plural", "बच्चे भी आवेदक हैं?", "Children are co-applicants?", default=False),
]


def field_spec() -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", required=True, section="court", hint="लोकेशन से स्वतः → कुटुम्ब न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः)", "Court name (auto)", section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("petitioner_name", "आवेदिका का नाम", "Petitioner (wife) name", F.NAME, True, "parties"),
        F.f("petitioner_father", "आवेदिका के पिता का नाम", "Petitioner's father", F.NAME, section="parties"),
        F.f("petitioner_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("petitioner_address", "हाल निवास (मायका)", "Present address (parents')", F.ADDRESS, True, "parties"),
        F.f("respondent_name", "अनावेदक (पति) का नाम", "Respondent (husband) name", F.NAME, True, "parties"),
        F.f("respondent_father", "पति के पिता का नाम", "Husband's father", F.NAME, section="parties"),
        F.f("respondent_occupation", "पति का व्यवसाय", "Husband's occupation", section="parties"),
        F.f("respondent_income", "पति की मासिक आय", "Husband's monthly income", F.MONEY, section="parties"),
        F.f("respondent_address", "पति का पता", "Husband's address", F.ADDRESS, section="parties"),
        F.f("marriage_date", "विवाह दिनांक", "Date of marriage", F.DATE, section="facts"),
        F.f("marriage_place", "विवाह स्थल", "Place of marriage", section="facts"),
        F.f("children", "बच्चे (नाम/आयु)", "Children (name/age)", F.TABLE, section="facts"),
        F.f("facts_narrative", "क्रूरता/परित्याग के तथ्य", "Cruelty / desertion facts", F.LONGTEXT, True, "facts"),
        F.f("amount_sought", "मांगी गई मासिक राशि", "Monthly maintenance sought", F.MONEY, True, "facts"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("maintenance", flds, _TOGGLES,
                        companions=["Rajnesh assets-&-liabilities affidavit (mandatory)",
                                    "interim-maintenance application", "§13 counsel-appointment", "vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court_city": "ग्वालियर", "court_city_en": "Gwalior", "state_name": "म.प्र.", "state_name_en": "M.P.",
    "case_number": "____", "case_year": "2025",
    "petitioner_name": "क ख", "petitioner_name_en": "K.",
    "petitioner_father": "ओमप्रकाश", "petitioner_father_en": "Omprakash", "petitioner_age": "26",
    "petitioner_address": "____, नाका चन्द्रबदनी, ग्वालियर", "petitioner_address_en": "____, Naka Chandrabadni, Gwalior",
    "respondent_name": "य र", "respondent_name_en": "Y.", "respondent_father": "बैजनाथ", "respondent_father_en": "Baijnath",
    "respondent_occupation": "प्रायवेट कम्पनी में नौकरी", "respondent_occupation_en": "private company service",
    "respondent_income": "₹75,000", "respondent_income_en": "Rs. 75,000",
    "respondent_address": "____, बहोड़ापुर, ग्वालियर", "respondent_address_en": "____, Bahodapur, Gwalior",
    "marriage_date": "06.02.2024", "marriage_place": "ग्वालियर", "marriage_place_en": "Gwalior",
    "amount_sought": "₹15,000",
    "facts_narrative": (
        "विवाह के पश्चात् अनावेदक एवं उसके परिजन द्वारा कार अथवा दस लाख रुपये की अतिरिक्त दहेज मांग को लेकर "
        "आवेदिका को प्रताड़ित किया जाता रहा।\n\n"
        "दिनांक 18.11.2024 को आवेदिका को मात्र पहने हुए कपड़ों में ससुराल से निकाल दिया गया; तब से आवेदिका अपने "
        "माता-पिता के घर निवास कर रही है।"
    ),
    "facts_narrative_en": (
        "after the marriage the respondent and his family harassed the petitioner over an additional dowry "
        "demand of a car or ten lakh rupees.\n\n"
        "on 18.11.2024 she was thrown out of the matrimonial home in the clothes she was wearing, and has since "
        "resided at her parents' home."
    ),
    "grounds": {"dowry_cruelty": True, "standard_of_living": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="भरण-पोषण (धारा 144 · 125) — समीक्षा · कुटुम्ब न्यायालय · canonical header · "
                           "द्विभाषी · विष्णु जी की Ankita sahu §144 फाइलिंग से अक्षरशः · reviewed: false")
