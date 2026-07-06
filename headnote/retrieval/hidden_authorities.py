"""
Hidden Authorities ranker — the moat differentiator.

Most legal-AI tools surface the famous cases lawyers already know: Arnesh
Kumar, Lalita Kumari, Satender Antil. Lawyers told us they want the
non-obvious authority — the case cited 6 times that directly fits their
fact pattern, not the case cited 3000 times that's tangential.

This module re-ranks the top-30 candidates from cheap retrieval (curated +
semantic + IK search) using six signals, with mode-specific weights:

  • fact_pattern_match  Sonnet judges how well the candidate's facts map
                         to the user's described scenario. Most expensive
                         signal; computed only for top-30 to cap cost.
  • semantic_similarity Cosine between query embedding and candidate
                         headnote/summary embedding (free; computed via
                         the local fastembed index).
  • citation_count      Built-in IK signal (numcitedby). For HIDDEN mode,
                         this becomes a *penalty*: famous = less hidden.
  • jurisdiction_match  Same court > same level > other > irrelevant.
  • recency_score       Newer is better, capped at 5 years.
  • good_law_score      1.0 default; 0.3 if distinguished; 0.0 if overruled.
                         (treatment data not always available for IK cases —
                         defaults to 1.0 when unknown.)

Final mode formulas (see _score_*).
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal, Optional

from headnote.llm import route_call


Mode = Literal["hidden", "famous", "mixed"]


# ----------------------------------------------------------------- shapes

@dataclass(frozen=True)
class Candidate:
    """One case under consideration. Built from existing retrieval outputs
    (curated dict OR ik CaseSummary)."""
    case_id: str
    title: str
    court: str
    year: int                       # 0 if unknown
    citation: str
    numcitedby: int                 # IK's built-in citation weight
    semantic_similarity: float      # 0.0-1.0; 0.0 if not computed
    summary: str                    # short summary for Sonnet's fact-match call
    subsequent_treatment: str = ""  # free-text; parsed for "overruled"/"distinguished"
    source: str = "ik"              # "curated" | "ik" | "ik-semantic"


@dataclass
class ScoredCandidate:
    candidate: Candidate
    fact_pattern_match: float
    semantic_similarity: float
    citation_count: int
    jurisdiction_match: float
    recency_score: float
    good_law_score: float
    fame_penalty: float             # only meaningful in hidden mode
    fame_boost: float               # only meaningful in famous mode
    final_score: float
    explanation: dict[str, float]   # per-signal breakdown for UI transparency


# ----------------------------------------------------------------- scoring helpers

# How many of the top semantic candidates do we send to Sonnet for fact-pattern
# matching. Caps cost: 30 × ~1K input × Sonnet pricing ≈ ₹4-5 per query.
DEFAULT_RERANK_TOP_K = 30

# How many cases we return to the caller / show the lawyer.
DEFAULT_RESULT_TOP_K = 5


def _years_old(year: int, now: Optional[datetime] = None) -> float:
    if year <= 0:
        return 99.0
    now = now or datetime.now(timezone.utc)
    return max(0.0, now.year - year)


def _recency_score(year: int, cap_years: int = 5) -> float:
    """1.0 for very recent; declines linearly; flatlines at cap (older than
    `cap_years` all get the same minimum score)."""
    age = _years_old(year)
    if age <= 0:
        return 1.0
    if age >= cap_years:
        return 0.2
    return 1.0 - 0.8 * (age / cap_years)


def _jurisdiction_match(candidate_court: str, query_jurisdiction: Optional[str]) -> float:
    """Simple heuristic.

      1.0  Same High Court as query, OR Supreme Court (always relevant)
      0.5  Different HC
      0.2  District court / tribunal
    """
    c = (candidate_court or "").lower()
    if "supreme court" in c:
        return 1.0
    if query_jurisdiction and query_jurisdiction.lower() in c:
        return 1.0
    if "high court" in c:
        return 0.5
    return 0.2


_OVERRULED_RX = re.compile(r"\boverruled\b", re.IGNORECASE)
_DISTINGUISHED_RX = re.compile(r"\bdistinguished\b", re.IGNORECASE)


def _good_law_score(subsequent_treatment: str) -> float:
    """Default 1.0 (assumed good law). If subsequent_treatment text says the
    case was overruled, drop to 0.0; if distinguished, drop to 0.3."""
    if not subsequent_treatment:
        return 1.0
    if _OVERRULED_RX.search(subsequent_treatment):
        return 0.0
    if _DISTINGUISHED_RX.search(subsequent_treatment):
        return 0.3
    return 1.0


def _fame_factor(numcitedby: int, scale: int = 100) -> float:
    """0.0 at 0 citations, 1.0 at scale (default 100) citations, capped at 1.0."""
    if numcitedby <= 0:
        return 0.0
    return min(1.0, numcitedby / scale)


# Exactness damper: the Sonnet fact-match rubric scores 0.1-0.3 for
# "tangentially related — touches the topic but different fact pattern".
# A famous-tangential case still racks up semantic similarity (shared topic
# keywords) + fame + jurisdiction and used to outrank the obscure case with
# the lawyer's exact facts. Below this threshold the composite is damped so
# tangential cases can only win when nothing better exists.
_TANGENTIAL_FACT_THRESHOLD = 0.35
_TANGENTIAL_DAMPER = 0.6


def _damp_tangential(score: float, s: ScoredCandidate) -> float:
    if s.fact_pattern_match <= _TANGENTIAL_FACT_THRESHOLD:
        return score * _TANGENTIAL_DAMPER
    return score


def _score_hidden(s: ScoredCandidate) -> float:
    return _damp_tangential(
        0.50 * s.fact_pattern_match
        + 0.22 * s.semantic_similarity
        + 0.13 * s.jurisdiction_match
        + 0.10 * s.recency_score
        + 0.05 * s.good_law_score
        - 0.20 * s.fame_penalty,
        s,
    )


def _score_famous(s: ScoredCandidate) -> float:
    # famous mode is explicitly landmark-seeking — no damper, weights unchanged
    return (
        0.30 * s.fact_pattern_match
        + 0.20 * s.semantic_similarity
        + 0.20 * s.fame_boost
        + 0.15 * s.jurisdiction_match
        + 0.10 * s.recency_score
        + 0.05 * s.good_law_score
    )


def _score_mixed(s: ScoredCandidate) -> float:
    """No fame adjustment in either direction — exactness-first neutral ranking.
    fact_pattern_match is the dominant signal (0.50): the case whose facts
    mirror the lawyer's matter must beat the famous case on the same topic."""
    return _damp_tangential(
        0.50 * s.fact_pattern_match
        + 0.25 * s.semantic_similarity
        + 0.12 * s.jurisdiction_match
        + 0.08 * s.recency_score
        + 0.05 * s.good_law_score,
        s,
    )


# ----------------------------------------------------------------- Sonnet rerank

_FACT_MATCH_SYSTEM = """You judge how well a candidate case's facts match a lawyer's described situation.

For each candidate you receive, output a single float in [0.0, 1.0]:
  1.0  Facts essentially identical to the lawyer's situation
  0.7-0.9  Substantially similar — same legal issue, similar facts
  0.4-0.6  Same legal issue, materially different facts
  0.1-0.3  Tangentially related (touches the topic but different fact pattern)
  0.0  Not actually about the same issue at all

Output STRICT JSON only:
{
  "matches": [
    {"case_id": "<id>", "score": 0.85, "reasoning": "one short sentence"},
    ...
  ]
}

One entry per candidate, in the order received. No prose outside JSON."""


def _build_fact_match_user_prompt(query_facts: str, candidates: list[Candidate]) -> str:
    candidates_block = "\n\n".join(
        f"CANDIDATE {i + 1}\n"
        f"case_id: {c.case_id}\n"
        f"title:   {c.title}\n"
        f"court:   {c.court} · {c.year or 'unknown year'}\n"
        f"summary: {c.summary[:600]}"
        for i, c in enumerate(candidates)
    )
    return (
        f"LAWYER'S SITUATION:\n{query_facts.strip()}\n\n"
        f"---\n\n"
        f"CANDIDATES TO RATE ({len(candidates)} total):\n\n"
        f"{candidates_block}\n\n"
        f"Output the JSON now."
    )


def _score_fact_patterns_via_sonnet(
    query_facts: str,
    candidates: list[Candidate],
) -> dict[str, float]:
    """Returns dict mapping case_id -> fact_pattern_match in [0,1].

    Single Sonnet call for the whole batch (cheaper than per-candidate).
    Falls back to 0.5 on parse failure so the ranker doesn't crash if
    Sonnet returns a degenerate response.
    """
    if not candidates:
        return {}
    user_prompt = _build_fact_match_user_prompt(query_facts, candidates)
    try:
        result = route_call(
            "rerank",
            {"system_prompt": _FACT_MATCH_SYSTEM, "user_prompt": user_prompt},
        )
    except Exception as e:
        print(f"[hidden_authorities] Sonnet rerank failed ({e}); defaulting all to 0.5")
        return {c.case_id: 0.5 for c in candidates}

    import json
    try:
        text = result.response.strip()
        if text.startswith("```"):
            text = "\n".join(text.split("\n")[1:])
            if text.endswith("```"):
                text = text[:-3]
        parsed = json.loads(text.strip())
        matches = parsed.get("matches") or []
    except Exception as e:
        print(f"[hidden_authorities] Sonnet returned non-JSON ({e}); defaulting to 0.5")
        return {c.case_id: 0.5 for c in candidates}

    scores: dict[str, float] = {c.case_id: 0.5 for c in candidates}
    for m in matches:
        cid = m.get("case_id")
        try:
            score = float(m.get("score", 0.5))
        except (TypeError, ValueError):
            score = 0.5
        if cid in scores:
            scores[cid] = max(0.0, min(1.0, score))
    return scores


# ----------------------------------------------------------------- main entry

def rank_candidates(
    query_facts: str,
    candidate_cases: Iterable[Candidate],
    mode: Mode = "hidden",
    *,
    query_jurisdiction: Optional[str] = None,
    rerank_top_k: int = DEFAULT_RERANK_TOP_K,
    result_top_k: int = DEFAULT_RESULT_TOP_K,
    skip_sonnet_rerank: bool = False,
) -> list[ScoredCandidate]:
    """Rank candidates by the mode-specific scoring formula.

    Cheap signals (semantic similarity, citation count, jurisdiction, recency)
    are computed for every candidate. The Sonnet fact-pattern call runs only
    on the top-`rerank_top_k` by semantic similarity (default 30) so the cost
    stays bounded at ~₹4-5 per query.

    `skip_sonnet_rerank=True` short-circuits the Sonnet call entirely (used
    in tests where we want deterministic ranking).

    Returns up to `result_top_k` scored candidates, highest score first.
    """
    candidates = list(candidate_cases)
    if not candidates:
        return []

    # Pre-sort by semantic similarity to pick the top-K for Sonnet rerank.
    by_semantic = sorted(candidates, key=lambda c: c.semantic_similarity, reverse=True)
    top_for_rerank = by_semantic[:rerank_top_k]

    if skip_sonnet_rerank:
        fact_scores = {c.case_id: c.semantic_similarity for c in top_for_rerank}
    else:
        fact_scores = _score_fact_patterns_via_sonnet(query_facts, top_for_rerank)

    scored: list[ScoredCandidate] = []
    for c in candidates:
        fpm = fact_scores.get(c.case_id, 0.0)
        sim = c.semantic_similarity
        cit = c.numcitedby
        jm = _jurisdiction_match(c.court, query_jurisdiction)
        rs = _recency_score(c.year)
        gls = _good_law_score(c.subsequent_treatment)
        fp = _fame_factor(cit)

        sc = ScoredCandidate(
            candidate=c,
            fact_pattern_match=fpm,
            semantic_similarity=sim,
            citation_count=cit,
            jurisdiction_match=jm,
            recency_score=rs,
            good_law_score=gls,
            fame_penalty=fp,
            fame_boost=fp,
            final_score=0.0,
            explanation={},
        )

        if mode == "hidden":
            final = _score_hidden(sc)
        elif mode == "famous":
            final = _score_famous(sc)
        else:
            final = _score_mixed(sc)
        sc.final_score = final
        sc.explanation = {
            "fact_pattern_match": round(fpm, 3),
            "semantic_similarity": round(sim, 3),
            "citation_count": cit,
            "jurisdiction_match": round(jm, 3),
            "recency_score": round(rs, 3),
            "good_law_score": round(gls, 3),
            "fame_signal": round(fp, 3),
        }
        scored.append(sc)

    scored.sort(key=lambda s: s.final_score, reverse=True)
    return scored[:result_top_k]


def explain_score(scored: ScoredCandidate, mode: Mode) -> str:
    """Produce a human-readable explanation for the UI.

    Example: "Cited 6 times — likely a hidden authority. Fact-pattern match
    0.91, jurisdiction match 1.0."
    """
    parts = []
    if mode == "hidden" and scored.candidate.numcitedby < 50:
        parts.append(f"Cited only {scored.candidate.numcitedby} times — likely a hidden authority.")
    elif mode == "famous" and scored.candidate.numcitedby >= 500:
        parts.append(f"Cited {scored.candidate.numcitedby} times — leading authority.")
    parts.append(f"Fact-pattern match {scored.fact_pattern_match:.2f}.")
    parts.append(f"Jurisdiction match {scored.jurisdiction_match:.1f}.")
    if scored.good_law_score < 1.0:
        parts.append("Subsequent treatment indicates not-fully-good-law — verify.")
    return " ".join(parts)
