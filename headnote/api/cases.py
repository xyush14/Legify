"""Cases ("Matters") — CNR-driven case folders that pre-fill the drafter.

POST   /api/cases/add-cnr              fetch a CNR (+ optional client), store it
GET    /api/cases                      list the lawyer's matters (with suggestions)
GET    /api/cases/{id}                 one matter (full payload + suggestions)
PATCH  /api/cases/{id}/client          save/merge client details (name/mobile/…)
DELETE /api/cases/{id}                 remove a matter
POST   /api/cases/{id}/draft/{story}   create a draft PRE-FILLED from the matter

Each matter carries `suggested`: the stage-aware ordered list of which draft
fits where the case is (primary first) — so the UI offers the right action.

Auth required (get_current_user). Locally (SUPABASE_URL unset) that returns the
synthetic dev user, so the flow works tokenless.

Cost: add-cnr in live mode spends one CASE_DETAIL credit (≈ ₹1.50); the draft
step is free (Headnote's own templates). Client details are lawyer-entered (the
CNR never has the client's phone) and power both autofill and reminders.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user
from headnote.cases import ecourts_client, mapping
from headnote.cases import storage as cases_storage
from headnote.drafter import storage as draft_storage, stories


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])

_STORY_LABELS = {"bail": "जमानत", "discharge": "उन्मोचन"}


class ClientBody(BaseModel):
    """The client the lawyer represents in this matter. All optional — eCourts
    never supplies these; the lawyer fills them once for autofill + reminders."""
    name:       Optional[str] = Field(None, max_length=200)
    father:     Optional[str] = Field(None, max_length=200, description="Father/Husband name")
    age:        Optional[str] = Field(None, max_length=12)
    occupation: Optional[str] = Field(None, max_length=120)
    address:    Optional[str] = Field(None, max_length=500)
    mobile:     Optional[str] = Field(None, max_length=20)
    email:      Optional[str] = Field(None, max_length=200)
    role:       Optional[str] = Field(None, max_length=40, description="accused | complainant | applicant …")
    consent:    Optional[bool] = Field(None, description="client consents to hearing reminders (DPDP)")


class AddCnrBody(BaseModel):
    cnr:    str = Field(..., min_length=1, max_length=32,
                        description="16-character eCourts CNR (e.g. MPGW010000122021)")
    client: Optional[ClientBody] = Field(None, description="Optional client details to save with the case")


def _enrich(row: Optional[dict]) -> Optional[dict]:
    """Attach the stage-aware draft suggestions to a matter row."""
    if row:
        row["suggested"] = mapping.suggest_drafts(row.get("case_json") or {})
    return row


@router.post("/add-cnr", summary="Fetch a case by CNR (+ optional client) and store it")
def add_case_by_cnr(body: AddCnrBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        case = ecourts_client.fetch_cnr(body.cnr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — network / vendor errors
        log.warning("CNR lookup failed for %s: %s", body.cnr, e)
        raise HTTPException(status_code=502, detail=f"CNR lookup failed: {e}")

    if body.client is not None:
        case["client"] = body.client.model_dump(exclude_none=True)

    row = cases_storage.add_case(user_id=user.id, case=case)
    return {"ok": True, "case": _enrich(row)}


@router.get("", summary="List the lawyer's matters (newest first)")
def list_cases(user: CurrentUser = Depends(get_current_user)) -> dict:
    items = [_enrich(r) for r in cases_storage.list_cases(user_id=user.id)]
    return {"items": items, "count": len(items)}


@router.get("/{case_id}", summary="Get one matter (full payload + suggestions)")
def get_case(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return _enrich(row)


@router.patch("/{case_id}/client", summary="Save/merge the client's details on a matter")
def set_client(case_id: str, body: ClientBody,
               user: CurrentUser = Depends(get_current_user)) -> dict:
    patch = body.model_dump(exclude_none=True)
    row = cases_storage.update_client(case_id, user_id=user.id, client=patch)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "case": _enrich(row)}


@router.delete("/{case_id}", summary="Remove a matter")
def delete_case(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    if not cases_storage.delete_case(case_id, user_id=user.id):
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "deleted": case_id}


@router.post("/{case_id}/draft/{story_id}",
             summary="Create a draft PRE-FILLED from this matter (the differentiator)")
def draft_for_case(case_id: str, story_id: str,
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    """Load the matter → map its parties/court/sections (+ client details) onto
    the template's fields → create a real draft → hand back a link to review it."""
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")

    if story_id not in mapping.SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"draft type '{story_id}' not supported yet "
                   f"(have: {', '.join(mapping.SUPPORTED)})",
        )
    s = stories.get_story(story_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown story_id={story_id!r}")

    answers = mapping.map_case_to_answers(story_id, row["case_json"])
    label = _STORY_LABELS.get(story_id, story_id)
    draft = draft_storage.create_draft(
        story_id=story_id,
        template_version=s.template_version,
        user_id=user.id,
        lang="hi",
        answers=answers,
        title=f"{label} — {row.get('case_title') or row.get('cnr')}",
    )
    return {
        "ok": True,
        "draft_id": draft.id,
        "story_id": story_id,
        "review_url": f"/draft/{story_id}/review?draft={draft.id}",
        "answers": answers,
    }
