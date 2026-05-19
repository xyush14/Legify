"""Bail Application template — MP / North India court Hindi format.

Models the structure of the sample document Ayush shared: a successive
bail application under Section 439 CrPC at MP High Court (Gwalior Bench)
in a dacoity-murder case.

The same renderer handles all three bail types:
  - anticipatory (Section 438 CrPC / 482 BNSS)
  - regular Magistrate (Section 437 CrPC / 479 BNSS)
  - regular Sessions/HC (Section 439 CrPC / 480 BNSS)

Hindi is the primary render (matches MP/UP/Bihar/Rajasthan court practice).
English render is provided for Delhi/Bombay HC English benches.

For the live UI, the same logic is mirrored in static/draft-bail.html
in JavaScript so the lawyer sees instant updates as they type. This
Python module is the authoritative render used for saved drafts +
PDF generation when called server-side.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional


# ----------------------------------------------------------- helpers

HINDI_ORDINAL = ["", "प्रथम", "द्वितीय", "तृतीय", "चतुर्थ", "पंचम", "षष्ठ", "सप्तम"]


def _custody_days(arrest_date: str | None) -> Optional[int]:
    """Days from arrest_date to today. arrest_date is 'DD.MM.YYYY' or 'YYYY-MM-DD'."""
    if not arrest_date:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d/%m/%Y"):
        try:
            d = datetime.strptime(arrest_date.strip(), fmt).date()
            return (date.today() - d).days
        except ValueError:
            continue
    return None


def _custody_hindi(days: int) -> str:
    """Render '762 days' as 'लगभग दो वर्ष से अधिक' style."""
    if days >= 365 * 2:
        years = days // 365
        return f"लगभग {_num_hi(years)} वर्ष से अधिक"
    if days >= 365:
        return "लगभग एक वर्ष से अधिक"
    if days >= 180:
        months = days // 30
        return f"लगभग {_num_hi(months)} माह से अधिक"
    if days >= 30:
        months = days // 30
        return f"लगभग {_num_hi(months)} माह"
    return f"{_num_hi(days)} दिन"


_HI_NUMERAL = {
    1: "एक", 2: "दो", 3: "तीन", 4: "चार", 5: "पाँच", 6: "छह",
    7: "सात", 8: "आठ", 9: "नौ", 10: "दस", 11: "ग्यारह", 12: "बारह",
}


def _num_hi(n: int) -> str:
    return _HI_NUMERAL.get(n, str(n))


def _esc(s: Optional[str]) -> str:
    """Minimal HTML escape — keeps Hindi characters intact."""
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _ph(s: Optional[str], placeholder: str = "............") -> str:
    """Return s or a dotted placeholder if empty/None."""
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{placeholder}</span>'


# ----------------------------------------------------------- main renders

def render_hi(a: dict) -> str:
    """Hindi (MP court format) bail application."""
    a = a or {}

    # ---- court header ----
    court_name = a.get("court_name") or "माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ, ग्वालियर"
    side_label = a.get("side_label") or "बंदी की ओर से"  # or 'आवेदक की ओर से' if anticipatory
    case_label = a.get("case_label") or "विविध आपराधिक प्रकरण क्रमांक"
    case_number = a.get("case_number") or ""
    case_year = a.get("case_year") or str(date.today().year)

    # ---- application type ----
    app_number = int(a.get("application_number") or 1)
    app_number_hi = HINDI_ORDINAL[app_number] if app_number < len(HINDI_ORDINAL) else f"{app_number}वाँ"
    bail_section = a.get("bail_section") or "439"
    is_successive = app_number >= 2
    is_anticipatory = bail_section == "438"

    section_titles = {
        "437": "धारा 437 दण्ड प्रकिया संहिता",
        "438": "धारा 438 दण्ड प्रकिया संहिता",
        "439": "धारा 439 दण्ड प्रकिया संहिता",
    }
    section_title = section_titles.get(bail_section, "धारा 439 दण्ड प्रकिया संहिता")

    # ---- applicant ----
    name = a.get("applicant_name") or ""
    father = a.get("applicant_father") or ""
    age = a.get("applicant_age") or ""
    occupation = a.get("applicant_occupation") or ""
    address = a.get("applicant_address") or ""

    # ---- non-applicant ----
    state_name = a.get("state_name") or "मध्य प्रदेश"
    ps_name = a.get("police_station") or ""
    district = a.get("district") or ""

    # ---- prior bail history (for successive) ----
    prior_bail = a.get("prior_bail_history") or []
    # Expected each row: {court_level: 'sc|hc|lower', case_no, disposal_date, outcome}

    # ---- crime details ----
    fir_number = a.get("fir_number") or ""
    fir_date = a.get("fir_date") or ""
    sections = a.get("sections") or []  # list of strings like '302 IPC'
    arrest_date = a.get("arrest_date") or ""
    current_jail = a.get("current_jail") or ""

    # ---- trial court ----
    trial_case_no = a.get("trial_case_no") or ""
    trial_judge = a.get("trial_judge") or ""
    trial_court = a.get("trial_court") or ""
    trial_location = a.get("trial_location") or district

    # ---- co-accused ----
    co_accused = a.get("co_accused") or []
    has_co_accused_with_bail = any(
        (c.get("outcome") or "").lower() in ("allowed", "granted", "स्वीकार")
        for c in co_accused
    )

    # ---- facts narrative ----
    facts_5_1 = a.get("facts_narrative") or ""
    cancellation_history = a.get("cancellation_history") or ""
    lower_court_history = a.get("lower_court_history") or ""

    # ---- grounds ----
    grounds = a.get("grounds") or {}
    witnesses_total = a.get("witnesses_total")
    witnesses_examined = a.get("witnesses_examined")
    custom_grounds = a.get("custom_grounds") or []  # list of free-text grounds

    # ---- signature ----
    place = a.get("place") or "ग्वालियर"
    filing_date = a.get("filing_date") or date.today().strftime("%d.%m.%Y")
    advocate_name = a.get("advocate_name") or ""

    # ============================================================
    # BUILD THE DOCUMENT
    # ============================================================
    out: list[str] = []

    out.append('<div class="bail-doc bail-doc--hi">')

    # --- HEADER ---
    out.append(f'<div class="bd-header">')
    out.append(f'<div class="bd-side">{_esc(side_label)}</div>')
    out.append(f'<h1 class="bd-court">{_esc(court_name)}</h1>')
    out.append(
        f'<div class="bd-caseno">{_esc(case_label)} '
        f'{_ph(case_number, ".........")} / {_esc(case_year)}</div>'
    )
    out.append('</div>')

    # --- PARTIES ---
    out.append('<div class="bd-parties">')
    out.append(
        f'<div class="bd-party"><span class="bd-party-label">आवेदक</span>'
        f'<span class="bd-party-dots">.............</span>'
        f'<div class="bd-party-detail">'
        f'{_ph(name, "नाम")} पुत्र श्री {_ph(father, "पिता का नाम")}, '
        f'आयु— {_ph(age, "..")} वर्ष, व्यवसाय— {_ph(occupation, "व्यवसाय")}, '
        f'निवासी— {_ph(address, "पता")}, जिला {_ph(district, "जिला")} {_esc(state_name)}'
        f'</div></div>'
    )
    out.append('<div class="bd-versus">विरूद्ध</div>')
    out.append(
        f'<div class="bd-party"><span class="bd-party-label">अनावेदक</span>'
        f'<span class="bd-party-dots">.............</span>'
        f'<div class="bd-party-detail">'
        f'{_esc(state_name)} राज्य द्वारा पुलिस थाना {_ph(ps_name, "थाना")} '
        f'जिला {_ph(district, "जिला")} {_esc(state_name)}'
        f'</div></div>'
    )
    out.append('</div>')

    # --- APPLICATION TITLE ---
    out.append(
        f'<h2 class="bd-app-title">{_esc(app_number_hi)} आवेदन पत्र '
        f'अन्तर्गत {_esc(section_title)}</h2>'
    )

    # --- PRIOR BAIL SUMMARY TABLE (always present, shows 'nil' if none) ---
    out.append(_render_prior_bail_summary_hi(prior_bail))

    # --- CRIME + TRIAL COURT TABLE ---
    out.append(_render_crime_table_hi(
        fir_number=fir_number, ps_name=ps_name, district=district,
        sections=sections, arrest_date=arrest_date,
        trial_case_no=trial_case_no, trial_judge=trial_judge,
        trial_court=trial_court, trial_location=trial_location,
    ))

    out.append('<p class="bd-prelude">आवेदक की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है:—</p>')

    # ============= NUMBERED PARAGRAPHS =============
    out.append('<ol class="bd-paras">')

    # PARA 1 — successive bail introduction
    if is_successive:
        out.append(
            f'<li><p>यहकि, आवेदक का माननीय न्यायालय के समक्ष {_esc(section_title)} '
            f'के तहत यह {_esc(app_number_hi)} आवेदन पत्र है, इसके पूर्व {_esc(section_title)} '
            f'के जो आवेदन निरस्त हुये थे उनके विवरण निम्नानुसार हैं :—</p>'
        )
        out.append(_render_prior_bail_detail_table_hi(prior_bail))
        out.append('</li>')
    else:
        out.append(
            f'<li><p>यहकि, आवेदक का माननीय न्यायालय के समक्ष {_esc(section_title)} '
            f'के तहत यह प्रथम आवेदन पत्र है।</p></li>'
        )

    # PARA 2 — no parallel applications
    out.append(
        '<li><p>यहकि, आवेदक की ओर से समान प्रकृति का अन्य कोई आवेदन पत्र '
        'माननीय न्यायालय के समक्ष अथवा माननीय उच्चतम न्यायालय के समक्ष प्रस्तुत नहीं '
        'किया गया, न ही निरस्त हुआ और न ही वर्तमान में विचाराधीन है।</p></li>'
    )

    # PARA 3 — co-accused bail table (parity)
    if co_accused:
        out.append(
            '<li><p>यहकि, प्रकरण में सहअभियुक्तगण के जमानत आवेदन का विवरण '
            'प्रार्थी की जानकारी के अनुसार निम्नानुसार है :—</p>'
        )
        out.append(_render_co_accused_table_hi(co_accused))
        out.append('</li>')

    # PARA 4 — annexures (only for successive)
    if is_successive and prior_bail:
        annex_count = 0
        annex_lines = []
        for i, p in enumerate(prior_bail):
            if not p.get("outcome"):
                continue
            annex_count += 1
            level = p.get("court_level", "")
            label = {"sc": "माननीय उच्चतम न्यायालय", "hc": "माननीय उच्च न्यायालय",
                     "lower": "अधीनस्थ न्यायालय"}.get(level, "न्यायालय")
            annex_lines.append(
                f'यहकि, {label} के आदेश दिनांक {_esc(p.get("disposal_date", "..."))} की '
                f'प्रमाणित प्रतिलिपि माननीय न्यायालय के अवलोकनार्थ प्रस्तुत की जा रही है, '
                f'जिसे एनेक्जर ए/{annex_count} से चिन्हित किया गया है।'
            )
        for line in annex_lines:
            out.append(f'<li><p>{line}</p></li>')

    # PARA 5 — FACTS
    out.append('<li class="bd-facts-block">')
    out.append('<p class="bd-section-label">प्रकरण के संक्षिप्त तथ्य :—</p>')
    out.append('<ol class="bd-subparas">')

    if facts_5_1:
        out.append(f'<li><p>यहकि, अभियोजन का मामला संक्षेप में इस प्रकार है कि '
                   f'{_esc(facts_5_1)}</p></li>')
    else:
        out.append('<li><p class="ph">[FIR की तथ्यात्मक स्थिति यहाँ लिखें — '
                   'या FIR का फोटो अपलोड करें और AI से भरवायें]</p></li>')

    # 5.2 — registration + arrest details
    if fir_number or arrest_date:
        sec_str = ", ".join(_esc(s) for s in sections) if sections else "..............."
        arrest_str = f'दिनांक {_esc(arrest_date)} को' if arrest_date else "दिनांक ......... को"
        out.append(
            f'<li><p>यहकि, उक्त रिपोर्ट पर से पुलिस थाना {_ph(ps_name, "थाना")} पर '
            f'अपराध क्रं. {_ph(fir_number, "..../....")} अन्तर्गत {sec_str} के तहत आवेदक '
            f'के विरुद्ध अपराध पंजीबद्ध किया गया जिसमें आवेदक को {arrest_str} '
            f'गिरफ्तार किया गया तथा पुलिस द्वारा अभियोग पत्र प्रस्तुत कर दिया गया।</p></li>'
        )

    # 5.3 — cancellation / re-arrest history (custom)
    if cancellation_history:
        out.append(f'<li><p>यहकि, {_esc(cancellation_history)}</p></li>')

    # 5.4 — lower court history (only if successive)
    if is_successive and lower_court_history:
        out.append(f'<li><p>यहकि, {_esc(lower_court_history)}</p></li>')
    elif is_successive:
        out.append(
            '<li><p>यहकि, आवेदक ने अधीनस्थ न्यायालय के समक्ष एक आवेदन अन्तर्गत '
            'धारा 439 दण्ड प्रकिया संहिता के तहत प्रस्तुत किया, जो अधीनस्थ न्यायालय '
            'द्वारा निरस्त किया गया।</p></li>'
        )

    out.append('</ol>')
    out.append('</li>')

    # PARA 6 — GROUNDS
    out.append('<li class="bd-grounds-block">')
    out.append('<p class="bd-section-label">आधार :—</p>')
    out.append('<ol class="bd-subparas">')

    if grounds.get("innocence", True):
        out.append(
            '<li><p>यहकि, आवेदक ने कोई अपराध नहीं किया है, आवेदक को इस प्रकरण में '
            'फरियादी पक्ष द्वारा झूठा फंसाया गया है, उसका उक्त अपराध से प्रत्यक्ष '
            'अथवा अप्रत्यक्ष रूप से कोई संबंध नहीं है।</p></li>'
        )

    cust_days = _custody_days(arrest_date)
    if grounds.get("long_custody") and cust_days:
        out.append(
            f'<li><p>यहकि, आवेदक दिनांक {_esc(arrest_date)} से न्यायिक निरोध में है '
            f'तथा आवेदक को निरोध में रहते हुये {_custody_hindi(cust_days)} '
            f'का समय हो चुका है।</p></li>'
        )

    if grounds.get("trial_delay") and witnesses_total and witnesses_examined is not None:
        out.append(
            f'<li><p>यहकि, अभियोजन की ओर से {_num_hi(int(witnesses_total))} साक्षियों '
            f'की सूची विचारण न्यायालय के समक्ष प्रस्तुत की गई है जिसमें से '
            f'सिर्फ {_num_hi(int(witnesses_examined))} साक्षियों के कथन हुये हैं, '
            f'षेष साक्षियों के कथन होने में काफी विलंब की संभावना है।</p></li>'
        )

    if grounds.get("parity") and has_co_accused_with_bail:
        out.append(
            '<li><p>यहकि, प्रकरण में आवेदक के साथ अभियुक्त बनाये गये '
            'सहअभियुक्तगण को माननीय न्यायालय द्वारा जमानत का लाभ प्रदान किया जा चुका है। '
            'समानता के सिद्धान्त (parity) के आधार पर आवेदक भी जमानत का अधिकारी है।</p></li>'
        )

    if grounds.get("local_resident", True):
        out.append(
            f'<li><p>यहकि, आवेदक जिला {_ph(district, "जिला")} '
            f'{_esc(state_name)} का स्थायी निवासी होकर आवेदक के कहीं भागकर जाने '
            f'अथवा अभियोजन साक्ष्य को प्रभावित करने की कोई संभावना नहीं है।</p></li>'
        )

    if grounds.get("medical"):
        out.append(f'<li><p>यहकि, आवेदक {_esc(grounds.get("medical"))}</p></li>')

    if grounds.get("sole_breadwinner"):
        out.append(
            '<li><p>यहकि, आवेदक अपने परिवार का एकमात्र कमाने वाला सदस्य है '
            'तथा उसके निरोध से उसके आश्रित परिवार पर गंभीर आर्थिक संकट उत्पन्न हो गया है।</p></li>'
        )

    if grounds.get("no_prior_record"):
        out.append(
            '<li><p>यहकि, आवेदक का कोई पूर्व आपराधिक इतिहास नहीं है तथा '
            'आवेदक प्रथम बार आरोपी बनाया गया है।</p></li>'
        )

    for custom in custom_grounds:
        if custom and str(custom).strip():
            out.append(f'<li><p>यहकि, {_esc(custom)}</p></li>')

    out.append('</ol>')
    out.append('</li>')

    # PARA 7 — delay in disposal
    out.append(
        '<li><p>यहकि, आवेदक के विरुद्ध लम्बित प्रकरण के अंतिम निराकरण में '
        'काफी विलंब की सम्भावना है।</p></li>'
    )

    # PARA 8 — already covered in grounds, but keep for non-grounds path
    if not grounds.get("local_resident", True):
        out.append(
            f'<li><p>यहकि, आवेदक जिला {_ph(district, "जिला")} '
            f'{_esc(state_name)} का स्थायी निवासी होकर आवेदक के कहीं भागकर जाने '
            f'अथवा अभियोजन साक्ष्य को प्रभावित करने की कोई संभावना नहीं है।</p></li>'
        )

    # PARA 9 — willingness to comply
    out.append(
        '<li><p>यहकि, आवेदक माननीय न्यायालय के आदेश के पालन में अपनी जमानत '
        'एवं मुचलका प्रस्तुत करने हेतु तैयार है तथा माननीय न्यायालय द्वारा निर्देशित '
        'समस्त शर्तों का पालन करने हेतु तैयार है।</p></li>'
    )

    out.append('</ol>')

    # --- PRAYER ---
    out.append('<div class="bd-prayer">')
    out.append('<h3>प्रार्थना</h3>')
    if is_anticipatory:
        out.append(
            '<p>अतः माननीय न्यायालय से विनम्र प्रार्थना है कि आवेदक की ओर से प्रस्तुत '
            'आवेदन पत्र स्वीकार किया जाकर आवेदक की गिरफ्तारी की स्थिति में '
            'उचित प्रतिभूति पर अग्रिम जमानत पर रिहा किये जाने हेतु आदेश पारित करने '
            'की कृपा करें।</p>'
        )
    else:
        out.append(
            '<p>अतः माननीय न्यायालय से विनम्र प्रार्थना है कि आवेदक की ओर से प्रस्तुत '
            'आवेदन पत्र स्वीकार किया जाकर आवेदक को उचित प्रतिभूति पर रिहा किये जाने '
            'हेतु आदेश पारित करने की कृपा करें।</p>'
        )
    out.append('</div>')

    # --- SIGNATURE ---
    out.append('<div class="bd-sig">')
    out.append(f'<div class="bd-sig-left">')
    out.append(f'<div>स्थान: {_ph(place, "स्थान")}</div>')
    out.append(f'<div>दिनांक: {_ph(filing_date, "...........")}</div>')
    out.append('</div>')
    out.append('<div class="bd-sig-right">')
    out.append('<div>प्रार्थी</div>')
    out.append(f'<div class="bd-sig-name">{_ph(name, "आवेदक का नाम")} (आवेदक)</div>')
    out.append('<div class="bd-sig-advocate">द्वारा अभिभाषक</div>')
    out.append(f'<div class="bd-sig-advname">({_ph(advocate_name, "अभिभाषक का नाम")})</div>')
    out.append('</div>')
    out.append('</div>')

    out.append('</div>')  # /.bail-doc

    return "\n".join(out)


def render_en(a: dict) -> str:
    """English bail application — for HC English benches.

    Minimal version for v1. Follows the same structure as Hindi but in
    formal court English. Will be polished when we target Delhi/Bombay HC.
    """
    a = a or {}
    name = a.get("applicant_name") or "(applicant)"
    father = a.get("applicant_father") or "(father)"
    age = a.get("applicant_age") or "..."
    occupation = a.get("applicant_occupation") or "(occupation)"
    address = a.get("applicant_address") or "(address)"
    district = a.get("district") or "(district)"
    state_name = a.get("state_name") or "Madhya Pradesh"
    ps_name = a.get("police_station") or "(police station)"
    court_name = a.get("court_name") or "Hon'ble High Court of Madhya Pradesh, Gwalior Bench"
    case_no = a.get("case_number") or "...."
    case_year = a.get("case_year") or str(date.today().year)
    bail_section = a.get("bail_section") or "439"
    app_num = int(a.get("application_number") or 1)
    app_ord = ["", "FIRST", "SECOND", "THIRD", "FOURTH"][min(app_num, 4)]

    fir_number = a.get("fir_number") or "...."
    arrest_date = a.get("arrest_date") or "...."
    facts = a.get("facts_narrative") or "(brief facts of the case to be inserted here)"
    custody_days = _custody_days(arrest_date)

    out = ['<div class="bail-doc bail-doc--en">']
    out.append(f'<div class="bd-header">')
    out.append(f'<h1 class="bd-court">IN THE {_esc(court_name).upper()}</h1>')
    out.append(f'<div class="bd-caseno">MCRC No. {_esc(case_no)} of {_esc(case_year)}</div>')
    out.append('</div>')

    out.append('<div class="bd-parties">')
    out.append(
        f'<div class="bd-party">{_esc(name)}, S/o {_esc(father)}, '
        f'aged about {_esc(age)} years, occupation {_esc(occupation)}, '
        f'R/o {_esc(address)}, District {_esc(district)}, {_esc(state_name)}'
        f' .....APPLICANT</div>'
    )
    out.append('<div class="bd-versus">Versus</div>')
    out.append(
        f'<div class="bd-party">State of {_esc(state_name)} through '
        f'Police Station {_esc(ps_name)}, District {_esc(district)} '
        f' .....RESPONDENT</div>'
    )
    out.append('</div>')

    out.append(
        f'<h2 class="bd-app-title">{app_ord} APPLICATION FOR BAIL UNDER '
        f'SECTION {bail_section} OF THE CODE OF CRIMINAL PROCEDURE, 1973</h2>'
    )

    out.append('<p>The above-named applicant most respectfully states as under:</p>')

    out.append('<ol class="bd-paras">')
    out.append(f'<li>That this is the {app_ord.lower()} application for bail under '
               f'Section {bail_section} CrPC filed by the applicant.</li>')
    out.append(
        '<li>That no similar application has been filed by the applicant before '
        'this Hon\'ble Court or before the Hon\'ble Supreme Court of India, '
        'nor any such application is currently pending.</li>'
    )
    out.append(f'<li>That the brief facts of the case are: {_esc(facts)}</li>')

    if custody_days:
        out.append(
            f'<li>That the applicant has been in judicial custody since '
            f'{_esc(arrest_date)} — a period of approximately '
            f'{custody_days} days — and his continued incarceration is causing '
            f'serious prejudice to him and his family.</li>'
        )

    out.append(
        '<li>That the applicant is a permanent resident of the abovementioned '
        'address and there is no apprehension of flight or of tampering with '
        'prosecution evidence.</li>'
    )
    out.append(
        '<li>That the applicant undertakes to abide by all conditions that '
        'may be imposed by this Hon\'ble Court and to furnish bail bond and '
        'surety as directed.</li>'
    )
    out.append('</ol>')

    out.append(
        '<div class="bd-prayer"><h3>PRAYER</h3>'
        '<p>It is therefore most respectfully prayed that this Hon\'ble Court may be pleased '
        'to allow the present application and direct that the applicant be released on bail '
        'on such terms and conditions as this Hon\'ble Court may deem fit and proper, '
        'in the interest of justice.</p></div>'
    )

    out.append('<div class="bd-sig">')
    out.append(f'<div>Place: {_esc(a.get("place") or "Gwalior")}</div>')
    out.append(f'<div>Date: {_esc(a.get("filing_date") or date.today().strftime("%d.%m.%Y"))}</div>')
    out.append(f'<div class="bd-sig-right">Through Counsel<br>'
               f'<b>{_esc(a.get("advocate_name") or "(Advocate)")}</b></div>')
    out.append('</div>')

    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- helper tables

def _render_prior_bail_summary_hi(prior_bail: list) -> str:
    """The 3-row 'क्या जमानत आवेदन पत्र विचाराधीन है या निराकृत है' table."""
    by_level = {p.get("court_level"): p for p in (prior_bail or [])}
    sc = by_level.get("sc") or {}
    hc = by_level.get("hc") or {}
    lower = by_level.get("lower") or {}

    def cell(p, key, default="निल"):
        v = p.get(key) if p else None
        return _esc(v) if v else default

    out = ['<table class="bd-table bd-prior-summary">']
    out.append(
        '<tr><th rowspan="2">क्या जमानत आवेदन पत्र न्यायालय के समक्ष विचाराधीन है '
        'या निराकृत है। <br><small>(यदि हाँ तो उसका विवरण)</small></th>'
        '<th colspan="3">जमानत आवेदन पत्र का विवरण</th></tr>'
        '<tr><th>नम्बर</th><th>आदेश दिनांक</th><th>परिणाम</th></tr>'
    )
    out.append(
        f'<tr><td>माननीय उच्चतम न्यायालय</td>'
        f'<td>{cell(sc, "case_no")}</td>'
        f'<td>{cell(sc, "disposal_date")}</td>'
        f'<td>{cell(sc, "outcome")}</td></tr>'
    )
    out.append(
        f'<tr><td>माननीय उच्च न्यायालय</td>'
        f'<td>{cell(hc, "case_no")}</td>'
        f'<td>{cell(hc, "disposal_date")}</td>'
        f'<td>{cell(hc, "outcome")}</td></tr>'
    )
    out.append(
        f'<tr><td>माननीय अधीनस्थ न्यायालय</td>'
        f'<td>{cell(lower, "case_no")}</td>'
        f'<td>{cell(lower, "disposal_date")}</td>'
        f'<td>{cell(lower, "outcome")}</td></tr>'
    )
    out.append('</table>')
    return "\n".join(out)


def _render_crime_table_hi(*, fir_number, ps_name, district, sections,
                            arrest_date, trial_case_no, trial_judge,
                            trial_court, trial_location) -> str:
    sec_str = ", ".join(sections) if sections else "..............."
    out = ['<table class="bd-table bd-crime-table">']
    out.append(
        '<tr><th>अपराध संबंधी विवरण</th><th>विचाराधीन आदेश का विवरण</th></tr>'
    )
    crime_cell = (
        f'अपराध क्रमांक {_ph(fir_number, "..../....")}<br>'
        f'पुलिस थाना— {_ph(ps_name, "थाना")} <br>'
        f'जिला {_ph(district, "जिला")}<br>'
        f'अन्तर्गत धारा {_esc(sec_str)}<br>'
        f'गिरफ्तारी दिनांक — {_ph(arrest_date, "...........")}'
    )
    trial_cell = (
        f'विशेष सत्रवाद कं. {_ph(trial_case_no, "..../....")}<br>'
        f'न्यायाधीश का नाम— श्री {_ph(trial_judge, "न्यायाधीश")}<br>'
        f'न्यायालय का नाम— {_ph(trial_court, "न्यायालय")}<br>'
        f'स्थान— {_ph(trial_location, "स्थान")}'
    )
    out.append(f'<tr><td>{crime_cell}</td><td>{trial_cell}</td></tr>')
    out.append('</table>')
    return "\n".join(out)


def _render_prior_bail_detail_table_hi(prior_bail: list) -> str:
    out = ['<table class="bd-table bd-prior-detail">']
    out.append(
        '<tr><th>क्र.सं.</th><th>केस नं./दिनांक</th>'
        '<th>पक्षकार</th><th>अधीनस्थ न्यायालय केस नं.</th>'
        '<th>पुलिस थाना</th><th>स्थिति</th>'
        '<th>आदेश दिनांक</th><th>परिणाम</th>'
        '<th>माननीय न्यायाधीश</th></tr>'
    )
    for i, p in enumerate(prior_bail or [], 1):
        out.append(
            f'<tr><td>{i}</td>'
            f'<td>{_esc(p.get("case_no", ""))}<br>'
            f'<small>{_esc(p.get("filing_date", ""))}</small></td>'
            f'<td>{_esc(p.get("parties", ""))}</td>'
            f'<td>{_esc(p.get("lower_case_no", ""))}</td>'
            f'<td>{_esc(p.get("police_station", ""))}</td>'
            f'<td>{_esc(p.get("status", "Disposed"))}</td>'
            f'<td>{_esc(p.get("disposal_date", ""))}</td>'
            f'<td>{_esc(p.get("outcome", ""))}</td>'
            f'<td>{_esc(p.get("justice", ""))}</td></tr>'
        )
    if not prior_bail:
        out.append('<tr><td colspan="9" style="text-align:center;color:#888">'
                   '(कोई पूर्व आवेदन नहीं — प्रथम आवेदन)</td></tr>')
    out.append('</table>')
    return "\n".join(out)


def _render_co_accused_table_hi(co_accused: list) -> str:
    out = ['<table class="bd-table bd-coaccused">']
    out.append(
        '<tr><th>क्र.सं.</th><th>केस नं./दिनांक</th><th>पक्षकार</th>'
        '<th>अधीनस्थ न्यायालय केस नं.</th><th>पुलिस थाना</th>'
        '<th>स्थिति</th><th>क्रम</th><th>निराकरण दिनांक</th>'
        '<th>परिणाम</th><th>माननीय न्यायाधीश</th></tr>'
    )
    for i, p in enumerate(co_accused or [], 1):
        out.append(
            f'<tr><td>{i}</td>'
            f'<td>{_esc(p.get("case_no", ""))}<br>'
            f'<small>{_esc(p.get("filing_date", ""))}</small></td>'
            f'<td>{_esc(p.get("parties", ""))}</td>'
            f'<td>{_esc(p.get("lower_case_no", ""))}</td>'
            f'<td>{_esc(p.get("police_station", ""))}</td>'
            f'<td>{_esc(p.get("status", "Disposed"))}</td>'
            f'<td>{_esc(p.get("bail_number", ""))}</td>'
            f'<td>{_esc(p.get("disposal_date", ""))}</td>'
            f'<td>{_esc(p.get("outcome", ""))}</td>'
            f'<td>{_esc(p.get("justice", ""))}</td></tr>'
        )
    out.append('</table>')
    return "\n".join(out)
