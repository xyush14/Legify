"""Saved case-law — a lawyer's personal library of kept research hits.

POST   /api/saved-caselaw            save (upsert on user_id + case_id)
GET    /api/saved-caselaw            list the signed-in lawyer's saved cases
PATCH  /api/saved-caselaw/{case_id}  edit the personal note on one saved case
DELETE /api/saved-caselaw/{case_id}  unsave

What's stored & why a full snapshot
-----------------------------------
Research results carry LLM-generated, *situation-specific* analysis (stinger
sentence, HELD line, court quote, 4-dimension match grid). That analysis is the
reason a lawyer keeps a case — and it is not a static property of the case, so
re-fetching by id later would lose it (and cost an LLM call against a different
query). So we snapshot the whole card object (`case_json`, stored as JSONB) and
re-render it verbatim in the Saved view, with zero LLM cost. A few display
fields are denormalised into columns so the list renders without parsing JSON.
`source_query` records the situation it came from, so the lawyer remembers why.

See migrations/008_saved_caselaw.sql for the table. Auth required — a library
belongs to one signed-in advocate.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements import _supabase


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/saved-caselaw", tags=["saved-caselaw"])

_TABLE = "saved_caselaw"

# Columns returned to the FE for the list view. case_json carries the full card.
# matter_id lets the Saved library group by matter (migration 012).
_LIST_COLS = (
    "id", "case_id", "title", "citation", "court", "year", "source",
    "note", "source_query", "matter_id", "case_json", "created_at", "updated_at",
)


class SaveBody(BaseModel):
    """A save request. case_json is the full normalised card object the FE
    rendered — we store it verbatim so the Saved view re-renders it identically."""
    case_id:      str = Field(..., min_length=1, max_length=200,
                              description="Stable id, e.g. 'ik:529907' or 'BHASK-1999-SC'")
    case_json:    dict = Field(..., description="Full case/card object snapshot")
    source_query: Optional[str] = Field(None, max_length=8000,
                                        description="The research situation this hit came from")
    note:         Optional[str] = Field(None, max_length=4000,
                                        description="Optional personal note set at save time")
    matter_id:    Optional[str] = Field(None,
                                        description="File this authority under a matter, so it "
                                                    "shows in that case's folder (migration 012)")


class NoteBody(BaseModel):
    """PATCH body — only the fields actually sent are written, so a note edit
    never clobbers the matter filing and vice-versa."""
    note: Optional[str] = Field(None, max_length=4000)
    matter_id: Optional[str] = Field(None,
                                     description="Re-file under a matter; explicit null un-files it")


def _clean(s: Optional[str]) -> Optional[str]:
    """Trim; empty/whitespace becomes None (so a field can be cleared)."""
    if s is None:
        return None
    v = str(s).strip()
    return v or None


def _denormalise(case_id: str, cj: dict) -> dict:
    """Pull the few display fields the list view needs out of the snapshot.
    Mirrors the priority used in the FE's normaliseCase()."""
    cj = cj or {}
    return {
        "title":    cj.get("title") or cj.get("case_title") or case_id,
        "citation": cj.get("official_citation") or cj.get("citation") or None,
        "court":    cj.get("court") or None,
        "year":     (str(cj.get("year")) if cj.get("year") not in (None, "") else None),
        "source":   cj.get("source") or None,
    }


@router.post("", summary="Save a case to the signed-in lawyer's library")
def save_caselaw(body: SaveBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Upsert on (user_id, case_id) — saving the same case twice updates the
    snapshot rather than creating a duplicate. `note` is only written when
    provided, so re-saving from a result card never clobbers an existing note."""
    row = {
        "user_id":      user.id,
        "case_id":      body.case_id,
        "case_json":    body.case_json,
        "source_query": _clean(body.source_query),
        **_denormalise(body.case_id, body.case_json),
    }
    if body.matter_id:
        row["matter_id"] = body.matter_id
    if body.note is not None:
        row["note"] = _clean(body.note)

    try:
        saved = _supabase.upsert(_TABLE, row, on_conflict="user_id,case_id")
    except Exception as e:  # noqa: BLE001
        log.exception("saved_caselaw save failed for %.8s case=%s", user.id, body.case_id)
        raise HTTPException(status_code=502, detail=f"could not save case-law: {e}")

    return {"ok": True, "saved": (saved[0] if saved else None)}


@router.get("", summary="List the signed-in lawyer's saved case-law (newest first)")
def list_caselaw(user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        rows = _supabase.select(
            _TABLE,
            params={
                "user_id": f"eq.{user.id}",
                "select":  ",".join(_LIST_COLS),
                "order":   "created_at.desc",
            },
        )
    except Exception as e:  # noqa: BLE001
        log.warning("saved_caselaw list failed for %.8s: %s", user.id, e)
        rows = []
    return {"items": rows, "count": len(rows)}


@router.patch("/{case_id}", summary="Edit the note / matter filing on a saved case")
def update_note(case_id: str, body: NoteBody,
                user: CurrentUser = Depends(get_current_user)) -> dict:
    patch: dict = {}
    if "note" in body.model_fields_set:
        patch["note"] = _clean(body.note)
    if "matter_id" in body.model_fields_set:
        patch["matter_id"] = _clean(body.matter_id)   # null → un-file from the matter
    if not patch:
        return {"ok": True}
    try:
        _supabase.update(
            _TABLE,
            patch,
            params={"user_id": f"eq.{user.id}", "case_id": f"eq.{case_id}"},
        )
    except Exception as e:  # noqa: BLE001
        log.exception("saved_caselaw update failed for %.8s case=%s", user.id, case_id)
        raise HTTPException(status_code=502, detail=f"could not save: {e}")
    return {"ok": True, **patch}


@router.delete("/{case_id}", summary="Remove a case from the library (unsave)")
def delete_caselaw(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        _supabase.delete(
            _TABLE,
            params={"user_id": f"eq.{user.id}", "case_id": f"eq.{case_id}"},
        )
    except Exception as e:  # noqa: BLE001
        log.exception("saved_caselaw delete failed for %.8s case=%s", user.id, case_id)
        raise HTTPException(status_code=502, detail=f"could not remove case: {e}")
    return {"ok": True}


def list_for_matter(user_id: str, matter_id: str, *, limit: int = 50) -> list[dict]:
    """The authorities saved against one matter — powers the case folder's
    Research section. Returns [] rather than raising: a folder that fails to open
    because research is unavailable would be worse than one showing no research."""
    try:
        return _supabase.select(_TABLE, params={
            "user_id": f"eq.{user_id}", "matter_id": f"eq.{matter_id}",
            "order": "updated_at.desc", "limit": str(limit)}) or []
    except Exception as e:  # noqa: BLE001
        log.warning("saved_caselaw matter lookup failed: %s", e)
        return []


def counts_by_matter(user_id: str, matter_ids: list[str]) -> dict[str, int]:
    """How many authorities are saved against each of these matters — in ONE call.

    The Home board needs this for every matter it paints. Asking per matter meant
    one HTTP round trip to Postgres per card: a 40-matter board cost 40 sequential
    network calls before the page could render, which is most of why Home felt
    slow. PostgREST's `in.()` answers the whole board in a single request.

    Returns {} on failure, which degrades a readiness badge — never the board.
    """
    ids = [str(m) for m in matter_ids if m]
    if not ids:
        return {}
    out: dict[str, int] = {}
    # PostgREST puts the filter in the URL, so chunk to keep it well under any
    # proxy's URI limit. 100 uuids ≈ 3.7 KB, comfortably safe.
    for i in range(0, len(ids), 100):
        chunk = ids[i:i + 100]
        quoted = ",".join(f'"{c}"' for c in chunk)
        try:
            rows = _supabase.select(_TABLE, params={
                "user_id": f"eq.{user_id}",
                "matter_id": f"in.({quoted})",
                "select": "matter_id",
                "limit": "2000"}) or []
        except Exception as e:  # noqa: BLE001
            log.warning("saved_caselaw bulk count failed: %s", e)
            continue
        for r in rows:
            mid = str(r.get("matter_id") or "")
            if mid:
                out[mid] = out.get(mid, 0) + 1
    return out
