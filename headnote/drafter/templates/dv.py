"""Domestic Violence — Section 12 application, PWDVA 2005 (घरेलू हिंसा से महिलाओं
का संरक्षण अधिनियम, धारा 12).

Canonical-standard builder mirrored VERBATIM from his filed §12 application
(benchmark: "12 DV — Ankita sahu"). Filed before the JMFC. Canonical header +
यहकि facts + per-section RELIEF blocks (§17-22) + सत्यापन + bilingual. No LLM text.

Mirror notes (decoded — do not "improve"):
  • व्यथित (aggrieved woman) vs प्रत्यर्थीगण (respondents — husband + in-laws, numbered);
    parties by बनाम. Case line `प्रकरण क्रमांक— ___/<yr> घरेलू हिंसा` (suffix).
  • Title `आवेदन पत्र अन्तर्गत धारा 12 घरेलू हिंसा से महिलाओं का संरक्षण अधिनियम 2005`.
  • Salutation `माननीय न्यायालय,` → `व्यथित की ओर से आवेदन निम्न प्रकार प्रस्तुत है ः—`.
  • Facts = यहकि paras (marriage → dowry → cruelty → thrown out → complaints → income).
  • RELIEFS under `व्यथित निम्नलिखित अनुतोष की अधिकारिणी है ः—`, each a §-labelled block:
    §17 residence right · §18 protection order · §19 residence order · §19(8) streedhan
    · §20 monetary relief (amount) · §21 custody (children) · §22 compensation (amount).
  • Optional पूर्व मुकदमेबाजी का ब्योरा; cause-of-action (continuing); jurisdiction; prayer
    (relief + punish respondents); सत्यापन verification (like maintenance).
  • Companions: §23 interim-maintenance application + affidavit + DIR + witness list + vakalatnama.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Hiral P. Harsora v. Kusum Narottamdas Harsora (2016) 10 SCC 165",
     "point": "‘Respondent’ is not confined to an adult male — relatives (incl. female) covered.", "verified": False},
    {"case": "S.R. Batra v. Taruna Batra (2007) 3 SCC 169 / Satish Chander Ahuja v. Sneha Ahuja (2021) 1 SCC 414",
     "point": "Shared-household right — Ahuja overrules the narrow Batra view.", "verified": False},
    {"case": "Prabha Tyagi v. Kamlesh Devi (2022) SCC OnLine SC 607",
     "point": "Right to reside in shared household even without actual residence; DIR not mandatory pre-condition.", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _relief(label, text):
    return f'<p class="cb-relief"><b><u>{label} ः—</u></b> {text}</p>'


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name") or "म.प्र.")
    name = a.get("aggrieved_name") or ""
    court_name = a.get("court_name") or (
        compose_court_name("magistrate", a.get("court_city"), state) if a.get("court_city")
        else "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ________ (म.प्र.)")
    g = a.get("grounds") or {}
    amt = a.get("monetary_amount") or "________"
    comp = a.get("compensation_amount") or "________"

    av_desc = (f'श्रीमती {_ph(name, "नाम")} पत्नी श्री {_ph(a.get("husband_name"), "पति")}, '
               f'पुत्री श्री {_ph(a.get("aggrieved_father"), "पिता")}, आयु— {_ph(a.get("aggrieved_age"), "..")} वर्ष, '
               f'व्यवसाय— {_ph(a.get("aggrieved_occupation"), "गृहणी")},')
    av_desc2 = f'निवासी— <u>{_ph(a.get("aggrieved_address"), "पता")}</u> ({state})'

    resp_lines = []
    if (a.get("respondents_desc") or "").strip():
        for ln in [x.strip() for x in a["respondents_desc"].split("\n") if x.strip()]:
            resp_lines.append(_esc(ln))
    else:
        resp_lines.append('<span class="ph">[प्रत्यर्थीगण — पति (क्र.1) '
                          'एवं ससुरालीजन, क्रमवार]</span>')
    if a.get("respondents_address"):
        resp_lines.append(f'निवासीगण— <u>{_esc(a.get("respondents_address"))}</u> ({state})')

    hdr = render_header({
        "side_label": "", "court_name": court_name,
        "case_code": "प्रकरण क्रमांक", "case_suffix": "घरेलू हिंसा",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "व्यथित", "applicant_desc": [av_desc, av_desc2],
        "respondent_label": "प्रत्यर्थीगण", "respondent_desc": resp_lines,
        "versus": "बनाम",
        "title_line": "आवेदन पत्र अन्तर्गत धारा 12 घरेलू हिंसा से महिलाओं का संरक्षण अधिनियम 2005",
    })

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    out.append('<p class="cb-prelude">व्यथित की ओर से आवेदन निम्न प्रकार प्रस्तुत है ः—</p>')

    # facts (numbered यहकि)
    out.append('<ol class="cb-paras">')
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            out.append(f'<li>यहकि, {_esc(ch)}</li>')
    else:
        out.append('<li><span class="ph">[विवाह · दहेज · प्रताड़ना · '
                   'घर से निकालना · शिकायतें · प्रत्यर्थी की आय — घरेलू हिंसा का कथानक यहाँ]</span></li>')
    out.append('</ol>')

    # reliefs (§17-22 blocks, toggleable)
    out.append('<p class="cb-block-label">व्यथित, प्रत्यर्थीगण से निम्नलिखित अनुतोष प्राप्त करने की अधिकारिणी है ः—</p>')
    R = []
    if g.get("residence_right", True):
        R.append(_relief("धारा 17 के अनुसार अनुतोष", 'व्यथित प्रत्यर्थी क्रमांक—01 की विवाहिता पत्नी है; '
                 'शामिलाती कौटुम्बिक गृह (साझा गृहस्थी) में निवास करने का अधिकार व्यथित को दिलाया जावे।'))
    if g.get("protection_order", True):
        R.append(_relief("धारा 18 के अनुसार संरक्षा आदेश", 'प्रत्यर्थीगण द्वारा व्यथित के साथ शारीरिक एवं मानसिक रूप से '
                 'घरेलू हिंसा कारित की गई है; व्यथित के हित में संरक्षा आदेश जारी किया जावे जिससे प्रत्यर्थीगण घरेलू '
                 'हिंसा की पुनरावृत्ति न करें।'))
    if g.get("residence_order", True):
        R.append(_relief("धारा 19 के अनुसार निवास का आदेश", 'व्यथित को साझा गृहस्थी में शांतिपूर्वक निवास का अधिकार '
                 'दिलाया जाकर प्रत्यर्थीगण को व्यथित को बेदखल करने अथवा घरेलू हिंसा कारित करने से रोकने हेतु '
                 'प्रतिभूति एवं बन्धपत्र लिया जावे ताकि पुनरावृत्ति न हो।'))
    if g.get("streedhan", True):
        R.append(_relief("धारा 19(8) के अनुसार", 'प्रत्यर्थीगण के कब्जे से व्यथित का समस्त स्त्रीधन, स्वर्ण/रजत '
                 'आभूषण, उपहार-सामग्री एवं माता-पिता द्वारा दी गई नगद राशि व्यथित को दिलाई जावे।'))
    if g.get("monetary_relief", True):
        R.append(_relief("धारा 20 के अनुसार मौद्रिक अनुतोष", f'व्यथित स्वयं के भरण-पोषण में असमर्थ है; व्यथित को '
                 f'भरण-पोषण, चिकित्सा, आवास-किराया एवं घरेलू व्यय हेतु {_esc(amt)} रुपये मासिक प्रत्यर्थीगण से '
                 f'प्रथक-प्रथक दिलाई जावे।'))
    if g.get("custody"):
        R.append(_relief("धारा 21 के अनुसार अभिरक्षा आदेश", f'व्यथित को नाबालिग संतान {_ph(a.get("children"), "________")} '
                 f'की अस्थाई अभिरक्षा प्रदान की जावे।'))
    if g.get("compensation", True):
        R.append(_relief("धारा 22 के अनुसार प्रतिकर आदेश", f'प्रत्यर्थीगण द्वारा व्यथित को शारीरिक, मानसिक एवं '
                 f'भावनात्मक रूप से प्रताड़ित कर बेइज्जत किया गया है; प्रतिकर के रूप में एकमुश्त {_esc(comp)} रुपये '
                 f'व्यथित को दिलाई जावे।'))
    out.extend(R)

    if (a.get("prior_litigation") or "").strip():
        out.append('<p class="cb-block-label">पूर्व मुकदमेबाजी का ब्योरा ः—</p>')
        out.append(f'<p class="cb-prelude">{_esc(a["prior_litigation"])}</p>')

    out.append('<p class="cb-prelude">यहकि, प्रत्यर्थीगण द्वारा व्यथित के साथ घरेलू हिंसा कारित कर असहाय स्थिति में '
               'छोड़ देने से वाद कारण उत्पन्न होकर दिन-प्रतिदिन जारी है।</p>')
    out.append(f'<p class="cb-prelude">यहकि, व्यथित वर्तमान में {_ph(a.get("aggrieved_address"), "________")} निवास कर '
               f'रही है, जो आरक्षी केन्द्र {_ph(a.get("police_station"), "थाना")} के क्षेत्रान्तर्गत होने से माननीय '
               f'न्यायालय को प्रकरण का श्रवणाधिकार एवं क्षेत्राधिकार प्राप्त है।</p>')

    out.append('<div class="cb-prayer"><p>अतः माननीय न्यायालय से निवेदन है कि व्यथित का आवेदन पत्र स्वीकार कर '
               'व्यथित को प्रत्यर्थीगण से आवेदन में चाही गई समस्त सहायता एवं अनुतोष दिलाया जाकर, प्रत्यर्थीगण को '
               'व्यथित के साथ किये गये कृत्य हेतु दण्डित किये जाने का आदेश पारित करने की कृपा करें।</p></div>')

    # verification
    out.append('<p class="cb-block-label" style="text-align:left">सत्यापन</p>')
    out.append(f'<p class="cb-prelude">मैं श्रीमती {_ph(name, "नाम")} शपथपूर्वक सत्यापित करती हूँ कि उपरोक्त आवेदन '
               f'पत्र में वर्णित समस्त तथ्य मेरे निजी ज्ञान व विश्वास के आधार पर सत्य व सही हैं तथा इन्हीं पदों में '
               f'वर्णित कानूनी अंश मेरे अभिभाषक द्वारा दी गई कानूनी जानकारी के आधार पर सत्य व सही हैं। इसमें कुछ '
               f'भी असत्य वर्णित नहीं है, न ही कुछ छिपाया गया है।</p>')

    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांकः— {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>व्यथित</div><div>श्रीमती {_ph(name, "नाम")} — व्यथित</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('<div class="cb-note">साथ संलग्न: धारा 23 अन्तरिम भरण-पोषण/संरक्षा हेतु पृथक आवेदन (मय शपथपत्र) · '
               'घरेलू घटना रिपोर्ट (DIR) · साक्ष्य सूची · वकालतनामा।</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name_en") or "M.P.")
    name = _ph(a.get("aggrieved_name_en") or a.get("aggrieved_name"), "aggrieved")
    g = a.get("grounds") or {}
    amt = _esc(a.get("monetary_amount") or "________")
    comp = _esc(a.get("compensation_amount") or "________")

    av = (f'Smt. {name}, W/o {_ph(a.get("husband_name_en") or a.get("husband_name"), "husband")}, '
          f'D/o {_ph(a.get("aggrieved_father_en") or a.get("aggrieved_father"), "father")}, '
          f'aged {_ph(a.get("aggrieved_age"), "..")} years, R/o '
          f'{_ph(a.get("aggrieved_address_en") or a.get("aggrieved_address"), "address")} ({state})')
    resp = []
    src = a.get("respondents_desc_en") or a.get("respondents_desc") or ""
    if src.strip():
        for ln in [x.strip() for x in src.split("\n") if x.strip()]:
            resp.append(_esc(ln))
    else:
        resp.append('[Respondents — husband (No. 1) and in-laws, serially]')
    if a.get("respondents_address_en") or a.get("respondents_address"):
        resp.append(f'all R/o {_ph(a.get("respondents_address_en") or a.get("respondents_address"), "")} ({state})')

    hdr = render_header({
        "side_label": "", "court_name": a.get("court_name_en") or compose_court_name(
            "magistrate", a.get("court_city_en") or a.get("court_city"), state, lang="en"),
        "case_code": "Case No.", "case_suffix": "(Domestic Violence)",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Aggrieved Person", "applicant_desc": [av],
        "respondent_label": "Respondents", "respondent_desc": resp,
        "versus": "Versus",
        "title_line": "APPLICATION UNDER SECTION 12 OF THE PROTECTION OF WOMEN FROM DOMESTIC VIOLENCE ACT, 2005",
    })

    out = [hdr, '<div class="doc-body">']
    out.append('<p class="cb-prelude">MAY IT PLEASE THIS HON\'BLE COURT,</p>')
    out.append('<p class="cb-prelude">The aggrieved person most respectfully submits as under:—</p>')
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    out.append('<ol class="cb-paras">')
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            out.append(f'<li>That {_esc(ch)}</li>')
    else:
        out.append('<li>[Marriage, dowry, cruelty, being driven out, complaints, respondent\'s income — '
                   'the domestic-violence narrative here.]</li>')
    out.append('</ol>')

    out.append('<p class="cb-block-label">The aggrieved person is entitled to the following reliefs:—</p>')
    R = []
    if g.get("residence_right", True):
        R.append(_relief("Section 17", 'The aggrieved person, being the legally wedded wife of Respondent No. 1, '
                 'is entitled to reside in the shared household.'))
    if g.get("protection_order", True):
        R.append(_relief("Section 18 — Protection Order", 'The respondents have subjected the aggrieved person to '
                 'physical and mental domestic violence; a protection order may issue to restrain its repetition.'))
    if g.get("residence_order", True):
        R.append(_relief("Section 19 — Residence Order", 'The aggrieved person may be secured peaceful residence in '
                 'the shared household, with a bond restraining the respondents from dispossession or further violence.'))
    if g.get("streedhan", True):
        R.append(_relief("Section 19(8)", 'The respondents may be directed to return the aggrieved person\'s entire '
                 'streedhan, gold/silver ornaments, gifts and cash given by her parents.'))
    if g.get("monetary_relief", True):
        R.append(_relief("Section 20 — Monetary Relief", f'The aggrieved person being unable to maintain herself, '
                 f'maintenance, medical, rent and household expenses of ₹{amt} per month may be granted from the respondents.'))
    if g.get("custody"):
        R.append(_relief("Section 21 — Custody Order", f'Temporary custody of the minor child/children '
                 f'{_ph(a.get("children_en") or a.get("children"), "________")} may be granted to the aggrieved person.'))
    if g.get("compensation", True):
        R.append(_relief("Section 22 — Compensation", f'For the physical, mental and emotional cruelty inflicted, '
                 f'a lump-sum compensation of ₹{comp} may be granted to the aggrieved person.'))
    out.extend(R)

    if (a.get("prior_litigation_en") or a.get("prior_litigation") or "").strip():
        out.append('<p class="cb-block-label">Particulars of prior litigation:—</p>')
        out.append(f'<p class="cb-prelude">{_esc(a.get("prior_litigation_en") or a.get("prior_litigation"))}</p>')
    out.append('<p class="cb-prelude">That the cause of action arose and continues from day to day on the respondents '
               'subjecting the aggrieved person to domestic violence and leaving her helpless.</p>')
    out.append(f'<p class="cb-prelude">That the aggrieved person presently resides within the jurisdiction of Police '
               f'Station {_ph(a.get("police_station_en") or a.get("police_station"), "police station")}, and this '
               f'Hon\'ble Court has jurisdiction to try the matter.</p>')
    out.append('<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may be '
               'pleased to allow the application, grant the aggrieved person all the reliefs prayed for, and pass such '
               'order as it deems fit.</p></div>')
    out.append('<p class="cb-block-label" style="text-align:left">VERIFICATION</p>')
    out.append(f'<p class="cb-prelude">I, Smt. {name}, do hereby verify that the contents of the above application are '
               f'true and correct to my personal knowledge and belief, and the legal submissions on the advice of my '
               f'counsel believed to be true; nothing material has been concealed.</p>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Aggrieved Person</div><div>Smt. {name} — Aggrieved</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")}) — Advocate</div></div></div>')
    out.append('</div>')
    return "\n".join(out).replace("ः—", ":—")  # Devanagari relief separator → ASCII in EN


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("residence_right", "धारा 17 — साझा गृहस्थी में निवास का अधिकार", "§17 — right to reside in shared household", default=True),
    F.toggle("protection_order", "धारा 18 — संरक्षा आदेश", "§18 — protection order", default=True),
    F.toggle("residence_order", "धारा 19 — निवास आदेश", "§19 — residence order", default=True),
    F.toggle("streedhan", "धारा 19(8) — स्त्रीधन वापसी", "§19(8) — return of streedhan", default=True),
    F.toggle("monetary_relief", "धारा 20 — मौद्रिक अनुतोष", "§20 — monetary relief", default=True),
    F.toggle("custody", "धारा 21 — संतान अभिरक्षा", "§21 — custody of children", default=False),
    F.toggle("compensation", "धारा 22 — प्रतिकर", "§22 — compensation", default=True),
]


def field_spec(court: str = "magistrate") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "न्यायालय का नाम (स्वतः)", "Court name (auto)", required=True, section="court", auto=True),
        F.f("case_number", "प्रकरण क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("aggrieved_name", "व्यथित का नाम", "Aggrieved person's name", F.NAME, True, "parties",
            hint="सम्मान-सूचक हटाकर (टेम्पलेट श्रीमती जोड़ता है)"),
        F.f("husband_name", "पति का नाम", "Husband's name", F.NAME, True, "parties"),
        F.f("aggrieved_father", "पिता का नाम", "Father's name", F.NAME, section="parties"),
        F.f("aggrieved_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("aggrieved_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("aggrieved_address", "व्यथित का पता", "Aggrieved's address", F.ADDRESS, True, "parties"),
        F.f("respondents_desc", "प्रत्यर्थीगण (क्रमवार — एक पंक्ति प्रति प्रत्यर्थी)",
            "Respondents (one per line, serially)", F.LONGTEXT, True, "parties"),
        F.f("respondents_address", "प्रत्यर्थीगण का पता", "Respondents' address", F.ADDRESS, section="parties"),
        F.f("police_station", "आरक्षी केन्द्र (क्षेत्राधिकार)", "Police station (jurisdiction)", section="parties"),
        F.f("facts_narrative", "घरेलू हिंसा का कथानक (विवाह·दहेज·प्रताड़ना·निष्कासन)",
            "Domestic-violence narrative", F.LONGTEXT, True, "facts"),
        F.f("monetary_amount", "§20 मासिक भरण-पोषण राशि", "§20 monthly maintenance amount", F.MONEY, section="grounds", depends="monetary_relief"),
        F.f("compensation_amount", "§22 प्रतिकर राशि (एकमुश्त)", "§22 compensation (lump sum)", F.MONEY, section="grounds", depends="compensation"),
        F.f("children", "संतान (§21 अभिरक्षा हेतु)", "Children (for §21 custody)", section="grounds", depends="custody"),
        F.f("prior_litigation", "पूर्व मुकदमेबाजी का ब्योरा (यदि कोई)", "Prior litigation (if any)", F.LONGTEXT, section="facts"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.f("state_name", "राज्य", "State", section="parties", hint="रिक्त रखने पर म.प्र."))
    return F.build_spec("dv:magistrate", flds, _TOGGLES,
                        companions=["§23 interim relief application + affidavit", "Domestic Incident Report (DIR)",
                                    "witness list (साक्ष्य सूची)", "vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court_name": "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, ग्वालियर (म.प्र.)",
    "court_name_en": "Court of the Judicial Magistrate First Class, Gwalior (M.P.)",
    "case_number": "", "case_year": "2025",
    "aggrieved_name": "क ख", "aggrieved_name_en": "K.",
    "husband_name": "य र", "husband_name_en": "Y.",
    "aggrieved_father": "ओमप्रकाश", "aggrieved_father_en": "Omprakash",
    "aggrieved_age": "26", "aggrieved_occupation": "कुछ नहीं",
    "aggrieved_address": "गली नम्बर—4, मुड़िया पहाड़, नाका चन्द्रबदनी, ग्वालियर",
    "aggrieved_address_en": "Gali No. 4, Mudiya Pahad, Naka Chandrabadni, Gwalior",
    "respondents_desc": ("य र पुत्र श्री ब र, आयु— 30 वर्ष (पति) — प्रत्यर्थी क्र.1\n"
                          "ब र पुत्र स्व. श्री स र, आयु— 58 वर्ष (ससुर) — प्रत्यर्थी क्र.2\n"
                          "श्रीमती ऊ र पत्नी श्री ब र, आयु— 52 वर्ष (सास) — प्रत्यर्थी क्र.3"),
    "respondents_desc_en": ("Y., S/o B., aged 30 (husband) — Respondent No. 1\n"
                             "B., S/o late S., aged 58 (father-in-law) — Respondent No. 2\n"
                             "Smt. U., W/o B., aged 52 (mother-in-law) — Respondent No. 3"),
    "respondents_address": "गरगज कॉलोनी, बहोड़ापुर, ग्वालियर", "respondents_address_en": "Gargaj Colony, Bahodapur, Gwalior",
    "police_station": "महिला थाना पड़ाव", "police_station_en": "Mahila Thana Padav",
    "state_name": "म.प्र.", "state_name_en": "M.P.",
    "facts_narrative": (
        "व्यथित का विवाह प्रत्यर्थी क्रमांक—01 के साथ हिन्दू रीति-रिवाज से दिनांक 06.02.2024 को सम्पन्न हुआ था एवं "
        "विवाह में व्यथित के माता-पिता ने सामर्थ्य से अधिक दहेज दिया था।\n\n"
        "विदाई के समय से ही प्रत्यर्थीगण कार अथवा दस लाख रुपये एवं स्वर्ण आभूषण की अतिरिक्त दहेज मांग को लेकर "
        "व्यथित को शारीरिक एवं मानसिक रूप से प्रताड़ित करने लगे।\n\n"
        "दिनांक 08.08.2025 को प्रत्यर्थी क्रमांक—01 ने व्यथित को मात्र पहने हुये कपड़ों में रेल्वे स्टेशन पर असहाय "
        "छोड़ दिया; तब से व्यथित अपने माता-पिता के घर निवास कर रही है। व्यथित का समस्त स्त्रीधन प्रत्यर्थीगण के पास है।"
    ),
    "facts_narrative_en": (
        "the aggrieved person was married to Respondent No. 1 per Hindu rites on 06.02.2024, and her parents gave "
        "dowry beyond their means.\n\n"
        "from the very farewell the respondents began subjecting her to physical and mental cruelty over an additional "
        "dowry demand of a car or ₹10,00,000 and gold ornaments.\n\n"
        "on 08.08.2025 Respondent No. 1 abandoned her at the railway station in the clothes she wore; she has since "
        "lived at her parents' home, and her entire streedhan remains with the respondents."
    ),
    "monetary_amount": "₹50,000", "compensation_amount": "₹25,00,000",
    "prior_litigation": ("व्यथित की शिकायत पर महिला थाना पड़ाव में अपराध क्रमांक— 324/2025 अन्तर्गत धारा 85, 296, "
                          "351(3) बी.एन.एस. पंजीबद्ध हुआ है जो दौराने विवेचना है।"),
    "prior_litigation_en": ("on the aggrieved person's complaint, Crime No. 324/2025 under §§85, 296, 351(3) BNS "
                             "stands registered at Mahila Thana Padav and is under investigation."),
    "grounds": {"residence_right": True, "protection_order": True, "residence_order": True,
                "streedhan": True, "monetary_relief": True, "compensation": True, "custody": False},
    "filing_date": "__/11/2025", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="घरेलू हिंसा — धारा 12 PWDVA 2005 — समीक्षा · canonical header · §17-22 अनुतोष · सत्यापन · "
                           "द्विभाषी · विष्णु जी की Ankita sahu फाइलिंग से अक्षरशः · reviewed: false")
