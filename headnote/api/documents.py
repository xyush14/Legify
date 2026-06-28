"""Document Vault — upload, OCR, store, and search scanned case documents.

POST   /api/documents/upload     OCR an uploaded scan/photo/PDF → store it
GET    /api/documents            list the lawyer's documents (newest first)
GET    /api/documents/search?q=  hybrid keyword + semantic search
GET    /api/documents/{id}       one document (full transcribed text)
DELETE /api/documents/{id}       remove a document

The OCR reuses the same Groq Llama-4-Scout vision pipeline that powers the
drafter's "draft from a document" path (handwriting + Hindi + PDF). The win
here is persistence + search: every upload becomes part of a searchable pile.

Auth required (get_current_user). Locally (SUPABASE_URL unset) that returns the
synthetic dev user, so the flow works tokenless. Upload is metered under the
'draft' feature (Groq is free-tier, so cost is recorded as 0).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile

from headnote.documents import storage as docs_storage
from headnote.entitlements import CurrentUser, check_and_record, get_current_user


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/documents", tags=["documents"])

# Mirror the drafter's OCR upload constraints exactly.
_OCR_ALLOWED_MIME = {
    "image/jpeg", "image/png", "image/webp", "image/gif", "application/pdf",
}
_OCR_MAX_BYTES = 20 * 1024 * 1024
_OCR_MAX_PAGES = 8

# Suggested types for the UI; doc_type is free-text, this is just the menu.
DOC_TYPES = ["postmortem", "fir", "affidavit", "order", "notice",
             "medical", "statement", "agreement", "other"]


@router.post("/upload", summary="OCR a scanned/photographed document and store it")
async def upload_document(
    file: Optional[UploadFile] = File(None),
    files: Optional[List[UploadFile]] = File(None),
    title: str = Form(""),
    doc_type: str = Form(""),
    user: CurrentUser = Depends(get_current_user),
):
    """Transcribe one or more pages (handwritten or printed, Hindi or English,
    image or PDF) and persist them as a searchable document.

    Accepts a single `file` or a list of `files` (multi-page document). The
    pages are OCR'd together and stored as one document.

    Supported: JPEG, PNG, WebP, GIF, PDF. Max 20 MB/page, 8 pages.
    """
    from headnote.drafter.ocr import ocr_text_pages, _rasterize_pdfs, OCR_MARKDOWN_PROMPT

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

    first_name = uploads[0].filename or "document"
    # Build the DISPLAY pages: keep photos as-is, rasterise PDFs to one PNG per
    # page. These are both what we OCR and what we store for the reader's image
    # pane (Groq vision needs images anyway, so this aligns the two).
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
        if mt == "application/pdf":
            pages.extend(_rasterize_pdfs([(data, mt)]))
        else:
            pages.append((data, mt))
    pages = pages[:_OCR_MAX_PAGES]
    if not pages:
        raise HTTPException(status_code=400, detail="no readable pages in upload")

    with check_and_record(user.id, "draft", endpoint="documents_upload", email=user.email) as _record:
        try:
            text = ocr_text_pages(pages, prompt=OCR_MARKDOWN_PROMPT)
        except ValueError as e:
            raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"OCR error: {e}")
        _record(cost_paise=0, model="groq/llama-4-scout-vision")

    if not (text or "").strip():
        raise HTTPException(
            status_code=422,
            detail="couldn't read any text from the document — try a clearer scan",
        )

    clean_title = (title or "").strip() or first_name
    clean_type = (doc_type or "").strip().lower() or "other"
    row = docs_storage.add_document(
        user_id=user.id,
        title=clean_title,
        full_text=text,
        doc_type=clean_type,
        original_filename=first_name,
        mime=pages[0][1],
        pages=pages,
    )
    return {"ok": True, "document": row}


@router.get("", summary="List the lawyer's documents (newest first)")
def list_documents(user: CurrentUser = Depends(get_current_user)) -> dict:
    items = docs_storage.list_documents(user_id=user.id)
    return {"items": items, "count": len(items)}


@router.get("/search", summary="Hybrid keyword + semantic search over the vault")
def search_documents(q: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    results = docs_storage.search_documents(user_id=user.id, query=q)
    return {"query": q, "results": results, "count": len(results)}


@router.get("/{doc_id}", summary="Get one document (full transcribed text)")
def get_document(doc_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    row = docs_storage.get_document(doc_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no document with id={doc_id!r}")
    return row


@router.get("/{doc_id}/page/{page_idx}", summary="Original page image (for the reader)")
def get_page(doc_id: str, page_idx: int,
             user: CurrentUser = Depends(get_current_user)) -> Response:
    page = docs_storage.get_page(doc_id, page_idx, user_id=user.id)
    if page is None:
        raise HTTPException(status_code=404, detail="no such page")
    mime, data = page
    return Response(content=data, media_type=mime,
                    headers={"Cache-Control": "private, max-age=3600",
                             "X-Content-Type-Options": "nosniff"})


@router.get("/{doc_id}/translate", summary="Translate the transcribed text (EN ⇄ हिं)")
def translate_document(doc_id: str, lang: str = "en",
                       user: CurrentUser = Depends(get_current_user)) -> dict:
    """Return the document text in `lang` ('en' or 'hi'). Free Google/MyMemory
    translation (no LLM cost); cached on the document after first call."""
    lang = "hi" if str(lang).lower().startswith("hi") else "en"
    row = docs_storage.get_document(doc_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no document with id={doc_id!r}")

    cached = ((row.get("metadata") or {}).get("translations") or {}).get(lang)
    if cached:
        return {"lang": lang, "text": cached, "cached": True}

    text = docs_storage.translate_text(row.get("full_text") or "", target=lang)
    docs_storage.set_translation(doc_id, user_id=user.id, lang=lang, text=text)
    return {"lang": lang, "text": text, "cached": False}


@router.delete("/{doc_id}", summary="Remove a document")
def delete_document(doc_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    if not docs_storage.delete_document(doc_id, user_id=user.id):
        raise HTTPException(status_code=404, detail=f"no document with id={doc_id!r}")
    return {"ok": True, "deleted": doc_id}
