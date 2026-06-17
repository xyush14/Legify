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
from pydantic import BaseModel, Field

from headnote.drafter import storage, stories
from headnote.entitlements import (
    CurrentUser,
    check_and_record,
    get_current_user,
)


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
    user: CurrentUser = Depends(get_current_user),
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

    with check_and_record(user.id, "draft", endpoint="translate_fields", email=user.email) as _record:
        try:
            raw = _llm_call(system, prompt, max_tokens=3000, model="quality")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Translation failed: {e}")

        # Strip fences if model wrapped output
        text = raw.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```$", "", text.strip())

        try:
            translated = json.loads(text)
        except json.JSONDecodeError:
            m = re.search(r"\{.*\}", text, re.DOTALL)
            if m:
                try:
                    translated = json.loads(m.group(0))
                except json.JSONDecodeError:
                    translated = to_translate  # fallback: return originals unchanged
            else:
                translated = to_translate

        cost_paise = 40  # DeepSeek V3; flat estimate for the cost meter
        _record(cost_paise=cost_paise, model="deepseek-chat")
        return {"translated": translated}


# ----------------------------------------------------------- OCR

_OCR_ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
}
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

    pages: list[tuple[bytes, str]] = []
    for idx, up in enumerate(uploads, start=1):
        mt = up.content_type or ""
        if mt not in _OCR_ALLOWED_MIME:
            raise HTTPException(
                status_code=400,
                detail=f"page {idx}: unsupported file type {mt!r}; use JPEG, PNG, WebP, GIF, or PDF",
            )
        data = await up.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"page {idx}: empty file")
        if len(data) > _OCR_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"page {idx}: too large; max 20 MB")
        pages.append((data, mt))

    with check_and_record(user.id, "draft", endpoint="ocr_fir", email=user.email) as _record:
        try:
            parsed = ocr_fir_pages(pages)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        # Cost scales roughly with page count. 300p per page is conservative.
        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(pages), "extracted": parsed}


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

    pages: list[tuple[bytes, str]] = []
    for idx, up in enumerate(uploads, start=1):
        mt = up.content_type or ""
        if mt not in _OCR_ALLOWED_MIME:
            raise HTTPException(
                status_code=400,
                detail=f"page {idx}: unsupported file type {mt!r}; use JPEG, PNG, WebP, GIF, or PDF",
            )
        data = await up.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"page {idx}: empty file")
        if len(data) > _OCR_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"page {idx}: too large; max 20 MB")
        pages.append((data, mt))

    with check_and_record(user.id, "draft", endpoint="ocr_bail_order", email=user.email) as _record:
        try:
            parsed = ocr_bail_order_pages(pages)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(pages), "extracted": parsed}


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

    pages: list[tuple[bytes, str]] = []
    for idx, up in enumerate(uploads, start=1):
        mt = up.content_type or ""
        if mt not in _OCR_ALLOWED_MIME:
            raise HTTPException(
                status_code=400,
                detail=f"page {idx}: unsupported file type {mt!r}; use JPEG, PNG, WebP, GIF, or PDF",
            )
        data = await up.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"page {idx}: empty file")
        if len(data) > _OCR_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"page {idx}: too large; max 20 MB")
        pages.append((data, mt))

    with check_and_record(user.id, "draft", endpoint="ocr_impugned_order", email=user.email) as _record:
        try:
            parsed = ocr_impugned_order_pages(pages)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(pages), "extracted": parsed}


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

    pages: list[tuple[bytes, str]] = []
    for idx, up in enumerate(uploads, start=1):
        mt = up.content_type or ""
        if mt not in _OCR_ALLOWED_MIME:
            raise HTTPException(status_code=400, detail=f"page {idx}: unsupported file type {mt!r}; use JPEG, PNG, WebP, GIF, or PDF")
        data = await up.read()
        if not data:
            raise HTTPException(status_code=400, detail=f"page {idx}: empty file")
        if len(data) > _OCR_MAX_BYTES:
            raise HTTPException(status_code=400, detail=f"page {idx}: too large; max 20 MB")
        pages.append((data, mt))

    with check_and_record(user.id, "draft", endpoint="ocr_generic", email=user.email) as _record:
        try:
            extracted = ocr_generic_pages(pages, fields, doc_label)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=0, model="groq/llama-4-scout-vision")
        return {"ok": True, "page_count": len(pages), "extracted": extracted}


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
    lang:     Literal["hi", "en"] = "hi"


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
