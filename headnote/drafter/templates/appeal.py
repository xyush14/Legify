"""Criminal Appeal against Conviction — §415 & §419 BNSS / §374 & §386 CrPC (आपराधिक अपील).

Canonical-standard builder mirrored VERBATIM from his filed appeal (benchmark:
"Apradhik apil Raju nayak" — a §374 CrPC appeal at the Sessions Court against a
Magistrate conviction; fine-only sentence). Canonical header + section-labelled
body + bilingual. No LLM writes any text.

Mirror notes (from the decoded filing — do not "improve"):
  • अपीलार्थी (appellant) vs प्रतिअपीलार्थी (State); parties separated by बनाम.
  • Case line `प्रकरण क्रमांक— ___/<वर्ष> आपराधिक अपील` (suffix); Sessions for a
    Magistrate conviction, High Court for a Sessions conviction.
  • Title (header, short): `आपराधिक अपील अन्तर्गत <provision>`; the flowing
    impugned-judgment sentence sits as a centred prelude BELOW the header:
    `विरुद्ध निर्णय दिनांक <date> पारित न्यायालय द्वारा विद्वान <court> (<judge>)
    द्वारा दाण्डिक प्रकरण क्रमांक— <no> उन्मान <State> राज्य बनाम <appellant> में …
    अपीलार्थी को धारा <secs> में <sentence> से दण्डित … निर्णय पारित किया है।`
  • Recital: no other appeal pending/rejected. Salutation `श्रीमान जी,`.
  • SECTION LABELS: प्रकरण के तथ्य ः— (NARRATIVE paras — prosecution case, issues
    framed, conviction recap, aggrieved transition) then अपील के आधार ः— (यहकि grounds).
  • Grounds attack the conviction (contrary to law / evidence not led / witness
    contradictions / issues not proved / [excessive sentence] / [clean image]).
  • Prayer flows directly (NO heading): call the record from the court below
    (`अभिलेखागार से मंगाया जाकर`), set aside (`निरस्त कर`), acquit (`दोषमुक्त`),
    and (fine cases) refund the fine (`जुर्माने की राशि वापिस`).
  • No case law in the body — candidates live in CITE_AT_HEARING (verified: false).
"""
from __future__ import annotations

from datetime import date
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name
from headnote.drafter.templates import _fields as F

CITE_AT_HEARING = [
    {"case": "Sharad Birdhichand Sarda v. State of Maharashtra (1984) 4 SCC 116",
     "point": "Five golden principles — circumstantial chain must be complete and point only to guilt.", "verified": False},
    {"case": "Kali Ram v. State of Himachal Pradesh (1973) 2 SCC 808",
     "point": "Benefit of every reasonable doubt goes to the accused.", "verified": False},
    {"case": "Babu v. State of Kerala (2010) 9 SCC 189",
     "point": "Appellate court can re-appreciate evidence; presumption of innocence reinforced by acquittal-style scrutiny.", "verified": False},
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


def _cfg(court):
    if court == "hc":   # appeal from a Sessions conviction
        return dict(level="hc", case_code="आपराधिक अपील क्रमांक", suffix="", case_code_en="Cr.A. No.")
    # appeal from a Magistrate conviction → Sessions Court (his Raju nayak benchmark)
    return dict(level="sessions", case_code="प्रकरण क्रमांक", suffix="आपराधिक अपील", case_code_en="Criminal Appeal No.")


def _para_list(facts, grounds, lbl_facts, lbl_grounds):
    out = ['<ol class="cb-paras">', f'<li class="cb-head">{lbl_facts}</li>']
    for p in facts:
        out.append(f'<li>{p}</li>')
    out.append(f'<li class="cb-head">{lbl_grounds}</li>')
    for p in grounds:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    return "\n".join(out)


# ----------------------------------------------------------- HINDI
def render_hi(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "sessions"
    c = _cfg(court)
    state = _esc(a.get("state_name") or "________")
    section_title = a.get("section_title") or "धारा 415 भा.ना.सु.सं. (374 दं.प्र.सं.)"
    name = a.get("appellant_name") or ""
    conviction_date = _ph(a.get("conviction_date"), "..........")
    convicting_court = _ph(a.get("convicting_court"), "विचारण न्यायालय")
    trial_case_no = _ph(a.get("trial_case_no"), "..../....")
    sentence = _ph(a.get("sentence_passed"), "दण्ड")
    sec_str = _secs(a.get("sections_convicted"), " तथा ")
    matter_title = f'{state} राज्य बनाम {_ph(name, "अपीलार्थी")}'
    # Always route through the pan-India chokepoint — it leaves blanks (____) when
    # city/state are unknown and NEVER defaults to MP. (Do not reintroduce a
    # hardcoded "(म.प्र.)" fallback here — see feedback_court_location.)
    court_name = a.get("court_name") or compose_court_name(c["level"], a.get("court_city"), state)

    # appellant descriptor (label-left canonical block)
    occ = a.get("appellant_occupation")
    l1 = f'{_ph(name, "नाम")} पुत्र श्री {_ph(a.get("appellant_father"), "पिता")}, आयु— {_ph(a.get("appellant_age"), "..")} वर्ष,'
    if occ:
        l1 += f' व्यवसाय— {_esc(occ)},'
    l2 = f'निवासी— <u>{_ph(a.get("appellant_address"), "पता")}</u> ({state})'
    if a.get("present_address"):
        l2 += f', हाल निवासी— <u>{_esc(a.get("present_address"))}</u>'
    if a.get("current_jail"):
        l2 += f', वर्तमान में <u>{_esc(a.get("current_jail"))}</u> में निरुद्ध'

    hdr = render_header({
        "side_label": "", "court_name": court_name,
        "case_code": c["case_code"], "case_suffix": c["suffix"],
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "अपीलार्थी", "applicant_desc": [l1, l2],
        "respondent_label": "प्रतिअपीलार्थी",
        "respondent_desc": [f'{state} राज्य द्वारा आरक्षी केन्द्र {_ph(a.get("police_station"), "थाना")} '
                            f'जिला {_ph(a.get("district"), "जिला")} ({state})'],
        "versus": "बनाम", "title_line": f"आपराधिक अपील अन्तर्गत {section_title}",
    })

    out = [hdr, '<div class="doc-body">']
    out.append(f'<p class="cb-prelude" style="text-align:center">विरुद्ध निर्णय दिनांक {conviction_date} पारित '
               f'न्यायालय द्वारा विद्वान {convicting_court}'
               + (f' ({_esc(a.get("convicting_judge"))})' if a.get("convicting_judge") else '')
               + f' द्वारा दाण्डिक प्रकरण क्रमांक— {trial_case_no} उन्मान {matter_title} में निर्णय पारित कर '
               f'अपीलार्थी को धारा {sec_str} में {sentence} से दण्डित किये जाने का निर्णय पारित किया है।</p>')
    out.append('<p class="cb-prelude">अपीलार्थी द्वारा आज दिनांक तक माननीय न्यायालय अथवा माननीय उच्च न्यायालय के '
               'समक्ष इसके अतिरिक्त अन्य कोई अपील न तो प्रस्तुत हुई है और न ही निरस्त हुई है।</p>')
    out.append('<p class="cb-prelude">श्रीमान जी,</p>')
    out.append('<p class="cb-prelude">अपीलार्थी की ओर से आपराधिक अपील निम्न प्रकार प्रस्तुत है ः—</p>')

    facts = []
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            facts.append(_esc(ch))
    else:
        facts.append('<span class="ph">[अभियोजन का कथानक संक्षेप में, '
                     'विचारण न्यायालय में निर्मित विचारणीय प्रश्न एवं दोषसिद्धि — या विवादित निर्णय अपलोड कर भरें]</span>')
    facts.append(f'उपरोक्त निर्णय द्वारा अपीलार्थी को दण्डित किये जाने से दुखित होकर यह आपराधिक अपील अपीलार्थी '
                 f'द्वारा निम्नलिखित आधारों पर प्रस्तुत की गई है।')

    g = a.get("grounds") or {}
    G = [f'यहकि, विद्वान विचारण न्यायालय द्वारा पारित निर्णय दिनांक {conviction_date} विधि विधान के विपरीत होकर '
         f'स्थिर रखे जाने योग्य नहीं है, क्योंकि विचारण न्यायालय द्वारा भावनात्मक विवेक एवं कल्पना के आधार पर '
         f'निर्णय पारित किया गया है।']
    if (a.get("grounds_narrative") or "").strip():
        for ch in [x.strip() for x in a["grounds_narrative"].split("\n\n") if x.strip()]:
            G.append(f'यहकि, {_esc(ch)}')
    if g.get("evidence_ignored", True):
        G.append('यहकि, अभियोजन द्वारा अपने कथानक के समर्थन में आवश्यक साक्ष्य विचारण न्यायालय के समक्ष प्रस्तुत '
                 'नहीं की गई, फिर भी उक्त तथ्य को अनदेखा कर विचारण न्यायालय द्वारा गम्भीर कानूनी त्रुटि कारित की गई है।')
    if g.get("pw_contradictions", True):
        G.append('यहकि, अभियोजन साक्षीगण के कथनों में परस्पर गम्भीर विरोधाभास है, जिससे अभियोजन प्रकरण को सन्देह '
                 'से परे प्रमाणित करने में पूर्णतः असफल रहा है।')
    if g.get("issues_not_proved", True):
        G.append('यहकि, विद्वान विचारण न्यायालय द्वारा निर्धारित विचारणीय प्रश्नों को अभियोजन पक्ष प्रमाणित करने में '
                 'असफल रहा है, ऐसी स्थिति में दिया गया दण्डादेश स्थिर रखने योग्य नहीं है।')
    if g.get("sentence_excessive"):
        G.append('यहकि, अधिरोपित दण्ड अपराध की प्रकृति एवं अपीलार्थी की भूमिका को देखते हुए अत्यधिक एवं अनुपातहीन है; '
                 'वैकल्पिक रूप से दण्ड को कम किया जाना न्यायोचित है।')
    if g.get("clean_image"):
        G.append('यहकि, अपीलार्थी की समाज में स्वच्छ छवि है; दण्डादेश से उसकी आपराधिक छवि बन जाएगी, जिससे उसका शेष '
                 'जीवन दागदार हो जाएगा। ऐसी स्थिति में विचारण न्यायालय के दण्डादेश को अपास्त कर अपीलार्थी को दोषमुक्त '
                 'किया जाना न्यायहित में अतिआवश्यक है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'यहकि, {_esc(cu)}')
    G.append('यहकि, शेष तथ्य वक्त बहस मौखिक रूप से निवेदित होंगे।')

    out.append(_para_list(facts, G, "प्रकरण के तथ्य ः—", "अपील के आधार ः—"))

    fine_tail = (' एवं अपीलार्थी द्वारा जमा अर्थदण्ड की राशि वापिस दिलाये जाने' if g.get("fine_deposited") else '')
    out.append('<div class="cb-prayer"><p>')
    out.append(f'अतः माननीय न्यायालय से निवेदन है कि प्रकरण से सम्बन्धित अभिलेख विद्वान {convicting_court} द्वारा '
               f'दाण्डिक प्रकरण क्रमांक— {trial_case_no} ({matter_title}) का अभिलेखागार से मंगाया जाकर, विद्वान '
               f'अधीनस्थ न्यायालय द्वारा पारित निर्णय दिनांक {conviction_date} को निरस्त कर अपीलार्थी को दोषमुक्त '
               f'किये जाने{fine_tail} का आदेश पारित करने की कृपा करें।')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>दिनांकः— {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>प्रार्थी</div><div>{_ph(name, "अपीलार्थी")} — अपीलार्थी</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    susp = (' विवादित निर्णय/दण्डादेश के निलम्बन हेतु पृथक आवेदन धारा 430 भा.ना.सु.सं. (389 दं.प्र.सं.);'
            if a.get("current_jail") else '')
    out.append('<div class="cb-note">साथ संलग्न: विवादित निर्णय दिनांक की प्रमाणित प्रति (एनेक्जर ए-1) · वकालतनामा।'
               + susp + ' (उच्च न्यायालय में अपील पर: इन्डेक्स।)</div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- ENGLISH
def render_en(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "sessions"
    c = _cfg(court)
    state = _esc(a.get("state_name_en") or a.get("state_name") or "________")
    name = _ph(a.get("appellant_name_en") or a.get("appellant_name"), "appellant")
    conviction_date = _ph(a.get("conviction_date"), "..........")
    convicting_court = _ph(a.get("convicting_court_en") or a.get("convicting_court"), "trial court")
    trial_case_no = _ph(a.get("trial_case_no"), "..../....")
    sentence = _ph(a.get("sentence_passed_en") or a.get("sentence_passed"), "sentence")
    sec_str = _secs(a.get("sections_convicted_en") or a.get("sections_convicted"), " and ")
    matter_title = f'State of {state} vs {name}'

    occ = a.get("appellant_occupation_en") or a.get("appellant_occupation")
    desc = (f'{name}, S/o {_ph(a.get("appellant_father_en") or a.get("appellant_father"), "father")}, '
            f'aged about {_ph(a.get("appellant_age"), "..")} years'
            + (f', {_esc(occ)} by occupation' if occ else '')
            + f', R/o {_ph(a.get("appellant_address_en") or a.get("appellant_address"), "address")} ({state})')
    if a.get("present_address_en") or a.get("present_address"):
        desc += f', presently at {_ph(a.get("present_address_en") or a.get("present_address"), "")}'
    if a.get("current_jail_en") or a.get("current_jail"):
        desc += f', presently lodged at {_ph(a.get("current_jail_en") or a.get("current_jail"), "")}'

    hdr = render_header({
        "side_label": "", "court_name": a.get("court_name_en") or compose_court_name(
            c["level"], a.get("court_city_en") or a.get("court_city"), state, lang="en"),
        "case_code": c["case_code_en"], "case_suffix": "",
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Appellant", "applicant_desc": [desc],
        "respondent_label": "Respondent",
        "respondent_desc": [f'State of {state} through Police Station '
                            f'{_ph(a.get("police_station_en") or a.get("police_station"), "police station")}, '
                            f'District {_ph(a.get("district_en") or a.get("district"), "district")}'],
        "versus": "Versus",
        "title_line": "CRIMINAL APPEAL UNDER SECTION 415 BNSS, 2023 (SECTION 374 CrPC) AGAINST CONVICTION",
    })

    g = a.get("grounds") or {}
    fn = a.get("facts_narrative_en") or a.get("facts_narrative") or ""
    gn = a.get("grounds_narrative_en") or a.get("grounds_narrative") or ""
    out = [hdr, '<div class="doc-body">']
    out.append(f'<p class="cb-prelude" style="text-align:center">Against the judgment of conviction dated '
               f'{conviction_date} passed by the learned {convicting_court}'
               + (f' ({_esc(a.get("convicting_judge_en") or a.get("convicting_judge"))})'
                  if (a.get("convicting_judge_en") or a.get("convicting_judge")) else '')
               + f' in Case No. {trial_case_no} ({matter_title}), convicting the appellant under {sec_str} and '
               f'sentencing him to {sentence}.</p>')
    out.append('<p class="cb-prelude">That no other appeal is pending or has been rejected before this Hon\'ble '
               'Court or the Hon\'ble High Court.</p>')
    out.append('<p class="cb-prelude">MOST RESPECTFULLY SHEWETH:—</p>')

    facts = []
    if fn.strip():
        for ch in [x.strip() for x in fn.split("\n\n") if x.strip()]:
            facts.append(_esc(ch))
    else:
        facts.append('[Brief facts — the prosecution case, the issues framed and the conviction.]')
    facts.append('Aggrieved by the said judgment of conviction, the appellant prefers this appeal on the '
                 'following grounds.')

    G = [f'That the judgment dated {conviction_date} is contrary to law and unsustainable, having been passed '
         f'on conjecture and surmise.']
    if gn.strip():
        for ch in [x.strip() for x in gn.split("\n\n") if x.strip()]:
            G.append(f'That {_esc(ch)}')
    if g.get("evidence_ignored", True):
        G.append('That the prosecution failed to lead necessary evidence in support of its case, yet the trial '
                 'court ignored this and erred gravely in law.')
    if g.get("pw_contradictions", True):
        G.append('That there are serious contradictions in the statements of the prosecution witnesses, so the '
                 'prosecution failed to prove its case beyond reasonable doubt.')
    if g.get("issues_not_proved", True):
        G.append('That the prosecution failed to prove the issues framed by the trial court, and the sentence is '
                 'therefore unsustainable.')
    if g.get("sentence_excessive"):
        G.append('That the sentence is excessive and disproportionate to the nature of the offence and the '
                 'appellant\'s role; in the alternative, it deserves to be reduced.')
    if g.get("clean_image"):
        G.append('That the appellant has a clean image in society; the conviction would stigmatise the rest of '
                 'his life, and it is necessary in the interest of justice that the sentence be set aside and the '
                 'appellant acquitted.')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'That {_esc(cu)}')
    G.append('That further submissions shall be made orally at the time of hearing.')

    out.append(_para_list(facts, G, "BRIEF FACTS:—", "GROUNDS OF APPEAL:—"))
    fine_tail = (' and refund of the fine deposited by the appellant' if g.get("fine_deposited") else '')
    out.append(f'<div class="cb-prayer"><p>It is therefore most respectfully prayed that this Hon\'ble Court may '
               f'be pleased to call for the record of Case No. {trial_case_no} from the learned {convicting_court}, '
               f'set aside the judgment dated {conviction_date}, and acquit the appellant{fine_tail}.</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append(f'<div class="r"><div>Appellant</div><div>{name} — Appellant</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")}) — Advocate</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("evidence_ignored", "अभियोजन ने आवश्यक साक्ष्य प्रस्तुत नहीं की",
             "Prosecution failed to lead necessary evidence", default=True),
    F.toggle("pw_contradictions", "अभियोजन साक्षीगण के कथनों में विरोधाभास",
             "Contradictions among prosecution witnesses", default=True),
    F.toggle("issues_not_proved", "विचारणीय प्रश्न प्रमाणित नहीं हुए",
             "Issues framed not proved", default=True),
    F.toggle("sentence_excessive", "दण्ड अत्यधिक — वैकल्पिक रूप से कम किया जावे",
             "Sentence excessive — alternatively reduce", default=False),
    F.toggle("clean_image", "अपीलार्थी की स्वच्छ छवि (दोषमुक्ति न्यायहित में)",
             "Appellant's clean image (acquittal in interest of justice)", default=False),
    F.toggle("fine_deposited", "जमा अर्थदण्ड की वापसी चाही गई",
             "Refund of fine deposited is sought", default=False),
]


def field_spec(court: str = "sessions") -> dict:
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", section="court", hint="लोकेशन से स्वतः → न्यायालय नाम"),
        F.f("court_name", "अपीलीय न्यायालय का नाम (स्वतः)", "Appellate court name (auto)", required=True, section="court", auto=True),
        F.f("case_number", "अपील क्रमांक", "Appeal no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("section_title", "अपील का प्रावधान", "Appeal provision", section="court",
            hint="धारा 415 भा.ना.सु.सं. (374 दं.प्र.सं.) — सम्पादनीय"),
        F.f("appellant_name", "अपीलार्थी का नाम", "Appellant name", F.NAME, True, "parties"),
        F.f("appellant_father", "पिता का नाम", "Father", F.NAME, section="parties"),
        F.f("appellant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("appellant_occupation", "व्यवसाय (यदि लिखना हो)", "Occupation (optional)", section="parties"),
        F.f("appellant_address", "पता", "Address", F.ADDRESS, True, "parties"),
        F.f("present_address", "हाल निवासी (यदि भिन्न)", "Present address (if different)", F.ADDRESS, section="parties"),
        F.f("current_jail", "वर्तमान कारागार (यदि निरुद्ध)", "Current jail (if in custody)", section="parties",
            hint="भरा हो तो धारा 430 निलम्बन-आवेदन साथ चलेगा"),
        F.f("state_name", "राज्य", "State", section="parties"),
        F.f("police_station", "आरक्षी केन्द्र (थाना)", "Police station", section="parties", ocr="order"),
        F.f("district", "जिला", "District", section="parties"),
        F.f("convicting_court", "दोषसिद्ध करने वाला न्यायालय", "Convicting (trial) court", required=True, section="order", ocr="order"),
        F.f("convicting_judge", "पीठासीन अधिकारी (यदि लिखना हो)", "Presiding officer (optional)", section="order", ocr="order"),
        F.f("trial_case_no", "विचारण प्रकरण क्रमांक", "Trial case no.", required=True, section="order", ocr="order"),
        F.f("conviction_date", "विवादित निर्णय दिनांक", "Impugned judgment date", F.DATE, True, "order", ocr="order"),
        F.f("sections_convicted", "दोषसिद्धि की धाराएँ", "Sections convicted", F.SECTION_LIST, True, "order", ocr="order"),
        F.f("sentence_passed", "अधिरोपित दण्ड", "Sentence passed", F.LONGTEXT, True, "order", ocr="order"),
        F.f("facts_narrative", "प्रकरण के तथ्य (अभियोजन कथानक + विचारणीय प्रश्न + दोषसिद्धि)",
            "Brief facts (prosecution case + issues framed + conviction)", F.LONGTEXT, True, "facts", ocr="order"),
        F.f("grounds_narrative", "अपील के आधार (प्रकरण-विशिष्ट)", "Grounds of appeal (case-specific)", F.LONGTEXT, True, "grounds"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    flds.append(F.custom_grounds())
    return F.build_spec(f"appeal:{court}", flds, _TOGGLES,
                        variants={"court": ["sessions", "hc"]},
                        companions=["certified copy of impugned judgment (annexure)", "vakalatnama",
                                    "§430 BNSS suspension-of-sentence application (if in custody)",
                                    "index (इन्डेक्स) — for High Court appeals"])


# ----------------------------------------------------------- SAMPLE + review
# Genericised illustrative example (NOT a real client) — modelled on the
# "Raju nayak" §374 Sessions appeal (fine-only Magistrate conviction).
SAMPLE = {
    "court": "sessions",
    "court_name": "न्यायालय माननीय सत्र न्यायाधीश महोदय, जिला ग्वालियर (म.प्र.)",
    "court_name_en": "Court of the Sessions Judge, District Gwalior (M.P.)",
    "case_number": "", "case_year": "2026",
    "section_title": "धारा 415 भा.ना.सु.सं. (374 दं.प्र.सं.)",
    "appellant_name": "क ख ग", "appellant_name_en": "K.",
    "appellant_father": "य र ल", "appellant_father_en": "Y.",
    "appellant_age": "62", "appellant_address": "ग्राम ____, थाना मोहना जिला ग्वालियर",
    "appellant_address_en": "Village ____, P.S. Mohna, District Gwalior",
    "present_address": "मकान नम्बर ____, इन्द्रा कॉलोनी, मोहना",
    "present_address_en": "House No. ____, Indra Colony, Mohna",
    "state_name": "म.प्र.", "state_name_en": "M.P.",
    "police_station": "मोहना", "police_station_en": "Mohna", "district": "ग्वालियर", "district_en": "Gwalior",
    "convicting_court": "न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर",
    "convicting_court_en": "Judicial Magistrate First Class, Gwalior",
    "convicting_judge": "श्री ____", "convicting_judge_en": "Shri ____",
    "trial_case_no": "____/2011", "conviction_date": "04.08.2022",
    "sections_convicted": ["323 भा.द.वि.", "294 भा.द.वि."],
    "sections_convicted_en": ["323 IPC", "294 IPC"],
    "sentence_passed": "क्रमशः ₹1,000 तथा ₹500 अर्थदण्ड (व्यतिक्रम पर क्रमशः 20 व 10 दिवस सश्रम कारावास)",
    "sentence_passed_en": "a fine of ₹1,000 and ₹500 respectively (in default, 20 and 10 days' RI respectively)",
    "facts_narrative": (
        "अभियोजन के अनुसार कथानक संक्षेप में इस प्रकार है कि फरियादी ने अपीलार्थी एवं उसके साथियों पर शासकीय "
        "कार्य में बाधा डालने एवं मारपीट का आक्षेप लगाया तथा थाना मोहना में अपराध पंजीबद्ध कराया गया।\n\n"
        "अभियोग पत्र पर संज्ञान लेकर विचारण न्यायालय द्वारा विचारणीय प्रश्न निर्मित किये गये एवं अभियोजन के "
        "साक्षीगण परीक्षित कराये गये; तदुपरान्त अपीलार्थी को उपरोक्त धाराओं में अर्थदण्ड से दण्डित किया गया।"
    ),
    "facts_narrative_en": (
        "the complainant alleged that the appellant and his companions obstructed public duty and assaulted him, "
        "and an offence was registered at P.S. Mohna.\n\n"
        "after cognizance the trial court framed the issues, the prosecution witnesses were examined, and the "
        "appellant was thereafter convicted and fined under the said sections."
    ),
    "grounds_narrative": (
        "अभियोजन ने जप्तीनामा एवं मौका पंचनामा से सम्बन्धित कोई दस्तावेज प्रस्तुत नहीं किया, न ही घटना का कोई "
        "स्वतंत्र साक्षी प्रस्तुत किया गया।\n\n"
        "वास्तविकता यह है कि फरियादी द्वारा ही अपीलार्थी के होटल पर विवाद किया गया था, जिसकी शिकायत अपीलार्थी ने "
        "घटना दिनांक को ही थाने पर की थी, परन्तु विचारण न्यायालय ने उक्त तथ्य को विलोपित कर दिया।"
    ),
    "grounds_narrative_en": (
        "the prosecution produced no document relating to the seizure memo or spot panchnama, nor any independent "
        "witness to the incident.\n\n"
        "in truth the complainant had created a dispute at the appellant's hotel, of which the appellant himself "
        "complained at the police station on the very date, but the trial court suppressed this fact."
    ),
    "grounds": {"evidence_ignored": True, "pw_contradictions": True, "issues_not_proved": True,
                "clean_image": True, "fine_deposited": True},
    "filing_date": "__/06/2026", "advocate_name": "____",
}


def review_page_html(data: Optional[dict] = None) -> str:
    d = data if data is not None else SAMPLE
    return doc_page([render_hi(d), render_en(d)],
                    banner="दोषसिद्धि के विरुद्ध अपील (धारा 415 भा.ना.सु.सं. · 374 दं.प्र.सं.) — समीक्षा · canonical "
                           "header · खण्ड-शीर्षक · द्विभाषी · विष्णु जी की Raju nayak फाइलिंग से अक्षरशः · reviewed: false")
