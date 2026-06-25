"""Assemble a draft type's FULL filing bundle (multi-sheet) for the V2 editor.

A real filing is not one sheet — HC bail = Index → Application(मय शपथपत्र) →
Affidavit → Annexures → Vakalatnama; subordinate-court types are lighter. A type
module exposes `bundle(data, lang) -> (sheets, labels)`; types without one fall
back to their single render_hi/render_en. Shared by the FastAPI /api/draft/render
and the local node→python bridge (scripts/_studio_render.py).
"""
from __future__ import annotations

ALIAS = {"cheque": "cheque_138"}


def module_for(doc_type: str):
    import importlib
    name = ALIAS.get(doc_type, doc_type)
    return importlib.import_module("headnote.drafter.templates." + name)


def _wrap(sheets):
    return "".join(f'<div class="doc-a4">{s}</div>' for s in sheets)


def assemble(mod, data: dict) -> dict:
    """Return both the per-sheet lists (for a sheet-aware editor) and the joined
    HTML (for simple consumers)."""
    data = data or {}
    if hasattr(mod, "bundle"):
        sheets_hi, labels_hi = mod.bundle(data, "hi")
        sheets_en, labels_en = mod.bundle(data, "en")
    else:
        sheets_hi, labels_hi = [mod.render_hi(data)], [""]
        sheets_en, labels_en = [mod.render_en(data)], [""]
    return {
        "ok": True,
        "sheets_hi": sheets_hi, "sheets_en": sheets_en,
        "labels_hi": labels_hi, "labels_en": labels_en,
        "html_hi": _wrap(sheets_hi), "html_en": _wrap(sheets_en),
    }
