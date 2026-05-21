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

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
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

    with check_and_record(user.id, "draft", endpoint="draft_start") as _record:
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

@router.post("/translate-fields", summary="Translate bail-form prose fields EN↔HI")
async def translate_fields(
    body: TranslateFieldsBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Translate the prose fields of a bail application form in either direction.

    Only non-empty string values are translated. Proper nouns (names, case
    numbers, dates, statute refs) are preserved by the prompt instruction.

    Backend: Groq Llama-3.3-70b (free tier) primary, Anthropic Haiku fallback.

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
        "You are a bilingual converter for Indian bail-application form fields. "
        "Your job: for each value in the given JSON, OUTPUT THE SAME CONTENT in the "
        "target script/language. Use these rules per field:\n"
        "• Person names (applicant_name, applicant_father, advocate_name, "
        "trial_judge): TRANSLITERATE phonetically to the target script. "
        "E.g., 'Anil Morya' → 'अनिल मोर्य'; 'श्री राम सिंह' → 'Shri Ram Singh'.\n"
        "• Place names, addresses, district, state, police station, jail names: "
        "TRANSLITERATE to the target script (use the conventional Indian-English "
        "spelling for places, e.g. 'Gwalior' ↔ 'ग्वालियर', 'Madhya Pradesh' ↔ "
        "'मध्य प्रदेश').\n"
        "• Court names + judge titles: TRANSLATE using standard Indian legal "
        "vocabulary (e.g. 'MP High Court Gwalior Bench' ↔ "
        "'माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ, ग्वालियर'; "
        "'2nd Additional Sessions Judge' ↔ 'द्वितीय अपर सत्र न्यायाधीश').\n"
        "• Occupation: TRANSLATE ('Shopkeeper' ↔ 'दुकानदारी').\n"
        "• Long prose (facts_narrative, cancellation_history, lower_court_history, "
        "custom_ground_1, grounds_medical): TRANSLATE naturally using formal legal "
        "Hindi/English. Keep statute refs (IPC, CrPC, BNS, §138, S.302 etc.), "
        "FIR/case numbers, and dates unchanged within the prose.\n"
        "Always return ONLY a JSON object with the same keys as input. No prose, "
        "no markdown fences, no commentary."
    )
    prompt = (
        f"Convert every value below to {target_name}. Apply the per-field rules "
        "from the system prompt. Return ONLY the JSON object.\n\n"
        f"{fields_json}"
    )

    with check_and_record(user.id, "draft", endpoint="translate_fields") as _record:
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

        cost_paise = 50  # Groq free tier; flat estimate for the cost meter
        _record(cost_paise=cost_paise, model="llama-3.3-70b-versatile")
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

    with check_and_record(user.id, "draft", endpoint="ocr_fir") as _record:
        try:
            parsed = ocr_fir_pages(pages)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        # Cost scales roughly with page count. 300p per page is conservative.
        _record(cost_paise=300 * len(pages), model="claude-sonnet-4-6-vision")
        return {"ok": True, "page_count": len(pages), "extracted": parsed}


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

    with check_and_record(user.id, "draft", endpoint="transcribe") as _record:
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

    with check_and_record(user.id, "draft", endpoint="compose") as _record:
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

        # Cost estimate: asking = ~haiku (50p), generating = ~sonnet (600p)
        cost = 600 if result.get("status") == "ready" else 50
        _record(cost_paise=cost, model="sonnet+haiku-compose")
        return result


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

    with check_and_record(user.id, "draft", endpoint="render_template") as _record:
        try:
            doc = _generate_document(template, body.fields or {}, body.lang)
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"render failed: {e}")
        _record(cost_paise=600, model="llama-3.3-70b-versatile")
        return {"ok": True, "document": doc}
