"""Retrieval primitives: keyword scoring (curated corpus), local embeddings,
and the Hidden Authorities re-ranker."""

from .keyword import prefilter_cases, score_case
from .embeddings import EmbeddingIndex, EmbeddingHit, EMBED_MODEL_NAME, EMBED_DIM
from .hidden_authorities import (
    Candidate, ScoredCandidate, Mode,
    rank_candidates, explain_score,
)

__all__ = [
    "prefilter_cases", "score_case",
    "EmbeddingIndex", "EmbeddingHit", "EMBED_MODEL_NAME", "EMBED_DIM",
    "Candidate", "ScoredCandidate", "Mode",
    "rank_candidates", "explain_score",
]
