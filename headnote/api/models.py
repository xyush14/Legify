"""Pydantic request/response models for the HTTP API.

Uses `typing.Optional` rather than `str | None` because Pydantic v2 evaluates
type annotations at class-definition time, and Pydantic's class machinery
does not honour `from __future__ import annotations`. On Python 3.9 the
PEP 604 union syntax raises TypeError at import. Optional[...] works on
3.9 and is identical at runtime on 3.10+.
"""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class SituationRequest(BaseModel):
    """Input for POST /api/situation."""
    situation: str = Field(..., min_length=10, max_length=8000,
                           description="Lawyer's factual scenario in plain English.")
    style: Literal["journal", "practitioner"] = Field(
        "journal",
        description="'journal' = Cri.L.J. headnote format; 'practitioner' = compressed chambers digest.",
    )
    deep_mode: bool = Field(
        False,
        description=(
            "Premium toggle: skip Sonnet entirely and go straight to Opus "
            "for highest-quality output. Disables the confidence-based "
            "auto-retry (no upgrade path beyond Opus)."
        ),
    )
    mode: Literal["hidden", "famous", "mixed"] = Field(
        "hidden",
        description=(
            "Ranking mode for candidate cases. "
            "'hidden' (default) — penalises fame; surfaces obscure-but-relevant authorities. "
            "'famous' — boosts citation count; returns the leading cases lawyers already know. "
            "'mixed' — neutral; ranks on fact-pattern + jurisdiction + recency."
        ),
    )
    jurisdiction: Optional[str] = Field(
        None,
        description=(
            "Optional jurisdiction hint for the ranker (e.g. 'Bombay High Court'). "
            "Boosts cases from the same court. Supreme Court is always boosted."
        ),
    )


class DigestRequest(BaseModel):
    """Input for POST /api/digest."""
    topic: str = Field(..., min_length=5, max_length=2000,
                       description="Doctrinal topic (e.g. 'circumstantial evidence requirements').")
    deep_mode: bool = Field(
        False,
        description="Premium toggle: force Opus for highest-quality output.",
    )


class HeadnoteRequest(BaseModel):
    """Input for POST /api/headnote."""
    judgment_text: str = Field(..., min_length=200, max_length=80000,
                               description="Full text of an Indian criminal-law judgment.")


class TranslateRequest(BaseModel):
    """Input for POST /api/translate."""
    payload: dict
    target_language: Literal["hi"] = "hi"


class FeedbackRequest(BaseModel):
    """Input for POST /api/feedback."""
    mode: str
    input_text: str
    output_json: str
    rating: int = Field(..., description="1 for thumbs-up, -1 for thumbs-down.")
    correction: Optional[str] = None
    lawyer_handle: Optional[str] = None
