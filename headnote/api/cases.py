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
from headnote.cases import dateutil as case_dates
from headnote.cases import storage as cases_storage
from headnote.consultations import storage as consult_storage
from headnote.documents import storage as docs_storage
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


def _diary_item(row: dict) -> dict:
    """A matter shaped for the diary: enriched + its next date normalised to ISO
    (for grouping) alongside the raw string (for display)."""
    item = _enrich(row)
    item["next_iso"] = case_dates.to_iso(row.get("next_hearing_date"))
    return item


@router.get("/diary", summary="Matters grouped by next hearing date (the diary)")
def diary(from_: Optional[str] = None, to: Optional[str] = None,
          user: CurrentUser = Depends(get_current_user)) -> dict:
    """Group the lawyer's matters by next hearing date across a window (default:
    the next 7 days from today). Unparseable/empty dates go in `undated`."""
    if not from_:
        from_, to = case_dates.week_window()
    elif not to:
        _, to = case_dates.week_window(from_)

    window = set(case_dates.date_range(from_, to))
    rows = cases_storage.list_cases(user_id=user.id, limit=500)

    by_day: dict[str, list] = {d: [] for d in sorted(window)}
    undated: list = []
    for r in rows:
        item = _diary_item(r)
        iso = item.get("next_iso")
        if iso and iso in by_day:
            by_day[iso].append(item)
        elif not iso:
            undated.append(item)
    days = [{"date": d, "count": len(by_day[d]), "items": by_day[d]}
            for d in sorted(by_day)]
    return {
        "from": from_, "to": to, "today": case_dates.today_iso(),
        "days": days, "undated": undated,
        "total": sum(d["count"] for d in days),
    }


@router.get("/diary/day", summary="Matters listed for one hearing date")
def diary_day(date: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    target = case_dates.to_iso(date) or date
    rows = cases_storage.list_cases(user_id=user.id, limit=500)
    items = [it for it in (_diary_item(r) for r in rows) if it.get("next_iso") == target]
    return {"date": target, "count": len(items), "items": items}


class AdvocateImportBody(BaseModel):
    enrolment_number: str = Field("", max_length=60, description="Bar enrolment/registration number, e.g. MP/1234/2010")
    advocate_name:    str = Field("", max_length=120, description="Fallback if no enrolment number")
    state:            str = Field("", max_length=60)
    court_code:       str = Field("", max_length=60)


@router.post("/import/advocate",
             summary="Import a lawyer's whole case list by Bar enrolment number (lawyer-centric onboarding)")
def import_by_advocate(body: AdvocateImportBody,
                       user: CurrentUser = Depends(get_current_user)) -> dict:
    if not (body.enrolment_number or body.advocate_name):
        raise HTTPException(status_code=400, detail="Give a Bar enrolment number or advocate name")
    try:
        cases = ecourts_client.import_by_advocate(
            body.enrolment_number, advocate_name=body.advocate_name,
            state=body.state, court_code=body.court_code,
        )
    except Exception as e:  # noqa: BLE001 — network / vendor errors
        log.warning("advocate import failed for %s: %s", body.enrolment_number, e)
        raise HTTPException(status_code=502, detail=f"advocate import failed: {e}")

    stored = []
    for case in cases:
        if not case.get("cnr"):
            continue
        row = cases_storage.add_case(user_id=user.id, case=case)
        if row:
            stored.append(_diary_item(row))
    return {"ok": True, "imported": len(stored), "items": stored}


@router.get("/_probe", summary="[temporary] raw vendor probe to lock the live shape")
def probe(key: str, path: str = "", cnr: str = "", enrolment: str = "",
          user: CurrentUser = Depends(get_current_user)) -> dict:
    """Fire one raw GET at the vendor (auth + browser UA) and return status +
    body snippet, so we can capture the real response shape from prod. Gated by
    CNR_API_PROBE_KEY; removed once the mapping is locked."""
    from headnote import config as _cfg
    if not _cfg.CNR_API_PROBE_KEY or key != _cfg.CNR_API_PROBE_KEY:
        raise HTTPException(status_code=403, detail="probe disabled")
    target = path or _cfg.CNR_API_ADVOCATE_PATH
    params = {}
    if cnr:
        params["cnr"] = cnr
    if enrolment:
        params.update({"bar_number": enrolment, "enrolment_number": enrolment, "advocate": enrolment})
    return ecourts_client.probe_raw(target, params)


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
        case_id=case_id,
    )
    return {
        "ok": True,
        "draft_id": draft.id,
        "story_id": story_id,
        "review_url": f"/draft/{story_id}/review?draft={draft.id}",
        "answers": answers,
    }


# ---------------------------------------------------------------- diary log
class HearingLogBody(BaseModel):
    hearing_date:      Optional[str] = Field(None, description="Date this outcome is for")
    what_happened:     Optional[str] = Field(None, max_length=2000)
    next_hearing_date: Optional[str] = Field(None, description="New next date")
    stage:             Optional[str] = Field(None, max_length=200)


@router.post("/{case_id}/hearing-log", summary="Log a hearing outcome + roll the next date")
def hearing_log(case_id: str, body: HearingLogBody,
                user: CurrentUser = Depends(get_current_user)) -> dict:
    row = cases_storage.log_hearing(
        case_id, user_id=user.id,
        hearing_date=body.hearing_date, what_happened=body.what_happened,
        next_hearing_date=body.next_hearing_date, stage=body.stage,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "case": _diary_item(row)}


@router.post("/{case_id}/refresh-next-date",
             summary="Re-fetch the case's next hearing date from the source")
def refresh_next_date(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Roll a matter forward: re-query the CNR source for the new next date.
    (In mock mode this is deterministic; live mode returns the fresh listing.)"""
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    cnr = row.get("cnr") or ""
    if not ecourts_client.is_valid_cnr(cnr):
        # Manual / diary-sourced matter with no real CNR — nothing to re-fetch.
        return {"ok": False, "reason": "no fetchable CNR", "case": _diary_item(row)}
    try:
        fresh = ecourts_client.fetch_cnr(cnr)
    except Exception as e:  # noqa: BLE001
        log.warning("refresh failed for %s: %s", cnr, e)
        raise HTTPException(status_code=502, detail=f"refresh failed: {e}")
    updated = cases_storage.set_next_date(
        case_id, user_id=user.id,
        next_hearing_date=fresh.get("next_hearing_date"), stage=fresh.get("stage"),
    )
    return {"ok": True, "case": _diary_item(updated)}


# ---------------------------------------------------------------- the folder
@router.get("/{case_id}/folder",
            summary="Everything filed under one matter (recordings/drafts/docs/case-law)")
def case_folder(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")

    recordings = consult_storage.list_consultations(user_id=user.id, case_id=case_id)
    drafts = [d.to_dict() for d in draft_storage.list_drafts(user_id=user.id, case_id=case_id, limit=100)]
    documents = docs_storage.list_documents(user_id=user.id, case_id=case_id)
    caselaw: list = []  # matter-linked case-law needs a Supabase matter_id column — deferred

    return {
        "case": _diary_item(row),
        "client": (row.get("case_json") or {}).get("client") or {},
        "recordings": recordings,
        "drafts": drafts,
        "documents": documents,
        "caselaw": caselaw,
        "hearing_logs": cases_storage.list_hearing_logs(case_id, user_id=user.id),
    }


class LinkBody(BaseModel):
    artifact_type: str = Field(..., description="recording | draft | document")
    artifact_id:   str = Field(..., min_length=1, max_length=64)


def _apply_link(kind: str, artifact_id: str, *, case_id: Optional[str], user_id) -> bool:
    if kind in ("recording", "consultation"):
        return consult_storage.set_consultation_case(artifact_id, case_id=case_id, user_id=user_id)
    if kind == "draft":
        return draft_storage.set_draft_case(artifact_id, case_id=case_id, user_id=user_id)
    if kind in ("document", "doc"):
        return docs_storage.set_document_case(artifact_id, case_id=case_id, user_id=user_id)
    raise HTTPException(status_code=400, detail=f"unknown artifact_type {kind!r}")


@router.post("/{case_id}/link", summary="File an existing recording/draft/document under this matter")
def link_artifact(case_id: str, body: LinkBody,
                  user: CurrentUser = Depends(get_current_user)) -> dict:
    if cases_storage.get_case(case_id, user_id=user.id) is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    ok = _apply_link(body.artifact_type, body.artifact_id, case_id=case_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found or not yours")
    return {"ok": True}


@router.post("/{case_id}/unlink", summary="Remove an artifact from this matter")
def unlink_artifact(case_id: str, body: LinkBody,
                    user: CurrentUser = Depends(get_current_user)) -> dict:
    ok = _apply_link(body.artifact_type, body.artifact_id, case_id=None, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found or not yours")
    return {"ok": True}
