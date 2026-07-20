"""Public, token-scoped daily cause-list endpoints (NO login).

A lawyer opens their daily link (/d/<token>, served by app.py) — this router backs
that page:
  GET  /api/daily/{token}          → the cause list for the token's date
  POST /api/daily/{token}/settle   → upload the marked sheet → patch next dates

The token (headnote/cases/daily_links.py) is an HMAC-signed {user_id, date, exp};
verifying it authorises ONLY that one lawyer's cause list for that one date — never
the whole account. No Supabase JWT needed, so it works from a WhatsApp tap.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date as _date, timedelta

from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from headnote.cases import daily_links
from headnote.cases import storage as cases_storage
from headnote.cases import dateutil as case_dates
from headnote.api.cases import _run_diary_ocr, settle_rows, _diary_item

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/daily", tags=["daily"])


def _resolve(token: str):
    ctx = daily_links.verify_token(token)
    if not ctx:
        raise HTTPException(status_code=403, detail="This link is invalid or has expired.")
    return ctx["user_id"], ctx["date"]


def _next_day(iso: str) -> str:
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return (_date(y, m, d) + timedelta(days=1)).strftime("%Y-%m-%d")
    except Exception:  # noqa: BLE001
        return iso


def _day_items(user_id, date_iso: str) -> list:
    target = case_dates.to_iso(date_iso) or date_iso
    rows = cases_storage.list_cases(user_id=user_id, limit=500)
    return [it for it in (_diary_item(r) for r in rows) if it.get("next_iso") == target]


@router.get("/{token}", summary="Cause list for a daily link (no login)")
def daily_view(token: str) -> dict:
    """One evening touchpoint: settle the token's date (upload the marked sheet) AND
    print the NEXT day's list (ready for tomorrow morning)."""
    user_id, date = _resolve(token)
    settle_date = case_dates.to_iso(date) or date
    prep_date = _next_day(settle_date)
    settle_items = _day_items(user_id, settle_date)
    prep_items = _day_items(user_id, prep_date)
    return {"ok": True, "today": case_dates.today_iso(),
            "settle_date": settle_date, "settle_items": settle_items,
            "settle_count": len(settle_items),
            "prep_date": prep_date, "prep_items": prep_items,
            "prep_count": len(prep_items)}


@router.post("/{token}/settle", summary="Upload the marked sheet for a daily link (no login)")
async def daily_settle(token: str, file: UploadFile = File(...)) -> dict:
    """OCR the handwritten Next Date column off the uploaded sheet and patch the
    matters listed on the token's date — rolling each onto its new hearing date."""
    user_id, date = _resolve(token)
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    fname = file.filename or "diary.jpg"
    mime = (file.content_type or "").split(";")[0].strip() or "image/jpeg"
    try:
        page_date, rows, engine, err = await asyncio.to_thread(_run_diary_ocr, data, fname, mime)
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
    target = case_dates.to_iso(date) or date
    res = settle_rows(user_id, rows, page_default=page_date or target)
    return {"ok": True, "engine": engine, "read": len(rows),
            "settled": res.get("logged", 0), "added": res.get("imported", 0) - res.get("logged", 0),
            "engine_error": err}


class _DateUpdate(BaseModel):
    case_id:   str = Field(..., min_length=1, max_length=64)
    next_date: str = Field("", max_length=40)
    stage:     str = Field("", max_length=200)


class _SetDatesBody(BaseModel):
    updates: list[_DateUpdate] = Field(default_factory=list)


@router.post("/{token}/set-dates",
             summary="Manually set next dates for a daily link (no login, no OCR)")
def daily_set_dates(token: str, body: _SetDatesBody) -> dict:
    """The manual alternative to uploading a photo: the lawyer types each case's next
    date on the link page. Each update rolls that matter onto its new date and logs
    the hearing. Only the token's own matters can be touched (set_next_date/log_hearing
    are scoped to the token's user_id)."""
    user_id, date = _resolve(token)
    hearing_on = case_dates.to_iso(date) or date
    updated = 0
    for u in body.updates:
        nd = (u.next_date or "").strip()
        if not nd:
            continue
        row = cases_storage.log_hearing(
            u.case_id, user_id=user_id, hearing_date=hearing_on,
            what_happened="settled (manual)", next_hearing_date=nd,
            stage=(u.stage or None))
        if row:
            updated += 1
    return {"ok": True, "updated": updated}
