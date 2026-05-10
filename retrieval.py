"""
Lightweight in-process keyword retrieval over the case corpus.

Used to pre-filter the full corpus down to the top-K most relevant cases for
a user query, BEFORE sending to the LLM. Cuts cache-write cost ~60% on 42
cases and is the architecture we need anyway as the corpus grows past Opus's
200k context window.

Score = weighted sum of:
  - Statute keyword matches (highest weight — "S. 138 NI Act" is a strong signal)
  - Topic-tag overlap
  - Title token overlap
  - Generic prose token overlap

No external deps. ~50ms for 1,000 cases on a modern CPU.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Any

# tokens with low signal; ignore in scoring
STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "of",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "i", "you", "he", "she", "it",
    "we", "they", "what", "which", "who", "whom", "whose", "whether", "case",
    "court", "judgment", "section", "act", "law", "legal", "client", "his",
    "her", "their", "my", "your", "our", "me", "him", "us", "them",
    "do", "does", "did", "have", "has", "had", "can", "could", "should",
    "would", "may", "might", "must", "will", "shall", "not", "no", "yes",
    "any", "some", "all", "every", "each", "very", "just",
}

# Statute / section regex — matches "S. 138", "Ss. 137, 178", "S. 3(1)(r)"
SECTION_RX = re.compile(r"\bSs?\.\s*\d+[\d\w\(\)\.\-]*", re.IGNORECASE)

# Famous-statute shorthand
STATUTE_RX = re.compile(
    r"\b(BNS|BNSS|BSA|IPC|CrPC|PMLA|UAPA|NDPS|POCSO|FIR|NI\s+Act|"
    r"Negotiable\s+Instruments|Penal\s+Code|Evidence\s+Act|Atrocities\s+Act|"
    r"Money\s+Laundering|Narcotic\s+Drugs|Unlawful\s+Activities)\b",
    re.IGNORECASE,
)


def _tokenize(text: str) -> list[str]:
    return [
        w.lower()
        for w in re.findall(r"[A-Za-z]+", text or "")
        if len(w) > 2 and w.lower() not in STOPWORDS
    ]


def _extract_section_refs(text: str) -> set[str]:
    """Normalise section refs to a canonical form for comparison."""
    out = set()
    for m in SECTION_RX.findall(text or ""):
        # collapse whitespace, lowercase
        out.add(re.sub(r"\s+", "", m).lower())
    return out


def _extract_statute_refs(text: str) -> set[str]:
    out = set()
    for m in STATUTE_RX.findall(text or ""):
        out.add(re.sub(r"\s+", " ", m).lower().strip())
    return out


def _case_haystack(case: dict) -> str:
    """Concatenate the searchable fields of a case into one string."""
    parts = [
        case.get("title", ""),
        " ".join(case.get("statutes", [])),
        " ".join(case.get("topics", [])),
        case.get("facts", ""),
        case.get("holding", ""),
        " ".join(case.get("issues", [])),
    ]
    return " ".join(parts)


def score_case(case: dict, query: str) -> float:
    """Return a relevance score (higher = better) for this case against query."""
    if not query:
        return 0.0

    q_tokens = Counter(_tokenize(query))
    q_sections = _extract_section_refs(query)
    q_statutes = _extract_statute_refs(query)

    haystack = _case_haystack(case)
    h_tokens = Counter(_tokenize(haystack))
    h_sections = _extract_section_refs(haystack)
    h_statutes = _extract_statute_refs(haystack)

    score = 0.0

    # 1. Section refs (very high weight — exact section match is a strong signal)
    section_overlap = q_sections & h_sections
    score += 8.0 * len(section_overlap)

    # 2. Statute names (high weight)
    statute_overlap = q_statutes & h_statutes
    score += 4.0 * len(statute_overlap)

    # 3. Topic-tag overlap (boost: topics are curated keywords)
    q_topic_tokens = set(_tokenize(query))
    case_topics_text = " ".join(case.get("topics", []))
    h_topic_tokens = set(_tokenize(case_topics_text))
    topic_overlap = q_topic_tokens & h_topic_tokens
    score += 2.0 * len(topic_overlap)

    # 4. Title token overlap (medium)
    h_title_tokens = set(_tokenize(case.get("title", "")))
    title_overlap = q_topic_tokens & h_title_tokens
    score += 1.5 * len(title_overlap)

    # 5. Body token overlap (lowest weight — generic prose)
    common = q_tokens & h_tokens
    body_score = sum(min(q_tokens[w], h_tokens[w]) for w in common)
    score += 0.3 * body_score

    return score


def prefilter_cases(corpus: list[dict], query: str, top_k: int = 12) -> list[dict]:
    """Return top_k most relevant cases for the query.

    If query is empty or no case scores > 0, falls back to first top_k cases
    so the system always has something to work with.
    """
    if not query.strip() or not corpus:
        return corpus[:top_k]

    scored = [(score_case(c, query), i, c) for i, c in enumerate(corpus)]
    scored.sort(key=lambda t: (-t[0], t[1]))  # high score first; stable on ties

    # If best score is 0, no keyword/statute hit — return first top_k as fallback
    if scored[0][0] == 0:
        return corpus[:top_k]

    return [c for (s, _, c) in scored[:top_k] if s > 0] or corpus[:top_k]
