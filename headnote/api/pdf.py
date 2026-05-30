"""Server-side PDF export for drafted documents — POST /api/draft/pdf.

Replaces the old client-side html2canvas pipeline, which rasterized the
document to a JPEG and so mangled Devanagari (broken conjuncts/matras) and
multi-page breaks, and produced a non-selectable image-PDF. The browser now
sends the rendered document HTML (all <style> blocks + the #doc-page markup)
and we render it to a REAL, text-selectable PDF with WeasyPrint:

  - Pango shapes Devanagari correctly using the Noto Serif/Sans Devanagari
    fonts installed in the image (see Dockerfile).
  - Latin / statute text falls back to Liberation Serif (Times metrics).
  - The document's own @page + page-break CSS is honoured natively, so a
    multi-page bail application splits cleanly (signature / prayer unsplit).

The same PDF blob powers all three toolbar buttons: Download, WhatsApp share
(a real file attachment), and print fallback.

Security: the HTML is the lawyer's own document, rendered back only to that
same authenticated user — never stored, never shared. We still strip
<script>/<iframe>/<object>/<link>/<base> and block every non-`data:` URL
fetch, so a crafted payload cannot make the server pull internal resources
(SSRF) or run remote content.
"""

from __future__ import annotations

import logging
import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/draft", tags=["draft-pdf"])

# Hard cap on the posted HTML. A bail application + index + affidavit, with
# all the page CSS inlined, is comfortably under this; anything larger is
# abuse rather than a real court document.
_MAX_HTML = 800_000

# Tags that are dropped before rendering: active content + remote resources.
_STRIP_TAGS = ("script", "iframe", "object", "embed", "link", "base")

# Injected as an author stylesheet AFTER the document's own <style> (so these
# !important rules win the cascade). Intentionally tiny:
#   1. Scope the font stack to the document so the *installed* server fonts
#      are used — the page's own stack names 'Times New Roman' / Google fonts
#      that don't exist in the container. Per-glyph fallback then routes Latin
#      to Liberation Serif (Times metrics) and Devanagari to Noto Serif
#      Devanagari (correct conjuncts).
#   2. Pin the grid-based party block (page CSS: grid 110px 16px 1fr) to a CSS
#      table — WeasyPrint's table support is rock-solid, so the label / dots /
#      detail columns never collapse.
#   3. Strip any screen-only card chrome (max-width, shadow, centering) off
#      #doc-page so it fills the printable page.
# We deliberately do NOT set @page here — the document's print CSS already
# defines A4 size + tuned margins, and we want to respect those.
_EXPORT_CSS = """
#doc-page, #doc-page * {
  font-family: 'Liberation Serif', 'Noto Serif Devanagari',
               'Noto Sans Devanagari', 'DejaVu Serif', serif !important;
}
#doc-page {
  width: auto !important; max-width: none !important;
  margin: 0 !important; padding: 0 !important;
  box-shadow: none !important; background: #fff !important;
}
/* Real data tables print with crisp borders. Scoped to <table> so it never
   touches the party block below (rendered AS a table out of <div>s). The
   bail page already borders its tables; the template page does not, so this
   also fixes borderless template tables. */
#doc-page table { border-collapse: collapse !important; }
#doc-page table th, #doc-page table td {
  border: 1px solid #444 !important; padding: 6px 8px !important;
  vertical-align: top;
}
#doc-page .bd-party {
  display: table !important; width: 100%; table-layout: fixed;
}
#doc-page .bd-party-label  { display: table-cell !important; width: 110px;
                             vertical-align: top; }
#doc-page .bd-party-dots   { display: table-cell !important; width: 16px;
                             vertical-align: top; text-align: center; }
#doc-page .bd-party-detail { display: table-cell !important;
                             vertical-align: top; }
/* The transliteration highlight is a screen aid — print it plain. */
#doc-page .xlit { background: transparent !important; border-bottom: none !important; }
"""


class PdfBody(BaseModel):
    html: str = Field(
        ..., min_length=20, max_length=_MAX_HTML,
        description="Full document HTML: all <style> blocks + the #doc-page markup",
    )
    filename: str = Field(
        "document", max_length=180,
        description="Suggested download name, without extension",
    )


def _safe_filename(name: str) -> str:
    """Collapse anything non-filename-safe to hyphens; never empty."""
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", (name or "").strip()).strip("-._")
    return (base or "document")[:120]


def _no_network_fetcher(url: str):
    """Allow only inline `data:` URIs; block every network/file fetch (SSRF)."""
    if url.startswith("data:"):
        from weasyprint.urls import default_url_fetcher
        return default_url_fetcher(url)
    raise ValueError("external resource blocked")


def _clean_html(raw: str) -> str:
    """Drop active/remote content but keep <style> + the document markup."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    # Strip inline event handlers (defence in depth — WeasyPrint ignores JS).
    for el in soup.find_all(True):
        for attr in [a for a in el.attrs if a.lower().startswith("on")]:
            del el[attr]
    return str(soup)


def _render_pdf(raw_html: str) -> bytes:
    # Import inside the function: if the system libs are missing in some
    # environment, the app must still boot — only this endpoint degrades.
    try:
        from weasyprint import CSS, HTML
    except Exception as e:  # pragma: no cover — only when Pango libs absent
        log.error("weasyprint import failed (system libs missing?): %s", e)
        raise HTTPException(status_code=503, detail="PDF service unavailable")

    cleaned = _clean_html(raw_html)
    try:
        return HTML(
            string=cleaned, base_url=None, url_fetcher=_no_network_fetcher,
        ).write_pdf(stylesheets=[CSS(string=_EXPORT_CSS)])
    except HTTPException:
        raise
    except Exception as e:
        log.exception("weasyprint render failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not render the PDF")


@router.post("/pdf", summary="Render the drafted document to a real-text PDF")
def render_document_pdf(
    body: PdfBody,
    user: CurrentUser = Depends(get_current_user),
):
    """Render the posted document HTML to a text-selectable A4 PDF.

    Auth-required: a lawyer can only render their own in-progress document.
    Returns the raw PDF bytes (``application/pdf``) — the client turns the
    blob into a download, a WhatsApp file share, or a print job.
    """
    pdf = _render_pdf(body.html)
    fname = _safe_filename(body.filename)
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{fname}.pdf"',
            "Cache-Control": "no-store",
        },
    )
