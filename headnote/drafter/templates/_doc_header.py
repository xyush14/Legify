"""Canonical document header — PIXEL-EXACT reproduction of Vishnu ji's filed
top-section (decoded from legal_petition_template.docx).

THE RULE (Ayush): every application reproduces THIS header exactly — same page,
font, sizes, alignment, spacing, underline pattern and the tab-aligned party
block. Only the variables change. The point-wise body starts after it. Getting
this header pixel-perfect is "60% of the win", so it is ONE shared component,
never re-typed per template.

Exact spec decoded from the .docx (ground truth):
  PAGE   A4 (210×297 mm / 8.27"×11.69") portrait; margins 1.00" (1440 tw) all sides.
  FONT   Mangal (Unicode Devanagari) throughout.
  TAB    party descriptor column = explicit LEFT tab at 4600 tw = 3.194" = 81.1 mm
         from the left margin (this is the wide gap before the descriptor block).
  TYPE   court name 18pt BOLD underline; everything else 13pt.
  LINES  (align / size / weight / underline / space-after in pt):
    side-line   center / 13 / normal / underline / 2
    court name  CENTER / 18 / BOLD   / underline / 3
    case code   CENTER / 13 / normal / —         / 5
    petitioner  label "<X> ——" underline + TAB→81.1mm + descriptor lines;
                place-values underlined; block space-after 4
    विरुद्ध     centered OVER the descriptor/name column (sits between the two
                party NAME blocks, not page-centered) / 13 / normal / 4
    respondent  same as petitioner; block space-after 6
    title line  CENTER / 13 / normal / underline / 0

NB on fidelity: a browser cannot be byte-identical to Word; the TRUE pixel-exact
filing output is produced by FILLING THE .docx itself (placeholder → value). This
HTML renderer is the faithful on-screen mirror for review + the structural spec
that the .docx-fill pipeline implements. Content width = 210 − 2×25.4 = 159.2 mm;
descriptor tab column at 81.1 mm.
"""
from __future__ import annotations

from typing import Optional


def _esc(s: Optional[str]) -> str:
    if s is None:
        return ""
    # NOTE: descriptor lines may legitimately contain <u>…</u> (place-values),
    # so callers pass pre-marked HTML for those; plain fields are escaped here.
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# Pixel-exact CSS. Units in mm/pt to mirror the .docx geometry 1:1.
HEADER_CSS = """
  .doc-a4{background:#fff;width:210mm;min-height:297mm;margin:0 auto;
    padding:25.4mm;            /* 1.00in margins all sides */
    box-shadow:0 1px 3px rgba(0,0,0,.06),0 10px 30px rgba(0,0,0,.08);
    font-family:'Mangal','Noto Sans Devanagari','Kokila',sans-serif;
    font-size:13pt;line-height:1.45;color:#000;box-sizing:border-box}
  .doc-a4 u{text-decoration:underline;text-underline-offset:2px}
  /* a little breathing room between header blocks (Ayush — "keep lil space") */
  .hdr-side{text-align:center;text-decoration:underline;text-underline-offset:2px;margin:0 0 7pt}
  .hdr-court{text-align:center;font-size:18pt;font-weight:700;text-decoration:underline;
    text-underline-offset:3px;margin:0 0 9pt;line-height:1.3;white-space:nowrap}
  .hdr-case{text-align:center;margin:0 0 15pt}
  /* party block: label column = 81.1mm tab; descriptor in the remaining width */
  .hdr-party{display:grid;grid-template-columns:81.1mm 1fr;align-items:start;margin:0}
  .hdr-party--p{margin-bottom:11pt}
  .hdr-party--r{margin-bottom:15pt}
  .hdr-party-label{text-decoration:underline;text-underline-offset:2px;white-space:nowrap}
  .hdr-party-desc{margin:0;line-height:1.55}
  /* विरुद्ध: centered OVER the name column (between the two party name blocks) */
  .hdr-versus{display:grid;grid-template-columns:81.1mm 1fr;margin:5pt 0 11pt}
  .hdr-versus .hv{text-align:center}
  .hdr-title{text-align:center;text-decoration:underline;text-underline-offset:2px;margin:0 0 9pt}
  /* ---- body: the point-wise application under the header ---- */
  .doc-body{margin-top:4pt}
  .cb-prelude{margin:0 0 7pt;text-align:justify}
  .cb-paras{margin:0;padding-left:0;counter-reset:cb;list-style:none}
  .cb-paras>li{counter-increment:cb;position:relative;padding-left:26pt;margin-bottom:9pt;text-align:justify;line-height:1.55}
  .cb-paras>li::before{content:counter(cb) ".";position:absolute;left:0;top:0;font-weight:600;width:20pt}
  /* in-list SECTION header (प्रकरण के संक्षिप्त तथ्य / जमानत के आधार) — same typography
     as other templates' block labels; no number, doesn't advance the counter */
  .cb-paras>li.cb-head{counter-increment:none;list-style:none;padding-left:0;margin:13pt 0 7pt;
    font-weight:700;text-decoration:underline;text-underline-offset:2px}
  .cb-paras>li.cb-head::before{content:""}
  .cb-prayer{margin:11pt 0 0;text-align:justify;line-height:1.55}
  .cb-block-label{font-weight:700;text-decoration:underline;text-underline-offset:2px;margin:12pt 0 6pt;text-align:center}
  /* per-section relief block (DV §17-22): inline bold-underline lead + justified text */
  .cb-relief{margin:0 0 8pt;text-align:justify;line-height:1.55;padding-left:14pt}
  .cb-sig{display:flex;justify-content:space-between;align-items:flex-start;margin-top:18pt}
  .cb-sig .r{text-align:center}
  .cb-witlist{margin:0;padding-left:22pt}
  .cb-witlist li{margin-bottom:5pt;text-align:justify;line-height:1.5}
  .cb-note{margin-top:12pt;font-size:11pt;color:#666;border-top:1px dashed #c4c0b6;padding-top:8pt}
  .cb-table{width:100%;border-collapse:collapse;margin:6pt 0 10pt;font-size:11.5pt}
  .cb-table th,.cb-table td{border:1px solid #333;padding:3pt 6pt;text-align:left}
  /* empty-field placeholder = field-name, subtly marked as a fill-in (dotted underline, no fill) */
  .ph{color:#9a958a;font-style:normal;border-bottom:1px dotted #c4bdad}
"""

# Court-name auto-fit: keep the dominant line on ONE line by shrinking it precisely
# to the content width. The Python start-size (in render_header) gets it close and is
# the deterministic value for the .docx; this nails it pixel-exact in the HTML preview.
_FIT_SCRIPT = (
    '<script>(function(){'
    'function fit(el){var w=el.clientWidth;if(!w)return;'
    'var fs=parseFloat(getComputedStyle(el).fontSize);var g=0;'
    'while(el.scrollWidth>w+0.5&&fs>13&&g<160){fs-=0.5;el.style.fontSize=fs+"px";g++;}}'
    'function run(){var n=document.querySelectorAll(".hdr-court");for(var i=0;i<n.length;i++)fit(n[i]);}'
    'if(document.readyState!=="loading")run();else document.addEventListener("DOMContentLoaded",run);'
    'window.addEventListener("load",run);})();</script>'
)


# ---------------------------------------------------------------------------
# Court-name composition — level + city/district → the cause-title per forum.
# Device geolocation only needs to supply the CITY/DISTRICT; the cause-title is
# then composed deterministically (and stays editable — lawyers file across
# districts). HC maps the district to its bench (Gwalior / Indore / Jabalpur).
# ---------------------------------------------------------------------------
_MP_HC_BENCH = {  # MP district → High Court bench (else Jabalpur principal seat)
    # Gwalior bench
    "ग्वालियर": "ग्वालियर", "भिण्ड": "ग्वालियर", "मुरैना": "ग्वालियर", "श्योपुर": "ग्वालियर",
    "दतिया": "ग्वालियर", "शिवपुरी": "ग्वालियर", "गुना": "ग्वालियर", "अशोकनगर": "ग्वालियर",
    # Indore bench
    "इन्दौर": "इन्दौर", "उज्जैन": "इन्दौर", "देवास": "इन्दौर", "धार": "इन्दौर", "झाबुआ": "इन्दौर",
    "अलीराजपुर": "इन्दौर", "खरगोन": "इन्दौर", "बड़वानी": "इन्दौर", "खण्डवा": "इन्दौर",
    "बुरहानपुर": "इन्दौर", "रतलाम": "इन्दौर", "मन्दसौर": "इन्दौर", "नीमच": "इन्दौर",
    "आगर-मालवा": "इन्दौर", "शाजापुर": "इन्दौर",
}
# Bench-seat name in BOTH scripts, keyed by every spelling we might receive
# (Hindi, Latin, nukta/no-nukta) — so "Indore", "इन्दौर" and "इंदौर" all resolve
# to the same seat, rendered in the document's own language.
_HC_SEAT_ALIASES = {
    "gwalior": ("ग्वालियर", "Gwalior"), "ग्वालियर": ("ग्वालियर", "Gwalior"),
    "indore": ("इन्दौर", "Indore"), "इन्दौर": ("इन्दौर", "Indore"), "इंदौर": ("इन्दौर", "Indore"),
    "jabalpur": ("जबलपुर", "Jabalpur"), "जबलपुर": ("जबलपुर", "Jabalpur"),
}


def _hc_bench(city="", bench=None, lang="hi"):
    """(district or seat) → the MP-HC bench cause-title token, in `lang`.
    Returns "" when NO city is given — the caller then shows a blank placeholder
    instead of guessing a bench from a default/location (a wrong bench on a
    filing is far worse than a blank one the lawyer fills in)."""
    if bench:
        return bench
    raw = (city or "").strip()
    if not raw:
        return ""                                   # no location → leave blank
    seat = _MP_HC_BENCH.get(raw)                    # known district → its Hindi seat
    alias = _HC_SEAT_ALIASES.get(seat) if seat else (
        _HC_SEAT_ALIASES.get(raw) or _HC_SEAT_ALIASES.get(raw.lower()))
    if alias:
        return alias[0] if lang == "hi" else alias[1]
    # any other MP district falls under the principal seat at Jabalpur
    return "जबलपुर" if lang == "hi" else "Jabalpur"
_COURT_TPL = {
    "magistrate":         "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, {city} ({state})",
    "cjm":                "न्यायालय माननीय मुख्य न्यायिक दण्डाधिकारी महोदय, {city} ({state})",
    "sessions":           "न्यायालय माननीय सत्र न्यायाधीश महोदय, {city} ({state})",
    "principal_sessions": "न्यायालय माननीय प्रधान सत्र न्यायाधीश महोदय, {city} ({state})",
    "family":             "न्यायालय माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय, {city} ({state})",
    "civil":              "न्यायालय माननीय व्यवहार न्यायाधीश महोदय वर्ग-____, {city} ({state})",
    "district_judge":     "न्यायालय माननीय जिला न्यायाधीश महोदय, {city} ({state})",
    "consumer":           "जिला उपभोक्ता विवाद प्रतितोष आयोग, {city} ({state})",
    "hc":                 "माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ {bench}",
}
_COURT_TPL_EN = {
    "magistrate":         "Court of the Judicial Magistrate First Class, {city} ({state})",
    "cjm":                "Court of the Chief Judicial Magistrate, {city} ({state})",
    "sessions":           "Court of the Sessions Judge, {city} ({state})",
    "principal_sessions": "Court of the Principal Sessions Judge, {city} ({state})",
    "family":             "Court of the Principal Judge, Family Court, {city} ({state})",
    "civil":              "Court of the Civil Judge, Class ____, {city} ({state})",
    "district_judge":     "Court of the District Judge, {city} ({state})",
    "consumer":           "District Consumer Disputes Redressal Commission, {city} ({state})",
    "hc":                 "High Court of Madhya Pradesh, Bench at {bench}",
}


def compose_court_name(level, city="", state="", bench=None, lang="hi"):
    """level (magistrate/cjm/sessions/principal_sessions/family/civil/district_judge/consumer/hc)
    + city/district → the forum's cause-title. For HC, the district picks the bench. Editable after."""
    tpls = _COURT_TPL if lang == "hi" else _COURT_TPL_EN
    if level == "hc":
        b = _hc_bench(city, bench, lang)
        if not b:
            b = "__________"          # location left blank → keep the bench blank
        return tpls["hc"].format(bench=b)
    state = state or ("म.प्र." if lang == "hi" else "M.P.")
    city = (city or "").strip() or ("............" if lang == "hi" else "............")
    return tpls.get(level, tpls["sessions"]).format(city=city, state=state)


# Device-location hook for the live form (HTTPS + user permission). Reverse-geocodes
# the device's coordinates to a district, fills the court_city field, and recomposes
# the court name. Provided here so the form UI can drop it in. Not used by the static
# review render (which has no form / no geolocation permission).
GEO_SNIPPET = (
    '<script>'
    'async function headnoteDetectCourtCity(onCity){'
    ' if(!navigator.geolocation)return;'
    ' navigator.geolocation.getCurrentPosition(async function(p){'
    '  try{'
    '   var u="https://nominatim.openstreetmap.org/reverse?format=json&zoom=10&lat="'
    '     +p.coords.latitude+"&lon="+p.coords.longitude;'
    '   var a=(await (await fetch(u,{headers:{"Accept-Language":"hi,en"}})).json()).address||{};'
    '   var city=a.state_district||a.county||a.city||a.town||a.district||"";'
    '   city=city.replace(/ District| जिला/gi,"").trim();'
    '   if(city)onCity(city,a.state||"");'  # caller fills court_city → recompose court_name
    '  }catch(e){}'
    ' });'
    '}'
    '</script>'
)


def render_header(d: dict) -> str:
    """Render the canonical top-section. `d` keys (already localised strings;
    descriptor lines may contain <u>…</u> for underlined place-values):
      side_label, court_name, case_code, case_number, case_year,
      applicant_label, applicant_desc (list[str]),
      respondent_label, respondent_desc (list[str]),
      versus, title_line
    """
    d = d or {}
    side = d.get("side_label") or ""
    court = d.get("court_name") or ""
    case_code = d.get("case_code") or ""
    case_no = d.get("case_number") or ""
    case_year = d.get("case_year") or ""
    case_suffix = d.get("case_suffix") or ""   # subordinate type label: परिवाद पत्र / मु.फौ. / आपराधिक अपील / घरेलू हिंसा …
    a_label = d.get("applicant_label") or "आवेदक"
    a_desc = d.get("applicant_desc") or []
    r_label = d.get("respondent_label") or "अनावेदक"
    r_desc = d.get("respondent_desc") or []
    versus = d.get("versus") or "विरुद्ध"
    title = d.get("title_line") or ""

    # case line: "<code>–   <no>   / <year> [suffix]"  (wide gap mirrors the filed form)
    no_part = _esc(case_no) if case_no else "&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;"
    case_line = f"{_esc(case_code)}– {no_part} / {_esc(case_year)}"
    if case_suffix:
        case_line += f" {_esc(case_suffix)}"

    def party(label, desc_lines, cls):
        body = "<br>".join(desc_lines) if desc_lines else ""
        return (
            f'<div class="hdr-party hdr-party--{cls}">'
            f'<div class="hdr-party-label">{_esc(label)} ——</div>'
            f'<div class="hdr-party-desc">{body}</div></div>'
        )

    out = ['<div class="doc-hdr">']
    if side:  # complaints (§138 परिवाद) etc. carry no "X की ओर से" side-line
        out.append(f'<div class="hdr-side">{_esc(side)}</div>')
    # court name = the dominant line, MUST sit on ONE line. Start size scales down
    # by length (deterministic / carries to the .docx); the JS auto-fit in the page
    # then shrinks precisely to the content width. Floor 12pt keeps it prominent.
    court_fs = 18.0 if len(court) <= 40 else max(12.0, round(18.0 * 40.0 / max(len(court), 1), 1))
    out.append(f'<div class="hdr-court" style="font-size:{court_fs}pt">{_esc(court)}</div>')
    out.append(f'<div class="hdr-case">{case_line}</div>')
    out.append(party(a_label, a_desc, "p"))
    out.append(f'<div class="hdr-versus"><span></span><span class="hv">{_esc(versus)}</span></div>')
    out.append(party(r_label, r_desc, "r"))
    out.append(f'<div class="hdr-title">{_esc(title)}</div>')
    out.append('</div>')
    return "\n".join(out)


def demo_page(header_html: str, banner: str = "") -> str:
    """Standalone A4 page rendering a header (for pixel-mirror review)."""
    return (
        '<!doctype html><html lang="hi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Canonical header — pixel mirror</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;700&display=swap" rel="stylesheet">'
        '<style>*{box-sizing:border-box}body{margin:0;background:#cdccc6;padding:24px 0}'
        + HEADER_CSS +
        '.rb{max-width:210mm;margin:0 auto 16px;font-family:system-ui,sans-serif;font-size:12.5px;'
        'color:#3a3730;background:#fdf6e3;border:1px solid #e3d9bd;padding:8px 12px;border-radius:6px}'
        '</style></head><body>'
        + (f'<div class="rb">{banner}</div>' if banner else '')
        + f'<div class="doc-a4">{header_html}<p style="color:#b9b3a5;margin-top:14pt">[ … आवेदन यहाँ से बिंदुवार प्रारम्भ — point-wise body follows … ]</p></div>'
        + _FIT_SCRIPT +
        '</body></html>'
    )


def render_index(hdr: dict, items, lang: str = "hi") -> str:
    """The इन्डेक्स (Form-4) cover sheet that LEADS a High-Court filing bundle.
    `hdr` = a header dict (same keys as render_header — court_name, case_code,
    case_number, case_year, applicant_label/desc, respondent_label/desc, versus);
    its title_line is overridden to इन्डेक्स/INDEX. `items` = ordered list of
    {"hi","en","annexure"} rows (विवरण | एनेक्जर | पृष्ठ). No page numbers in the
    preview (filled at print) — mirrors his real index."""
    hi = lang == "hi"
    head = render_header({**hdr, "title_line": "इन्डेक्स" if hi else "INDEX"})
    th = ("क्र.", "विवरण", "एनेक्जर", "पृष्ठ") if hi else ("S.No.", "Particulars", "Annexure", "Page")
    rows = "".join(
        f'<tr><td style="text-align:center">{i + 1}.</td><td>{(it.get("hi") if hi else it.get("en")) or ""}</td>'
        f'<td style="text-align:center">{it.get("annexure", "") or ""}</td><td></td></tr>'
        for i, it in enumerate(items))
    table = (f'<table class="cb-table" style="margin-top:14pt"><tr>'
             f'<th style="width:10%">{th[0]}</th><th>{th[1]}</th>'
             f'<th style="width:16%">{th[2]}</th><th style="width:14%">{th[3]}</th></tr>{rows}</table>')
    return head + '<div class="doc-body">' + table + '</div>'


def doc_page(docs, banner: str = "") -> str:
    """Standalone page rendering one or more FULL documents (header + body) on
    A4 sheets. Pass [hi_html, en_html] for a bilingual review."""
    if isinstance(docs, str):
        docs = [docs]
    sheets = "".join(f'<div class="doc-a4">{d}</div>' for d in docs)
    return (
        '<!doctype html><html lang="hi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<title>Headnote draft — review</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;700&display=swap" rel="stylesheet">'
        '<style>*{box-sizing:border-box}body{margin:0;background:#cdccc6;padding:24px 0}'
        + HEADER_CSS +
        '.rb{max-width:210mm;margin:0 auto 16px;font-family:system-ui,sans-serif;font-size:12.5px;'
        'line-height:1.5;color:#3a3730;background:#fdf6e3;border:1px solid #e3d9bd;padding:8px 12px;border-radius:6px}'
        '.doc-a4{margin-bottom:24px}</style></head><body>'
        + (f'<div class="rb">{banner}</div>' if banner else '')
        + sheets + _FIT_SCRIPT +
        '</body></html>'
    )


# ---- the image example (Gopal Singh Kanjar §483 HC bail) — for verification ----
SAMPLE = {
    "side_label": "बन्दी की ओर से",
    "court_name": "माननीय उच्च न्यायालय मध्य प्रदेश खण्डपीठ ग्वालियर",
    "case_code": "एम.सी.आर.सी.", "case_number": "", "case_year": "2025",
    "applicant_label": "आवेदक",
    "applicant_desc": [
        "गोपाल सिंह कंजर पुत्र श्री अमर सिंह,",
        "आयु— 43 वर्ष, व्यवसाय— कृषि,",
        "निवासी— <u>बरसाने का डाडा, मोहना</u>",
        "जिला <u>ग्वालियर</u> (म.प्र.)",
    ],
    "respondent_label": "अनावेदक",
    "respondent_desc": [
        "म0प्र0 शासन द्वारा पुलिस थाना वृत्त",
        "आंतरिक क्षेत्र आबकरी पड़ाव जिला",
        "<u>ग्वालियर</u> (म0प्र0)",
    ],
    "versus": "विरुद्ध",
    "title_line": "द्वितीय जमानत आवेदन पत्र अन्तर्गत धारा 483 भारतीय नागरिक सुरक्षा संहिता",
}
