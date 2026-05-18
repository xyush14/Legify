"""
Universal fact extractor for Indian criminal-law text.

Extracts structured facts from free-text legal queries OR full judgments
and returns them as a deterministic JSON-serialisable dict. The same
extractor works for ANY criminal scenario — POCSO, murder, NDPS, 138 NI,
498A, cheque bounce, dowry death, etc. Each fact dimension is OPTIONAL
and only fires when the relevant pattern is present.

Why a regex extractor (not an LLM)?
-----------------------------------
Two reasons:

1. **Speed + cost.** We need to score 20-50 candidates per query at sub-
   100 ms. An LLM call per case is impossible at scale.
2. **Determinism.** Citations downstream depend on knowing which
   statutes/sections the case actually construes. An LLM that confidently
   hallucinates "S. 376" when the case is about S. 354 poisons the
   pipeline. Regex either matches or it doesn't — no hallucination.

The extractor is intentionally conservative. False negatives (missing a
fact) are recoverable via the LLM reranker downstream. False positives
(extracting a fact that isn't there) corrupt scoring across the corpus.
When in doubt, return nothing.

Universal fact dimensions
-------------------------
Every dimension is OPTIONAL. The extractor returns whatever it finds.

- statutes          : canonical refs like 'IPC-302', 'POCSO-4', 'NDPS-21'
- stage             : 'bail' / 'anticipatory_bail' / 'quash' / 'trial' /
                      'appeal' / 'revision' / 'suspension_of_sentence' /
                      'discharge' / 'transit_bail' / 'default_bail'
- court_level       : 'supreme_court' / 'high_court' / 'sessions' /
                      'magistrate' / 'district_court'
- victim            : { is_minor, gender, age } — fires for any offence
                      with an identified victim/complainant/prosecutrix
- accused           : { role, is_minor, is_woman, is_public_servant,
                        has_antecedents }
- outcome           : 'granted' / 'denied' / 'acquitted' / 'convicted' /
                      'quashed' / 'set_aside' / 'dismissed'
- doctrines         : set of legal doctrines (consent, delay_in_fir,
                      circumstantial, dying_declaration, etc.)
- special_category  : ['woman', 'juvenile', 'senior', 'sick', 'pregnant']
- numerics          : { cheque_amount_inr, drug_qty_grams, custody_days,
                        fir_delay_days, age_victim, age_accused }
- weapon            : 'firearm' / 'knife' / 'blunt' / 'poison' / 'none'

Usage
-----
    from headnote.retrieval.fact_extractor import extract_facts

    facts = extract_facts(
        "Need bail for client accused under POCSO Act, victim was 16, "
        "consensual relationship, FIR delay of 4 months."
    )
    # -> {
    #     'statutes': ['POCSO'],
    #     'stage': ['bail'],
    #     'victim': {'is_minor': True, 'age': 16},
    #     'doctrines': ['consent', 'delay_in_fir'],
    #     'numerics': {'fir_delay_days': 120, 'age_victim': 16},
    # }
"""

from __future__ import annotations

import re
from typing import Any, Optional


# ============================================================== STATUTES

# Canonical statute aliases. The key is the canonical form we emit; the
# value is the regex alternation that matches in text. Ordered by
# specificity — longer/more-specific patterns first so 'NI Act' beats 'Act'.
_STATUTE_ALIASES = {
    "POCSO":      r"P\.?\s*O\.?\s*C\.?\s*S\.?\s*O\.?(?:\s*Act)?",
    "NDPS":       r"N\.?\s*D\.?\s*P\.?\s*S\.?(?:\s*Act)?",
    "PMLA":       r"P\.?\s*M\.?\s*L\.?\s*A\.?",
    "UAPA":       r"U\.?\s*A\.?\s*P\.?\s*A\.?",
    "PC_ACT":     r"P\.?\s*C\.?\s*Act|Prevention\s+of\s+Corruption\s+Act",
    "SC_ST_ACT":  r"S\.?\s*C\.?\s*[\\/]?\s*S\.?\s*T\.?(?:\s*Act)?|Atrocities\s+Act",
    "NI_ACT":     r"N\.?\s*I\.?\s*Act|Negotiable\s+Instruments\s+Act",
    "MV_ACT":     r"M\.?\s*V\.?\s*Act|Motor\s+Vehicles\s+Act",
    "TADA":       r"T\.?\s*A\.?\s*D\.?\s*A\.?",
    "MCOCA":      r"M\.?\s*C\.?\s*O\.?\s*C\.?\s*A\.?",
    "IT_ACT":     r"I\.?\s*T\.?\s*Act|Information\s+Technology\s+Act",
    "JJ_ACT":     r"J\.?\s*J\.?\s*Act|Juvenile\s+Justice\s+Act",
    "DV_ACT":     r"D\.?\s*V\.?\s*Act|Domestic\s+Violence\s+Act|Protection\s+of\s+Women",
    "DOWRY_ACT":  r"Dowry\s+Prohibition\s+Act",
    "ARMS_ACT":   r"Arms\s+Act",
    "COMPANIES":  r"Companies\s+Act",
    "EVIDENCE":   r"(?:Indian\s+)?Evidence\s+Act|BSA",
    "IPC":        r"I\.?\s*P\.?\s*C\.?|Indian\s+Penal\s+Code",
    "CRPC":       r"Cr\.?\s*P\.?\s*C\.?|Criminal\s+Procedure\s+Code",
    "BNS":        r"B\.?\s*N\.?\s*S\.?(?!\s*S)|Bharatiya\s+Nyaya\s+Sanhita",
    "BNSS":       r"B\.?\s*N\.?\s*S\.?\s*S\.?|Bharatiya\s+Nagarik\s+Suraksha",
    "BSA":        r"B\.?\s*S\.?\s*A\.?|Bharatiya\s+Sakshya",
}

# Compile a single pass over text with named groups for each statute.
# We use word boundaries on both sides so 'IPC' inside 'GIPCo' doesn't match.
_STATUTE_REGEX = re.compile(
    "|".join(f"(?P<{name}>\\b(?:{pat})\\b)" for name, pat in _STATUTE_ALIASES.items()),
    re.IGNORECASE,
)

# Section pattern, used to find associated section numbers near each statute.
# Matches: "S. 302", "Section 376", "u/s 138", "u/Sec 437", "S.302A",
# "Section 376(2)(i)", "Sec. 34", "S/138".
#
# Important: bare "S" without a period is too ambiguous in English prose
# ("is 16", "was 14", "Rs 500" would all leak). We require either:
#   - "S." (with period)
#   - "Section" / "Sec." (full word)
#   - "u/s" / "U/S" shorthand
#   - "S/" (slash form)
# All have a leading \b word-boundary so they don't match inside other words.
_SECTION_PATTERN = re.compile(
    r"(?:"
    r"\bS\."
    r"|\bSection\b"
    r"|\bSec\."
    r"|\bu/s\b"
    r"|\bU/Sec\b"
    r"|\bU/S\b"
    r"|\bS/"
    r")\s*"
    r"(\d{1,4}[A-Z]{0,3}(?:\([\dA-Za-z]+\))*)",
    re.IGNORECASE,
)

# Bare "statute-then-number" pattern catches the common Indian shorthand:
# "IPC 302", "BNS 103", "POCSO 4", "NDPS 20", "NI Act 138". We process this
# in a separate pass because the section prefix is implicit (the statute
# name itself acts as the prefix).
_STATUTE_THEN_NUMBER = re.compile(
    r"\b(IPC|CrPC|BNS|BNSS|BSA|POCSO|NDPS|PMLA|UAPA|NI\s*Act|TADA|MCOCA|"
    r"Arms\s*Act|Evidence\s*Act|MV\s*Act|IT\s*Act|JJ\s*Act|DV\s*Act|"
    r"PC\s*Act|SC[/\s]ST\s*Act|Dowry\s*Prohibition\s*Act|Companies\s*Act)"
    r"\s*"
    r"(?:Act\s+)?"
    r"(\d{1,4}[A-Z]{0,3}(?:\([\dA-Za-z]+\))*)",
    re.IGNORECASE,
)


def _extract_statutes(text: str) -> list[str]:
    """Find statutes and their associated section numbers.

    Returns canonical refs like 'IPC-302', 'POCSO-4', 'NDPS' (bare statute
    if no section nearby).

    The trick: we scan for both statutes and sections, then pair each
    section with the NEAREST statute reference (within a window). This
    catches phrasings like 'S. 302 IPC', 'IPC S. 302', and bare 'S. 302'
    when an IPC reference appears elsewhere in the same paragraph.
    """
    if not text:
        return []

    # 1. Find all statute hits with their positions
    statute_hits: list[tuple[int, str]] = []
    for m in _STATUTE_REGEX.finditer(text):
        for name in _STATUTE_ALIASES:
            if m.group(name):
                statute_hits.append((m.start(), name))
                break

    # 2. Find all section hits with their positions
    section_hits: list[tuple[int, str]] = []
    for m in _SECTION_PATTERN.finditer(text):
        section_hits.append((m.start(), m.group(1).upper()))

    refs: set[str] = set()

    # 3. Pair each section with the nearest statute (within 80 chars)
    for sec_pos, sec_num in section_hits:
        nearest = None
        nearest_dist = 81
        for st_pos, st_name in statute_hits:
            dist = abs(sec_pos - st_pos)
            if dist < nearest_dist:
                nearest_dist = dist
                nearest = st_name
        if nearest:
            refs.add(f"{nearest}-{sec_num}")
        else:
            # Bare section number with no statute → assume IPC (most common)
            # Only do this if there's an IPC mention SOMEWHERE in the text.
            if any(name == "IPC" for _, name in statute_hits):
                refs.add(f"IPC-{sec_num}")

    # 3b. Pick up bare "statute-then-number" shorthand: "IPC 302", "BNS 103",
    # "POCSO 4". This is the most common form in Indian practitioner writing
    # and we'd lose huge recall without it.
    _ALIAS_TO_CANONICAL = {
        "IPC": "IPC", "CRPC": "CRPC", "BNS": "BNS", "BNSS": "BNSS", "BSA": "BSA",
        "POCSO": "POCSO", "NDPS": "NDPS", "PMLA": "PMLA", "UAPA": "UAPA",
        "TADA": "TADA", "MCOCA": "MCOCA",
        "NI ACT": "NI_ACT", "ARMS ACT": "ARMS_ACT", "EVIDENCE ACT": "EVIDENCE",
        "MV ACT": "MV_ACT", "IT ACT": "IT_ACT", "JJ ACT": "JJ_ACT",
        "DV ACT": "DV_ACT", "PC ACT": "PC_ACT",
        "SC/ST ACT": "SC_ST_ACT", "SC ST ACT": "SC_ST_ACT",
        "DOWRY PROHIBITION ACT": "DOWRY_ACT", "COMPANIES ACT": "COMPANIES",
    }
    for m in _STATUTE_THEN_NUMBER.finditer(text):
        raw_statute = re.sub(r"\s+", " ", m.group(1).upper().strip())
        canonical = _ALIAS_TO_CANONICAL.get(raw_statute)
        if canonical:
            refs.add(f"{canonical}-{m.group(2).upper()}")

    # 4. Add bare statute refs (no section) for statutes that had no near section
    paired_statutes = {ref.split("-")[0] for ref in refs}
    for _, st_name in statute_hits:
        if st_name not in paired_statutes:
            refs.add(st_name)
            paired_statutes.add(st_name)

    return sorted(refs)


# ============================================================== STAGE / PROCEEDINGS

# Order matters: longer/more-specific phrases first so 'anticipatory bail'
# beats 'bail'.
_STAGE_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("anticipatory_bail",       re.compile(r"\banticipatory\s+bail\b|\bA\.?B\.?\s+application\b|\b438\s+CrPC\b|\b438\s+Cr\.?P\.?C\.?\b", re.IGNORECASE)),
    ("default_bail",            re.compile(r"\bdefault\s+bail\b|\bstatutory\s+bail\b|\b167\s*\(\s*2\s*\)", re.IGNORECASE)),
    ("transit_bail",            re.compile(r"\btransit\s+bail\b", re.IGNORECASE)),
    ("suspension_of_sentence",  re.compile(r"\bsuspension\s+of\s+sentence\b|\bsuspend\s+(?:the\s+)?sentence\b|\b389\s+CrPC\b", re.IGNORECASE)),
    ("quash",                   re.compile(r"\bquash(?:ing|ed)?\b|\bu/s\.?\s*482\b|\bSection\s+482\b|\b482\s+CrPC\b|\bquashment\b", re.IGNORECASE)),
    ("discharge",               re.compile(r"\bdischarge\b|\bdischarged\b|\b227\s+CrPC\b|\b239\s+CrPC\b", re.IGNORECASE)),
    ("framing_of_charge",       re.compile(r"\bframing\s+of\s+charge\b|\bcharges?\s+framed\b|\b228\s+CrPC\b|\b240\s+CrPC\b", re.IGNORECASE)),
    ("appeal",                  re.compile(r"\b(?:criminal\s+)?appeal\b|\bappellant\b|\b374\s+CrPC\b", re.IGNORECASE)),
    ("revision",                re.compile(r"\b(?:criminal\s+)?revision\b|\brevisionist\b|\b397\s+CrPC\b|\b401\s+CrPC\b", re.IGNORECASE)),
    ("trial",                   re.compile(r"\btrial\b|\bsessions\s+trial\b|\bSC\s+No\.?\b", re.IGNORECASE)),
    ("regular_bail",            re.compile(r"\bregular\s+bail\b|\b437\s+CrPC\b|\b439\s+CrPC\b|\bbail\s+application\b", re.IGNORECASE)),
    ("bail",                    re.compile(r"\bbail\b|\benlarge(?:d)?\s+on\s+bail\b", re.IGNORECASE)),
    ("fir_quash",               re.compile(r"\bquash\s+(?:the\s+)?FIR\b", re.IGNORECASE)),
    ("writ",                    re.compile(r"\bwrit\s+petition\b|\bArticle\s+226\b|\bArticle\s+32\b|\bhabeas\s+corpus\b", re.IGNORECASE)),
]


def _extract_stage(text: str) -> list[str]:
    if not text:
        return []
    hits: list[str] = []
    seen: set[str] = set()
    for label, pat in _STAGE_PATTERNS:
        if pat.search(text) and label not in seen:
            hits.append(label)
            seen.add(label)
            # Coalesce: 'regular_bail' / 'anticipatory_bail' / etc. all
            # imply 'bail' generally — add the parent.
            if label in {"regular_bail", "anticipatory_bail", "default_bail", "transit_bail"} and "bail" not in seen:
                hits.append("bail")
                seen.add("bail")
    return hits


# ============================================================== COURT LEVEL

_COURT_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("supreme_court", re.compile(r"\bSupreme\s+Court\s+of\s+India\b|\bSupreme\s+Court\b|\bS\.?C\.?\s+of\s+India\b", re.IGNORECASE)),
    ("high_court",    re.compile(r"\bHigh\s+Court\b|\bH\.?C\.?\b", re.IGNORECASE)),
    ("sessions",      re.compile(r"\bSessions\s+Court\b|\bSessions\s+Judge\b|\bAdditional\s+Sessions\b", re.IGNORECASE)),
    ("magistrate",    re.compile(r"\bMagistrate\b|\bJudicial\s+Magistrate\b|\bCJM\b|\bACJM\b|\bACMM\b", re.IGNORECASE)),
    ("district_court", re.compile(r"\bDistrict\s+Court\b|\bDistrict\s+Judge\b", re.IGNORECASE)),
]


def _extract_court_level(text: str) -> Optional[str]:
    """Return the highest-precedence court mentioned (SC > HC > Sessions...)."""
    if not text:
        return None
    for label, pat in _COURT_PATTERNS:
        if pat.search(text):
            return label
    return None


# ============================================================== VICTIM / ACCUSED

_VICTIM_GENDER_FEMALE = re.compile(
    r"\b(?:prosecutrix|victim\s+girl|she\s+was|her\s+statement|the\s+girl|"
    r"survivor\s+girl|female\s+victim|complainant\s+is\s+a\s+woman)\b",
    re.IGNORECASE,
)
_VICTIM_GENDER_MALE = re.compile(
    r"\b(?:victim\s+boy|he\s+was\s+(?:assaulted|attacked)|male\s+victim|the\s+boy)\b",
    re.IGNORECASE,
)
_MINOR_INDICATORS = re.compile(
    r"\b(?:minor|child|juvenile|below\s+(?:the\s+)?age\s+of\s+18|"
    r"below\s+18(?:\s+years)?|under\s+18|aged?\s+(\d{1,2})\s+years?|"
    r"(\d{1,2})\s+years?\s+old)\b",
    re.IGNORECASE,
)


def _extract_victim(text: str) -> dict[str, Any]:
    """Pull victim/prosecutrix attributes from the text."""
    if not text:
        return {}
    out: dict[str, Any] = {}

    # Gender
    if _VICTIM_GENDER_FEMALE.search(text):
        out["gender"] = "female"
    elif _VICTIM_GENDER_MALE.search(text):
        out["gender"] = "male"

    # Age + minor status. Look for age near victim-context words.
    # First pass: explicit "victim was X years old" / "aged X" / "X-year-old"
    age_match = re.search(
        r"(?:victim|prosecutrix|girl|child|survivor|complainant)\b[^.]{0,80}?"
        r"\b(?:aged?|was)\s+(\d{1,2})\s*(?:years?|yrs?)\b",
        text,
        re.IGNORECASE,
    ) or re.search(
        r"\b(\d{1,2})[-\s]?(?:years?|yrs?)[-\s]?old\b[^.]{0,80}?"
        r"(?:victim|prosecutrix|girl|child|survivor|complainant)",
        text,
        re.IGNORECASE,
    )
    if age_match:
        try:
            age = int(age_match.group(1))
            if 1 <= age <= 99:
                out["age"] = age
                if age < 18:
                    out["is_minor"] = True
        except (ValueError, IndexError):
            pass

    # Generic "minor" / "child victim" mention without explicit age
    if "is_minor" not in out and _MINOR_INDICATORS.search(text):
        # Only flag as minor if the minor reference is near a victim word
        # — otherwise 'minor' could refer to the accused.
        victim_near_minor = re.search(
            r"(?:victim|prosecutrix|girl|child|survivor)\b[^.]{0,60}?"
            r"(?:minor|child|juvenile|below\s+18|under\s+18)",
            text,
            re.IGNORECASE,
        ) or re.search(
            r"(?:minor|child|juvenile|below\s+18|under\s+18)\b[^.]{0,60}?"
            r"(?:victim|prosecutrix|girl|child|survivor)",
            text,
            re.IGNORECASE,
        )
        if victim_near_minor:
            out["is_minor"] = True

    return out


_ACCUSED_JUVENILE = re.compile(r"\b(?:juvenile\s+(?:accused|offender|in\s+conflict)|child\s+in\s+conflict\s+with\s+law|JCL)\b", re.IGNORECASE)
_ACCUSED_PUBLIC_SERVANT = re.compile(r"\b(?:public\s+servant|government\s+servant|IAS|IPS|police\s+officer\s+accused|sanction\s+under\s+S\.?\s*197)\b", re.IGNORECASE)
_ACCUSED_ANTECEDENTS = re.compile(r"\b(?:criminal\s+antecedents|previous\s+convictions?|habitual\s+offender|history\s+sheet|repeat\s+offender)\b", re.IGNORECASE)
_ACCUSED_WOMAN = re.compile(r"\b(?:woman\s+accused|female\s+accused|lady\s+accused|she\s+is\s+the\s+accused|accused\s+is\s+a\s+woman)\b", re.IGNORECASE)
_ACCUSED_CO = re.compile(r"\b(?:co[-\s]?accused|other\s+accused|accused\s+No\.?\s*[2-9])\b", re.IGNORECASE)


def _extract_accused(text: str) -> dict[str, Any]:
    if not text:
        return {}
    out: dict[str, Any] = {}
    if _ACCUSED_JUVENILE.search(text):
        out["is_minor"] = True
        out["role"] = "juvenile"
    if _ACCUSED_PUBLIC_SERVANT.search(text):
        out["is_public_servant"] = True
    if _ACCUSED_ANTECEDENTS.search(text):
        out["has_antecedents"] = True
    if _ACCUSED_WOMAN.search(text):
        out["is_woman"] = True
    if _ACCUSED_CO.search(text) and "role" not in out:
        out["role"] = "co_accused"
    return out


# ============================================================== OUTCOME

_OUTCOME_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("granted",    re.compile(r"\bbail\s+(?:is\s+)?(?:hereby\s+)?granted\b|\bbail\s+application\s+is\s+allowed\b|\benlarged?\s+on\s+bail\b|\bgranted\s+bail\b", re.IGNORECASE)),
    ("denied",     re.compile(r"\bbail\s+(?:is\s+)?(?:hereby\s+)?(?:rejected|refused|denied|dismissed)\b|\bbail\s+application\s+is\s+(?:rejected|dismissed)\b", re.IGNORECASE)),
    ("acquitted",  re.compile(r"\bacquit(?:ted|tal)\b|\bset\s+free\b|\bfound\s+not\s+guilty\b", re.IGNORECASE)),
    ("convicted",  re.compile(r"\bconvict(?:ed|ion)\b|\bfound\s+guilty\b|\bguilty\s+as\s+charged\b", re.IGNORECASE)),
    ("quashed",    re.compile(r"\b(?:FIR|complaint|proceedings?|charge\s*sheet)\s+(?:is\s+)?quashed\b|\bhereby\s+quashed\b", re.IGNORECASE)),
    ("set_aside",  re.compile(r"\bset\s+aside\b|\boverturned\b|\breversed\b", re.IGNORECASE)),
    ("dismissed",  re.compile(r"\b(?:appeal|petition|application)\s+is\s+(?:hereby\s+)?dismissed\b", re.IGNORECASE)),
    ("allowed",    re.compile(r"\b(?:appeal|petition|application)\s+is\s+(?:hereby\s+)?allowed\b", re.IGNORECASE)),
]


def _extract_outcome(text: str) -> Optional[str]:
    if not text:
        return None
    for label, pat in _OUTCOME_PATTERNS:
        if pat.search(text):
            return label
    return None


# ============================================================== DOCTRINES

# Doctrine vocabulary — terms that distinguish one legal question from another.
# Multi-word entries allowed. Match is case-insensitive substring.
_DOCTRINE_TERMS = {
    "consent":                 [r"\bconsensual\b", r"\bconsent\s+given\b", r"\bwith\s+(?:her|his)\s+consent\b", r"\bage\s+proximity\b"],
    "delay_in_fir":            [r"\bdelay\s+in\s+(?:lodging\s+(?:the\s+)?)?FIR\b", r"\bdelayed\s+FIR\b", r"\bFIR\s+(?:was\s+)?lodged\s+(?:after|with\s+a\s+delay)"],
    "circumstantial":          [r"\bcircumstantial\s+evidence\b", r"\bchain\s+of\s+circumstances\b"],
    "last_seen":               [r"\blast\s+seen\b", r"\blast\s+seen\s+together\b"],
    "alibi":                   [r"\balibi\b"],
    "motive":                  [r"\bmotive\b"],
    "dying_declaration":       [r"\bdying\s+declaration\b"],
    "extra_judicial_confession": [r"\bextra[-\s]?judicial\s+confession\b"],
    "recovery":                [r"\brecovery\s+(?:of|made)\b", r"\bdisclosure\s+statement\b", r"\bSection\s+27\b"],
    "tip":                     [r"\btest\s+identification\s+parade\b", r"\bT\.?I\.?P\.?\b"],
    "hostile_witness":         [r"\bhostile\s+witness\b", r"\bturned\s+hostile\b"],
    "child_witness":           [r"\bchild\s+witness\b"],
    "interested_witness":      [r"\binterested\s+witness\b", r"\brelated\s+witness\b"],
    "false_implication":       [r"\bfalse\s+(?:case|implication|allegation)\b", r"\bfalsely\s+implicated\b"],
    "matrimonial_dispute":     [r"\bmatrimonial\s+dispute\b", r"\bmatrimonial\s+discord\b"],
    "settlement":              [r"\bsettlement\b", r"\bcompromise\b", r"\bcompounding\b", r"\bcompoundable\b"],
    "mens_rea":                [r"\bmens\s+rea\b"],
    "common_intention":        [r"\bcommon\s+intention\b", r"\bS\.?\s*34\s+IPC\b", r"\bSection\s+34\s+IPC\b"],
    "common_object":           [r"\bcommon\s+object\b", r"\bunlawful\s+assembly\b", r"\bS\.?\s*149\b"],
    "cheating":                [r"\bcheating\b", r"\bfraud(?:ulent)?\b"],
    "forgery":                 [r"\bforger(?:y|ed)\b", r"\bforged\s+document\b"],
    "criminal_breach_of_trust": [r"\bcriminal\s+breach\s+of\s+trust\b", r"\bCBT\b"],
    "dishonour":               [r"\bdishonou?r(?:ed)?\b", r"\bcheque\s+bounce\b", r"\binsufficient\s+funds\b"],
    "territorial_jurisdiction": [r"\bterritorial\s+jurisdiction\b"],
    "sanction":                [r"\bsanction\s+(?:under\s+)?(?:S\.?\s*197|S\.?\s*19)\b", r"\bprior\s+sanction\b", r"\bsanction\s+for\s+prosecution\b"],
    "default_bail_doctrine":   [r"\b167\s*\(\s*2\s*\)\s+CrPC\b", r"\bindefeasible\s+right\b"],
    "twin_conditions":         [r"\btwin\s+conditions?\b", r"\bSection\s+45\s+PMLA\b", r"\bS\.?\s*45\s+PMLA\b"],
    "small_quantity":          [r"\bsmall\s+quantity\b", r"\bcommercial\s+quantity\b", r"\bintermediate\s+quantity\b"],
    "personal_use":            [r"\bpersonal\s+(?:use|consumption)\b"],
}

# Pre-compile
_DOCTRINE_COMPILED = {
    label: [re.compile(p, re.IGNORECASE) for p in patterns]
    for label, patterns in _DOCTRINE_TERMS.items()
}


def _extract_doctrines(text: str) -> list[str]:
    if not text:
        return []
    hits = []
    for label, patterns in _DOCTRINE_COMPILED.items():
        if any(p.search(text) for p in patterns):
            hits.append(label)
    return hits


# ============================================================== SPECIAL CATEGORY

_SPECIAL_CATEGORY_PATTERNS = {
    "woman":     re.compile(r"\b(?:woman\s+accused|lady\s+accused|female\s+accused|she\s+is\s+the\s+accused|accused\s+is\s+a\s+woman)\b", re.IGNORECASE),
    "juvenile":  re.compile(r"\b(?:juvenile\s+(?:accused|offender)|child\s+in\s+conflict\s+with\s+law|JCL)\b", re.IGNORECASE),
    "senior":    re.compile(r"\b(?:senior\s+citizen|elderly\s+accused|aged\s+(?:7[0-9]|[89]\d)\s+years)\b", re.IGNORECASE),
    "sick":      re.compile(r"\b(?:sick(?:ly)?|ailing|medical\s+(?:condition|grounds)|terminal\s+illness|cancer\s+patient)\b", re.IGNORECASE),
    "pregnant":  re.compile(r"\bpregnant\b|\bpregnancy\b", re.IGNORECASE),
    "disabled":  re.compile(r"\b(?:differently[-\s]abled|disabled|physical\s+disability|mental\s+(?:disability|illness))\b", re.IGNORECASE),
}


def _extract_special_category(text: str) -> list[str]:
    if not text:
        return []
    return [label for label, pat in _SPECIAL_CATEGORY_PATTERNS.items() if pat.search(text)]


# ============================================================== NUMERICS

# These are scenario-specific but the extractor is generic — fires only when
# the pattern matches. False negatives are fine; false positives are not, so
# patterns are tight.

_NUMERIC_PATTERNS: dict[str, re.Pattern] = {
    # NDPS: "50 grams of charas", "2 kg of ganja", "10 kilograms heroin"
    "drug_qty_grams": re.compile(
        r"(\d+(?:\.\d+)?)\s*(g|gm|gms|grams?|kg|kgs?|kilograms?)\s+of\s+"
        r"(?:charas|ganja|heroin|opium|cocaine|MDMA|LSD|cannabis|hashish|brown\s+sugar|narcotics?|contraband|drugs?)",
        re.IGNORECASE,
    ),
    # 138 NI: "cheque for Rs. 5,00,000" / "amount of Rs 50000"
    "cheque_amount_inr": re.compile(
        r"(?:cheque|amount|Rs\.?|rupees|INR|₹)\s*(?:of\s+)?(?:Rs\.?\s*|INR\s*|₹\s*)?"
        r"((?:\d{1,3}(?:,\d{2,3})+|\d+)(?:\.\d+)?)\s*"
        r"(?:/-)?(?:\s*(?:lakhs?|crores?))?",
        re.IGNORECASE,
    ),
    # Custody: "90 days in jail" / "in custody for 6 months"
    "custody_days": re.compile(
        r"(?:in\s+(?:judicial\s+)?custody|in\s+jail|behind\s+bars)\s+(?:for\s+)?"
        r"(\d+)\s+(days?|months?|years?)",
        re.IGNORECASE,
    ),
    # FIR delay: "FIR was lodged after 4 months" / "delay of 30 days"
    "fir_delay_days": re.compile(
        r"(?:delay\s+(?:of\s+)?|FIR\s+(?:was\s+)?(?:lodged|registered)\s+(?:after\s+|with\s+a\s+delay\s+of\s+))"
        r"(\d+)\s+(days?|months?|years?)",
        re.IGNORECASE,
    ),
}


def _parse_indian_amount(num_str: str, qualifier: str = "") -> Optional[int]:
    """Convert '5,00,000' or '5 lakhs' to INR integer."""
    try:
        cleaned = num_str.replace(",", "").strip()
        value = float(cleaned)
    except ValueError:
        return None
    q = qualifier.lower()
    if "lakh" in q:
        value *= 100_000
    elif "crore" in q:
        value *= 10_000_000
    return int(value)


def _to_days(amount: int, unit: str) -> int:
    """Convert (amount, unit) → days."""
    u = unit.lower()
    if u.startswith("year"):
        return amount * 365
    if u.startswith("month"):
        return amount * 30
    return amount  # days


def _to_grams(amount: float, unit: str) -> float:
    u = unit.lower()
    if u.startswith("kg") or u.startswith("kilogram"):
        return amount * 1000
    return amount


def _extract_numerics(text: str) -> dict[str, Any]:
    if not text:
        return {}
    out: dict[str, Any] = {}

    m = _NUMERIC_PATTERNS["drug_qty_grams"].search(text)
    if m:
        try:
            out["drug_qty_grams"] = round(_to_grams(float(m.group(1)), m.group(2)), 2)
        except (ValueError, IndexError):
            pass

    # Cheque amount — pull all hits and take the LARGEST (usually the
    # principal sum, not interest or fees).
    cheque_hits = []
    for m in _NUMERIC_PATTERNS["cheque_amount_inr"].finditer(text):
        # Look ahead in the match for 'lakh'/'crore' qualifier
        end = m.end()
        tail = text[end:end + 20].lower()
        qualifier = "lakh" if "lakh" in tail else ("crore" if "crore" in tail else "")
        amount = _parse_indian_amount(m.group(1), qualifier)
        if amount and 100 <= amount <= 10_000_000_000:   # sanity bounds
            cheque_hits.append(amount)
    if cheque_hits:
        out["cheque_amount_inr"] = max(cheque_hits)

    m = _NUMERIC_PATTERNS["custody_days"].search(text)
    if m:
        try:
            out["custody_days"] = _to_days(int(m.group(1)), m.group(2))
        except (ValueError, IndexError):
            pass

    m = _NUMERIC_PATTERNS["fir_delay_days"].search(text)
    if m:
        try:
            out["fir_delay_days"] = _to_days(int(m.group(1)), m.group(2))
        except (ValueError, IndexError):
            pass

    return out


# ============================================================== WEAPON

_WEAPON_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("firearm",  re.compile(r"\b(?:firearm|pistol|revolver|gun|rifle|country[-\s]made\s+pistol|katta|gunshot|bullet\s+(?:wound|injury))\b", re.IGNORECASE)),
    ("knife",    re.compile(r"\b(?:knife|dagger|chhuri|chaaku|stabbed?|stab\s+wound|sharp[-\s]edged\s+weapon)\b", re.IGNORECASE)),
    ("blunt",    re.compile(r"\b(?:lathi|danda|iron\s+rod|stick|blunt\s+(?:weapon|object)|hammer|axe)\b", re.IGNORECASE)),
    ("poison",   re.compile(r"\b(?:poison(?:ed|ing)?|toxic\s+substance|cyanide|insecticide)\b", re.IGNORECASE)),
    ("strangulation", re.compile(r"\bstrangulation\b|\bstrangled\b|\bhanging\b|\bligature\s+mark\b", re.IGNORECASE)),
    ("acid",     re.compile(r"\bacid\s+attack\b|\bacid\s+thrown\b", re.IGNORECASE)),
]


def _extract_weapon(text: str) -> Optional[str]:
    if not text:
        return None
    for label, pat in _WEAPON_PATTERNS:
        if pat.search(text):
            return label
    return None


# ============================================================== PUBLIC API

def extract_facts(text: str) -> dict[str, Any]:
    """Run the full fact extraction pipeline on free-text input.

    Returns a dict with whichever fact dimensions fired. Empty dimensions
    are omitted (NOT set to None / []) so the JSON payload stays compact
    and downstream scorers can use `if facts.get('statutes'):` cleanly.

    The same function is called on both:
      - lawyer queries  (typically 1-3 sentences)
      - case judgments  (typically thousands of words)
    so it has to be robust against both very short and very long input.
    """
    if not text or not isinstance(text, str):
        return {}

    facts: dict[str, Any] = {}

    statutes = _extract_statutes(text)
    if statutes:
        facts["statutes"] = statutes

    stage = _extract_stage(text)
    if stage:
        facts["stage"] = stage

    court_level = _extract_court_level(text)
    if court_level:
        facts["court_level"] = court_level

    victim = _extract_victim(text)
    if victim:
        facts["victim"] = victim

    accused = _extract_accused(text)
    if accused:
        facts["accused"] = accused

    outcome = _extract_outcome(text)
    if outcome:
        facts["outcome"] = outcome

    doctrines = _extract_doctrines(text)
    if doctrines:
        facts["doctrines"] = doctrines

    special = _extract_special_category(text)
    if special:
        facts["special_category"] = special

    numerics = _extract_numerics(text)
    if numerics:
        facts["numerics"] = numerics

    weapon = _extract_weapon(text)
    if weapon:
        facts["weapon"] = weapon

    return facts


# ============================================================== SCORING

# Weights for fact-vector overlap. Tuned by hand against the design notes:
# statute match is the strongest signal, weapon is a nice-to-have.
SCORE_WEIGHTS = {
    "statute":          5.0,
    "stage":            3.0,
    "court_level":      1.5,
    "victim_minor":     2.0,
    "victim_gender":    1.0,
    "accused_role":     1.5,
    "outcome":          2.0,
    "doctrines":        1.5,
    "special_category": 1.5,
    "weapon":           0.5,
    "numerics":         1.0,
}


def score_overlap(query_facts: dict, case_facts: dict) -> tuple[float, dict]:
    """Score the overlap between query facts and case facts.

    Returns (total_score, breakdown_dict). The breakdown is for debugging /
    explainable scoring. Both inputs are the output of extract_facts().

    The scoring philosophy:
      - A dimension only contributes if BOTH query and case have it.
        (No signal from a dimension the user didn't even mention.)
      - List dimensions: score = weight * |intersection| / |query_set|
        (Jaccard-style but normalised by query, not union — we don't want
         to penalise long judgments that mention extra statutes.)
      - Binary dimensions: score = weight if match else 0.
      - Numeric closeness: score = weight * proximity (1 / (1 + log-distance)).
    """
    if not query_facts or not case_facts:
        return 0.0, {}

    breakdown: dict[str, float] = {}

    # --- statutes (list overlap, query-normalised) ---
    qs = set(query_facts.get("statutes") or [])
    cs = set(case_facts.get("statutes") or [])
    if qs and cs:
        # Match on full ref (IPC-302) OR on bare statute (IPC)
        qs_full = {s for s in qs if "-" in s}
        qs_bare = {s.split("-")[0] for s in qs}
        cs_full = {s for s in cs if "-" in s}
        cs_bare = {s.split("-")[0] for s in cs}

        # Full-ref matches are stronger than bare-statute matches
        full_overlap = qs_full & cs_full
        bare_overlap = (qs_bare & cs_bare) - {s.split("-")[0] for s in full_overlap}
        denom = max(len(qs_full | qs_bare), 1)
        statute_score = SCORE_WEIGHTS["statute"] * (len(full_overlap) + 0.4 * len(bare_overlap)) / denom
        if statute_score > 0:
            breakdown["statute"] = round(statute_score, 2)

    # --- stage (list overlap) ---
    q_stage = set(query_facts.get("stage") or [])
    c_stage = set(case_facts.get("stage") or [])
    if q_stage and c_stage:
        overlap = q_stage & c_stage
        if overlap:
            breakdown["stage"] = round(SCORE_WEIGHTS["stage"] * len(overlap) / len(q_stage), 2)

    # --- court level (exact match) ---
    if query_facts.get("court_level") and case_facts.get("court_level"):
        if query_facts["court_level"] == case_facts["court_level"]:
            breakdown["court_level"] = SCORE_WEIGHTS["court_level"]

    # --- victim attributes ---
    q_victim = query_facts.get("victim") or {}
    c_victim = case_facts.get("victim") or {}
    if q_victim and c_victim:
        if q_victim.get("is_minor") and c_victim.get("is_minor"):
            breakdown["victim_minor"] = SCORE_WEIGHTS["victim_minor"]
        if q_victim.get("gender") and c_victim.get("gender") == q_victim.get("gender"):
            breakdown["victim_gender"] = SCORE_WEIGHTS["victim_gender"]

    # --- accused role ---
    q_acc = query_facts.get("accused") or {}
    c_acc = case_facts.get("accused") or {}
    if q_acc and c_acc:
        if q_acc.get("role") and q_acc.get("role") == c_acc.get("role"):
            breakdown["accused_role"] = SCORE_WEIGHTS["accused_role"]

    # --- outcome ---
    if query_facts.get("outcome") and case_facts.get("outcome"):
        if query_facts["outcome"] == case_facts["outcome"]:
            breakdown["outcome"] = SCORE_WEIGHTS["outcome"]

    # --- doctrines (list overlap) ---
    q_doc = set(query_facts.get("doctrines") or [])
    c_doc = set(case_facts.get("doctrines") or [])
    if q_doc and c_doc:
        overlap = q_doc & c_doc
        if overlap:
            breakdown["doctrines"] = round(SCORE_WEIGHTS["doctrines"] * len(overlap) / len(q_doc), 2)

    # --- special category (list overlap) ---
    q_sp = set(query_facts.get("special_category") or [])
    c_sp = set(case_facts.get("special_category") or [])
    if q_sp and c_sp:
        overlap = q_sp & c_sp
        if overlap:
            breakdown["special_category"] = round(SCORE_WEIGHTS["special_category"] * len(overlap) / len(q_sp), 2)

    # --- weapon ---
    if query_facts.get("weapon") and case_facts.get("weapon"):
        if query_facts["weapon"] == case_facts["weapon"]:
            breakdown["weapon"] = SCORE_WEIGHTS["weapon"]

    # --- numerics: proximity scoring (within an order of magnitude → strong) ---
    q_num = query_facts.get("numerics") or {}
    c_num = case_facts.get("numerics") or {}
    if q_num and c_num:
        num_score = 0.0
        shared_keys = set(q_num) & set(c_num)
        for k in shared_keys:
            try:
                qv = float(q_num[k])
                cv = float(c_num[k])
                if qv <= 0 or cv <= 0:
                    continue
                ratio = max(qv, cv) / min(qv, cv)
                # ratio=1 → proximity=1; ratio=10 → proximity≈0.5; ratio=100 → ≈0.33
                import math
                proximity = 1.0 / (1.0 + math.log10(ratio))
                num_score += SCORE_WEIGHTS["numerics"] * proximity
            except (ValueError, TypeError):
                continue
        if num_score > 0:
            breakdown["numerics"] = round(num_score, 2)

    total = sum(breakdown.values())
    return round(total, 2), breakdown


__all__ = ["extract_facts", "score_overlap", "SCORE_WEIGHTS"]
