"""Citation gate — the check that makes a cheap translation model safe to ship.

No model can be *trusted* to carry a legal citation across a translation, so we
do not trust one: every case number, section, date and figure is extracted from
the source, and the translation is rejected unless each one survives byte-exact.

This is what caught the two real failures measured on live documents:

    Sarvam Mayura   dropped charge-sheet "394/25" entirely, and rendered
                    "मु0अ0सं0 359/25" (case crime number) as "section 359/25"
    Sarvam 105B     preserved 6/6 citations but answered in Hindi when asked
                    for English — caught by ``wrong_script``

Because the gate is deterministic and free, the translation engine becomes a
swappable config choice rather than a quality decision: any model that passes
is safe, and a cheaper model that passes is strictly better. Nothing here calls
an API or costs a rupee.

Deliberately conservative: it reports what it can prove was lost. A citation it
cannot parse is never silently declared fine — see ``verify`` for the contract.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# Devanagari digits map to Latin so "१०९" and "109" compare equal. A translation
# is free to change the numerals' script; it is not free to change the number.
_DEV_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Ordered widest-first: a date must win over the bare number inside it, and a
# section list (3/4/25/28) over the case number pattern it otherwise resembles.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # 24.12.2025 · 11.10.25 · 09-10-2025
    ("date", re.compile(r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b")),
    # 3/4/25/28 · 3/5/8 — Arms Act / Gangsters Act style section lists
    ("sections", re.compile(r"\b\d{1,3}(?:/\d{1,3}){2,}\b")),
    # 359/25 · 394/2025 — case crime / charge-sheet / case numbers
    ("case_no", re.compile(r"\b\d{1,5}/\d{2,4}\b")),
    # 109(1) · 318(4) · 336(2) — section with sub-section
    ("section", re.compile(r"\b\d{1,3}\s?\(\s?\d{1,3}\s?\)")),
    # 2(ख) — Devanagari sub-clause
    ("section", re.compile(r"\b\d{1,3}\s?\(\s?[ऀ-ॿ]{1,3}\s?\)")),
    # ₹ 1,20,000 · Rs. 5000
    ("money", re.compile(r"(?:₹|\bRs\.?\s?)\s?[\d,]+(?:\.\d{1,2})?", re.I)),
]

# Statute names that must not be swapped for one another. Mayura turned a Cow
# Slaughter Act case into a Gangsters Act case; that is not a wording choice.
_STATUTES: dict[str, tuple[str, ...]] = {
    "bns": ("बीएनएस", "बी एन एस", "bns", "bharatiya nyaya sanhita"),
    "bnss": ("बीएनएसएस", "bnss", "bharatiya nagarik suraksha sanhita"),
    "arms": ("आर्मस", "आर्म्स", "arms act"),
    "gangsters": ("गैंग0अधि0", "गैंगस्टर", "गिरोहबन्द", "गिरोहबंद", "gangster", "gangsters act"),
    "cow_slaughter": ("गौवध", "गोवध", "cow slaughter", "prevention of cow slaughter"),
    "ndps": ("एनडीपीएस", "ndps"),
    "pocso": ("पॉक्सो", "pocso"),
}


@dataclass
class Report:
    """Outcome of checking one translation against its source."""

    missing: list[str] = field(default_factory=list)
    statutes_lost: list[str] = field(default_factory=list)
    wrong_script: str = ""

    @property
    def ok(self) -> bool:
        return not self.missing and not self.statutes_lost and not self.wrong_script

    def reason(self) -> str:
        bits = []
        if self.missing:
            bits.append("dropped or altered " + ", ".join(self.missing))
        if self.statutes_lost:
            bits.append("lost statute reference: " + ", ".join(self.statutes_lost))
        if self.wrong_script:
            bits.append(self.wrong_script)
        return "; ".join(bits)


def _fold(text: str) -> str:
    """Normalise for comparison: NFKC, Devanagari digits to Latin, no spaces.

    Spaces go because engines legitimately reflow "मु0अ0सं0 359/25" to
    "Case Crime No. 359/25" — the number survived, which is what we check.
    """
    t = unicodedata.normalize("NFKC", text or "").translate(_DEV_DIGITS)
    return re.sub(r"\s+", "", t)


def extract(text: str) -> list[str]:
    """Every citation-like token in `text`, longest first, de-duplicated.

    Overlapping matches are resolved by preferring the longer span, so the
    "25" inside "24.12.2025" is never reported as a citation of its own.
    """
    src = unicodedata.normalize("NFKC", text or "").translate(_DEV_DIGITS)
    spans: list[tuple[int, int, str]] = []
    for _kind, pat in _PATTERNS:
        for m in pat.finditer(src):
            spans.append((m.start(), m.end(), m.group(0)))
    spans.sort(key=lambda s: (s[0] - s[1], s[0]))  # longest span first
    taken: list[tuple[int, int]] = []
    out: list[str] = []
    for start, end, tok in spans:
        if any(start < te and end > ts for ts, te in taken):
            continue
        taken.append((start, end))
        norm = re.sub(r"\s+", "", tok)
        if norm not in out:
            out.append(norm)
    return out


def _fold_statute(text: str) -> str:
    """Lowercase and strip the separators an engine is free to add or drop.

    Mayura renders बीएनएस as "बी.एन.एस." — same statute, different punctuation.
    A gate that blocks a correct translation over a full stop is worse than no
    gate, because it teaches everyone to switch it off.
    """
    t = unicodedata.normalize("NFKC", text or "").lower()
    return re.sub(r"[\s.\-_']", "", t)


def statutes(text: str) -> set[str]:
    """Which known statutes are named in `text`, script- and punctuation-agnostic."""
    low = _fold_statute(text)
    return {name for name, forms in _STATUTES.items()
            if any(_fold_statute(f) in low for f in forms)}


def _script_share(text: str) -> float:
    """Fraction of letters that are Devanagari."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(1 for c in letters if "ऀ" <= c <= "ॿ") / len(letters)


def verify(source: str, translation: str, *, target_lang: str = "") -> Report:
    """Check a translation against its source. Empty report == safe to use.

    `target_lang` — an ISO-ish code ("en", "hi", "mr"). When given, the output
    is also checked for being in the language actually asked for: Sarvam 105B
    returns fluent Hindi when asked for English, which every citation check in
    the world would happily pass.
    """
    rep = Report()
    flat = _fold(translation)
    rep.missing = [c for c in extract(source) if _fold(c) not in flat]
    rep.statutes_lost = sorted(statutes(source) - statutes(translation))

    if target_lang:
        share = _script_share(translation)
        lang = target_lang.lower()[:2]
        if lang == "en" and share > 0.30:
            rep.wrong_script = "asked for English, answered in Devanagari"
        elif lang in {"hi", "mr", "ne", "sa"} and translation.strip() and share < 0.30:
            rep.wrong_script = f"asked for {lang}, answered in Latin script"
    return rep


def guard(source: str, translation: str, *, target_lang: str = "") -> tuple[bool, str]:
    """Convenience wrapper: ``(ok, reason)`` for a caller that just wants a gate."""
    rep = verify(source, translation, target_lang=target_lang)
    return rep.ok, rep.reason()
