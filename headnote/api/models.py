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


class DigestRequest(BaseModel):
    """Input for POST /api/digest."""
    topic: str = Field(..., min_length=5, max_length=2000,
                       description="Doctrinal topic (e.g. 'circumstantial evidence requirements').")


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
