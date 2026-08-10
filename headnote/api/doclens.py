"""Document Lens API — read any document, translate it, download it as a PDF.

Surfaced as the "Document" tab on /research. Three endpoints, deliberately
stateless: the client holds the text between calls, so a lawyer can read a page,
change his mind about the language twice, and download — without us storing a
police file we were never asked to keep.

Reading is metered; translating and rendering the result are not. The advocate
paid when the page was read, and charging him again to see it in his own
language would be charging twice for one document.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field

from headnote.documents import lens
from headnote.entitlements import CurrentUser, get_current_user

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/doclens", tags=["doclens"])


class TranslateBody(BaseModel):
    text: str = Field(..., max_length=400_000)
    target: str = Field(..., max_length=8)
    source: str = Field("", max_length=8)


class PdfBody(BaseModel):
    text: str = Field(..., max_length=400_000)
    title: str = Field("Document", max_length=200)
    subtitle: str = Field("", max_length=120)
    flags: list[str] = Field(default_factory=list)


def _meter(user: CurrentUser, pages: int) -> None:
    """Count a read against the plan. Never fails the request on a meter error —
    a billing hiccup must not eat a document the advocate already uploaded."""
    try:
        from headnote.entitlements import meters

        meters.increment(user.id, "documents", max(1, pages))
    except Exception:  # noqa: BLE001
        log.warning("doclens: metering failed for %s", user.id, exc_info=True)


@router.post("/read", summary="Read an uploaded document into faithful text")
async def read_document(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    """Any format in — PDF, JPG, PNG, HEIC, WEBP, DOCX, TXT — faithful text out.

    Runs deterministic page preparation before the model sees anything: on real
    phone photos that step is the difference between a usable read and none at
    all (documents/prepare.py carries the measurements).
    """
    data = await file.read()
    try:
        res = await _in_thread(lens.read, data, file.filename or "upload", file.content_type or "")
    except lens.LensError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("doclens read failed")
        raise HTTPException(status_code=500, detail="The document could not be read.") from e
    _meter(user, res.pages)
    return res.as_dict()


@router.post("/translate", summary="Translate read text, refusing to lose a citation")
async def translate_text(
    body: TranslateBody,
    user: CurrentUser = Depends(get_current_user),
) -> dict:
    try:
        res = await _in_thread(lens.translate, body.text, body.target,
                               source_hint=body.source)
    except lens.LensError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        log.exception("doclens translate failed")
        raise HTTPException(status_code=500, detail="The translation could not be made.") from e
    return res.as_dict()


@router.post("/pdf", summary="Download the read or translated text as a PDF")
async def download_pdf(
    body: PdfBody,
    user: CurrentUser = Depends(get_current_user),
) -> Response:
    from headnote.api.pdf import _render_pdf, _safe_filename

    res = lens.LensResult(text=body.text, flags=list(body.flags or []))
    html = lens.to_html(res, title=body.title, subtitle=body.subtitle)
    try:
        pdf = await _in_thread(_render_pdf, html)
    except Exception as e:  # noqa: BLE001
        log.exception("doclens pdf failed")
        raise HTTPException(status_code=500, detail="The PDF could not be made.") from e
    name = _safe_filename(body.title or "document") + ".pdf"
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


async def _in_thread(fn, *a, **kw):
    """Run blocking work off the event loop.

    Reading a document is a multi-second HTTP call to a vision model. Doing that
    on the loop stalls every other request on this single-vCPU machine — which
    is precisely how this site was pulled from the routing pool twice while the
    app itself was perfectly healthy.
    """
    import asyncio
    import functools

    return await asyncio.to_thread(functools.partial(fn, *a, **kw))
