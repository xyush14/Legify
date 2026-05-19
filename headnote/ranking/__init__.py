"""Stage 3 ranking layer — Haiku scores the candidate pool on a 5-dimension
rubric BEFORE the expensive Sonnet call.

Public API:
    from headnote.ranking import prerank_candidates
    top_n, scores, cost_paise = prerank_candidates(refined_query, candidates, top_n=10)
"""

from headnote.ranking.prerank import prerank_candidates, PrerankScore

__all__ = ["prerank_candidates", "PrerankScore"]
