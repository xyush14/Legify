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
  /* fact-grounding flag: a concrete detail in the draft that is NOT in what the
     advocate provided (may be auto-invented). Amber highlight on screen so the
     lawyer catches it at a glance; stays as an underline in print so a filed copy
     never silently carries an unverified fact. */
  mark.fab{background:#fff2c2;color:inherit;border-bottom:1.5px solid #d99a00;
    padding:0 1px;border-radius:2px;cursor:help}
  @media print{mark.fab{background:transparent;border-bottom:1px solid #999}}
  /* ---- mirrored draft (reference-matched) — generic court-format blocks ----
     The mr-* renderer reproduces an UPLOADED filed document's layout: recital-first
     cause-titles, indented party blocks with the designation pinned to the right
     edge, lettered prayer sub-clauses, companion pages. Kept separate from the
     canonical hdr- and cb- house format on purpose. */
  .mr-serif{font-family:'Times New Roman','Liberation Serif',Georgia,serif}
  .mr-center{text-align:center;margin:0 0 8pt;line-height:1.5}
  .mr-b{font-weight:700}
  .mr-u{text-decoration:underline;text-underline-offset:2px}
  .mr-label{font-weight:700;text-decoration:underline;text-underline-offset:2px;margin:14pt 0 8pt}
  .mr-recital{margin:0 0 10pt 38mm;font-weight:700;text-align:justify;line-height:1.65}
  .mr-party{margin:0 0 9pt 38mm;line-height:1.6}
  .mr-party .mr-desig{text-align:right;margin-top:2pt;font-weight:700}
  .mr-versus{text-align:center;font-weight:700;margin:10pt 0}
  .mr-num{position:relative;padding-left:26pt;margin:0 0 9pt;text-align:justify;line-height:1.65}
  .mr-num>.n{position:absolute;left:0;top:0;font-weight:600}
  .mr-item{position:relative;padding-left:36pt;margin:0 0 8pt;text-align:justify;line-height:1.65}
  .mr-item>.n{position:absolute;left:10pt;top:0}
  .mr-head{text-align:center;font-weight:700;text-decoration:underline;text-underline-offset:2px;
    margin:16pt 0 10pt;letter-spacing:.05em}
  .mr-text{margin:0 0 9pt;text-align:justify;line-height:1.65}
  .mr-right{text-align:right;margin:14pt 0 9pt}
  .mr-sig{display:flex;justify-content:space-between;align-items:flex-end;margin:22pt 0 8pt;white-space:pre-line}
  .mr-sig .r{text-align:center}
  .mr-break{border-top:1px dashed #c4c0b6;margin:28pt -6pt 26pt}
  .mr-table{width:100%;border-collapse:collapse;margin:8pt 0 12pt;font-size:12pt}
  .mr-table th,.mr-table td{border:1px solid #333;padding:4pt 6pt;text-align:left;vertical-align:top}
  /* letterhead row (advocate name left, office/mobile right) + separator rules —
     mirrors the two-column top of a real filed letterhead (e.g. जवाब सूचना पत्र) */
  .mr-cols{display:flex;justify-content:space-between;gap:18pt;margin:0 0 8pt;white-space:pre-line;line-height:1.5}
  .mr-cols .l{font-weight:700}
  .mr-cols .r{text-align:left;max-width:55%}
  .mr-rule{margin:6pt 0 10pt}
  .mr-rule-single{border-top:1.5pt solid #000}
  .mr-rule-double{border-top:3.5pt double #000}
  .mr-rule-dashed{border-top:1.5pt dashed #000}
"""

# Print fidelity: the on-screen 1.00" margins live as PADDING on the .doc-a4 card,
# which a printer applies once — page 2+ would start at the paper edge. In print we
# strip the card and let @page put the 1.00" margins on EVERY sheet, add page-break
# hygiene (no para split mid-page, headings keep their content), and drop the app
# chrome so the printout is the document alone.
PRINT_CSS = """
  @page{size:A4;margin:25.4mm}
  @media print{
    body{background:#fff !important;padding:0 !important}
    .rb{display:none !important}
    .doc-a4{width:auto;min-height:0;margin:0;padding:0;box-shadow:none}
    .doc-a4+.doc-a4{page-break-before:always}
    .cb-paras>li,.mr-num,.mr-item,.mr-party,.mr-recital,.cb-relief{break-inside:avoid}
    .cb-sig,.mr-sig{break-inside:avoid}
    .cb-head,.mr-head,.cb-block-label,.mr-label{break-after:avoid}
    .mr-break{border:0;margin:0;height:0;page-break-after:always}
  }
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
# PAN-INDIA court-name composition — Headnote is nationwide, not MP-only.
# level + city/district + STATE → the cause-title for the matter's OWN forum.
# The state picks the correct High Court (all 25); the district/city picks the
# HC bench where one exists. Nothing defaults to MP: an unknown state/city leaves
# a blank placeholder (a wrong forum on a filing is far worse than a blank one).
# ---------------------------------------------------------------------------
# The 25 High Courts. Each: Hindi + English NAME (no seat baked in), principal
# seat (hi/en bare city), a `bw` (bench word: Bench / Wing / Circuit Bench), and
# benches keyed by lowercased city/district/state tokens → bare seat city (hi,en).
# The cause-title is assembled in _compose_hc so phrasing is uniform and correct
# ("In the High Court of <Name> at <Seat>" / "…, <Bench> Bench").
_HIGH_COURTS = {
    "allahabad": {"hi": "इलाहाबाद", "en": "Allahabad", "seat": ("इलाहाबाद", "Allahabad"),
        "benches": {"lucknow": ("लखनऊ", "Lucknow"), "लखनऊ": ("लखनऊ", "Lucknow")}},
    "andhra": {"hi": "आन्ध्र प्रदेश", "en": "Andhra Pradesh", "seat": ("अमरावती", "Amaravati"), "benches": {}},
    "bombay": {"hi": "बम्बई", "en": "Bombay", "seat": ("मुम्बई", "Bombay"),
        "benches": {"nagpur": ("नागपुर", "Nagpur"), "नागपुर": ("नागपुर", "Nagpur"),
                    "aurangabad": ("औरंगाबाद", "Aurangabad"),
                    "chhatrapati sambhajinagar": ("औरंगाबाद", "Aurangabad"),
                    "goa": ("पणजी", "Panaji"), "panaji": ("पणजी", "Panaji"), "गोवा": ("पणजी", "Panaji")}},
    "calcutta": {"hi": "कलकत्ता", "en": "Calcutta", "seat": ("कलकत्ता", "Calcutta"),
        "bw": ("परिपथ पीठ", "Circuit Bench"),
        "benches": {"port blair": ("पोर्ट ब्लेयर", "Port Blair"), "jalpaiguri": ("जलपाईगुड़ी", "Jalpaiguri")}},
    "chhattisgarh": {"hi": "छत्तीसगढ़", "en": "Chhattisgarh", "seat": ("बिलासपुर", "Bilaspur"), "benches": {}},
    "delhi": {"hi": "दिल्ली", "en": "Delhi", "seat": ("नई दिल्ली", "New Delhi"), "benches": {}},
    "gauhati": {"hi": "गुवाहाटी", "en": "Gauhati", "seat": ("गुवाहाटी", "Guwahati"),
        "benches": {"nagaland": ("कोहिमा", "Kohima"), "kohima": ("कोहिमा", "Kohima"),
                    "mizoram": ("आइजोल", "Aizawl"), "aizawl": ("आइजोल", "Aizawl"),
                    "arunachal": ("ईटानगर", "Itanagar"), "itanagar": ("ईटानगर", "Itanagar"),
                    "arunachal pradesh": ("ईटानगर", "Itanagar")}},
    "gujarat": {"hi": "गुजरात", "en": "Gujarat", "seat": ("अहमदाबाद", "Ahmedabad"), "benches": {}},
    "himachal": {"hi": "हिमाचल प्रदेश", "en": "Himachal Pradesh", "seat": ("शिमला", "Shimla"), "benches": {}},
    "jk": {"hi": "जम्मू-कश्मीर एवं लद्दाख", "en": "Jammu & Kashmir and Ladakh", "seat": ("श्रीनगर", "Srinagar"),
        "bw": ("विंग", "Wing"),
        "benches": {"jammu": ("जम्मू", "Jammu"), "जम्मू": ("जम्मू", "Jammu"),
                    "ladakh": ("लेह", "Leh"), "leh": ("लेह", "Leh"), "लद्दाख": ("लेह", "Leh")}},
    "jharkhand": {"hi": "झारखण्ड", "en": "Jharkhand", "seat": ("राँची", "Ranchi"), "benches": {}},
    "karnataka": {"hi": "कर्नाटक", "en": "Karnataka", "seat": ("बेंगलुरु", "Bengaluru"),
        "benches": {"dharwad": ("धारवाड़", "Dharwad"), "hubli": ("धारवाड़", "Dharwad"),
                    "kalaburagi": ("कलबुर्गी", "Kalaburagi"), "gulbarga": ("कलबुर्गी", "Kalaburagi")}},
    "kerala": {"hi": "केरल", "en": "Kerala", "seat": ("एर्नाकुलम", "Ernakulam"), "benches": {}},
    "mp": {"hi": "मध्यप्रदेश", "en": "Madhya Pradesh", "seat": ("जबलपुर", "Jabalpur"),
        "benches": {"indore": ("इन्दौर", "Indore"), "इन्दौर": ("इन्दौर", "Indore"), "इंदौर": ("इन्दौर", "Indore"),
                    "ujjain": ("इन्दौर", "Indore"), "उज्जैन": ("इन्दौर", "Indore"), "dewas": ("इन्दौर", "Indore"),
                    "dhar": ("इन्दौर", "Indore"), "धार": ("इन्दौर", "Indore"), "ratlam": ("इन्दौर", "Indore"),
                    "रतलाम": ("इन्दौर", "Indore"), "khargone": ("इन्दौर", "Indore"), "khandwa": ("इन्दौर", "Indore"),
                    "gwalior": ("ग्वालियर", "Gwalior"), "ग्वालियर": ("ग्वालियर", "Gwalior"),
                    "bhind": ("ग्वालियर", "Gwalior"), "भिण्ड": ("ग्वालियर", "Gwalior"),
                    "morena": ("ग्वालियर", "Gwalior"), "मुरैना": ("ग्वालियर", "Gwalior"),
                    "datia": ("ग्वालियर", "Gwalior"), "दतिया": ("ग्वालियर", "Gwalior"),
                    "shivpuri": ("ग्वालियर", "Gwalior"), "शिवपुरी": ("ग्वालियर", "Gwalior"),
                    "guna": ("ग्वालियर", "Gwalior"), "गुना": ("ग्वालियर", "Gwalior")}},
    "madras": {"hi": "मद्रास", "en": "Madras", "seat": ("मद्रास", "Madras"),
        "benches": {"madurai": ("मदुरै", "Madurai"), "मदुरै": ("मदुरै", "Madurai")}},
    "manipur": {"hi": "मणिपुर", "en": "Manipur", "seat": ("इम्फाल", "Imphal"), "benches": {}},
    "meghalaya": {"hi": "मेघालय", "en": "Meghalaya", "seat": ("शिलांग", "Shillong"), "benches": {}},
    "orissa": {"hi": "उड़ीसा", "en": "Orissa", "seat": ("कटक", "Cuttack"), "benches": {}},
    "patna": {"hi": "पटना", "en": "Patna", "seat": ("पटना", "Patna"), "benches": {}},
    "ph": {"hi": "पंजाब एवं हरियाणा", "en": "Punjab and Haryana", "seat": ("चण्डीगढ़", "Chandigarh"), "benches": {}},
    "rajasthan": {"hi": "राजस्थान", "en": "Rajasthan", "seat": ("जोधपुर", "Jodhpur"),
        "benches": {"jaipur": ("जयपुर", "Jaipur"), "जयपुर": ("जयपुर", "Jaipur")}},
    "sikkim": {"hi": "सिक्किम", "en": "Sikkim", "seat": ("गंगटोक", "Gangtok"), "benches": {}},
    "telangana": {"hi": "तेलंगाना", "en": "Telangana", "seat": ("हैदराबाद", "Hyderabad"), "benches": {}},
    "tripura": {"hi": "त्रिपुरा", "en": "Tripura", "seat": ("अगरतला", "Agartala"), "benches": {}},
    "uttarakhand": {"hi": "उत्तराखण्ड", "en": "Uttarakhand", "seat": ("नैनीताल", "Nainital"), "benches": {}},
}
# every state / UT / common abbreviation → its High Court key (lowercased lookup)
_STATE_TO_HC = {
    "uttar pradesh": "allahabad", "up": "allahabad", "उत्तर प्रदेश": "allahabad", "उ.प्र.": "allahabad",
    "andhra pradesh": "andhra", "ap": "andhra", "आन्ध्र प्रदेश": "andhra", "आंध्र प्रदेश": "andhra",
    "maharashtra": "bombay", "महाराष्ट्र": "bombay", "goa": "bombay", "गोवा": "bombay",
    "dadra and nagar haveli": "bombay", "daman and diu": "bombay",
    "west bengal": "calcutta", "wb": "calcutta", "पश्चिम बंगाल": "calcutta",
    "andaman and nicobar": "calcutta", "andaman & nicobar": "calcutta",
    "chhattisgarh": "chhattisgarh", "cg": "chhattisgarh", "छत्तीसगढ़": "chhattisgarh", "छ.ग.": "chhattisgarh",
    "delhi": "delhi", "nct of delhi": "delhi", "new delhi": "delhi", "दिल्ली": "delhi",
    "assam": "gauhati", "असम": "gauhati", "nagaland": "gauhati", "नागालैंड": "gauhati",
    "mizoram": "gauhati", "मिज़ोरम": "gauhati", "arunachal pradesh": "gauhati", "अरुणाचल प्रदेश": "gauhati",
    "gujarat": "gujarat", "गुजरात": "gujarat",
    "himachal pradesh": "himachal", "hp": "himachal", "हिमाचल प्रदेश": "himachal", "हि.प्र.": "himachal",
    "jammu and kashmir": "jk", "jammu & kashmir": "jk", "j&k": "jk", "jk": "jk", "ladakh": "jk",
    "जम्मू और कश्मीर": "jk", "जम्मू-कश्मीर": "jk", "लद्दाख": "jk",
    "jharkhand": "jharkhand", "झारखण्ड": "jharkhand", "झारखंड": "jharkhand",
    "karnataka": "karnataka", "कर्नाटक": "karnataka",
    "kerala": "kerala", "lakshadweep": "kerala", "केरल": "kerala",
    "madhya pradesh": "mp", "mp": "mp", "m.p.": "mp", "मध्य प्रदेश": "mp", "मध्यप्रदेश": "mp", "म.प्र.": "mp",
    "tamil nadu": "madras", "tn": "madras", "तमिलनाडु": "madras", "puducherry": "madras",
    "pondicherry": "madras", "पुदुच्चेरी": "madras",
    "manipur": "manipur", "मणिपुर": "manipur",
    "meghalaya": "meghalaya", "मेघालय": "meghalaya",
    "odisha": "orissa", "orissa": "orissa", "ओडिशा": "orissa", "उड़ीसा": "orissa",
    "bihar": "patna", "बिहार": "patna",
    "punjab": "ph", "haryana": "ph", "chandigarh": "ph", "पंजाब": "ph", "हरियाणा": "ph", "चण्डीगढ़": "ph",
    "rajasthan": "rajasthan", "राजस्थान": "rajasthan", "raj": "rajasthan",
    "sikkim": "sikkim", "सिक्किम": "sikkim",
    "telangana": "telangana", "तेलंगाना": "telangana", "तेलंगाणा": "telangana",
    "tripura": "tripura", "त्रिपुरा": "tripura",
    "uttarakhand": "uttarakhand", "uk": "uttarakhand", "उत्तराखण्ड": "uttarakhand", "उत्तराखंड": "uttarakhand",
}


def _hc_record(state="", city=""):
    """Resolve (state, city) → an HC record, or None if the state is unknown.
    State wins; a bench-city (e.g. 'Lucknow') can also pin the HC when state is blank."""
    for tok in ((state or "").strip().lower(), (city or "").strip().lower()):
        if tok and tok in _STATE_TO_HC:
            return _HIGH_COURTS[_STATE_TO_HC[tok]]
    # a bench/city name alone (Lucknow, Nagpur, Madurai…) can identify the HC
    probe = (city or "").strip().lower()
    if probe:
        for rec in _HIGH_COURTS.values():
            if probe in rec["benches"]:
                return rec
    return None


def _hc_seat(rec, city="", state="", lang="hi"):
    """Pick the localized seat city for this HC from the city/district/state, and
    whether it is a BENCH (vs the principal seat). Returns (place, is_bench)."""
    for tok in ((city or "").strip().lower(), (state or "").strip().lower()):
        if tok and tok in rec["benches"]:
            return rec["benches"][tok][0 if lang == "hi" else 1], True
    return (rec["seat"][0] if lang == "hi" else rec["seat"][1]), False


def _compose_hc(city="", state="", bench=None, lang="hi"):
    """Full High-Court cause-title for the matter's OWN state, phrased uniformly:
    'In the High Court of <Name> at <PrincipalSeat>' / '…, <Bench> Bench'. Blank
    placeholders (never an MP guess) when the state/court cannot be resolved."""
    rec = _hc_record(state, city)
    if rec is None:                                   # unknown state → blank, don't guess
        st = (state or "").strip() or "__________"
        seat = bench or "__________"
        return (f"माननीय उच्च न्यायालय {st}, {seat}" if lang == "hi"
                else f"In the High Court of {st} at {seat}")
    if bench:                                         # explicit override wins
        return (f"माननीय उच्च न्यायालय {rec['hi']}, {bench}" if lang == "hi"
                else f"In the High Court of {rec['en']} at {bench}")
    place, is_bench = _hc_seat(rec, city, state, lang)
    bw_hi, bw_en = rec.get("bw", ("खण्डपीठ", "Bench"))
    if lang == "hi":
        return (f"माननीय उच्च न्यायालय {rec['hi']} {bw_hi} {place}" if is_bench
                else f"माननीय उच्च न्यायालय {rec['hi']}, {place}")
    if is_bench:
        # "Circuit Bench"/"Wing" read as "… , Circuit Bench at Port Blair"; a plain
        # "Bench" reads "… at Bombay, Nagpur Bench" (principal named, then the bench).
        if bw_en == "Bench":
            return f"In the High Court of {rec['en']} at {rec['seat'][1]}, {place} Bench"
        return f"In the High Court of {rec['en']} at {rec['seat'][1]}, {bw_en} at {place}"
    return f"In the High Court of {rec['en']} at {place}"


_COURT_TPL = {
    "magistrate":         "न्यायालय माननीय न्यायिक दण्डाधिकारी प्रथम श्रेणी महोदय, {city} ({state})",
    "cjm":                "न्यायालय माननीय मुख्य न्यायिक दण्डाधिकारी महोदय, {city} ({state})",
    "sessions":           "न्यायालय माननीय सत्र न्यायाधीश महोदय, {city} ({state})",
    "principal_sessions": "न्यायालय माननीय प्रधान सत्र न्यायाधीश महोदय, {city} ({state})",
    "family":             "न्यायालय माननीय प्रधान न्यायाधीश महोदय, कुटुम्ब न्यायालय, {city} ({state})",
    "civil":              "न्यायालय माननीय व्यवहार न्यायाधीश महोदय वर्ग-____, {city} ({state})",
    "district_judge":     "न्यायालय माननीय जिला न्यायाधीश महोदय, {city} ({state})",
    "consumer":           "जिला उपभोक्ता विवाद प्रतितोष आयोग, {city} ({state})",
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
}


def compose_court_name(level, city="", state="", bench=None, lang="hi"):
    """level (magistrate/cjm/sessions/principal_sessions/family/civil/district_judge/consumer/hc)
    + city/district + STATE → the forum's cause-title, PAN-INDIA. The state selects the
    correct High Court (all 25) and the district selects its bench. Nothing defaults to
    MP — an unknown state/city leaves a blank placeholder the lawyer fills. Editable after."""
    if level == "hc":
        return _compose_hc(city, state, bench, lang)
    tpls = _COURT_TPL if lang == "hi" else _COURT_TPL_EN
    state = (state or "").strip() or ("________" if lang == "hi" else "________")
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


def doc_page(docs, banner: str = "", title: str = "") -> str:
    """Standalone page rendering one or more FULL documents (header + body) on
    A4 sheets. Pass [hi_html, en_html] for a bilingual review. `title` becomes the
    document title — it is what the browser's print header shows, so pass the
    draft's own name rather than app chrome."""
    if isinstance(docs, str):
        docs = [docs]
    sheets = "".join(f'<div class="doc-a4">{d}</div>' for d in docs)
    return (
        '<!doctype html><html lang="hi"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f'<title>{_esc(title) or "Headnote draft — review"}</title>'
        '<link rel="preconnect" href="https://fonts.googleapis.com">'
        '<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+Devanagari:wght@400;700&display=swap" rel="stylesheet">'
        '<style>*{box-sizing:border-box}body{margin:0;background:#cdccc6;padding:24px 0}'
        + HEADER_CSS + PRINT_CSS +
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
