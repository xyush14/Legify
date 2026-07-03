"""Court-term glossary — Hindi → {Marathi, Bengali, Gujarati}.

This is the QUALITY BACKBONE of regional drafting. Generic machine translation
silently keeps Hindi legal words that read as *wrong* in another state's court
(e.g. Hindi धारा "section" must become Marathi कलम; अपराध must become गुन्हा).
The glossary pins the court-correct rendering for the highest-frequency terms so
the translator cannot drift on them.

Status of each column:
  * mr (Marathi)  — drafted; needs sign-off by a Maharashtra advocate.
  * bn (Bengali)  — core terms only; the rest fall through to the model.
  * gu (Gujarati) — core terms only; the rest fall through to the model.

A blank ("") means "no pinned term — let the model translate in context." Only
pin a cell once a practising advocate in that jurisdiction has confirmed it.
Every pinned cell is, in effect, pre-verified vocabulary the advocate review can
trust and skip.
"""
from __future__ import annotations

# term_hi : {lang: court_correct_term}
# Ordered roughly by how often it appears across the criminal templates.
TERMS: dict[str, dict[str, str]] = {
    # ---- connective / register ----
    "यह कि,":            {"mr": "हे की,", "bn": "", "gu": "કે,"},
    "माननीय न्यायालय":   {"mr": "माननीय न्यायालय", "bn": "মাননীয় আদালত", "gu": "નામદાર અદાલત"},
    "माननीय न्यायालय,":  {"mr": "माननीय न्यायालय,", "bn": "মাননীয় আদালত,", "gu": "નામદાર અદાલત,"},

    # ---- parties ----
    "प्रार्थी":          {"mr": "अर्जदार", "bn": "আবেদনকারী", "gu": "અરજદાર"},
    "प्रार्थीगण":        {"mr": "अर्जदारगण", "bn": "আবেদনকারীগণ", "gu": "અરજદારો"},
    "अभियुक्त":          {"mr": "आरोपी", "bn": "অভিযুক্ত", "gu": "આરોપી"},
    "अभियुक्तगण":        {"mr": "आरोपीगण", "bn": "অভিযুক্তগণ", "gu": "આરોપીઓ"},
    "अभियोगी":           {"mr": "अभियोग पक्ष", "bn": "রাষ্ট্রপক্ষ", "gu": "ફરિયાદ પક્ષ"},
    "फरियादी":           {"mr": "फिर्यादी", "bn": "ফরিয়াদি", "gu": "ફરિયાદી"},
    "फरियादिया":         {"mr": "फिर्यादी", "bn": "ফরিয়াদি", "gu": "ફરિયાદી"},

    # ---- offence / procedure ----
    "धारा":              {"mr": "कलम", "bn": "ধারা", "gu": "કલમ"},
    "अपराध क्रमांक":     {"mr": "गुन्हा क्रमांक", "bn": "অপরাধ নম্বর", "gu": "ગુનો ક્રમાંક"},
    "प्रकरण क्रमांक":    {"mr": "प्रकरण क्रमांक", "bn": "মামলা নম্বর", "gu": "કેસ ક્રમાંક"},
    "अनुसंधान":          {"mr": "तपास", "bn": "তদন্ত", "gu": "તપાસ"},
    "अभियोग पत्र":       {"mr": "दोषारोपपत्र", "bn": "অভিযোগপত্র", "gu": "આરોપનામું"},
    "साक्ष्य":           {"mr": "पुरावा", "bn": "সাক্ষ্য", "gu": "પુરાવો"},
    "प्रथम दृष्टया":     {"mr": "प्रथमदर्शनी", "bn": "প্রাথমিকভাবে", "gu": "પ્રથમદર્શી"},
    "थाना":              {"mr": "पोलीस ठाणे", "bn": "থানা", "gu": "પોલીસ સ્ટેશન"},

    # ---- document / relief ----
    "आवेदन पत्र":        {"mr": "अर्ज", "bn": "আবেদনপত্র", "gu": "અરજી"},
    "प्रार्थना":         {"mr": "विनंती", "bn": "প্রার্থনা", "gu": "વિનંતી"},
    "उन्मोचित":          {"mr": "आरोपमुक्त", "bn": "অব্যাহতি", "gu": "મુક્ત"},
    "उन्मुक्त":          {"mr": "आरोपमुक्त", "bn": "অব্যাহতি", "gu": "મુક્ત"},
    "न्यायोचित एवं न्यायसंगत": {"mr": "न्याय्य व न्यायोचित", "bn": "ন্যায়সঙ্গত", "gu": "ન્યાયોચિત"},

    # ---- signature block ----
    "दिनांक":            {"mr": "दिनांक", "bn": "তারিখ", "gu": "તારીખ"},
    "स्थान":             {"mr": "स्थळ", "bn": "স্থান", "gu": "સ્થળ"},
    "द्वारा अभिभाषक":    {"mr": "द्वारा अधिवक्ता", "bn": "মাধ্যমে আইনজীবী", "gu": "મારફતે વકીલ"},
    "एडवोकेट":           {"mr": "अधिवक्ता", "bn": "আইনজীবী", "gu": "એડવોકેટ"},
}


def glossary_lines(lang: str) -> list[str]:
    """Return "hi_term → lang_term" lines for the pinned terms in `lang`.
    Blank cells (not yet advocate-verified) are skipped so the model is only
    constrained where we're sure."""
    out: list[str] = []
    for hi, m in TERMS.items():
        tgt = (m.get(lang) or "").strip()
        if tgt:
            out.append(f"{hi}  →  {tgt}")
    return out


def coverage(lang: str) -> tuple[int, int]:
    """(pinned, total) — how much of the glossary is advocate-ready for `lang`."""
    total = len(TERMS)
    pinned = sum(1 for m in TERMS.values() if (m.get(lang) or "").strip())
    return pinned, total
