"""Pre-ranking: Haiku scores 20-30 candidates on the 5-dimension rubric
BEFORE the expensive Sonnet call sees them.

Why this stage exists
=====================
Retrieval (Stage 2) returns 20-30 candidates with reasonable recall but
mediocre precision — BM25 and embedding similarity get confused by famous
cases that share keywords but don't share doctrine or facts.

Sending 30 candidates straight to Sonnet costs ₹10-15 per query and gives
the model too much noise to discriminate well.

This Stage 3 pre-rank is the cheap discriminator: Haiku reads each
candidate's title + ratio + facets, scores it on 5 dimensions (statute /
stage / doctrinal / facts / authority), drops anything < 4.5 weighted, and
hands Sonnet the top 8-10 cleanly.

Net effect:
  - Sonnet sees a smaller, higher-quality pool → better precision@3
  - Total cost actually drops (Haiku × 30 < Sonnet × 30)
  - Latency drops too (Haiku is ~3× faster per token)

Cost: ~₹2 per query (one Haiku call seeing all candidates).
Latency: ~1.2s.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from headnote.llm import route_call
from headnote.refine.canonicalize import RefinedQuery


log = logging.getLogger(__name__)


# Weighted dimensions — keep in lockstep with the Stage 4 system prompt.
DIMENSION_WEIGHTS = {
    "statute":   0.30,
    "stage":     0.20,
    "doctrinal": 0.25,
    "facts":     0.15,
    "authority": 0.10,
}

PRERANK_MIN_SCORE = 4.5     # weighted total below this → drop the case
PRERANK_TOP_N      = 10     # how many to hand to Sonnet after pruning


PRERANK_SYSTEM = """You are a fast pre-ranker for Indian case-law retrieval — criminal AND civil. Your job: score every candidate case in the input pool on five dimensions and return JSON.

The query envelope carries a `domain` (criminal / civil / mixed). Score candidates
against THAT domain: for a civil query (property, contract, specific performance,
tenancy, succession, family), a civil case on the same Act/doctrine is a strong
match and a criminal case is usually a weak one — and vice versa. For a mixed
matter (e.g. double sale of land raising both title and IPC 420/BNS 318 cheating),
cases on EITHER face can score high on their own merits.

YOU ARE NOT THE FINAL REASONER. You do quick discrimination on a wide pool.
Sonnet will do the deep relevance work later on the top N you return.

INPUT FORMAT
============
- A structured query envelope (canonical question, statutes, stage, doctrines).
- A candidate pool — each candidate has: id, title, citation, court, year,
  ratio_or_holding, and pre-extracted facets where available.

SCORING RUBRIC (apply to EVERY candidate)
=========================================

For each candidate, score on these five dimensions, integer 1–10:

  1. STATUTE MATCH
     10 = exact section + Act match (e.g., both invoke Section 372 CrPC proviso;
          both invoke Section 54 Transfer of Property Act)
      7 = same Act, different section
      4 = related Act in same domain
      1 = unrelated statute
     [Old↔new code equivalents count as the SAME section: IPC 420 ≡ BNS 318 etc.]

  2. STAGE MATCH
     10 = same procedural stage (both are bail / both are appeal / both are
          suits for specific performance / both are Order XXXIX injunctions)
      7 = adjacent stage (ABA → regular bail; suit → first appeal)
      4 = different stage but same broad phase (trial → appeal)
      1 = unrelated stage

  3. DOCTRINAL MATCH
     10 = case's ratio decides the EXACT question the lawyer is asking
      7 = case addresses an adjacent doctrine the lawyer needs
      4 = related principle but a tangent
      1 = different doctrine entirely

  4. FACT ARCHETYPE
     10 = mirror fact pattern
      7 = overlapping fact pattern
      4 = same broad domain, different facts
      1 = different domain
      [Note: for PROCEDURAL questions (limitation, jurisdiction, bail conditions),
       facts are irrelevant — score 5 (neutral) for every candidate.]

  5. AUTHORITY WEIGHT
     10 = Supreme Court ratio binding on the question
      7 = jurisdictional High Court ratio
      4 = other High Court / persuasive
      1 = trial court / obiter / superseded

COMPUTE the weighted total:
   total = 0.30*statute + 0.20*stage + 0.25*doctrinal + 0.15*facts + 0.10*authority

KEEP candidates with total >= 4.5. DROP the rest.
Sort remaining by total descending. Return the top {top_n} (or fewer if pool is thin).

CRITICAL RULES
==============
- You are a DISCRIMINATOR. If a candidate doesn't fit, drop it confidently.
- A famous landmark on a different doctrine ranks LOWER than an obscure HC case
  on the exact question.
- Never invent a case_id. Every id in your output must come from the input pool.
- One short reason per dimension is enough. You are not writing essays — Sonnet
  will do that. Speed and discrimination are what we need from you.

OUTPUT JSON
===========
{
  "scored": [
    {
      "id": "string  — must match an input candidate id",
      "dimensions": {
        "statute":   <int 1-10>,
        "stage":     <int 1-10>,
        "doctrinal": <int 1-10>,
        "facts":     <int 1-10>,
        "authority": <int 1-10>
      },
      "weighted_total": <float, rounded to 2 dp>,
      "one_line_reason": "string — one sentence, max 25 words"
    },
    ...
  ],
  "dropped_count": <int — how many you scored < 4.5 and excluded>,
  "kept_count":    <int — length of scored[]>,
  "notes":         "string | null — flag any pool-quality issue, e.g. 'pool dominated by famous landmarks; suggest widening retrieval'"
}

Return ONLY the JSON. No prose, no markdown fences.
"""


PRERANK_USER_TEMPLATE = """STRUCTURED QUERY:
  canonical_question: {canonical_question}
  domain:             {domain}
  primary_statute:    {primary_statute}
  secondary_statutes: {secondary_statutes}
  stage:              {stage}
  appeal_subtype:     {appeal_subtype}
  doctrines:          {doctrines}
  factual_archetype:  {factual_archetype}
  expected_answer:    {expected_answer}
  ranking_hint:       {ranking_hint}

CANDIDATE POOL ({n_candidates} cases):
{candidates_block}

Score every candidate. Drop those below 4.5 weighted. Return top {top_n}.
"""


@dataclass
class PrerankScore:
    """One candidate's pre-rank result."""
    id:               str
    dimensions:       dict
    weighted_total:   float
    one_line_reason:  str

    def to_dict(self) -> dict:
        return asdict(self)


def prerank_candidates(
    refined: RefinedQuery,
    candidates: list[dict],
    *,
    top_n: int = PRERANK_TOP_N,
    min_score: float = PRERANK_MIN_SCORE,
) -> tuple[list[dict], list[PrerankScore], int]:
    """Score `candidates` via Haiku, drop low-scorers, return top N.

    Args:
      refined:    Stage 1 output (canonical question + facets)
      candidates: list of dicts; each must have at minimum:
                    id, title, citation, ratio_or_holding (or 'summary')
                  optional but valued:
                    court, year, statutes (list), stage, doctrines (list)
      top_n:      how many to return after pruning
      min_score:  weighted threshold; below this → dropped

    Returns:
      (kept_candidates, all_scores, cost_paise)
        kept_candidates: subset of input dicts ordered by weighted_total desc
        all_scores:      PrerankScore objects (incl. dropped, for telemetry)
        cost_paise:      cost of the Haiku call
    """
    if not candidates:
        return [], [], 0
    if len(candidates) <= 3:
        # Pool too thin to bother pre-ranking. Pass through.
        return candidates, [], 0

    user_prompt = PRERANK_USER_TEMPLATE.format(
        canonical_question = refined.canonical_question,
        domain             = getattr(refined, "domain", "criminal") or "criminal",
        primary_statute    = refined.primary_statute or "(none)",
        secondary_statutes = ", ".join(refined.secondary_statutes) or "(none)",
        stage              = refined.stage or "(unspecified)",
        appeal_subtype     = refined.appeal_subtype or "(n/a)",
        doctrines          = ", ".join(refined.doctrines_at_issue) or "(none)",
        factual_archetype  = refined.factual_archetype or "(none)",
        expected_answer    = json.dumps(refined.expected_answer_shape or {}, ensure_ascii=False),
        ranking_hint       = refined.ranking_hint or "(none)",
        n_candidates       = len(candidates),
        top_n              = top_n,
        candidates_block   = _format_candidates(candidates),
    )

    system_prompt = PRERANK_SYSTEM.replace("{top_n}", str(top_n))

    try:
        result = route_call(
            "extraction",  # → Haiku
            {
                "system_prompt": system_prompt,
                "user_prompt":   user_prompt,
                "cache":         True,
            },
        )
    except Exception as e:
        log.warning("prerank: Haiku call failed (%s); passing pool through unranked", e)
        return candidates[:top_n], [], 0

    parsed = _parse_json_safe(result.response)
    if not parsed or "scored" not in parsed:
        log.warning("prerank: non-JSON or missing 'scored'; passing pool through unranked")
        return candidates[:top_n], [], result.cost_paise

    cand_by_id = {str(c.get("id")): c for c in candidates}
    scores: list[PrerankScore] = []
    kept_ids: list[tuple[str, float]] = []

    for entry in parsed.get("scored", []):
        cid = str(entry.get("id", ""))
        if not cid or cid not in cand_by_id:
            continue
        weighted = float(entry.get("weighted_total", 0))
        scores.append(PrerankScore(
            id              = cid,
            dimensions      = entry.get("dimensions", {}),
            weighted_total  = weighted,
            one_line_reason = entry.get("one_line_reason", ""),
        ))
        if weighted >= min_score:
            kept_ids.append((cid, weighted))

    # Sort by weighted total descending, take top N.
    kept_ids.sort(key=lambda t: -t[1])
    kept = [cand_by_id[cid] for cid, _ in kept_ids[:top_n]]

    # Annotate each kept candidate with its prerank score for the Sonnet prompt
    score_by_id = {s.id: s for s in scores}
    for c in kept:
        s = score_by_id.get(str(c.get("id")))
        if s:
            c["_prerank"] = {
                "weighted_total": s.weighted_total,
                "dimensions":     s.dimensions,
                "reason":         s.one_line_reason,
            }

    log.info(
        "prerank: scored=%d kept=%d dropped=%d cost_paise=%d",
        len(scores), len(kept), len(scores) - len(kept), result.cost_paise,
    )
    return kept, scores, result.cost_paise


# ---------------------------------------------------------------- helpers

def _format_candidates(candidates: list[dict]) -> str:
    """Render the candidate pool as a compact text block for Haiku.

    Compactness matters here — Haiku has a context window but per-token cost
    means we want the smallest representation that preserves the signal.
    ~150-200 tokens per candidate is the sweet spot.
    """
    blocks: list[str] = []
    for c in candidates:
        lines = [
            f"--- ID: {c.get('id', '?')} ---",
            f"Title:    {_short(c.get('title') or '(untitled)', 120)}",
        ]
        if c.get("citation"):
            lines.append(f"Citation: {_short(c['citation'], 80)}")
        if c.get("court") or c.get("year"):
            lines.append(f"Court:    {c.get('court', '?')} | Year: {c.get('year', '?')}")
        # Pre-extracted facets if available (from fact_extractor)
        facets = c.get("facts") or {}
        facet_bits = []
        if facets.get("statutes"):
            facet_bits.append(f"statutes={facets['statutes'][:3]}")
        if facets.get("stage"):
            facet_bits.append(f"stage={facets['stage']}")
        if facets.get("doctrines"):
            facet_bits.append(f"doctrines={facets['doctrines'][:3]}")
        if facet_bits:
            lines.append("Facets:   " + " | ".join(facet_bits))
        # Ratio / holding
        ratio = c.get("ratio_or_holding") or c.get("holding") or c.get("summary") or ""
        if ratio:
            lines.append(f"Ratio:    {_short(ratio, 400)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _short(s: str, n: int) -> str:
    s = (s or "").strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1] + "…"


def _parse_json_safe(raw: str) -> dict:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}
