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
from typing import Literal, Optional

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
    Uses Haiku 4.5 — typically 1-2 seconds for a typical bail form.

    Gated: draft feature (same quota as draft_start).
    """
    from headnote.llm.client import call_claude_cached

    # Filter to non-empty string values only
    to_translate = {k: v for k, v in (body.fields or {}).items()
                    if isinstance(v, str) and v.strip()}
    if not to_translate:
        return {"translated": {}, "skipped": True}

    target_name = "Hindi (Devanagari script)" if body.target == "hi" else "English"
    fields_json = json.dumps(to_translate, ensure_ascii=False, indent=2)

    system = (
        "You are a bilingual legal translator for Indian courts. "
        "Translate prose accurately using standard legal terminology. "
        "PRESERVE without change: proper names of people, places, case numbers, "
        "FIR numbers, dates, statute references (IPC, CrPC, BNS, etc.), "
        "police station names, court names, and district names."
    )
    prompt = (
        f"Translate all values in the JSON below to {target_name}. "
        "Return ONLY a valid JSON object with the same keys.\n\n"
        f"{fields_json}"
    )

    with check_and_record(user.id, "draft", endpoint="translate_fields") as _record:
        try:
            raw, usage = call_claude_cached(
                system_prompt=system,
                user_prompt=prompt,
                model="claude-haiku-4-5",
                max_tokens=3000,
                cache=False,
            )
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

        from headnote.llm.client import estimate_cost_usd
        cost_paise = int(estimate_cost_usd(usage) * 8400 * 100)
        _record(cost_paise=cost_paise, model="claude-haiku-4-5")
        return {"translated": translated}


# ----------------------------------------------------------- OCR

@router.post("/ocr-fir", summary="OCR a photographed/scanned FIR → structured fields")
async def ocr_fir(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Claude vision reads the FIR (Hindi or English, printed or handwritten)
    and returns the structured fields needed to pre-fill a bail application.

    Supported: JPEG, PNG, WebP, GIF, PDF (single-page best, multi-page OK).
    Max file size: ~20 MB (Anthropic's limit on vision payloads).

    Gated: draft feature (counts against quota; 402 if exhausted).
    """
    from headnote.drafter.ocr import ocr_fir_image

    if not file.content_type:
        raise HTTPException(status_code=400, detail="file content_type required")
    if file.content_type not in {
        "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
    }:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported file type {file.content_type!r}; use JPEG, PNG, WebP, GIF, or PDF",
        )

    image_bytes = await file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=400, detail="empty file")
    if len(image_bytes) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="file too large; max 20 MB")

    with check_and_record(user.id, "draft", endpoint="ocr_fir") as _record:
        try:
            parsed = ocr_fir_image(image_bytes, media_type=file.content_type)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")

        _record(cost_paise=300, model="claude-sonnet-4-6-vision")  # rough estimate
        return {"ok": True, "extracted": parsed}
