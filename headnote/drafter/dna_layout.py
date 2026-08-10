"""Draft DNA — end-to-end orchestration.

Two paths, one promise: a draft comes out looking exactly like the advocate's own
filings.

  1. SKELETON (exact — the primary path). He has filed this type before, so we
     keep HIS OWN .docx as the template and swap only the values that change from
     case to case. Nothing is re-created, so nothing can be lost — no letterhead,
     footer, border, table style or page setting. Universal across advocates,
     languages and layouts. See doc_skeleton.py.
  2. LAYOUT TEMPLATE (fallback). A type he has never filed, so there is no file to
     reuse: we render into his measured geometry + font instead. See
     layout_template.py.

Everything is stored per advocate, keyed by their user id:
  • filestore  dna/<user_id>/<doc_type>/spine.docx   — his template file
  •            dna/<user_id>/<doc_type>/skeleton.json — the fixed/slot map
  • user_profiles.draft_style["layout"]              — geometry + a small index
"""
from __future__ import annotations

import json
import logging
import re
from typing import Optional

from headnote.drafter import doc_skeleton as DS
from headnote.drafter import layout_template as LT
from headnote.drafter import style_profile as SP

log = logging.getLogger("headnote.drafter.dna_layout")

_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_DEFAULT_TYPE = "general"


def _safe_type(doc_type: Optional[str]) -> str:
    t = re.sub(r"[^a-z0-9_]+", "_", (doc_type or _DEFAULT_TYPE).strip().lower())
    return t.strip("_")[:40] or _DEFAULT_TYPE


def _paths(user_id: str, doc_type: str) -> tuple[str, str]:
    base = f"dna/{user_id}/{_safe_type(doc_type)}"
    return f"{base}/spine.docx", f"{base}/skeleton.json"


# ---------------------------------------------------------------------------
# CAPTURE
# ---------------------------------------------------------------------------
def capture_and_save(user_id: str, files: list, *, doc_type: Optional[str] = None,
                     lang: str = "hi", use_llm: bool = True) -> dict:
    """`files` = [(data: bytes, filename: str)] of the advocate's own .docx drafts.

    Learns two things and persists both under his id:
      • his measured geometry (works for any type, incl. ones he never filed)
      • his SKELETON for this type, when he gave 2+ drafts of it — the exact path
    Returns a summary for the confirm screen (never persists his client's text)."""
    doc_type = _safe_type(doc_type)
    blobs = [(d, n) for d, n in files if d]

    # --- geometry (always) ---
    labeller = LT.llm_labeller(lang) if use_llm else None
    caps = []
    for data, name in blobs:
        try:
            caps.append(LT.capture_layout(data, labeller=labeller))
        except Exception:
            log.warning("layout capture failed for %r", name, exc_info=True)
    tpl = LT.merge_templates(caps)

    # --- skeleton (the exact path; needs 2+ drafts of the same type) ---
    skel, spine_ok = None, False
    if len(blobs) >= 2:
        try:
            skel = DS.build_skeleton([d for d, _ in blobs])
            if skel.get("blocks"):
                DS.label_slots(skel, lang=lang, use_llm=use_llm)
                spine_ok = _store_skeleton(user_id, doc_type, blobs[0][0], skel)
        except Exception:
            log.warning("skeleton build failed for %.8s/%s", user_id, doc_type, exc_info=True)
            skel = None

    if not tpl.get("roles") and not skel:
        return {"has_layout": False}

    # --- persist geometry + the per-type index (small) ---
    stored = LT.strip_preview(tpl)
    existing = SP.load_layout(user_id) or {}
    index = dict((existing.get("skeletons") or {}))
    if skel and spine_ok:
        index[doc_type] = {
            "n_docs": skel.get("n_docs"), "coverage": skel.get("coverage"),
            "blocks": len(skel.get("blocks") or []), "slots": DS.slot_count(skel),
            "fields": [f["label"] for f in DS.slot_fields(skel)][:60],
        }
    if index:
        stored["skeletons"] = index
    SP.save_layout(user_id, stored)

    out = dict(tpl)
    out["skeletons"] = index
    out["exact_for"] = doc_type if (skel and spine_ok) else None
    if skel and spine_ok:
        out["template_preview"] = template_preview(skel)
        out["fields"] = DS.slot_fields(skel)
    return out


def _store_skeleton(user_id: str, doc_type: str, spine: bytes, skel: dict) -> bool:
    """His template file + slot map go to durable storage under his own id."""
    try:
        from headnote import filestore
    except Exception:
        return False
    spine_path, skel_path = _paths(user_id, doc_type)
    ok_spine = filestore.put(spine_path, spine, mime=_DOCX_MIME)
    ok_skel = filestore.put(skel_path, json.dumps(skel, ensure_ascii=False).encode("utf-8"),
                            mime="application/json")
    return bool(ok_spine and ok_skel)


def load_skeleton(user_id: str, doc_type: Optional[str] = None) -> tuple[Optional[bytes], Optional[dict]]:
    """(his template .docx, his slot map) for this type — or (None, None)."""
    try:
        from headnote import filestore
    except Exception:
        return None, None
    spine_path, skel_path = _paths(user_id, doc_type)
    try:
        spine = filestore.get(spine_path)
        raw = filestore.get(skel_path)
        if spine and raw:
            return spine, json.loads(raw.decode("utf-8"))
    except Exception:
        log.warning("skeleton load failed for %.8s/%s", user_id, doc_type, exc_info=True)
    return None, None


# ---------------------------------------------------------------------------
# STATE
# ---------------------------------------------------------------------------
def has_layout(user_id: Optional[str]) -> bool:
    return SP.load_layout(user_id) is not None


def skeleton_types(user_id: Optional[str]) -> dict:
    return ((SP.load_layout(user_id) or {}).get("skeletons") or {})


def template_preview(skel: dict, *, limit: int = 80) -> list[dict]:
    """The extracted template, block by block, with its holes marked — so the
    advocate can SEE what Headnote will reuse verbatim and what it will fill."""
    out = []
    for b in (skel or {}).get("blocks", [])[:limit]:
        if "fixed" in b:
            if b["fixed"].strip():
                out.append({"kind": "fixed", "text": b["fixed"][:400]})
        else:
            parts = [{"lit": p["lit"]} if "lit" in p
                     else {"slot": p.get("label") or "", "example": (p.get("slot") or "").strip()[:40]}
                     for p in b["pattern"]]
            out.append({"kind": "slots", "parts": parts})
    return out


# ---------------------------------------------------------------------------
# GENERATE
# ---------------------------------------------------------------------------
def generate(user_id: str, *, doc_type: Optional[str] = None,
             values: Optional[dict] = None, blocks=None, lang: str = "hi") -> tuple[Optional[bytes], str]:
    """A draft in the advocate's own format. Returns (docx_bytes, how).

    `how` is "exact" when his own filing was used as the template, "geometry" when
    we re-rendered into his measured layout, or "" when he has no DNA yet.
    """
    spine, skel = load_skeleton(user_id, doc_type)
    if spine and skel:
        vals = dict(values or {})
        per_slot = DS.fill_by_label(skel, vals)          # {label: value} → {block.slot: value}
        per_slot.update({k: v for k, v in vals.items() if re.fullmatch(r"\d+\.\d+", str(k))})
        try:
            return DS.fill(spine, skel, per_slot), "exact"
        except Exception:
            log.warning("skeleton fill failed for %.8s/%s — falling back", user_id, doc_type,
                        exc_info=True)
    if blocks:
        data = apply_layout(user_id, blocks, lang=lang)
        if data:
            return data, "geometry"
    return None, ""


def render_blocks(user_id: Optional[str], blocks, *, lang: str = "hi") -> tuple[bytes, str]:
    """Role-tagged blocks → a .docx. Returns (bytes, how).

    This is the seam the drafting flow uses: `how` is "own" when the advocate's
    captured layout and font were reproduced, "standard" when he has no Draft DNA
    yet and got the plain court format instead. Never returns None — "Download
    .docx" must always be a live action; what changes is whose format it is in.
    """
    norm = _as_blocks(blocks, lang, label=False)
    if not norm:
        raise ValueError("no blocks to render")
    # DNA is STICKY: once captured it is loaded for every draft, for good, until the
    # advocate changes or clears it. Nothing here is per-draft or per-session.
    tpl = SP.load_layout(user_id) if user_id else None
    if tpl and tpl.get("roles"):
        return LT.render_into_layout(tpl, norm), "own"
    return LT.render_into_layout(LT.standard_template(LT.default_font_for(lang)), norm), "standard"


def apply_layout(user_id: Optional[str], blocks, *, lang: str = "hi",
                 label: bool = True) -> Optional[bytes]:
    """Fallback path: render `blocks` into his measured geometry + font. Used for a
    document type he has never filed (no skeleton to reuse)."""
    tpl = SP.load_layout(user_id)
    if not tpl or not tpl.get("roles"):
        return None
    return LT.render_into_layout(tpl, _as_blocks(blocks, lang, label))


def _as_blocks(blocks, lang, label):
    """Normalise caller input to [(role, content), …]. Tolerant of malformed
    items (a client sending a bare string or a 1-element pair must not 500)."""
    if not blocks:
        return []
    if isinstance(blocks[0], (tuple, list)):
        out = []
        for b in blocks:
            if isinstance(b, (tuple, list)):
                if len(b) >= 2:
                    out.append((str(b[0]) or "text", b[1]))
                elif len(b) == 1:
                    out.append(("text", b[0]))
            elif b is not None:
                out.append(("text", b))
        return out
    lines = [str(b) for b in blocks]
    labels = LT.llm_labeller(lang)(lines) if label else LT._label_deterministic(lines)
    return list(zip([lb or "text" for lb in labels], lines))
