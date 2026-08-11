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

Who can reach this
------------------
Every SIGNED-IN advocate — `get_current_user` throughout, no beta gate.

The layout-mirroring endpoints (/layout, /capture, /template, /generate, /render)
were originally `require_beta` because they were new and only /draft-dna called
them. The beta is over (V2 is public), and they are now called from the fields
drafting screen too, which every paying user is on. Leaving them gated meant the
whole feature would silently switch off for everybody the moment `V2_PUBLIC` was
unset — a one-env-var outage of the product's main differentiator. Draft DNA is
per-advocate by construction (everything is keyed by his own user id), so there
is nothing here a signed-in user should not reach for himself.
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from headnote.drafter import office, style_profile
from headnote.entitlements import (
    CurrentUser,
    check_and_record,
    get_current_user,
)

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


# ===========================================================================
# LAYOUT DNA — exact-layout mirroring (page/margins/indents/tabs/tables/font).
# Capture the advocate's .docx layout, save it under his id, and render new
# drafts into it in his own font. Works for any advocate / language.
# ===========================================================================
def _layout_summary(tpl: Optional[dict]) -> dict:
    """What the Draft DNA screen needs to show — and to DRAW the advocate's page:
    page geometry, each block's real format, and the per-signal confidence."""
    if not tpl:
        return {"has_layout": False}
    from headnote.drafter import layout_template as LT
    return {
        "has_layout": True,
        "font": LT.template_primary_font(tpl),
        "page": tpl.get("page", {}),
        "roles": sorted((tpl.get("roles") or {}).keys()),
        "role_formats": tpl.get("roles", {}),
        "tables": tpl.get("tables") or [],
        "n_drafts": tpl.get("n_drafts"),
        "confidence": tpl.get("confidence", {}),
        # his own page, block by block — shown on the confirm screen so he can see
        # a faithful reproduction rather than a mock-up. Not persisted.
        "preview_blocks": tpl.get("preview_blocks") or [],
        # which document types he has an EXACT template for (his own file reused)
        "skeletons": (tpl.get("skeletons") or {}),
    }


@router.get("/layout", summary="The advocate's saved LAYOUT template (summary)")
def get_layout(user: CurrentUser = Depends(get_current_user)) -> dict:
    return {"ok": True, **_layout_summary(style_profile.load_layout(user.id))}


@router.post("/capture", summary="Upload filed .docx drafts → learn + SAVE the advocate's format (his id)")
async def capture_layout_dna(
    files: Optional[List[UploadFile]] = File(None),
    file: Optional[UploadFile] = File(None),
    doc_type: str = Form("general"),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Read the advocate's own .docx filings and persist his format under his id.

    Two drafts of the SAME type give the exact path: his own file becomes the
    template and only case-specific values are swapped. A single draft still gives
    his measured geometry + font. Needs real .docx — a scan has no layout inside."""
    from headnote.drafter import dna_layout

    uploads: List[UploadFile] = list(files or [])
    if file:
        uploads.append(file)
    if not uploads:
        return JSONResponse({"ok": False, "error": "attach at least one filed .docx draft"}, status_code=400)
    if len(uploads) > _MAX_FILES:
        return JSONResponse({"ok": False, "error": f"too many files; max {_MAX_FILES}"}, status_code=400)

    payload: list = []
    for up in uploads:
        name = up.filename or ""
        if not name.lower().endswith(".docx"):
            continue
        data = await up.read()
        if data and len(data) <= _MAX_BYTES:
            payload.append((data, name))
    if not payload:
        return JSONResponse({"ok": False, "error":
                             "your format is read from Word files (.docx) — a scan or PDF has no "
                             "layout stored inside it"}, status_code=400)

    with check_and_record(user.id, "draft", endpoint="draft_dna_capture", email=user.email):
        try:
            tpl = await run_in_threadpool(dna_layout.capture_and_save, user.id, payload,
                                          doc_type=doc_type)
        except Exception as e:
            log.exception("format capture failed for %.8s", user.id)
            raise HTTPException(status_code=502, detail=f"could not save your format: {e}")
    if not tpl.get("roles") and not tpl.get("exact_for"):
        return JSONResponse({"ok": False, "error":
                             "could not read the structure of these drafts — try your standard filed format"})
    return {"ok": True, **_layout_summary(tpl),
            "exact_for": tpl.get("exact_for"),
            "skeletons": tpl.get("skeletons") or {},
            "template_preview": tpl.get("template_preview") or [],
            "fields": tpl.get("fields") or []}


@router.get("/template/{doc_type}", summary="The advocate's extracted template for one type")
def get_template(doc_type: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """What Headnote will reuse verbatim from his own filing, and which values it
    will fill — so he can see the template before trusting it."""
    from headnote.drafter import dna_layout, doc_skeleton

    spine, skel = dna_layout.load_skeleton(user.id, doc_type)
    if not (spine and skel):
        return {"ok": True, "has_template": False, "doc_type": doc_type}
    return {"ok": True, "has_template": True, "doc_type": doc_type,
            "n_docs": skel.get("n_docs"), "coverage": skel.get("coverage"),
            "blocks": len(skel.get("blocks") or []),
            "slots": doc_skeleton.slot_count(skel),
            "fields": doc_skeleton.slot_fields(skel),
            "template_preview": dna_layout.template_preview(skel)}


class GenerateBody(BaseModel):
    doc_type: str = Field("general")
    values: dict = Field(default_factory=dict,
                         description="field_label → value (or '<block>.<slot>' → value)")
    blocks: Optional[list] = Field(None, description="fallback content when there is no template")
    lang: str = Field("hi")


@router.post("/generate", summary="A draft in the advocate's own format → .docx")
async def generate_in_format(body: GenerateBody,
                             user: CurrentUser = Depends(get_current_user)) -> dict:
    """Fills his own filing (exact) when he has one for this type; otherwise renders
    into his measured geometry. `how` says which path produced it."""
    from headnote.drafter import dna_layout

    data, how = await run_in_threadpool(
        dna_layout.generate, user.id, doc_type=body.doc_type,
        values=body.values, blocks=body.blocks, lang=body.lang)
    if not data:
        return JSONResponse({"ok": False, "error":
                             "no saved format yet — add a couple of your filed drafts first"},
                            status_code=400)
    import base64
    return {"ok": True, "how": how, "filename": f"{body.doc_type or 'draft'}.docx",
            "docx_base64": base64.b64encode(data).decode("ascii")}


class RenderLayoutBody(BaseModel):
    blocks: Optional[list] = Field(None, description="[[role, text], …] already tagged")
    lines: Optional[List[str]] = Field(None, description="[text, …] — labelled server-side")
    lang: str = Field("hi")


@router.post("/render", summary="Render content INTO the advocate's saved layout (his font) → .docx")
async def render_in_layout(body: RenderLayoutBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    from headnote.drafter import dna_layout

    src = body.blocks if body.blocks else (body.lines or [])
    if not src:
        return JSONResponse({"ok": False, "error": "nothing to render"}, status_code=400)
    if not dna_layout.has_layout(user.id):
        return JSONResponse({"ok": False, "error": "no saved layout — upload your drafts first"}, status_code=400)
    data = await run_in_threadpool(dna_layout.apply_layout, user.id, src, lang=body.lang)
    if not data:
        return JSONResponse({"ok": False, "error": "could not render into your layout"}, status_code=502)
    import base64
    return {"ok": True, "filename": "draft.docx", "docx_base64": base64.b64encode(data).decode("ascii")}
