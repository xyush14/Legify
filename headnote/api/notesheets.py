"""Home hub + hearing note sheets.

GET   /api/home?date=                 the whole Home screen in one call
PATCH /api/matters/{id}/prep          purpose · prepared tick · assignee · board item
GET   /api/matters/{id}/notesheet     the sheet for a hearing date
PUT   /api/matters/{id}/notesheet     save the sheet (lawyer edits, or after OCR)
POST  /api/matters/{id}/notesheet/prepare   assemble a first draft from the file
POST  /api/matters/{id}/notesheet/scan      read the handwritten sheet + check it
DELETE /api/matters/{id}/notesheet    discard the sheet for that date

Everything is scoped to the signed-in lawyer. These routes are called ONLY by
the V2 Home screen (static/home.html), so they depend on `require_beta` rather
than plain `get_current_user`: signed in AND on the V2 beta allowlist, else 403
{"code": "not_in_beta"}. See headnote/entitlements/beta.py. Nothing on the old
/app surface calls these, so the gate cannot affect existing users.

Readiness is derived server-side (headnote/notesheets/readiness.py) so the badge
a lawyer sees is never the frontend's opinion.

Nothing is invented: `prepare` only arranges what the matter already holds, and
`scan` reports what it read plus deterministic checks (section concordance,
citation lookup) — the lawyer confirms before anything is stored.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import asdict, is_dataclass
from datetime import date as _date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from headnote import statute_map
from headnote.cases import dateutil as case_dates
from headnote.cases import courtsync
from headnote.cases import ecourts_client
from headnote.cases import storage as cases_storage
from headnote.consultations import storage as consult_storage
from headnote.documents import storage as docs_storage
from headnote.drafter import storage as draft_storage
from headnote.api import saved_caselaw
from headnote.entitlements import CurrentUser, require_beta
from headnote.notesheets import readiness as rd
from headnote.notesheets import storage as ns_storage

log = logging.getLogger(__name__)
router = APIRouter(tags=["home"])

_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today_iso() -> str:
    return _date.today().isoformat()


def _check_date(d: Optional[str]) -> str:
    d = (d or "").strip() or _today_iso()
    if not _ISO.match(d):
        raise HTTPException(status_code=400, detail="date must be YYYY-MM-DD")
    return d


def _iso_of(raw: Optional[str]) -> Optional[str]:
    """Court dates arrive as dd/mm/yyyy; normalise for grouping."""
    if not raw:
        return None
    try:
        return case_dates.to_iso(raw)
    except Exception:  # noqa: BLE001
        return None


def _party(case: dict) -> str:
    cj = case.get("case_json") or {}
    client = (cj.get("client") or {}).get("name")
    if client:
        return client
    for key in ("respondent_name", "petitioner_name"):
        v = cj.get(key)
        if v and not re.search(r"राज्य|state|union of india", str(v), re.I):
            return v
    return case.get("case_title") or case.get("cnr") or "—"


def _rowdict(x) -> dict:
    """The three artifact stores disagree on shape: drafts come back as `Draft`
    dataclasses, documents and recordings as plain dicts. Normalise both."""
    if isinstance(x, dict):
        return x
    if is_dataclass(x) and not isinstance(x, type):
        return asdict(x)
    return {k: getattr(x, k) for k in dir(x)
            if not k.startswith("_") and not callable(getattr(x, k, None))}


def _artifacts(case_id: str, user_id: str) -> dict:
    """What exists for this matter — the other half of the readiness rule."""
    def _safe(fn, **kw):
        try:
            return [_rowdict(r) for r in (fn(**kw) or [])]
        except Exception as e:  # noqa: BLE001
            log.warning("artifact lookup failed for %s: %s", case_id, e)
            return []

    drafts = _safe(draft_storage.list_drafts, user_id=user_id, case_id=case_id)
    docs = _safe(docs_storage.list_documents, user_id=user_id, case_id=case_id)
    recs = _safe(consult_storage.list_consultations, user_id=user_id, case_id=case_id)
    # Authorities saved to this matter. These were NOT being loaded — readiness
    # was called with a hardcoded `authorities=[]`, so an arguments hearing always
    # read "Still to prepare: authorities" even when the lawyer had saved a dozen
    # judgments to the file, and research was never a state we could know about.
    auths = _safe(saved_caselaw.list_for_matter, user_id=user_id, matter_id=case_id)
    return {
        "drafts": [{"id": d.get("id"), "title": d.get("title") or d.get("story_id"),
                    "status": "filed" if d.get("exported_at") else "draft"} for d in drafts],
        "documents": [{"id": d.get("id"), "title": d.get("title"),
                       "pages": d.get("page_count")} for d in docs],
        "recordings": [{"id": r.get("id"), "title": r.get("title"),
                        "duration_sec": r.get("duration_sec")} for r in recs],
        "authorities": [{"id": a.get("case_id") or a.get("id"), "title": a.get("title"),
                         "citation": a.get("citation")} for a in auths],
    }


def _artifacts_bulk(case_ids: list[str], user_id: str) -> dict[str, dict]:
    """`_artifacts` for a whole board — FOUR queries instead of four per matter.

    Painting Home used to cost 4 lookups per card: three SQLite round trips that
    each opened a connection and re-ran the schema DDL, plus one HTTP call to
    Postgres for saved authorities. A 40-matter board therefore made ~160 calls,
    40 of them over the network, strictly sequentially — which is the bulk of why
    Home took seconds to appear and why changing the date felt broken.

    Readiness needs the real draft rows (their title, and whether one is final),
    but only the COUNT of documents, recordings and authorities. So drafts come
    back in full and the rest as integers.
    """
    ids = [str(c) for c in case_ids if c]
    if not ids:
        return {}
    drafts_by = draft_storage.drafts_for_cases(user_id, ids)
    docs_n = docs_storage.counts_by_case(user_id, ids)
    recs_n = consult_storage.counts_by_case(user_id, ids)
    auth_n = saved_caselaw.counts_by_matter(user_id, ids)
    return {cid: {"drafts": drafts_by.get(cid, []),
                  "documents": docs_n.get(cid, 0),
                  "recordings": recs_n.get(cid, 0),
                  "authorities": auth_n.get(cid, 0)}
            for cid in ids}


def _as_rows(v) -> list[dict]:
    """Readiness takes lists; the bulk path carries counts. A count of n is
    exactly n anonymous rows as far as `derive` is concerned — it only ever asks
    "any?" of documents and "how many?" of authorities."""
    if isinstance(v, int):
        return [{} for _ in range(max(0, v))]
    return v or []


def _matter_card(case: dict, user_id: str, *, with_artifacts: bool = True,
                 arts: Optional[dict] = None) -> dict:
    prep = ns_storage.get_prep(case)
    row = dict(case)
    row["prep"] = prep
    if arts is None:
        arts = _artifacts(str(case["id"]), user_id) if with_artifacts else {}
    state = rd.derive(row,
                      drafts=_as_rows(arts.get("drafts")),
                      documents=_as_rows(arts.get("documents")),
                      authorities=_as_rows(arts.get("authorities")))
    # Carry the wording with the state. Every screen used to keep its own copy of
    # the state→label map, so adding a state (e.g. "research") silently degraded
    # to "Review" everywhere until each copy was found and updated.
    state["label"] = rd.label(state["state"])
    cj = case.get("case_json") or {}
    return {
        "id": case["id"],
        "cnr": case.get("cnr"),
        "case_title": case.get("case_title"),
        "party": _party(case),
        "court_name": case.get("court_name"),
        "case_number": case.get("case_number"),
        "case_year": case.get("case_year"),
        "stage": case.get("stage"),
        "next_hearing_date": case.get("next_hearing_date"),
        "next_hearing_iso": _iso_of(case.get("next_hearing_date")),
        "prev_hearing_date": cj.get("last_listed_date"),
        "purpose": prep.get("purpose"),
        "prepared": bool(prep.get("prepared")),
        "assignee": prep.get("assignee"),
        "item": prep.get("item"),
        "time": prep.get("time"),
        # straight off the court's own cause list — which room, and the judge
        "court_no": prep.get("court_no"),
        "judge": prep.get("judge"),
        "readiness": state,
        "counts": {k: (v if isinstance(v, int) else len(v))
                   for k, v in arts.items()} if arts else {},
        "court_updates": len(courtsync.unseen(cj)),
    }


# ============================================================ the Home screen

@router.get("/api/home", summary="Everything the Home screen needs, in one call")
def home(date: Optional[str] = Query(None, description="board date, YYYY-MM-DD (default today)"),
         week_from: Optional[str] = Query(None, description="Monday of the week strip (default: this week)"),
         span: int = Query(1, ge=1, le=3,
                           description="1 = just `date`; 3 = yesterday+today+tomorrow around `date`"),
         user: CurrentUser = Depends(require_beta)) -> dict:
    day = _check_date(date)
    today = _today_iso()
    cases = cases_storage.list_cases(user_id=user.id, limit=500) or []

    # The 3-day view is one call, not three: the lawyer's whole docket is already
    # in memory here, so widening the window costs nothing but the card build.
    d0 = datetime.fromisoformat(day)
    span_dates = ([(d0 + timedelta(days=i)).date().isoformat() for i in (-1, 0, 1)]
                  if span == 3 else [day])

    boards: dict[str, list] = {d: [] for d in span_dates}
    undated, overdue, week, month = [], [], 0, 0
    month_days: dict[str, int] = {}
    anchor = _check_date(week_from) if week_from else today
    a = datetime.fromisoformat(anchor)
    wk_start = a - timedelta(days=a.weekday())
    wk_days = {(wk_start + timedelta(days=i)).date().isoformat(): 0 for i in range(7)}

    # Matters with no real CNR can never be court-synced — they came from a
    # photographed cause list, not from eCourts. Counting them is what turns
    # "the sync does nothing" into something the lawyer can actually fix.
    unlinked = sum(1 for c in cases
                   if not ecourts_client.is_valid_cnr((c.get("cnr") or "").strip()))

    # Everything the board will paint, resolved in one batch before the loop.
    # Building cards inside the loop meant the artifact lookups ran per matter.
    on_board = [c for c in cases if _iso_of(c.get("next_hearing_date")) in boards]
    arts_by = _artifacts_bulk([str(c["id"]) for c in on_board], user.id)

    for c in cases:
        iso = _iso_of(c.get("next_hearing_date"))
        if iso in boards:
            boards[iso].append(_matter_card(c, user.id, arts=arts_by.get(str(c["id"]), {})))
        if iso is None or not c.get("next_hearing_date"):
            undated.append({"id": c["id"], "party": _party(c),
                            "court_name": c.get("court_name"),
                            "last_listed": (c.get("case_json") or {}).get("last_listed_date")})
        if iso:
            if iso in wk_days:
                wk_days[iso] += 1
                week += 1
            if iso[:7] == today[:7]:
                month += 1
            # dots for the calendar popover, for the month the lawyer is looking at
            if iso[:7] == day[:7]:
                month_days[iso] = month_days.get(iso, 0) + 1
            # A date that has passed with no new date is NOT "nothing listed" —
            # it is a matter waiting to be settled. Without this it silently
            # disappears from every day of the diary.
            if iso < today:
                overdue.append({"id": c["id"], "party": _party(c),
                                "court_name": c.get("court_name"),
                                "cnr": c.get("cnr"),
                                "next_hearing_date": c.get("next_hearing_date"),
                                "next_hearing_iso": iso})

    for d in boards:
        boards[d].sort(key=lambda m: (m.get("item") or 999, str(m.get("time") or ""), m["party"]))
    overdue.sort(key=lambda m: m["next_hearing_iso"], reverse=True)
    board = boards[day]
    ready = [m for m in board if m["readiness"]["state"] == "ready"]
    gaps = [m for m in board if m["readiness"]["state"] != "ready"]
    for d, rows in boards.items():
        sheets_d = ns_storage.list_for_date(user.id, d)
        for m in rows:
            m["has_note_sheet"] = str(m["id"]) in sheets_d

    # what the courts changed since the lawyer last looked — the reason to open
    # the dashboard at all, so it rides along with the board in the same call
    inbox = []
    for c in cases:
        cj_c = c.get("case_json") or {}
        for u in courtsync.unseen(cj_c if isinstance(cj_c, dict) else {}):
            inbox.append({**u, "case_id": c["id"], "party": _party(c),
                          "court_name": c.get("court_name")})
    inbox.sort(key=lambda u: str(u.get("at") or ""), reverse=True)

    # Who is actually in this chamber — learned from the names the advocate has
    # assigned work to, never invented. The UI used to offer a hardcoded
    # ["Adv. Nikhil Jain", "Adv. Priya Soni", "Clerk"] to every user, which is
    # mock data on a live screen: it tells a sole practitioner he has two juniors
    # he has never heard of. An empty roster is correct for a lawyer working
    # alone; the free-text field is how the first name gets in.
    roster: dict[str, int] = {}
    for c in cases:
        who = (ns_storage.get_prep(c).get("assignee") or "").strip()
        if who:
            roster[who] = roster.get(who, 0) + 1

    return {
        "roster": [w for w, _ in sorted(roster.items(), key=lambda kv: (-kv[1], kv[0]))][:8],
        "date": day, "today": today, "span": span,
        "board": board,
        "boards": boards,
        "counts": {"board": len(board), "ready": len(ready), "gaps": len(gaps),
                   "week": week, "month": month, "undated": len(undated),
                   "overdue": len(overdue), "unlinked": unlinked,
                   "notes_ready": sum(1 for m in board if m["has_note_sheet"]),
                   "court_updates": len(inbox)},
        "court_updates": inbox[:12],
        "week_days": wk_days,
        "month_days": month_days,
        "undated": undated[:20],
        "overdue": overdue[:20],
        "courts": sorted({(m.get("court_name") or "").split("/")[0].strip()
                          for m in board if m.get("court_name")}),
    }


@router.get("/api/home/month", summary="Hearing counts per day for one month (calendar dots)")
def home_month(month: str = Query(..., description="YYYY-MM"),
               user: CurrentUser = Depends(require_beta)) -> dict:
    """Feeds the calendar popover so it can page months without disturbing the
    board. Counts only — no card building, so it stays cheap."""
    m = (month or "").strip()
    if not re.match(r"^\d{4}-\d{2}$", m):
        raise HTTPException(status_code=400, detail="month must be YYYY-MM")
    days: dict[str, int] = {}
    for c in cases_storage.list_cases(user_id=user.id, limit=500) or []:
        iso = _iso_of(c.get("next_hearing_date"))
        if iso and iso[:7] == m:
            days[iso] = days.get(iso, 0) + 1
    return {"month": m, "days": days, "total": sum(days.values())}


@router.post("/api/home/sync-court", summary="Re-read the court record for this lawyer's whole docket")
async def sync_court_now(user: CurrentUser = Depends(require_beta)) -> dict:
    """The one button behind "check the court for new dates".

    Overdue matters were a dead end: the banner only navigated to the first one,
    and settling 122 of them by hand is not a thing anyone will do. This runs the
    same three-pass sweep the 18:00 cron runs — batch cause list, then a full
    read only for matters the court actually moved — but for this lawyer, now.

    Deliberately reuses `sync_all_dockets` rather than looping `fetch_cnr`: the
    per-matter refresh costs one vendor call per matter, where the sweep answers
    a whole docket in a handful.

    Runs in a worker thread. It is blocking HTTP to the vendor, and blocking the
    event loop is exactly how this app got pulled from Fly's routing pool twice
    while it was perfectly healthy.
    """
    from headnote.cases.daily_sync import sync_all_dockets

    res = await asyncio.to_thread(sync_all_dockets, only_user_id=user.id)

    # Be straight about the split. Most of this docket came off a photographed
    # cause list and has no CNR, so "check the court" can do nothing for those —
    # saying "0 updated" without saying why reads as a broken button.
    return {"ok": bool(res.get("ok", True)),
            "reason": res.get("reason"),
            "checked": res.get("synced", 0),
            "changed": res.get("changed", 0),
            "no_cnr": res.get("skipped_no_cnr", 0),
            "failed": res.get("failed", 0),
            "updates": (res.get("updates") or [])[:20]}


# ============================================================ preparation state

class PrepBody(BaseModel):
    purpose: Optional[str] = Field(None, description="what the court listed it for")
    prepared: Optional[bool] = Field(None, description="the lawyer's explicit tick")
    assignee: Optional[str] = Field(None, description="junior this file is assigned to")
    item: Optional[int] = Field(None, description="serial/item number on the board")
    time: Optional[str] = Field(None, description="time, where the court gives one")
    clear_assignee: bool = Field(False, description="unassign the junior")
    clear_override: bool = Field(False, description="drop a manual status back to auto")


@router.patch("/api/matters/{case_id}/prep", summary="Set purpose, the prepared tick, or the assigned junior")
def set_prep(case_id: str, body: PrepBody,
             user: CurrentUser = Depends(require_beta)) -> dict:
    patch = body.model_dump(exclude_none=True)
    patch.pop("clear_assignee", None)
    patch.pop("clear_override", None)
    # A purpose the lawyer typed is theirs: flag it so the next court sync does
    # not quietly overwrite it with the vendor's wording.
    if patch.get("purpose"):
        patch["purpose_manual"] = True
    if body.clear_assignee:
        patch["assignee"] = None
    if body.clear_override:
        patch["override"] = None
    if not patch:
        raise HTTPException(status_code=400, detail="nothing to update")

    case = ns_storage.set_prep(case_id, user.id, patch)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    return {"ok": True, "matter": _matter_card(case, user.id)}


# ============================================================ the note sheet

_EMPTY_SHEET = {"chronology": [], "points": [], "provisions": [], "objections": [],
                "paperbook": [], "prayer": "", "ask": []}


def _sheet_payload(case: dict, user_id: str, day: str) -> dict:
    row = ns_storage.get_sheet(str(case["id"]), user_id, day)
    carried_from = None
    if not row:
        # the hearing may have been adjourned since the sheet was written
        prev = ns_storage.latest_for_case(str(case["id"]), user_id)
        if prev and prev.get("hearing_date") != day:
            row, carried_from = prev, prev.get("hearing_date")
    card = _matter_card(case, user_id)
    return {"matter": card, "hearing_date": day,
            "carried_from": carried_from,
            "exists": bool(row),
            "source": (row or {}).get("source"),
            "ocr_engine": (row or {}).get("ocr_engine"),
            "updated_at": (row or {}).get("updated_at"),
            "sheet": (row or {}).get("sheet_json") or dict(_EMPTY_SHEET)}


@router.get("/api/matters/{case_id}/notesheet", summary="The note sheet for one hearing")
def get_notesheet(case_id: str, date: Optional[str] = Query(None),
                  user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    day = _check_date(date or _iso_of(case.get("next_hearing_date")))
    return _sheet_payload(case, user.id, day)


class SheetBody(BaseModel):
    hearing_date: Optional[str] = None
    sheet: dict = Field(default_factory=dict)
    source: str = Field("junior", description="'junior', 'hand' or 'mine'")


@router.put("/api/matters/{case_id}/notesheet", summary="Save the note sheet")
def put_notesheet(case_id: str, body: SheetBody,
                  user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    day = _check_date(body.hearing_date or _iso_of(case.get("next_hearing_date")))
    # "mine" = the advocate typed or corrected it himself. Worth distinguishing
    # from "junior": once he has touched a sheet, the screen must stop captioning
    # it "drafted by your junior — edit before you rely on it".
    src = body.source if body.source in ("junior", "hand", "mine") else "junior"
    saved = ns_storage.save_sheet(case_id, user.id, day, body.sheet or {}, source=src)
    if not saved:
        raise HTTPException(status_code=500, detail="could not save the note sheet")
    return _sheet_payload(case, user.id, day)


@router.delete("/api/matters/{case_id}/notesheet", summary="Discard the note sheet for a date")
def delete_notesheet(case_id: str, date: Optional[str] = Query(None),
                     user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    day = _check_date(date or _iso_of(case.get("next_hearing_date")))
    ns_storage.delete_sheet(case_id, user.id, day)
    return {"ok": True}


# --- prepare a first draft from the matter's own file ------------------------

_LINES = {
    "bail": ["Custody already undergone; investigation complete — no purpose in further detention.",
             "No criminal antecedents on record.",
             "Evidence is documentary and in the prosecution's custody — no risk of tampering.",
             "Applicant has roots in the community; no flight risk."],
    "discharge": ["No prima facie material connecting the accused to the offence.",
                  "The charge-sheet documents, taken at their highest, do not make out the ingredients."],
    "reply": ["Deny the averments para-wise.",
              "The opposite party's own documents contradict the stand now taken.",
              "The relief sought is within the statutory framework."],
    "evidence": ["Take the witness through the documents exhibit-wise.",
                 "Confront on the contradiction between the pleading and the deposition.",
                 "Prove the documents formally before closing."],
    "arguments": ["Open with the settled position and the leading authority.",
                  "Meet the opposite party's principal objection first.",
                  "Close on the relief and the equities."],
    "review": ["Confirm the purpose from the court's board before the hearing."],
}


@router.post("/api/matters/{case_id}/notesheet/prepare",
             summary="Let the junior assemble a first note sheet from the file")
def prepare_notesheet(case_id: str, date: Optional[str] = Query(None),
                      user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    day = _check_date(date or _iso_of(case.get("next_hearing_date")))

    prep = ns_storage.get_prep(case)
    arts = _artifacts(case_id, user.id)
    cj = case.get("case_json") or {}

    # chronology comes from the court's own record — the hearing log
    try:
        logs = cases_storage.list_hearing_logs(case_id, user_id=user.id) or []
    except Exception:  # noqa: BLE001
        logs = []
    # Two sources overlap here, so the same hearing could be listed twice: a
    # diary import writes a hearing log AND sets case_json.last_listed_date, and
    # re-importing the same cause-list page writes the log again. A chronology
    # that repeats "22/4 listed (from diary page)" twice reads as a broken file,
    # so collapse on (date, event) and only fall back to last_listed_date when no
    # log already speaks for that day.
    chronology, seen, dated = [], set(), set()
    for l in logs:
        d = l.get("hearing_date")
        if not d:
            continue
        ev = (l.get("what_happened") or "").strip()
        key = (str(d), ev.casefold())
        if key in seen:
            continue
        seen.add(key)
        dated.add(str(d))
        chronology.append({"date": d, "event": ev or "Listed",
                           "source": "court record"})

    last = cj.get("last_listed_date")
    if last and str(last) not in dated:
        chronology.append({"date": last, "event": "Previous hearing",
                           "source": "from file"})

    # Most recent first — a chronology in arbitrary storage order is unreadable.
    chronology.sort(key=lambda r: str(_iso_of(r["date"]) or r["date"]), reverse=True)

    cat = rd.category(prep.get("purpose"))
    sheet = {
        "chronology": chronology,
        "points": [{"text": t, "authority": ""} for t in _LINES.get(cat, _LINES["review"])],
        "provisions": ([{"ref": prep.get("purpose_section") or "", "note": "as stated in the application",
                         "status": "ok"}] if prep.get("purpose_section") else []),
        "objections": [],
        "paperbook": [{"item": d["title"], "ref": f"{d.get('pages') or '—'} pp"}
                      for d in arts.get("documents", [])],
        "prayer": "",
        "ask": [],
        "generated": True,
        "note": "Drafted by your junior from this matter's file — read before you rely on it.",
    }
    ns_storage.save_sheet(case_id, user.id, day, sheet, source="junior")
    return _sheet_payload(case, user.id, day)


# --- read the handwritten sheet, then check it -------------------------------

def _analyse(lines: list[str], case: dict) -> list[dict]:
    """Deterministic checks over the pointers the lawyer wrote.

    Old-code → new-code concordance comes from the shipped statute map, so it is
    a lookup and never a guess. Anything we cannot confirm is reported as a
    question, not asserted.
    """
    findings: list[dict] = []
    joined = " \n ".join(lines)

    for m in re.finditer(r"\b(?:sec(?:tion)?\.?\s*)?(\d{1,3}[A-Z]?)\s*(IPC|CrPC|CPC|BNS|BNSS)\b",
                         joined, re.I):
        q = f"{m.group(2)} {m.group(1)}"
        try:
            hit = statute_map.lookup(q, limit=1)
        except Exception:  # noqa: BLE001
            continue
        res = (hit or {}).get("results") or []
        if not res:
            continue
        r0 = res[0]
        old, new = r0.get("old") or {}, r0.get("new") or {}
        wrote = m.group(2).lower()
        # Only flag when the lawyer actually wrote the OLD code. "483 BNSS" is
        # already current; the concordance would otherwise answer for CrPC 483
        # and send them to an unrelated section.
        if wrote in ("bns", "bnss"):
            continue
        if old.get("section") and new.get("section") and \
           wrote in str(old.get("code", "")).lower():
            findings.append({
                "kind": "section", "level": "warn",
                "text": (f"{old.get('code','').upper()} {old['section']} → "
                         f"{new.get('code','').upper()} {new['section']}"
                         f" ({new.get('title') or ''}). Your sheet uses the old code."),
            })

    if not re.search(r"\bpray|prayer|relief\b", joined, re.I):
        findings.append({"kind": "prayer", "level": "warn",
                         "text": "No prayer on the sheet — add what you are asking the court for."})

    # a shorthand like "cite Sanjay Chandra v CBI" — drop the instruction word so
    # the case name we echo back is the case name, not the lawyer's note to self
    cited = re.findall(r"\b([A-Z][A-Za-z.']+(?:\s+[A-Z][A-Za-z.']+)*)\s+v\.?\s+", joined)
    _lead = re.compile(r"^(?:cite|see|refer|ref|read|rely\s+on)\s+", re.I)
    for name in cited[:5]:
        name = _lead.sub("", name).strip()
        if not name:
            continue
        findings.append({"kind": "citation", "level": "check",
                         "text": f"“{name} v. …” — verify the citation and holding before relying on it."})

    if not findings:
        findings.append({"kind": "ok", "level": "ok",
                         "text": "Nothing to flag — sections and prayer look consistent."})
    return findings


_SHEET_PROMPT = (
    "This is a photo of an Indian advocate's handwritten hearing note sheet. "
    "Transcribe it as a JSON object: {\"lines\": [\"…\", \"…\"]} — one entry per "
    "bullet/pointer, in the order written, verbatim. Keep Hindi in Devanagari. "
    "Do not translate, do not summarise, do not add anything that is not on the page.")

_SHEET_TEXT_PROMPT = (
    "Transcribe this handwritten page verbatim, one pointer per line. Keep Hindi in "
    "Devanagari. Do not translate or summarise.")


def _lines_from_text(text: str) -> list[str]:
    """Flat OCR text → pointers. Strips bullet/numbering marks the lawyer wrote."""
    out: list[str] = []
    for raw in (text or "").splitlines():
        s = re.sub(r"^\s*(?:[-•*–—]|\(?\d{1,2}[.)]|\(?[ivx]{1,4}[.)])\s*", "", raw).strip()
        if len(s) > 2 and not re.fullmatch(r"[-=_—\s|]+", s):
            out.append(s)
    return out


def _read_sheet_ocr(data: bytes, filename: str, mime: str) -> tuple[list[str], str]:
    """Handwriting → pointers, best engine first — the same precedence the diary
    import uses (headnote/api/cases.py::_run_diary_ocr), so there is one OCR
    policy in the codebase rather than two:

      1) Gemini Flash vision — reads the page spatially and returns the pointers
         in one call. Best for handwriting, which is what a note sheet is.
      2) Sarvam Document Intelligence — Indic-native, but returns flat Markdown,
         so the line structure has to be recovered afterwards.
      3) Groq Llama vision — last resort, always available.

    Degrades rather than failing: whichever key is configured, the lawyer gets a
    reading. Only if none is configured do we say so plainly.
    """
    from headnote.integrations import gemini, sarvam

    if gemini.enabled():
        try:
            out = gemini.generate_json(_SHEET_PROMPT, image=data, mime=mime) or {}
            lines = [str(x).strip() for x in (out.get("lines") or []) if str(x).strip()]
            if lines:
                return lines, "gemini"
        except Exception as e:  # noqa: BLE001 — degrade to Sarvam/Groq
            log.warning("Gemini note-sheet OCR failed, falling back: %s", e)

    if sarvam.enabled():
        try:
            md = sarvam.digitize_to_text(data, filename=filename, mime=mime)
            lines = _lines_from_text(md)
            if lines:
                return lines, "sarvam"
        except Exception as e:  # noqa: BLE001 — degrade to Groq
            log.warning("Sarvam note-sheet OCR failed, falling back to Groq: %s", e)

    try:
        from headnote.drafter.ocr import ocr_text_pages, _rasterize_pdfs
        pages = _rasterize_pdfs([(data, mime)]) if mime == "application/pdf" else [(data, mime)]
        lines = _lines_from_text(ocr_text_pages(pages, prompt=_SHEET_TEXT_PROMPT))
        if lines:
            return lines, "groq"
    except Exception as e:  # noqa: BLE001
        log.warning("Groq note-sheet OCR failed: %s", e)

    if not (gemini.enabled() or sarvam.enabled()):
        raise HTTPException(
            status_code=503,
            detail="Handwriting reading isn't configured on this server. "
                   "Set GEMINI_API_KEY (best for handwriting) or SARVAM_API_KEY.")
    raise HTTPException(status_code=422,
                        detail="Couldn't read any pointers from that photo — try a clearer, "
                               "straight-on shot of the page.")


@router.post("/api/matters/{case_id}/notesheet/scan",
             summary="Read a photo of the handwritten note sheet and check it")
async def scan_notesheet(case_id: str, file: UploadFile = File(...),
                         date: Optional[str] = Query(None),
                         user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    day = _check_date(date or _iso_of(case.get("next_hearing_date")))

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    mime = (file.content_type or "image/jpeg").split(";")[0].strip()

    lines, engine = await asyncio.to_thread(
        _read_sheet_ocr, data, file.filename or "sheet.jpg", mime)

    # NOTHING is stored here — the lawyer reviews first, then PUTs the sheet.
    return {"hearing_date": day, "engine": engine,
            "lines": [{"text": l} for l in lines],
            "analysis": _analyse(lines, case),
            "note": "Nothing is saved until you check these and save."}


# ============================================================ court updates
#
# The CNR adapter already returns stage, purpose, the hearing history and the
# order list (with links). Syncing = fetch it again, diff it, and tell the lawyer
# what moved. This is what makes the dashboard live rather than a filing cabinet.

def _case_json(case: dict) -> dict:
    """Kept as a thin alias — several routes below still call it."""
    return courtsync.case_json_of(case)


def _sync_one(case: dict, user_id: str) -> dict:
    """One matter, re-read from the court. The implementation lives in
    courtsync.sync_case so the per-file button and the daily sweep can never
    drift apart."""
    return courtsync.sync_case(case, user_id)


@router.post("/api/matters/{case_id}/sync",
             summary="Ask the court what changed on this matter")
def sync_matter(case_id: str, user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    res = _sync_one(case, user.id)
    fresh = cases_storage.get_case(case_id, user_id=user.id)
    return {**res, "matter": _matter_card(fresh, user.id) if fresh else None}


@router.post("/api/matters/sync-all",
             summary="Sync every matter listed in the next fortnight")
def sync_all(user: CurrentUser = Depends(require_beta)) -> dict:
    """Bounded on purpose: each sync is a paid vendor call, so we only refresh
    matters that are actually coming up, newest first, capped."""
    today = _today_iso()
    horizon = (datetime.fromisoformat(today) + timedelta(days=14)).date().isoformat()
    cases = cases_storage.list_cases(user_id=user.id, limit=500) or []
    due = [c for c in cases
           if ecourts_client.is_valid_cnr((c.get("cnr") or ""))
           and (_iso_of(c.get("next_hearing_date")) or "") <= horizon]
    due.sort(key=lambda c: _iso_of(c.get("next_hearing_date")) or "9999")
    done, changed = [], 0
    for c in due[:25]:
        r = _sync_one(c, user.id)
        changed += len(r.get("updates") or [])
        done.append(r)
    return {"synced": len(done), "updates": changed, "results": done,
            "skipped": max(0, len(due) - 25)}


@router.get("/api/updates", summary="Everything the courts changed, unread first")
def updates(user: CurrentUser = Depends(require_beta)) -> dict:
    out = []
    for c in cases_storage.list_cases(user_id=user.id, limit=500) or []:
        cj = _case_json(c)
        for u in courtsync.unseen(cj):
            out.append({**u, "case_id": c["id"], "party": _party(c),
                        "court_name": c.get("court_name"),
                        "case_number": c.get("case_number"),
                        "case_year": c.get("case_year")})
    out.sort(key=lambda u: str(u.get("at") or ""), reverse=True)
    return {"count": len(out), "updates": out[:50]}


@router.post("/api/matters/{case_id}/updates/read", summary="Mark this matter's updates seen")
def mark_updates_read(case_id: str, user: CurrentUser = Depends(require_beta)) -> dict:
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    cj = _case_json(case)
    ups = [{**u, "seen": True} for u in (cj.get("updates") or []) if isinstance(u, dict)]
    cj["updates"] = ups
    payload = dict(cj)
    payload["cnr"] = case.get("cnr")
    cases_storage.replace_case_identity(case_id, user_id=user.id, case=payload)
    return {"ok": True, "cleared": len(ups)}


class SaveOrderBody(BaseModel):
    link: str = Field(..., description="the order's URL from the court listing")
    date: Optional[str] = Field(None, description="order date, as the court states it")
    order_type: Optional[str] = Field(None, description="e.g. Interim Order / Judgment")


@router.post("/api/matters/{case_id}/orders/save",
             summary="Download a court order and file it in this matter's folder")
async def save_order(case_id: str, body: SaveOrderBody,
                     user: CurrentUser = Depends(require_beta)) -> dict:
    """Fetch the order PDF the court published and store it in the Document Vault
    against this matter — so it is in the case folder, searchable, beside the rest
    of the file. Reuses the vault, so the reader and Legal Lens work on it too."""
    case = cases_storage.get_case(case_id, user_id=user.id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    if not str(body.link or "").lower().startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="that doesn't look like an order link")

    import httpx
    try:
        async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as cl:
            r = await cl.get(body.link)
            r.raise_for_status()
            data, ctype = r.content, (r.headers.get("content-type") or "").split(";")[0].strip()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not download the order: {e}")
    if not data:
        raise HTTPException(status_code=502, detail="the court returned an empty file")

    label = f"{body.order_type or 'Order'} dated {body.date or 'unknown'}"

    # Read the order so it is searchable in the vault. Best-effort: if OCR is
    # unavailable the order is still filed — losing the text is a nuisance,
    # losing the order is not acceptable.
    text, pages = "", []
    try:
        from headnote.drafter.ocr import ocr_text_pages, _rasterize_pdfs
        pages = _rasterize_pdfs([(data, ctype)]) if "pdf" in (ctype or "") else [(data, ctype)]
        text = await asyncio.to_thread(ocr_text_pages, pages) or ""
    except Exception as e:  # noqa: BLE001
        log.warning("order OCR skipped for %s: %s", case_id, e)

    doc = docs_storage.add_document(
        user_id=user.id, title=label, full_text=text,
        doc_type="order", original_filename=(body.link.rsplit("/", 1)[-1] or "order.pdf"),
        mime=ctype or "application/pdf", case_id=case_id, pages=pages or None,
        metadata={"source": "ecourts", "order_date": body.date,
                  "order_type": body.order_type, "link": body.link})
    if not doc:
        raise HTTPException(status_code=500, detail="could not save the order")
    return {"ok": True, "document": {"id": doc.get("id"), "title": doc.get("title")},
            "ocr": bool(text)}
