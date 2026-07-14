"""
FastAPI routes for the drafting engine.

Mounted under /api/draft/* by the main app. Auth model is light for v0:
- Anonymous drafts allowed (user_id=null) — useful while we build the
  Supabase bearer-validation middleware. Production should require a
  valid Supabase JWT on every write.
- Drafts are NOT user-scoped on read in v0 (anyone with the draft_id can
  read it). Treat draft_ids as capability tokens until we wire ACL.

This file is small on purpose. Heavy logic (template rendering,
transliteration, OCR) lives in sibling modules and is called from here.
"""

from __future__ import annotations

import json
import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field

from headnote.drafter import office, storage, stories
from headnote.entitlements import (
    CurrentUser,
    check_and_record,
    get_current_user,
)
from headnote.entitlements.auth import optional_user


router = APIRouter(prefix="/api/draft", tags=["drafter"])


# ----------------------------------------------------------- request models

class StartDraftBody(BaseModel):
    story_id: str = Field(..., description="One of stories.STORIES keys, e.g. 'friendly_cash_loan'")
    lang: str = Field("en", description="'en' or 'hi'")
    user_id: Optional[str] = Field(None, description="Supabase user.id; null = anon")
    title: Optional[str] = Field(None, description="Short label for the FE drafts list")
    answers: Optional[dict] = Field(None, description="Optional initial answers")


class UpdateDraftBody(BaseModel):
    answers: Optional[dict] = None
    lang: Optional[str] = None
    title: Optional[str] = None


class TranslateFieldsBody(BaseModel):
    fields: dict = Field(..., description="Dict of prose field key→value to translate")
    target: Literal["hi", "en"] = Field("hi", description="Target language")


# ----------------------------------------------------------- routes

@router.get("/stories", summary="List all draft story types (for FE tile grid)")
def list_stories(lang: str = "en"):
    return {"stories": stories.list_stories(lang=lang)}


@router.get("/story/{story_id}", summary="Detailed schema for one story (sections + readiness)")
def get_story_schema(story_id: str):
    s = stories.get_story(story_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown story_id={story_id!r}")
    return {
        "id": s.id,
        "label": s.label,
        "sub": s.sub,
        "icon": s.icon,
        "ready": s.ready,
        "template_version": s.template_version,
        "sections": [
            {
                "id": sec.id,
                "eyebrow": sec.eyebrow,
                "title": sec.title,
                "sub": sec.sub,
                "type": sec.type,
                "scan": sec.scan,
            }
            for sec in s.sections
        ],
    }


@router.post("/start", summary="Begin a new draft (creates a drafts row)")
def start_draft(
    body: StartDraftBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Gated: `draft` feature. Counts against quota; 402 if exhausted.

    `body.user_id` is ignored — the authenticated user is used instead so
    drafts can never be created under another user's id.
    """
    s = stories.get_story(body.story_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown story_id={body.story_id!r}")

    with check_and_record(user.id, "draft", endpoint="draft_start", email=user.email) as _record:
        # v0: we allow start even on not-ready stories so the FE can save
        # progress before the template module is finalised. The /render endpoint
        # will still return a 'coming soon' message until ready=True.
        draft = storage.create_draft(
            story_id=body.story_id,
            template_version=s.template_version,
            user_id=user.id,
            lang=body.lang,
            answers=body.answers,
            title=body.title,
        )
        _record(cost_paise=0, model=None)  # drafts are templated, no LLM cost yet
        return draft.to_dict()


# Note: these routes must be declared BEFORE `/{draft_id}` so FastAPI's
# path matcher doesn't treat 'templates' / 'template-schema' as a draft id.
@router.get("/templates", summary="List Smart-Drafter document types")
def list_compose_templates():
    """Returns metadata for every template the conversational drafter
    knows about — used by the FE picker."""
    from headnote.drafter.compose import list_templates_slim
    return {"templates": list_templates_slim()}


@router.get("/courts", summary="Templates grouped by court (drafting home)")
def list_compose_courts():
    """Returns the 6 court groups (sc / hc / sessions / magistrate / family /
    procedural) with their templates sorted by popularity. Drives the new
    court-card drafting home and the per-court drill-down pages.

    Public (no auth) — same access policy as /templates."""
    from headnote.drafter.compose import list_templates_by_court
    return {"courts": list_templates_by_court()}


@router.get("/template-schema/{doc_type}", summary="Full schema for one template (fields + format spec)")
def get_template_schema(doc_type: str):
    """Returns the complete field schema for one template. Used by the
    universal template-drafter page to auto-render the form."""
    from headnote.drafter import template_adapter as TA
    if TA.is_canonical(doc_type):                       # V2 canonical engine
        return {"template": TA.schema(doc_type)}
    from headnote.drafter.compose import get_template
    tpl = get_template(doc_type)
    if not tpl:
        raise HTTPException(status_code=404, detail=f"no template '{doc_type}'")
    # Strip the LLM-only `format_spec` — frontend doesn't need it
    slim = {k: v for k, v in tpl.items() if k != "format_spec"}
    return {"template": slim}


class RenderLiveBody(BaseModel):
    story_id: str
    answers:  dict = Field(default_factory=dict)
    lang:     Literal["hi", "en"] = "hi"


@router.post("/render-live", summary="Render a story template to HTML from posted fields (live preview; no save/LLM/metering)")
def render_live(body: RenderLiveBody):
    """Deterministic live-preview render: fields → court-format HTML via the
    story's template module (e.g. discharge_239). No persistence, no metering,
    no model call — drives the drafter pages' instant preview."""
    html = stories.render_story(body.story_id, body.lang, body.answers or {})
    return {"ok": True, "html": html}


class FromPromptBody(BaseModel):
    prompt: str = Field(..., description="freeform matter description (Hindi / English / Hinglish)")
    lang:   Literal["hi", "en", "auto"] = "auto"  # 'auto' → intent-aware detect from the prompt


def _persist_editor_draft(result: dict) -> dict:
    """Persist a from-prompt/from-document result so it opens in the Draft Studio
    editor at /draft/editor/<id>, and stamp `draft_id` onto the returned dict. The
    full editor payload (body HTML both langs + the trust data) lives in the draft's
    `answers` blob — no schema change. Best-effort: a storage failure never breaks
    the draft response (the inline fallback still renders)."""
    if not isinstance(result, dict) or not result.get("ok"):
        return result
    try:
        payload = {k: result.get(k) for k in (
            "doc_type", "court", "bail_type", "lang", "title", "mode",
            "html_hi", "html_en", "page_hi", "page_en", "warnings", "ungrounded",
            "cite_at_hearing", "companions", "editor_id", "editor_fields",
            "data", "mirrored", "confidence", "reason", "classified_as",
        )}
        d = storage.create_draft(
            story_id=(result.get("doc_type") or "other_criminal"),
            template_version=1,
            lang=(result.get("lang") or "hi"),
            answers=payload,
            title=(result.get("title") or result.get("doc_type") or "Draft"),
        )
        result["draft_id"] = d.id
    except Exception:
        import logging
        logging.getLogger("headnote.drafter").warning("draft persist failed", exc_info=True)
    return result


@router.post("/from-prompt", summary="Prompt-first drafting → best court-ready draft (authored-primary, never fails)")
def draft_from_prompt_route(body: FromPromptBody):
    """One freeform description → the LLM authors the draft from the WHOLE input, with the
    matching canonical template injected as the PRESCRIBED FORMAT and every guard in force
    (verified-citation whitelist, fact-grounding, section pairs, input coverage). Never-fail
    ladder inside: authored → canonical floor → pure-python skeleton.
    See headnote/drafter/from_prompt.py."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.from_prompt import draft_from_prompt
    if not (body.prompt or "").strip():
        return JSONResponse({"ok": False, "error": "empty prompt"}, status_code=400)
    try:
        return _persist_editor_draft(draft_from_prompt(body.prompt, body.lang))
    except Exception as e:  # draft_from_prompt never raises — this is a belt-and-braces backstop
        import logging
        logging.getLogger("headnote.drafter").exception("from-prompt backstop hit")
        return JSONResponse({"ok": False, "error":
                             "ड्राफ्ट बनाने में क्षणिक बाधा आई — कृपया दोबारा 'Draft' दबाएँ। "
                             "(A temporary hiccup while drafting — please tap Draft again.)"})


class SuggestBody(BaseModel):
    doc_type: str = Field(..., description="classifier doc_type / brief key, e.g. 'recovery_suit', 'bail'")
    text:     str = Field(..., description="the current draft (HTML or plain text)")
    lang:     Literal["hi", "en"] = "hi"
    llm:      bool = Field(True, description="False = deterministic-only (skip the missing-points LLM call)")


@router.post("/suggest", summary="सुझाव rail — sections check, missing points, limitation, companions, authorities")
def suggest_route(body: SuggestBody):
    """Live drafting suggestions beside the editor: everything except `missing`
    is a pure lookup over the type briefs + section guards (zero LLM); `missing`
    is one guarded DeepSeek call that degrades gracefully when offline. Nothing
    is ever auto-inserted — see headnote/drafter/suggest.py."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.suggest import suggest_for
    if not (body.text or "").strip():
        return JSONResponse({"ok": False, "error": "empty draft text"}, status_code=400)
    try:
        return suggest_for(body.doc_type, body.text, body.lang, use_llm=body.llm)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


class AssistRouteBody(BaseModel):
    prompt:  str = Field(..., description="freeform request, e.g. 'I need an RFA' / 'जमानत का आवेदन'")
    lang:    Literal["hi", "en", "auto"] = "auto"
    name:    Optional[str] = Field(None, description="requester name (optional, for the queue log)")
    contact: Optional[str] = Field(None, description="phone / email (optional, for follow-up)")


@router.post("/assist-route", summary="Personal-Assist auto-router: request → live /draft link or an authored draft")
def assist_route(body: AssistRouteBody):
    """The self-serve intake behind the assist queue. A freeform request →
    either the clean shareable link of a live /draft/<type> page (instant, no
    LLM), or, for anything we don't have a page for, a court-ready draft
    authored on the spot by the guarded engine (no fabricated case law). See
    headnote/drafter/assist.py."""
    from fastapi.responses import JSONResponse
    from headnote.drafter import assist as _assist
    prompt = (body.prompt or "").strip()
    if not prompt:
        return JSONResponse({"ok": False, "error": "empty request"}, status_code=400)
    try:
        result = _assist.route_request(prompt, body.lang)
        # Lightweight queue log (stdout for now; Notion sync is a fast-follow).
        try:
            import logging
            logging.getLogger("headnote.assist").info(
                "assist request: kind=%s who=%s contact=%s prompt=%r",
                result.get("kind"), (body.name or "-"), (body.contact or "-"), prompt[:160])
        except Exception:
            pass
        result["ok"] = result.get("kind") != "error"
        return result
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=500)


@router.post("/from-document", summary="Draft from an attached document — as source facts, or as a style reference to mirror")
async def draft_from_document(
    prompt: str = Form(""),
    lang: str = Form("auto"),
    role: str = Form("facts"),
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
):
    """One upload endpoint, TWO intents chosen by `role`:

    • role="facts" (default) — the file is CASE PAPERS (FIR / order / notice). We OCR it and
      run it through the draft pipeline as the matter's FACTS, so the document drives the draft.

    • role="reference" — the file is a FILED DRAFT the advocate likes. We OCR it and MIRROR its
      structure, headings, tone and formatting, filling the dynamic slots with the typed prompt's
      facts. The reference's own facts/citations are never copied. See draft_from_prompt(reference_text=…).

    Ungated. Image, PDF, Word (.docx) or Excel (.xlsx); max 20 MB/file, 8 pages."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.ocr import ocr_text_pages
    from headnote.drafter.from_prompt import draft_from_prompt

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads and not (prompt or "").strip():
        return JSONResponse({"ok": False, "error": "attach a document or describe the matter"}, status_code=400)

    doc_text = ""
    ocr_warning = ""
    if uploads:
        if len(uploads) > _OCR_MAX_PAGES:
            return JSONResponse({"ok": False, "error": f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}"}, status_code=400)
        entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
        try:
            pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
        except ValueError as e:
            return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
        # OCR failure must NEVER kill the request — degrade to whatever text we do
        # have (office extraction / the typed prompt) and say so in a warning.
        # run_in_threadpool: this endpoint is async, and OCR/LLM are BLOCKING — calling
        # them directly would freeze the whole event loop for the entire (30-120s) job,
        # so health checks fail and the platform drops the connection → "Failed to fetch"
        # on multi-page uploads. The threadpool keeps the loop free. (The typed /from-prompt
        # route is a sync `def`, which FastAPI already threadpools — that's why it worked.)
        try:
            doc_text = await run_in_threadpool(ocr_text_pages, pages, office_text=office_text)
        except Exception as e:
            import logging
            logging.getLogger("headnote.drafter").warning("OCR degraded: %s", e)
            doc_text = (office_text or "").strip()
            ocr_warning = ("अपलोड किया दस्तावेज़ पढ़ा नहीं जा सका — ड्राफ्ट आपके लिखे विवरण से बना है। "
                           "साफ़ फोटो के साथ दोबारा कोशिश करें।"
                           if (lang or "hi") != "en" else
                           "Could not read the uploaded document — the draft was made from your typed "
                           "description. Try again with a clearer photo.")

    def _with_ocr_warning(result):
        if ocr_warning and isinstance(result, dict):
            result.setdefault("warnings", []).insert(0, ocr_warning)
        return _persist_editor_draft(result)

    # role="reference": the document is a STYLE reference to mirror; the typed prompt carries the facts.
    if role == "reference":
        if not doc_text.strip():
            if (prompt or "").strip():
                # reference unreadable but the matter is typed — draft it anyway
                res = await run_in_threadpool(draft_from_prompt, (prompt or "").strip(), lang)
                return _with_ocr_warning(res)
            return JSONResponse({"ok": False, "error":
                                 "रेफरेंस दस्तावेज़ पढ़ा नहीं जा सका — साफ़ फोटो/PDF के साथ दोबारा कोशिश करें। "
                                 "(Could not read the reference document — try a clearer photo/PDF.)"})
        res = await run_in_threadpool(draft_from_prompt, (prompt or "").strip(), lang,
                                      reference_text=doc_text.strip())
        return _with_ocr_warning(res)

    # role="facts" (default): the document is the source of facts; a typed prompt adds intent.
    matter = (prompt or "").strip()
    if doc_text.strip():
        ref = "संलग्न दस्तावेज से तथ्य" if lang == "hi" else "Facts from the attached document"
        matter = (matter + "\n\n" if matter else "") + ref + ":\n" + doc_text.strip()
    if not matter.strip():
        return JSONResponse({"ok": False, "error":
                             "दस्तावेज़ पढ़ा नहीं जा सका और कोई विवरण भी नहीं लिखा गया — मामला टाइप करें या साफ़ "
                             "फोटो अपलोड करें। (Could not read the document and nothing was typed — describe "
                             "the matter or upload a clearer photo.)"})
    res = await run_in_threadpool(draft_from_prompt, matter, lang)
    return _with_ocr_warning(res)


class RefineBody(BaseModel):
    prev_html: str = Field(..., description="the advocate's current authored draft (HTML or text)")
    instruction: str = Field(..., description="what to change, in plain Hindi/English")
    doc_type: str = Field("other_criminal", description="the draft's doc_type, echoed from the result")
    lang: Literal["hi", "en", "auto"] = "auto"  # normally the resolved lang echoed from the result


@router.post("/refine", summary="Instruction-based refine of an AUTHORED draft (the edit path for non-canonical drafts)")
def refine_route(body: RefineBody):
    """Authored (house-style, non-canonical) drafts have no structured fields, so the advocate refines
    them by INSTRUCTION: 'make it more concise', 'add a ground on parity', 'change court to CJM'. We
    revise the current draft and return the same unified shape as /from-prompt (with page_hi/page_en)."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.author import revise_document, revise_mirrored
    from headnote.drafter.from_prompt import _finalize, resolve_lang
    if not (body.instruction or "").strip():
        return JSONResponse({"ok": False, "error": "tell us what to change"}, status_code=400)
    if not (body.prev_html or "").strip():
        return JSONResponse({"ok": False, "error": "nothing to refine"}, status_code=400)
    lang = resolve_lang(body.lang, body.prev_html + " " + body.instruction)
    try:
        # a MIRRORED draft (matched to an uploaded reference — root carries mr-doc) must
        # be revised through the block engine, or the refine would silently strip the
        # advocate's reference formatting back to the house style
        if 'class="mr-doc' in body.prev_html:
            result = revise_mirrored(body.prev_html, body.instruction, body.doc_type, lang)
        else:
            result = revise_document(body.prev_html, body.instruction, body.doc_type, lang)
        result.update({
            "html_hi": result["html"] if lang != "en" else "",
            "html_en": result["html"] if lang == "en" else "",
        })
        return _finalize(result)
    except Exception:
        # never a 500 mid-edit: the advocate's current draft is safe in the editor —
        # tell them the change didn't land and to retry, in a shape the UI handles.
        import logging
        logging.getLogger("headnote.drafter").exception("refine failed")
        return JSONResponse({"ok": False, "error":
                             "बदलाव लागू नहीं हो सका — आपका ड्राफ्ट सुरक्षित है; कृपया वही निर्देश दोबारा भेजें। "
                             "(The change could not be applied — your draft is safe; please send the "
                             "instruction again.)"})


@router.get("/{draft_id}", summary="Get one draft by id")
def get_draft(draft_id: str):
    d = storage.get_draft(draft_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"no draft with id={draft_id!r}")
    return d.to_dict()


@router.patch("/{draft_id}", summary="Partial update: answers / lang / title")
def update_draft(draft_id: str, body: UpdateDraftBody):
    d = storage.update_draft(
        draft_id,
        answers=body.answers,
        lang=body.lang,
        title=body.title,
    )
    if d is None:
        raise HTTPException(status_code=404, detail=f"no draft with id={draft_id!r}")
    return d.to_dict()


@router.delete("/{draft_id}", summary="Delete a draft")
def delete_draft(draft_id: str):
    deleted = storage.delete_draft(draft_id)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"no draft with id={draft_id!r}")
    return {"deleted": True, "id": draft_id}


def _draft_matter_text(answers: dict) -> str:
    """The current draft's own text, tags stripped — used as the FACTS source when
    re-mirroring in place (the draft now carries the matter, so it is the brief)."""
    body = (answers.get("html_hi") or answers.get("html_en") or "")
    t = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", body)
    t = re.sub(r"(?i)<(br|/p|/div|/li|/h\d|/tr)[^>]*>", "\n", t)
    t = re.sub(r"<[^>]+>", "", t)
    t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
          .replace("&nbsp;", " ").replace("&#39;", "'").replace("&quot;", '"'))
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n", t).strip()


@router.post("/{draft_id}/apply-reference", summary="Re-mirror this draft into an uploaded reference's format, IN PLACE")
async def apply_reference(
    draft_id: str,
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
):
    """Attach a filed document as a STYLE reference to an EXISTING draft: OCR the
    reference, re-mirror the draft's current facts into that format, and update the
    SAME draft in place (same id — no orphan, no navigation). Reference = format,
    the draft's own text = facts (two-source rule); every guard still fires."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.ocr import ocr_text_pages
    from headnote.drafter.from_prompt import draft_from_prompt

    d = storage.get_draft(draft_id)
    if d is None:
        return JSONResponse({"ok": False, "error": "draft not found"}, status_code=404)
    answers = d.to_dict().get("answers") or {}

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        return JSONResponse({"ok": False, "error": "attach a reference document (image / PDF / Word)"}, status_code=400)
    if len(uploads) > _OCR_MAX_PAGES:
        return JSONResponse({"ok": False, "error": f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}"}, status_code=400)

    entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
    except ValueError as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
    try:
        # threadpool: OCR + mirror are blocking; this is an async endpoint (see the note
        # in draft_from_document) — running them inline would freeze the event loop.
        ref_text = await run_in_threadpool(ocr_text_pages, pages, office_text=office_text)
    except Exception:
        return JSONResponse({"ok": False, "error":
                             "रेफरेंस दस्तावेज़ पढ़ा नहीं जा सका — साफ़ फोटो/PDF के साथ फिर कोशिश करें। "
                             "(Could not read the reference — try a clearer photo/PDF.)"})
    if not (ref_text or "").strip():
        return JSONResponse({"ok": False, "error": "could not read the reference document"})

    matter = _draft_matter_text(answers)
    lang = answers.get("lang") or d.lang or "hi"
    result = await run_in_threadpool(draft_from_prompt, matter, lang,
                                     reference_text=ref_text.strip())
    if not (isinstance(result, dict) and result.get("ok")):
        return JSONResponse({"ok": False, "error":
                             "रेफरेंस लागू नहीं हो सका — कृपया दोबारा कोशिश करें। "
                             "(Could not apply the reference — please try again.)"})
    # update the SAME draft in place with the re-mirrored payload
    new_payload = {**answers}
    for k in ("html_hi", "html_en", "page_hi", "page_en", "warnings", "ungrounded",
              "cite_at_hearing", "companions", "mirrored", "title", "lang"):
        if k in result:
            new_payload[k] = result[k]
    new_payload["mirrored"] = True
    storage.update_draft(draft_id, answers=new_payload,
                         lang=(result.get("lang") or lang),
                         title=(result.get("title") or d.title))
    result["draft_id"] = draft_id
    return result


@router.get("/{draft_id}/render", summary="Render the draft to HTML for preview")
def render_draft(draft_id: str, lang: Optional[str] = None):
    """Returns rendered HTML. `lang` query param overrides the draft's
    stored lang — handy for letting the lawyer toggle EN/HI in the preview
    without persisting the change."""
    d = storage.get_draft(draft_id)
    if d is None:
        raise HTTPException(status_code=404, detail=f"no draft with id={draft_id!r}")
    use_lang = lang if lang in ("en", "hi") else d.lang
    html = stories.render_story(d.story_id, use_lang, d.answers)
    return {
        "id": d.id,
        "story_id": d.story_id,
        "lang": use_lang,
        "template_version": d.template_version,
        "html": html,
    }


@router.get("/", summary="List recent drafts (for the FE drafts panel)")
def list_drafts(
    limit: int = 20,
    user: CurrentUser = Depends(get_current_user),
):
    """List drafts owned by the authenticated user. Recent-first."""
    drafts = storage.list_drafts(user_id=user.id, limit=limit)
    return {"count": len(drafts), "drafts": [d.to_dict() for d in drafts]}


# ----------------------------------------------------------- field translation

@router.post("/translate-fields", summary="Translate legal-form prose fields EN↔HI")
async def translate_fields(
    body: TranslateFieldsBody,
    user: Optional[CurrentUser] = Depends(optional_user),
):
    """Translate the prose fields of any legal drafting form in either direction.

    Used by the bail drafter AND the universal template drafter, so the prompt
    is document-type-agnostic and routes each value by what it is (name →
    transliterate, court → translate, prose → translate).

    Only non-empty string values are translated. Proper nouns (names, case
    numbers, dates, statute refs) are preserved by the prompt instruction.

    Backend: DeepSeek V3 (deepseek-chat) primary, Groq llama as last resort.

    Gated: draft feature (same quota as draft_start).
    """
    from headnote.drafter.compose import _llm_call

    # Filter to non-empty string values only
    to_translate = {k: v for k, v in (body.fields or {}).items()
                    if isinstance(v, str) and v.strip()}
    if not to_translate:
        return {"translated": {}, "skipped": True}

    target_name = "Hindi (Devanagari script)" if body.target == "hi" else "English (Roman script)"
    fields_json = json.dumps(to_translate, ensure_ascii=False, indent=2)

    system = (
        "You are a bilingual converter for Indian legal-document form fields "
        "(bail, vakalatnama, writ, maintenance, appeals, notices — any "
        "petition or application). Your job: for each value in the given JSON, "
        "OUTPUT THE SAME CONTENT in the target script/language. Decide per "
        "value by WHAT IT IS (the JSON key hints at it):\n"
        "• Person names (applicant/petitioner/accused/father/advocate/judge "
        "names): TRANSLITERATE phonetically to the target script. "
        "E.g., 'Anil Verma' → 'अनिल वर्मा'; 'श्री राम सिंह' → 'Shri Ram Singh'.\n"
        "• Place names, addresses, district, state, police station, jail names: "
        "TRANSLITERATE to the target script (use the conventional Indian-English "
        "spelling for places, e.g. 'Lucknow' ↔ 'लखनऊ', 'Uttar Pradesh' ↔ "
        "'उत्तर प्रदेश').\n"
        "• Court names, designations + judge titles: TRANSLATE using standard "
        "Indian legal vocabulary (e.g. 'Allahabad High Court Lucknow Bench' ↔ "
        "'माननीय उच्च न्यायालय इलाहाबाद खण्डपीठ, लखनऊ'; "
        "'2nd Additional Sessions Judge' ↔ 'द्वितीय अपर सत्र न्यायाधीश').\n"
        "• Occupation: TRANSLATE ('Shopkeeper' ↔ 'दुकानदारी').\n"
        "• Any long prose (facts, grounds, narratives, histories, prayers, "
        "relief sought): TRANSLATE naturally using formal legal Hindi/English. "
        "Keep statute refs (IPC, CrPC, BNS, BNSS, §138, S.302 etc.), "
        "FIR/case/cheque/account numbers, and dates unchanged within the prose.\n"
        "Always return ONLY a JSON object with the same keys as input. No prose, "
        "no markdown fences, no commentary."
    )
    prompt = (
        f"Convert every value below to {target_name}. Apply the per-field rules "
        "from the system prompt. Return ONLY the JSON object.\n\n"
        f"{fields_json}"
    )

    def _translate() -> dict:
        try:
            raw = _llm_call(system, prompt, max_tokens=3000, model="quality")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Translation failed: {e}")
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text.strip())
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    return json.loads(m.group(0))
                except json.JSONDecodeError:
                    return to_translate  # fallback: return originals unchanged
            return to_translate

    # Meter for signed-in users; anon (Word add-in — English→doc-language on apply)
    # runs unmetered, same policy as /fir/extract.
    if user:
        with check_and_record(user.id, "draft", endpoint="translate_fields", email=user.email) as _record:
            translated = _translate()
            _record(cost_paise=40, model="deepseek-chat")
            return {"translated": translated}
    return {"translated": _translate()}


# ----------------------------------------------------------- OCR

# Upload type validation lives in headnote.drafter.office.collect_uploads:
# image/PDF take the vision-OCR path, Word (.docx) / Excel (.xlsx) are text-extracted.
_OCR_MAX_BYTES = 20 * 1024 * 1024
_OCR_MAX_PAGES = 8  # NCRB I.I.F.-I is at most 4-5 pages; cap generously


@router.post("/ocr-fir", summary="OCR a photographed/scanned FIR → structured fields")
async def ocr_fir(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    user: CurrentUser = Depends(get_current_user),
):
    """Claude vision reads the FIR (Hindi or English, printed or handwritten)
    and returns the structured fields needed to pre-fill a bail application.

    Accepts either a single `file` OR a list of `files` (multi-page FIR — the
    NCRB I.I.F.-I form runs 3-5 pages; sending them all in one call lets the
    model reconcile fields that span pages, e.g. narrative on p3 + IO name
    on p4).

    Supported: JPEG, PNG, WebP, GIF, PDF.
    Max per file: 20 MB. Max pages per FIR: 8.

    Gated: draft feature (counts against quota; 402 if exhausted).
    """
    from headnote.drafter.ocr import ocr_fir_pages

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=400, detail="upload 'file' or 'files'")
    if len(uploads) > _OCR_MAX_PAGES:
        raise HTTPException(
            status_code=400,
            detail=f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}",
        )

    entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with check_and_record(user.id, "draft", endpoint="ocr_fir", email=user.email) as _record:
        try:
            parsed = ocr_fir_pages(pages, office_text=office_text)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        # Cost scales roughly with page count. 300p per page is conservative.
        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(uploads), "extracted": parsed}


@router.post("/fir/extract", summary="OCR an FIR → bail confirm-step fields (Draft from FIR, step 1)")
async def fir_extract(
    court: str = Form("sessions"),
    lang: str = Form("hi"),
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    user: Optional[CurrentUser] = Depends(optional_user),
):
    """Step 1 of the "Draft from FIR" flow (web confirm step AND the Word add-in).

    OCR the uploaded FIR, map it onto the canonical bail template's own slots,
    and return them as a CONFIRM step: each value the FIR supplied is flagged
    `found` (amber — machine-read, the advocate confirms before it goes in), and
    each required field the FIR can't supply is flagged `missing` so the UI can
    prompt for it. NOTHING is written into a draft here. Jurisdiction is never inferred.

    `court`: magistrate | sessions | hc (→ doc_type bail_<court>). `lang`: hi | en.
    Accepts a single `file` or a list of `files` (NCRB I.I.F.-I runs 3-5 pages).

    Anon-friendly: OCR is Groq free-tier (₹0), so the Word add-in (which has no
    login session) may call it unauthenticated; signed-in calls are metered as usual.
    """
    from headnote.drafter import template_adapter as TA
    from headnote.drafter.ocr import ocr_fir_pages
    from headnote.drafter.fir_intake import fir_ocr_to_bail_slots, confirm_fields

    lang = "en" if (lang or "").lower().startswith("en") else "hi"
    doc_type = f"bail_{(court or 'sessions').lower().strip()}"
    if not TA.is_canonical(doc_type):
        doc_type = "bail_sessions"

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=400, detail="upload 'file' or 'files'")
    if len(uploads) > _OCR_MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}")

    entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    async def _build() -> dict:
        # OCR is blocking; threadpool it so the async loop stays free on multi-page
        # uploads (see the note in draft_from_document). An unreadable FIR must never
        # 500 — degrade to an empty confirm step with a friendly note so the advocate
        # can just type the fields instead.
        try:
            parsed = await run_in_threadpool(ocr_fir_pages, pages, office_text=office_text)
        except Exception as e:
            import logging
            logging.getLogger("headnote.drafter").warning("FIR OCR degraded: %s", e)
            parsed = {}
        slots = fir_ocr_to_bail_slots(parsed, lang) if parsed else {}
        fields = confirm_fields(doc_type, slots, lang)
        read_ok = bool(slots)
        note = "" if read_ok else (
            "एफआईआर पढ़ी नहीं जा सकी — नीचे विवरण स्वयं भरें, या साफ़ फोटो के साथ दोबारा कोशिश करें।"
            if lang != "en" else
            "Couldn't read the FIR — fill the details below, or try again with a clearer photo."
        )
        return {
            "ok": True,
            "read_ok": read_ok,
            "doc_type": doc_type,
            "court": doc_type.split("_", 1)[1],
            "lang": lang,
            "page_count": len(uploads),
            "fields": fields,          # the confirm step (amber/missing/empty)
            "slots": slots,            # raw mapped values, for the render step
            "narrative": {"hi": parsed.get("narrative_hi", ""), "en": parsed.get("narrative_en", "")},
            "note": note,
        }

    # Meter only for signed-in users; anon (Word add-in) runs free-tier OCR unmetered.
    if user:
        with check_and_record(user.id, "draft", endpoint="fir_extract", email=user.email) as _record:
            result = await _build()
            _record(cost_paise=0, model="groq/llama-4-scout-vision")
            return result
    return await _build()


class RenderCanonicalBody(BaseModel):
    doc_type: str
    fields:   dict = Field(default_factory=dict)
    lang:     Literal["hi", "en", "mr", "bn", "gu"] = "hi"


@router.get("/canonical-types", summary="List canonical (deterministic) drafter types, grouped criminal/civil (for the Word add-in)")
def canonical_types():
    """Every canonical/deterministic template with its hi/en label and a coarse
    group (criminal · civil · family · other), for the Word add-in's drafter picker.
    Ungated (labels only, no client data). Stays in sync with CANONICAL_MAP/LABELS."""
    from headnote.drafter import template_adapter as TA
    _civil = {"recovery_suit", "injunction_suit", "specific_performance", "declaration_suit",
              "partition_suit", "eviction_suit", "written_statement", "consumer_complaint", "mact_166"}
    _family = {"maintenance", "dv", "divorce_13", "restitution_9"}
    _other = {"vakalatnama", "general_affidavit", "legal_notice", "mention_memo"}
    def _group(tid: str) -> str:
        if tid in _civil:  return "civil"
        if tid in _family: return "family"
        if tid in _other:  return "other"
        return "criminal"
    out = []
    for tid in TA.CANONICAL_MAP:
        lab = TA.LABELS.get(tid, {"en": tid, "hi": tid})
        out.append({"doc_type": tid, "label_en": lab["en"], "label_hi": lab["hi"], "group": _group(tid)})
    order = {"criminal": 0, "civil": 1, "family": 2, "other": 3}
    out.sort(key=lambda x: (order.get(x["group"], 9), x["label_en"]))
    return {"ok": True, "types": out}


@router.post("/render-canonical", summary="Deterministic canonical render (free, ungated) — fields → document HTML")
def render_canonical(body: RenderCanonicalBody):
    """Free, deterministic render of a CANONICAL template only (no LLM, ₹0). Used by
    the Word add-in's Fields tab to turn structured fields → the live document as the
    lawyer types. Refuses non-canonical types (those need the metered LLM path via
    /render-template), so it's safe to leave unauthenticated."""
    from fastapi.responses import JSONResponse
    from headnote.drafter import template_adapter as TA
    if not TA.is_canonical(body.doc_type):
        return JSONResponse({"ok": False, "error": f"'{body.doc_type}' is not a canonical (deterministic) template"}, status_code=400)
    try:
        return {"ok": True, "document": TA.document(body.doc_type, body.fields or {}, body.lang)}
    except Exception as e:
        import logging
        logging.getLogger("headnote.drafter").exception("render-canonical failed: %s", body.doc_type)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=502)


@router.post("/render-docx", summary="Canonical draft → native Word .docx (base64) for the Word add-in (fidelity)")
def render_docx(body: RenderCanonicalBody):
    """Render a CANONICAL draft as a NATIVE .docx (python-docx) and return it
    base64-encoded, so the Word add-in drops it in with insertFileFromBase64 and
    keeps the court format 1:1 (centered court name, party blocks, numbered grounds,
    right-aligned signature) — unlike HTML import, which can't reproduce our
    flex/grid layout. Free, deterministic, canonical-only → safe unauthenticated."""
    import base64
    from fastapi.responses import JSONResponse
    from headnote.drafter import template_adapter as TA
    if not TA.is_canonical(body.doc_type):
        return JSONResponse({"ok": False, "error": f"'{body.doc_type}' is not a canonical template"}, status_code=400)
    try:
        from headnote.drafter.docx_render import canonical_to_docx
        data = canonical_to_docx(body.doc_type, body.fields or {}, body.lang)
        return {"ok": True, "filename": f"{body.doc_type}.docx",
                "docx_base64": base64.b64encode(data).decode("ascii")}
    except Exception as e:
        import logging
        logging.getLogger("headnote.drafter").exception("render-docx failed: %s", body.doc_type)
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=502)


class EditSelectionBody(BaseModel):
    text:        str = Field(..., description="the SELECTED snippet from the document")
    action:      str = Field("formalise", description="formalise|strengthen|shorten|simplify|grammar|translate|rewrite")
    instruction: Optional[str] = Field(None, description="custom instruction (for action=rewrite)")
    lang:        Literal["hi", "en", "auto"] = "auto"


# Persona-informed transforms for select-to-act. Each is a one-shot, SCOPED edit of
# just the selected text — never a whole document. Covers litigation (formalise /
# strengthen / shorten), in-house & client-facing (simplify), and quick fixes (grammar).
_SELECTION_ACTIONS = {
    "formalise":  "Rewrite in formal Indian court register.",
    "strengthen": "Strengthen it as a legal argument — firmer, better-reasoned, persuasive.",
    "shorten":    "Make it tighter and more concise.",
    "simplify":   "Rewrite in plain, clear language a client could follow, keeping it accurate.",
    "grammar":    "Fix grammar, spelling and flow only — keep the wording and meaning as close as possible.",
    "translate":  "Translate to the OTHER language (Hindi↔English) in formal legal register.",
}


@router.post("/edit-selection", summary="Transform ONLY a selected snippet (Word add-in select-to-act) — fast, scoped")
def edit_selection(body: EditSelectionBody):
    """The add-in's select-to-act. Applies ONE transformation to just the selected text
    and returns ONLY the transformed text — it never turns a snippet into a whole
    document (that was the /refine bug) and never invents facts. Fast: a single small
    DeepSeek-V3 call. Ungated (operates on text the user already has open)."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.compose import _llm_call

    text = (body.text or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "no text selected"}, status_code=400)
    if body.action == "rewrite":
        task = (body.instruction or "").strip() or "Improve this text."
    else:
        task = _SELECTION_ACTIONS.get(body.action, _SELECTION_ACTIONS["formalise"])

    system = (
        "You are editing a SELECTED SNIPPET from an Indian legal document — not the whole "
        "document. Apply ONLY the requested change to this snippet and return ONLY the "
        "revised snippet.\n"
        "HARD RULES:\n"
        "- Return just the edited text — NO headings, NO court format, NO extra paragraphs, "
        "never expand a snippet into a full draft or template.\n"
        "- Preserve every fact, name, date, number, FIR/case number and statute reference "
        "exactly (unless the task is to translate, then keep those tokens unchanged).\n"
        "- Keep the SAME language/script as the input unless explicitly translating.\n"
        "- Output plain text only — no markdown, no quotes around it, no commentary."
    )
    prompt = f"Task: {task}\n\nSnippet:\n{text}"
    # size the response to the input so short selections come back fast
    max_toks = min(2000, max(256, len(text) // 2 + 300))
    try:
        out = _llm_call(system, prompt, max_tokens=max_toks, model="fast")
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"edit failed: {e}"}, status_code=502)
    out = (out or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-z]*\s*", "", out)
        out = re.sub(r"\s*```$", "", out.strip())
    # strip a wrapping quote the model sometimes adds
    if len(out) > 1 and out[0] in "\"'“" and out[-1] in "\"'”":
        out = out[1:-1].strip()
    if not out:
        return JSONResponse({"ok": False, "error": "no change produced"}, status_code=502)
    return {"ok": True, "text": out}


class DetectFieldsBody(BaseModel):
    text: str = Field(..., description="plain text of the OPEN Word document")
    lang: Literal["hi", "en", "auto"] = "auto"


@router.post("/detect-fields", summary="Read an open draft's text → its client-specific fields (Word add-in 'adapt this draft')")
def detect_fields(body: DetectFieldsBody):
    """The intelligence behind the add-in's "adapt this draft" pane. Given the text of
    whatever draft the lawyer has open (ANY type, ours or theirs), an LLM returns the
    CLIENT-SPECIFIC PARTICULARS it finds — party names/relations, age, occupation,
    address, police station, district, FIR/case number, sections, key dates, court —
    each with its value copied VERBATIM as it appears, so the add-in can find-and-replace
    it surgically. Boilerplate legal prose is ignored. Ungated (labels/values from the
    doc the user already has open; no metering). DeepSeek V3 (fast)."""
    from fastapi.responses import JSONResponse
    from headnote.drafter.compose import _llm_call

    text = (body.text or "").strip()
    if not text:
        return JSONResponse({"ok": False, "error": "empty document"}, status_code=400)
    doc_lang = "en" if (body.lang == "en" or (body.lang == "auto" and not re.search(r"[ऀ-ॿ]", text))) else "hi"

    system = (
        "You extract the CLIENT-SPECIFIC PARTICULARS from an Indian court draft so they "
        "can be edited for a new matter. These are the values that change case-to-case: "
        "party names (applicant/petitioner/complainant/accused/respondent), father/husband "
        "name, age, occupation, address, police station, district/place, FIR or crime or "
        "case number, statutory sections, key dates, and the court's name/place.\n"
        "RULES:\n"
        "- Copy each value EXACTLY as it appears in the document (verbatim, same script, same "
        "digits, same punctuation) — it will be used for find-and-replace, so it must match.\n"
        "- Do NOT include boilerplate legal language, grounds prose, or prayer text.\n"
        "- Skip anything you cannot find an actual value for (no guessing, no blanks).\n"
        "- Use stable snake_case keys (applicant_name, father_name, age, occupation, address, "
        "police_station, district, fir_number, sections, court, incident_date, next_date …).\n"
        "- Give each a short English label for the UI.\n"
        "Return STRICT JSON only: "
        '{"fields":[{"key","label","value"}], "facts":{"label","value"}|null} '
        "where facts.value is the verbatim first sentence of the facts/story narrative if the "
        "draft has one (used to locate it), else null. No markdown, no commentary."
    )
    prompt = "Extract the particulars from this draft:\n\n" + text[:9000]
    try:
        raw = _llm_call(system, prompt, max_tokens=1500, model="fast")
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"detection failed: {e}"}, status_code=502)

    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s.strip())
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, re.DOTALL)
        if not m:
            return JSONResponse({"ok": False, "error": "could not parse the draft's fields"}, status_code=502)
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return JSONResponse({"ok": False, "error": "could not parse the draft's fields"}, status_code=502)

    # keep only well-formed field rows whose value actually occurs in the document
    fields = []
    for f in (data.get("fields") or []):
        if not isinstance(f, dict):
            continue
        key, label, value = (f.get("key") or "").strip(), (f.get("label") or "").strip(), (f.get("value") or "").strip()
        if key and value and value in text:
            fields.append({"key": key, "label": label or key, "value": value})
    facts = data.get("facts") if isinstance(data.get("facts"), dict) else None
    if facts and not (facts.get("value") or "").strip():
        facts = None
    return {"ok": True, "lang": doc_lang, "fields": fields, "facts": facts}


class FirFieldsBody(BaseModel):
    slots:    dict = Field(default_factory=dict, description="raw FIR→bail slots from /fir/extract")
    doc_type: str = Field("bail_sessions", description="canonical bail doc_type to re-map onto")
    lang:     Literal["hi", "en"] = "hi"


@router.post("/fir/fields", summary="Re-map FIR slots onto a different bail court (no OCR; instant court switch)")
def fir_fields(body: FirFieldsBody):
    """Step 1b: the advocate switches court (Magistrate/Sessions/HC · regular/anticipatory)
    in the confirm step. The FIR facts don't change — only the target template's field set
    does — so we re-derive the confirm fields from the already-extracted slots against the new
    doc_type's schema. No OCR, no LLM, no cost. Open (no auth): operates only on client-held
    slots, mints nothing."""
    from fastapi.responses import JSONResponse
    from headnote.drafter import template_adapter as TA
    from headnote.drafter.fir_intake import confirm_fields
    doc_type = body.doc_type if TA.is_canonical(body.doc_type) else "bail_sessions"
    try:
        fields = confirm_fields(doc_type, body.slots or {}, body.lang)
    except Exception as e:
        return JSONResponse({"ok": False, "error": f"{type(e).__name__}: {e}"}, status_code=502)
    return {"ok": True, "doc_type": doc_type, "fields": fields}


@router.post("/ocr-bail-order", summary="OCR a Sessions/Magistrate bail order → structured fields")
async def ocr_bail_order(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    user: CurrentUser = Depends(get_current_user),
):
    """Vision reads a lower-court BAIL ORDER (the order disposing of a bail /
    anticipatory-bail application) and returns the fields needed to draft a
    SUCCESSIVE bail application before the High Court — lower court name,
    bail-case number, order date, applicants, crime details, the outcome,
    and the court's reasoning.

    Best document for a S.439 / S.483 BNSS High Court bail draft: it carries
    six fields the FIR can't (Sessions case number, judge, order date,
    application number, the rejection reasoning, prior-bail history).

    Accepts a single `file` or a list of `files` (multi-page order).
    Supported: JPEG, PNG, WebP, GIF, PDF. Max 20 MB/file, 8 pages.
    Gated: draft feature.
    """
    from headnote.drafter.ocr import ocr_bail_order_pages

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=400, detail="upload 'file' or 'files'")
    if len(uploads) > _OCR_MAX_PAGES:
        raise HTTPException(
            status_code=400,
            detail=f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}",
        )

    entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with check_and_record(user.id, "draft", endpoint="ocr_bail_order", email=user.email) as _record:
        try:
            parsed = ocr_bail_order_pages(pages, office_text=office_text)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(uploads), "extracted": parsed}


@router.post("/ocr-impugned-order", summary="OCR a govt / tribunal / lower-court order → structured writ-draft fields")
async def ocr_impugned_order(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    user: CurrentUser = Depends(get_current_user),
):
    """Vision reads the IMPUGNED ORDER being challenged in a writ petition
    under Article 226 (a SDO/Tehsildar/Collector order, a tribunal order, a
    departmental enquiry order, a service-side authority order — anything an
    aggrieved party brings to a High Court writ court) and returns the fields
    needed to draft the writ.

    Pulls out: authority, case number, order date, signing officer, the
    petitioner's particulars, the respondent, a neutral subject-matter
    summary, the operative direction, statutes cited, and — if THIS order is
    itself an appeal / revision over an EARLIER order (very common) — that
    earlier order's reference, so the writ can challenge both.

    Accepts a single `file` or a list of `files` (multi-page order).
    Supported: JPEG, PNG, WebP, GIF, PDF. Max 20 MB/file, 8 pages.
    Gated: draft feature.
    """
    from headnote.drafter.ocr import ocr_impugned_order_pages

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=400, detail="upload 'file' or 'files'")
    if len(uploads) > _OCR_MAX_PAGES:
        raise HTTPException(
            status_code=400,
            detail=f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}",
        )

    entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with check_and_record(user.id, "draft", endpoint="ocr_impugned_order", email=user.email) as _record:
        try:
            parsed = ocr_impugned_order_pages(pages, office_text=office_text)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(uploads), "extracted": parsed}


@router.post("/ocr-generic", summary="OCR any document → fill a template's own fields (Groq vision)")
async def ocr_generic(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    fields_json: str = Form("[]"),
    doc_label: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
):
    """Universal auto-fill: read an uploaded document and extract whatever
    fields the calling template declares. Powers the "auto-fill from a
    document" uploader available on every template. Vision via Groq
    Llama-4-Scout (DeepSeek fallback); never Claude unless OCR_ENABLE_ANTHROPIC=1.

    `fields_json` is a JSON array of {key, label, hint}. Returns the extracted
    values keyed by field key so the frontend's filler applies them directly.
    """
    import json as _json
    from headnote.drafter.ocr import ocr_generic_pages

    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        raise HTTPException(status_code=400, detail="upload 'file' or 'files'")
    if len(uploads) > _OCR_MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"too many pages ({len(uploads)}); max {_OCR_MAX_PAGES}")

    try:
        fields = _json.loads(fields_json or "[]")
        if not isinstance(fields, list):
            fields = []
    except Exception:
        fields = []
    if not fields:
        raise HTTPException(status_code=400, detail="no target fields provided")

    entries = [(await up.read(), up.content_type or "", up.filename or "") for up in uploads]
    try:
        pages, office_text = office.collect_uploads(entries, max_bytes=_OCR_MAX_BYTES)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    with check_and_record(user.id, "draft", endpoint="ocr_generic", email=user.email) as _record:
        try:
            extracted = ocr_generic_pages(pages, fields, doc_label, office_text=office_text)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(uploads), "extracted": extracted}


# ----------------------------------------------------------- Voice transcription

# Audio formats Whisper accepts. Web's MediaRecorder typically produces
# audio/webm on Chrome/Firefox and audio/mp4 on Safari — both supported.
_AUDIO_ALLOWED_MIME = {
    "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav",
    "audio/mp4", "audio/m4a", "audio/mpeg", "audio/mp3",
    "audio/flac",
}
_AUDIO_MAX_BYTES = 25 * 1024 * 1024  # Whisper's hard cap is 25 MB


@router.post("/transcribe", summary="Transcribe voice dictation → text (Groq Whisper)")
async def transcribe(
    file: UploadFile = File(...),
    language: str = "hi",  # 'hi' | 'en' | 'mr' | 'ta' | 'te' | 'bn' | ...
    user: CurrentUser = Depends(get_current_user),
):
    """Server-side speech-to-text via Groq's hosted Whisper.

    Used as the fallback path when the browser's built-in SpeechRecognition
    isn't available (Firefox mobile, some embedded webviews). The primary
    voice path is the Web Speech API on the client — free, real-time, and
    avoids round-trips.

    Whisper handles Hindi + code-mixed Hinglish natively. We pass `language`
    as a hint to lower latency and improve accuracy.

    Audio is NEVER persisted on disk — read into memory, sent to Groq,
    discarded. Compliant with our "voice data not retained" privacy claim.

    Gated as a 'draft' feature (counts toward quota).
    """
    import os
    if not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Voice transcription requires GROQ_API_KEY on the server.",
        )

    mt = (file.content_type or "").lower()
    # Browsers often send 'audio/webm;codecs=opus' — strip the codecs suffix.
    base_mt = mt.split(";")[0].strip()
    if base_mt not in _AUDIO_ALLOWED_MIME:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported audio type {mt!r}; use webm, mp4/m4a, wav, ogg, mp3 or flac",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio file")
    if len(data) > _AUDIO_MAX_BYTES:
        raise HTTPException(status_code=400, detail="audio too large; max 25 MB")

    # Normalise language to ISO-639-1 (Whisper's expected format)
    lang = (language or "").lower().strip()[:2] or "hi"

    with check_and_record(user.id, "draft", endpoint="transcribe", email=user.email) as _record:
        try:
            from groq import Groq
            client = Groq(api_key=os.environ["GROQ_API_KEY"])
            # Pick a filename + media type Whisper will accept. The SDK
            # expects (filename, bytes, mime_type) tuple.
            ext = {
                "audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav",
                "audio/x-wav": "wav", "audio/mp4": "m4a", "audio/m4a": "m4a",
                "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/flac": "flac",
            }.get(base_mt, "webm")
            resp = client.audio.transcriptions.create(
                file=(f"audio.{ext}", data, base_mt),
                model=os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
                language=lang,
                response_format="json",
                temperature=0.0,
            )
            text = (resp.text or "").strip()
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Transcription failed: {e}")

        # Whisper free tier. Roughly 100p per call as a rough estimate so
        # the cost meter shows non-zero activity. Free in practice.
        _record(cost_paise=100, model="whisper-large-v3-turbo")
        return {"ok": True, "text": text, "language": lang}


# ----------------------------------------------------------- Smart Drafter
# Conversational AI drafter: lawyer describes the matter (voice or text),
# AI conductor asks contextual follow-ups, then generates the full document.
# See headnote/drafter/compose.py for the conductor logic + template registry.

class ComposeBody(BaseModel):
    doc_type:     str
    conversation: list[dict] = Field(default_factory=list, description="Prior chat turns")
    collected:    dict       = Field(default_factory=dict, description="Fields filled so far")
    user_message: Optional[str] = Field(None, description="Latest user utterance (text or voice transcript)")
    lang:         Literal["hi", "en"] = "hi"
    force_draft:  bool = Field(False, description="Skip remaining questions and generate now")


@router.post("/compose", summary="Conversational AI drafter — ask questions or generate document")
def compose(
    body: ComposeBody,
    user: CurrentUser = Depends(get_current_user),
):
    """One step of the conversational drafter.

    Lawyer either gives the latest answer (`user_message`) or hits
    "Draft Now" (`force_draft=True`). The conductor either returns the
    next question to ask or the generated document.
    """
    from headnote.drafter.compose import conductor_step

    if not body.doc_type:
        raise HTTPException(status_code=400, detail="doc_type required")

    with check_and_record(user.id, "draft", endpoint="compose", email=user.email) as _record:
        try:
            result = conductor_step(
                doc_type=body.doc_type,
                conversation=body.conversation,
                collected=body.collected,
                user_message=body.user_message,
                lang=body.lang,
                force_draft=body.force_draft,
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"compose failed: {e}")

        # Cost estimate (DeepSeek V3): asking ~30p, full generation ~80p
        cost = 80 if result.get("status") == "ready" else 30
        _record(cost_paise=cost, model="deepseek-chat")
        return result


class PolishTextBody(BaseModel):
    text:           str
    field_key:      Optional[str] = None
    field_label:    Optional[str] = None
    doc_type:       Optional[str] = None
    lang:           Literal["hi", "en"] = "hi"
    style:          Literal["formal", "neutral", "concise"] = "formal"


@router.post("/polish-text", summary="Polish free-form lawyer input into formal legal prose")
def polish_text(
    body: PolishTextBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Take a lawyer's quick-and-dirty story / notes and refine into the
    formal language a court draft expects. Preserves facts, dates, names,
    statute references unchanged — only fixes grammar, formality, and flow.
    """
    from headnote.drafter.compose import _llm_call, get_template

    text = (body.text or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="text is empty")

    doc_ctx = ""
    if body.doc_type:
        tpl = get_template(body.doc_type)
        if tpl:
            doc_ctx = f" The text is intended for a {tpl['name_en']} ({tpl['name_hi']}) being drafted."
    field_ctx = ""
    if body.field_label:
        field_ctx = f" Specifically, it goes into the '{body.field_label}' field."

    if body.lang == "hi":
        sys = (
            "You are a senior Indian advocate. Polish the lawyer's raw text "
            "into formal court Hindi (Devanagari) suitable for a legal "
            "document.{ctx}{field}\n\n"
            "RULES:\n"
            "- Preserve ALL facts, names, dates, statute references, FIR/case "
            "  numbers, addresses verbatim.\n"
            "- Use formal court-Hindi register (माननीय, सादर निवेदन, यह कि, "
            "  आवेदक, अधिवक्ता).\n"
            "- Fix grammar, spelling, and flow.\n"
            "- Remove filler words ('um', 'so', 'basically') and 'मतलब', 'यानी'.\n"
            "- Keep length similar — don't pad or shrink dramatically.\n"
            "- Output PURE Devanagari — no Latin letters mixed in.\n"
            "- Return ONLY the polished text. No preamble, no explanation, "
            "  no markdown fences."
        ).format(ctx=doc_ctx, field=field_ctx)
    else:
        sys = (
            "You are a senior Indian advocate. Polish the lawyer's raw text "
            "into formal Indian legal English suitable for a court document."
            "{ctx}{field}\n\n"
            "RULES:\n"
            "- Preserve ALL facts, names, dates, statute references, FIR/case "
            "  numbers, addresses verbatim.\n"
            "- Use formal Indian legal English register ('It is most "
            "  respectfully submitted', 'humbly states', 'the applicant').\n"
            "- Fix grammar, spelling, and flow.\n"
            "- Remove filler words and casual phrasing.\n"
            "- Keep length similar — don't pad or shrink dramatically.\n"
            "- Return ONLY the polished text. No preamble, no markdown fences."
        ).format(ctx=doc_ctx, field=field_ctx)

    user_prompt = f"Polish this text:\n\n{text}"

    with check_and_record(user.id, "draft", endpoint="polish_text", email=user.email) as _record:
        try:
            polished = _llm_call(sys, user_prompt, max_tokens=1200, model="fast")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"polish failed: {e}")

        polished = polished.strip()
        # Strip code fences if model wrapped output
        if polished.startswith("```"):
            polished = re.sub(r"^```(?:[a-z]+)?\s*", "", polished)
            polished = re.sub(r"\s*```$", "", polished)
        _record(cost_paise=80, model="llama-3.1-8b-instant")
        return {"ok": True, "polished": polished, "original_length": len(text), "polished_length": len(polished)}


class RenderTemplateBody(BaseModel):
    doc_type: str
    fields:   dict = Field(default_factory=dict)
    lang:     Literal["hi", "en", "mr", "bn", "gu"] = "hi"


@router.post("/render-template", summary="Render a complete document from filled template fields")
def render_template(
    body: RenderTemplateBody,
    user: CurrentUser = Depends(get_current_user),
):
    """One-shot document generation from a fully (or partially) filled
    template. Used by the universal template-drafter page on the lawyer's
    "Generate" press — same machinery as Smart Drafter's final step but
    without the conversational interview.

    Empty fields are passed through as [BLANK] placeholders so the lawyer
    can see the document take shape progressively.
    """
    from headnote.drafter import template_adapter as TA
    if TA.is_canonical(body.doc_type):                  # V2 canonical engine — deterministic, free
        try:
            return {"ok": True, "document": TA.document(body.doc_type, body.fields or {}, body.lang)}
        except Exception as e:
            # A malformed field value must never take down the live preview with a
            # raw 500. Surface a readable error the editor can toast instead.
            import logging
            logging.getLogger("headnote.drafter").exception("canonical render failed: %s", body.doc_type)
            raise HTTPException(status_code=502, detail=f"render failed: {type(e).__name__}: {e}")

    from headnote.drafter.compose import get_template, _generate_document

    template = get_template(body.doc_type)
    if not template:
        raise HTTPException(status_code=400, detail=f"unknown doc_type '{body.doc_type}'")

    with check_and_record(user.id, "draft", endpoint="render_template", email=user.email) as _record:
        try:
            doc = _generate_document(template, body.fields or {}, body.lang)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"render failed: {e}")
        _record(cost_paise=80, model="deepseek-chat")
        return {"ok": True, "document": doc}


class RegionalizeBody(BaseModel):
    html: str                                   # already-rendered Hindi document HTML
    lang: Literal["mr", "bn", "gu"] = "mr"


@router.post("/regionalize", summary="Translate an already-rendered Hindi draft into a regional language")
def regionalize_html(body: RegionalizeBody):
    """Universal regional-language path for ANY drafting surface. A page sends
    already-rendered Hindi (a fragment or a full standalone page) and gets it
    back in Marathi/Bengali/Gujarati — verified-cache boilerplate + LLM-glossary
    for the rest — with a 'machine draft' banner unless every string is
    advocate-verified.

    Open (no auth) to match /render-live and /from-prompt: the SPA prompt drafter
    is unauthenticated, and this only translates already-produced draft HTML.
    Style/script/head text is skipped, so full pages are safe to post.
    """
    from headnote.drafter.i18n.render import regionalize
    from headnote.drafter.template_adapter import _MACHINE_DRAFT_BANNER
    try:
        out, rep = regionalize(body.html or "", body.lang)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"regionalize failed: {e}")
    if not rep.get("verified"):
        out = _MACHINE_DRAFT_BANNER + out
    return {"ok": True, "document": out, "report": rep}
