"""Query refinement layer — Stage 1 of the case-law finder pipeline.

Two-step refinement:
  1. normalize() — deterministic regex/alias substitutions (FREE)
  2. canonicalize() — Haiku call producing canonical question + intent (₹0.50)

Public API:
    from headnote.refine import refine_query
    refined = refine_query(raw_input)  # → RefinedQuery dataclass
"""

from headnote.refine.canonicalize import (
    RefinedQuery,
    refine_query,
    canonicalize,
)
from headnote.refine.normalize import normalize

__all__ = ["RefinedQuery", "refine_query", "canonicalize", "normalize"]
