"""Personal-assist endpoints — the in-product "we'll help you personally"
escape hatch.

Two CTAs fire requests here:

    POST /api/assist/research
        Lawyer didn't like the research output → wants a human to send
        case-law. Promise: case-law back within 15 minutes.

    POST /api/assist/draft
        Lawyer can't find the template they need → wants it uploaded.
        Promise: template live within 2 hours.

Both are simple, fire-and-forget. The frontend shows a success toast as
soon as it gets 2xx; the founder gets an email immediately via Resend
and replies to the lawyer directly (so the lawyer's experience is "I
said something, a human got back to me").

Auth is required (so we don't get drive-by spam). No quota — these are
manual-help requests, not LLM calls.
"""

from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from headnote.email import send_assist_request
from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements import _supabase


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/assist", tags=["assist"])


class AssistBody(BaseModel):
    query: str = Field(..., min_length=3, max_length=2000,
                       description="What the lawyer wants — a case-law ask or a template name")
    source_context: Optional[str] = Field(
        None, max_length=2000,
        description="The lawyer's last research query / page context, so we don't have to ask them",
    )


def _profile(user_id: str) -> dict:
    """Pull name + phone from user_profiles. Best-effort; empty dict on miss."""
    try:
        rows = _supabase.select(
            "user_profiles",
            params={"id": f"eq.{user_id}", "select": "name,phone", "limit": "1"},
        )
        return rows[0] if rows else {}
    except Exception as e:
        log.info("assist: profile lookup failed for user=%.8s: %s", user_id, e)
        return {}


def _handle(mode: Literal["research", "draft"], body: AssistBody, user: CurrentUser) -> dict:
    if not user.email:
        raise HTTPException(status_code=400, detail="No email on account — cannot route reply.")
    profile = _profile(user.id)
    sent = send_assist_request(
        mode=mode,
        query=body.query.strip(),
        user_email=user.email,
        user_name=profile.get("name") or "",
        user_phone=profile.get("phone") or "",
        source_context=(body.source_context or "").strip() or None,
    )
    # Always 2xx — the lawyer's UX shouldn't depend on whether Resend was
    # configured. If `sent` is False we still log it server-side.
    if not sent:
        log.warning("assist: send_assist_request returned False for user=%.8s mode=%s",
                    user.id, mode)
    return {"ok": True, "sent": sent}


@router.post("/research", summary="Lawyer requests personal case-law help (15-min SLA)")
def post_research_assist(
    body: AssistBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Fired by the 'Not satisfied? Our team will assist you personally'
    CTA in research mode. The lawyer's last query goes in `source_context`
    so the founder doesn't have to ask what they were searching."""
    return _handle("research", body, user)


@router.post("/draft", summary="Lawyer requests a template we don't have yet (2-hour SLA)")
def post_draft_assist(
    body: AssistBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Fired by the 'Not finding what you need? We'll upload within 2 hours'
    CTA on the draft picker. `query` is the template they want (free-form
    name + use-case); `source_context` is the court filter they were on,
    if any."""
    return _handle("draft", body, user)
