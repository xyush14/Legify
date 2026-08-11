"""Client hearing reminders — the routes behind Home's "Remind clients" panel.

GET   /api/reminders/status              which sending lane is live, and why
GET   /api/reminders/due?date=           everyone listed that day + the exact message
POST  /api/reminders/send                one tap, N clients
GET   /api/reminders/history?case_id=    what this client has already been told
PATCH /api/reminders/my-number           the advocate's own callback number

Auth is `get_current_user`, not `require_beta`. The V2 beta is over and this is a
core feature of the paying product — gating it behind an env var would mean
unsetting one variable silently stops every advocate's clients being reminded.
Same reasoning as the /api/draft-dna/* routes.

The message a client receives is built server-side from the matter's own stored
fields (headnote/reminders/copy.py). The browser may choose WHO to send to and in
WHICH language; it can never supply the words, the date or the number. See
service._rebuild_vars.
"""

from __future__ import annotations

import logging
import re
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements import _supabase
from headnote.reminders import copy as rcopy
from headnote.reminders import service as rsvc
from headnote.reminders import storage as rstore

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/reminders", tags=["reminders"])

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _check_date(d: Optional[str]) -> str:
    from datetime import date as _date
    d = (d or "").strip() or _date.today().isoformat()
    if not _ISO.match(d):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return d


def _advocate(user: CurrentUser) -> tuple[str, str]:
    """The advocate's own name and callback number.

    Both go INTO the client's message — "a reminder from the office of Adv. X …
    call Y if you cannot come" — so they are read from the profile rather than
    accepted from the request. The name falls back to whatever the token carries
    so a lawyer who never filled his profile still gets a signed message; the
    number has no fallback, and its absence is reported as a blocker the panel
    offers to fix, because a reminder a client cannot reply to is a poor one.
    """
    name, phone = "", ""
    try:
        rows = _supabase.select("user_profiles", params={
            "id": f"eq.{user.id}", "select": "advocate_name,phone", "limit": "1"})
        if rows:
            name = (rows[0].get("advocate_name") or "").strip()
            phone = (rows[0].get("phone") or "").strip()
    except Exception as e:  # noqa: BLE001
        log.warning("advocate profile read failed for %.8s: %s", user.id, e)
    if not name:
        name = (getattr(user, "name", "") or getattr(user, "email", "") or "").split("@")[0]
    return name, rsvc.norm_phone(phone)


@router.get("/status", summary="Is automatic sending live, and what is the wording?")
def status(lang: str = Query("hi", description="which language's template body to show"),
           user: CurrentUser = Depends(get_current_user)) -> dict:
    """What the lawyer (and whoever files the template with Meta) needs to know.

    `template_body` is the exact string to register with Meta for that language,
    placeholders and all — approval fails if the registered body differs by a
    character from what we send, so it is published here rather than transcribed.
    """
    name, phone = _advocate(user)
    l = rcopy.normalise(lang)
    return {
        "channel": rsvc.channel_status(),
        "advocate": {"name": name, "phone": phone, "has_number": bool(phone)},
        "languages": list(rcopy.SUPPORTED),
        "needs_signoff": list(rcopy.NEEDS_SIGNOFF),
        "template_name": rsvc.TEMPLATE_NAME,
        "template_lang": l,
        "template_body": rcopy.body(l),
        "template_variables": rcopy.VAR_COUNT,
    }


@router.get("/due", summary="Every client listed on a date, and the message each would get")
def due(date: Optional[str] = Query(None, description="hearing date, YYYY-MM-DD (default today)"),
        lang: Optional[str] = Query(None, description="force a language; default is per-client from the script"),
        user: CurrentUser = Depends(get_current_user)) -> dict:
    day = _check_date(date)
    name, phone = _advocate(user)
    return rsvc.due(user_id=user.id, hearing_iso=day,
                    advocate_name=name, advocate_phone=phone, lang=lang)


class SendBody(BaseModel):
    date: str = Field(..., description="the hearing date these reminders are about, YYYY-MM-DD")
    case_ids: list[str] = Field(..., min_length=1, max_length=200,
                                description="the matters to remind; the server re-checks every gate")
    lang: Optional[str] = Field(None, description="force a language for all of them")
    dry_run: bool = Field(False, description="report what would go out, send nothing")


@router.post("/send", summary="Send the reminders — one call, every ticked client")
def send(body: SendBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    """One tap, N clients.

    Every gate is re-evaluated here against the stored matter, not trusted from
    the panel: consent, a usable number, the double-send guard, and the words
    themselves. A tampered or merely stale browser payload therefore cannot cause
    a message to a client who withdrew consent since the panel was opened.
    """
    day = _check_date(body.date)
    name, phone = _advocate(user)
    try:
        return rsvc.send_batch(user_id=user.id, hearing_iso=day,
                               case_ids=body.case_ids, advocate_name=name,
                               advocate_phone=phone, lang=body.lang,
                               dry_run=body.dry_run)
    except Exception as e:  # noqa: BLE001
        log.exception("reminder batch failed for %.8s on %s", user.id, day)
        raise HTTPException(status_code=502, detail=f"Could not send the reminders: {e}")


@router.get("/history", summary="What this client has already been told")
def history(case_id: str = Query(..., description="the matter"),
            user: CurrentUser = Depends(get_current_user)) -> dict:
    rows = rstore.history_for_matter(user_id=user.id, case_id=case_id)
    return {"case_id": case_id, "items": rows, "count": len(rows)}


class MyNumberBody(BaseModel):
    phone: str = Field(..., min_length=6, max_length=20)


@router.patch("/my-number", summary="Save the advocate's own callback number")
def my_number(body: MyNumberBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Set the number the client is told to call.

    Stored on user_profiles.phone — the same column the daily cause-list message
    and Razorpay prefill already read, in the same "+91XXXXXXXXXX" form
    payments.py writes, so this cannot leave two disagreeing numbers on one user.
    """
    phone = rsvc.norm_phone(body.phone)
    if not rsvc.plausible(phone):
        raise HTTPException(
            status_code=400,
            detail="That does not look like a full mobile number — 10 digits, "
                   "or with the country code.")
    try:
        _supabase.update_or_raise("user_profiles", {"phone": phone},
                                  params={"id": f"eq.{user.id}"})
    except Exception as e:  # noqa: BLE001
        log.warning("could not save office number for %.8s: %s", user.id, e)
        raise HTTPException(status_code=502, detail="Could not save your number — try again.")
    return {"ok": True, "phone": phone}
