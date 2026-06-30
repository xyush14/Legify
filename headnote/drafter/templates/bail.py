"""Bail — unified engine for ALL court types, on the canonical header, bilingual.

One renderer, parameterised by court (magistrate|sessions|hc) × bail_type
(regular|anticipatory). Every skeleton, table and boilerplate line is reproduced
VERBATIM from Vishnu ji's filings — Magistrate §480 "Anshul Kanjar", Sessions §483
"439 _ 34(2)", HC §482 "Sanjeev/Narendra chouhan" (the full HC set: index + crime/
order table + prior-bail table + co-accused table + cross-case + section labels +
separate शपथ पत्र), anticipatory §482 "Krishna ojha". No LLM writes any text.

Mirrored structure (from his HC bail):
  • crime / impugned-order table  →  अपराध का विवरण | विवादित आदेश का विवरण
  • prior-bail-history table       →  जमानत आवेदन पत्र का विवरण (SC/HC/subordinate)
  • co-accused table + cross-case  (HC)
  • SECTION LABELS in the body     →  प्रकरण के संक्षिप्त तथ्य ः—  /  जमानत के आधार
  • the affidavit is a SEPARATE शपथ पत्र document in HIS format (render_affidavit_hi),
    NOT an invented disclosure block.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from headnote.drafter.templates._doc_header import render_header, doc_page, compose_court_name, render_index
from headnote.drafter.templates import _fields as F

HINDI_ORDINAL = ["", "प्रथम", "द्वितीय", "तृतीय", "चतुर्थ", "पंचम", "षष्ठ", "सप्तम"]
EN_ORDINAL = ["", "FIRST", "SECOND", "THIRD", "FOURTH", "FIFTH", "SIXTH", "SEVENTH"]

# Leading bail judgments — CITE-AT-HEARING only (Arnesh/Antil ALSO appear verbatim in
# the ≤7yr ground, from his filing). Verify before any oral use.
CITE_AT_HEARING = [
    {"case": "Satender Kumar Antil v. CBI (2022) 10 SCC 51", "point": "bail categories A–D; bail the rule", "verified": False},
    {"case": "Arnesh Kumar v. State of Bihar (2014) 8 SCC 273", "point": "arrest not automatic ≤7yr", "verified": False},
    {"case": "Sanjay Chandra v. CBI (2012) 1 SCC 40", "point": "bail not punitive; Art. 21", "verified": False},
    {"case": "Prasanta Kumar Sarkar v. Ashis Chatterjee (2010) 14 SCC 496", "point": "multi-factor bail checklist", "verified": False},
    {"case": "Gurbaksh Singh Sibbia v. State of Punjab (1980) 2 SCC 565", "point": "anticipatory — liberal", "verified": False},
    {"case": "Zeba Khan v. State of U.P. 2026 INSC 144", "point": "mandatory bail disclosure on affidavit (his prior-bail/co-accused/cross-case tables satisfy it)", "verified": False},
]


def _esc(s: Optional[str]) -> str:
    return "" if s is None else str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _ph(s: Optional[str], ph: str = "________") -> str:
    if s and str(s).strip():
        return _esc(s)
    return f'<span class="ph">{ph}</span>'


def _secs(sections) -> str:
    if isinstance(sections, (list, tuple)):
        return ", ".join(_esc(s) for s in sections if str(s).strip()) or "................"
    return _esc(sections) if sections and str(sections).strip() else "................"


def _ord_hi(n):
    return HINDI_ORDINAL[n] if 0 < n < len(HINDI_ORDINAL) else f"{n}वाँ"


def _custody_since(arrest):
    if not arrest:
        return None
    for fmt in ("%d.%m.%Y", "%d/%m/%Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(str(arrest).strip(), fmt).date()
            days = (date.today() - d).days
            if days >= 365:
                return f"लगभग {days // 365} वर्ष"
            if days >= 30:
                return f"लगभग {days // 30} माह"
            return f"{days} दिन"
        except ValueError:
            continue
    return None


def _level(court, antic):
    return "hc" if court == "hc" else ("magistrate" if court == "magistrate"
                                       else ("principal_sessions" if antic else "sessions"))


def _cfg(court, bail_type):
    antic = bail_type == "anticipatory"
    if court == "magistrate":
        sec = "480"
        case_code, case_suffix, case_code_en = "प्रकरण क्रमांक", "जमानत आवेदन", "Criminal Case"
    elif court == "hc":
        sec = "482" if antic else "483"
        case_code, case_suffix, case_code_en = "एम.सी.आर.सी.", "", "M.Cr.C."
    else:
        sec = "482" if antic else "483"
        case_code, case_suffix, case_code_en = "प्रकरण क्रमांक", "जमानत आवेदन", "Criminal Case"
    return dict(antic=antic, hc=(court == "hc"), sec=sec,
                case_code=case_code, case_suffix=case_suffix, case_code_en=case_code_en)


# ----------------------------------------------------------- tables (Hindi)
def _crime_order_table_hi(a, antic):
    """अपराध का विवरण | विवादित आदेश का विवरण — his bail summary table (verbatim)."""
    ps = _ph(a.get("police_station"), "थाना"); dist = _ph(a.get("district"), "जिला")
    st = _esc(a.get("state_name") or "म.प्र.")
    crime = (f'अपराध क्रमांक— {_ph(a.get("fir_number"), "..../....")}<br>'
             f'पुलिस— थाना {ps} जिला {dist} ({st})<br>'
             f'अपराध धारा ः— {_secs(a.get("sections"))}<br>'
             f'गिरफ्तारी दिनांक ः— {_ph(a.get("arrest_date"), "निल" if antic else "..........")}')
    order = (f'जमानत प्रकरण क्र.— {_ph(a.get("prior_bail_case"), "निल")}<br>'
             f'न्यायालय का नाम— {_ph(a.get("prior_court"), "—")}<br>'
             f'स्थान— {_ph(a.get("court_city"), "—")} ({st})<br>'
             f'आदेश दिनांक— {_ph(a.get("prior_order_date"), "निल")}')
    return ('<table class="cb-table"><tr><th>अपराध का विवरण</th>'
            '<th>विवादित आदेश का विवरण</th></tr>'
            f'<tr><td>{crime}</td><td>{order}</td></tr></table>')


def _prior_bail_table_hi(rows):
    out = ['<div class="cb-block-label">जमानत आवेदन पत्र लम्बित / निराकृत हुआ हो तो उसका विवरण</div>',
           '<table class="cb-table"><tr><th>न्यायालय</th><th>क्रमांक</th><th>आदेश दिनांक</th><th>नतीजा</th></tr>']
    by = {r.get("level"): r for r in (rows or [])}
    for label, lv in [("माननीय उच्चतम न्यायालय", "sc"), ("माननीय उच्च न्यायालय", "hc"),
                      ("माननीय अधीनस्थ न्यायालय", "lower")]:
        r = by.get(lv) or {}
        out.append(f'<tr><td>{label}</td><td>{_esc(r.get("case_no") or "निल")}</td>'
                   f'<td>{_esc(r.get("date") or "निल")}</td><td>{_esc(r.get("result") or "निल")}</td></tr>')
    out.append('</table>')
    return "\n".join(out)


def _co_accused_table_hi(rows):
    out = ['<table class="cb-table"><tr><th>क्र.</th><th>आवेदक का नाम</th><th>केस क्र.</th>'
           '<th>आदेश दिनांक</th><th>परिणाम</th><th>माननीय न्यायमूर्ति</th></tr>']
    for i, r in enumerate(rows or [], 1):
        out.append(f'<tr><td>{i}</td><td>{_esc(r.get("name"))}</td><td>{_esc(r.get("case_no"))}</td>'
                   f'<td>{_esc(r.get("date"))}</td><td>{_esc(r.get("result"))}</td>'
                   f'<td>{_esc(r.get("judge"))}</td></tr>')
    out.append('</table>')
    return "\n".join(out)


def _para_list(decls, facts, grounds, heavy=False):
    """Numbered body. heavy=True (HC) → in-list SECTION headers; heavy=False
    (Sessions/Magistrate, his real light filing) → one continuous यहकि list, no labels."""
    out = ['<ol class="cb-paras">']
    if not heavy:
        for p in decls + facts + grounds:
            out.append(f'<li>{p}</li>')
        out.append('</ol>')
        return "\n".join(out)
    for p in decls:
        out.append(f'<li>{p}</li>')
    if facts:
        out.append('<li class="cb-head">प्रकरण के संक्षिप्त तथ्य ः—</li>')
        for p in facts:
            out.append(f'<li>{p}</li>')
    out.append('<li class="cb-head">जमानत के आधार ः—</li>')
    for p in grounds:
        out.append(f'<li>{p}</li>')
    out.append('</ol>')
    return "\n".join(out)


# ----------------------------------------------------------- HINDI render (main app)
def render_hi(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "sessions"
    btype = a.get("bail_type") or "regular"
    c = _cfg(court, btype)
    antic, hc = c["antic"], c["hc"]
    appno = int(a.get("application_number") or 1)
    name = a.get("applicant_name") or ""
    title_sec = f"धारा {c['sec']} भारतीय नागरिक सुरक्षा संहिता"
    title = (f"आवेदन पत्र अन्तर्गत {title_sec}" if court == "magistrate"
             else f"{_ord_hi(appno)} {'अग्रिम जमानत' if antic else 'जमानत'} आवेदन पत्र अन्तर्गत {title_sec}")
    court_name = a.get("court_name") or compose_court_name(_level(court, antic), a.get("court_city"), a.get("state_name") or "म.प्र.")

    hdr = render_header({
        "side_label": "आवेदक की ओर से" if antic else "बन्दी की ओर से",
        "court_name": court_name, "case_code": c["case_code"],
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": c["case_suffix"], "applicant_label": "आवेदक",
        "applicant_desc": [
            f'{_ph(name, "नाम")} पुत्र श्री {_ph(a.get("applicant_father"), "पिता")},',
            f'आयु— {_ph(a.get("applicant_age"), "..")} वर्ष, व्यवसाय— {_ph(a.get("applicant_occupation"), "व्यवसाय")},',
            f'निवासी— <u>{_ph(a.get("applicant_address"), "पता")}</u>, जिला {_ph(a.get("district"), "जिला")} ({_esc(a.get("state_name") or "म.प्र.")})',
        ],
        "respondent_label": "अनावेदक",
        "respondent_desc": [f'{_esc(a.get("state_name") or "म.प्र.")} शासन द्वारा',
                            f'पुलिस थाना {_ph(a.get("police_station"), "थाना")} जिला {_ph(a.get("district"), "जिला")}'],
        "versus": "बनाम", "title_line": title,
    })

    g = a.get("grounds") or {}
    out = [hdr, '<div class="doc-body">']

    # --- recital + tables (his order) ---
    if court in ("sessions", "hc"):
        out.append('<p class="cb-prelude">आवेदक का इस आशय का अन्य कोई जमानत आवेदन माननीय उच्चतम '
                   'न्यायालय, माननीय उच्च न्यायालय अथवा माननीय अधीनस्थ न्यायालय में न तो विचाराधीन है '
                   'और न ही पूर्व में निरस्त हुआ है।</p>')
    # HC-only heavy framing: prior-bail + crime/impugned-order tables + co-accused/cross-case
    if hc:
        out.append(_prior_bail_table_hi(a.get("prior_bail") or []))
        out.append(_crime_order_table_hi(a, antic))
        if a.get("co_accused"):
            out.append('<div class="cb-block-label">सहअभियुक्तगण के जमानत आवेदन का विवरण</div>')
            out.append(_co_accused_table_hi(a.get("co_accused")))
            out.append('<p class="cb-prelude">यहकि, आवेदक के विरुद्ध कोई क्रॉस-केस पंजीवद्ध नहीं है।</p>')

    out.append('<p class="cb-prelude">माननीय न्यायालय,</p>')
    who = "आवेदक" if antic else "प्रार्थी"
    out.append(f'<p class="cb-prelude">{who} की ओर से आवेदन पत्र निम्न प्रकार प्रस्तुत है ः—</p>')

    # --- DECLARATION (HC keeps the formal application-number para; subordinate
    #     courts carry the number in the TITLE line, not a separate para) ---
    decls = []
    if hc:
        decls.append(f'यहकि, माननीय न्यायालय के समक्ष {who} की ओर से यह {_ord_hi(appno)} '
                     f'{"अग्रिम जमानत" if antic else "जमानत"} आवेदन पत्र अन्तर्गत {title_sec} का प्रस्तुत किया जा रहा है।')

    # --- FACTS: F1 case-line · D prior-rejected (successive) · [F] case-specific defence ---
    facts = []
    ps = _ph(a.get("police_station"), "थाना"); dist = _ph(a.get("district"), "जिला")
    fir = _ph(a.get("fir_number"), "..../...."); secs = _secs(a.get("sections"))
    if antic:
        appr = a.get("apprehension_reason") or ""
        tail = f' तथा {_esc(appr)}' if appr.strip() else ''
        facts.append(f'यहकि, पुलिस थाना {ps} जिला {dist} में अपराध क्रमांक— {fir} अन्तर्गत धारा {secs} '
                     f'का प्रकरण पंजीवद्ध है, जिसमें पुलिस द्वारा प्रार्थी को गिरफ्तार करने हेतु प्रयास '
                     f'किया जा रहा है, जिससे प्रार्थी की गिरफ्तारी की युक्तियुक्त आशंका उत्पन्न हो गई है{tail}।')
    else:
        arr = a.get("arrest_date")
        arr_ph = f'दिनांक {_esc(arr)} को' if arr else 'गिरफ्तारी उपरान्त'
        facts.append(f'यहकि, पुलिस थाना {ps} जिला {dist} द्वारा प्रार्थी के विरुद्ध अपराध क्रमांक— {fir} '
                     f'अन्तर्गत धारा {secs} का मिथ्या आधारों पर पंजीवद्ध कर लिया गया, जिसमें प्रार्थी को '
                     f'{arr_ph} गिरफ्तार कर माननीय न्यायालय के समक्ष प्रस्तुत कर न्यायिक अभिरक्षा में भेजा गया है।')
    if not antic and court in ("sessions", "hc") and g.get("prior_mag_rejected", False):
        lc = "अधीनस्थ न्यायालय" if court == "hc" else "विद्वान न्यायिक दण्डाधिकारी प्रथम श्रेणी"
        facts.append(f'यहकि, {who} की ओर से प्रस्तुत पूर्व जमानत आवेदन {lc} द्वारा निरस्त किया जा चुका है।')
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            facts.append(f'यहकि, {_esc(ch)}')
    else:
        facts.append('<span class="ph">[प्रकरण के संक्षिप्त तथ्य — अभियोजन का आक्षेप एवं प्रार्थी का बचाव; या FIR अपलोड कर भरवायें]</span>')

    # --- GROUNDS ---
    G = []
    G.append('यहकि, प्रार्थी द्वारा कोई अपराध कारित नहीं किया गया है, न ही प्रार्थी का किसी अपराध अथवा '
             'अपराधी से प्रत्यक्ष अथवा परोक्ष कोई सम्बन्ध है। प्रार्थी को मिथ्या तथ्यों के आधार पर आरोपी '
             'बनाया गया है।')
    if g.get("respected_resident"):
        G.append('यहकि, प्रार्थी समाज का प्रतिष्ठित एवं सम्मानीय व्यक्ति है तथा उपरोक्त वर्णित पते का '
                 'स्थायी निवासी है।')
    if g.get("breadwinner"):
        G.append(f'यहकि, प्रार्थी पेशे से {_ph(a.get("applicant_occupation"), "मजदूर")} होकर अपने परिवार '
                 f'का भरण पोषण करने वाला एकमात्र व्यक्ति है; प्रार्थी को {"गिरफ्तार किया गया" if antic else "कारागार में अधिक समय तक रखा गया"} '
                 f'तो उसके परिवार के भरण पोषण पर विपरीत प्रभाव पड़ेगा।')
    if g.get("parity") and (a.get("co_accused_note") or a.get("co_accused")):
        note = a.get("co_accused_note") or "प्रकरण के सहअभियुक्त को माननीय न्यायालय द्वारा जमानत का लाभ प्रदान किया जा चुका है।"
        G.append(f'यहकि, {_esc(note)} प्रार्थी का प्रकरण सहअभियुक्त से भिन्न नहीं है, अतः समानता के '
                 f'सिद्धान्त पर प्रार्थी भी जमानत का अधिकारी है।')
    if not antic:
        G.append('यहकि, प्रार्थी पर अधिरोपित अपराध आजीवन कारावास एवं मृत्यु दण्ड से दण्डनीय न होकर '
                 'माननीय न्यायालय के समक्ष विचारण योग्य है।')
    if g.get("nature_circumstance"):
        G.append('यहकि, प्रकरण की परिस्थिति, तथ्यों एवं अपराध के स्वरूप को दृष्टिगत रखते हुये प्रार्थी को '
                 'जमानत का लाभ दिया जाना न्यायोचित है।')
    G.append('यहकि, प्रार्थी उपरोक्त वर्णित पते का स्थाई निवासी है; जमानत का लाभ दिया जाने पर प्रार्थी के '
             'कहीं भागकर जाने अथवा अभियोजन साक्ष्य को प्रभावित किये जाने की कोई संभावना नहीं है।')
    if g.get("offence_upto_7yr"):
        G.append('यहकि, प्रार्थी के विरुद्ध अधिरोपित अपराध 07 वर्ष से अधिक के कारावास से दण्डनीय नहीं है। '
                 'ऐसी स्थिति में अर्नेश कुमार बनाम बिहार राज्य (2014) 8 एस.सी.सी. 273 एवं सतेन्द्र कुमार '
                 'अंटिल बनाम सेन्ट्रल ब्यूरो ऑफ इन्वेस्टिगेशन (2022) 10 एस.सी.सी. 51 के न्यायदृष्टान्त के '
                 'अनुसार प्रार्थी जमानत का अधिकारी है।')
    cust = _custody_since(a.get("arrest_date")) if not antic else None
    if not antic and g.get("trial_delay") and cust:
        G.append(f'यहकि, प्रार्थी दिनांक {_esc(a.get("arrest_date"))} से न्यायिक अभिरक्षा में निरुद्ध है '
                 f'तथा उसे निरुद्ध हुये {cust} का समय हो चुका है; विचारण में समय लगना सम्भावित है।')
    for cu in (a.get("custom_grounds") or []):
        if str(cu).strip():
            G.append(f'यहकि, {_esc(cu)}')
    G.append('यहकि, प्रार्थी के प्रकरण में समय लगने की संभावना से इन्कार नहीं किया जा सकता। प्रार्थी '
             + ('अग्रिम ' if antic else '') + 'जमानत पर रिहा किया जाता है तो माननीय न्यायालय द्वारा '
             'अधिरोपित समस्त शर्तों का विधिवत पालन करता रहेगा तथा प्रत्येक पेशी पर उपस्थित रहेगा।')
    G.append('यहकि, अन्य तर्क वक्त बहस मौखिक रुप से निवेदित किये जावेंगे।')

    out.append(_para_list(decls, facts, G, heavy=hc))

    # --- prayer ---
    out.append('<div class="cb-prayer"><p>')
    if antic:
        out.append(f'अतः श्रीमान न्यायालय से प्रार्थना है कि प्रार्थी की ओर से प्रस्तुत आवेदन पत्र स्वीकार '
                   f'कर पुलिस थाना {ps} जिला {dist} से सम्बन्धित अपराध क्रमांक— {fir} की केस डायरी मय कैफियत '
                   f'तलब कर प्रार्थी को उचित अग्रिम प्रतिभूति पर रिहा किये जाने का आदेश प्रदान करने की कृपा करें।')
    else:
        out.append('अतः श्रीमान न्यायालय से प्रार्थना है कि प्रार्थी की ओर से प्रस्तुत आवेदन पत्र स्वीकार '
                   'कर प्रार्थी को उचित प्रतिभूति पर रिहा किये जाने का आदेश प्रदान करने की कृपा करें।')
    out.append('</p></div>')

    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>स्थान: {_ph(a.get("court_city"), "स्थान")}</div>'
               f'<div>दिनांक: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append('<div class="r"><div>प्रार्थी</div>'
               f'<div>{_ph(name, "नाम")} — {"आवेदक" if antic else "बन्दी आवेदक"}</div>'
               '<div style="margin-top:10pt">द्वारा अभिभाषक</div>'
               f'<div>({_ph(a.get("advocate_name"), "अधिवक्ता")}) — एडवोकेट</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- AFFIDAVIT (शपथ पत्र) — his format
def render_affidavit_hi(a: dict) -> str:
    a = a or {}
    court = a.get("court") or "sessions"
    btype = a.get("bail_type") or "regular"
    c = _cfg(court, btype)
    antic = c["antic"]
    court_name = a.get("court_name") or compose_court_name(_level(court, antic), a.get("court_city"), a.get("state_name") or "म.प्र.")
    appno = int(a.get("application_number") or 1)
    applicant = a.get("applicant_name") or "________"
    dep_name = a.get("deponent_name") or applicant
    dep_rel = a.get("deponent_relation") or "स्वयं आवेदक"

    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": c["case_code"],
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "case_suffix": c["case_suffix"], "applicant_label": "आवेदक",
        "applicant_desc": [_ph(applicant, "आवेदक")], "respondent_label": "अनावेदक",
        "respondent_desc": [f'{_esc(a.get("state_name") or "म.प्र.")} शासन'],
        "versus": "बनाम", "title_line": "शपथ पत्र",
    })
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    out = [hdr, '<div class="doc-body">']
    out.append('<table class="cb-table" style="max-width:62%">'
               f'<tr><td>नाम</td><td>{_ph(dep_name, "नाम")}</td></tr>'
               f'<tr><td>पिता/पति का नाम</td><td>{_ph(a.get("deponent_father") or a.get("applicant_father"), "पिता")}</td></tr>'
               f'<tr><td>आयु</td><td>{_ph(a.get("deponent_age") or a.get("applicant_age"), "..")} वर्ष</td></tr>'
               f'<tr><td>व्यवसाय</td><td>{_ph(a.get("deponent_occupation") or a.get("applicant_occupation"), "व्यवसाय")}</td></tr>'
               f'<tr><td>निवासी</td><td>{_ph(a.get("deponent_address") or a.get("applicant_address"), "पता")}</td></tr>'
               '</table>')
    out.append('<p class="cb-prelude">मैं उक्त शपथकर्ता शपथपूर्वक सत्य कथन करता/करती हूँ किः—</p>')
    out.append('<ol class="cb-paras">')
    out.append(f'<li>यहकि, उपरोक्त प्रकरण में आवेदक {_ph(applicant, "आवेदक")} मुझ शपथकर्ता का {_esc(dep_rel)} '
               f'है तथा मुझे प्रकरण की सम्पूर्ण जानकारी है। मुझ शपथकर्ता द्वारा आवेदक की ओर से यह '
               f'{_ord_hi(appno)} {"अग्रिम जमानत" if antic else "जमानत"} आवेदन पत्र अन्तर्गत धारा {c["sec"]} '
               f'भारतीय नागरिक सुरक्षा संहिता माननीय न्यायालय के समक्ष प्रस्तुत किया गया है। उक्त आवेदन के '
               f'अतिरिक्त माननीय उच्चतम न्यायालय, माननीय उच्च न्यायालय एवं माननीय अधीनस्थ न्यायालय में '
               f'वर्तमान में न तो प्रस्तुत है, न लंबित है और न ही निराकृत हुआ है।</li>')
    out.append(f'<li>यहकि, मुझ शपथकर्ता द्वारा उक्त जमानत आवेदन में पैरवी हेतु अभिभाषक '
               f'{_ph(a.get("advocate_name"), "अधिवक्ता")} को नियुक्त किया गया है, जो उक्त प्रकरण में '
               f'पैरवी करेंगे।</li>')
    out.append('</ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>दिनांक: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">हस्ताक्षर शपथकर्ता</div>'
               f'<div>({_ph(dep_name, "शपथकर्ता")})</div></div></div>')
    out.append('<div class="cb-block-label">सत्यापन</div>')
    out.append('<p class="cb-prelude">मैं शपथकर्ता शपथपूर्वक सत्यापित करता/करती हूँ कि शपथ पत्र के पद '
               'क्रमांक 1 लगायत 2 में दी गई जानकारी मेरे ज्ञान व विश्वास के आधार पर सत्य व सही है, जिसमें '
               'कुछ भी असत्य नहीं है और न ही कुछ छिपाया गया है।</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>दिनांक: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">हस्ताक्षर सत्यापनकर्ता</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


def render_affidavit_en(a: dict) -> str:
    """English mirror of the supporting affidavit (शपथ पत्र)."""
    a = dict(a or {})
    for _k in list(a):
        if _k.endswith("_en") and a[_k] not in (None, ""):
            a[_k[:-3]] = a[_k]
    court = a.get("court") or "sessions"
    c = _cfg(court, a.get("bail_type") or "regular")
    court_name = a.get("court_name") or compose_court_name(_level(court, c["antic"]), a.get("court_city"), a.get("state_name") or "M.P.", lang="en")
    applicant = _ph(a.get("applicant_name"), "applicant")
    dep = _ph(a.get("deponent_name") or a.get("applicant_name"), "deponent")
    fd = _ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))
    hdr = render_header({
        "side_label": "", "court_name": court_name, "case_code": c["case_code_en"],
        "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
        "applicant_label": "Applicant", "applicant_desc": [applicant], "respondent_label": "Respondent",
        "respondent_desc": [f'State of {_esc(a.get("state_name") or "M.P.")}'], "versus": "Versus", "title_line": "AFFIDAVIT",
    })
    out = [hdr, '<div class="doc-body">']
    out.append('<table class="cb-table" style="max-width:62%">'
               f'<tr><td>Name</td><td>{dep}</td></tr>'
               f'<tr><td>Father/Husband</td><td>{_ph(a.get("deponent_father") or a.get("applicant_father"), "father")}</td></tr>'
               f'<tr><td>Age</td><td>{_ph(a.get("deponent_age") or a.get("applicant_age"), "..")} yrs</td></tr>'
               f'<tr><td>Occupation</td><td>{_ph(a.get("deponent_occupation") or a.get("applicant_occupation"), "occupation")}</td></tr>'
               f'<tr><td>R/o</td><td>{_ph(a.get("deponent_address") or a.get("applicant_address"), "address")}</td></tr></table>')
    out.append('<p class="cb-prelude">I, the deponent, do solemnly affirm and state as under:—</p><ol class="cb-paras">')
    out.append(f'<li>That the applicant {applicant} is known to me and I am acquainted with the facts; this bail '
               f'application under Section {c["sec"]} BNSS has been filed on the applicant\'s behalf, and no other '
               f'such application is pending or decided before the Hon\'ble Supreme Court, this Court or the court below.</li>')
    out.append(f'<li>That counsel {_ph(a.get("advocate_name"), "advocate")} has been engaged to conduct the case.</li></ol>')
    out.append(f'<div class="cb-sig"><div class="l"><div>Date: {fd}</div></div>'
               f'<div class="r"><div style="margin-top:18pt">Signature of Deponent</div><div>({dep})</div></div></div>')
    out.append('<div class="cb-block-label" style="text-align:left">VERIFICATION</div>')
    out.append('<p class="cb-prelude">I, the deponent, verify that paras 1-2 are true to my knowledge and belief; '
               'nothing material has been concealed.</p>')
    out.append(f'<div class="cb-sig"><div class="l"><div>Date: {fd}</div></div>'
               '<div class="r"><div style="margin-top:18pt">Signature of Deponent</div></div></div></div>')
    return "\n".join(out)


def bundle(a: dict, lang: str = "hi"):
    """The full bail FILING bundle as an ordered list of sheets (+ labels).
    HC = Index → Application(मय शपथपत्र) → Affidavit ; Sessions/Magistrate =
    Application → Affidavit. (Annexure list + vakalatnama added in the next pass.)"""
    a = a or {}
    hi = lang == "hi"
    court = a.get("court") or "sessions"
    R = render_hi if hi else render_en
    AFF = render_affidavit_hi if hi else render_affidavit_en
    sheets, labels = [], []
    if court == "hc":
        idx_hdr = {
            "side_label": "",
            "court_name": (a.get("court_name") if hi else (a.get("court_name_en") or a.get("court_name")))
            or ("माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर" if hi else "High Court of M.P., Bench at Gwalior"),
            "case_code": "एम.सी.आर.सी." if hi else "M.Cr.C.",
            "case_number": a.get("case_number") or "", "case_year": a.get("case_year") or str(date.today().year),
            "applicant_label": "आवेदक" if hi else "Applicant",
            "applicant_desc": [_ph(a.get("applicant_name"), "आवेदक" if hi else "applicant")],
            "respondent_label": "अनावेदक" if hi else "Respondent",
            "respondent_desc": [(_esc(a.get("state_name") or "म.प्र.") + " शासन") if hi else ("State of " + _esc(a.get("state_name") or "M.P."))],
            "versus": "बनाम" if hi else "Versus",
        }
        items = [
            {"hi": "जमानत आवेदन पत्र मय शपथपत्र", "en": "Bail application with affidavit"},
            {"hi": "विचारण/अधीनस्थ न्यायालय के आदेश की प्रति", "en": "Copy of the trial / lower-court order", "annexure": "ए-1" if hi else "A-1"},
            {"hi": "वकालतनामा", "en": "Vakalatnama"},
        ]
        sheets.append(render_index(idx_hdr, items, lang)); labels.append("इन्डेक्स" if hi else "Index")
    sheets.append(R(a)); labels.append("जमानत आवेदन पत्र" if hi else "Bail Application")
    sheets.append(AFF(a)); labels.append("शपथ पत्र" if hi else "Affidavit")
    return sheets, labels


# ----------------------------------------------------------- ENGLISH render
def render_en(a: dict) -> str:
    a = dict(a or {})
    for _k in list(a):  # overlay any *_en value onto its base key → English-aware render
        if _k.endswith("_en") and a[_k] not in (None, ""):
            a[_k[:-3]] = a[_k]
    court = a.get("court") or "sessions"
    btype = a.get("bail_type") or "regular"
    c = _cfg(court, btype)
    antic, hc = c["antic"], c["hc"]
    appno = int(a.get("application_number") or 1)
    name = a.get("applicant_name") or ""
    title = f'APPLICATION FOR {"ANTICIPATORY " if antic else ""}BAIL UNDER SECTION {c["sec"]} OF THE BNSS, 2023'
    if court != "magistrate":
        title = f'{EN_ORDINAL[appno] if appno < len(EN_ORDINAL) else str(appno)} {title}'
    court_name = a.get("court_name_en") or compose_court_name(_level(court, antic), a.get("court_city"), a.get("state_name") or "M.P.", lang="en")
    hdr = render_header({
        "side_label": "On behalf of the Applicant", "court_name": court_name,
        "case_code": c["case_code_en"], "case_number": a.get("case_number") or "",
        "case_year": a.get("case_year") or str(date.today().year), "applicant_label": "Applicant",
        "applicant_desc": [
            f'{_ph(name, "name")}, S/o {_ph(a.get("applicant_father"), "father")},',
            f'aged {_ph(a.get("applicant_age"), "..")} yrs, occupation {_ph(a.get("applicant_occupation"), "occupation")},',
            f'R/o <u>{_ph(a.get("applicant_address"), "address")}</u>, Distt. {_ph(a.get("district"), "district")}',
        ],
        "respondent_label": "Respondent",
        "respondent_desc": [f'State of {_esc(a.get("state_name") or "M.P.")} through',
                            f'P.S. {_ph(a.get("police_station"), "P.S.")}, Distt. {_ph(a.get("district"), "district")}'],
        "versus": "Versus", "title_line": title,
    })
    ps = _ph(a.get("police_station"), "P.S."); dist = _ph(a.get("district"), "district")
    fir = _ph(a.get("fir_number"), "..../...."); secs = _secs(a.get("sections"))
    g = a.get("grounds") or {}
    out = [hdr, '<div class="doc-body">']
    if court in ("sessions", "hc"):
        out.append('<p class="cb-prelude">That no similar bail application is pending or has been rejected '
                   'before the Hon\'ble Supreme Court, this Hon\'ble Court or the subordinate court.</p>')
    if hc:   # HC-only heavy framing: crime / impugned-order table
        out.append('<table class="cb-table"><tr><th>Crime details</th><th>Impugned order</th></tr>'
                   f'<tr><td>Crime No. {fir}<br>P.S. {ps}, Distt. {dist}<br>u/s {secs}<br>'
                   f'Arrest: {_ph(a.get("arrest_date"), "Nil" if antic else "..........")}</td>'
                   f'<td>Bail Case No. {_ph(a.get("prior_bail_case"), "Nil")}<br>'
                   f'Court: {_ph(a.get("prior_court"), "—")}<br>Order dt. {_ph(a.get("prior_order_date"), "Nil")}</td></tr></table>')
    out.append('<p class="cb-prelude">MAY IT PLEASE THE COURT,</p>')
    out.append('<p class="cb-prelude">The applicant most respectfully submits as under:—</p>')
    decls = []
    if hc:
        decls.append(f'That this is the {EN_ORDINAL[appno].lower() if appno < len(EN_ORDINAL) else appno} '
                     f'{"anticipatory " if antic else ""}bail application of the applicant under Section {c["sec"]} BNSS.')
    facts = []
    if antic:
        facts.append(f'That a case, Crime No. {fir} under {secs}, stands registered at P.S. {ps}, Distt. {dist}; '
                     f'the police are attempting to arrest the applicant, giving rise to a reasonable apprehension of arrest.')
    else:
        facts.append(f'That a false case, Crime No. {fir} under {secs}, was registered against the applicant at '
                     f'P.S. {ps}, Distt. {dist}; the applicant was arrested and remanded to judicial custody.')
    if not antic and court in ("sessions", "hc") and g.get("prior_mag_rejected", False):
        facts.append('That the applicant\'s earlier bail application was rejected by the court below.')
    if (a.get("facts_narrative") or "").strip():
        for ch in [x.strip() for x in a["facts_narrative"].split("\n\n") if x.strip()]:
            facts.append(f'That {_esc(ch)}')
    else:
        facts.append('<span class="ph">[Brief facts — the allegation and the defence; or upload the FIR to auto-fill.]</span>')
    G = ['That the applicant has committed no offence and has no connection with any offence; he has been falsely implicated.']
    if g.get("respected_resident"):
        G.append('That the applicant is a respectable member of society and a permanent resident of the address stated above.')
    if g.get("breadwinner"):
        G.append('That the applicant is the sole breadwinner of his family.')
    if g.get("parity") and (a.get("co_accused_note") or a.get("co_accused")):
        G.append('That a similarly placed co-accused has been granted bail; on parity the applicant too is entitled.')
    if not antic:
        G.append('That the offence is not punishable with death or life imprisonment and is triable by this Court.')
    if g.get("nature_circumstance"):
        G.append('That having regard to the facts, circumstances and nature of the offence, the grant of bail to the applicant is just and proper.')
    G.append('That the applicant is a permanent resident; there is no apprehension of flight or tampering with evidence.')
    if g.get("offence_upto_7yr"):
        G.append('That the offence is not punishable with imprisonment exceeding seven years, and per Arnesh Kumar '
                 'v. State of Bihar (2014) 8 SCC 273 and Satender Kumar Antil v. CBI (2022) 10 SCC 51 the applicant '
                 'is entitled to bail.')
    G.append(f'That if released on {"anticipatory " if antic else ""}bail the applicant shall abide by all '
             f'conditions and attend every hearing.')
    G.append('That further arguments shall be advanced orally at the time of hearing.')
    # body: HC = in-list section labels; subordinate courts = flat continuous list
    body = ['<ol class="cb-paras">']
    if hc:
        for p in decls:
            body.append(f'<li>{p}</li>')
        if facts:
            body.append('<li class="cb-head">BRIEF FACTS:—</li>')
            for p in facts:
                body.append(f'<li>{p}</li>')
        body.append('<li class="cb-head">GROUNDS FOR BAIL:—</li>')
        for p in G:
            body.append(f'<li>{p}</li>')
    else:
        for p in decls + facts + G:
            body.append(f'<li>{p}</li>')
    body.append('</ol>')
    out.append("\n".join(body))
    out.append('<div class="cb-prayer"><p>')
    if antic:
        out.append(f'It is therefore prayed that this Hon\'ble Court may call for the case diary in Crime No. {fir} '
                   f'(P.S. {ps}) and direct that, in the event of arrest, the applicant be released on anticipatory '
                   f'bail on suitable security.')
    else:
        out.append('It is therefore prayed that this Hon\'ble Court may be pleased to release the applicant on bail '
                   'on suitable security, in the interest of justice.')
    out.append('</p></div>')
    out.append('<div class="cb-sig"><div class="l">')
    out.append(f'<div>Place: {_ph(a.get("court_city"), "place")}</div>'
               f'<div>Date: {_ph(a.get("filing_date"), date.today().strftime("%d/%m/%Y"))}</div></div>')
    out.append('<div class="r"><div>Applicant</div>'
               f'<div>{_ph(name, "applicant")}</div>'
               '<div style="margin-top:10pt">Through Counsel</div>'
               f'<div>({_ph(a.get("advocate_name"), "advocate")})</div></div></div>')
    out.append('</div>')
    return "\n".join(out)


# ----------------------------------------------------------- FIELD SCHEMA
_TOGGLES = [
    F.toggle("prior_mag_rejected", "अधीनस्थ न्यायालय से जमानत निरस्त (successive)", "Lower-court bail rejected (successive)", default=False),
    F.toggle("respected_resident", "प्रतिष्ठित/सम्मानीय व्यक्ति, स्थायी निवासी", "Respectable person, permanent resident", default=False),
    F.toggle("breadwinner", "एकमात्र कमाने वाला", "Sole breadwinner", default=False),
    F.toggle("parity", "सहअभियुक्त को जमानत (समानता)", "Co-accused bailed (parity)", default=False),
    F.toggle("nature_circumstance", "प्रकरण की परिस्थिति/स्वरूप अनुसार न्यायोचित", "Just per facts & nature of offence", default=False),
    F.toggle("offence_upto_7yr", "अपराध ≤ 7 वर्ष (अर्नेश कुमार)", "Offence ≤ 7 yrs (Arnesh Kumar)", default=False),
    F.toggle("trial_delay", "विचारण में विलंब / दीर्घ निरोध", "Trial delay / long custody", default=False),
]


def field_spec(court: str = "sessions", bail_type: str = "regular") -> dict:
    antic = bail_type == "anticipatory"
    flds = [
        F.f("court_city", "जिला / शहर", "District / City", required=True, section="court",
            hint="डिवाइस-लोकेशन से स्वतः; इसी से न्यायालय का नाम बनता है"),
        F.f("court_name", "न्यायालय का नाम (स्वतः)", "Court name (auto)", section="court", auto=True),
        F.f("case_number", "प्रकरण/केस क्रमांक", "Case no.", section="court"),
        F.f("case_year", "वर्ष", "Year", F.NUMBER, section="court"),
        F.f("application_number", "आवेदन क्रमांक (प्रथम/द्वितीय…)", "Application no.", F.NUMBER, section="court", default=1),
        F.f("applicant_name", "आवेदक का नाम", "Applicant name", F.NAME, True, "parties", ocr="fir"),
        F.f("applicant_father", "पिता/पति का नाम", "Father/Husband", F.NAME, section="parties", ocr="fir"),
        F.f("applicant_age", "आयु", "Age", F.NUMBER, section="parties"),
        F.f("applicant_occupation", "व्यवसाय", "Occupation", section="parties"),
        F.f("applicant_address", "पता", "Address", F.ADDRESS, True, "parties", ocr="fir"),
        F.f("police_station", "पुलिस थाना", "Police station", required=True, section="crime", ocr="fir"),
        F.f("district", "जिला", "District", required=True, section="crime", ocr="fir"),
        F.f("fir_number", "अपराध/FIR क्रमांक", "Crime / FIR no.", required=True, section="crime", ocr="fir"),
        F.f("sections", "धाराएं", "Offence sections", F.SECTION_LIST, True, "crime", ocr="fir"),
        F.f("facts_narrative", "तथ्य (अभियोजन कहानी / बचाव)", "Facts (prosecution story / defence)", F.LONGTEXT, section="facts", ocr="fir"),
        F.f("advocate_name", "अधिवक्ता का नाम", "Advocate name", F.NAME, section="filing"),
        F.f("filing_date", "दिनांक", "Date", F.DATE, section="filing", auto=True),
    ]
    if antic:
        flds.insert(14, F.f("apprehension_reason", "गिरफ्तारी की आशंका का कारण", "Reason for apprehension", F.LONGTEXT, True, "facts"))
    else:
        flds.insert(13, F.f("arrest_date", "गिरफ्तारी दिनांक", "Date of arrest", F.DATE, section="crime", hint="→ निरोध अवधि स्वतः"))
    # impugned-order fields (successive — sessions/hc)
    if court in ("sessions", "hc"):
        flds += [
            F.f("prior_bail_case", "पूर्व जमानत प्रकरण क्र.", "Prior bail case no.", section="grounds", depends="prior_mag_rejected"),
            F.f("prior_court", "विवादित आदेश का न्यायालय", "Court of impugned order", section="grounds", depends="prior_mag_rejected"),
            F.f("prior_order_date", "विवादित आदेश दिनांक", "Impugned order date", F.DATE, section="grounds", depends="prior_mag_rejected"),
        ]
    if court == "hc":
        flds += [
            F.f("prior_bail", "पूर्व जमानत इतिहास (तालिका)", "Prior bail history (table)", F.TABLE, section="grounds"),
            F.f("co_accused", "सहअभियुक्त जमानत (तालिका)", "Co-accused bail (table)", F.TABLE, section="grounds"),
            F.f("deponent_name", "शपथकर्ता का नाम", "Deponent name", F.NAME, section="filing", hint="शपथ पत्र हेतु; प्रायः आवेदक/परिजन"),
            F.f("deponent_relation", "शपथकर्ता का सम्बन्ध", "Deponent's relation", section="filing", default="स्वयं आवेदक"),
        ]
    companions = ["vakalatnama"]
    if court == "hc":
        companions += ["शपथ पत्र (separate sheet)", "index/annexures (lower-court order + FIR)"]
    flds.append(F.custom_grounds())
    flds.append(F.f("state_name", "राज्य", "State", section="parties", hint="रिक्त रखने पर म.प्र."))
    return F.build_spec(f"bail:{court}:{bail_type}", flds, _TOGGLES,
                        variants={"court": ["magistrate", "sessions", "hc"], "bail_type": ["regular", "anticipatory"]},
                        companions=companions)


# ----------------------------------------------------------- SAMPLES + review
_BASE = {
    "court_city": "ग्वालियर", "court_city_en": "Gwalior",
    "applicant_name": "क ख ग", "applicant_name_en": "K. B. G.",
    "applicant_father": "य र ल", "applicant_father_en": "Y. R. L.", "applicant_age": "32",
    "applicant_occupation": "मजदूरी", "applicant_occupation_en": "labour",
    "applicant_address": "ग्राम ____, पनिहार", "applicant_address_en": "Village ____, Panihar",
    "state_name": "म.प्र.", "state_name_en": "M.P.",
    "police_station": "पनिहार", "police_station_en": "Panihar",
    "district": "ग्वालियर", "district_en": "Gwalior",
    "fir_number": "____/2025", "sections": ["32(2) आबकारी अधिनियम"], "sections_en": ["§32(2) Excise Act"],
    "filing_date": "__/06/2026", "advocate_name": "____",
    "facts_narrative": "अभियोजन कहानी के अनुसार प्रार्थी को मिथ्या आधारों पर आरोपी बनाया गया है; घटना से प्रार्थी का कोई सम्बन्ध नहीं है।",
    "facts_narrative_en": "as per the prosecution story the applicant has been falsely implicated on baseless grounds; the applicant has no connection with the incident.",
    "grounds": {"breadwinner": True},
}
SAMPLE_MAGISTRATE = {**_BASE, "court": "magistrate", "bail_type": "regular", "arrest_date": "01.06.2026"}
SAMPLE_SESSIONS = {**_BASE, "court": "sessions", "bail_type": "regular", "arrest_date": "20.03.2026",
                   "grounds": {"prior_mag_rejected": True, "breadwinner": True, "trial_delay": True},
                   "prior_bail_case": "____/2026", "prior_court": "विद्वान न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर",
                   "prior_court_en": "learned JMFC, Gwalior", "prior_order_date": "15.04.2026"}
SAMPLE_HC = {**_BASE, "court": "hc", "bail_type": "regular", "arrest_date": "10.01.2026",
             "grounds": {"prior_mag_rejected": True, "trial_delay": True},
             "prior_bail_case": "982/2026", "prior_court": "अठारहवें अतिरिक्त सत्र न्यायाधीश, ग्वालियर",
             "prior_court_en": "18th Addl. Sessions Judge, Gwalior", "prior_order_date": "28.04.2026",
             "prior_bail": [{"level": "lower", "case_no": "982/2026", "date": "28.04.2026", "result": "निरस्त"}],
             "co_accused": [{"name": "राजेश", "case_no": "12210/2026", "date": "16.03.2026", "result": "स्वीकार", "judge": "श्री ____ जी"}],
             "deponent_name": "ब ब", "deponent_relation": "भाई"}
SAMPLE_ANTICIPATORY = {**_BASE, "court": "sessions", "bail_type": "anticipatory",
                       "sections": ["420", "406 भा.न्या.सं."],
                       "apprehension_reason": "पुलिस द्वारा प्रार्थी को गिरफ्तार किये जाने की सूचना दी गई है",
                       "grounds": {"offence_upto_7yr": True, "breadwinner": True}}


def review_page_html(data: Optional[dict] = None) -> str:
    if data is not None:
        docs = [render_hi(data), render_en(data)]
        if (data.get("court") == "hc"):
            docs.append(render_affidavit_hi(data))
        return doc_page(docs, banner="जमानत — समीक्षा (canonical header · bilingual)")
    banner = (
        '<b>समीक्षा — जमानत आवेदन (एक इंजन, सभी न्यायालय · विष्णु जी की filings से अक्षरशः)</b><br>'
        'canonical header · अपराध/विवादित-आदेश तालिका · प्रकरण के संक्षिप्त तथ्य + जमानत के आधार (खण्ड-शीर्षक) · '
        'द्विभाषी · नीचे: सत्र §483 (हिन्दी+English), मजिस्ट्रेट §480, उच्च न्यायालय §483 (+ पृथक शपथ पत्र), '
        'अग्रिम §482 — प्रत्येक का अपना framing। reviewed: false.'
    )
    return doc_page(
        [render_hi(SAMPLE_SESSIONS), render_en(SAMPLE_SESSIONS),
         render_hi(SAMPLE_MAGISTRATE),
         render_hi(SAMPLE_HC), render_affidavit_hi(SAMPLE_HC),
         render_hi(SAMPLE_ANTICIPATORY)],
        banner=banner)
