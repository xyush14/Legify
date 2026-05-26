"""GET /case/<doc_id> — internal judgment viewer.

Replaces the "Search Indian Kanoon" garbage-text-search fallback that
was on the case cards. Lawyers click "Read judgment" → land on this
in-app viewer showing the full judgment text we hold in SQLite, with
proper case caption, citation, court, judges, and verification footer.

This is the trust layer for HF-sourced cases:

- Curated cases     → /case/<curated_id> (full vetted content)
- IK live results   → still link to indiankanoon.org for the authoritative
                      source (no point recreating IK's UI)
- HF IL-TUR cases   → /case/<hf_doc_id> shows our DB text with provenance
                      footer + "Verify on Indian Kanoon" search-fallback

Routes:
  GET /case/<doc_id>      — HTML page (case-viewer.html) shell
  GET /api/case/<doc_id>  — JSON payload (parties, citation, court,
                            judges, full_text, paragraphs, provenance)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse

from headnote import config
from headnote.retrieval.hf_corpus import get_by_id as _hf_get


log = logging.getLogger(__name__)
router = APIRouter(tags=["case-viewer"])


# ---------------------------------------------------------------- helpers

def _paragraphs_from_text(text: str) -> list[dict]:
    """Split judgment text into renderable paragraphs with anchor IDs.
    Trims empty lines and section markers (=== Section ===) since those
    were introduced by the harvest text-flattener for BAIL judgments and
    aren't part of the original judgment."""
    if not text:
        return []
    paras = []
    idx = 0
    for raw in text.split("\n\n"):
        para = raw.strip()
        if not para:
            continue
        # Skip pure section markers; the next paragraph is the real content
        is_marker = para.startswith("===") and para.endswith("===")
        if is_marker:
            continue
        # Detect numbered paragraphs ("1.", "2.", "12.") to surface them
        # as the lawyer's anchor target
        is_numbered = bool(para[:5].rstrip(".)").rstrip().isdigit())
        paras.append({
            "id": f"p_{idx}",
            "num": idx + 1,
            "text": para,
            "numbered": is_numbered,
        })
        idx += 1
    return paras


def _provenance_label(doc_id: str, source: str) -> dict:
    """Build a provenance card for the viewer footer."""
    if not doc_id.startswith("hf:"):
        return {
            "source_name": "Curated",
            "source_note": "Hand-curated by Headnote editors.",
            "verify_url":  None,
        }
    subset = doc_id.split(":")[1] if ":" in doc_id[3:] else "unknown"
    subset_map = {
        "cjpe": ("IL-TUR / CJPE", "Supreme Court Court Judgment Prediction & Explanation dataset"),
        "summ": ("IL-TUR / SUMM", "Supreme + High Court summarised judgments dataset"),
        "bail": ("IL-TUR / BAIL", "Hindi district-court bail orders dataset"),
        "lsi":  ("IL-TUR / LSI",  "Legal Statute Identification dataset"),
        "pcr":  ("IL-TUR / PCR",  "Prior Case Retrieval dataset (SC citation graph)"),
    }
    label, desc = subset_map.get(subset, (f"IL-TUR / {subset.upper()}", "Indian Legal NLP benchmark dataset"))
    return {
        "source_name": label,
        "source_note": (
            f"{desc}. Published by Exploration-Lab, IIT-Kanpur. "
            "For court filings, please cross-reference this judgment with "
            "Indian Kanoon or the official court record."
        ),
        "verify_url": None,  # filled in by /api/case JSON using extracted citation
    }


def _build_verify_url(case_metadata: dict, fallback_title: str) -> Optional[str]:
    """Build an Indian Kanoon search URL using extracted metadata. Prefers
    the citation (most precise), falls back to parties name."""
    citation = (case_metadata.get("citation") or "").strip()
    parties = (case_metadata.get("parties") or "").strip()
    case_no = (case_metadata.get("case_number") or "").strip()
    query = citation or parties or case_no or fallback_title
    if not query:
        return None
    from urllib.parse import quote_plus
    return f"https://indiankanoon.org/search/?formInput={quote_plus(query)}"


# ---------------------------------------------------------------- routes

@router.get("/case/{doc_id:path}", include_in_schema=False)
def serve_case_viewer_html(doc_id: str, request: Request):
    """Serve the static HTML shell. The JS in /static/case-viewer.html
    reads its own URL, extracts doc_id, calls /api/case/<doc_id> for data."""
    html_path = config.STATIC_DIR / "case-viewer.html"
    if not html_path.exists():
        raise HTTPException(status_code=404, detail="Case viewer page not deployed")
    return FileResponse(html_path, headers={"Cache-Control": "no-cache, must-revalidate, max-age=0"})


@router.get("/api/case/{doc_id:path}", summary="Full judgment data for the in-app viewer")
def get_case_data(doc_id: str) -> dict:
    """Return parties, citation, court, judges, full text, and paragraphs
    for a single judgment by its doc_id (curated or HF)."""
    # HF case
    if doc_id.startswith("hf:"):
        hj = _hf_get(doc_id)
        if not hj:
            raise HTTPException(status_code=404, detail=f"Judgment {doc_id} not found")

        md = getattr(hj, "case_metadata", None) or {}
        provenance = _provenance_label(doc_id, hj.source)
        provenance["verify_url"] = _build_verify_url(md, hj.title or doc_id)

        return {
            "doc_id":      hj.doc_id,
            "source":      hj.source,
            "language":    hj.language,
            "title":       md.get("parties") or hj.title or doc_id,
            "parties":     md.get("parties"),
            "petitioner":  md.get("petitioner"),
            "respondent":  md.get("respondent"),
            "citation":    md.get("citation"),
            "citations_all": md.get("citations_all", []),
            "court":       md.get("court") or hj.court or "",
            "bench":       md.get("bench"),
            "judges":      md.get("judges", []),
            "date":        md.get("date"),
            "case_number": md.get("case_number"),
            "outcome":     hj.label,
            "district":    hj.district,
            "word_count":  hj.word_count,
            "summary":     hj.summary,
            "paragraphs":  _paragraphs_from_text(hj.text or ""),
            "provenance":  provenance,
            "metadata_confidence": md.get("confidence", "low"),
        }

    # Curated case
    try:
        curated = config.load_curated_corpus()
    except Exception:
        curated = []
    match = next((c for c in curated if c.get("id") == doc_id), None)
    if match:
        # Curated cases have structured fields already
        return {
            "doc_id":      match.get("id"),
            "source":      "curated",
            "language":    "en",
            "title":       match.get("title"),
            "parties":     match.get("title"),
            "citation":    match.get("citation"),
            "court":       match.get("court"),
            "bench":       match.get("bench"),
            "judges":      [match.get("bench")] if match.get("bench") else [],
            "date":        match.get("year"),
            "case_number": None,
            "outcome":     match.get("outcome"),
            "kanoon_url":  (
                f"https://indiankanoon.org/doc/{match.get('kanoon_doc_id')}/"
                if match.get("kanoon_doc_id") else None
            ),
            "kanoon_doc_id": match.get("kanoon_doc_id"),
            "facts":       match.get("facts", ""),
            "issues":      match.get("issues", []),
            "holding":     match.get("holding", ""),
            "key_paras":   match.get("key_paras", ""),
            "bns_mapping": match.get("bns_mapping", []),
            "topics":      match.get("topics", []),
            "provenance": {
                "source_name": "Curated",
                "source_note": "Hand-curated by Headnote editors with verified citation and holding.",
                "verify_url": (
                    f"https://indiankanoon.org/doc/{match.get('kanoon_doc_id')}/"
                    if match.get("kanoon_doc_id") else None
                ),
            },
        }

    raise HTTPException(status_code=404, detail=f"Case {doc_id} not found")
