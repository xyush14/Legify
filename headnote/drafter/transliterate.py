"""
EN ↔ HI transliteration ported from the v3 JS prototype.

Same algorithm as `static/drafter.html` lines 305-516:
  - HI_DICT: ~200-entry dictionary of common names, surnames, cities,
    address words, banks, conjunctions.
  - Phonetic fallback: state-machine that handles consonant clusters,
    aspirated consonants, vowel matras vs independent vowels, anusvara
    rule, end-of-word -a → -ā lengthening.

Hindi has three sibilants (श / ष / स) all transliterating to 'sh' or 's'
in English. The phonetic fallback cannot disambiguate without context —
it always picks श for 'sh'. The dotted underline class `xlit` lives in
the templates so a lawyer can spot any wrong transliteration and edit
the source field. Production should pair this with a Haiku-4.5
transliteration call for unknown names (~₹0.05 per draft).

This module is deliberately a pure-Python translation of the JS — same
ordering, same edge cases, same dictionary entries — so the rendered
HTML from a Python template matches the prototype byte-for-byte modulo
the final docx formatting layer.
"""

from __future__ import annotations

import re
from typing import Final


# Dictionary: ~200 entries, ordered by class for readability + diffability
# against the JS prototype. Add new entries in the relevant section
# (first names / surnames / cities / etc.) rather than dumping at the end.
HI_DICT: Final[dict[str, str]] = {
    # First names — male
    "priyanshu": "प्रियंशु", "abhishek": "अभिषेक", "rajesh": "राजेश", "dheeraj": "धीरज",
    "shyam": "श्याम", "ayush": "आयुष", "amit": "अमित", "sunil": "सुनील", "anil": "अनिल",
    "mukesh": "मुकेश", "suresh": "सुरेश", "ramesh": "रमेश", "mahesh": "महेश",
    "rakesh": "राकेश", "dinesh": "दिनेश", "naresh": "नरेश", "rohit": "रोहित",
    "mohit": "मोहित", "vishal": "विशाल", "vikash": "विकास", "vikas": "विकास",
    "manoj": "मनोज", "sanjay": "संजय", "ajay": "अजय", "vijay": "विजय", "jay": "जय",
    "arjun": "अर्जुन", "krishna": "कृष्ण", "ram": "राम", "gopal": "गोपाल",
    "mohan": "मोहन", "sohan": "सोहन", "ashok": "अशोक", "pankaj": "पंकज",
    "deepak": "दीपक", "rahul": "राहुल", "sachin": "सचिन", "gaurav": "गौरव",
    "siddharth": "सिद्धार्थ", "aditya": "आदित्य", "akash": "आकाश", "arun": "अरुण",
    "varun": "वरुण", "tarun": "तरुण", "karan": "करन", "kabir": "कबीर",
    "piyush": "पीयूष", "harsh": "हर्ष", "yash": "यश", "shivam": "शिवम",
    # First names — female
    "anita": "अनीता", "sunita": "सुनीता", "kavita": "कविता", "pooja": "पूजा",
    "priya": "प्रिया", "priyanka": "प्रियंका", "neha": "नेहा", "rekha": "रेखा",
    "meena": "मीना", "reena": "रीना", "seema": "सीमा", "asha": "आशा",
    "usha": "उषा", "sushma": "सुषमा", "lata": "लता", "radha": "राधा",
    "sita": "सीता", "gita": "गीता", "kalpana": "कल्पना", "shobha": "शोभा",
    # Surnames
    "sharma": "शर्मा", "verma": "वर्मा", "gupta": "गुप्ता", "singh": "सिंह",
    "kumar": "कुमार", "kumari": "कुमारी", "agarwal": "अग्रवाल", "agrawal": "अग्रवाल",
    "mishra": "मिश्रा", "tiwari": "तिवारी", "chaurasiya": "चौरसिया", "chaurasia": "चौरसिया",
    "pandey": "पाण्डेय", "tripathi": "त्रिपाठी", "dubey": "दुबे", "jha": "झा",
    "yadav": "यादव", "patel": "पटेल", "shah": "शाह", "mehta": "मेहता",
    "joshi": "जोशी", "desai": "देसाई", "rao": "राव", "reddy": "रेड्डी",
    "iyer": "अय्यर", "menon": "मेनन", "nair": "नायर", "pillai": "पिल्लई",
    "kapoor": "कपूर", "khanna": "खन्ना", "malhotra": "मल्होत्रा", "chopra": "चोपड़ा",
    "thakur": "ठाकुर", "rajput": "राजपूत", "gurjar": "गुर्जर", "jat": "जाट",
    "gaur": "गौड़", "kushwaha": "कुशवाहा", "saxena": "सक्सेना", "srivastava": "श्रीवास्तव",
    # Address words
    "shri": "श्री", "shree": "श्री", "smt": "श्रीमती", "colony": "कॉलोनी",
    "colaney": "कॉलोनी", "nagar": "नगर", "road": "रोड", "street": "स्ट्रीट",
    "gali": "गली", "mohalla": "मोहल्ला", "ward": "वार्ड", "block": "ब्लॉक",
    "sector": "सेक्टर", "phase": "फेज़", "mandir": "मंदिर", "masjid": "मस्जिद",
    "school": "स्कूल", "town": "टाउन", "model": "मॉडल", "park": "पार्क",
    "hospital": "हॉस्पिटल", "collector": "कलेक्टर", "office": "कार्यालय",
    "station": "स्टेशन", "distt": "जिला", "district": "जिला", "tehsil": "तहसील",
    # Cities (MP-heavy because the founder is in Bhopal)
    "gwalior": "ग्वालियर", "bhopal": "भोपाल", "indore": "इंदौर", "jabalpur": "जबलपुर",
    "ujjain": "उज्जैन", "sagar": "सागर", "rewa": "रीवा", "satna": "सतना",
    "dabra": "डबरा", "morena": "मुरैना", "bhind": "भिंड", "shivpuri": "शिवपुरी",
    "guna": "गुना", "ashoknagar": "अशोकनगर", "datia": "दतिया",
    "delhi": "दिल्ली", "mumbai": "मुंबई", "kolkata": "कोलकाता", "chennai": "चेन्नई",
    "lucknow": "लखनऊ", "kanpur": "कानपुर", "jaipur": "जयपुर", "patna": "पटना",
    # Business / legal
    "private": "प्राइवेट", "limited": "लिमिटेड", "ltd": "लिमिटेड", "pvt": "प्रा.",
    "enterprises": "एंटरप्राइजेज़", "traders": "ट्रेडर्स", "industries": "इंडस्ट्रीज़",
    "service": "नौकरी", "business": "व्यापार", "trader": "व्यापारी",
    "advocate": "अधिवक्ता", "lawyer": "अधिवक्ता",
    # Banks
    "sbi": "एसबीआई", "state": "स्टेट", "bank": "बैंक", "india": "इंडिया",
    "uco": "यूको", "pnb": "पीएनबी", "icici": "आईसीआईसीआई", "hdfc": "एचडीएफसी",
    "axis": "एक्सिस", "kotak": "कोटक", "yes": "यस", "idfc": "आईडीएफसी",
    "branch": "शाखा",
    # Common conjunctions / prepositions
    "and": "और", "or": "या", "of": "का", "the": "", "at": "में", "in": "में",
    "near": "के पास", "opposite": "के सामने", "behind": "के पीछे",
}

# Reverse map for HI → EN, first occurrence wins (skip empty maps to "")
EN_DICT: Final[dict[str, str]] = {}
for _en, _hi in HI_DICT.items():
    if _hi and _hi not in EN_DICT:
        EN_DICT[_hi] = _en[:1].upper() + _en[1:]


# Phonetic mappings — multi-char first so 'shri' beats 's' + 'h' + 'r' + 'i'.
CONS_MULTI: Final[dict[str, str]] = {
    "shri": "श्री", "shr": "श्र", "chh": "छ", "jny": "ज्ञ",
    "kh": "ख", "gh": "घ", "ch": "च", "jh": "झ",
    "th": "थ", "dh": "ध", "ph": "फ", "bh": "भ", "sh": "श",
}
CONS_SINGLE: Final[dict[str, str]] = {
    "k": "क", "g": "ग", "c": "क", "j": "ज", "t": "त", "d": "द",
    "n": "न", "p": "प", "b": "ब", "m": "म", "y": "य", "r": "र",
    "l": "ल", "v": "व", "w": "व", "s": "स", "h": "ह", "z": "ज़",
    "f": "फ़", "q": "क", "x": "क्स",
}
VOWEL_MULTI: Final[list[str]] = ["aa", "ee", "ii", "oo", "uu", "ai", "au"]
VOWEL_INDEP: Final[dict[str, str]] = {
    "aa": "आ", "ee": "ई", "ii": "ई", "oo": "ऊ", "uu": "ऊ",
    "ai": "ऐ", "au": "औ",
    "a": "अ", "e": "ए", "i": "इ", "o": "ओ", "u": "उ",
}
VOWEL_MATRA: Final[dict[str, str]] = {
    "aa": "ा", "ee": "ी", "ii": "ी", "oo": "ू", "uu": "ू",
    "ai": "ै", "au": "ौ",
    "a": "", "e": "े", "i": "ि", "o": "ो", "u": "ु",
}

# Multi-keys sorted longest-first to match greedily
_MULTI_KEYS_BY_LEN: Final[list[str]] = sorted(CONS_MULTI.keys(), key=len, reverse=True)

# Devanagari Unicode block — used to detect script
_DEVA_RE: Final[re.Pattern] = re.compile(r"[ऀ-ॿ]")


def phonetic_to_hi(word: str) -> str:
    """Convert a single ASCII word to Devanagari via the phonetic
    state machine. Doesn't handle whitespace or punctuation — caller
    is expected to tokenise first.
    """
    word = word.lower()
    result = ""
    i = 0
    last_was_consonant = False

    while i < len(word):
        is_last = i == len(word) - 1

        # Anusvara: 'n' or 'm' followed by a consonant becomes ं on previous vowel
        if (
            (word[i] == "n" or word[i] == "m")
            and not last_was_consonant
            and 0 < i < len(word) - 1
        ):
            next_ch = word[i + 1]
            next_two = word[i + 1 : i + 3]
            next_three = word[i + 1 : i + 3] + (word[i + 3] if i + 3 < len(word) else "")
            followed_by_consonant = (
                next_ch in CONS_SINGLE
                or next_two in CONS_MULTI
                or (len(next_two) == 2 and next_two in CONS_MULTI)
            )
            followed_by_vowel = next_ch in ("a", "e", "i", "o", "u")
            if followed_by_consonant and not followed_by_vowel:
                result += "ं"
                i += 1
                last_was_consonant = False
                continue

        # Multi-char consonants (longest first)
        matched = False
        for key in _MULTI_KEYS_BY_LEN:
            if word[i : i + len(key)] == key:
                if last_was_consonant:
                    result += "्"
                result += CONS_MULTI[key]
                i += len(key)
                last_was_consonant = True
                matched = True
                break
        if matched:
            continue

        # Multi-char vowels
        for v in VOWEL_MULTI:
            if word[i : i + len(v)] == v:
                if last_was_consonant:
                    result += VOWEL_MATRA[v]
                else:
                    result += VOWEL_INDEP[v]
                i += len(v)
                last_was_consonant = False
                matched = True
                break
        if matched:
            continue

        # Single consonant
        if word[i] in CONS_SINGLE:
            if last_was_consonant:
                result += "्"
            result += CONS_SINGLE[word[i]]
            i += 1
            last_was_consonant = True
            continue

        # Single vowel — end-of-word 'a' after consonant becomes long ा
        if word[i] in VOWEL_INDEP:
            v = word[i]
            if v == "a" and is_last and last_was_consonant and len(word) > 2:
                v = "aa"
            if last_was_consonant:
                result += VOWEL_MATRA[v]
            else:
                result += VOWEL_INDEP[v]
            i += 1
            last_was_consonant = False
            continue

        # Numbers and punctuation passthrough
        result += word[i]
        i += 1

    return result


_TOKEN_SPLIT_RE: Final[re.Pattern] = re.compile(r"(\s+|[,.;:()\-\/])")
_DIGITS_RE: Final[re.Pattern] = re.compile(r"^\d+$")
_PUNCT_OR_WS_RE: Final[re.Pattern] = re.compile(r"^(\s+|[,.;:()\-\/]+)$")


def en_to_hi(text: str) -> str:
    """Transliterate Latin → Devanagari.
    - Whitespace and punctuation preserved.
    - Already-Devanagari input passes through untouched.
    - Dictionary lookup wins over phonetic fallback.
    """
    if not text or not isinstance(text, str):
        return text or ""
    if _DEVA_RE.search(text):
        return text  # already Devanagari, don't touch

    parts = _TOKEN_SPLIT_RE.split(text)
    out: list[str] = []
    for tok in parts:
        if not tok:
            continue
        if _PUNCT_OR_WS_RE.match(tok) or _DIGITS_RE.match(tok):
            out.append(tok)
            continue
        lower = tok.lower()
        if lower in HI_DICT:
            out.append(HI_DICT[lower])
        else:
            out.append(phonetic_to_hi(tok))
    return "".join(out)


# HI → EN: mostly 1-to-1 character mapping, used as fallback when token
# is not in EN_DICT. The JS prototype uses the same approach; capital
# letter on first character only.
_HI_TO_EN_MAP: Final[dict[str, str]] = {
    "अ": "a", "आ": "aa", "इ": "i", "ई": "ee", "उ": "u", "ऊ": "oo", "ऋ": "ri",
    "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au",
    "क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "ng",
    "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "ny",
    "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n",
    "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
    "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m",
    "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh", "ष": "sh",
    "स": "s", "ह": "h", "ळ": "l",
    "ा": "a", "ि": "i", "ी": "ee", "ु": "u", "ू": "oo", "े": "e",
    "ै": "ai", "ो": "o", "ौ": "au",
    "ं": "n", "ः": "h", "ँ": "n",
    "्": "",
    "क़": "q", "ज़": "z", "फ़": "f", "ड़": "r", "ढ़": "rh",
    "०": "0", "१": "1", "२": "2", "३": "3", "४": "4",
    "५": "5", "६": "6", "७": "7", "८": "8", "९": "9",
}


def hi_to_en(text: str) -> str:
    """Transliterate Devanagari → Latin.
    - Dictionary lookup wins for known words.
    - Per-character fallback otherwise.
    - First character of each token capitalised.
    """
    if not text or not isinstance(text, str):
        return text or ""
    if not _DEVA_RE.search(text):
        return text  # already Latin, don't touch

    parts = _TOKEN_SPLIT_RE.split(text)
    out: list[str] = []
    for tok in parts:
        if not tok:
            continue
        if _PUNCT_OR_WS_RE.match(tok):
            out.append(tok)
            continue
        if tok in EN_DICT:
            out.append(EN_DICT[tok])
            continue
        # Per-character fallback
        chars = [_HI_TO_EN_MAP.get(ch, ch) for ch in tok]
        result = "".join(chars)
        if result:
            result = result[:1].upper() + result[1:]
        out.append(result)
    return "".join(out)


def xlit(text: str, target_lang: str) -> tuple[str, bool]:
    """Render a user-typed field for the target lang.

    Returns (rendered_text, was_transliterated). When was_transliterated
    is true, the template wraps in <span class="xlit"> so the lawyer can
    spot the converted text in the preview and edit the source field.
    """
    if not text:
        return text or "", False
    is_deva = bool(_DEVA_RE.search(text))
    if target_lang == "hi":
        result = text if is_deva else en_to_hi(text)
    else:  # "en"
        result = hi_to_en(text) if is_deva else text
    return result, result != text
