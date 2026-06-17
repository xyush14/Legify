"""Discharge Application template — Section 239 CrPC / Section 262 BNSS.

Reproduces, verbatim, the structure and language of Vishnu ji's filed §239
discharge (benchmark: "239__ 498 - Arvind sharma" — a 498A/Dowry-Prohibition
matter). The fixed legal language is hard-coded (reviewed); only the client
variables and the case-specific facts narrative are filled in. No LLM writes
any text — OCR/voice only READ the lawyer's inputs.

Same render contract + CSS classes as headnote/drafter/templates/
bail_application.py, so it inherits the identical court format, spacing and
alignment used by the /draft/bail reference.

This module is the authoritative server-side render (saved drafts + PDF). The
live UI mirrors the same paragraph logic in JS for instant preview.
"""
from __future__ import annotations

from datetime import date
from typing import Optional


# ----------------------------------------------------------- helpers

def _esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], placeholder: str = "............") -> str:
    """Return the value, or a dotted placeholder if empty — never blank,
    never invented (matches the filed-form look)."""
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{placeholder}</span>'


def _sections_str(sections) -> str:
    """sections may be a list ['498ए भा.द.वि.', '3/4 दहेज प्रतिषेध अधिनियम'] or a string."""
    if isinstance(sections, (list, tuple)):
        return " एवं ".join(_esc(s) for s in sections if str(s).strip()) or "..............."
    return _esc(sections) if sections and str(sections).strip() else "..............."


# ----------------------------------------------------------- main render (Hindi)

def render_hi(a: dict) -> str:
    a = a or {}

    # ---- court header ----
    court_name = a.get("court_name") or "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर"
    case_number = a.get("case_number") or ""
    case_type = a.get("case_type") or "आर.सी.टी."          # RCT / Regular Criminal Trial
    case_year = a.get("case_year") or ""

    # ---- parties ----
    state_name = a.get("state_name") or "म.प्र."
    accused_names = a.get("accused_names") or ""           # e.g. 'रामेश्वर दयाल आदि'
    is_plural = bool(a.get("is_plural", True))             # प्रार्थीगण vs प्रार्थी
    applicant_word = "प्रार्थीगण" if is_plural else "प्रार्थी"
    accused_word = "अभियुक्तगण" if is_plural else "अभियुक्त"

    # ---- the offence / FIR ----
    section = a.get("discharge_section") or "239"          # 239 CrPC / 262 BNSS
    police_station = a.get("police_station") or ""
    crime_number = a.get("crime_number") or ""
    sections = a.get("sections") or []                     # offence sections (498A etc.)
    offence_allegation = a.get("offence_allegation") or (
        f"{applicant_word} द्वारा फरियादिया से दहेज की मांग करते हुये शारीरिक व "
        f"मानसिक रूप से प्रताड़ित किया जाता है"
    )

    # ---- case-specific defense facts (lawyer-entered / OCR-seeded) ----
    facts_narrative = a.get("facts_narrative") or ""

    # ---- grounds (reviewed legal paragraphs — toggles, default ON) ----
    g = a.get("grounds") or {}
    custom_grounds = a.get("custom_grounds") or []

    # ---- signature ----
    place = a.get("place") or ""
    filing_date = a.get("filing_date") or date.today().strftime("%d/%m/%Y")
    advocate_name = a.get("advocate_name") or ""

    sec_str = _sections_str(sections)
    out: list[str] = ['<div class="bail-doc bail-doc--hi">']

    # --- HEADER ---
    out.append('<div class="bd-header">')
    out.append(f'<h1 class="bd-court">{_esc(court_name)}</h1>')
    caseno = f'{_ph(case_number, ".........")}'
    if case_year:
        caseno += f'/{_esc(case_year)}'
    out.append(f'<div class="bd-caseno">प्रकरण क्रमांक— {caseno} {_esc(case_type)}</div>')
    out.append('</div>')

    # --- PARTIES ---
    out.append('<div class="bd-parties">')
    out.append(
        f'<div class="bd-party"><div class="bd-party-detail">'
        f'{_esc(state_name)} राज्य</div>'
        f'<span class="bd-party-dots">............</span>'
        f'<span class="bd-party-label">अभियोगी</span></div>'
    )
    out.append('<div class="bd-versus">बनाम</div>')
    out.append(
        f'<div class="bd-party"><div class="bd-party-detail">'
        f'{_ph(accused_names, "अभियुक्तगण के नाम")}</div>'
        f'<span class="bd-party-dots">............</span>'
        f'<span class="bd-party-label">{accused_word}</span></div>'
    )
    out.append('</div>')

    # --- APPLICATION TITLE ---
    out.append(
        f'<h2 class="bd-app-title">आवेदन पत्र अन्तर्गत धारा {_esc(section)} '
        f'द.प्र.सं.</h2>'
    )

    out.append('<p class="bd-prelude">माननीय न्यायालय,</p>')
    out.append(
        f'<p class="bd-prelude">{applicant_word}/{accused_word} की ओर से आवेदन पत्र '
        f'निम्न प्रकार प्रस्तुत है :—</p>'
    )

    # ============= NUMBERED PARAGRAPHS =============
    out.append('<ol class="bd-paras">')

    # PARA 1 — registration + chargesheet + stage (fixed phrasing, client vars)
    out.append(
        f'<li><p>यह कि, {applicant_word} के विरुद्ध {_ph(police_station, "थाना")} '
        f'द्वारा अपराध क्रमांक— {_ph(crime_number, "..../....")} अन्तर्गत धारा {sec_str} '
        f'के तहत फरियादी की रिपोर्ट पर से दर्ज किया गया है, जिसमें अनुसंधान पूर्ण होने '
        f'के उपरान्त अभियोग पत्र माननीय न्यायालय के समक्ष प्रस्तुत किया गया है। '
        f'उक्त प्रकरण आज दिनांक को आरोप तर्क हेतु नियत है।</p></li>'
    )

    # PARA 2 — the complainant's allegation (fixed framing, editable)
    out.append(
        f'<li><p>यह कि, उपरोक्त प्रकरण में फरियादी द्वारा अपनी रिपोर्ट में '
        f'{applicant_word} के विरुद्ध आरोप लगाया है कि {_esc(offence_allegation)}।</p></li>'
    )

    # PARA 3+ — the defense facts narrative (case-specific; lawyer/OCR)
    if facts_narrative.strip():
        for chunk in [c.strip() for c in facts_narrative.split("\n\n") if c.strip()]:
            out.append(f'<li><p>यह कि, {_esc(chunk)}</p></li>')
    else:
        out.append(
            '<li><p class="ph">[प्रकरण के वास्तविक तथ्य यहाँ लिखें — '
            'आरोपी का फरियादिया से संबंध, पृथक निवास, सहअभियुक्त, झूठे फँसाये जाने का '
            'कारण आदि — या अभियोग पत्र / FIR अपलोड कर AI से भरवायें]</p></li>'
        )

    # ---- reviewed legal grounds (default ON; lawyer can toggle) ----
    if g.get("no_dowry_demand", True):
        out.append(
            f'<li><p>यह कि, {applicant_word} द्वारा फरियादिया से कभी भी दहेज की मांग '
            f'को लेकर शारीरिक एवं मानसिक प्रताड़ना नहीं की गई है। फरियादिया द्वारा '
            f'द्वेषपूर्ण भाव से {applicant_word} को उक्त प्रकरण में झूठा फँसाया गया है।</p></li>'
        )

    if g.get("family_member_principle", True):
        out.append(
            '<li><p>यह कि, माननीय सर्वोच्च न्यायालय एवं माननीय उच्च न्यायालय द्वारा '
            'पारित न्यायदृष्टान्तों में स्पष्ट रूप से अभिनिर्धारित किया गया है कि केवल '
            'पारिवारिक सदस्य होने के आधार पर असत्य रूप से आरोपी बनाये गये पारिवारिक '
            'सदस्यों के विरुद्ध धारा 498ए भा.द.वि. एवं घरेलू हिंसा का अपराध निर्मित '
            'नहीं होता है।</p></li>'
        )

    if g.get("no_prima_facie", True):
        out.append(
            f'<li><p>यह कि, फरियादिया द्वारा {applicant_word} के विरुद्ध लगाये गये समस्त '
            f'आक्षेप मिथ्या व बनावटी हैं। {applicant_word} के विरुद्ध प्रथम दृष्टया '
            f'अभिलेख पर ऐसी कोई साक्ष्य विद्यमान नहीं है जिससे यह प्रमाणित होता हो कि '
            f'फरियादिया द्वारा लगाये गये आरोप सत्य हैं।</p></li>'
        )

    for custom in custom_grounds:
        if custom and str(custom).strip():
            out.append(f'<li><p>यह कि, {_esc(custom)}</p></li>')

    # closing two paras — always present
    out.append(
        f'<li><p>यह कि, उपरोक्त स्थिति में {applicant_word} को उक्त प्रकरण से '
        f'उन्मुक्त किया जाना न्यायोचित एवं न्यायसंगत है।</p></li>'
    )
    out.append('<li><p>यह कि, अन्य तर्क वक्त बहस निवेदित किये जावेंगे।</p></li>')
    out.append('</ol>')

    # --- PRAYER ---
    out.append('<div class="bd-prayer">')
    out.append('<h3>प्रार्थना</h3>')
    out.append(
        f'<p>अतः माननीय न्यायालय से सादर निवेदन है कि {applicant_word} का यह आवेदन पत्र '
        f'स्वीकार कर {applicant_word} को उक्त प्रकरण में वर्णित धारा {sec_str} से '
        f'उन्मोचित (discharge) किये जाने की कृपा करें।</p>'
    )
    out.append('</div>')

    # --- SIGNATURE ---
    out.append('<div class="bd-sig">')
    out.append('<div class="bd-sig-left">')
    out.append(f'<div>स्थान: {_ph(place, "स्थान")}</div>')
    out.append(f'<div>दिनांक: {_ph(filing_date, "...........")}</div>')
    out.append('</div>')
    out.append('<div class="bd-sig-right">')
    out.append(f'<div>{applicant_word}</div>')
    out.append(f'<div class="bd-sig-name">—{accused_word}</div>')
    out.append('<div class="bd-sig-advocate">द्वारा अभिभाषक</div>')
    out.append(f'<div class="bd-sig-advname">({_ph(advocate_name, "अभिभाषक का नाम")} — एडवोकेट)</div>')
    out.append('</div>')
    out.append('</div>')

    out.append('</div>')  # /.bail-doc
    return "\n".join(out)


def render_en(a: dict) -> str:
    """Full English discharge — mirrors render_hi paragraph-for-paragraph
    (for HC English benches; MP district courts file the Hindi render)."""
    a = a or {}
    court_name = a.get("court_name") or "(name of the Court)"
    case_number = a.get("case_number") or ""
    case_type = a.get("case_type") or "R.C.T."
    state_name = a.get("state_name") or "M.P."
    accused_names = a.get("accused_names") or ""
    section = a.get("discharge_section") or "239"
    police_station = a.get("police_station") or ""
    crime_number = a.get("crime_number") or ""
    sections = a.get("sections") or []
    offence_allegation = a.get("offence_allegation") or (
        "the applicants subjected the complainant to physical and mental cruelty "
        "in connection with a demand for dowry")
    facts_narrative = a.get("facts_narrative") or ""
    g = a.get("grounds") or {}
    custom_grounds = a.get("custom_grounds") or []
    place = a.get("place") or ""
    filing_date = a.get("filing_date") or date.today().strftime("%d/%m/%Y")
    advocate_name = a.get("advocate_name") or ""
    sec_str = _sections_str(sections)

    out = ['<div class="bail-doc bail-doc--en">']
    out.append('<div class="bd-header">')
    out.append(f'<h1 class="bd-court">{_esc(court_name)}</h1>')
    out.append(f'<div class="bd-caseno">Criminal Case No. {_ph(case_number, ".........")} '
               f'{_esc(case_type)}</div>')
    out.append('</div>')

    out.append('<div class="bd-parties">')
    out.append(f'<div class="bd-party"><div class="bd-party-detail">State of {_esc(state_name)}</div>'
               f'<span class="bd-party-dots">............</span>'
               f'<span class="bd-party-label">Prosecution</span></div>')
    out.append('<div class="bd-versus">Versus</div>')
    out.append(f'<div class="bd-party"><div class="bd-party-detail">{_ph(accused_names, "names of the accused")}</div>'
               f'<span class="bd-party-dots">............</span>'
               f'<span class="bd-party-label">Accused</span></div>')
    out.append('</div>')

    out.append(f'<h2 class="bd-app-title">APPLICATION FOR DISCHARGE UNDER SECTION {_esc(section)} '
               f'OF THE CODE OF CRIMINAL PROCEDURE, 1973</h2>')
    out.append('<p class="bd-prelude">May it please the Court,</p>')
    out.append('<p class="bd-prelude">The applicants/accused most respectfully submit as under:—</p>')
    out.append('<ol class="bd-paras">')

    out.append(f'<li><p>That the applicants have been charge-sheeted by Police Station '
               f'{_ph(police_station, "police station")} in Crime No. {_ph(crime_number, "..../....")} '
               f'under {sec_str} on a report of the complainant; investigation being complete, the '
               f'charge-sheet stands filed before this Hon\'ble Court and the matter is fixed today for '
               f'arguments on charge.</p></li>')
    out.append(f'<li><p>That in the said report the complainant has alleged against the applicants that '
               f'{_esc(offence_allegation)}.</p></li>')

    if facts_narrative.strip():
        for chunk in [c.strip() for c in facts_narrative.split("\n\n") if c.strip()]:
            out.append(f'<li><p>That in truth, {_esc(chunk)}</p></li>')
    else:
        out.append('<li><p class="ph">[State the true facts of the defence here — the applicants’ '
                   'relationship to the complainant, separate residence, co-accused, and the reason for '
                   'the false implication — or upload the charge-sheet / FIR and let the AI read it.]</p></li>')

    if g.get("no_dowry_demand", True):
        out.append('<li><p>That the applicants never subjected the complainant to any physical or mental '
                   'cruelty over a demand for dowry; the complainant has, out of malice, falsely implicated '
                   'the applicants in the present case.</p></li>')
    if g.get("family_member_principle", True):
        out.append('<li><p>That the Hon’ble Supreme Court and the Hon’ble High Court have '
                   'authoritatively held that merely being a family member does not make out an offence under '
                   'Section 498A IPC or under the Protection of Women from Domestic Violence Act against '
                   'relatives arrayed as accused without specific allegations.</p></li>')
    if g.get("no_prima_facie", True):
        out.append('<li><p>That all the allegations levelled by the complainant against the applicants are '
                   'false and concocted, and there is no prima facie material on record to establish that '
                   'the said allegations are true.</p></li>')
    for c in custom_grounds:
        if c and str(c).strip():
            out.append(f'<li><p>That {_esc(c)}</p></li>')

    out.append('<li><p>That in the facts and circumstances above, it is just and proper that the applicants '
               'be discharged from the present case.</p></li>')
    out.append('<li><p>That further arguments shall be advanced at the time of hearing.</p></li>')
    out.append('</ol>')

    out.append('<div class="bd-prayer"><h3>PRAYER</h3>')
    out.append(f'<p>It is therefore most respectfully prayed that this Hon’ble Court may be pleased to '
               f'allow the present application and discharge the applicants from the offences under {sec_str}, '
               f'in the interest of justice.</p></div>')

    out.append('<div class="bd-sig"><div class="bd-sig-left">')
    out.append(f'<div>Place: {_ph(place, "place")}</div><div>Date: {_ph(filing_date, "..........")}</div></div>')
    out.append('<div class="bd-sig-right"><div>Applicants</div>'
               '<div class="bd-sig-name">— Accused</div>'
               '<div class="bd-sig-advocate">Through Counsel</div>'
               f'<div class="bd-sig-advname">({_ph(advocate_name, "advocate")} — Advocate)</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- benchmark sample
# The real filed matter ("239__ 498 - Arvind sharma"), reproduced verbatim.
# Fixed legal paragraphs live in render_hi; only these variables + the facts
# narrative change per client. Used by the /draft/discharge review page.

SAMPLE = {
    "court_name": "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर",
    "case_number": "1878/2021", "case_type": "आर.सी.टी.",
    "state_name": "म.प्र.", "accused_names": "रामेश्वर दयाल आदि", "is_plural": True,
    "discharge_section": "239",
    "police_station": "महिला थाना पड़ाव, ग्वालियर", "crime_number": "240/2021",
    "sections": ["498ए भा.द.वि.", "3/4 दहेज प्रतिषेध अधिनियम"],
    "facts_narrative": (
        "वास्तविकता यह है कि प्रार्थीगण फरियादिया के जेठ एवं जेठानी हैं तथा फरियादिया के "
        "विवाह के पूर्व से ही स्वयं अपने बच्चों के साथ अपने माता-पिता एवं सहअभियुक्त अंकित, "
        "विनोद, भारती से पृथक निवास करते हैं। प्रार्थीगण द्वारा फरियादिया के साथ विवाह के पूर्व "
        "अथवा पश्चात् आज दिनांक तक किसी भी प्रकार की कोई दहेज की मांग नहीं की गई है और न ही "
        "उसके साथ किसी भी प्रकार की प्रताड़ना की गई है। फरियादिया द्वारा केवल द्वेषभाव एवं "
        "सहअभियुक्त अंकित के बड़े भाई एवं भाभी होने के कारण प्रार्थीगण को उक्त प्रकरण में "
        "मिथ्या रूप से आलिप्त किया गया है।"
        "\n\n"
        "प्रार्थीगण के पिता द्वारा प्रार्थीगण के विवाह के पश्चात् ही प्रार्थीगण को अपने पैतृक भवन "
        "में पृथक भाग में रहने हेतु दे दिया गया था एवं प्रार्थीगण अपने बच्चों सहित पृथक रूप से "
        "निवास कर रहे हैं। प्रकरण की फरियादिया तथा उसके पति अंकित के मध्य आपसी मतभेद के कारण "
        "आये दिन विवाद की स्थिति रहती थी। इस सम्बन्ध में प्रार्थीगण द्वारा प्रकरण दर्ज होने से "
        "पूर्व ही पुलिस अधीक्षक, ग्वालियर को लिखित आवेदन प्रस्तुत कर निष्पक्ष जांच का निवेदन "
        "किया गया था, किन्तु पुलिस द्वारा बिना उचित अनुसंधान के मिथ्या अपराध पंजीबद्ध कर दिया गया।"
        "\n\n"
        "प्रार्थी क्रमांक-01 पेशे से अधिवक्ता है तथा नियमित रूप से माननीय उच्च न्यायालय खण्डपीठ "
        "ग्वालियर में विधि व्यवसाय करता है। प्रार्थी की समाज में प्रतिष्ठा है, जिसे धूमिल करने के "
        "उद्देश्य से फरियादिया द्वारा मिथ्या रूप से उक्त प्रकरण में आलिप्त किया गया है।"
    ),
    "filing_date": "22/03/2024", "advocate_name": "अरविन्द शर्मा",
}


# ----------------------------------------------------------- review page
# A self-contained, read-only page that renders the discharge in the EXACT
# court-paper format used by /draft/bail (same .doc-page + .bail-doc CSS), so
# Vishnu ji can review the drafting on the live site before the full form/OCR
# page is built.

_REVIEW_CSS = """
  *{box-sizing:border-box}
  body{margin:0;background:#e8e6df;font-family:'Tiro Devanagari Hindi','Noto Serif Devanagari',serif;color:#1a1814}
  .review-banner{background:#1a1814;color:#faf8f3;padding:12px 18px;font-size:13px;line-height:1.5;text-align:center}
  .review-banner b{color:#e9c46a}
  .review-banner small{display:block;color:#cfc9bd;font-size:11.5px;margin-top:3px}
  .doc-pane{padding:30px 16px 70px}
  .doc-page{background:#fff;max-width:760px;margin:0 auto;padding:60px 70px 80px;min-height:85vh;
    box-shadow:0 1px 3px rgba(0,0,0,.04),0 8px 24px rgba(0,0,0,.06);border-radius:4px;
    font-family:'Times New Roman','Tiro Devanagari Hindi','Noto Serif Devanagari',Times,serif;
    line-height:1.7;color:#000;font-size:14.5px}
  .bail-doc{font-size:14.5px}
  .bail-doc .bd-header{text-align:center;margin-bottom:20px}
  .bail-doc .bd-court{font-size:16.5px;font-weight:700;margin:4px 0 12px;letter-spacing:.01em}
  .bail-doc .bd-caseno{font-size:14px;margin-bottom:6px}
  .bail-doc .bd-parties{margin:26px 0 14px}
  .bail-doc .bd-party{display:grid;grid-template-columns:1fr auto auto;gap:6px;margin-bottom:10px;align-items:end}
  .bail-doc .bd-party-label{font-weight:500;white-space:nowrap}
  .bail-doc .bd-party-dots{color:#555;overflow:hidden;white-space:nowrap}
  .bail-doc .bd-party-detail{text-align:left}
  .bail-doc .bd-versus{text-align:center;font-weight:700;margin:10px 0;font-size:15px}
  .bail-doc .bd-app-title{text-align:center;text-decoration:underline;font-size:16px;font-weight:700;margin:24px 0 18px}
  .bail-doc .bd-prelude{margin:16px 0 10px;text-align:justify}
  .bail-doc .bd-paras{padding-left:0;counter-reset:para;list-style:none}
  .bail-doc .bd-paras>li{counter-increment:para;position:relative;padding-left:36px;margin-bottom:14px;text-align:justify;line-height:1.75}
  .bail-doc .bd-paras>li::before{content:counter(para) ".";position:absolute;left:0;font-weight:700;width:30px;text-align:right;padding-right:6px}
  .bail-doc .bd-prayer{margin:24px 0}
  .bail-doc .bd-prayer h3{text-align:center;text-decoration:underline;margin:10px 0 12px;font-size:16px;font-weight:700}
  .bail-doc .bd-prayer p{text-align:justify;padding-left:36px;text-indent:-10px;line-height:1.75}
  .bail-doc .bd-sig{display:flex;justify-content:space-between;margin-top:38px;font-size:14px}
  .bail-doc .bd-sig-right{text-align:center}
  .bail-doc .bd-sig-name{margin-top:8px}
  .bail-doc .bd-sig-advocate{margin-top:14px}
  .bail-doc .bd-sig-advname{font-weight:600;margin-top:18px}
  .bail-doc .ph{color:#b4afa3;font-style:italic}
"""

_REVIEW_PAGE = (
    '<!doctype html><html lang="hi"><head><meta charset="utf-8">'
    '<meta name="viewport" content="width=device-width, initial-scale=1">'
    '<title>उन्मोचन आवेदन (धारा 239) — समीक्षा</title>'
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link href="https://fonts.googleapis.com/css2?family=Tiro+Devanagari+Hindi&family=Noto+Serif+Devanagari:wght@400;600;700&display=swap" rel="stylesheet">'
    '<style>' + _REVIEW_CSS + '</style></head><body>'
    '<div class="review-banner"><b>समीक्षा — धारा 239 द.प्र.सं. / 498ए उन्मोचन आवेदन</b>'
    '<small>नमूना: अरविन्द शर्मा प्रकरण · निश्चित विधिक भाषा दाखिल प्रति से अक्षरशः · '
    'केवल चर (नाम, धारा, दिनांक आदि) परिवर्तनीय · कोई AI-लिखित पाठ नहीं</small></div>'
    '<div class="doc-pane"><div class="doc-page"><!--DOC--></div></div>'
    '</body></html>'
)


def review_page_html(data: Optional[dict] = None) -> str:
    """Full standalone HTML review page (read-only) for advocate sign-off."""
    return _REVIEW_PAGE.replace("<!--DOC-->", render_hi(data if data is not None else SAMPLE))
