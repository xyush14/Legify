"""
Case-caption metadata extractor for Indian judgment text.

This is the *catalogue layer* — distinct from `fact_extractor.py` (which
extracts legal facts like statutes / stage / doctrines). This module
extracts what goes on the COVER of a judgment:

    - parties           : "Sunil Bharti Mittal v. Central Bureau of Investigation"
    - petitioner / respondent : separated for downstream display
    - citation          : "(2024) 5 SCC 123", "AIR 2023 SC 456", etc.
    - court             : "Supreme Court of India", "Allahabad High Court, Lucknow Bench"
    - judges            : ["A.B. Sharma, J.", "C.D. Verma, J."]
    - date              : "14 Aug 2024" / "2024-08-14"
    - case_number       : "Criminal Appeal No. 1234 of 2023"

The current `hf_judgments.title` field is broken for most IL-TUR subsets
— it contains the first sentence of the judgment body instead of the
caption. This extractor fixes that at backfill time by reading the full
text and extracting clean metadata to store in `case_metadata_json`.

Design principles
-----------------
1. **Conservative.** Better to leave a field None than emit a wrong value.
   Wrong metadata flowing into a case card destroys lawyer trust.
2. **First 50 lines only.** Indian judgments put all caption info at the
   top. Scanning beyond that is wasted compute and risks false positives.
3. **Regex over heuristics.** Determinism beats cleverness. If a pattern
   doesn't match, return None — let the LLM downstream fill gaps from the
   refined query envelope.
4. **No dependency on subset.** Works equally on cjpe / summ / lsi / pcr /
   bail. Subset-specific tweaks are minimal (mostly the bail title
   synthesis already in retrieval.py).

Usage
-----
    from headnote.retrieval.case_metadata_extractor import extract_metadata

    md = extract_metadata(text, source="cjpe", doc_id="hf:cjpe:xxxx")
    # -> CaseMetadata(parties="X v. Y", citation="(2024) 5 SCC 123", ...)
    json_blob = md.to_json()
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field, asdict
from typing import Optional


# ============================================================== datatypes

@dataclass
class CaseMetadata:
    """Structured caption + metadata of a judgment. Every field is optional;
    we emit whatever the extractor finds with high confidence."""
    parties:        Optional[str] = None      # "X v. Y" (display-ready)
    petitioner:     Optional[str] = None      # "X" (clean)
    respondent:     Optional[str] = None      # "Y" (clean)
    citation:       Optional[str] = None      # "(2024) 5 SCC 123"
    citations_all:  list[str] = field(default_factory=list)  # all citations found
    court:          Optional[str] = None      # "Supreme Court of India"
    bench:          Optional[str] = None      # "Lucknow Bench" / "Division Bench"
    judges:         list[str] = field(default_factory=list)
    date:           Optional[str] = None      # ISO format YYYY-MM-DD
    case_number:    Optional[str] = None      # "Criminal Appeal No. 1234 of 2023"
    # Quality flags — downstream can decide whether to trust each field
    confidence:     str = "low"               # low | medium | high
    notes:          list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)

    def display_caption(self) -> Optional[str]:
        """The string we'd show as the case title in a card. None if we
        couldn't extract anything usable."""
        if self.parties:
            return self.parties
        if self.petitioner and self.respondent:
            return f"{self.petitioner} v. {self.respondent}"
        return None


# ============================================================== regex patterns

# Match common citation formats used in Indian reporters. Conservative —
# only emit if we see the unambiguous "(YEAR) Vol REPORTER PAGE" or
# "AIR YEAR REPORTER PAGE" patterns.
_CITATION_PATTERNS = [
    # (2024) 5 SCC 123  /  (2024) 5 S.C.C. 123
    re.compile(r"\((?:19|20)\d{2}\)\s*\d+\s*S\.?\s*C\.?\s*C\.?\s*\d+", re.IGNORECASE),
    # AIR 2023 SC 456
    re.compile(r"A\.?\s*I\.?\s*R\.?\s*(?:19|20)\d{2}\s*S\.?\s*C\.?\s*\d+", re.IGNORECASE),
    # (2024) SCC OnLine SC 567
    re.compile(r"\((?:19|20)\d{2}\)\s*S\.?\s*C\.?\s*C\.?\s*OnLine\s*[A-Z]{2,4}(?:\s+\w+)?\s*\d+", re.IGNORECASE),
    # 2024 SCC OnLine SC 567
    re.compile(r"(?:19|20)\d{2}\s+SCC\s+OnLine\s+[A-Z]{2,4}(?:\s+\w+)?\s+\d+", re.IGNORECASE),
    # 1995 Cri LJ 1234  /  1995 CriLJ 1234
    re.compile(r"(?:19|20)\d{2}\s*Cri\.?\s*L\.?\s*J\.?\s*\d+", re.IGNORECASE),
    # (1995) 1 Crimes 234
    re.compile(r"\((?:19|20)\d{2}\)\s*\d+\s*Crimes\s*\d+", re.IGNORECASE),
    # 2024 (1) MPLJ 123  /  2024 MPLJ 123
    re.compile(r"(?:19|20)\d{2}\s*\(?\d*\)?\s*M\.?\s*P\.?\s*L\.?\s*J\.?\s*\d+", re.IGNORECASE),
    # (2024) 1 BomCR 345  /  (2024) 1 Bom CR 345
    re.compile(r"\((?:19|20)\d{2}\)\s*\d+\s*[A-Z][a-z]{1,4}\s*C\.?\s*R\.?\s*\d+", re.IGNORECASE),
]

# Indian judgments list parties in TWO different layouts:
#
# 1. Inline:   "Sunil Bharti Mittal v. Central Bureau of Investigation"
# 2. Stacked (most common for SC/HC):
#       Sunil Bharti Mittal              .... Appellant
#       Versus
#       Central Bureau of Investigation        .... Respondent
#
# Party name: one or more capitalised "words" each separated by a SINGLE
# space. This natural-language-shaped pattern stops at runs of 2+ spaces
# (the indentation gap before ".... Appellant"), at em-dashes, dots, or
# newlines. Avoids greedy/non-greedy quantifier headaches.
_PARTY_WORD = r"[A-Z][A-Za-z0-9'\-]*(?:\.|,)?"
_PARTY_NAME = rf"{_PARTY_WORD}(?: (?:{_PARTY_WORD}|of|and|the|&|in|for))*"

# Stacked pattern — "Versus" on its own line between two party-name lines.
# Petitioner line: party_name + (any chars until \n).  Respondent same.
_VS_STACKED_PATTERN = re.compile(
    r"^[ \t]*(" + _PARTY_NAME + r")\b"                # petitioner (anchored at line start)
    r"[^\n]*\n+"                                       # rest of line + newline
    r"[ \t]*(?:VERSUS|Versus|versus|Vs\.?|vs\.?|V\.?|VS\.?)[ \t]*\n+"
    r"[ \t]*(" + _PARTY_NAME + r")\b",                # respondent
    re.MULTILINE,
)

# Inline pattern — "X v. Y" on one line. Strictly anchored to line start
# OR start of head_text so we don't catch in-body precedent references.
_VS_INLINE_PATTERN = re.compile(
    r"(?:^|\n)[ \t]*"
    r"(" + _PARTY_NAME + r")"
    r"\s+(?:v\.?|vs\.?|versus|Vs\.?|VS\.?)\s+"
    r"(" + _PARTY_NAME + r")",
    re.MULTILINE,
)

# Match court header lines:
#   "IN THE SUPREME COURT OF INDIA"
#   "IN THE HIGH COURT OF MADHYA PRADESH, JABALPUR BENCH"
#   "IN THE COURT OF SESSIONS JUDGE, AGRA"
_COURT_PATTERNS = [
    (re.compile(r"IN\s+THE\s+SUPREME\s+COURT\s+OF\s+INDIA", re.IGNORECASE),
     "Supreme Court of India", "supreme_court"),
    (re.compile(r"IN\s+THE\s+HIGH\s+COURT\s+OF\s+([A-Z][A-Za-z &]+?)(?:\s+AT\s+|\s+\(|\s*,|\s*\n)", re.IGNORECASE),
     None, "high_court"),  # state captured separately
    (re.compile(r"IN\s+THE\s+(?:HON'?BLE\s+)?COURT\s+OF\s+(?:THE\s+)?SESSIONS\s+JUDGE(?:,\s*([A-Z][A-Za-z]+))?", re.IGNORECASE),
     None, "sessions"),
    (re.compile(r"IN\s+THE\s+(?:HON'?BLE\s+)?COURT\s+OF\s+(?:THE\s+)?(?:CHIEF\s+)?JUDICIAL\s+MAGISTRATE", re.IGNORECASE),
     "Court of Judicial Magistrate", "magistrate"),
    (re.compile(r"IN\s+THE\s+(?:HON'?BLE\s+)?COURT\s+OF\s+(?:THE\s+)?(?:CHIEF\s+)?METROPOLITAN\s+MAGISTRATE", re.IGNORECASE),
     "Court of Metropolitan Magistrate", "magistrate"),
    (re.compile(r"IN\s+THE\s+FAMILY\s+COURT(?:\s+AT\s+([A-Z][A-Za-z]+))?", re.IGNORECASE),
     "Family Court", "family"),
]

# Match bench info: "Aurangabad Bench" / "Madurai Bench" / "Lucknow Bench"
_BENCH_PATTERN = re.compile(
    r"\b(?:AT\s+)?([A-Z][a-z]+(?:pur|abad|bagh|gar|ganj|gaon|bad|nagar|patnam))\s+(?:Bench|BENCH)\b",
    re.MULTILINE,
)

# Match case-number lines:
#   "CRIMINAL APPEAL NO. 1234 OF 2023"
#   "WRIT PETITION (CRL.) NO. 567 OF 2024"
#   "MISC. CRIMINAL CASE NO. 27486 OF 2024"
#   "M.Cr.C. No. 27486/2024"
_CASE_NO_PATTERNS = [
    re.compile(
        r"(CRIMINAL\s+APPEAL|CRIMINAL\s+REVISION|CRIMINAL\s+(?:MISC\.?\s+)?(?:WRIT|APPLICATION|PETITION)|"
        r"M\.\s*Cr\.\s*C\.|MISC\.?\s+CRIMINAL\s+CASE|WRIT\s+PETITION(?:\s*\([Cc]rl?\.?\))?|S\.L\.P\.)"
        r"\s*(?:\([A-Za-z]+\))?\s*(?:No\.?\s*)?"
        r"([\d,]+)\s*(?:of|/)\s*(\d{4})",
        re.IGNORECASE,
    ),
]

# Match judge listing lines:
#   "BEFORE: HON'BLE MR. JUSTICE A.B. SHARMA"
#   "CORAM: A.B. SHARMA, J."
#   "A.B. SHARMA, J."
_JUDGE_PATTERNS = [
    re.compile(r"(?:BEFORE|CORAM)\s*:?\s*(?:HON'?BLE\s+)?(?:MR\.?|MRS\.?|MS\.?|DR\.?|JUSTICE)?\s*"
               r"([A-Z][A-Z. ]{2,40}?)\s*(?:,\s*J\.?J?\.?|,\s*JUDGE|\n)", re.IGNORECASE),
    re.compile(r"^([A-Z][A-Z. ]{2,40}?),\s*JJ?\.?\s*$", re.MULTILINE),
]

# Match dates in common Indian formats:
#   "DATED: 14.08.2024"   "Date of judgment: 14/08/2024"
#   "Decided on: August 14, 2024"   "Pronounced on 14th August 2024"
_DATE_PATTERNS = [
    re.compile(
        r"(?:DATED|DATE\s+OF\s+(?:JUDGMENT|ORDER|DECISION)|PRONOUNCED\s+ON|DECIDED\s+ON|RESERVED\s+ON|ORDER\s+DATED)"
        r"\s*:?\s*"
        r"(\d{1,2})(?:st|nd|rd|th)?[\s.\-/]+(\d{1,2}|[A-Za-z]+)[\s.\-/]+((?:19|20)\d{2})",
        re.IGNORECASE,
    ),
    re.compile(
        r"(?:DATED|DATE\s+OF\s+(?:JUDGMENT|ORDER))"
        r"\s*:?\s*"
        r"((?:19|20)\d{2})[\s.\-/]+(\d{1,2}|[A-Za-z]+)[\s.\-/]+(\d{1,2})",
        re.IGNORECASE,
    ),
]

_MONTH_NAMES = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6,
    "jul": 7, "july": 7, "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


# ============================================================== extractors

def _clean_party_name(s: str) -> str:
    """Tidy a captured party-name string: strip dots, collapse whitespace,
    trim trailing punctuation."""
    s = re.sub(r"\.{2,}", "", s)             # remove trailing "....."
    s = re.sub(r"\s+", " ", s).strip()
    s = s.strip(".,;: \t")
    return s


def _extract_parties(head_text: str) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Extract petitioner and respondent from the head of the judgment.
    Returns (combined_display, petitioner, respondent).

    Tries stacked layout first (dominant convention in SC/HC judgments),
    then inline layout. Both go through the same sanity filter.
    """
    candidates = []
    m = _VS_STACKED_PATTERN.search(head_text)
    if m:
        candidates.append((m.group(1), m.group(2)))
    m = _VS_INLINE_PATTERN.search(head_text)
    if m:
        candidates.append((m.group(1), m.group(2)))

    for raw_pet, raw_res in candidates:
        pet = _clean_party_name(raw_pet)
        res = _clean_party_name(raw_res)
        if not (3 <= len(pet) <= 100 and 3 <= len(res) <= 100):
            continue
        # Reject extractions where either side looks like a body fragment.
        bad_starts = (
            "the ", "a ", "an ", "this ", "that ",
            "appellant", "respondent", "petitioner", "applicant",
            "accused", "complainant",
            "in ", "on ", "as ", "by ", "for ", "from ",
            "section ", "article ",
        )
        if pet.lower().startswith(bad_starts) or res.lower().startswith(bad_starts):
            continue
        # Reject if either side contains sentence-y words
        sentence_signals = (
            " was ", " were ", " is ", " are ", " has ", " have ",
            " filed ", " held ", " summoned ", " arrested ", " convicted ",
        )
        full_string = f"{pet} {res}".lower()
        if any(s in full_string for s in sentence_signals):
            continue
        return f"{pet} v. {res}", pet, res
    return None, None, None


def _extract_citations(text: str) -> list[str]:
    """Extract all citation strings, deduplicated, in document order."""
    seen: set[str] = set()
    out: list[str] = []
    for pattern in _CITATION_PATTERNS:
        for m in pattern.finditer(text):
            cite = re.sub(r"\s+", " ", m.group(0)).strip()
            key = cite.lower()
            if key not in seen:
                seen.add(key)
                out.append(cite)
    return out[:8]


def _extract_court_and_bench(head_text: str) -> tuple[Optional[str], Optional[str]]:
    """Identify the court level + bench (if any) from the head of the
    judgment. Returns (display_label, bench)."""
    bench = None
    bm = _BENCH_PATTERN.search(head_text)
    if bm:
        bench = f"{bm.group(1).title()} Bench"

    for pattern, label, level in _COURT_PATTERNS:
        m = pattern.search(head_text)
        if not m:
            continue
        if label:
            full_label = label
        elif level == "high_court":
            state = _clean_party_name(m.group(1)).title()
            full_label = f"High Court of {state}"
            if bench:
                full_label = f"{full_label}, {bench}"
        elif level == "sessions":
            place = (m.group(1) if m.lastindex else None) or ""
            full_label = f"Court of Sessions{', ' + place.title() if place else ''}"
        else:
            full_label = m.group(0).title()
        return full_label, bench
    return None, bench


def _extract_case_number(head_text: str) -> Optional[str]:
    for pattern in _CASE_NO_PATTERNS:
        m = pattern.search(head_text)
        if not m:
            continue
        kind = re.sub(r"\s+", " ", m.group(1)).strip().title()
        num = m.group(2).strip()
        year = m.group(3).strip()
        return f"{kind} No. {num} of {year}"
    return None


def _extract_judges(head_text: str) -> list[str]:
    """Extract judge name strings. Returns up to 5, deduplicated."""
    found: list[str] = []
    seen: set[str] = set()
    for pattern in _JUDGE_PATTERNS:
        for m in pattern.finditer(head_text):
            name = re.sub(r"\s+", " ", m.group(1)).strip().title()
            if 3 <= len(name) <= 60 and name.lower() not in seen:
                seen.add(name.lower())
                found.append(f"{name}, J.")
            if len(found) >= 5:
                return found
    return found


def _extract_date(head_text: str) -> Optional[str]:
    """Extract date of judgment as ISO YYYY-MM-DD (when possible). Returns
    None if no date pattern matches."""
    for pattern in _DATE_PATTERNS:
        m = pattern.search(head_text)
        if not m:
            continue
        try:
            g1, g2, g3 = m.group(1), m.group(2), m.group(3)
            # First pattern: day, month, year
            if int(g3) >= 1900:
                day = int(g1)
                month = (
                    int(g2) if g2.isdigit()
                    else _MONTH_NAMES.get(g2.lower()[:3], None)
                )
                year = int(g3)
            else:
                # Second pattern: year, month, day
                year = int(g1)
                month = (
                    int(g2) if g2.isdigit()
                    else _MONTH_NAMES.get(g2.lower()[:3], None)
                )
                day = int(g3)
            if not (month and 1 <= month <= 12 and 1 <= day <= 31 and 1900 <= year <= 2100):
                continue
            return f"{year:04d}-{month:02d}-{day:02d}"
        except (ValueError, AttributeError):
            continue
    return None


# ============================================================== public API

def extract_metadata(text: str, *, source: str = "", doc_id: str = "") -> CaseMetadata:
    """Extract caption + metadata from a judgment's full text.

    Only the FIRST ~50 lines (or 5000 chars) are scanned — caption info
    always appears at the top of Indian judgments. Bottom of judgment is
    irrelevant for metadata extraction and adds false-positive risk.
    """
    md = CaseMetadata()
    if not text or len(text) < 100:
        md.notes.append("text-too-short")
        return md

    # Take the first 50 non-empty lines OR 5000 chars, whichever is smaller
    head_lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line:
            head_lines.append(line)
        if len(head_lines) >= 50:
            break
    head_text = "\n".join(head_lines)
    if len(head_text) > 5000:
        head_text = head_text[:5000]

    # Parties
    combined, pet, res = _extract_parties(head_text)
    md.parties = combined
    md.petitioner = pet
    md.respondent = res

    # Citations (scan whole text — sometimes citation appears inline late)
    md.citations_all = _extract_citations(text[:20000])
    md.citation = md.citations_all[0] if md.citations_all else None

    # Court + bench
    court_label, bench = _extract_court_and_bench(head_text)
    md.court = court_label
    md.bench = bench

    # Case number
    md.case_number = _extract_case_number(head_text)

    # Judges
    md.judges = _extract_judges(head_text)

    # Date
    md.date = _extract_date(head_text)

    # Confidence scoring — how many fields did we extract?
    extracted_count = sum(1 for v in [
        md.parties, md.citation, md.court, md.case_number, md.date
    ] if v)
    if extracted_count >= 4:
        md.confidence = "high"
    elif extracted_count >= 2:
        md.confidence = "medium"
    else:
        md.confidence = "low"

    return md


def display_title(md: CaseMetadata, fallback_doc_id: str = "") -> str:
    """Build a display-ready title from extracted metadata. Falls back to
    a structured placeholder if we couldn't extract anything usable.
    Never returns garbage like '=== Facts And Arguments ==='."""
    caption = md.display_caption()
    if caption:
        return caption
    if md.case_number:
        return md.case_number
    if md.court and md.date:
        return f"{md.court} — {md.date}"
    if md.court:
        return f"{md.court} judgment"
    short_id = (fallback_doc_id.rsplit(":", 1)[-1] or "").replace("_", " ")[:60]
    return f"Judgment {short_id}" if short_id else "Judgment (metadata pending)"
