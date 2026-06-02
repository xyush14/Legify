"""Official judgment corpus API — browse the SC open-data set and stream the
ACTUAL official judgment PDF.

  GET /api/judgment/search?q=...   → metadata hits (court-accepted citations)
  GET /api/judgment/pdf/{doc_id}   → the real official judgment PDF bytes
  GET /api/judgment/stats          → corpus counts (health/admin)

The PDF route is the answer to "when a user taps a judgment they just get the
actual judgment copy PDF": doc_id "sc:<path>" → a single HTTP Range fetch of
that PDF's bytes out of the year tar on AWS Open Data, cached locally (LRU).

Left open (un-metered) to match the existing /api/case viewer endpoint; a
`judgment_read` gate can be layered on later via the entitlements module.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

import requests

from headnote.judgments import opendata


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/judgment", tags=["judgments"])


def _serialize(j: opendata.SCJudgment) -> dict:
    return {
        "doc_id": j.doc_id,
        "title": j.title or f"{j.petitioner} v. {j.respondent}",
        "petitioner": j.petitioner,
        "respondent": j.respondent,
        "neutral_citation": j.neutral_citation,
        "scr_citation": j.scr_citation,
        "citation": j.best_citation,
        "cnr": j.cnr,
        "court": j.court,
        "judge": j.judge,
        "author_judge": j.author_judge,
        "date": j.decision_date,
        "disposal": j.disposal_nature,
        "year": j.year,
        "pdf_url": f"/api/judgment/pdf/{j.doc_id}",
    }


@router.get("/search", summary="Search the official SC judgment corpus")
def search_judgments(
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(25, ge=1, le=100),
) -> dict:
    results = opendata.search(q, limit=limit)
    return {"query": q, "count": len(results),
            "results": [_serialize(j) for j in results]}


@router.get("/fulltext", summary="Full-text fact-pattern search over SC judgments")
def fulltext_search(
    q: str = Query(..., min_length=2, max_length=400),
    limit: int = Query(12, ge=1, le=50),
) -> dict:
    """Relevance-ranked (FTS5/BM25) search over the EXTRACTED text of the
    official SC judgments — the discovery layer behind research mode. Returns
    each hit with its court-accepted citation + official PDF url. Empty until
    text has been extracted (scripts/extract_sc_text.py)."""
    results = opendata.search_fulltext(q, limit=limit)
    return {"query": q, "count": len(results),
            "results": [_serialize(j) for j in results]}


@router.get("/stats", summary="Official judgment corpus stats")
def judgment_stats() -> dict:
    return opendata.corpus_stats()


@router.get("/pdf/{doc_id:path}", summary="Stream the actual official judgment PDF")
def get_judgment_pdf(doc_id: str):
    """Return the official judgment PDF bytes for ``sc:<path>``.

    Inline disposition so it renders directly in the browser / an <iframe>;
    immutable so it caches hard at the edge and in the browser.
    """
    try:
        result = opendata.resolve_pdf(doc_id)
    except requests.RequestException as e:
        log.warning("pdf fetch failed for %s: %s", doc_id, e)
        raise HTTPException(status_code=502,
                            detail="Could not fetch the official judgment PDF "
                                   "from source. Please retry.")
    if not result:
        raise HTTPException(status_code=404,
                            detail=f"No official PDF available for {doc_id}")
    pdf, filename = result
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"',
            "Cache-Control": "public, max-age=604800, immutable",
            "X-Judgment-Source": "Supreme Court of India / AWS Open Data CC-BY-4.0",
        },
    )
