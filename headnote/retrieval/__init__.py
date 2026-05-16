"""Retrieval primitives: keyword scoring (curated corpus) + local embeddings."""

from .keyword import prefilter_cases, score_case
from .embeddings import EmbeddingIndex, EmbeddingHit, EMBED_MODEL_NAME, EMBED_DIM

__all__ = [
    "prefilter_cases", "score_case",
    "EmbeddingIndex", "EmbeddingHit", "EMBED_MODEL_NAME", "EMBED_DIM",
]
