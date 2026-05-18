"""
Multi-facet keyword prefilter — the v2 scorer.

Replaces the old single-score keyword overlap with a four-facet model:

  (A) Section / statute overlap — strongest signal. If the lawyer mentions
      S. 138 NI Act, a case construing S. 138 is gold.
  (B) Doctrine overlap — terms like "quashing", "anticipatory bail",
      "circumstantial evidence", "consent", "age proximity" — the
      vocabulary that distinguishes one matter from another.
  (C) Outcome match — if the lawyer is seeking acquittal, weight cases
      that produced acquittals.
  (D) Content-token TF overlap — residual fallback, capped so frequent
      terms don't dominate.

Each case is scored on each facet independently. The total is the sum.
The per-facet breakdown is attached to the returned case dict as
`_prefilter_debug` for tuning + cost-dashboard reporting. Strip these
fields before sending to the LLM (see `_strip_debug_fields` below).

Used to pre-filter the corpus down to top_k cases (default 20) before
the LLM sees them. Cuts cache-write cost and gives the LLM a curated
shortlist to discriminate from.
"""

from __future__ import annotations

import re
from collections import Counter

from headnote.retrieval.fact_extractor import (
    extract_facts as _extract_universal_facts,
    score_overlap as _score_universal_facts,
)

# ----------------------------------------------------------------- vocabularies

# Section / statute regex. Catches "S. 138", "Section 376", "Article 21",
# and statute shorthand (IPC, CrPC, NI Act, POCSO, NDPS, PMLA, etc.).
SECTION_PATTERN = re.compile(
    r"\b(?:S\.?|Section)\s*(\d+[A-Z]?(?:\([\d\w]+\))?)\b|"
    r"\b(IPC|CrPC|NI\s*Act|NDPS|POCSO|BNS|BNSS|BSA|Evidence\s*Act|PMLA|"
    r"PC\s*Act|UAPA|MV\s*Act|Companies\s*Act|TADA|MCOCA|Atrocities\s*Act)"
    r"\s*[,\-]?\s*S?\.?\s*(\d+[A-Z]?)?\b",
    re.IGNORECASE,
)

# Doctrine vocabulary — terms that distinguish one legal question from another.
# Add to this list as your senior advocate identifies missing facets.
DOCTRINE_TERMS = {
    "quashing", "quash", "quashed", "discharge", "discharged",
    "framing of charge", "framing", "charge",
    "anticipatory bail", "regular bail", "default bail", "transit bail",
    "bail granted", "bail denied", "bail refused",
    "acquittal", "acquitted", "conviction", "convicted",
    "sentence", "sentencing", "remission", "parole", "set aside",
    "circumstantial evidence", "last seen", "alibi", "motive",
    "extra-judicial confession", "extrajudicial confession",
    "recovery", "panchnama", "test identification parade", "tip",
    "dying declaration", "delay in fir", "magistrate", "remand",
    "police custody", "judicial custody",
    "mens rea", "actus reus", "common intention", "common object",
    "consent", "consensual", "age proximity", "majority", "minor",
    "false case", "false implication", "matrimonial dispute",
    "settlement", "compromise", "compounding", "compoundable",
    "hostile witness", "child witness", "interested witness",
    "cheating", "forgery", "criminal breach of trust",
    "dishonour", "cheque", "territorial jurisdiction",
    "trial in absentia", "non-compoundable",
}

# Outcome vocabulary — the disposition the lawyer is seeking. If a case's
# text contains the outcome term, it gets the outcome bonus.
OUTCOME_TERMS = {
    "acquittal": "acquittal",
    "acquitted": "acquittal",
    "discharge": "discharge",
    "discharged": "discharge",
    "conviction": "conviction",
    "convicted": "conviction",
    "quash": "quashing",
    "quashing": "quashing",
    "quashed": "quashing",
    "bail granted": "bail",
    "bail denied": "bail",
    "anticipatory bail": "bail",
    "set aside": "set_aside",
    "remand": "remand",
}

# Generic procedural / connective vocabulary that matches too many docs to
# be useful for discrimination. These ARE NOT bad words — they're just
# uninformative. Strip them from the content-token overlap to avoid noise.
GENERIC_NOISE = {
    "the", "a", "an", "and", "or", "but", "for", "of", "to", "in",
    "on", "at", "by", "with", "from", "as", "is", "are", "was", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "this", "that", "these", "those", "what", "which", "who", "whether",
    "case", "cases", "matter", "matters", "court", "courts", "judgment",
    "judgments", "judge", "judges", "accused", "complainant", "victim",
    "person", "party", "parties",
    "year", "years", "month", "months", "day", "days", "age", "old",
    "male", "female", "boy", "girl", "man", "woman",
    "client", "lawyer", "advocate", "junior", "senior",
    "fir", "filed", "registered", "booked", "lodged", "stated",
    "alleged", "alleging", "claimed", "claims", "needed", "wants",
    "want", "looking", "find", "say", "says", "his", "her", "their",
}


# ----------------------------------------------------------------- helpers

def _extract_sections(text: str) -> set[str]:
    """Pull section / statute references from free text.
    Returns a canonical-form set: {'POCSO-4', 'IPC-376', 'SECTION-138'} etc."""
    sections = set()
    for m in SECTION_PATTERN.finditer(text or ""):
        groups = [g for g in m.groups() if g]
        if groups:
            sections.add("-".join(g.upper() for g in groups))
    return sections


def _extract_doctrines(text: str) -> set[str]:
    """Doctrine terms (multi-word allowed) that appear in the text."""
    if not text:
        return set()
    tl = text.lower()
    return {d for d in DOCTRINE_TERMS if d in tl}


def _extract_outcome(text: str) -> str | None:
    """The disposition term the lawyer is seeking (if any)."""
    if not text:
        return None
    tl = text.lower()
    for term, outcome in OUTCOME_TERMS.items():
        if term in tl:
            return outcome
    return None


def _content_tokens(text: str) -> list[str]:
    """Tokenise for general overlap, dropping generic procedural noise."""
    raw = re.findall(r"[a-zA-Z]+", (text or "").lower())
    return [t for t in raw if t not in GENERIC_NOISE and len(t) > 2]


def _case_text_blob(case: dict) -> str:
    """Flatten a curated corpus case into one searchable string."""
    parts = [
        case.get("title", ""),
        case.get("citation", ""),
        " ".join(case.get("topics", [])),
        " ".join(case.get("statutes", [])),
        case.get("ratio", ""),
        case.get("facts", ""),
        case.get("holding", ""),
        " ".join(case.get("issues", []) or []),
        " ".join(case.get("key_paras", []) or []) if isinstance(case.get("key_paras"), list) else str(case.get("key_paras") or ""),
        " ".join(case.get("bns_mapping", []) or []) if isinstance(case.get("bns_mapping"), list) else str(case.get("bns_mapping") or ""),
        case.get("subsequent_treatment", ""),
    ]
    return " ".join(p for p in parts if p)


# Module-level cache of fact_extractor output per curated case. The 42
# curated cases never change at runtime, so extracting facts once on first
# touch and reusing them saves ~40ms per query (42 cases * ~1ms each).
# Keyed by case id; falls back to the dict's `id` field, then to id(case).
_CASE_FACTS_CACHE: dict[str, dict] = {}


def _case_facts(case: dict) -> dict:
    """Return universal facts for a curated case, lazily extracted + cached.

    The cache is keyed on the case's stable `id` field (e.g. 'DASH-2014-SC').
    If a case lacks an id, we fall back to the Python id() — that's fine for
    in-process correctness; we just lose cross-call caching.
    """
    case_id = case.get("id") or f"_noid_{id(case)}"
    cached = _CASE_FACTS_CACHE.get(case_id)
    if cached is not None:
        return cached
    facts = _extract_universal_facts(_case_text_blob(case))
    _CASE_FACTS_CACHE[case_id] = facts
    return facts


def prime_case_facts_cache(corpus: list[dict]) -> None:
    """Pre-extract facts for every case in the corpus.

    Cheap (~40-50ms for 42 cases on a cold cache) but skipping the first-
    query latency spike is worth a tiny boot cost. Safe to call multiple
    times — cache is idempotent.
    """
    for case in corpus or []:
        _case_facts(case)


# ----------------------------------------------------------------- scoring

def _score_facets(case: dict, situation: str) -> tuple[float, dict]:
    """Multi-facet score with explainable breakdown.

    Two scorer layers:

      (1) Legacy facets — section / doctrine / outcome / tokens. These
          are computed over plaintext via the keyword.py vocabularies and
          have been tuned against the curated corpus over many iterations.
          We keep them for stability + tokens-as-tiebreaker.

      (2) Universal fact scoring — calls fact_extractor.score_overlap.
          Adds dimensions the legacy facets don't have: stage (bail vs
          trial vs quash), victim-is-minor, accused role, special category
          (woman/juvenile/sick/pregnant), numerics (cheque amt, drug qty,
          FIR delay, custody days), weapon.

    Both layers are summed. The legacy facets max ~9.5; the universal
    layer maxes ~15+. So the universal layer is the dominant signal where
    it fires, while legacy facets provide a stable floor for queries the
    universal extractor doesn't parse (e.g. very loose natural-language
    queries with no statute / stage hints).
    """
    case_text = _case_text_blob(case).lower()
    case_sections = _extract_sections(case_text)
    case_doctrines = _extract_doctrines(case_text)

    q_sections = _extract_sections(situation)
    q_doctrines = _extract_doctrines(situation)
    q_outcome = _extract_outcome(situation)
    q_tokens = _content_tokens(situation)
    case_tokens_count = Counter(_content_tokens(case_text))

    # FACET A — section overlap (heaviest weight)
    section_score = 0.0
    if q_sections:
        overlap = q_sections & case_sections
        section_score = 5.0 * len(overlap) / max(len(q_sections), 1)

    # FACET B — doctrine overlap
    doctrine_score = 0.0
    if q_doctrines:
        overlap = q_doctrines & case_doctrines
        doctrine_score = 3.0 * len(overlap) / max(len(q_doctrines), 1)

    # FACET C — outcome match (binary bonus)
    outcome_score = 0.0
    if q_outcome and q_outcome in case_text:
        outcome_score = 1.5

    # FACET D — content TF overlap (log-capped)
    token_score = 0.0
    seen = set()
    for tok in q_tokens:
        if tok in seen:
            continue
        seen.add(tok)
        c = case_tokens_count.get(tok, 0)
        if c > 0:
            token_score += min(c, 3) * 0.3

    # FACET E — universal fact scoring (the new dimensions)
    # Cached extraction of case facts; fresh extraction of query facts.
    case_facts = _case_facts(case)
    q_facts = _extract_universal_facts(situation) if situation else {}
    universal_score, universal_breakdown = (0.0, {})
    if q_facts and case_facts:
        universal_score, universal_breakdown = _score_universal_facts(q_facts, case_facts)

    total = (
        section_score + doctrine_score + outcome_score + token_score
        + universal_score
    )

    return total, {
        "section": round(section_score, 2),
        "doctrine": round(doctrine_score, 2),
        "outcome": round(outcome_score, 2),
        "tokens": round(token_score, 2),
        "universal": round(universal_score, 2),
        "universal_breakdown": universal_breakdown,
        "matched_sections": sorted(q_sections & case_sections),
        "matched_doctrines": sorted(q_doctrines & case_doctrines),
        "query_facts": q_facts,
    }


# Public API — preserves the signatures the rest of the code uses.

def score_case(case: dict, query: str) -> float:
    """Score a single case against a query. Returns a single float for
    backward compatibility with retrieval.py's hybrid pipeline."""
    if not query or not query.strip() or not case:
        return 0.0
    total, _ = _score_facets(case, query)
    return total


def prefilter_cases(corpus: list[dict], situation: str, top_k: int = 20) -> list[dict]:
    """Multi-facet prefilter. Returns top_k cases scored across all four
    facets, each annotated with `_prefilter_score` + `_prefilter_debug`
    fields. Strip the debug fields via `_strip_debug_fields()` before
    serialising the cases to the LLM prompt — they're for tuning only.

    Falls back to corpus[:top_k] if the query is empty or no case scores > 0.
    """
    if not situation or not situation.strip() or not corpus:
        return corpus[:top_k]

    scored = []
    for case in corpus:
        total, debug = _score_facets(case, situation)
        scored.append((total, debug, case))

    scored.sort(key=lambda x: -x[0])

    if scored[0][0] == 0:
        # No keyword/statute/doctrine hit at all — fall back so the LLM
        # at least sees something rather than an empty corpus.
        return corpus[:top_k]

    out = []
    for total, debug, case in scored[:top_k]:
        if total <= 0:
            continue
        case_copy = {
            **case,
            "_prefilter_score": round(total, 2),
            "_prefilter_debug": debug,
        }
        out.append(case_copy)
    return out or corpus[:top_k]


def strip_debug_fields(cases: list[dict]) -> list[dict]:
    """Strip the `_prefilter_*` diagnostic fields before sending cases to
    the LLM. The debug fields exist for tuning + cost-dashboard reporting,
    not for the model to read."""
    return [
        {k: v for k, v in c.items() if not k.startswith("_prefilter_")}
        for c in cases
    ]
