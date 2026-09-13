"""Brief → which document, and every fact it already contains. Deterministic.

This is the front door of drafting. An advocate types or speaks one line —

    "bail for Ramkumar s/o Shyamlal, 32, r/o village Barai, thana Kotwali,
     district Gwalior, FIR 145/2025 u/s 420, 406 BNS, in jail since 10/03/2025"

— and the screen should open on the RIGHT reviewed template with those fields
already filled. Before this module that step depended entirely on a model call:
when the model was unreachable (which in production was every call, for weeks)
the classifier fell back to a guess at confidence 0.3 and extracted nothing, so
the advocate got a blank form whose placeholders were the field names.

So this runs with NO model at all, in milliseconds:

  recognise(brief)            → the reviewed template id (bail_sessions, cheque_138 …),
                                how sure, and why — every signal it matched is shown
  extract(brief, tid, lang)   → {field_key: value} for that template's OWN fields,
                                each with the words in the brief it came from

A model, when one answers, is only ever allowed to add to this (see api
/intake/enrich) — never to replace a value the advocate's own words produced.

ZERO FABRICATION. Every value here is either a span of the brief, the same span
in the other script (a district's Hindi name, a name transliterated — flagged
`converted` so the screen asks him to check the spelling), or a fixed legal term
for a fact the brief states ("no criminal record" → the standard ground wording).
Nothing is inferred about the client. The two things that ARE inferred — the
court's city from the FIR district, and the State from a district — are marked
`inferred` and shown amber, because choosing a forum is the advocate's call.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from headnote.drafter import geo_in as GEO

# Devanagari LETTERS. Not the whole block: the danda "।" (U+0964) and the Devanagari
# digits live inside U+0900–097F, and treating them as letters glued every
# sentence-final word to its full stop ("ग्वालियर।" was no longer a place).
DEVA = "ऀ-ॣॱ-ॿ"
_WORD = rf"[A-Za-z][A-Za-z'.]*|[{DEVA}‌‍]+"


def _nfc(s: str) -> str:
    return unicodedata.normalize("NFC", (s or "")).replace("‌", "").replace("‍", "")


def is_deva(s: str) -> bool:
    return bool(re.search(rf"[{DEVA}]", s or ""))


# =========================================================================== language
_HINGLISH = re.compile(
    r"(?<![a-z])(jamanat|zamanat|thana|dhara|mukadma|mukadama|arzi|arji|aavedan|avedan|"
    r"nyayalay|adalat|ko|ka|ki|ke|hai|hain|tha|thi|mein|me|se|liye|lie|wala|wali|"
    r"bhai|beta|pita|putra|patni|pati|gaon|gram|tehsil|zila|jila|giraftar|jail\s+me)(?![a-z])",
    re.I)


def choose_lang(brief: str) -> str:
    """The document language the brief implies: Devanagari or Hinglish → Hindi,
    plain English → English. The screen's toggle always overrides this."""
    t = _nfc(brief)
    letters = re.findall(rf"[A-Za-z{DEVA}]", t)
    if not letters:
        return "hi"
    deva = sum(1 for c in letters if re.match(rf"[{DEVA}]", c))
    if deva / len(letters) > 0.15:
        return "hi"
    return "hi" if len(_HINGLISH.findall(t)) >= 2 else "en"


# =========================================================================== recognition
# (base type, weight, pattern). A base type is the canonical document; the court
# picks the reviewed template id. Weights: a document named outright = 10, a
# strong subject word = 5–6, a weak one = 2–3. Procedural section numbers only
# count WITH their Act beside them — "u/s 302 IPC" is an offence, not a door.
_CRPC = r"(?:cr\.?\s?p\.?\s?c\.?|crpc|दं\.?\s?प्र\.?\s?सं\.?|दण्ड प्रक्रिया|दंड प्रक्रिया)"
_BNSS = r"(?:bnss|b\.n\.s\.s\.?|बीएनएसएस|भा\.?\s?ना\.?\s?सु\.?\s?सं\.?|भारतीय नागरिक सुरक्षा)"


def _sec(nums: str, act: str) -> str:
    return rf"(?:(?:धारा|section|sec\.?|u/s|s\.)\s*)?(?<!\d)(?:{nums})(?!\d)\s*(?:of\s+(?:the\s+)?)?{act}"


_SIGNALS: list[tuple[str, int, str]] = [
    # ---------------- bail family
    ("anticipatory", 10, r"अग्रिम\s*जमानत|anticipatory|agrim\s+(?:jamanat|zamanat|bail)|pre[-\s]?arrest"),
    ("anticipatory", 6, r"गिरफ्तारी\s*(?:की|का)\s*(?:आशंका|डर|भय)|(?:fear|apprehen\w*)\s+(?:of\s+)?arrest|"
                        r"giraftari\s+ka\s+(?:dar|darr)|not\s+(?:yet\s+)?arrested|गिरफ्तार\s+नहीं"),
    ("anticipatory", 8, _sec("438", _CRPC) + "|" + _sec("482", _BNSS)),
    ("bail", 10, r"जमानत\s*(?:आवेदन|अर्जी|याचिका|प्रार्थना)|bail\s+(?:application|petition|plea)|"
                 r"(?:jamanat|zamanat)\s+(?:ki\s+)?(?:arzi|arji|application|aavedan)"),
    ("bail", 5, r"जमानत|(?<![a-z])bail(?![a-z])|jamanat|zamanat"),
    ("bail", 4, r"(?:^|\.\s*)(?:regular\s+)?bail\s+(?:for|of)\s|(?:jamanat|zamanat)\s+(?:lagani|karani|chahiye)|जमानत\s+(?:करानी|लगानी|चाहिए)"),
    ("bail", 4, r"न्यायिक\s*अभिरक्षा|judicial\s+custody|(?:in|since)\s+jail|जेल\s*में|jail\s+me"),
    ("bail", 8, _sec("437|439", _CRPC) + "|" + _sec("480|483", _BNSS)),
    ("default_bail", 10, r"default\s+bail|statutory\s+bail|डिफॉल्ट\s*जमानत|अनिवार्य\s*जमानत"),
    ("default_bail", 8, _sec(r"167\s*\(\s*2\s*\)", _CRPC) + "|" + _sec(r"187\s*\(\s*3\s*\)", _BNSS) +
                        r"|167\s*\(\s*2\s*\)|187\s*\(\s*3\s*\)"),
    ("default_bail", 6, r"(?:charge\s*sheet|chargesheet|challan|चालान|अभियोग\s*पत्र)\s+(?:not|नहीं)"),
    ("suspension_389", 10, r"suspension\s+of\s+sentence|sentence\s+suspen\w*|सजा\s*(?:का\s*)?निलंबन|"
                           r"दण्डादेश\s*(?:का\s*)?निलंबन|bail\s+pending\s+appeal"),
    ("suspension_389", 8, _sec("389", _CRPC) + "|" + _sec("430", _BNSS)),
    # ---------------- criminal proceedings
    ("quashing", 10, r"quash\w*|अभिखण्डन|अभिखंडन|(?:fir|एफआईआर)\s+(?:रद्द|निरस्त)\s+(?:करने|कराने)"),
    ("quashing", 8, _sec("482", _CRPC) + "|" + _sec("528", _BNSS)),
    ("revision", 10, r"(?<![a-z])revision(?![a-z])|पुनरीक्षण|निगरानी|nigrani"),
    ("revision", 8, _sec("397|399|401", _CRPC) + "|" + _sec("438|440|442", _BNSS)),
    ("appeal", 10, r"criminal\s+appeal|appeal\s+against\s+(?:the\s+)?(?:conviction|judgment)|"
                   r"दाण्डिक\s*अपील|आपराधिक\s*अपील|दोषसिद्धि\s*के\s*विरुद्ध\s*अपील"),
    ("appeal", 5, r"(?<![a-z])appeal(?![a-z])|अपील|convicted|conviction|दोषसिद्ध|सजा\s+(?:हुई|सुनाई)"),
    ("appeal", 8, _sec("374", _CRPC) + "|" + _sec("415", _BNSS)),
    ("discharge", 10, r"discharge|उन्मोचन|डिस्चार्ज|आरोप\s*मुक्त"),
    ("discharge", 8, _sec("227|239", _CRPC) + "|" + _sec("250|262", _BNSS)),
    ("production", 9, r"(?:summon|call\s+for|production\s+of)\s+(?:the\s+)?(?:documents?|records?|cctv|cdr)|"
                      r"दस्तावेज\s*(?:तलब|मंगाने|प्रस्तुत\s+कराने)|cctv\s+footage|call\s+detail"),
    ("production", 8, _sec("91", _CRPC) + "|" + _sec("94", _BNSS)),
    ("reply", 10, r"(?<![a-z])reply(?![a-z])|जवाब|जबाव|counter\s+affidavit|प्रत्युत्तर|objection\s+to"),
    ("complaint_156", 10, r"156\s*\(\s*3\s*\)|175\s*\(\s*3\s*\)|"
                          r"(?:fir|एफआईआर|रिपोर्ट|report)\s+(?:not\s+(?:being\s+)?(?:registered|lodged)|दर्ज\s+नहीं)|"
                          r"police\s+(?:is\s+)?not\s+registering|direction\s+to\s+(?:the\s+)?police"),
    ("parivad", 10, r"परिवाद\s*पत्र|private\s+complaint|इस्तगासा|istgasa"),
    ("parivad", 7, _sec("200", _CRPC) + "|" + _sec("223", _BNSS)),
    ("recall_311", 10, r"recall\s+(?:of\s+)?(?:the\s+)?witness|re[-\s]?examin\w*\s+(?:the\s+)?witness|"
                       r"साक्षी\s*(?:को\s*)?(?:पुनः|पुन:|दोबारा)"),
    ("recall_311", 8, _sec("311", _CRPC) + "|" + _sec("348", _BNSS)),
    ("supurdgi", 10, r"सुपुर्दगी|सुपुर्दनामा|supurd\w*|superdari|sapurd\w*|(?:release|interim\s+custody)\s+of\s+"
                     r"(?:the\s+)?(?:seized\s+)?(?:vehicle|motorcycle|bike|car|truck|tractor|mobile|property)"),
    ("supurdgi", 6, r"(?:जब्त|ज़ब्त|seized)\b.{0,30}(?:वाहन|मोटरसाइकिल|मोटर\s*साइकिल|गाड़ी|vehicle|motorcycle|bike|car|truck|tractor)|"
                    r"(?:वाहन|मोटरसाइकिल|गाड़ी|vehicle|motorcycle|bike|car|truck|tractor).{0,30}(?:जब्त|ज़ब्त|seized)"),
    ("supurdgi", 8, _sec("451|457", _CRPC) + "|" + _sec("497|503", _BNSS)),
    ("exemption_205", 10, r"exemption\s+from\s+(?:personal\s+)?(?:appearance|attendance)|हाजिरी\s*माफी|"
                          r"व्यक्तिगत\s*उपस्थिति\s*से\s*छूट|haziri\s+maafi"),
    ("exemption_205", 8, _sec("205|317", _CRPC) + "|" + _sec("228|355", _BNSS)),
    ("compounding", 10, r"compound\w*|राजीनामा|rajinama|razinama|samjhauta|समझौता\s+(?:हो\s+गया|आवेदन)"),
    ("compounding", 8, _sec("320", _CRPC) + "|" + _sec("359", _BNSS)),
    ("statement_178", 9, _sec("164", _CRPC) + "|" + _sec("183", _BNSS) + r"|कथन\s+(?:दर्ज|लेखबद्ध)"),
    ("production_warrant", 10, r"production\s+warrant|उत्पादन\s*वारंट|प्रोडक्शन\s*वारंट"),
    ("mention_memo", 10, r"mention(?:ing)?\s+memo|urgent\s+listing|स्मरण\s*पत्र"),
    ("transfer_petition", 10, r"transfer\s+(?:petition|application|of\s+(?:the\s+)?case)|स्थानान्तरण|स्थानांतरण"),
    ("transfer_petition", 8, _sec("407|408", _CRPC) + "|" + _sec("447|448", _BNSS)),
    # ---------------- cheque / money
    ("cheque", 12, r"138\s*(?:(?:of\s+)?(?:the\s+)?n\.?\s?i\.?\s*act\s*)?complaint|complaint\s+(?:u/s|under)\s+(?:section\s+)?138|"
                   r"परिवाद\s*(?:पत्र)?\s*(?:अन्तर्गत|अंतर्गत)?\s*(?:धारा)?\s*138"),
    ("cheque", 10, r"(?<!\d)138(?!\d)|cheque\s*(?:bounce|dishonou?r|return)|चेक\s*(?:बाउंस|अनादर|अनादरित)|"
                   r"chek\s+bounce|परक्राम्य\s*लिखत|n\.?\s?i\.?\s+act|negotiable\s+instruments"),
    ("cheque", 5, r"(?<![a-z])cheque(?![a-z])|चेक|dishonou?r(?:ed)?|अनादरित|insufficient\s+funds"),
    ("ni_138_dismiss", 12, r"(?:notice|सूचना|नोटिस)\s+(?:was\s+)?(?:not\s+served|never\s+(?:received|served)|"
                           r"तामील\s+नहीं)"),
    ("legal_notice", 12, r"(?:draft|prepare|send|issue|make|write)\w*\s+(?:a\s+|the\s+)?(?:legal\s+|demand\s+)?notice|"
                         r"(?:legal|demand)\s+notice\s+(?:for|to|against|on\s+behalf|in\s+favou?r)|^\s*(?:legal|demand)\s+notice|"
                         r"notice\s+(?:bhej|bhejna|bhejni|draft|banana|banani|likhna)|"
                         r"(?:विधिक|कानूनी)\s*(?:सूचना\s*पत्र|सूचना|नोटिस)\s*(?:तैयार|भेज|बना|लिख)|नोटिस\s*(?:भेजना|भेजनी|बनाना|तैयार\s+करना)"),
    ("legal_notice", 4, r"legal\s+notice|demand\s+notice|विधिक\s*सूचना|कानूनी\s*नोटिस"),
    ("recovery_suit", 10, r"recovery\s+(?:suit|of\s+money)|money\s+(?:suit|recovery)|suit\s+for\s+(?:the\s+)?recovery|"
                          r"recovery\s+of\s+(?:rs\.?|₹|inr|the\s+amount|amount|dues)|वसूली\s*(?:का\s*)?वाद|धन\s*वसूली"),
    ("recovery_suit", 5, r"(?:loan|udhar|उधार|कर्ज|कर्ज़|रुपये)\s+(?:not\s+returned|wapas\s+nahi|वापस\s+नहीं)|took\s+(?:a\s+)?loan|borrowed|"
                         r"(?:did\s+not|has\s+not|refus\w+\s+to)\s+(?:repay|return)\s+(?:the\s+)?(?:money|loan|amount)"),
    # ---------------- family
    ("maintenance", 10, r"maintenance|भरण\s*[-–]?\s*पोषण|guzara|गुजारा\s*भत्ता|kharcha|खर्चा\s*पानी|"
                        r"bharan\s*poshan"),
    ("maintenance", 8, _sec("125", _CRPC) + "|" + _sec("144", _BNSS)),
    ("dv", 10, r"domestic\s+violence|घरेलू\s*हिंसा|d\.?\s?v\.?\s+act|pwdva|महिलाओं\s*का\s*संरक्षण"),
    ("divorce_13", 10, r"divorce|तलाक|talaq|विवाह\s*विच्छेद|13\s*(?:\(1\)|b)?\s*(?:hma|hindu\s+marriage)"),
    ("restitution_9", 10, r"restitution\s+of\s+conjugal|दाम्पत्य\s*(?:अधिकारों?\s*की\s*)?पुन[र्:]?स्थापना|"
                          r"section\s*9\s+(?:of\s+)?(?:the\s+)?(?:hma|hindu\s+marriage)|धारा\s*9\s+हिन्दू\s+विवाह"),
    # ---------------- constitutional / HC
    ("writ_petition", 10, r"(?<![a-z])writ(?![a-z])|रिट|article\s*22[67]|अनुच्छेद\s*22[67]"),
    ("habeas_corpus", 12, r"habeas\s+corpus|बन्दी\s*प्रत्यक्षीकरण|बंदी\s*प्रत्यक्षीकरण|illegal\s+detention"),
    ("stay_petition", 8, r"(?<![a-z])stay\s+(?:application|petition|of|on)|स्थगन\s*(?:आवेदन|आदेश)"),
    # ---------------- civil
    ("vakalatnama", 12, r"vakalat\s*nama|wakalat\s*nama|vakalatnama|वकालतनामा|वकालत\s*नामा"),
    ("general_affidavit", 9, r"(?<![a-z])affidavit(?![a-z])|शपथ\s*पत्र|हलफनामा|halafnama"),
    ("mact_166", 10, r"accident\s+claim|motor\s+accident|m\.?a\.?c\.?t|दुर्घटना\s*(?:दावा|क्लेम)|claim\s+tribunal"),
    ("injunction_suit", 10, r"injunction|निषेधाज्ञा|stay\s+on\s+construction|कब्जे\s+में\s+हस्तक्षेप"),
    ("specific_performance", 10, r"specific\s+performance|agreement\s+to\s+sell|विक्रय\s*(?:का\s*)?(?:अनुबंध|इकरारनामा)|"
                                 r"बिक्री\s*(?:का\s*)?(?:अनुबंध|इकरारनामा)|इकरारनामा"),
    ("declaration_suit", 9, r"declaratory|declaration\s+(?:suit|of\s+title)|घोषणा\s*(?:का\s*)?वाद|स्वत्व\s*घोषणा"),
    ("partition_suit", 10, r"partition|बंटवारा|बँटवारा|batwara|विभाजन\s*वाद"),
    ("eviction_suit", 10, r"eviction|बेदखली|bedakhli|vacate\s+the\s+(?:shop|house|premises)|"
                          r"(?:tenant|किरायेदार|kirayedar).{0,40}(?:rent|किराया|kiraya)"),
    ("written_statement", 12, r"written\s+statement|जवाब\s*दावा|जवाबदावा|order\s*(?:viii|8)\s*(?:rule|cpc)"),
    ("consumer_complaint", 10, r"consumer\s+(?:complaint|forum|commission|court)|उपभोक्ता|deficiency\s+in\s+service"),
]
_SIGNALS_C = [(b, w, re.compile(p, re.I)) for b, w, p in _SIGNALS]

# When a document is named outright, the subject words it carries should not
# out-vote it: "legal notice for cheque bounce" is a notice, "anticipatory bail"
# contains the word bail, "reply to bail application" is a reply.
_SUPPRESS = {
    "anticipatory": ("bail", "default_bail"),
    "default_bail": ("bail",),
    "suspension_389": ("bail", "appeal"),
    "legal_notice": ("cheque", "recovery_suit", "maintenance", "eviction_suit"),
    "reply": ("bail", "maintenance", "cheque", "discharge", "anticipatory", "supurdgi", "production",
              "exemption_205", "recall_311"),
    "written_statement": ("recovery_suit", "injunction_suit", "specific_performance", "declaration_suit",
                          "partition_suit", "eviction_suit", "reply"),
    "habeas_corpus": ("writ_petition",),
    "cheque": ("parivad",),
    "ni_138_dismiss": ("cheque", "legal_notice"),
    "compounding": ("cheque",),
    "production_warrant": ("production",),
    "stay_petition": ("injunction_suit",),
    "general_affidavit": (),
}

# base type → court → template id. The first court listed is the default.
_BY_COURT: dict[str, list[tuple[str, str]]] = {
    "bail": [("sessions", "bail_sessions"), ("magistrate", "bail_magistrate"), ("hc", "bail_hc")],
    "anticipatory": [("sessions", "anticipatory_bail"), ("hc", "anticipatory_bail_hc")],
    "revision": [("sessions", "revision_sessions"), ("hc", "revision_hc")],
    "appeal": [("sessions", "appeal_sessions"), ("hc", "appeal_hc")],
    "discharge": [("sessions", "discharge_sessions"), ("magistrate", "discharge_magistrate")],
    "production": [("magistrate", "production_magistrate"), ("sessions", "production_sessions")],
    "reply": [("magistrate", "reply_magistrate"), ("sessions", "reply_sessions"), ("hc", "reply_hc")],
}
_SINGLE = {
    "default_bail": "default_bail", "suspension_389": "suspension_389", "quashing": "quashing",
    "complaint_156": "complaint_156", "parivad": "parivad", "recall_311": "recall_311",
    "supurdgi": "supurdgi", "exemption_205": "exemption_205", "compounding": "compounding",
    "statement_178": "statement_178", "production_warrant": "production_warrant",
    "mention_memo": "mention_memo", "transfer_petition": "transfer_petition", "cheque": "cheque_138",
    "ni_138_dismiss": "ni_138_dismiss", "legal_notice": "legal_notice", "recovery_suit": "recovery_suit",
    "maintenance": "maintenance", "dv": "dv", "divorce_13": "divorce_13", "restitution_9": "restitution_9",
    "writ_petition": "writ_petition", "habeas_corpus": "habeas_corpus", "stay_petition": "stay_petition",
    "vakalatnama": "vakalatnama", "general_affidavit": "general_affidavit", "mact_166": "mact_166",
    "injunction_suit": "injunction_suit", "specific_performance": "specific_performance",
    "declaration_suit": "declaration_suit", "partition_suit": "partition_suit",
    "eviction_suit": "eviction_suit", "written_statement": "written_statement",
    "consumer_complaint": "consumer_complaint",
}

_COURT_WORDS = {
    "hc": r"high\s*court|हाई\s*कोर्ट|हाईकोर्ट|उच्च\s*न्यायालय|खण्डपीठ|खंडपीठ|(?<![A-Za-z])H\.?C\.?(?![A-Za-z])",
    "sessions": r"sessions?\s*(?:court|judge)|session\s*kort|सत्र\s*(?:न्यायालय|न्यायाधीश|न्यायधीश)|सेशन(?:्स)?\s*कोर्ट|"
                r"(?<![A-Za-z])A\.?S\.?J\.?(?![A-Za-z])|additional\s+sessions|अपर\s*सत्र|special\s+judge|"
                r"विशेष\s*न्यायाधीश|district\s*(?:&|and)\s*sessions",
    "magistrate": r"magistrate|(?<![A-Za-z])(?:J\.?M\.?F\.?C|C\.?J\.?M|A\.?C\.?J\.?M)\.?(?![A-Za-z])|jmfc|cjm|"
                  r"मजिस्ट्रेट|दण्डाधिकारी|दंडाधिकारी|मजिस्ट्रेट\s*कोर्ट",
    "family": r"family\s*court|कुटुम्ब\s*न्यायालय|कुटुंब\s*न्यायालय|परिवार\s*न्यायालय|फैमिली\s*कोर्ट",
}
_REJECT = re.compile(r"reject\w*|dismiss\w*|निरस्त|खारिज|ख़ारिज|नामंजूर|ना-मंजूर|khariz|kharij|radd|रद्द", re.I)
_BELOW = re.compile(r"reject\w*|dismiss\w*|निरस्त|खारिज|ख़ारिज|नामंजूर|khariz|kharij|convict\w*|sentenc\w*|"
                    r"judgment\s+(?:of|dated|passed)|(?:order|judgment)\s+(?:of|passed\s+by|dated)|passed\s+by|"
                    r"दोषसिद्ध\w*|सजा|द्वारा\s+पारित|के\s+आदेश|आदेश\s+दिनांक|impugned|विवादित", re.I)
_SUCCESSIVE = re.compile(r"second\s+bail|successive|द्वितीय|दूसरा\s+(?:जमानत|आवेदन)|दूसरी\s+(?:बार|अर्जी)|"
                         r"doosr[ai]\s+(?:bail|jamanat)|पूर्व\s+में\s+(?:प्रस्तुत\s+)?जमानत", re.I)


def _courts(text: str) -> dict:
    """Which court he is filing in, and which court already refused him. A court
    named beside a rejection word is the court BELOW — it must never be read as
    the forum ("rejected by the magistrate" means file in Sessions)."""
    target, prior = None, None
    for level, pat in _COURT_WORDS.items():
        for m in re.finditer(pat, text, re.I):
            window = text[max(0, m.start() - 45): m.end() + 30]
            if _BELOW.search(window):
                prior = prior or level
            else:
                target = target or level
    return {"target": target, "prior": prior}


_ESCALATE = {"magistrate": "sessions", "sessions": "hc"}


def recognise(brief: str) -> dict:
    """The reviewed template this brief is asking for.

    Returns {tid, base, court, confidence, level, why, alternatives}. `level` is
    what the screen says: "sure" (open it), "likely" (open it, show the other
    candidates beside it), "unsure" (ask him to pick — never silently guess)."""
    text = _nfc(brief)
    scores: dict[str, int] = {}
    why: dict[str, list[str]] = {}
    for base, w, rx in _SIGNALS_C:
        m = rx.search(text)
        if m:
            scores[base] = scores.get(base, 0) + w
            why.setdefault(base, []).append(m.group(0).strip())
    strong = {b for b, w, rx in _SIGNALS_C if w >= 10 and rx.search(text)}
    for b in strong:
        for loser in _SUPPRESS.get(b, ()):
            if loser in scores:
                scores[loser] = max(0, scores[loser] - (30 if loser in strong else 12))
    ranked = sorted((kv for kv in scores.items() if kv[1] > 0), key=lambda kv: -kv[1])
    courts = _courts(text)
    if not ranked:
        return {"tid": None, "base": None, "court": courts["target"], "confidence": 0.0,
                "level": "unsure", "why": [], "alternatives": [], "courts": courts}

    def to_tid(base: str) -> tuple[str, str]:
        if base in _SINGLE:
            return _SINGLE[base], ""
        options = _BY_COURT[base]
        want = courts["target"]
        if not want and courts["prior"] and base in ("bail", "anticipatory", "revision", "appeal"):
            want = _ESCALATE.get(courts["prior"])
        if base == "appeal" and not courts["target"] and re.search(
                r"(?:sessions|सत्र).{0,30}(?:convict|दोषसिद्ध|सजा)|(?:convict|दोषसिद्ध|सजा).{0,30}(?:sessions|सत्र)",
                text, re.I):
            want = "hc"          # a Sessions conviction is appealed in the High Court
        for c, tid in options:
            if c == want:
                return tid, c
        return options[0][1], options[0][0]

    top_base, top = ranked[0]
    second = ranked[1][1] if len(ranked) > 1 else 0
    conf = min(1.0, top / 10.0) * (1.0 - 0.5 * (second / top if top else 0))
    conf = round(conf, 2)
    level = "sure" if conf >= 0.6 else ("likely" if conf >= 0.35 else "unsure")
    tid, court = to_tid(top_base)
    alts: list[str] = []
    for b, _s in ranked[1:5]:
        t, _c = to_tid(b)
        if t != tid and t not in alts:
            alts.append(t)
    # the same document in the other courts is always a one-tap switch
    siblings = [t for c, t in _BY_COURT.get(top_base, []) if t != tid]
    return {"tid": tid, "base": top_base, "court": court or courts["target"], "confidence": conf,
            "level": level, "why": why.get(top_base, [])[:4], "alternatives": alts,
            "siblings": siblings, "courts": courts}


# =========================================================================== extraction helpers
_STOP = {w.lower() for w in """
    a an the and or of for to in on at by with from as is was are be been being has have had it its
    this that these those my our his her their your me him them he she they we you i who whom which
    application app petition bail anticipatory regular jamanat zamanat case matter file filing draft
    please make prepare write need want client my accused applicant complainant petitioner respondent
    plaintiff defendant appellant revisionist deponent wife husband tenant landlord son daughter father
    mother brother name named aged age years yrs year old resident r/o village gram district distt dist
    police station thana ps fir crime no number u/s under section sections sec dated date since jail
    custody court sessions session magistrate high against versus vs v kumar? mr mrs ms smt shri sri late
    ko ka ki ke hai hain tha thi mein me se liye wala wali ne par aur ya bhi
    through thru proprietor prop partner director manager authorised authorized representative its
    gave given give took taken lent borrowed filed paid issued sent dated did does not who whose having
    residing working living order judgment notice complaint cheque check fir suit petition transfer decree
    award compromise land property shop house money loan rent amount ground grounds cruelty divorce
    teacher farmer driver labourer labour student shopkeeper businessman housewife doctor clerk employee
    constable patwari sarpanch officer engineer contractor worker rs rupees lakh
    already granted released got also other rest all both convicted sentenced wants want seeks seeking
    ipc bns bnss crpc ndps act acts owner police illegally illegal detained custody wrongfully
""".split() if not w.endswith("?")}
_STOP_HI = set("""
    का की के को में से ने पर और या भी है हैं था थी हो हुआ हुई द्वारा हेतु लिए लिये तथा एवं व बनाम विरुद्ध
    आवेदक आवेदिका आरोपी अभियुक्त अभियुक्ता परिवादी फरियादी शिकायतकर्ता प्रार्थी प्रार्थिया याचिकाकर्ता वादी प्रतिवादी
    अनावेदक पत्नी पति पुत्र पुत्री पिता माता भाई बहन नाम नामक उम्र आयु वर्ष साल निवासी ग्राम गांव गाँव मोहल्ला
    वार्ड थाना जिला जिले तहसील अपराध क्रमांक धारा दिनांक जमानत आवेदन न्यायालय सत्र मजिस्ट्रेट जेल अभिरक्षा
    श्री श्रीमती कुमारी कु स्व स्वर्गीय मेरे मेरा मेरी हमारे उसके उनके यह वह इस उस एक किसान मजदूर मजदूरी
    व्यवसाय पेशा प्रथम द्वितीय सूचना रिपोर्ट एफआईआर चेक राशि रुपये रु मुवक्किल पक्षकार जिसकी जिसका जिनकी
    मुल्जिम मुलजिम मुल्ज़िम जनपद कारागार निरुद्ध चाहती चाहता चाहते
""".split())
_HONORIFIC = re.compile(r"^(?:श्री(?:मती)?|कु\.?|कुमारी|स्व\.?|स्वर्गीय|shri|sri|smt\.?|mr\.?|mrs\.?|ms\.?|late|sh\.)\s+",
                        re.I)

_REL = (r"s/o|s\.o\.|son\s+of|d/o|daughter\s+of|w/o|wife\s+of|h/o|husband\s+of|"
        r"पुत्र(?:\s+श्री)?|पुत्री(?:\s+श्री)?|आत्मज|आत्मजा|पत्नी(?:\s+श्री)?|पति(?:\s+श्री)?|पिता(?:\s+श्री)?|"
        r"पिता\s*का\s*नाम|father(?:'s)?\s+name|putra")
_REL_RX = re.compile(rf"(?<![A-Za-z{DEVA}])(?:{_REL})(?![A-Za-z{DEVA}])\s*[:\-–—]?\s*", re.I)
_TOK_RX = re.compile(rf"@|{_WORD}")
_ALIAS_WORDS = {"@", "उर्फ", "urf", "alias", "alias@"}


def _clean_name(words: list[str]) -> str:
    while words and words[0].lower() in _ALIAS_WORDS:
        words = words[1:]
    while words and words[-1].lower() in _ALIAS_WORDS:
        words = words[:-1]
    s = " ".join(w.strip(".,;:") for w in words if w.strip(".,;:"))
    s = _HONORIFIC.sub("", s).strip()
    if s and not is_deva(s) and s == s.lower():
        s = " ".join(w[:1].upper() + w[1:] for w in s.split())
    return s


def _is_stop(w: str) -> bool:
    lw = w.lower().strip(".,")
    return lw in _STOP or w in _STOP_HI or bool(re.match(r"^\d", w))


def _name_before(text: str, end: int, limit: int = 4) -> tuple[str, int]:
    """Up to `limit` name words that END at `end` (skipping commas), stopping at a
    stopword, a digit or sentence punctuation."""
    seg = text[max(0, end - 80):end]
    seg = re.sub(r"[\s,]+$", "", seg)
    toks = list(_TOK_RX.finditer(seg))
    words: list[str] = []
    start = end
    base = max(0, end - 80)
    for t in reversed(toks):
        gap = seg[t.end(): (words and start - base) or len(seg)]
        if re.search(r"[.;:।|()\[\]\n/]|\d", gap.replace(".", "", 1) if len(gap) <= 2 else gap):
            if words:
                break
        w = t.group(0)
        if _is_stop(w) or _HONORIFIC.match(w + " ") or (GEO.lookup(w) and not GEO.is_weak(w) and not words):
            break
        words.insert(0, w)
        start = base + t.start()
        if len(words) >= limit:
            break
    return _clean_name(words), start


def _name_after(text: str, start: int, limit: int = 4) -> tuple[str, int]:
    seg = text[start:start + 80]
    m = _HONORIFIC.match(seg)
    off = m.end() if m else 0
    words: list[str] = []
    end = start
    pos = off
    for t in _TOK_RX.finditer(seg, off):
        gap = seg[pos:t.start()]
        if words and re.search(r"[,.;:।|()\[\]\n/]|\d", gap):
            break
        if not words and re.search(r"[;:।|()\[\]\n/]|\d", gap):
            break
        w = t.group(0)
        if _is_stop(w) or (len(w) <= 2 and seg[t.end():t.end() + 1] == "/"):
            break
        words.append(w)
        end = start + t.end()
        pos = t.end()
        if len(words) >= limit:
            break
    return _clean_name(words), end


# role words, in both scripts → canonical hint
_ROLE_HINTS: list[tuple[str, str]] = [
    ("accused", r"accused|आरोपी|अभियुक्त(?:ा)?|मुलजिम|mulzim|aaropi|aropi"),
    ("applicant", r"applicant|आवेदक|आवेदिका|प्रार्थी|प्रार्थिया"),
    ("complainant", r"complainant|informant|परिवादी|परिवादिनी|फरियादी|शिकायतकर्ता|शिकायतकर्ता|pariwadi|fariyadi"),
    ("client", r"(?:my\s+)?client|मुवक्किल|मेरे\s+पक्षकार|muvakkil|mawakkil"),
    ("wife", r"wife|पत्नी|patni|biwi|बीवी"),
    ("husband", r"husband|पति|pati"),
    ("petitioner", r"petitioner|याचिकाकर्ता|याची"),
    ("respondent", r"respondent|प्रत्यर्थी|अनावेदक|opposite\s+party"),
    ("plaintiff", r"plaintiff|वादी(?!\s*पत्र)"),
    ("defendant", r"defendant|प्रतिवादी"),
    ("tenant", r"tenant|किरायेदार|kirayedar"),
    ("landlord", r"landlord|मकान\s*मालिक|makan\s*malik"),
    ("deponent", r"deponent|शपथकर्ता"),
    ("appellant", r"appellant|अपीलार्थी"),
    ("revisionist", r"revisionist|पुनरीक्षणकर्ता"),
    ("owner", r"owner|मालिक|स्वामी"),
    ("detenu", r"detenu|detained\s+person|निरुद्ध\s+व्यक्ति|(?:his|her)\s+(?:daughter|son)"),
    ("client", r"(?:by|from)\s+(?:her|his|the)?\s*(?:father|mother|brother|sister)"),
    ("against", r"against|के\s+(?:विरुद्ध|खिलाफ|ख़िलाफ़)|ke\s+khilaf|versus|vs\.?|बनाम|from\s+whom"),
    ("client", r"(?:filed|petition|application|notice)\s+by|की\s+ओर\s+से|on\s+behalf\s+of"),
]
_ROLE_RX = [(h, re.compile(rf"(?<![A-Za-z{DEVA}])(?:{p})(?![A-Za-z{DEVA}])", re.I)) for h, p in _ROLE_HINTS]


class Person:
    def __init__(self, name: str, start: int, end: int):
        self.name, self.start, self.end = name, start, end
        self.relative = ""
        self.relation = ""
        self.hints: list[str] = []
        self.age = ""
        self.address = ""
        self.occupation = ""
        self.evidence: dict[str, str] = {}

    def key(self) -> str:
        return re.sub(r"\s+", " ", self.name.lower())


def _find_people(text: str) -> list[Person]:
    people: list[Person] = []

    def add(name: str, s: int, e: int) -> Optional[Person]:
        if not name or len(name) < 2 or len(name) > 60:
            return None
        for p in people:
            if p.key() == name.lower():
                return p
            if s < p.end and e > p.start:          # overlapping mention
                return p
        p = Person(name, s, e)
        people.append(p)
        return p

    # 1) "X s/o Y" — the strongest anchor there is in an Indian brief
    for m in _REL_RX.finditer(text):
        rel = m.group(0).strip().lower()
        if re.match(r"पति|पत्नी|husband|wife", rel) and re.search(r"[,;।]\s*$", text[max(0, m.start() - 3):m.start()]):
            continue
        who, ws = _name_before(text, m.start())
        rel_name, re_ = _name_after(text, m.end())
        if not who or not rel_name:
            continue
        p = add(who, ws, re_)
        if p and not p.relative:
            p.relative = rel_name
            p.relation = ("wife" if re.match(r"w/o|wife|पत्नी", rel) else
                          "husband_of" if re.match(r"h/o|husband|पति", rel) else
                          "daughter" if re.match(r"d/o|daughter|पुत्री|आत्मजा", rel) else "son")
            p.end = re_
            p.evidence["relative"] = text[ws:re_]

    # 2) role word + name ("accused Ramesh", "आरोपी रमेश", "client: Sunita Devi")
    for hint, rx in _ROLE_RX:
        for m in rx.finditer(text):
            after = text[m.end():m.end() + 3]
            if re.search(r"(?:co|सह)\s*[-]?\s*$", text[max(0, m.start() - 4):m.start()], re.I):
                continue
            nxt = re.match(r"\s*(?:(?:is|name|named|नाम|नामक|श्री|श्रीमती|smt\.?|shri|mr\.?|mrs\.?|"
                           r"teacher|farmer|driver|labou?rer|student|shopkeeper|businessman|housewife|doctor|clerk|"
                           r"employee|constable|officer|engineer|widow|minor|shikshak|शिक्षक|किसान|मजदूर|छात्र|"
                           r"विधवा|नाबालिग|a|an|the)(?![A-Za-z{DEVA}])\s*|[:\-–—]\s*)*", text[m.end():], re.I)
            s = m.end() + (nxt.end() if nxt else 0)
            name, e = _name_after(text, s)
            target = None
            if name:
                target = add(name, s, e)
            else:
                # "रमेश नामक आरोपी" / "Ramesh (accused)" — the name sits BEFORE the role
                pre = re.search(r"(?:नामक|named|\()\s*$", text[max(0, m.start() - 12):m.start()])
                if pre:
                    nb, ns = _name_before(text, m.start() - len(pre.group(0)))
                    if nb:
                        target = add(nb, ns, m.start())
            if target is not None and hint not in target.hints:
                target.hints.append(hint)
            _ = after

    people.sort(key=lambda p: p.start)
    # "Agrawal Traders through proprietor Suresh Agrawal s/o …" is ONE party
    merged: list[Person] = []
    for p in people:
        if merged:
            prev = merged[-1]
            gap = text[prev.start:p.start]
            fm = re.search(r"(?:through|thru|द्वारा)\s+(?:its\s+|उसके\s+)?(proprietor|prop\.?|partner|director|manager|"
                           r"authori[sz]ed\s+signatory|प्रोपराइटर|प्रोप्राइटर|साझेदार|संचालक|प्रबंधक)\s*$", gap, re.I)
            if fm and not prev.relative:
                role = fm.group(1)
                prev.name = f"{prev.name} {'द्वारा' if is_deva(prev.name) else 'through'} {role} {p.name}"
                prev.relative, prev.relation = p.relative, p.relation
                prev.age = prev.age or p.age
                prev.address = prev.address or p.address
                prev.end = p.end
                prev.evidence.update(p.evidence)
                prev.hints += [h for h in p.hints if h not in prev.hints]
                continue
        merged.append(p)
    people = merged
    # a role word just BEFORE an "X s/o Y" mention belongs to that person
    for p in people:
        lead = text[max(0, p.start - 40):p.start]
        for hint, rx in _ROLE_RX:
            if hint != "against" and rx.search(lead) and hint not in p.hints:
                last = list(rx.finditer(lead))[-1]
                if not re.search(r"[.;।\n]", lead[last.end():]):
                    p.hints.append(hint)
        if (re.search(rf"(?:against|के\s+(?:विरुद्ध|खिलाफ)|versus|vs\.?)\s*$", lead, re.I) or
                re.search(r"(?:divorce|maintenance|talaq|guzara|separation|release\w*)\s+from\s+(?:(?:her|his|the)\s+)?"
                          r"(?:husband|wife)?\s*$", lead, re.I)) and "against" not in p.hints:
            p.hints.append("against")
        if re.search(r"(?:by|from)\s+(?:her|his|the)?\s*(?:father|mother|brother|sister)\s*$", lead, re.I) and "client" not in p.hints:
            p.hints.append("client")
        if re.search(r"(?:his|her|their)\s+(?:daughter|son|wife|husband|brother|sister)\s*$", lead, re.I) and "detenu" not in p.hints:
            p.hints.append("detenu")
    return people


# ---------------------------------------------------------------- simple facts
_AGE_RX = re.compile(
    rf"(?:(?<![A-Za-z{DEVA}])(?:age|aged|umr|umar|umra|उम्र|आयु|वय)\s*[:\-–]?\s*(?:about|approx\.?|लगभग|करीब|qareeb)?\s*"
    rf"(\d{{1,2}})(?:\s*(?:years?|yrs?|वर्ष|साल|sal|varsh))?)|"
    rf"(?<!\d)(\d{{1,2}})\s*(?:years?|yrs?|वर्ष|साल|sal|varsh)(?:\s*(?:old|की\s+उम्र|आयु))?(?![A-Za-z])", re.I)
_ADDR_RX = re.compile(
    rf"(?<![A-Za-z{DEVA}])(?:r/o|r\.o\.|resident\s+of|residing\s+at|निवासी|निवासरत|niwasi|nivasi|rahne\s+wala)\s*[:\-–]?\s*", re.I)
_VILLAGE_RX = re.compile(rf"(?<![A-Za-z{DEVA}])(?:village|vill\.?|gram|ग्राम|गांव|गाँव|mohalla|मोहल्ला|ward|वार्ड)\s+", re.I)
_ADDR_STOP = re.compile(
    rf"(?:\bfir\b|एफ\.?आई\.?आर|अपराध\s*क्र|crime\s*no|\bu/s\b|धारा|section|\bage\b|aged|उम्र|आयु|"
    rf"occupation|व्यवसाय|पेशा|\bin\s+jail|जेल|\bsince\b|dated|दिनांक|\bis\s+in\b|who\s|जो\s|"
    rf"\bhas\b|\bwas\b|arrested|गिरफ्तार|court|न्यायालय|कोर्ट|[.;।\n]|\s-\s|\(|\bthe\s+accused|"
    rf"\bagainst\b|के\s+(?:विरुद्ध|खिलाफ)|\bin\s+(?:the\s+|a\s+)?(?:civil|criminal|case|suit|court|matter)|"
    rf",?\s*(?:पति|पत्नी|husband|wife|आरोपी|accused|complainant|परिवादी|अनावेदक|respondent|defendant|प्रतिवादी)(?![A-Za-z])|"
    rf"\bgave\b|\bwho\b|की\s+आय|\bdrawn\b|चेक|\bcheque|राशि|\bamount|\brs\.?\s*\d|₹|रुपये|"
    rf"\bwants?\b|\bseeks?\b|चाहती|चाहता|\(\s*(?:m\.?\s?p|u\.?\s?p|म\.?\s?प्र|उ\.?\s?प्र)|\s(?:उ|म)\.\s?प्र)", re.I)
_PS_RX = re.compile(
    rf"(?<![A-Za-z{DEVA}])(?:police\s+station|p\.\s?s\.|(?<![a-z])ps|thana|थाना|पुलिस\s*थाना|चौकी|chowki|chauki)\s*[:\-–]?\s*", re.I)
_DIST_RX = re.compile(rf"(?<![A-Za-z{DEVA}])(?:district|distt\.?|dist\.?|zila|jila|janpad|जिला|जिले|ज़िला|जनपद|जि\.)\s*[:\-–]?\s*", re.I)
_NOT_A_DISTRICT = re.compile(r"^(?:कारागार|जेल|न्यायालय|न्यायाधीश|अस्पताल|चिकित्सालय|पंचायत|अधिकारी|कलेक्टर|दण्डाधिकारी|"
                             r"अभियोजन|jail|court|judge|hospital|magistrate|collector|prosecution|panchayat|officer)", re.I)
_FIR_RX = re.compile(
    rf"(?:(?<![A-Za-z{DEVA}])(?:f\.?\s?i\.?\s?r\.?|एफ\.?\s?आई\.?\s?आर\.?|प्रथम\s*सूचना\s*(?:रिपोर्ट)?|अपराध|"
    rf"अप\.?\s*क्र\.?|crime|cr\.?|case\s+crime|मु\.?\s*अ\.?\s*स\.?|मुकदमा\s*अपराध\s*संख्या|"
    rf"अपराध\s*संख्या)\s*(?:no\.?|number|nos?\.|क्रमांक|क्र\.?|संख्या|नं\.?|न\.)?\s*[:\-–]?\s*)"
    rf"(\d{{1,6}})\s*[/\\\-]\s*(\d{{2,4}})(?!\d)", re.I)
_CASE_RX = re.compile(
    rf"(?:case\s*(?:no\.?|number)|प्रकरण\s*(?:क्रमांक|क्र\.?)|केस\s*(?:नं\.?|नंबर)|"
    rf"(?:sessions|s\.?t\.?|cr\.?\s?c\.?|m\.?cr\.?c\.?|rcs|mjc|complaint\s*case)\s*(?:no\.?|number))\s*[:\-–]?\s*"
    rf"(\d{{1,6}})\s*[/\\\-]\s*(\d{{2,4}})(?!\d)", re.I)
_SEC_MARK = re.compile(
    rf"(?<![A-Za-z{DEVA}])(?:u/ss?\.?|u/s|under\s+sections?|sections?|secs?\.?|धाराओं|धाराएं|धाराएँ|धारा|dhara|s\.)\s*[:\-–]?\s*", re.I)
_SEC_TOKEN = re.compile(r"\s*((?:\d{1,3}[A-Za-z]{0,2}(?:\s*\(\s*[0-9a-zA-Z]{1,3}\s*\))*))\s*")
_SEC_SEP = re.compile(r"\s*(?:,|/|&|\+|and|एवं|व|तथा|सहपठित|r/w|read\s+with|संग|सह)\s*", re.I)

# Act words → (Hindi house form, English form)
_ACTS: list[tuple[str, str, str]] = [
    (r"b\.?\s?n\.?\s?s\.?\s?s\.?|bnss|भा\.?\s?ना\.?\s?सु\.?\s?सं\.?|भारतीय\s*नागरिक\s*सुरक्षा\s*संहिता", "भा.ना.सु.सं.", "BNSS"),
    (r"b\.?\s?n\.?\s?s\.?(?!\s?s)|(?<![a-z])bns(?!s)|भा\.?\s?न्या\.?\s?सं\.?|भारतीय\s*न्याय\s*संहिता|बीएनएस", "भा.न्या.सं.", "BNS"),
    (r"i\.?\s?p\.?\s?c\.?|(?<![a-z])ipc|भा\.?\s?द\.?\s?वि\.?|भा\.?\s?दं\.?\s?वि\.?|भारतीय\s*दण्ड\s*(?:विधान|संहिता)|"
     r"भारतीय\s*दंड\s*(?:विधान|संहिता)|भादवि|आईपीसी", "भा.द.वि.", "IPC"),
    (r"cr\.?\s?p\.?\s?c\.?|crpc|दं\.?\s?प्र\.?\s?सं\.?", "दं.प्र.सं.", "CrPC"),
    (r"n\.?\s?d\.?\s?p\.?\s?s\.?|ndps|एन\.?डी\.?पी\.?एस", "एन.डी.पी.एस. एक्ट", "NDPS Act"),
    (r"arms\s+act|आयुध\s*अधिनियम|आर्म्स\s*एक्ट", "आयुध अधिनियम", "Arms Act"),
    (r"sc\s*/\s*st|atrocit\w*|अनुसूचित\s*जाति|अजा\s*/\s*अजजा|एससी\s*/?\s*एसटी", "अ.जा./अ.ज.जा. (अत्याचार निवारण) अधिनियम", "SC/ST (PoA) Act"),
    (r"pocso|पॉक्सो|पोक्सो", "पॉक्सो अधिनियम", "POCSO Act"),
    (r"excise|आबकारी", "आबकारी अधिनियम", "Excise Act"),
    (r"i\.?\s?t\.?\s+act|information\s+technology|सूचना\s*प्रौद्योगिकी", "सूचना प्रौद्योगिकी अधिनियम", "IT Act"),
    (r"dowry\s+prohibition|दहेज\s*प्रतिषेध", "दहेज प्रतिषेध अधिनियम", "Dowry Prohibition Act"),
    (r"m\.?\s?v\.?\s+act|motor\s+vehicles?\s+act|मोटरयान|मोटर\s*यान", "मोटरयान अधिनियम", "MV Act"),
    (r"n\.?\s?i\.?\s+act|negotiable|परक्राम्य", "परक्राम्य लिखत अधिनियम", "NI Act"),
    (r"gambling|जुआ", "सार्वजनिक द्यूत अधिनियम", "Public Gambling Act"),
]
_ACTS_C = [(re.compile(rf"\s*(?:of\s+(?:the\s+)?)?(?:{p})(?![A-Za-z])", re.I), hi, en) for p, hi, en in _ACTS]
_ACTS_TAIL = [(re.compile(rf"(?:{p})\s*(?:ki\s+|की\s+|ke\s+|के\s+)?$", re.I), hi, en) for p, hi, en in _ACTS]

_DATE_RX = re.compile(r"(?<!\d)(\d{1,2})\s*[./\-]\s*(\d{1,2})\s*[./\-]\s*(\d{2,4})(?!\d)")
_MONTHS = {
    "jan": 1, "january": 1, "जनवरी": 1, "feb": 2, "february": 2, "फरवरी": 2, "mar": 3, "march": 3, "मार्च": 3,
    "apr": 4, "april": 4, "अप्रैल": 4, "may": 5, "मई": 5, "jun": 6, "june": 6, "जून": 6, "jul": 7, "july": 7,
    "जुलाई": 7, "aug": 8, "august": 8, "अगस्त": 8, "sep": 9, "sept": 9, "september": 9, "सितम्बर": 9, "सितंबर": 9,
    "oct": 10, "october": 10, "अक्टूबर": 10, "nov": 11, "november": 11, "नवम्बर": 11, "नवंबर": 11,
    "dec": 12, "december": 12, "दिसम्बर": 12, "दिसंबर": 12,
}
_TEXT_DATE_RX = re.compile(
    r"(?<!\d)(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(sorted(_MONTHS, key=len, reverse=True)) + r")\.?,?\s+(\d{4})(?!\d)",
    re.I)

# which date is which, by the words next to it (before OR after)
_DATE_KINDS: list[tuple[str, str]] = [
    ("arrest_date", r"arrest\w*|गिरफ्तार\w*|giraftar\w*|custody|अभिरक्षा|jail|जेल|कारागार|निरुद्ध|detained|since"),
    ("dishonour_date", r"dishonou?r\w*|bounc\w*|return\w*|अनादर\w*|बाउंस|वापस\s+(?:आया|हुआ)"),
    ("notice_known_date", r"(?:notice|नोटिस|सूचना)\s*(?:पत्र\s*)?(?:was\s+|की\s+)?(?:served|received|delivered|तामील|प्राप्त)|"
                          r"तामील|served\s+on|received\s+(?:the\s+)?notice|service\s+of\s+(?:the\s+)?notice"),
    ("notice_date", r"notice|नोटिस|सूचना\s*पत्र|legal\s+notice"),
    ("cheque_date", r"cheque\s+dated|चेक\s+दिनांक|dated\s+cheque|cheque\s+(?:no\.?\s*\d+\s*)?dated|चेक"),
    ("marriage_date", r"marri\w*|विवाह|शादी|shadi"),
    ("conviction_date", r"convict\w*|दोषसिद्ध\w*|sentenc\w*|सजा|judgment"),
    ("order_date", r"order|आदेश|reject\w*|dismiss\w*|निरस्त|खारिज|ख़ारिज|khariz|kharij|nirast|radd"),
    ("seizure_date", r"seiz\w*|जब्त|ज़ब्त"),
    ("fir_date", r"(?:fir|एफआईआर)\s+(?:dated|registered|lodged|दिनांक|दर्ज)|registered\s+on|lodged\s+on"),
    ("transaction_date", r"loan|उधार|lent|gave|दिए|दिये|advanced|payment|transaction"),
]
_DATE_KINDS_C = [(k, re.compile(p, re.I)) for k, p in _DATE_KINDS]

_MONEY_RX = re.compile(
    r"(?:(?:rs\.?|inr|₹|रु\.?|रुपये|रुपए|rupees)\s*([\d,]+(?:\.\d+)?)\s*(lakh|lac|लाख|thousand|हजार|हज़ार|crore|करोड़)?)|"
    r"(?:([\d,]+(?:\.\d+)?)\s*(lakh|lac|लाख|thousand|हजार|हज़ार|crore|करोड़)?\s*(?:rs\.?|rupees|रुपये|रुपए|रु\.?|/-))",
    re.I)
_MONEY_KINDS: list[tuple[str, str]] = [
    ("monthly_rent", r"(?<![a-z])rent|किराया|kiraya"),
    ("respondent_income", r"income|earn\w*|salary|वेतन|(?<![ऀ-ॿ])आय(?![ऀ-ॿ])|कमाता|कमाई|kamata"),
    ("amount_sought", r"maintenance|भरण|गुजारा|खर्चा|चाहिए|chahiye|seek\w*|claim\w*\s+maintenance"),
    ("amount", r"cheque|चेक"),
    ("principal_amount", r"loan|उधार|कर्ज|lent|borrow\w*|advanced|दिए|दिये"),
    ("claim_amount", r"claim|compensation|मुआवजा|क्षतिपूर्ति"),
]
_MONEY_KINDS_C = [(k, re.compile(p, re.I)) for k, p in _MONEY_KINDS]

_OCCUPATIONS: list[tuple[str, str, str]] = [
    (r"farmer|agricultur\w*|kisan|किसान|कृषक|खेती|kheti|कृषि", "कृषि", "Agriculture"),
    (r"labou?r\w*|mazdoor|majdoor|मजदूर\w*|मज़दूर\w*|daily\s+wage", "मजदूरी", "Labour"),
    (r"driver|ड्राइवर\w*|चालक", "ड्राइवरी", "Driver"),
    (r"shopkeeper|business\w*|trader|व्यापार\w*|दुकानदार|dukandar|vyapar\w*", "व्यापार", "Business"),
    (r"student|छात्र|छात्रा|विद्यार्थी|padhai", "विद्यार्थी", "Student"),
    (r"housewife|homemaker|गृहिणी|गृहणी|grihini", "गृहकार्य", "Housewife"),
    (r"private\s+(?:job|service)|प्राइवेट\s+नौकरी|naukri|नौकरी|service", "नौकरी", "Service"),
    (r"government\s+(?:job|servant|employee)|सरकारी\s+(?:नौकरी|कर्मचारी)", "शासकीय सेवा", "Government service"),
    (r"teacher|शिक्षक|अध्यापक", "अध्यापन", "Teacher"),
    (r"unemployed|बेरोजगार", "बेरोजगार", "Unemployed"),
]
_OCC_C = [(re.compile(rf"(?<![A-Za-z{DEVA}])(?:{p})(?![A-Za-z])", re.I), hi, en) for p, hi, en in _OCCUPATIONS]

# Facts a brief STATES that the reviewed bail grounds already speak to. Only a
# statement in the brief switches a ground on; nothing is presumed.
_TOGGLE_PHRASES: dict[str, str] = {
    "prior_mag_rejected": _SUCCESSIVE.pattern,
    "parity": r"co[-\s]?accused.{0,40}(?:bail|जमानत|released)|सह\s*[-]?\s*(?:अभियुक्त|आरोपी).{0,40}(?:जमानत|रिहा)|parity|समानता",
    "breadwinner": r"(?:only|sole)\s+(?:earning|bread\s*winner|earner)|breadwinner|एकमात्र\s+(?:कमाने|कमाऊ)|"
                   r"परिवार\s+(?:का|की)\s+(?:भरण[-\s]?पोषण|जिम्मेदारी)|kamane\s+wala",
    "trial_delay": r"long\s+custody|trial\s+(?:will\s+take|delay)|(?:charge\s*sheet|chargesheet|challan)\s+(?:has\s+been\s+)?"
                   r"(?:filed|submitted|pesh)|चालान\s+(?:पेश|प्रस्तुत)|अभियोग\s*पत्र\s+(?:पेश|प्रस्तुत)|"
                   r"लंबे\s+समय\s+से\s+(?:जेल|अभिरक्षा)|विचारण\s+में\s+(?:समय|विलम्ब)",
    "respected_resident": r"permanent\s+resident|स्थायी\s+निवासी|स्थाई\s+निवासी|respect\w*\s+(?:person|family)|प्रतिष्ठित",
    "offence_upto_7yr": r"(?:less\s+than|upto|up\s+to|below|within)\s+(?:7|seven)\s+years|(?:7|सात)\s+(?:वर्ष|साल)\s+से\s+कम",
    "is_company": r"(?:pvt\.?|private)\s+(?:ltd|limited)|(?<![a-z])(?:ltd|llp)(?![a-z])|company|firm|फर्म|कंपनी|traders|enterprises",
    "dowry_cruelty": r"dowry|दहेज|dahej",
    "is_plural": r"(?:with|and)\s+(?:her\s+)?(?:\d+\s+)?(?:children|kids|son|daughter)|बच्च[ेों]|children",
    "no_prima_facie": r"no\s+prima\s+facie|प्रथम\s*दृष्टया\s+कोई",
    "complainant_is_woman": r"(?:she|woman|lady|महिला)\s+(?:complainant|परिवादिनी)|परिवादिनी",
}
_TOGGLE_C = {k: re.compile(p, re.I) for k, p in _TOGGLE_PHRASES.items()}

# Extra bail grounds for facts a brief states outright. The wording is fixed
# (it is ours, reviewed-style), the fact is his.
_STATED_GROUNDS: list[tuple[str, str, str]] = [
    (r"no\s+(?:previous\s+|prior\s+|past\s+)?(?:criminal\s+)?(?:record|antecedents?)|clean\s+record|"
     r"(?:कोई|कोइ)\s+(?:पूर्व\s+)?आपराधिक\s+(?:रिकॉर्ड|रिकार्ड|इतिहास|पृष्ठभूमि)\s+नहीं|"
     r"आपराधिक\s+(?:रिकॉर्ड|रिकार्ड)\s+नहीं|koi\s+criminal\s+record\s+nahi",
     "प्रार्थी का कोई पूर्व आपराधिक रिकॉर्ड नहीं है।",
     "The applicant has no previous criminal record."),
    (r"(?:charge\s*sheet|chargesheet|challan)\s+(?:has\s+been\s+|is\s+|already\s+)?(?:filed|submitted|pesh)|"
     r"investigation\s+(?:is\s+)?(?:complete|over)|विवेचना\s+पूर्ण|चालान\s+(?:पेश|प्रस्तुत)|अभियोग\s*पत्र\s+(?:पेश|प्रस्तुत)",
     "प्रकरण में विवेचना पूर्ण होकर अभियोग पत्र प्रस्तुत किया जा चुका है, अतः प्रार्थी को अभिरक्षा में रखे जाने से कोई प्रयोजन सिद्ध नहीं होगा।",
     "Investigation is complete and the charge-sheet has been filed; no purpose would be served by keeping the applicant in custody."),
    (r"(?:nothing|no)\s+(?:was\s+)?recover\w*|कोई\s+(?:बरामदगी|जप्ती|जब्ती)\s+नहीं|बरामदगी\s+नहीं",
     "प्रार्थी से प्रकरण में कोई बरामदगी नहीं हुई है।",
     "Nothing has been recovered from the applicant."),
    (r"(?:is\s+)?(?:ill|sick|unwell)(?![a-z])|बीमार|अस्वस्थ|medical\s+(?:treatment|condition)|इलाज",
     "प्रार्थी अस्वस्थ है तथा उसे उपचार की आवश्यकता है।",
     "The applicant is unwell and requires medical treatment."),
]
_STATED_GROUNDS_C = [(re.compile(p, re.I), hi, en) for p, hi, en in _STATED_GROUNDS]

_VEHICLE_RX = re.compile(
    rf"((?:motor\s*cycle|motorcycle|bike|scooty|scooter|car|truck|tractor|jeep|auto|pickup|mobile\s*phone|mobile|"
    rf"मोटर\s*साइकिल|मोटरसाइकिल|स्कूटी|कार|ट्रक|ट्रैक्टर|जीप|ऑटो|मोबाइल)"
    rf")", re.I)
_REGNO_RX = re.compile(r"(?<![A-Za-z0-9])([A-Z]{2}\s?-?\s?\d{1,2}\s?-?\s?[A-Z]{0,3}\s?-?\s?\d{3,4})(?![A-Za-z0-9])")
_CHEQUE_NO_RX = re.compile(r"(?:cheque|चेक)\s*(?:no\.?|number|नं\.?|क्रमांक|संख्या|#)\s*[:\-–]?\s*(\d{4,10})", re.I)
_BANK_RX = re.compile(
    r"((?:state\s+bank\s+of\s+india|sbi|punjab\s+national\s+bank|pnb|bank\s+of\s+baroda|bob|hdfc(?:\s+bank)?|"
    r"icici(?:\s+bank)?|axis(?:\s+bank)?|canara\s+bank|union\s+bank(?:\s+of\s+india)?|central\s+bank(?:\s+of\s+india)?|"
    r"bank\s+of\s+india|indian\s+bank|uco\s+bank|idbi(?:\s+bank)?|kotak(?:\s+mahindra)?(?:\s+bank)?|yes\s+bank|"
    r"indusind(?:\s+bank)?|bank\s+of\s+maharashtra|[a-z]+\s+(?:co-?operative|sahkari)\s+bank|"
    r"स्टेट\s+बैंक(?:\s+ऑफ\s+इंडिया)?|पंजाब\s+नेशनल\s+बैंक|बैंक\s+ऑफ\s+बड़ौदा|सेंट्रल\s+बैंक|केनरा\s+बैंक|"
    r"यूनियन\s+बैंक|[ऀ-ॿ]+\s+सहकारी\s+बैंक)(?:[,\s]+(?:branch|शाखा)\s*[:\-]?\s*[A-Za-zऀ-ॿ]+|\s+[A-Za-zऀ-ॿ]+\s+(?:branch|शाखा))?)", re.I)
_REASON_RX = [
    (re.compile(r"insufficient\s+funds?|funds?\s+insufficient|अपर्याप्त\s+(?:राशि|निधि)|पैसे\s+(?:नहीं|कम)", re.I),
     "अपर्याप्त निधि (Funds Insufficient)", "Funds Insufficient"),
    (re.compile(r"account\s+closed|खाता\s+बंद", re.I), "खाता बंद (Account Closed)", "Account Closed"),
    (re.compile(r"payment\s+stopped|stop\s+payment|भुगतान\s+रोक", re.I), "भुगतान रोका गया (Payment Stopped by Drawer)",
     "Payment Stopped by Drawer"),
    (re.compile(r"signature\s+(?:mismatch|differ)|हस्ताक्षर\s+(?:भिन्न|मेल\s+नहीं)", re.I),
     "हस्ताक्षर भिन्न (Signature Differs)", "Signature Differs"),
    (re.compile(r"exceeds\s+arrangement", re.I), "व्यवस्था से अधिक (Exceeds Arrangement)", "Exceeds Arrangement"),
]


def _fmt_date(d: int, m: int, y: int) -> Optional[str]:
    if y < 100:
        y += 2000 if y <= 60 else 1900
    if not (1 <= d <= 31 and 1 <= m <= 12 and 1950 <= y <= 2100):
        return None
    return f"{d:02d}/{m:02d}/{y}"


def _dates(text: str) -> list[tuple[int, int, str]]:
    out: list[tuple[int, int, str]] = []
    for m in _DATE_RX.finditer(text):
        v = _fmt_date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        if v:
            out.append((m.start(), m.end(), v))
    for m in _TEXT_DATE_RX.finditer(text):
        v = _fmt_date(int(m.group(1)), _MONTHS[m.group(2).lower()], int(m.group(3)))
        if v:
            out.append((m.start(), m.end(), v))
    return sorted(out)


def _money_value(num: str, unit: str) -> str:
    n = float(num.replace(",", ""))
    u = (unit or "").lower()
    if u in ("lakh", "lac", "लाख"):
        n *= 100000
    elif u in ("thousand", "हजार", "हज़ार"):
        n *= 1000
    elif u in ("crore", "करोड़"):
        n *= 10000000
    return str(int(n)) if n == int(n) else str(n)


def _words_until(text: str, start: int, stop_rx: re.Pattern, max_words: int, *, stop_at_place: bool = False) -> tuple[str, int]:
    seg = text[start:start + 120]
    stop = stop_rx.search(seg)
    if stop:
        seg = seg[:stop.start()]
    words: list[tuple[str, int]] = []
    for t in _TOK_RX.finditer(seg):
        w = t.group(0)
        if words and re.search(r"[,;:।\n]", seg[words[-1][1]:t.start()]):
            break
        if _is_stop(w) and w.lower() not in ("road", "nagar", "colony"):
            break
        if stop_at_place and words and GEO.lookup(w) and not GEO.is_weak(w):
            break
        words.append((w, t.end()))
        if len(words) >= max_words:
            break
    if not words:
        return "", start
    return " ".join(w for w, _ in words).strip(" ,.-"), start + words[-1][1]


class Found:
    """One extracted value and the words of the brief it came from."""
    __slots__ = ("value", "source", "span", "note")

    def __init__(self, value, source: str = "brief", span: str = "", note: str = ""):
        self.value, self.source, self.span, self.note = value, source, span, note

    def to_dict(self) -> dict:
        return {"value": self.value, "source": self.source, "span": self.span, "note": self.note}


def facts(brief: str) -> dict:
    """Every template-independent fact in the brief. `extract` maps these onto one
    template's own field keys."""
    text = _nfc(brief)
    out: dict = {}

    people = _find_people(text)
    name_spans = [(p.start, p.end) for p in people]

    def inside_name(s: int, e: int) -> bool:
        return any(s < ne and e > ns for ns, ne in name_spans)

    # ---- age / address / occupation attach to the nearest person BEFORE them
    def owner(pos: int) -> Optional[Person]:
        prior = [p for p in people if p.start <= pos]
        return prior[-1] if prior else (people[0] if people else None)

    for m in _AGE_RX.finditer(text):
        n = int(m.group(1) or m.group(2))
        if m.group(2) and (n < 12 or re.search(r"(?:sentenc\w*|imprison\w*|RI|rigorous|simple|सजा|कारावास|for|last|since|"
                                                 r"from|past|में|से|का\s+कारावास|custody)\s*(?:to\s+|of\s+)?$",
                                                 text[max(0, m.start() - 22):m.start()], re.I)):
            continue
        if 5 <= n <= 99:
            p = owner(m.start())
            if p is not None and not p.age:
                p.age, p.evidence["age"] = str(n), m.group(0)
            elif p is None:
                out.setdefault("age", Found(str(n), span=m.group(0)))

    for m in list(_ADDR_RX.finditer(text)) + [v for v in _VILLAGE_RX.finditer(text)]:
        seg = text[m.end():m.end() + 140]
        stop = _ADDR_STOP.search(seg)
        raw = seg[:stop.start()] if stop else seg
        # an address never runs into the next person's name
        for p in people:
            if m.end() < p.start < m.end() + len(raw):
                raw = raw[:p.start - m.end()]
        raw = re.sub(r"\s+(?:and|aur|और|evam|एवं)\s*$", "", raw).strip(" ,.-–")
        if not raw:
            continue
        is_village = m.re is _VILLAGE_RX
        value = (m.group(0).strip() + " " + raw) if is_village else raw
        value = re.sub(r"^(?:village|vill\.?)\s+", "Village ", value, flags=re.I)
        value = re.sub(r"^gram\s+", "Gram ", value, flags=re.I)
        p = owner(m.start())
        if p is not None and not p.address:
            p.address, p.evidence["address"] = value, text[m.start():m.end() + len(raw)]
        elif p is None and "address" not in out:
            out["address"] = Found(value, span=text[m.start():m.end() + len(raw)])

    for rx, hi, en in _OCC_C:
        m = rx.search(text)
        if m:
            p = owner(m.start())
            if p is not None and not p.occupation:
                p.occupation, p.evidence["occupation"] = f"{hi}|{en}", m.group(0)
            break

    out["people"] = people

    # ---- police station
    qm = re.search(rf"(?<![A-Za-z{DEVA}])((?:mahila|महिला|ajak|अजाक|cyber|साइबर|traffic|यातायात|gramin|ग्रामीण|"
                   rf"sc\s*/\s*st|women)\s+(?:thana|थाना|police\s+station|ps))(?![A-Za-z])", text, re.I)
    if qm:
        out["police_station"] = Found(qm.group(1), span=qm.group(0))
    for m in ([] if qm else _PS_RX.finditer(text)):
        seg_ps = text[m.end():m.end() + 60]
        gk = re.match(r"([A-Za-z]+\s+(?:ka|ki|ke)\s+[A-Za-z]+|[ऀ-ॣॱ-ॿ]+\s+(?:का|की|के)\s+[ऀ-ॣॱ-ॿ]+)(?=\s|,|$)", seg_ps, re.I)
        if gk and not _is_stop(gk.group(1).split()[0]) and not re.search(r"(?:mein|में|jail|जेल|court|कोर्ट)$", gk.group(1), re.I):
            out["police_station"] = Found(gk.group(1).strip(), span=text[m.start():m.end() + gk.end()])
            break
        name, end = _words_until(text, m.end(), re.compile(
            r"(?:district|distt|dist\.|zila|jila|janpad|जिला|जिले|ज़िला|जनपद|\bfir\b|एफ\.?आई|अपराध|crime|\bu/s|धारा|section|"
            r"\bmein\b|\bme\b|में|\bin\b|द्वारा|\bne\b|ने|पर|से|\bki\b|की|का|के|\bis\b|\bcase\b|[.;।\n(]|\d)", re.I),
            3, stop_at_place=True)
        if name and not re.match(r"^(?:in|me|mein|no|number)$", name, re.I):
            out["police_station"] = Found(name, span=text[m.start():end])
            break

    # ---- district: explicit marker first
    for m in _DIST_RX.finditer(text):
        name, end = _words_until(text, m.end(), re.compile(r"[.;।\n(,]|\d|\bfir\b|\bu/s|धारा|thana|थाना", re.I), 3)
        if name and _NOT_A_DISTRICT.match(name):
            continue
        if name:
            if not GEO.lookup(name) and any(GEO.lookup(w) for w in name.split()):
                name = next(w for w in name.split() if GEO.lookup(w))
            p = GEO.lookup(name) or (GEO.lookup(name.split()[0]) if name.split() else None)
            if p:
                out["district"] = Found(p, span=text[m.start():end])
            else:
                out["district"] = Found(name, span=text[m.start():end])
            break

    # ---- court's city: a place beside a court word
    places = [(s, e, p) for s, e, p in GEO.find_places(text) if not inside_name(s, e)]
    court_rx = re.compile("|".join(f"(?:{v})" for v in _COURT_WORDS.values()) +
                          r"|(?<![A-Za-z])court|कोर्ट|न्यायालय|adalat|अदालत|bench|बेंच", re.I)
    for s, e, p in places:
        before, after = text[max(0, s - 32):s], text[e:e + 32]
        if court_rx.search(before) or re.match(r"\s*(?:" + court_rx.pattern + ")", after, re.I):
            if GEO.is_weak(text[s:e]) and not re.search(r"(?:court|न्यायालय|कोर्ट)\s*[,:]?\s*$", before, re.I):
                continue
            window = text[max(0, s - 50):e + 50]
            if _REJECT.search(window):
                out.setdefault("prior_court_city", Found(p, span=text[s:e]))
                continue
            out["court_city"] = Found(p, span=text[max(0, s - 32):e].strip())
            break
    # no marked district: an unmarked, unambiguous, strong place becomes the district
    if "district" not in out:
        strong = [(s, e, p) for s, e, p in places if not GEO.is_weak(text[s:e])]
        distinct = {p.en: (s, e, p) for s, e, p in strong}
        if len(distinct) == 1:
            s, e, p = next(iter(distinct.values()))
            out["district"] = Found(p, source="brief", span=text[s:e])

    st = GEO.find_state(text)
    if st:
        out["state"] = Found(st, span=st)

    # ---- FIR / case number
    m = _FIR_RX.search(text)
    if m:
        y = m.group(2)
        y = ("20" + y) if len(y) == 2 else y
        out["fir"] = Found(f"{int(m.group(1))}/{y}", span=m.group(0).strip())
    m = _CASE_RX.search(text)
    if m and "fir" not in out and re.search(r"(?:p\.?\s?s\.?|thana|थाना|police\s+station)\s+\S+(?:\s+\S+)?\s*$",
                                             text[max(0, m.start() - 30):m.start()], re.I):
        out["fir"] = Found(f"{int(m.group(1))}/{('20' + m.group(2)) if len(m.group(2)) == 2 else m.group(2)}",
                           span=m.group(0).strip())
        m = None
    if m:
        y = m.group(2)
        y = ("20" + y) if len(y) == 2 else y
        out["case_no"] = Found((str(int(m.group(1))), y), span=m.group(0).strip())

    # ---- sections + act
    groups: list[dict] = []
    for m in _SEC_MARK.finditer(text):
        pos, nums = m.end(), []
        while True:
            t = _SEC_TOKEN.match(text, pos)
            if not t or not re.match(r"\d", t.group(1)):
                break
            val = re.sub(r"\s+", "", t.group(1))
            if len(re.match(r"\d+", val).group(0)) > 3:
                break
            nums.append(val)
            pos = t.end()
            sep = _SEC_SEP.match(text, pos)
            if sep and _SEC_TOKEN.match(text, sep.end()) and re.match(r"\s*\d", text[sep.end():]):
                pos = sep.end()
                continue
            break
        if not nums:
            continue
        act = None
        for rx, hi, en in _ACTS_C:
            am = rx.match(text, pos)
            if am:
                act = (hi, en)
                pos = am.end()
                break
        if act is None:   # "IPC section 420" — the Act before the marker
            pre = text[max(0, m.start() - 22):m.start()]
            for rx, hi, en in _ACTS_TAIL:
                if rx.search(pre):
                    act = (hi, en)
                    break
        groups.append({"nums": nums, "act": act, "span": text[m.start():pos]})
        while act:
            cont = re.match(r"\s*(?:and|&|,|एवं|व|तथा)\s*(?:(?:u/s|section|sec\.?|धारा)\s*)?", text[pos:], re.I)
            if not cont:
                break
            p2, nums2 = pos + cont.end(), []
            while True:
                t = _SEC_TOKEN.match(text, p2)
                if not t or not re.match(r"\d", t.group(1)) or len(re.match(r"\d+", t.group(1)).group(0)) > 3:
                    break
                nums2.append(re.sub(r"\s+", "", t.group(1)))
                p2 = t.end()
                sep = _SEC_SEP.match(text, p2)
                if sep and re.match(r"\s*\d", text[sep.end():]):
                    p2 = sep.end()
                    continue
                break
            act2 = None
            for rx, hi, en in _ACTS_C:
                am = rx.match(text, p2)
                if am:
                    act2, p2 = (hi, en), am.end()
                    break
            if not nums2 or not act2:
                break
            groups.append({"nums": nums2, "act": act2, "span": text[pos:p2]})
            pos, act = p2, act2
    # the procedural provision he is applying under ("application u/s 483 BNSS")
    # is not an offence — drop CrPC/BNSS groups when offence groups exist
    offence = [g for g in groups if not (g["act"] and g["act"][1] in ("CrPC", "BNSS"))]
    if offence:
        out["sections"] = Found(offence, span="; ".join(g["span"] for g in offence))

    # ---- dates, each by the words around it
    used: set[str] = set()
    all_dates = _dates(text)
    for idx, (s, e, v) in enumerate(all_dates):
        # the words around a date belong to it only up to the NEIGHBOURING date —
        # "rejected 05/08/2024 ko, 12/07/2024 se jail" must not give the first date
        # the second date's "jail"
        prev_end = all_dates[idx - 1][1] if idx else 0
        next_start = all_dates[idx + 1][0] if idx + 1 < len(all_dates) else len(text)
        before = text[max(prev_end, s - 55):s]
        after = text[e:min(next_start, e + 44)]
        # Indian briefs name the thing first — "चेक … दिनांक 01/07", "dishonoured on
        # 10/06", "arrested on …" — so the nearest label BEFORE the date decides.
        # Only a date with no label before it looks after ("12/07/2024 se jail").
        kind, best = None, 10 ** 6
        for k, rx in _DATE_KINDS_C:
            if k in used:
                continue
            for mm in rx.finditer(before):
                d = len(before) - mm.end()
                if d < best:
                    kind, best = k, d
        if kind is None:
            for k, rx in _DATE_KINDS_C:
                if k in used:
                    continue
                mm = rx.search(after[:40])
                if mm and mm.start() < best:
                    kind, best = k, mm.start()
        if kind:
            used.add(kind)
            out[kind] = Found(v, span=text[max(0, s - 28):e].strip())
        else:
            out.setdefault("dates_unlabelled", []).append(Found(v, span=text[s:e]))

    # ---- money
    for m in _MONEY_RX.finditer(text):
        num, unit = (m.group(1), m.group(2)) if m.group(1) else (m.group(3), m.group(4))
        if not num or not re.search(r"\d", num):
            continue
        val = _money_value(num, unit)
        ctx = text[max(0, m.start() - 40):m.end() + 25]
        for k, rx in _MONEY_KINDS_C:
            if k not in out and rx.search(ctx):
                out[k] = Found(val, span=m.group(0).strip())
                break
        else:
            out.setdefault("money", Found(val, span=m.group(0).strip()))

    # ---- §138 specifics
    m = _CHEQUE_NO_RX.search(text)
    if m:
        out["cheque_no"] = Found(m.group(1), span=m.group(0))
    banks = [b.group(1).strip() for b in _BANK_RX.finditer(text)]
    if banks:
        out["banks"] = Found(banks, span=", ".join(banks))
    for rx, hi, en in _REASON_RX:
        rm = rx.search(text)
        if rm:
            out["dishonour_reason"] = Found(f"{hi}|{en}", span=rm.group(0))
            break

    # ---- seized property (supurdgi) / vehicle
    vm = _VEHICLE_RX.search(text)
    rm = _REGNO_RX.search(text)
    if rm:
        out["vehicle_no"] = Found(re.sub(r"\s+", " ", rm.group(1)).strip(), span=rm.group(0))
    if vm:
        desc = vm.group(1).strip(" ,")
        if rm and 0 <= rm.start() - vm.end() <= 25:
            desc = f"{desc} {out['vehicle_no'].value}"
        out["property"] = Found(desc, span=text[vm.start():(rm.end() if rm and 0 <= rm.start() - vm.end() <= 25 else vm.end())])

    # ---- stated grounds / toggles
    out["toggles"] = {k: rx.search(text).group(0) for k, rx in _TOGGLE_C.items() if rx.search(text)}
    out["grounds"] = [(hi, en, rx.search(text).group(0)) for rx, hi, en in _STATED_GROUNDS_C if rx.search(text)]
    out["courts"] = _courts(text)
    return out


# =========================================================================== mapping onto a template
# (role prefix a template uses) → the hints that may fill it, in preference order.
_ROLE_ACCEPTS: dict[str, tuple[str, ...]] = {
    "applicant": ("applicant", "accused", "client", "owner", "petitioner"),
    "appellant": ("appellant", "accused", "client", "applicant"),
    "revisionist": ("revisionist", "accused", "client", "applicant"),
    "accused": ("accused", "against"),
    "complainant": ("complainant", "client"),
    "petitioner": ("petitioner", "wife", "client", "applicant"),
    "aggrieved": ("wife", "client", "applicant", "complainant"),
    "husband": ("husband", "against", "respondent", "accused"),
    "respondent": ("respondent", "husband", "against"),
    "plaintiff": ("plaintiff", "landlord", "client"),
    "defendant": ("defendant", "tenant", "against"),
    "deponent": ("deponent", "client", "applicant"),
    "client": ("client", "applicant", "accused", "complainant", "plaintiff", "petitioner"),
    "recipient": ("against", "respondent", "defendant", "accused"),
    "claimant": ("client", "applicant", "petitioner"),
    "detenu": ("detenu", "accused"),
}
# a hint that says "this is the OTHER side" can never fill the advocate's own party
_OPPOSED = {"against", "tenant", "husband", "defendant", "respondent"}
_OWN_ROLES = {"applicant", "appellant", "revisionist", "petitioner", "aggrieved", "plaintiff", "deponent",
              "client", "claimant", "complainant"}
# templates where the advocate acts for the side whose role is NOT first in the spec
_PRIMARY_OVERRIDE = {"reply_magistrate": "respondent", "reply_sessions": "respondent", "reply_hc": "respondent",
                     "written_statement": "defendant", "ni_138_dismiss": "accused"}


def _roles_in(spec_fields: list[dict]) -> list[str]:
    roles: list[str] = []
    for f in spec_fields:
        k = f["key"]
        m = re.match(r"^([a-z]+)_(?:name|names|desc)$", k)
        if m and m.group(1) not in ("advocate", "court", "state", "company", "jail", "case", "client_father") \
                and m.group(1) not in roles:
            roles.append(m.group(1))
    return roles


# A matrimonial petition can be brought by EITHER spouse, so "husband"/"wife" says
# nothing about which side he is on — only "by"/"against" does.
_MATRIMONIAL = {"divorce_13", "restitution_9"}
_MATRIMONIAL_ACCEPTS = {"applicant": ("applicant", "petitioner", "client", "husband", "wife"),
                        "respondent": ("respondent", "against", "wife", "husband")}


def _assign(people: list[Person], roles: list[str], tid: str) -> dict[str, Person]:
    out: dict[str, Person] = {}
    taken: set[int] = set()
    order = list(roles)
    accepts = dict(_ROLE_ACCEPTS)
    if tid in _MATRIMONIAL:
        accepts.update(_MATRIMONIAL_ACCEPTS)
    primary = _PRIMARY_OVERRIDE.get(tid)
    if primary in order:
        order.remove(primary)
        order.insert(0, primary)
    # 1) explicit hints
    for role in order:
        for want in accepts.get(role, (role,)):
            for i, p in enumerate(people):
                if i not in taken and want in p.hints:
                    if role in _OWN_ROLES and "against" in p.hints and want != role:
                        continue
                    if role in _OWN_ROLES and tid not in _MATRIMONIAL and \
                            any(h in _OPPOSED for h in p.hints) and want != role:
                        continue
                    out[role] = p
                    taken.add(i)
                    break
            if role in out:
                break
    # 2) the rest, in the order he mentioned them
    free = [i for i in range(len(people)) if i not in taken]
    for role in order:
        if role in out or not free:
            continue
        i = free[0]
        p = people[i]
        if role in _OWN_ROLES and any(h in _OPPOSED for h in p.hints):
            continue
        out[role] = p
        taken.add(i)
        free.pop(0)
    return out


def _localise_place(v, lang: str) -> tuple[str, bool]:
    if isinstance(v, GEO.Place):
        return v.name(lang), False
    return _script(str(v), lang)


def _script(v: str, lang: str) -> tuple[str, bool]:
    """A value typed in one script, for a document in another. Returns (value,
    converted). Converted values are flagged so the screen asks him to check."""
    from headnote.drafter import transliterate as TR
    if not v:
        return v, False
    if lang == "hi" and not is_deva(v) and re.search(r"[A-Za-z]", v):
        place = GEO.lookup(v)
        if place:
            return place.hi, False
        return translit_to_hi(v), True
    if lang == "en" and is_deva(v):
        place = GEO.lookup(v)
        if place:
            return place.en, False
        return TR.hi_to_en(v), True
    return v, False


# name parts the phonetic engine gets wrong on its own ("Ramkumar" → "रंकुमर")
_NAME_PARTS = {
    "ram": "राम", "shyam": "श्याम", "lal": "लाल", "chand": "चंद", "prasad": "प्रसाद", "nath": "नाथ",
    "devi": "देवी", "bai": "बाई", "kumari": "कुमारी", "kumar": "कुमार", "singh": "सिंह", "pal": "पाल",
    "das": "दास", "mohan": "मोहन", "kishan": "किशन", "kishore": "किशोर", "narayan": "नारायण",
    "prakash": "प्रकाश", "sharma": "शर्मा", "verma": "वर्मा", "gupta": "गुप्ता", "yadav": "यादव",
    "jain": "जैन", "khan": "खान", "ahmed": "अहमद", "ahmad": "अहमद", "mohammad": "मोहम्मद",
    "mohammed": "मोहम्मद", "ali": "अली", "raj": "राज", "rajesh": "राजेश", "suresh": "सुरेश",
    "ramesh": "रमेश", "mahesh": "महेश", "dinesh": "दिनेश", "ganesh": "गणेश", "rakesh": "राकेश",
    "mukesh": "मुकेश", "naresh": "नरेश", "umesh": "उमेश", "kamlesh": "कमलेश", "santosh": "संतोष",
    "ashok": "अशोक", "anil": "अनिल", "sunil": "सुनील", "vijay": "विजय", "ajay": "अजय", "sanjay": "संजय",
    "manoj": "मनोज", "pawan": "पवन", "pradeep": "प्रदीप", "sandeep": "संदीप", "deepak": "दीपक",
    "vinod": "विनोद", "pramod": "प्रमोद", "arvind": "अरविंद", "govind": "गोविंद", "krishna": "कृष्णा",
    "sita": "सीता", "gita": "गीता", "geeta": "गीता", "laxmi": "लक्ष्मी", "lakshmi": "लक्ष्मी",
    "sunita": "सुनीता", "anita": "अनीता", "kavita": "कविता", "savita": "सविता", "rekha": "रेखा",
    "pooja": "पूजा", "priya": "प्रिया", "neha": "नेहा", "rani": "रानी", "shiv": "शिव", "hari": "हरि",
    "om": "ओम", "jai": "जय", "ravi": "रवि", "amit": "अमित", "sumit": "सुमित", "rahul": "राहुल",
    "rohit": "रोहित", "mohit": "मोहित", "ankit": "अंकित", "vikas": "विकास", "vikash": "विकास",
    "akash": "आकाश", "gopal": "गोपाल", "bhagwan": "भगवान", "bharat": "भरत", "lakhan": "लखन",
    "babu": "बाबू", "bahadur": "बहादुर", "pratap": "प्रताप", "veer": "वीर", "bir": "बीर",
    "tiwari": "तिवारी", "mishra": "मिश्रा", "pandey": "पाण्डेय", "dubey": "दुबे", "shukla": "शुक्ला",
    "chauhan": "चौहान", "rathore": "राठौर", "kushwaha": "कुशवाहा", "patel": "पटेल", "sahu": "साहू",
    "rajput": "राजपूत", "thakur": "ठाकुर", "meena": "मीणा", "jatav": "जाटव", "kewat": "केवट",
    "lodhi": "लोधी", "gurjar": "गुर्जर", "baghel": "बघेल", "tomar": "तोमर", "bhadoria": "भदौरिया",
    "sikarwar": "सिकरवार", "agrawal": "अग्रवाल", "agarwal": "अग्रवाल", "goyal": "गोयल", "bansal": "बंसल",
    "soni": "सोनी", "rai": "राय", "roy": "राय", "saxena": "सक्सेना", "srivastava": "श्रीवास्तव",
    "shrivastava": "श्रीवास्तव", "dixit": "दीक्षित", "joshi": "जोशी", "parmar": "परमार", "solanki": "सोलंकी",
    "dhakad": "धाकड़", "ahirwar": "अहिरवार", "prajapati": "प्रजापति", "rawat": "रावत", "negi": "नेगी",
    "bhai": "भाई", "ben": "बेन", "begum": "बेगम", "bano": "बानो", "khatoon": "खातून", "hussain": "हुसैन",
    "shaikh": "शेख", "sheikh": "शेख", "qureshi": "कुरैशी", "ansari": "अंसारी", "mansoori": "मंसूरी",
    "kotwali": "कोतवाली", "city": "सिटी", "civil": "सिविल", "lines": "लाइंस", "cantt": "कैंट",
    "road": "रोड", "nagar": "नगर", "pur": "पुर", "garh": "गढ़", "ganj": "गंज", "abad": "आबाद",
    "gaon": "गांव", "gram": "ग्राम", "village": "ग्राम", "colony": "कॉलोनी", "mohalla": "मोहल्ला",
    "ward": "वार्ड", "chowk": "चौक", "bazar": "बाजार", "market": "मार्केट", "khurd": "खुर्द",
    "kalan": "कलां", "tola": "टोला", "basti": "बस्ती", "station": "स्टेशन", "police": "पुलिस",
    "mahila": "महिला", "thana": "थाना", "kheda": "खेड़ा", "khera": "खेड़ा",
}


def translit_to_hi(text: str) -> str:
    """Latin → Devanagari for names and places: whole-word dictionary, then the
    longest known name parts ("Ramkumar" = ram + kumar), then the phonetic engine
    only for what is left. Always surfaced to him as "check the spelling"."""
    from headnote.drafter import transliterate as TR

    def word(w: str) -> str:
        lw = w.lower().strip(".")
        if not lw.isalpha():
            return w
        if lw in _NAME_PARTS:
            return _NAME_PARTS[lw]
        if lw in TR.HI_DICT:
            return TR.HI_DICT[lw]
        # greedy segmentation into known parts; phonetic for the remainder
        i, parts, ok = 0, [], True
        while i < len(lw):
            for j in range(len(lw), i + 1, -1):
                chunk = lw[i:j]
                if chunk in _NAME_PARTS and len(chunk) >= 2:
                    parts.append(_NAME_PARTS[chunk])
                    i = j
                    break
            else:
                ok = False
                break
        if ok and parts:
            return "".join(parts)
        return TR.phonetic_to_hi(w)

    return re.sub(r"[A-Za-z][A-Za-z.]*", lambda m: word(m.group(0)), text)


def _sections_value(groups: list[dict], lang: str) -> list[str]:
    items: list[str] = []
    for g in groups:
        nums = list(g["nums"])
        if g["act"]:
            act = g["act"][0] if lang == "hi" else g["act"][1]
            nums[-1] = f"{nums[-1]} {act}"
        items.extend(nums)
    return items


def extract(brief: str, tid: str, lang: str = "hi") -> dict:
    """The brief's facts, placed into THIS template's own fields.

    Returns {"fields": {key: value}, "evidence": {key: {source, span, note}},
             "converted": [keys whose script was converted], "notes": [...]}"""
    from headnote.drafter import template_adapter as TA

    spec = TA._spec(tid)
    fields_spec = spec.get("fields", [])
    keys = {f["key"]: f for f in fields_spec}
    toggle_keys = {t["key"] for t in spec.get("toggles", [])}
    F = facts(brief)
    vals: dict = {}
    ev: dict = {}
    converted: list[str] = []
    notes: list[str] = []

    def put(key: str, value, *, source="brief", span="", note="", convert=False):
        if key not in keys or value in (None, "", []):
            return
        if isinstance(value, str) and convert:
            value, conv = _script(value, lang)
            if conv:
                converted.append(key)
                source = "converted" if source == "brief" else source
        if isinstance(value, str):
            value = re.sub(r"\s*@\s*", " उर्फ " if lang == "hi" else " @ ", value).strip()
        vals[key] = value
        ev[key] = {"source": source, "span": span, "note": note}

    # ---- parties
    roles = _roles_in(fields_spec)
    assigned = _assign(F["people"], roles, tid)
    for role, p in assigned.items():
        nk = f"{role}_name" if f"{role}_name" in keys else (f"{role}_names" if f"{role}_names" in keys else None)
        if nk is None and f"{role}_desc" in keys:
            put(f"{role}_desc", p.name, span=p.name, convert=True)
        elif nk:
            put(nk, p.name, span=p.evidence.get("relative", p.name), convert=True)
        if p.relative:
            if p.relation == "wife" and "husband_name" in keys:
                fk = "husband_name" if "husband_name" not in vals else None
            else:
                fk = next((k for k in (f"{role}_spouse" if p.relation == "wife" else "", f"{role}_father") if k in keys), None)
            if fk:
                put(fk, p.relative, span=p.evidence.get("relative", ""), convert=True)
        if p.age:
            put(f"{role}_age", p.age, span=p.evidence.get("age", ""))
        if p.address:
            put(f"{role}_address", p.address, span=p.evidence.get("address", ""), convert=True)
        if p.occupation:
            hi, en = p.occupation.split("|")
            put(f"{role}_occupation", hi if lang == "hi" else en, span=p.evidence.get("occupation", ""))
    if "recipient_name" in keys and "recipient_name" not in vals:
        rm = re.search(r"(?<![A-Za-z])to\s+(?:m/s\.?\s+|mr\.?\s+|shri\s+)?((?:[A-Z][\w.&]*)(?:\s+[A-Z][\w.&]*){0,3})", _nfc(brief))
        hm = re.search(r"([ऀ-ॿ]+(?:\s+[ऀ-ॿ]+){0,2})\s+को\s+(?:विधिक\s+|कानूनी\s+)?(?:नोटिस|सूचना)", _nfc(brief))
        cand = rm.group(1) if rm else (hm.group(1) if hm else "")
        cand = " ".join(w for w in cand.split() if not _is_stop(w))
        if cand and all(cand.lower() != v.lower() for v in vals.values() if isinstance(v, str)):
            put("recipient_name", cand, span=(rm or hm).group(0), convert=True)
    # unattached address / age (brief with no recognisable name)
    own = next((r for r in roles if r in _OWN_ROLES or r == _PRIMARY_OVERRIDE.get(tid)), roles[0] if roles else None)
    if own:
        if "address" in F and f"{own}_address" not in vals:
            put(f"{own}_address", F["address"].value, span=F["address"].span, convert=True)
        if "age" in F and f"{own}_age" not in vals:
            put(f"{own}_age", F["age"].value, span=F["age"].span)
    # the discharge/production family names the accused as one free-text field
    if "accused_names" in keys and "accused_names" not in vals and F["people"]:
        ps = [p for p in F["people"] if not any(h in ("complainant", "against") for h in p.hints)]
        if ps:
            put("accused_names", ", ".join(p.name for p in ps), span=", ".join(p.name for p in ps), convert=True)

    # ---- place: police station, district, court city, state
    if "police_station" in F:
        put("police_station", F["police_station"].value, span=F["police_station"].span, convert=True)
    district = F.get("district")
    if district is not None:
        v, conv = _localise_place(district.value, lang)
        if "district" in keys:
            put("district", v, span=district.span)
            if conv:
                converted.append("district")
    court_city = F.get("court_city")
    city_key = "court_city" if "court_city" in keys else None
    if city_key:
        if court_city is not None:
            v, conv = _localise_place(court_city.value, lang)
            put(city_key, v, span=court_city.span)
            if conv:
                converted.append(city_key)
        elif district is not None:
            v, _ = _localise_place(district.value, lang)
            put(city_key, v, source="inferred", span=district.span,
                note="The court's city is taken from the district in your brief — change it if you file elsewhere.")
    # the address line in the bail family prints ", जिला <district>" itself — strip a
    # trailing district from the extracted address so it does not print twice
    for k in list(vals):
        if k.endswith("_address") and "district" in vals and isinstance(vals[k], str):
            vals[k] = re.sub(rf"[,\s]*(?:district|distt\.?|dist\.?|zila|jila|जिला|जिले|जनपद|janpad)\s*[:\-]?\s*{re.escape(vals['district'])}\s*$",
                             "", vals[k], flags=re.I).strip(" ,")
    city_place = (court_city.value if court_city is not None else (district.value if district is not None else None))
    if "place" in keys and city_place is not None:
        put("place", _localise_place(city_place, lang)[0], source="inferred",
            span=(court_city or district).span, note="The place of filing is taken from the court's city.")
    # court_name is the ENGINE's to compose on most templates (an `auto` field); only
    # where it is a plain field he types (§138, vakalatnama, MACT) do we write it
    if "court_name" in keys and not keys["court_name"].get("auto") and city_place is not None:
        from headnote.drafter.templates._doc_header import compose_court_name
        level = F["courts"]["target"] or {"cheque_138": "magistrate"}.get(tid)
        st = F["state"].value if "state" in F else (city_place.state if isinstance(city_place, GEO.Place) else None)
        if level:
            put("court_name", compose_court_name(level, _localise_place(city_place, lang)[0],
                                                 GEO.state_name(st, lang), lang=lang),
                source="inferred", span=(court_city or district).span,
                note="The court is composed from the court and city in your brief — check the designation.")
    if "state_name" in keys:
        st_key = F["state"].value if "state" in F else None
        source = "brief"
        if not st_key:
            for cand in (court_city, district):
                if cand is not None and isinstance(cand.value, GEO.Place) and cand.value.state:
                    st_key, source = cand.value.state, "inferred"
                    break
        if st_key:
            put("state_name", GEO.state_name(st_key, lang), source=source,
                note="" if source == "brief" else "The State is taken from the district in your brief.")

    # ---- FIR / sections
    if "fir" in F:
        for k in ("fir_number", "crime_number", "case_no"):
            if k in keys:
                put(k, F["fir"].value, span=F["fir"].span)
                break
    if "case_no" in F:
        num, year = F["case_no"].value
        for nk, yk in (("case_number", "case_year"), ("suit_number", "suit_year")):
            if nk in keys:
                put(nk, num, span=F["case_no"].span)
                put(yk, year, span=F["case_no"].span)
                break
    if "sections" in F:
        secs = _sections_value(F["sections"].value, lang)
        target = next((k for k in ("sections", "fir_sections", "offence_sections", "sections_convicted") if k in keys), None)
        if target:
            put(target, secs, span=F["sections"].span)
            if not any(g["act"] for g in F["sections"].value):
                notes.append("act_missing")

    # ---- marriage particulars
    if "marriage_date" in F and "marriage_year" in keys:
        put("marriage_year", F["marriage_date"].value[-4:], span=F["marriage_date"].span)
    elif "marriage_year" in keys:
        my = re.search(r"(?:marri\w*|wedding|विवाह|शादी)\D{0,12}((?:19|20)\d{2})(?!\d)", _nfc(brief), re.I)
        if my:
            put("marriage_year", my.group(1), span=my.group(0))
    mp = re.search(rf"(?:marri\w*|wedding|विवाह|शादी)[^.;।\n]{{0,40}}?(?:\bat\b|\bin\b|में|स्थान)\s+([A-Za-z{DEVA}]+(?:\s+[A-Za-z{DEVA}]+)?)",
                   _nfc(brief), re.I)
    if mp and "marriage_place" in keys:
        place = GEO.lookup(mp.group(1)) or GEO.lookup(mp.group(1).split()[0])
        val = place.name(lang) if place else mp.group(1)
        put("marriage_place", val, span=mp.group(0), convert=not place)

    # ---- dates
    for kind in ("arrest_date", "dishonour_date", "notice_date", "notice_known_date", "cheque_date", "marriage_date",
                 "conviction_date", "order_date", "seizure_date", "transaction_date"):
        if kind in F:
            key = kind
            if kind == "order_date" and "order_date" not in keys and "prior_order_date" in keys:
                key = "prior_order_date"
            if kind == "transaction_date" and "transaction_date" not in keys and "advance_date" in keys:
                key = "advance_date"
            put(key, F[kind].value, span=F[kind].span)

    # ---- money, written the way a filing writes it
    from headnote.drafter import amounts as AM

    def money(key: str, raw: str, span: str):
        n = AM.parse(raw)
        if n is None:
            return
        plain = key in ("principal_amount", "claim_amount", "valuation", "court_fee",
                        "total_consideration", "earnest_paid")
        put(key, AM.group(n) if plain else AM.display(n, lang), span=span)

    for kind in ("amount", "amount_sought", "respondent_income", "monthly_rent", "principal_amount", "claim_amount"):
        if kind in F:
            money(kind, F[kind].value, F[kind].span)
    if "money" in F:
        for k in ("amount", "principal_amount", "claim_amount", "amount_sought", "monetary_amount"):
            if k in keys and k not in vals:
                money(k, F["money"].value, F["money"].span)
                break

    # ---- §138 / supurdgi specifics
    if "cheque_no" in F:
        put("cheque_no", F["cheque_no"].value, span=F["cheque_no"].span)
    if "banks" in F:
        banks = F["banks"].value
        if "accused_bank_branch" in keys:
            put("accused_bank_branch", banks[0], span=banks[0], convert=True)
        if len(banks) > 1 and "complainant_bank_branch" in keys:
            put("complainant_bank_branch", banks[1], span=banks[1], convert=True)
    if "dishonour_reason" in F and "dishonour_reason" in keys:
        hi, en = F["dishonour_reason"].value.split("|")
        put("dishonour_reason", hi if lang == "hi" else en, span=F["dishonour_reason"].span)
    if "property" in F:
        for k in ("property_desc", "property_description"):
            if k in keys:
                put(k, F["property"].value, span=F["property"].span, convert=True)
                break
    if "vehicle_no" in F:
        put("vehicle_no", F["vehicle_no"].value, span=F["vehicle_no"].span)

    # ---- the court below (convicting / impugned-order court)
    below_keys = [k for k in ("convicting_court", "court_below", "trial_court") if k in keys]
    if below_keys:
        t = _nfc(brief)
        cb = re.search(
            r"(?:by|of|before|passed\s+by)\s+(?:the\s+)?(?:learned\s+|ld\.?\s+)?"
            r"((?:additional\s+|addl\.?\s+|special\s+|principal\s+|chief\s+|1st\s+|first\s+)?"
            r"(?:district\s+(?:and|&)\s+)?(?:sessions?\s+judge|judicial\s+magistrate(?:\s+first\s+class)?|jmfc|cjm|acjm|asj|"
            r"district\s+judge|magistrate|family\s+court|civil\s+judge)"
            r"(?:\s*(?:no\.?\s*\d+|[,]))?(?:\s+[A-Z][a-z]+)?)|"
            r"((?:अपर\s+|विशेष\s+|प्रधान\s+)?(?:सत्र\s+न्यायाधीश|न्यायिक\s+(?:दण्डाधिकारी|मजिस्ट्रेट)(?:\s+प्रथम\s+श्रेणी)?|"
            r"मुख्य\s+न्यायिक\s+दण्डाधिकारी|व्यवहार\s+न्यायाधीश)\s*,?\s*(?:[ऀ-ॣॱ-ॿ]+)?)", t, re.I)
        if cb:
            val = (cb.group(1) or cb.group(2)).strip(" ,")
            if cb.group(1):
                val = re.sub(r"\bjmfc\b", "JMFC", val, flags=re.I)
                val = " ".join(w if w.isupper() else w[:1].upper() + w[1:] for w in val.split())
            put(below_keys[0], val, span=cb.group(0), convert=True)
    if "sentence_passed" in keys:
        sm = re.search(r"sentenc\w*\s+(?:to\s+)?(?:undergo\s+)?((?:\d+|one|two|three|five|seven|ten|life)\s+(?:years?|months?|imprisonment)"
                       r"(?:\s+(?:RI|R\.I\.|rigorous(?:\s+imprisonment)?|simple\s+imprisonment))?)|"
                       r"(\d+\s+(?:वर्ष|माह|साल)\s+(?:का\s+)?(?:सश्रम\s+|साधारण\s+)?(?:कारावास|सजा))", _nfc(brief), re.I)
        if sm:
            put("sentence_passed", (sm.group(1) or sm.group(2)).strip(), span=sm.group(0))

    # ---- grounds he stated
    toggles: dict[str, bool] = {}
    if "is_company" in F["toggles"]:
        t = _nfc(brief)
        acc = re.search(r"(?:against|accused|आरोपी|अभियुक्त|के\s+विरुद्ध|drawer)(.{0,60})", t, re.I)
        if not (acc and _TOGGLE_C["is_company"].search(acc.group(1))):
            F["toggles"].pop("is_company")
    for k, span in F["toggles"].items():
        if k in toggle_keys:
            toggles[k] = True
            ev[k] = {"source": "brief", "span": span, "note": ""}
    if F["courts"]["prior"] and "prior_mag_rejected" in toggle_keys:
        toggles["prior_mag_rejected"] = True
        ev.setdefault("prior_mag_rejected", {"source": "brief", "span": "rejected earlier", "note": ""})
    if "prior_court" in keys and (F["courts"]["prior"] or "prior_court_city" in F):
        level = F["courts"]["prior"]
        names = {"magistrate": ("न्यायिक दण्डाधिकारी प्रथम श्रेणी", "Judicial Magistrate First Class"),
                 "sessions": ("सत्र न्यायालय", "Sessions Court"), "hc": ("उच्च न्यायालय", "High Court"),
                 "family": ("कुटुम्ब न्यायालय", "Family Court")}.get(level or "", ("", ""))
        city = _localise_place(F["prior_court_city"].value, lang)[0] if "prior_court_city" in F else ""
        label = names[0] if lang == "hi" else names[1]
        v = ", ".join(x for x in (label, city) if x)
        if v:
            put("prior_court", v, span=(F["prior_court_city"].span if "prior_court_city" in F else level))
    if F["grounds"] and "custom_grounds" in keys and TA.CANONICAL_MAP[tid][0] in ("bail", "default_bail"):
        lines = [hi if lang == "hi" else en for hi, en, _span in F["grounds"]]
        put("custom_grounds", "\n".join(lines), span="; ".join(s for _h, _e, s in F["grounds"]),
            note="Standard wording for facts stated in your brief.")
    vals.update(toggles)

    return {"fields": vals, "evidence": ev, "converted": sorted(set(converted)), "notes": notes}


# =========================================================================== the whole front door
def intake(brief: str, *, tid: Optional[str] = None, lang: str = "auto") -> dict:
    """recognise + extract, with the language decided. `tid` (his pick) wins over
    recognition; `lang` "auto" follows the brief."""
    from headnote.drafter import template_adapter as TA

    rec = recognise(brief)
    chosen = tid if (tid and TA.is_canonical(tid)) else rec["tid"]
    lang = lang if lang in ("hi", "en") else choose_lang(brief)
    out = {"recognised": rec, "tid": chosen, "lang": lang, "fields": {}, "evidence": {},
           "converted": [], "notes": []}
    if chosen:
        out.update(extract(brief, chosen, lang))
    return out
