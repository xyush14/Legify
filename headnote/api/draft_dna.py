"""GET / PATCH / analyze  →  /api/draft-dna — the advocate's "Draft DNA".

Draft DNA is a per-advocate StyleProfile distilled from 2–3 of their own filed
drafts. Once saved, every prompt-drafted document comes out in their house format
(see headnote/drafter/style_profile.py + docs/DRAFT_DNA_DESIGN.md).

Endpoints
---------
  POST  /api/draft-dna/analyze   upload 2–3 filed drafts → OCR → analyze_style →
                                 a PROPOSED profile for the confirm/edit screen.
                                 Extract-then-discard: the uploaded text is never
                                 persisted — only the profile the advocate saves.
  GET   /api/draft-dna           read the saved profile (null if none).
  PATCH /api/draft-dna           save the confirmed/edited profile (or clear it).

Stored as one `draft_style` jsonb column on public.user_profiles
(migrations/010_draft_dna.sql). Facts are never learned — DNA is format-side only.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from headnote.drafter import office, style_profile
from headnote.entitlements import CurrentUser, check_and_record, get_current_user

log = logging.getLogger("headnote.api.draft_dna")
router = APIRouter(prefix="/api/draft-dna", tags=["draft-dna"])

_MAX_FILES = 5           # a couple of filed drafts is plenty to learn a style
_MAX_BYTES = 20 * 1024 * 1024


class SaveDnaBody(BaseModel):
    profile: Optional[dict] = Field(
        None, description="The confirmed/edited StyleProfile. null/omitted clears the DNA.")
    clear: bool = Field(False, description="True to delete the saved DNA.")


@router.get("", summary="Read the signed-in advocate's saved Draft DNA")
def get_draft_dna(user: CurrentUser = Depends(get_current_user)) -> dict:
    profile = style_profile.load_style(user.id)
    return {"ok": True, "has_dna": profile is not None, "draft_style": profile}


@router.patch("", summary="Save (or clear) the confirmed Draft DNA")
def patch_draft_dna(body: SaveDnaBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    profile = None if (body.clear or body.profile is None) else body.profile
    try:
        stored = style_profile.save_style(user.id, profile)
    except Exception as e:
        log.exception("save Draft DNA failed for %.8s", user.id)
        raise HTTPException(status_code=502, detail=f"could not save Draft DNA: {e}")
    return {"ok": True, "has_dna": stored is not None, "draft_style": stored}


@router.post("/analyze", summary="OCR 2–3 filed drafts → a proposed Draft DNA (not saved)")
async def analyze_draft_dna(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Read the advocate's uploaded drafts and propose a StyleProfile. Does NOT
    save — the frontend shows it for confirm/light-edit, then PATCHes to persist.
    Extract-then-discard: OCR text lives only for this request."""
    uploads: List[UploadFile] = []
    if files:
        uploads.extend(files)
    if file:
        uploads.append(file)
    if not uploads:
        return JSONResponse({"ok": False, "error": "attach at least one of your filed drafts"}, status_code=400)
    if len(uploads) > _MAX_FILES:
        return JSONResponse({"ok": False, "error": f"too many files ({len(uploads)}); max {_MAX_FILES}"}, status_code=400)

    from headnote.drafter.ocr import ocr_text_pages

    # OCR each upload independently so analyze_style sees per-draft texts (a more
    # reliable aggregate than one merged blob).
    with check_and_record(user.id, "draft", endpoint="draft_dna_analyze", email=user.email):
        texts: list[str] = []
        for up in uploads:
            entry = (await up.read(), up.content_type or "", up.filename or "")
            try:
                pages, office_text = office.collect_uploads([entry], max_bytes=_MAX_BYTES)
            except ValueError as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=400)
            try:
                txt = await run_in_threadpool(ocr_text_pages, pages, office_text=office_text)
            except Exception as e:
                log.warning("Draft DNA OCR degraded for one upload: %s", e)
                txt = (office_text or "").strip()
            if (txt or "").strip():
                texts.append(txt.strip())

        if not texts:
            return JSONResponse({"ok": False, "error":
                                 "आपके दस्तावेज़ पढ़े नहीं जा सके — साफ़ फोटो/PDF के साथ दोबारा कोशिश करें। "
                                 "(Could not read your drafts — try clearer photos/PDFs.)"})
        profile = await run_in_threadpool(style_profile.analyze_style, texts, "hi")

    return {"ok": True, "draft_style": profile}
