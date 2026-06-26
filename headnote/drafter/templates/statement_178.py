"""दस्तयावी बयान — record the applicant's statement before the Court — §178 BNSS.

Canonical build, mirror-first from Vishnu ji's real filings (benchmarks: "Najiya
Dastyav", "Rashmi Dastyav" — a woman who has left home voluntarily / married of
her own will asks the Magistrate to record HER statement before the Court so the
police (in collusion with relatives who filed a false missing/abduction report)
cannot fabricate a kidnapping case. Ships as a 2-sheet bundle [application,
शपथपत्र]. No case law in the body.

This is a HIGH-VOLUME type in his practice (~18 filings) that had no catalogue
tile — a new tile (statement_178) is added.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = []  # statement-recording rests on the facts; no body case law.


def _esc(s): return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
def _ph(s, ph="________"): return _esc(s) if (s and str(s).strip()) else f'<span class="ph">{ph}</span>'
def _chunks(t): return [x.strip() for x in str(t or "").split("\n\n") if x.strip()]
def _overlay_en(a):
    a = dict(a or {})
    for k in list(a):
        if k.endswith("_en") and a[k] not in (None, ""): a[k[:-3]] = a[k]
    return a


_CD = "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ............ (म.प्र.)"


def render_hi(a: dict) -> str:
    a = a or {}; g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "म.प्र. राज्य")
    ps = _ph(a.get("police_station"), "पुलिस थाना")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": a.get("case_type") or "", "applicant_label": "आवेदिका",
        "applicant_desc": [_ph(a.get("applicant_name"), "आवेदिका का नाम")],
        "respondent_label": "अनावेदक", "respondent_desc": [f'{state} द्वारा {ps}'],
        "versus": "बनाम",
        "title_line": "आवेदन पत्र अन्तर्गत धारा 178 भा.ना.सु.सं. वास्ते दस्तयावी बयान न्यायालय के समक्ष कराये जाने बावत्",
    })
    P = []
    facts = _chunks(a.get("facts_narrative"))
    if facts:
        for ch in facts: P.append(f'यहकि, {_esc(ch)}')
    else:
        P.append('<span class="ph">[आवेदिका की परिस्थिति — स्वेच्छा से घर छोड़ना/विवाह, परिजनों द्वारा झूठी '
                 'गुमशुदगी/अपहरण रिपोर्ट — खाली पंक्ति से अलग पैरा]</span>')
    if g.get("false_report", True):
        P.append(f'यहकि, आवेदिका को जानकारी प्राप्त हुई है कि उसके परिजनों द्वारा आवेदिका के गुम होने/अपहरण '
                 f'किये जाने की झूठी शिकायत {ps} में की गई है, जिस पर {ps} आवेदिका के कथन लेना चाहती है।')
    if g.get("apprehension", True):
        P.append(f'यहकि, आवेदिका को आशंका है कि {ps} परिजनों से मिलकर आवेदिका के झूठे कथन लिखकर अथवा अपहरण '
                 f'दर्शाते हुए किसी को झूठा फँसा सकती है अथवा आवेदिका के विरुद्ध कोई असत्य कार्यवाही कर सकती है।')
    if g.get("voluntary", True):
        P.append('यहकि, आवेदिका को किसी ने बन्दी बनाकर नहीं रखा है, न ही आवेदिका का कोई अपहरण अथवा बहला-फुसलाकर '
                 'ले जाना हुआ है; आवेदिका बालिग होकर अपना भला-बुरा सोचने में पूर्ण सक्षम है तथा अपनी स्वेच्छा से '
                 'निवास कर रही है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'यहकि, {_esc(cu)}')
    P.append('यहकि, आवेदिका का दस्तयावी कथन न्यायालय श्रीमान के समक्ष कराया जाना न्यायोचित एवं न्यायसंगत है।')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">माननीय महोदय,</p>',
           '<p class="cb-prelude">आवेदिका की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>अतः श्रीमान जी से सादर निवेदन है कि {ps} से सम्बन्धित विवेचना '
               f'अधिकारी को तलब कर आवेदिका के दस्तयावी कथन न्यायालय श्रीमान के समक्ष दर्ज करवाये जाने का आदेश '
               f'पारित करने की कृपा करें।</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "आवेदिका")}</div><div>— आवेदिका</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div></div>')
    return "\n".join(out)


def render_affidavit_hi(a: dict) -> str:
    a = a or {}
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "म.प्र.") \
        if a.get("court_city") else (a.get("court_name") or _CD)
    dep = _ph(a.get("applicant_name"), "शपथकर्ता")
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "प्रकरण क्रमांक",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "आवेदिका", "applicant_desc": [dep],
        "respondent_label": "अनावेदक", "respondent_desc": [_esc(a.get("state_name") or "म.प्र. राज्य")],
        "versus": "बनाम", "title_line": "शपथ पत्र",
    })
    out = [hdr, '<div class="doc-body">']
    out.append('<table class="cb-table" style="max-width:62%">'
               f'<tr><td>नाम</td><td>{dep}</td></tr>'
               f'<tr><td>पति/पिता का नाम</td><td>{_ph(a.get("applicant_father"), "पति/पिता")}</td></tr>'
               f'<tr><td>आयु</td><td>{_ph(a.get("applicant_age"), "..")} वर्ष</td></tr>'
               f'<tr><td>व्यवसाय</td><td>{_ph(a.get("applicant_occupation"), "व्यवसाय")}</td></tr>'
               f'<tr><td>निवासी</td><td>{_ph(a.get("applicant_address"), "पता")}</td></tr>'
               '</table>')
    out.append('<p class="cb-prelude">मैं उक्त शपथकर्ता शपथपूर्वक सत्य कथन करती हूँ किः—</p>')
    out.append('<ol class="cb-paras">')
    out.append('<li>यहकि, मुझ शपथकर्ता द्वारा माननीय न्यायालय के समक्ष दस्तयावी बयान कराये जाने बावत् एक '
               'आवेदन पत्र प्रस्तुत किया गया है।</li>')
    out.append('<li>यहकि, उक्त आवेदन पत्र में वर्णित समस्त तथ्य मेरे निजी ज्ञान व विश्वास से सत्य व सही हैं; '
               'इसमें कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।</li>')
    out.append('<li>यहकि, उक्त तथ्यों के समर्थन में यह शपथ पत्र प्रस्तुत है।</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>दिनांक: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">हस्ताक्षर शपथकर्ता</div>'
               f'<div>({dep})</div></div></div>')
    out.append('<div class="cb-block-label">सत्यापन</div>')
    out.append('<p class="cb-prelude">मैं शपथकर्ता शपथपूर्वक सत्यापित करती हूँ कि शपथ पत्र के पद क्रमांक 1 '
               'लगायत 3 में दी गई जानकारी मेरे ज्ञान व विश्वास से सत्य व सही है, जिसमें कुछ भी असत्य नहीं है '
               'और न ही कुछ छिपाया गया है।</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>दिनांक: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">हस्ताक्षर सत्यापनकर्ता</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def render_en(a: dict) -> str:
    a = _overlay_en(a); g = a.get("grounds") or {}
    state = _esc(a.get("state_name") or "State of M.P.")
    ps = _ph(a.get("police_station"), "police station")
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "M.P.", lang="en")
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [_ph(a.get("applicant_name"), "applicant")],
        "respondent_label": "Respondent", "respondent_desc": [f'{state} through {ps}'],
        "versus": "Versus", "title_line": "APPLICATION UNDER SECTION 178 BNSS, 2023 — TO RECORD THE "
                                          "APPLICANT'S STATEMENT BEFORE THE COURT"})
    P = []
    for ch in _chunks(a.get("facts_narrative")): P.append(f'That {_esc(ch)}')
    if g.get("false_report", True):
        P.append(f'That the applicant has learnt that her relatives have lodged a false report of her going '
                 f'missing / being abducted at {ps}, on which {ps} seeks to record her statement.')
    if g.get("apprehension", True):
        P.append(f'That the applicant apprehends that {ps}, in collusion with the relatives, may record false '
                 f'statements or, by showing an abduction, falsely implicate someone or take adverse action '
                 f'against the applicant.')
    if g.get("voluntary", True):
        P.append('That the applicant has not been detained by anyone, nor has she been abducted or enticed away; '
                 'being a major, she is fully capable of deciding her own welfare and is residing of her own '
                 'free will.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip(): P.append(f'That {_esc(cu)}')
    P.append('That it is just and proper that the applicant\'s statement be recorded before this Hon\'ble Court.')
    out = [hdr, '<div class="doc-body">', '<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>',
           '<p class="cb-prelude">The applicant most respectfully submits as under:—</p>', '<ol class="cb-paras">']
    out += [f'<li>{p}</li>' for p in P]
    out.append('</ol>')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that the investigating '
               f'officer concerned with {ps} be summoned and the applicant\'s statement be recorded before this '
               f'Hon\'ble Court, in the interest of justice.</p></div>')
    out.append('<div class="cb-sig"><div class="l">'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>'
               f'<div class="r"><div>{_ph(a.get("applicant_name"), "Applicant")}</div><div>— Applicant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div></div>')
    return "\n".join(out)


def render_affidavit_en(a: dict) -> str:
    a = _overlay_en(a)
    court_name = a.get("court_name") or compose_court_name("magistrate", a.get("court_city"), "M.P.", lang="en")
    dep = _ph(a.get("applicant_name"), "deponent")
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": "Case No.",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [dep],
        "respondent_label": "Respondent", "respondent_desc": [_esc(a.get("state_name") or "State of M.P.")],
        "versus": "Versus", "title_line": "AFFIDAVIT"})
    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">I, the deponent above-named, do solemnly affirm and state as under:—</p>')
    out.append('<ol class="cb-paras">')
    out.append('<li>That the deponent has filed an application before this Hon\'ble Court for recording her '
               'statement before the Court.</li>')
    out.append('<li>That all the facts stated in the said application are true and correct to the deponent\'s '
               'personal knowledge and belief; nothing is false and nothing has been concealed.</li>')
    out.append('<li>That this affidavit is filed in support of the said facts.</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>Date: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">Signature of the Deponent</div>'
               f'<div>({dep})</div></div></div>')
    out.append('<div class="cb-block-label">VERIFICATION</div>')
    out.append('<p class="cb-prelude">I, the deponent, verify that the contents of paras 1 to 3 are true and '
               'correct to my knowledge and belief; nothing is false and nothing has been concealed.</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>Date: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">Signature of the Verifier</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def bundle(a: dict, lang: str = "hi"):
    a = a or {}; hi = lang == "hi"; g = a.get("grounds") or {}
    R = render_hi if hi else render_en
    AFF = render_affidavit_hi if hi else render_affidavit_en
    sheets, labels = [R(a)], ["आवेदन पत्र" if hi else "Application"]
    if g.get("with_affidavit", True):
        sheets.append(AFF(a)); labels.append("शपथ पत्र" if hi else "Affidavit")
    return sheets, labels


_TOGGLES = [
    F.toggle("false_report", "परिजनों की झूठी रिपोर्ट — पैरा", "Relatives' false report — para", default=True),
    F.toggle("apprehension", "पुलिस द्वारा झूठ गढ़ने की आशंका", "Apprehension police may fabricate", default=True),
    F.toggle("voluntary", "स्वेच्छा/बालिग — बन्दी नहीं — पैरा", "Voluntary / major — not detained — para", default=True),
    F.toggle("with_affidavit", "शपथ पत्र संलग्न", "Attach affidavit", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः/ओवरराइड)", "Court name", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("applicant_name", "आवेदिका का नाम", "Applicant name", F.NAME, True, "parties"),
        F.f("applicant_father", "पति/पिता का नाम", "Husband's/father's name", F.NAME, section="parties"),
        F.f("applicant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("applicant_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("applicant_address", "पता", "Address", F.ADDRESS, section="parties"),
        F.f("state_name", "राज्य", "State", section="parties", default="म.प्र. राज्य"),
        F.f("police_station", "पुलिस थाना", "Police station", required=True, section="crime"),
        F.f("facts_narrative", "आवेदिका की परिस्थिति", "Applicant's situation", F.LONGTEXT, True, "facts",
            hint="स्वेच्छा से घर छोड़ना/विवाह, परिजनों की झूठी रिपोर्ट — खाली पंक्ति से अलग पैरा"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("statement_178", flds, _TOGGLES, companions=["affidavit (मय शपथपत्र)", "vakalatnama"])


SAMPLE = {
    "court_city": "ग्वालियर", "case_number": "____/2024",
    "applicant_name": "श्रीमती ____", "applicant_father": "श्री ____", "applicant_age": "21",
    "applicant_occupation": "गृहकार्य", "applicant_address": "____, ग्वालियर (म.प्र.)",
    "state_name": "म.प्र. राज्य", "police_station": "थाना ____, ग्वालियर",
    "facts_narrative": (
        "आवेदिका बालिग होकर अपनी स्वेच्छा से ____ के साथ हिन्दू रीति से विवाह कर वर्तमान में अपने पति के साथ "
        "निवास कर रही है।\n\n"
        "आवेदिका के परिजन उसकी इच्छा के विरुद्ध अन्यत्र विवाह कर रहे थे, इस कारण आवेदिका स्वेच्छा से घर से आई थी।"
    ),
    "court_city_en": "Gwalior", "applicant_name_en": "Smt. ____", "applicant_father_en": "Shri ____",
    "applicant_occupation_en": "homemaker", "applicant_address_en": "____, Gwalior (M.P.)",
    "state_name_en": "State of M.P.", "police_station_en": "P.S. ____, Gwalior",
    "facts_narrative_en": (
        "the applicant, a major, has of her own free will married ____ by Hindu rites and is presently residing "
        "with her husband.\n\n"
        "the applicant's relatives were getting her married elsewhere against her wishes, due to which the "
        "applicant left home of her own accord."
    ),
    "grounds": {"false_report": True, "apprehension": True, "voluntary": True, "with_affidavit": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    bh, _ = bundle(d, "hi"); be, _ = bundle(d, "en")
    return doc_page(bh + be,
                    banner="दस्तयावी बयान §178 (कथन न्यायालय के समक्ष) — समीक्षा · आवेदन + शपथ पत्र · द्विभाषी · "
                           "विष्णु जी की Najiya/Rashmi फाइलिंग से अक्षरशः · reviewed: false")
