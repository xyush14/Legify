"""Quashing petition — §528 BNSS / §482 CrPC (विविध आपराधिक याचिका — inherent powers).

Canonical-standard builder mirrored VERBATIM from his filed §528 petition
(benchmark: "528 / 482 — Pawan shivhare" — a COMPROMISE/राजीनामा-based quashing of an
FIR + the conviction/appeal arising from it, at the High Court). Canonical header +
section-labelled body + bilingual. No LLM writes any text.

Mirror notes (decoded — do not "improve"):
  • आवेदक (applicant/accused) vs अनावेदक (State क्र.1 + अभियोक्त्री/complainant क्र.2);
    parties by विरुद्ध (NOT बनाम — quashing house-style). Case code एम.सी.आर.सी. (M.Cr.C.). HC only.
  • Title (header, short): `प्रथम विविध आपराधिक याचिका अन्तर्गत धारा 528 भा.ना.सु.सं. (482 दं.प्र.सं.)`;
    the flowing object sits as a centred prelude: `वास्ते पुलिस थाना <ps> जिला <dist> में दर्ज
    प्रथम सूचना रिपोर्ट अपराध क्रमांक— <fir> अन्तर्गत धारा <secs> एवं उससे उत्पन्न <derived>
    की कार्यवाही राजीनामा के आधार पर न्यायिक उद्देश्यों की प्राप्ती हेतु समाप्त किये जाने बावत्।`
  • Recital: same facts/subject-matter — no other petition pending/decided (Supreme/High Court).
  • SECTION LABELS: संक्षेप विवरण ः— (यहकि facts) then आधार ः— (यहकि grounds).
  • Compromise grounds (default): valid राजीनामा · victim major & consenting · no dispute remains ·
    no collusion · continuing the proceeding not justified. (abuse_of_process toggle for the
    no-prima-facie / abuse-of-process basis instead of compromise.)
  • Prayer flows direct: accept petition → निरस्त the FIR + derived proceedings/judgment →
    terminate on compromise to secure the ends of justice → दोषमुक्त.
  • Companions: stay application + affidavit + compromise deed (राजीनामा) + index + annexures + vakalatnama.
  • No case law in body — settlement-quashing trilogy lives in CITE_AT_HEARING (verified: false).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Gian Singh v. State of Punjab (2012) 10 SCC 303",
     "point": "Inherent power to quash a non-heinous, private-natured offence on genuine compromise.", "verified": False},
    {"case": "Narinder Singh v. State of Punjab (2014) 6 SCC 466",
     "point": "Guidelines for compromise-quashing; heinous/serious offences excluded.", "verified": False},
    {"case": "State of Haryana v. Bhajan Lal 1992 Supp (1) SCC 335",
     "point": "Seven categories where FIR/proceedings may be quashed (abuse-of-process basis).", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _secs(sections, sep) -> str:
    if isinstance(sections, (list, tuple)):
        items = [_esc(s) for s in sections if str(s).strip()]
        return sep.join(items) if items else "________"
    return _esc(sections) if sections and str(sections).strip() else "________"


def _para_list(facts, grounds, lbl_f, lbl_g):
    out = ['<ol class="cb-paras">', f'<li class="cb-head">{lbl_f}</li>']
    for p in facts:
        out.append(f'<li>{p}</li>')
    out.append(f'<li class="cb-head">{lbl_g}</li>')
    for p in grounds:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    return "\n".join(out)


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name") or "म.प्र.")
    section_title = a.get("section_title") or "धारा 528 भा.ना.सु.सं. (482 दं.प्र.सं.)"
    fir = _ph(a.get("fir_number"), "..../....")
    ps = _ph(a.get("police_station"), "थाना")
    dist = _ph(a.get("district"), "जिला")
    fir_secs = _secs(a.get("fir_sections"), ", ")
    derived = _ph(a.get("derived_proceedings"), "उससे उत्पन्न आपराधिक प्रकरण/अपील")
    name = a.get("applicant_name") or ""
    g = a.get("grounds") or {}
    abuse = g.get("abuse_of_process")
    court_name = a.get("court_name") or "माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर"

    app_desc = (f'{_ph(name, "नाम")} पुत्र श्री {_ph(a.get("applicant_father"), "पिता")}, '
                f'आयु— {_ph(a.get("applicant_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("applicant_occupation"), "व्यवसाय")},')
    app_desc2 = f'निवासी— <u>{_ph(a.get("applicant_address"), "पता")}</u> ({state})'
    resp = [f'1— {state} शासन द्वारा पुलिस थाना {ps} जिला {dist} ({state})',
            f'2— अभियोक्त्री द्वारा पुलिस थाना {ps} जिला {dist} ({state})']

    hdr = render_header({
        "side_label": "", "court_name": court_name,
        "case_code": "एम.सी.आर.सी.", "case_suffix": "",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "आवेदक", "applicant_desc": [app_desc, app_desc2],
        "respondent_label": "अनावेदक", "respondent_desc": resp,
        "versus": "विरुद्ध", "title_line": f"प्रथम विविध आपराधिक याचिका अन्तर्गत {section_title}",
    })

    basis = ('राजीनामा के आधार पर न्यायिक उद्देश्यों की प्राप्ती हेतु' if not abuse
             else 'विधि-प्रक्रिया के दुरुपयोग की रोकथाम एवं न्यायहित में')
    out = [hdr, '<div class="doc-body">']
    out.append(f'<p class="cb-prelude" style="text-align:center">वास्ते पुलिस थाना {ps} जिला {dist} में दर्ज प्रथम '
               f'सूचना रिपोर्ट अपराध क्रमांक— {fir} अन्तर्गत धारा {fir_secs} एवं उससे उत्पन्न {derived} की कार्यवाही '
               f'{basis} समाप्त/निरस्त किये जाने बावत्।</p>')
    out.append('<p class="cb-prelude">समान तथ्य एवं समान विषय-वस्तु का अन्य कोई प्रकरण आवेदक की ओर से न तो माननीय '
               'सर्वोच्च न्यायालय एवं न ही माननीय उच्च न्यायालय में प्रस्तुत है और न ही निराकृत है।</p>')
    out.append('<p class="cb-prelude">आवेदक की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')

    facts = []
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            facts.append(f'यहकि, {_esc(ch)}')
    else:
        facts.append('<span class="ph">[प्रथम सूचना रिपोर्ट · विवेचना · '
                     'अभियोग पत्र/दोषसिद्धि · लंबित कार्यवाही — संक्षिप्त विवरण यहाँ]</span>')

    G = []
    if not abuse:
        G.append('यहकि, प्रकरण के तथ्यों एवं परिस्थितियों को दृष्टिगत रखते हुये प्रकरण राजीनामा के आधार पर समाप्त '
                 'किया जाना न्यायोचित है।')
        if g.get("victim_consenting", True):
            G.append('यहकि, फरियादी/अभियोक्त्री पूर्णतः बालिग एवं अपना भला-बुरा सोचने में सक्षम है तथा आवेदक से '
                     'स्वेच्छापूर्वक राजीनामा करने हेतु सहमत है।')
        if g.get("compromise_voluntary", True):
            G.append('यहकि, आवेदक एवं फरियादी पक्ष के मध्य समाज के प्रतिष्ठित लोगों की उपस्थिति में स्वेच्छापूर्वक '
                     'राजीनामा हो चुका है, जिसकी प्रति इस याचिका के साथ संलग्न है; मध्य में कोई दुरभिसंधि नहीं है।')
        if g.get("no_dispute_remains", True):
            G.append('यहकि, राजीनामा हो जाने के पश्चात् पक्षकारों के मध्य कोई विवाद शेष नहीं है; कार्यवाही जारी '
                     'रखा जाना न्यायोचित नहीं है।')
    else:
        G.append('यहकि, प्रकरण के अभिकथन को सम्पूर्ण रूप से सत्य मान लिया जावे तब भी आवेदक के विरुद्ध कोई संज्ञेय '
                 'अपराध प्रथम दृष्टया प्रकट नहीं होता; कार्यवाही विधि-प्रक्रिया का दुरुपयोग है।')
    if (a.get("grounds_narrative") or "").strip():
        for ch in [x.strip() for x in a["grounds_narrative"].split("\n\n") if x.strip()]:
            G.append(f'यहकि, {_esc(ch)}')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'यहकि, {_esc(cu)}')
    G.append('यहकि, अन्य आधार वक्त बहस मौखिक रूप से निवेदित किये जावेंगे।')

    out.append(_para_list(facts, G, "संक्षेप विवरण ः—", "आधार ः—"))
    relief_tail = (f' एवं उससे उत्पन्न कार्यवाही {derived} को राजीनामा के आधार पर न्यायिक उद्देश्यों की प्राप्ती हेतु '
                   f'समाप्त कर आवेदक को दोषमुक्त' if not abuse
                   else f' एवं उससे उत्पन्न समस्त कार्यवाही {derived} को')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः माननीय न्यायालय से विनम्र निवेदन है कि आवेदक की ओर से प्रस्तुत याचिका स्वीकार कर पुलिस थाना '
               f'{ps} जिला {dist} के अपराध क्रमांक— {fir} (एनेक्जर ए-1){relief_tail} किये जाने का आदेश पारित करने '
               f'की कृपा करें।')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांकः— {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>प्रार्थी</div><div>{_ph(name, "नाम")} — आवेदक</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('<div class="cb-note">साथ संलग्न: स्थगन आवेदन (मय शपथपत्र) · राजीनामा/समझौता-पत्र · इन्डेक्स · '
               'प्र.सू.रि. (ए-1) · निर्णय/आदेश की प्रति (ए-2) · वकालतनामा।</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    state = _esc(a.get("state_name_en") or "M.P.")
    fir = _ph(a.get("fir_number"), "..../....")
    ps = _ph(a.get("police_station_en") or a.get("police_station"), "P.S.")
    dist = _ph(a.get("district_en") or a.get("district"), "District")
    fir_secs = _secs(a.get("fir_sections_en") or a.get("fir_sections"), ", ")
    derived = _ph(a.get("derived_proceedings_en") or a.get("derived_proceedings"), "the proceedings arising therefrom")
    name = _ph(a.get("applicant_name_en") or a.get("applicant_name"), "applicant")
    g = a.get("grounds") or {}
    abuse = g.get("abuse_of_process")

    app = (f'{name}, S/o {_ph(a.get("applicant_father_en") or a.get("applicant_father"), "father")}, '
           f'aged {_ph(a.get("applicant_age"), "..")} years, R/o '
           f'{_ph(a.get("applicant_address_en") or a.get("applicant_address"), "address")} ({state})')
    resp = [f'1. State of {state} through Police Station {ps}, District {dist}',
            f'2. The Prosecutrix/Complainant through Police Station {ps}, District {dist}']

    hdr = render_header({
        "side_label": "", "court_name": a.get("court_name_en") or "High Court of Madhya Pradesh, Bench at Gwalior",
        "case_code": "M.Cr.C.", "case_suffix": "",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [app],
        "respondent_label": "Respondents", "respondent_desc": resp,
        "versus": "Versus",
        "title_line": "MISC. CRIMINAL CASE UNDER SECTION 528 BNSS, 2023 (SECTION 482 CrPC)",
    })
    basis = ('on the basis of compromise, to secure the ends of justice' if not abuse
             else 'to prevent abuse of the process of law and to secure the ends of justice')
    out = [hdr, '<div class="doc-body">']
    out.append(f'<p class="cb-prelude" style="text-align:center">For quashing FIR No. {fir} under {fir_secs} '
               f'registered at Police Station {ps}, District {dist}, and {derived}, {basis}.</p>')
    out.append('<p class="cb-prelude">That no other petition on the same facts and subject-matter is pending or has '
               'been decided, before the Hon\'ble Supreme Court or this Hon\'ble Court, on the applicant\'s behalf.</p>')
    out.append('<p class="cb-prelude">The applicant most respectfully submits as under:—</p>')

    facts = []
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            facts.append(f'That {_esc(ch)}')
    else:
        facts.append('[FIR · investigation · charge-sheet/conviction · pending proceeding — brief particulars here.]')

    G = []
    if not abuse:
        G.append('That, regard being had to the facts and circumstances, it is just and proper to terminate the '
                 'proceedings on the basis of compromise.')
        if g.get("victim_consenting", True):
            G.append('That the complainant/prosecutrix is a major capable of taking her own decisions and has '
                     'voluntarily agreed to compromise with the applicant.')
        if g.get("compromise_voluntary", True):
            G.append('That a voluntary compromise has been arrived at between the applicant and the complainant '
                     'party before respectable members of society (deed annexed); there is no collusion.')
        if g.get("no_dispute_remains", True):
            G.append('That after the compromise no dispute survives between the parties; continuing the proceeding '
                     'is not justified.')
    else:
        G.append('That even taking the allegations at their highest, no cognizable offence is prima facie made out '
                 'against the applicant; continuing the proceeding is an abuse of the process of law.')
    gn = a.get("grounds_narrative_en") or a.get("grounds_narrative") or ""
    if gn.strip():
        for ch in [x.strip() for x in gn.split("\n\n") if x.strip()]:
            G.append(f'That {_esc(ch)}')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'That {_esc(cu)}')
    G.append('That further grounds shall be urged orally at the time of hearing.')

    out.append(_para_list(facts, G, "BRIEF FACTS:—", "GROUNDS:—"))
    tail = (' and terminate the proceedings arising therefrom on the basis of compromise to secure the ends of '
            'justice, and acquit the applicant' if not abuse else ' and all proceedings arising therefrom')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may be '
               f'pleased to allow the petition and quash FIR No. {fir} (Annexure A-1) registered at Police Station '
               f'{ps}, District {dist}{tail}.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Applicant</div><div>{name} — Applicant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")}) — Advocate</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("victim_consenting", "पीड़ित/अभियोक्त्री बालिग एवं स्वेच्छा से सहमत",
             "Victim/prosecutrix major & voluntarily consenting", default=True),
    F.toggle("compromise_voluntary", "स्वेच्छापूर्वक राजीनामा (समाज के समक्ष) — दुरभिसंधि नहीं",
             "Voluntary compromise before society — no collusion", default=True),
    F.toggle("no_dispute_remains", "राजीनामे के पश्चात् कोई विवाद शेष नहीं",
             "No dispute survives after compromise", default=True),
    F.toggle("abuse_of_process", "आधार: राजीनामा नहीं, बल्कि प्रथम-दृष्टया अपराध नहीं / प्रक्रिया-दुरुपयोग",
             "Basis: not compromise — no prima-facie offence / abuse of process", default=False),
]


def field_spec(court: str = "hc") -> dict:
    flds = [
        F.f("court_name", "उच्च न्यायालय खण्डपीठ (स्वतः)", "High Court Bench (auto)", required=True, section="court", auto=True),
        F.f("case_number", "एम.सी.आर.सी. क्रमांक", "M.Cr.C. no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.DATE, section="court"),
        F.f("section_title", "याचिका का प्रावधान", "Petition provision", section="court",
            hint="धारा 528 भा.ना.सु.सं. (482 दं.प्र.सं.) — सम्पादनीय"),
        F.f("applicant_name", "आवेदक का नाम", "Applicant name", F.NAME, True, "parties"),
        F.f("applicant_father", "पिता का नाम", "Father", F.NAME, section="parties"),
        F.f("applicant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("applicant_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("applicant_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("police_station", "आरक्षी केन्द्र (थाना)", "Police station", required=True, section="crime", ocr="fir"),
        F.f("district", "जिला", "District", section="crime", ocr="fir"),
        F.f("fir_number", "प्रथम सूचना रिपोर्ट अपराध क्रमांक", "FIR / Crime no.", required=True, section="crime", ocr="fir"),
        F.f("fir_sections", "एफ.आई.आर. की धाराएँ", "FIR sections", F.SECTION_LIST, True, "crime", ocr="fir"),
        F.f("derived_proceedings", "उससे उत्पन्न कार्यवाही (प्रकरण/अपील — नामतः)",
            "Proceedings arising (case/appeal — named)", F.LONGTEXT, True, "crime"),
        F.f("facts_narrative", "संक्षेप विवरण (FIR·विवेचना·दोषसिद्धि·लंबित कार्यवाही)",
            "Brief facts (FIR·investigation·conviction·pending)", F.LONGTEXT, True, "facts", ocr="fir"),
        F.f("grounds_narrative", "अतिरिक्त आधार (प्रकरण-विशिष्ट)", "Additional grounds (case-specific)", F.LONGTEXT, section="grounds"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    return F.build_spec("quashing:hc", flds, _TOGGLES,
                        companions=["stay application + affidavit", "compromise deed (राजीनामा)",
                                    "index (इन्डेक्स)", "certified copy of FIR + impugned judgment (annexures)",
                                    "vakalatnama"])


# ----------------------------------------------------------- SAMPLE + review
SAMPLE = {
    "court_name": "माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर",
    "court_name_en": "High Court of Madhya Pradesh, Bench at Gwalior",
    "case_number": "", "case_year": "2026", "section_title": "धारा 528 भा.ना.सु.सं. (482 दं.प्र.सं.)",
    "applicant_name": "क ख", "applicant_name_en": "K.", "applicant_father": "रमेशचन्द्र", "applicant_father_en": "Rameshchandra",
    "applicant_age": "34", "applicant_occupation": "मजदूरी",
    "applicant_address": "गायत्री मंदिर के पास, सेवढ़ा जिला दतिया", "applicant_address_en": "Near Gayatri Mandir, Seondha, Distt. Datia",
    "state_name": "म.प्र.", "state_name_en": "M.P.",
    "police_station": "सेवढ़ा", "police_station_en": "Seondha", "district": "दतिया", "district_en": "Datia",
    "fir_number": "139/2020", "fir_sections": ["354 भा.द.वि.", "506 भा.द.वि."], "fir_sections_en": ["354 IPC", "506 IPC"],
    "derived_proceedings": ("उससे उत्पन्न आपराधिक प्रकरण क्रमांक— 13/2021 में पारित दोषसिद्धि निर्णय दिनांक 30.04.2025 "
                            "एवं उसके विरुद्ध लंबित आपराधिक अपील क्रमांक— 52/2025 (अपर सत्र न्यायालय सेवढ़ा)"),
    "derived_proceedings_en": ("the conviction dated 30.04.2025 in Criminal Case No. 13/2021 arising therefrom and "
                                "the pending Criminal Appeal No. 52/2025 (Addl. Sessions Court, Seondha)"),
    "facts_narrative": (
        "पीड़िता एवं आवेदक सेवढ़ा जिला दतिया के निवासी हैं; पीड़िता की शिकायत पर आरक्षी केन्द्र सेवढ़ा द्वारा "
        "अपराध क्रमांक— 139/2020 अन्तर्गत धारा 354, 506 भा.द.वि. पंजीबद्ध किया गया।\n\n"
        "विचारण उपरान्त आवेदक को प्रकरण क्रमांक— 13/2021 में दिनांक 30.04.2025 को दोषसिद्ध किया गया, जिसके विरुद्ध "
        "आपराधिक अपील क्रमांक— 52/2025 विचाराधीन है।\n\n"
        "अब आवेदक एवं फरियादी पक्ष के मध्य समाज के प्रतिष्ठित लोगों की उपस्थिति में स्वेच्छापूर्वक राजीनामा हो चुका है।"
    ),
    "facts_narrative_en": (
        "the prosecutrix and the applicant reside in Seondha, Distt. Datia; on her complaint, Crime No. 139/2020 "
        "under §§354, 506 IPC was registered at P.S. Seondha.\n\n"
        "after trial the applicant was convicted in Case No. 13/2021 on 30.04.2025, against which Criminal Appeal "
        "No. 52/2025 is pending.\n\n"
        "the applicant and the complainant party have now voluntarily compromised before respectable members of society."
    ),
    "grounds": {"victim_consenting": True, "compromise_voluntary": True, "no_dispute_remains": True, "abuse_of_process": False},
    "filing_date": "__/01/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="विविध आपराधिक याचिका — धारा 528 भा.ना.सु.सं. (482 दं.प्र.सं.) — समीक्षा · canonical header · "
                           "राजीनामा-आधार · खण्ड-शीर्षक · द्विभाषी · विष्णु जी की Pawan shivhare फाइलिंग से अक्षरशः · reviewed: false")
