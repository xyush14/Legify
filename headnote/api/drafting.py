"""The API behind the /draft workspace.

    GET  /api/drafting/catalog            the documents, grouped (open)
    POST /api/drafting/recognise          brief → which document, live as he types (open, ~ms)
    POST /api/drafting/intake             brief (+ his pick) → fields filled from the brief + the page (open)
    POST /api/drafting/render             fields → the page + progress + the junior's note (open)
    POST /api/drafting/enrich             a model reads the brief for what is still empty — grounded or dropped
    POST /api/drafting/read-document      an FIR / order photo or PDF → its text, to join the brief
    GET  /api/drafting/matter/{id}        a matter from his diary, as a brief
    POST /api/drafting/save               create / update the draft (autosave)
    GET  /api/drafting/draft/{id}         reopen one
    POST /api/drafting/docx               the Word file, in his format or the layout he picked

Why a new prefix: `/api/draft` carries `GET /{draft_id}`, which silently swallows
any GET declared below it (that bug has bitten this router twice). A separate
prefix removes the trap instead of adding a third comment warning about it.

Recognise / intake / render are deterministic Python — no model, no network, no
storage — so they stay open: the page works (and can be checked) before sign-in,
and a slow model can never make the paper blank again. Everything that spends
money, touches his data or uses his format requires a signed-in user.
"""
from __future__ import annotations

import logging
import re
import time
from collections import defaultdict, deque
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from pydantic import BaseModel, Field

from headnote.drafter import intake as IN
from headnote.drafter import storage
from headnote.drafter import template_adapter as TA
from headnote.drafter import workspace as WS
from headnote.entitlements import CurrentUser
from headnote.entitlements.auth import get_current_user, optional_user

log = logging.getLogger("headnote.api.drafting")
router = APIRouter(prefix="/api/drafting", tags=["drafting"])

_MAX_BRIEF = 20_000


def _tid_or_404(tid: str) -> str:
    if not TA.is_canonical(tid or ""):
        raise HTTPException(status_code=404, detail=f"no reviewed template '{tid}'")
    return tid


def _lang(lang: Optional[str], brief: str = "") -> str:
    return lang if lang in ("hi", "en") else IN.choose_lang(brief)


@router.get("/catalog")
def catalog() -> dict:
    return {"groups": WS.catalog()}


class BriefBody(BaseModel):
    brief: str = ""


@router.post("/recognise")
def recognise(body: BriefBody) -> dict:
    brief = (body.brief or "")[:_MAX_BRIEF]
    rec = IN.recognise(brief)
    return {"recognised": rec, "title": WS.title(rec["tid"]) if rec["tid"] else None,
            "alternatives": [WS.title(t) for t in rec["alternatives"]], "lang": IN.choose_lang(brief)}


class IntakeBody(BaseModel):
    brief: str = ""
    tid: Optional[str] = Field(None, description="his pick — beats recognition")
    lang: Optional[str] = Field(None, description="'hi' | 'en'; omitted = follow the brief")
    fields: dict = Field(default_factory=dict, description="values he has already typed — never overwritten")
    locked: List[str] = Field(default_factory=list, description="keys he edited by hand")


def _merge(extracted: dict, current: dict, locked: list[str]) -> tuple[dict, list[str]]:
    """Brief values go only into fields he has not touched."""
    out = dict(current or {})
    added = []
    for k, v in (extracted or {}).items():
        if k in locked:
            continue
        if WS._is_empty(out.get(k)) or out.get(k) is False:
            out[k] = v
            added.append(k)
    return out, added


def _payload(tid: str, fields: dict, lang: str, evidence: dict) -> dict:
    fields, evidence = WS.derive(tid, fields, evidence, lang)
    try:
        pv = WS.preview(tid, fields, lang)
    except Exception as e:  # a malformed value must never blank the page with a 500
        log.exception("preview failed for %s", tid)
        raise HTTPException(status_code=422, detail=f"could not render this draft ({type(e).__name__})")
    return {"tid": tid, "lang": lang, "fields": fields, "evidence": evidence,
            "schema": WS.schema(tid), "html": pv["html"],
            "progress": {k: pv[k] for k in ("required", "filled", "missing")},
            "checks": WS.checks(tid, fields, lang, evidence)}


@router.post("/intake")
def intake(body: IntakeBody) -> dict:
    brief = (body.brief or "")[:_MAX_BRIEF]
    res = IN.intake(brief, tid=body.tid, lang=body.lang or "auto")
    rec = res["recognised"]
    tid = res["tid"]
    out = {"recognised": rec, "title": WS.title(tid) if tid else None,
           "alternatives": [WS.title(t) for t in rec["alternatives"]]}
    if not tid:
        return {**out, "tid": None, "lang": res["lang"]}
    fields, added = _merge(res["fields"], WS.without_derived(tid, body.fields), body.locked)
    evidence = {k: res["evidence"][k] for k in added if k in res["evidence"]}
    return {**out, **_payload(tid, fields, res["lang"], evidence), "added": added}


class RenderBody(BaseModel):
    tid: str
    fields: dict = Field(default_factory=dict)
    lang: str = "hi"
    evidence: dict = Field(default_factory=dict)


@router.post("/render")
def render(body: RenderBody) -> dict:
    tid = _tid_or_404(body.tid)
    return _payload(tid, body.fields or {}, _lang(body.lang), body.evidence or {})


# ---- AI top-up: per-user rate limit, because this is the one call that costs money
_ENRICH_LOG: dict[str, deque] = defaultdict(deque)
_ENRICH_PER_HOUR = 40


class EnrichBody(BaseModel):
    brief: str
    tid: str
    lang: str = "hi"
    fields: dict = Field(default_factory=dict)


@router.post("/enrich")
async def enrich(body: EnrichBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    tid = _tid_or_404(body.tid)
    q = _ENRICH_LOG[user.id]
    now = time.time()
    while q and now - q[0] > 3600:
        q.popleft()
    if len(q) >= _ENRICH_PER_HOUR:
        return {"fields": {}, "evidence": {}, "dropped": [], "model": None, "skipped": "rate"}
    q.append(now)
    try:
        res = await run_in_threadpool(WS.enrich, (body.brief or "")[:_MAX_BRIEF], tid, _lang(body.lang), body.fields)
    except Exception as e:
        # the page is already complete without this — say so, don't fail it
        log.warning("enrich unavailable: %s", e)
        return {"fields": {}, "evidence": {}, "dropped": [], "model": None, "skipped": "unavailable"}
    return res


_DOC_MAX_FILES = 6
_DOC_MAX_BYTES = 20 * 1024 * 1024


@router.post("/read-document")
async def read_document(files: List[UploadFile] = File(...),
                        user: CurrentUser = Depends(get_current_user)) -> dict:
    from headnote.drafter import office
    from headnote.drafter.ocr import ocr_text_pages

    if not files:
        raise HTTPException(status_code=400, detail="attach a photo, PDF or Word file")
    if len(files) > _DOC_MAX_FILES:
        raise HTTPException(status_code=400, detail=f"at most {_DOC_MAX_FILES} pages at a time")
    entries = [(await f.read(), f.content_type or "", f.filename or "") for f in files]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_DOC_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    try:
        text = await run_in_threadpool(ocr_text_pages, pages, office_text=office_text)
    except Exception as e:
        log.warning("read-document OCR failed: %s", e)
        raise HTTPException(status_code=502, detail="Could not read that document right now. "
                                                    "Your file is fine — try again, or type the details.")
    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="No readable text was found in that file.")
    return {"text": text[:_MAX_BRIEF], "pages": len(files)}


@router.get("/matter/{matter_id}")
def matter(matter_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    from headnote.cases import storage as cases_storage
    row = cases_storage.get_case(matter_id, user_id=user.id)
    if not row:
        raise HTTPException(status_code=404, detail="matter not found")
    brief = WS.matter_brief(row)
    title = row.get("case_title") or (row.get("case_json") or {}).get("case_title") or ""
    return {"matter_id": matter_id, "title": title, "brief": brief}


class SaveBody(BaseModel):
    draft_id: Optional[str] = None
    tid: str
    lang: str = "hi"
    fields: dict = Field(default_factory=dict)
    evidence: dict = Field(default_factory=dict)
    brief: str = ""
    matter_id: Optional[str] = None
    layout_id: Optional[str] = None


def _draft_title(tid: str, fields: dict) -> str:
    t = WS.title(tid)["name"]
    who = next((str(v) for k, v in (fields or {}).items()
                if re.match(r"^(applicant|complainant|petitioner|plaintiff|client|appellant|revisionist|aggrieved|deponent|claimant)_name$", k)
                and isinstance(v, str) and v.strip()), "")
    return f"{t} — {who}" if who else t


@router.post("/save")
def save(body: SaveBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    tid = _tid_or_404(body.tid)
    answers = {"workspace": 2, "tid": tid, "lang": _lang(body.lang), "fields": body.fields or {},
               "evidence": body.evidence or {}, "brief": (body.brief or "")[:_MAX_BRIEF],
               "matter_id": body.matter_id, "layout_id": body.layout_id}
    title = _draft_title(tid, body.fields)
    if body.draft_id:
        d = storage.get_draft(body.draft_id)
        if d is None or (d.user_id and d.user_id != user.id):
            raise HTTPException(status_code=404, detail="draft not found")
        d = storage.update_draft(body.draft_id, answers=answers, lang=answers["lang"], title=title)
        if d is None:
            raise HTTPException(status_code=503, detail="Could not save right now — your work is still on this screen.")
        if body.matter_id and d.case_id != body.matter_id:
            try:
                storage.set_draft_case(d.id, case_id=body.matter_id, user_id=user.id)
            except Exception:
                log.warning("could not bind draft %s to matter", d.id, exc_info=True)
        return {"draft_id": d.id, "updated_at": d.updated_at, "title": title}
    d = storage.create_draft(story_id=tid, template_version=2, user_id=user.id, lang=answers["lang"],
                             answers=answers, title=title, case_id=body.matter_id)
    return {"draft_id": d.id, "updated_at": d.updated_at, "title": title}


@router.get("/draft/{draft_id}")
def load(draft_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    d = storage.get_draft(draft_id)
    if d is None or (d.user_id and d.user_id != user.id):
        raise HTTPException(status_code=404, detail="draft not found")
    a = d.answers or {}
    if a.get("workspace") != 2 or not TA.is_canonical(a.get("tid") or ""):
        # an older draft from the prompt editor — it opens where it was made
        return {"draft_id": d.id, "legacy": True, "open": f"/draft/editor/{d.id}"}
    tid, lang = a["tid"], _lang(a.get("lang"))
    return {"draft_id": d.id, "legacy": False, "brief": a.get("brief") or "", "matter_id": a.get("matter_id") or d.case_id,
            "layout_id": a.get("layout_id"), "title": d.title, "updated_at": d.updated_at,
            **_payload(tid, a.get("fields") or {}, lang, a.get("evidence") or {})}


class DocxBody(BaseModel):
    tid: str
    lang: str = "hi"
    fields: dict = Field(default_factory=dict)
    layout_id: Optional[str] = None


@router.post("/docx")
def docx(body: DocxBody, user: CurrentUser = Depends(get_current_user)) -> Response:
    """The Word file. Same pipeline as the reviewed fields screen: the canonical
    document → role-tagged blocks → HIS captured layout, or the preset he picked.
    Empty particulars print as filing blanks, never as the field's own name."""
    from headnote.drafter.api import TemplateDocxBody, template_docx
    tid = _tid_or_404(body.tid)
    lang = _lang(body.lang)
    return template_docx(TemplateDocxBody(doc_type=tid, lang=lang,
                                          fields=WS.export_fields(tid, body.fields or {}),
                                          layout_id=body.layout_id), user)


class PrintBody(BaseModel):
    tid: str
    lang: str = "hi"
    fields: dict = Field(default_factory=dict)


@router.post("/print-html")
def print_html(body: PrintBody, user: Optional[CurrentUser] = Depends(optional_user)) -> dict:
    """The page exactly as it prints — filing blanks instead of on-screen chips."""
    tid = _tid_or_404(body.tid)
    return {"html": TA.document(tid, WS.export_fields(tid, body.fields or {}), _lang(body.lang))}
