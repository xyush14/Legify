"""Deterministic query normalization — regex + alias dict.

What this layer fixes (FREE, ~5ms):
  1. Statute shorthand:  "U/S 372 CrPC"  →  "Section 372 of the CrPC, 1973"
  2. Act aliases:         "NI Act"        →  "Negotiable Instruments Act, 1881"
  3. BNS/BNSS aliases:    "BNS S. 100"    →  "Section 100 of the BNS, 2023"
  4. Common typos:        "i should"      →  "should"   (legal-domain grammar fixes)
  5. Punctuation cleanup: spurious commas/periods around statutes

What it does NOT do (deferred to canonicalize.py + LLM):
  - intent classification
  - semantic reformulation
  - question/statement detection

Returns a NormalizedQuery dataclass — keeps both the original and the cleaned
form, plus a list of substitutions applied (used for transparency in /api/me).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field


# ----------------------------------------------------------------- Substitution rules

# Statute alias → canonical citation. Order matters — longest match first.
# Tuples of (regex pattern, replacement, label).
_STATUTE_ALIASES: list[tuple[str, str, str]] = [
    # Indian Penal Code
    (r"\bIPC\b", "Indian Penal Code, 1860", "IPC"),
    (r"\bI\.P\.C\.?\b", "Indian Penal Code, 1860", "I.P.C."),

    # Code of Criminal Procedure
    (r"\bCrPC\b", "Code of Criminal Procedure, 1973", "CrPC"),
    (r"\bCr\.P\.C\.?\b", "Code of Criminal Procedure, 1973", "Cr.P.C."),
    (r"\bCr\.\s?P\.\s?C\.?\b", "Code of Criminal Procedure, 1973", "Cr. P. C."),

    # Bharatiya Nyaya Sanhita
    (r"\bBNS\b", "Bharatiya Nyaya Sanhita, 2023", "BNS"),
    (r"\bB\.N\.S\.?\b", "Bharatiya Nyaya Sanhita, 2023", "B.N.S."),

    # Bharatiya Nagarik Suraksha Sanhita
    (r"\bBNSS\b", "Bharatiya Nagarik Suraksha Sanhita, 2023", "BNSS"),
    (r"\bB\.N\.S\.S\.?\b", "Bharatiya Nagarik Suraksha Sanhita, 2023", "B.N.S.S."),

    # Bharatiya Sakshya Adhiniyam
    (r"\bBSA\b", "Bharatiya Sakshya Adhiniyam, 2023", "BSA"),

    # Indian Evidence Act
    (r"\bIEA\b", "Indian Evidence Act, 1872", "IEA"),
    (r"\bEvidence Act\b(?!\s*,)", "Indian Evidence Act, 1872", "Evidence Act"),

    # Negotiable Instruments Act
    (r"\bNI Act\b(?!\s*,)", "Negotiable Instruments Act, 1881", "NI Act"),
    (r"\bN\.I\. Act\b", "Negotiable Instruments Act, 1881", "N.I. Act"),

    # Limitation Act
    (r"\bLimitation Act\b(?!\s*,)", "Limitation Act, 1963", "Limitation Act"),

    # POCSO
    (r"\bPOCSO Act\b(?!\s*,)", "Protection of Children from Sexual Offences Act, 2012", "POCSO"),
    (r"\bPOCSO\b(?!\s+Act)", "Protection of Children from Sexual Offences Act, 2012", "POCSO"),

    # NDPS
    (r"\bNDPS Act\b(?!\s*,)", "Narcotic Drugs and Psychotropic Substances Act, 1985", "NDPS"),
    (r"\bNDPS\b(?!\s+Act)", "Narcotic Drugs and Psychotropic Substances Act, 1985", "NDPS"),

    # PMLA
    (r"\bPMLA\b", "Prevention of Money Laundering Act, 2002", "PMLA"),

    # UAPA
    (r"\bUAPA\b", "Unlawful Activities (Prevention) Act, 1967", "UAPA"),

    # Domestic Violence
    (r"\bDV Act\b(?!\s*,)", "Protection of Women from Domestic Violence Act, 2005", "DV Act"),

    # Dowry Prohibition
    (r"\bDowry Prohibition Act\b(?!\s*,)", "Dowry Prohibition Act, 1961", "Dowry Prohibition Act"),

    # 498A is a section of IPC — leave standalone
]


# Section shorthand → "Section N". Run AFTER statute aliases so the section
# reference attaches to the now-expanded statute name where possible.
_SECTION_SHORTHAND: list[tuple[str, str, str]] = [
    (r"\bU/[Ss]\s*\.?\s*(\d+[A-Z]*)\b", r"Section \1", "U/S → Section"),
    (r"\bu/s\s*\.?\s*(\d+[A-Z]*)\b", r"Section \1", "u/s → Section"),
    (r"\bS\.\s*(\d+[A-Z]*)\b", r"Section \1", "S. → Section"),
    (r"\bSec\.\s*(\d+[A-Z]*)\b", r"Section \1", "Sec. → Section"),
    (r"\bsec\.\s*(\d+[A-Z]*)\b", r"Section \1", "sec. → Section"),
]


# Stage shorthand — normalize to canonical stage names.
_STAGE_ALIASES: list[tuple[str, str, str]] = [
    (r"\bABA\b", "anticipatory bail application", "ABA"),
    (r"\banti\.\s*bail\b", "anticipatory bail", "anti. bail"),
    (r"\bdischarge appln?\.\b", "discharge application", "discharge appln."),
    (r"\bquash(?:ing)? petn\.?\b", "quashing petition", "quash petn."),
]


# Court shorthand
_COURT_ALIASES: list[tuple[str, str, str]] = [
    (r"\bHC\b(?!\.)", "High Court", "HC"),
    (r"\bSC\b(?!\.)", "Supreme Court", "SC"),
    (r"\bH\.C\.\b", "High Court", "H.C."),
    (r"\bS\.C\.\b", "Supreme Court", "S.C."),
    (r"\bAddl\. Sessions\b", "Additional Sessions", "Addl. Sessions"),
    (r"\bJMFC\b", "Judicial Magistrate First Class", "JMFC"),
    (r"\bCJM\b", "Chief Judicial Magistrate", "CJM"),
]


# Grammar / phrasing cleanup — small set of high-frequency legal-input errors.
_GRAMMAR_FIXES: list[tuple[str, str, str]] = [
    # "Then i should be the limitation days" → "Then what should be the limitation period"
    (r"\b[Tt]hen i should be the limitation days?\b", "Then what should be the limitation period", "i should be → what should be"),
    (r"\b[Tt]hen i should be the\b", "Then what should be the", "i should be → what should be"),
    # Lowercase "i" as a pronoun → uppercase
    (r"(?<=\s)i\s+(?=should|am|have|need|want|believe)", "I ", "i → I"),
    # Common: "wht" → "what"
    (r"\bwht\b", "what", "wht → what"),
    # "limitation days" → "limitation period" (legal terminology)
    (r"\blimitation days\b", "limitation period", "limitation days → limitation period"),
]


@dataclass
class NormalizedQuery:
    """Result of deterministic normalization."""
    raw:           str
    normalized:    str
    substitutions: list[dict] = field(default_factory=list)

    def applied(self) -> bool:
        return bool(self.substitutions)


def normalize(raw: str) -> NormalizedQuery:
    """Apply all deterministic rules. Idempotent + side-effect free.

    Returns a NormalizedQuery with the cleaned text and an audit list of
    what was substituted (useful for transparency in API responses).
    """
    if not raw or not raw.strip():
        return NormalizedQuery(raw=raw, normalized=raw)

    text = raw
    subs: list[dict] = []

    # Apply rule groups in order:
    #   1. Statute aliases (longest match handled by order in list)
    #   2. Section shorthand (U/S, S., Sec.)
    #   3. Stage shorthand (ABA, etc.)
    #   4. Court shorthand (HC, SC)
    #   5. Grammar fixes
    for group_name, rules in [
        ("statute",  _STATUTE_ALIASES),
        ("section",  _SECTION_SHORTHAND),
        ("stage",    _STAGE_ALIASES),
        ("court",    _COURT_ALIASES),
        ("grammar",  _GRAMMAR_FIXES),
    ]:
        for pattern, replacement, label in rules:
            new_text, n = re.subn(pattern, replacement, text)
            if n > 0 and new_text != text:
                subs.append({
                    "group":   group_name,
                    "rule":    label,
                    "count":   n,
                })
                text = new_text

    # Collapse extra whitespace.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\.", ".", text)  # " ." → "."
    text = re.sub(r"\.\s*\.", ".", text)
    text = text.strip()

    return NormalizedQuery(raw=raw, normalized=text, substitutions=subs)
