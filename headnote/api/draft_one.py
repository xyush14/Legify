"""The one door into drafting — the API behind the V2 `/draft` screen.

    POST /api/draft/one         brief + attachments + matter → the draft (NDJSON)
    POST /api/draft/skeleton    the instant court skeleton in HIS page (free)
    POST /api/draft/questions   the at-most-one round of questions (free)
    POST /api/draft/preflight   the junior's note for any draft text (free)

Why one endpoint
----------------
`/from-prompt` and `/from-document` being separate is the reason the frontend grew
separate flows — a typed door and an upload door, each with its own form and its
own output quality. `/one` accepts everything the screen can hold: the brief, any
number of attachments EACH tagged `facts` or `format`, an optional matter id, the
language, and the answers to the one round of questions. The old endpoints are
untouched; other pages still call them.

The two-source rule
-------------------
`roles[i]` says what attachment `i` is for, in the advocate's own words on screen
("Facts from this" / "Format from this"), and it DEFAULTS TO FACTS. A document
becomes a format source only when he says so. Facts sources are OCR'd and folded
into the brief; a format source travels separately as the mirror reference, and
its own facts and citations never enter the draft. An attached reference beats the
saved Draft DNA, which is what an advocate means when he attaches one.

Streaming
---------
`/one` answers NDJSON so the paper is never blank:

    {"type":"skeleton", page, roles, font, blocks, format, doc_type}   immediately
    {"type":"result",  …the unified draft dict…, "preflight": {…}}     when written
    {"type":"error","message":…}                                       pipeline down

The skeleton event is pure Python — no model, no quota, no network — so it lands in
milliseconds. Today the advocate stares at nothing for 5–15 seconds.

Metering
--------
ONE draft credit per COMPLETED draft. Not per utterance: once voice is the primary
way in, charging per utterance would make a rambling brief cost five credits, which
is severe to the point of being a reason not to speak. Skeleton, questions and
preflight are free — they are deterministic Python and cost us nothing.

Gating
------
All of these are V2-only and reachable only from `/draft`, so they use
`require_beta` (403 {"code":"not_in_beta"}) rather than plain `get_current_user`.
Nothing on the live `/app` surface calls them.
"""
from __future__ import annotations

import json
import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from headnote.drafter import office, onedoor, preflight
from headnote.entitlements import CurrentUser, check_and_record, require_beta

log = logging.getLogger("headnote.api.draft_one")
router = APIRouter(prefix="/api/draft", tags=["drafter"])

_MAX_FILES = 8
_MAX_BYTES = 20 * 1024 * 1024


class _NoCharge(Exception):
    """Internal sentinel: close the metering context WITHOUT charging a credit."""


# ===========================================================================
# free, deterministic helpers — the screen calls these before it spends anything
# ===========================================================================

class BriefBody(BaseModel):
    brief: str = Field("", description="what the advocate typed or dictated")
    lang: str = Field("auto", description="'auto' | 'hi' | 'en' | 'mr' | 'gu' | …")
    answers: dict = Field(default_factory=dict, description="answers to the one round")
    matter_id: Optional[str] = None


@router.post("/skeleton", summary="The instant court skeleton, in the advocate's own page (free)")
def draft_skeleton(body: BriefBody, user: CurrentUser = Depends(require_beta)) -> dict:
    """The paper before the model has written a word: the canonical skeleton as
    role-tagged blocks, plus his captured page geometry, per-role formats and font,
    so the browser can draw HIS page to scale. Deterministic — no LLM, no quota."""
    return onedoor.instant_skeleton(body.brief, lang=body.lang, user_id=user.id,
                                    answers=body.answers)


@router.post("/questions", summary="The at-most-one round of questions before drafting (free)")
def draft_questions(body: BriefBody, user: CurrentUser = Depends(require_beta)) -> dict:
    """Only what genuinely changes the section, the cause title or the grounds, and
    only when the brief does not already answer it. Always skippable."""
    return onedoor.questions_for(body.brief, lang=body.lang, answers=body.answers)


class PreflightBody(BaseModel):
    html: str = Field("", description="the draft as HTML or plain text")
    doc_type: str = Field("other_criminal")
    brief: str = Field("", description="what he gave us — where the FIR date usually is")
    warnings: List[str] = Field(default_factory=list)
    ungrounded: List[str] = Field(default_factory=list)
    cite_at_hearing: List[str] = Field(default_factory=list)
    companions: List[str] = Field(default_factory=list)


@router.post("/preflight", summary="The junior's note — deterministic checks on a draft (free)")
def draft_preflight(body: PreflightBody, user: CurrentUser = Depends(require_beta)) -> dict:
    """Re-run the checks after an edit or a Reform, without redrafting anything.
    Pure Python: no model, no cost, no latency."""
    return preflight.review({
        "html": body.html, "doc_type": body.doc_type,
        "warnings": body.warnings, "ungrounded": body.ungrounded,
        "cite_at_hearing": body.cite_at_hearing, "companions": body.companions,
    }, brief=body.brief)


# ===========================================================================
# the one door
# ===========================================================================

def _parse_roles(raw: Optional[str], n: int) -> list[str]:
    """`roles` is a JSON array aligned to `files`, each "facts" | "format".

    Anything we cannot read becomes "facts". That default is a safety property, not
    a convenience: treating an unknown document as a FORMAT source would let its
    text govern a filed draft's shape without the advocate ever having said so."""
    out: list[str] = []
    try:
        parsed = json.loads(raw) if raw else []
        if isinstance(parsed, list):
            out = ["format" if str(x).strip().lower() in ("format", "reference", "style")
                   else "facts" for x in parsed]
    except Exception:
        out = []
    while len(out) < n:
        out.append("facts")
    return out[:n]


async def _read_uploads(uploads: List[UploadFile], roles: list[str]) -> tuple[list, list, list[str]]:
    """→ (facts_entries, format_entries, names). Entries are the (bytes, mime, name)
    tuples `office.collect_uploads` takes."""
    facts, fmt, names = [], [], []
    for i, up in enumerate(uploads):
        data = await up.read()
        if not data:
            continue
        entry = (data, up.content_type or "", up.filename or f"file{i + 1}")
        names.append(up.filename or f"file{i + 1}")
        (fmt if roles[i] == "format" else facts).append(entry)
    return facts, fmt, names


def _ocr(entries: list) -> str:
    """OCR one bucket of attachments → text. Blocking on purpose: every caller
    hands this to a threadpool, because OCR + LLM on the event loop is what once
    made multi-page uploads fail as 'Failed to fetch'."""
    if not entries:
        return ""
    from headnote.drafter.ocr import ocr_text_pages
    pages, office_text = office.collect_uploads(entries, max_bytes=_MAX_BYTES)
    try:
        return (ocr_text_pages(pages, office_text=office_text) or "").strip()
    except Exception as e:  # noqa: BLE001 — degrade to whatever text we do have
        log.warning("one-door OCR degraded: %s", e)
        return (office_text or "").strip()


@router.post("/one", summary="One door: brief + attachments + matter → a court-ready draft (NDJSON)")
async def draft_one(
    brief: str = Form("", description="what the advocate typed or dictated"),
    lang: str = Form("auto"),
    matter_id: Optional[str] = Form(None),
    answers: str = Form("", description="JSON object of answers to the one round"),
    roles: str = Form("", description='JSON array aligned to files: "facts" | "format"'),
    files: Optional[List[UploadFile]] = File(None),
    user: CurrentUser = Depends(require_beta),
):
    """The single drafting endpoint the `/draft` screen uses.

    Emits NDJSON: the free deterministic skeleton first (so the paper is never
    blank), then the finished draft with its junior's note. One draft credit is
    charged for the completed draft — never per utterance.

    A draft with a matter attached is SAVED to that matter, so it lands in the case
    folder rather than in a pile of loose documents."""
    uploads = [u for u in (files or []) if u is not None]
    if len(uploads) > _MAX_FILES:
        return JSONResponse({"ok": False, "error": f"too many files ({len(uploads)}); max {_MAX_FILES}"},
                            status_code=400)
    try:
        ans = json.loads(answers) if answers else {}
        if not isinstance(ans, dict):
            ans = {}
    except Exception:
        ans = {}

    role_list = _parse_roles(roles, len(uploads))
    fact_entries, fmt_entries, names = await _read_uploads(uploads, role_list)
    if not (brief or "").strip() and not fact_entries and not fmt_entries:
        return JSONResponse({"ok": False, "error": "describe the matter or attach a paper"},
                            status_code=400)

    resolved_lang = onedoor.detect_lang(brief, lang)
    skeleton = onedoor.instant_skeleton(brief, lang=lang, user_id=user.id, answers=ans)

    # Gate BEFORE the 200 stream opens: a half-open stream cannot carry a 402/429,
    # so quota and entitlement failures must surface as a clean status here.
    _cm = check_and_record(user.id, "draft", endpoint="draft_one", email=user.email)
    _record = _cm.__enter__()

    def _work() -> dict:
        from headnote.drafter.api import _persist_editor_draft
        from headnote.drafter.from_prompt import draft_from_prompt

        facts_text = _ocr(fact_entries)
        ref_text = _ocr(fmt_entries)
        matter = onedoor.merge_brief(
            brief,
            facts_texts=[facts_text] if facts_text else [],
            matter_context=onedoor.matter_context(matter_id, user.id),
            answers=ans, lang=resolved_lang)
        if not matter.strip() and not ref_text.strip():
            return {"ok": False, "error":
                    "Could not read the attachment and nothing was described — say what you "
                    "need, or attach a clearer photo."}

        result = draft_from_prompt(matter, lang, reference_text=ref_text, user_id=user.id)
        if isinstance(result, dict) and result.get("ok"):
            if fmt_entries and ref_text:
                result["format_source"] = names[-1] if names else "your attached reference"
            elif not ref_text and fmt_entries:
                result.setdefault("warnings", []).append(
                    "Could not read the reference you marked 'Format from this' — drafted in "
                    "your saved format instead.")
            if fact_entries and not facts_text:
                result.setdefault("warnings", []).append(
                    "Could not read the attached papers — the draft is from what you described. "
                    "Try a clearer photo.")
            # `_persist_editor_draft` POPS `blocks` (they are for the server-side
            # .docx render only). Canvas has to draw from the SAME blocks, or the
            # screen and the Word file would be two different documents — so a
            # reference is kept and handed over under its own key. Block text is
            # raw, so the HTML preview's grounding markers and citation flags
            # still cannot reach the paper.
            blocks = result.get("blocks")
            result = _persist_editor_draft(result, user_id=user.id, case_id=matter_id)
            if blocks:
                result["canvas_blocks"] = blocks
            result["preflight"] = preflight.review(result, brief=matter)
            result["matter_id"] = matter_id
        return result

    async def gen():
        yield json.dumps({"type": "skeleton", **skeleton}, ensure_ascii=False) + "\n"
        charged = False
        try:
            result = await run_in_threadpool(_work)
            if isinstance(result, dict) and result.get("ok"):
                _record(model=str(result.get("mode") or "authored"))
                charged = True
            yield json.dumps({"type": "result", **(result or {})}, ensure_ascii=False) + "\n"
        except Exception as exc:  # noqa: BLE001
            log.exception("one-door drafting failed")
            yield json.dumps({"type": "error", "message":
                              "Drafting hit a temporary hiccup — your brief is safe, press "
                              f"Draft it again. ({type(exc).__name__})"}) + "\n"
        finally:
            # The meter increments on the context manager's CLEAN exit, so a draft
            # that never arrived must not exit cleanly: closing it with an exception
            # skips the increment. Charging for a failed draft is the bug that made
            # a broken stream cost a lawyer a credit (docs/RESEARCH_AUDIT.md P0).
            # __exit__ returns False here rather than raising, because the thrown
            # exception propagates out of the generator unchanged.
            try:
                if charged:
                    _cm.__exit__(None, None, None)
                else:
                    _cm.__exit__(_NoCharge, _NoCharge("draft not produced"), None)
            except Exception:
                log.warning("one-door meter close failed", exc_info=True)

    return StreamingResponse(gen(), media_type="application/x-ndjson",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
