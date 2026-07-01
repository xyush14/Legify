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

from headnote.entitlements import CurrentUser, optional_user


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/draft", tags=["draft-pdf"])

# Hard cap on the posted HTML. A bail application + index + affidavit, with
# all the page CSS inlined, is comfortably under this; anything larger is
# abuse rather than a real court document.
_MAX_HTML = 800_000

# Tags that are dropped before rendering: active content + remote resources.
_STRIP_TAGS = ("script", "iframe", "object", "embed", "link", "base")

# Injected as an author stylesheet AFTER the document's own <style>, so every
# !important rule here wins the cascade — including over inline style="" attrs,
# which `!important` outranks. The posted HTML is a *fragment*: #doc-page lifted
# out of its live .split/.doc-pane parents and shipped with the page's ENTIRE
# <style> (screen rules, @media(max-width:880px), @media print, flex/grid,
# fixed positioning, 85vh/60vh/100vh heights, and — on the template page — an
# inline `display:none` that JS clears only while the page is live). WeasyPrint
# renders in print media, so the chrome-hiding rules already apply; but to
# *guarantee* the document itself paints in normal flow we forcibly neutralise
# everything that could hide it, collapse its height, clip it, or shove it
# off-page. This is what makes Download / WhatsApp stop coming out blank.
#
# It also:
#   - Scopes the font stack to installed server fonts (the page names 'Times
#     New Roman' / Google web-fonts absent in the container); per-glyph
#     fallback routes Latin → Liberation Serif and Devanagari → Noto Serif
#     Devanagari (correct conjuncts).
#   - Pins the grid party block to a CSS table (WeasyPrint table layout is
#     rock-solid; a collapsed grid would drop the parties entirely).
#   - Borders real <table>s and prints the transliteration highlight plain.
# We deliberately do NOT set @page — the document's print CSS already defines
# A4 size + tuned margins, and we respect those.
_EXPORT_CSS = """
/* ── Hard render reset: force the document visible & in normal flow ── */
html, body {
  margin: 0 !important; padding: 0 !important;
  width: auto !important; height: auto !important;
  min-height: 0 !important; max-height: none !important;
  background: #fff !important; color: #000 !important;
  overflow: visible !important;
}
#doc-page {
  display: block !important; position: static !important;
  visibility: visible !important; opacity: 1 !important;
  float: none !important; clip: auto !important;
  width: auto !important; max-width: none !important;
  height: auto !important; min-height: 0 !important; max-height: none !important;
  margin: 0 !important; padding: 0 !important;
  transform: none !important; overflow: visible !important;
  box-shadow: none !important; border: none !important;
  background: #fff !important; color: #000 !important;
}
/* Nothing inside the document may stay hidden or collapsed by a screen rule. */
#doc-page * { visibility: visible !important; }
#doc-page, #doc-page * {
  font-family: 'Liberation Serif', 'Noto Serif Devanagari',
               'Noto Sans Devanagari', 'DejaVu Serif', serif !important;
}
/* Real data tables print with crisp borders. Scoped to <table> so it never
   touches the party block below (rendered AS a table out of <div>s). */
#doc-page table { border-collapse: collapse !important; }
#doc-page table th, #doc-page table td {
  border: 1px solid #444 !important; padding: 6px 8px !important;
  vertical-align: top;
}
/* Mirror the browser grid (auto 1fr 50%): label shrinks, dots fill the
   middle, and the party detail (name + parentage + address) is pinned to
   the RIGHT HALF. Without the explicit 50% the detail cell grabbed all the
   leftover width and the names printed nearly full-page — the very bug the
   browser grid already fixed on screen. table-layout:fixed makes WeasyPrint
   honour these column widths regardless of content length. */
#doc-page .bd-party {
  display: table !important; width: 100%; table-layout: fixed;
}
#doc-page .bd-party-label  { display: table-cell !important; width: 18%;
                             white-space: nowrap; vertical-align: top; }
#doc-page .bd-party-dots   { display: table-cell !important; width: 32%;
                             vertical-align: top; overflow: hidden;
                             white-space: nowrap; }
#doc-page .bd-party-detail { display: table-cell !important; width: 50%;
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


def _clean_html(raw: str) -> tuple[str, int]:
    """Drop active/remote content but keep <style> + the document markup.

    Returns ``(clean_html, doc_text_len)`` where ``doc_text_len`` is the count
    of visible characters inside #doc-page. That length is logged on render so
    a blank PDF can be told apart from empty input: lots of text + a tiny PDF
    means a layout/CSS collapse (server-side), whereas zero text means the
    client serialised an empty document.
    """
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    # Strip inline event handlers (defence in depth — WeasyPrint ignores JS).
    for el in soup.find_all(True):
        for attr in [a for a in el.attrs if a.lower().startswith("on")]:
            del el[attr]
    doc = soup.find(id="doc-page")
    doc_text_len = len(doc.get_text(strip=True)) if doc else 0
    return str(soup), doc_text_len


def _render_pdf(raw_html: str) -> bytes:
    # Import inside the function: if the system libs are missing in some
    # environment, the app must still boot — only this endpoint degrades.
    try:
        from weasyprint import CSS, HTML
    except Exception as e:  # pragma: no cover — only when Pango libs absent
        log.error("weasyprint import failed (system libs missing?): %s", e)
        raise HTTPException(status_code=503, detail="PDF service unavailable")

    cleaned, doc_text_len = _clean_html(raw_html)
    if doc_text_len == 0:
        # The page sent us a document with no text — render will be blank, but
        # the cause is upstream (client serialisation), not WeasyPrint.
        log.warning(
            "draft/pdf: #doc-page empty/missing after clean (input=%d chars)",
            len(raw_html),
        )
    try:
        pdf = HTML(
            string=cleaned, base_url=None, url_fetcher=_no_network_fetcher,
        ).write_pdf(stylesheets=[CSS(string=_EXPORT_CSS)])
    except HTTPException:
        raise
    except Exception as e:
        log.exception("weasyprint render failed: %s", e)
        raise HTTPException(status_code=500, detail="Could not render the PDF")

    # Diagnostics: if the document carried real text but the PDF came back
    # tiny, a screen-only CSS rule collapsed the layout — surface it in the
    # logs instead of shipping a silent blank page.
    n = len(pdf)
    if doc_text_len > 200 and n < 3000:
        log.warning(
            "draft/pdf: suspiciously small PDF (%d bytes) for %d chars of "
            "document text — possible blank render", n, doc_text_len,
        )
    else:
        log.info(
            "draft/pdf rendered: input=%d chars, doc_text=%d chars, pdf=%d bytes",
            len(raw_html), doc_text_len, n,
        )
    return pdf


@router.post("/pdf", summary="Render the drafted document to a real-text PDF")
def render_document_pdf(
    body: PdfBody,
    user: CurrentUser | None = Depends(optional_user),
):
    """Render the posted document HTML to a text-selectable A4 PDF.

    Anonymous-friendly: the standalone public share pages (``/draft/recovery``,
    ``/draft/maintenance`` …) carry no auth token, yet their Print/PDF and
    WhatsApp buttons must still produce the file. The endpoint is a stateless
    render utility — it only ever renders the HTML the caller posts, back to
    that same caller; nothing is stored or cross-user readable, so requiring a
    login added no protection. It stays hardened against SSRF/active content
    (see ``_clean_html`` / ``_no_network_fetcher``).

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
