"""
Parse Indian Kanoon API document HTML into structured judgment data.

IK API returns judgments as HTML with rich annotation we exploit:
  - <h2 class="doc_title">           case title
  - <h3 class="doc_citations">       parallel citations (comma-separated)
  - <h3 class="doc_bench">           bench composition (with /search/?benchid= links)
  - <h3 class="doc_author">          author judge
  - <pre id="pre_1">                 preamble (court, appeal number, parties)
  - <p id="p_NN" data-structure=...> body paragraphs, each tagged with IK's
    own structural classification: Facts, Issue, PetArg, RespArg, Precedent,
    Section, CDiscource, Conclusion

The structural annotation is the key signal: for headnote generation we
preferentially feed Conclusion + CDiscource paragraphs to the LLM; for
"cases referred" we extract from Precedent paragraphs; etc.

All extraction is best-effort: missing fields return empty/None rather than
raising, so the pipeline doesn't break on edge-case judgments (e.g. older
ones with sparser markup).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from bs4 import BeautifulSoup, Tag


# IK's structural taxonomy. Map to canonical labels we use elsewhere.
KNOWN_STRUCTURES = {
    "Facts": "facts",
    "Issue": "issue",
    "PetArg": "petitioner_argument",
    "RespArg": "respondent_argument",
    "Precedent": "precedent",
    "Section": "section_discussion",
    "CDiscource": "court_discussion",   # IK's spelling
    "CDiscourse": "court_discussion",   # in case they fix it later
    "Conclusion": "conclusion",
    "Ratio": "ratio",
}

# Paragraph num is usually the leading "33." or "33)" of the paragraph text
PARA_NUM_RX = re.compile(r"^\s*(\d+)\s*[\.\)]")


@dataclass(frozen=True)
class Paragraph:
    id: str                 # "p_74" — IK's stable paragraph id (use for anchors)
    num: int | None         # 33 — the human-visible "33." prefix, if present
    structure: str          # canonical: "facts" / "issue" / "conclusion" / ... / "other"
    text: str               # cleaned plaintext (entities decoded, whitespace normalised)

    def anchor(self) -> str:
        """Human-readable anchor for citation in a headnote."""
        return f"Para {self.num}" if self.num else f"({self.id})"


@dataclass
class ParsedJudgment:
    tid: int
    title: str
    court: str                              # from API metadata (docsource)
    date_of_decision: str                   # ISO from API metadata
    parallel_citations: list[str] = field(default_factory=list)
    primary_citation: str = ""              # best single citation (SCC > AIR > Cri.L.J. > other)
    bench: list[str] = field(default_factory=list)        # ["T.S. Thakur", "Vikramajit Sen", ...]
    author_judge: str | None = None
    case_number: str = ""                   # "Criminal Appeal No. 2287 of 2009"
    paragraphs: list[Paragraph] = field(default_factory=list)
    statutes: list[str] = field(default_factory=list)     # normalised statute refs
    full_text: str = ""                     # all paragraphs joined (for BM25 / display)

    def paragraphs_by_structure(self, *labels: str) -> list[Paragraph]:
        """Return paragraphs whose canonical structure matches any of `labels`."""
        wanted = set(labels)
        return [p for p in self.paragraphs if p.structure in wanted]

    def conclusion_paragraphs(self) -> list[Paragraph]:
        """Paragraphs most likely to carry the ratio. Preferred for headnote ratio
        extraction. Falls back to court_discussion if no explicit conclusion."""
        conc = self.paragraphs_by_structure("conclusion", "ratio")
        return conc or self.paragraphs_by_structure("court_discussion")

    def referenced_cases_paragraphs(self) -> list[Paragraph]:
        return self.paragraphs_by_structure("precedent")


# ====================================================================== parser

def parse_judgment(doc_html: str, *, tid: int, title_hint: str = "",
                   court_hint: str = "", publishdate_hint: str = "") -> ParsedJudgment:
    """Parse IK API doc HTML. `*_hint` fields come from the API's top-level metadata
    and are used as fallbacks when the HTML lacks them.
    """
    soup = BeautifulSoup(doc_html or "", "html.parser")

    title = _text(soup.find("h2", class_="doc_title")) or title_hint
    parallel = _parse_citations_block(soup.find("h3", class_="doc_citations"))
    primary = _pick_primary_citation(parallel)
    bench = _parse_bench(soup.find("h3", class_="doc_bench"))
    author = _parse_author(soup.find("h3", class_="doc_author"))
    case_number = _extract_case_number(soup)

    paragraphs = list(_iter_paragraphs(soup))
    full_text = "\n\n".join(p.text for p in paragraphs).strip()
    statutes = extract_statutes(full_text)

    return ParsedJudgment(
        tid=tid,
        title=_normalise_title(title),
        court=court_hint or _infer_court_from_preamble(soup),
        date_of_decision=publishdate_hint,
        parallel_citations=parallel,
        primary_citation=primary,
        bench=bench,
        author_judge=author,
        case_number=case_number,
        paragraphs=paragraphs,
        statutes=statutes,
        full_text=full_text,
    )


# ----- field extractors

def _text(tag: Tag | None) -> str:
    if tag is None:
        return ""
    return re.sub(r"\s+", " ", tag.get_text(" ", strip=True))


def _normalise_title(title: str) -> str:
    """IK titles look like 'X vs Y on 1 August, 2014'. Normalise to 'X v. Y'."""
    if not title:
        return ""
    # Cut the trailing " on DD Month, YYYY" if present
    title = re.sub(r"\s+on\s+\d{1,2}\s+\w+,\s*\d{4}\s*$", "", title)
    # Standardise " vs " / " Vs " / " v/s " / " v. " → " v. "
    title = re.sub(r"\s+v(?:s\.?|/s|\.)\s+", " v. ", title, flags=re.IGNORECASE)
    return title.strip()


def _parse_citations_block(tag: Tag | None) -> list[str]:
    """Citations are comma-separated inside <h3 class='doc_citations'>."""
    if tag is None:
        return []
    raw = tag.get_text(" ", strip=True)
    # Drop leading "Equivalent citations:" label if present
    raw = re.sub(r"^\s*Equivalent\s+citations\s*:\s*", "", raw, flags=re.IGNORECASE)
    # Split on commas — citations sometimes contain commas inside parens, so
    # be defensive: split on `,` not inside parens. Simple state machine:
    out: list[str] = []
    depth = 0
    buf: list[str] = []
    for ch in raw:
        if ch == "(":
            depth += 1
            buf.append(ch)
        elif ch == ")":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == "," and depth == 0:
            s = "".join(buf).strip()
            if s:
                out.append(s)
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        out.append(tail)
    return out


# Preference order for primary citation. We prefer SCC > AIR > Cri.L.J. > INSC > other.
_PRIMARY_PRIORITY = [
    re.compile(r"\(\d{4}\)\s*\d+\s*SCC\b", re.IGNORECASE),     # (2014) 9 SCC 129
    re.compile(r"\d{4}\s*\(\d+\)\s*SCC\b", re.IGNORECASE),     # 2014 (9) SCC 129
    re.compile(r"\bAIR\s+\d{4}\s+SC\b", re.IGNORECASE),        # AIR 2014 SC 3673
    re.compile(r"\bCri\.?\s*L\.?\s*J\.?\s+\d+", re.IGNORECASE),
    re.compile(r"\d{4}\s+INSC\s+\d+", re.IGNORECASE),
]


def _pick_primary_citation(citations: list[str]) -> str:
    for pat in _PRIMARY_PRIORITY:
        for c in citations:
            if pat.search(c):
                return c
    return citations[0] if citations else ""


def _parse_bench(tag: Tag | None) -> list[str]:
    if tag is None:
        return []
    # Each judge appears as an <a> with text "<judge name>"
    links = tag.find_all("a")
    if links:
        names = [_text(a) for a in links]
        return [n for n in names if n]
    # Fallback: parse the raw text after "Bench:"
    text = tag.get_text(" ", strip=True)
    text = re.sub(r"^\s*Bench\s*:\s*", "", text, flags=re.IGNORECASE)
    return [n.strip() for n in re.split(r",|\band\b", text) if n.strip()]


def _parse_author(tag: Tag | None) -> str | None:
    if tag is None:
        return None
    link = tag.find("a")
    if link:
        return _text(link) or None
    text = tag.get_text(" ", strip=True)
    text = re.sub(r"^\s*Author\s*:\s*", "", text, flags=re.IGNORECASE)
    return text.strip() or None


_CASE_NUMBER_RX = re.compile(
    r"\b(?:CRIMINAL|CIVIL|SPECIAL\s+LEAVE)\s+(?:APPEAL|PETITION)\s+"
    r"(?:NO\.?|Nos?\.?)?\s*\d+[\d\s\-/A-Z]*\s+OF\s+\d{4}",
    re.IGNORECASE,
)


def _extract_case_number(soup: BeautifulSoup) -> str:
    pre = soup.find("pre", id="pre_1") or soup.find("pre")
    if pre is None:
        return ""
    m = _CASE_NUMBER_RX.search(pre.get_text(" ", strip=True))
    if m:
        return re.sub(r"\s+", " ", m.group(0)).strip()
    return ""


def _infer_court_from_preamble(soup: BeautifulSoup) -> str:
    pre = soup.find("pre", id="pre_1") or soup.find("pre")
    if pre is None:
        return ""
    head = pre.get_text(" ", strip=True)[:300].upper()
    if "SUPREME COURT" in head:
        return "Supreme Court of India"
    m = re.search(r"HIGH\s+COURT\s+OF\s+([A-Z\s]+)", head)
    if m:
        return f"High Court of {m.group(1).strip().title()}"
    return ""


# ----- paragraphs

def _iter_paragraphs(soup: BeautifulSoup) -> Iterable[Paragraph]:
    """Yield Paragraph objects for every <p id='p_NN'> in the doc body."""
    for p in soup.find_all("p"):
        pid = p.get("id") or ""
        if not pid.startswith("p_"):
            # Skip <p> inside the citations block etc.
            continue
        text = p.get_text(" ", strip=True)
        text = re.sub(r"\s+", " ", text).strip()
        if not text:
            continue
        structure_raw = p.get("data-structure") or ""
        structure = KNOWN_STRUCTURES.get(structure_raw, "other")
        m = PARA_NUM_RX.match(text)
        num = int(m.group(1)) if m else None
        yield Paragraph(id=pid, num=num, structure=structure, text=text)


# ----- statute extraction (two-pass: find statute names, then assign sections)
#
# The naive "S. NNN of <Act>" regex misses how judgments actually cite. Once a
# judgment defines "the Act" or "the said Act", every subsequent "Section NNN"
# refers to that statute without naming it again. The fix is a two-pass scan:
#  1. Find every statute-name mention in the text, in order.
#  2. Find every section/article reference, in order.
#  3. Attribute each section to the most recently named statute.

# (regex matching a statute name in body text, canonical form to emit)
_STATUTE_NAME_PATTERNS = [
    (r"\bNegotiable\s+Instruments\s+Act(?:,?\s*1881)?\b|\bN\.?\s*I\.?\s+Act\b",
     "Negotiable Instruments Act, 1881"),
    (r"\bIndian\s+Penal\s+Code(?:,?\s*1860)?\b|\bPenal\s+Code(?:,?\s*1860)?\b|\bI\.?\s*P\.?\s*C\.?\b",
     "Penal Code, 1860"),
    (r"\bCode\s+of\s+Criminal\s+Procedure(?:,?\s*1973)?\b|\bCr\.?\s*P\.?\s*C\.?\b",
     "Code of Criminal Procedure, 1973"),
    (r"\bBharatiya\s+Nyaya\s+Sanhita(?:,?\s*2023)?\b|\bBNS\b",
     "Bharatiya Nyaya Sanhita, 2023"),
    (r"\bBharatiya\s+Nagarik\s+Suraksha\s+Sanhita(?:,?\s*2023)?\b|\bBNSS\b",
     "Bharatiya Nagarik Suraksha Sanhita, 2023"),
    (r"\bBharatiya\s+Sakshya\s+Adhiniyam(?:,?\s*2023)?\b|\bBSA\b",
     "Bharatiya Sakshya Adhiniyam, 2023"),
    (r"\bIndian\s+Evidence\s+Act(?:,?\s*1872)?\b|\bEvidence\s+Act(?:,?\s*1872)?\b",
     "Indian Evidence Act, 1872"),
    (r"\bNarcotic\s+Drugs\s+and\s+Psychotropic\s+Substances\s+Act\b|\bNDPS(?:\s+Act)?\b",
     "Narcotic Drugs and Psychotropic Substances Act, 1985"),
    (r"\bProtection\s+of\s+Children\s+from\s+Sexual\s+Offences\s+Act\b|\bPOCSO(?:\s+Act)?\b",
     "Protection of Children from Sexual Offences Act, 2012"),
    (r"\bPrevention\s+of\s+Money\s+Laundering\s+Act\b|\bPMLA\b",
     "Prevention of Money Laundering Act, 2002"),
    (r"\bUnlawful\s+Activities\s*\(Prevention\)\s+Act\b|\bUAPA\b",
     "Unlawful Activities (Prevention) Act, 1967"),
    (r"\bConstitution\s+of\s+India\b",
     "Constitution of India"),
]

# Compiled once
_STATUTE_NAME_RX = [(re.compile(pat, re.IGNORECASE), canon)
                    for pat, canon in _STATUTE_NAME_PATTERNS]
_SECTION_REF_RX = re.compile(
    r"\b(?:S\.|Sec\.?|Section)\s+(\d+[A-Z]?(?:\([^\)]+\))*(?:\s+to\s+\d+[A-Z]?)?)",
    re.IGNORECASE,
)
_ARTICLE_REF_RX = re.compile(
    r"\bArt(?:icle)?\.?\s+(\d+[A-Z]?(?:\([^\)]+\))?)\b",
    re.IGNORECASE,
)


def extract_statutes(text: str, top_k: int = 20) -> list[str]:
    """Two-pass statute extraction.

    Pass 1: collect every statute-name mention with its position.
    Pass 2: collect every section/article reference with its position.
    Merge, sort by position, and attribute each section to the most recent
    statute name seen. Articles always go to Constitution of India.
    """
    if not text:
        return []

    events: list[tuple[int, str, str]] = []  # (position, kind, value)
    for rx, canon in _STATUTE_NAME_RX:
        for m in rx.finditer(text):
            events.append((m.start(), "statute", canon))
    for m in _SECTION_REF_RX.finditer(text):
        events.append((m.start(), "section", m.group(1).strip()))
    for m in _ARTICLE_REF_RX.finditer(text):
        events.append((m.start(), "article", m.group(1).strip()))

    events.sort(key=lambda t: t[0])

    out: list[str] = []
    seen: set[str] = set()
    current_statute: str | None = None
    for _pos, kind, value in events:
        if kind == "statute":
            current_statute = value
            # Also emit the bare statute name once, so it's discoverable even
            # if the doc never cites a section of it. Useful for retrieval.
            if value not in seen:
                seen.add(value)
                out.append(value)
        elif kind == "article":
            entry = f"Constitution of India, Art. {value}"
            if entry not in seen:
                seen.add(entry)
                out.append(entry)
        elif kind == "section" and current_statute:
            entry = f"{current_statute}, S. {value}"
            if entry not in seen:
                seen.add(entry)
                out.append(entry)
        if len(out) >= top_k:
            break
    return out
