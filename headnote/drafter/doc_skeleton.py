"""Draft DNA — the universal layout engine.

THE PRINCIPLE
-------------
Do not re-create a lawyer's layout. Keep HIS OWN FILE as the template and change
only the words that vary between his drafts.

Re-creating a layout from measurements is inherently lossy: it can only reproduce
what we thought to model, so anything unmodelled — a letterhead, a footer, a
border, a logo, a table style, page numbering, some convention from a state we
have never seen — is silently dropped. Reusing his actual .docx is lossless *by
construction* and therefore works for every advocate, every language and every
document structure, including layouts we have never encountered.

HOW THE SLOTS ARE FOUND (no language or layout knowledge required)
------------------------------------------------------------------
Put two or three of his own filings side by side and align them block by block:

  • text identical in every draft   → his fixed skeleton (reproduce verbatim)
  • text that differs               → a SLOT (the case-specific part)

Within a differing block we diff further, so a sentence keeps his exact wording
and only the changing span becomes a hole:

      "यहकि, आवेदक ⟦slot⟧ निर्दोष है तथा उसे झूठा फंसाया गया है।"

This is pure comparison — it never asks what a block *means*, so it is equally
valid for a Gwalior bail, a Gujarati plaint or a Madras writ with a letterhead.

Generation then opens his real .docx and replaces only the slot text, preserving
every run's formatting (and encoding into his font when it is a legacy face).
"""
from __future__ import annotations

import difflib
import io
import logging
import re
from typing import Optional

from headnote.drafter import krutidev as _kd

log = logging.getLogger("headnote.drafter.skeleton")

_MAX_BLOCKS = 400
_MIN_LITERAL = 4          # a shared run shorter than this is noise, not boilerplate


# ---------------------------------------------------------------------------
# 1) READ — a document as an ordered list of blocks
# ---------------------------------------------------------------------------
def read_blocks(data: bytes | str) -> list[dict]:
    """The document in reading order: one entry per paragraph and per table cell.

    `text` is decoded to Unicode (font-aware) purely so drafts can be COMPARED;
    the original file is never modified. `path` locates the block for filling.
    """
    from docx import Document

    doc = Document(io.BytesIO(data) if isinstance(data, (bytes, bytearray)) else data)
    blocks: list[dict] = []
    for i, p in enumerate(doc.paragraphs):
        blocks.append({"kind": "p", "path": ("p", i),
                       "text": _kd._decode_paragraph(p).rstrip()})
        if len(blocks) >= _MAX_BLOCKS:
            return blocks
    for ti, t in enumerate(doc.tables):
        for ri, row in enumerate(t.rows):
            for ci, cell in enumerate(row.cells):
                txt = "\n".join(_kd._decode_paragraph(p) for p in cell.paragraphs).rstrip()
                blocks.append({"kind": "cell", "path": ("t", ti, ri, ci), "text": txt})
                if len(blocks) >= _MAX_BLOCKS:
                    return blocks
    return blocks


def _norm(s: str) -> str:
    """Whitespace-insensitive key used only for aligning blocks across drafts."""
    return re.sub(r"\s+", " ", (s or "")).strip()


# ---------------------------------------------------------------------------
# 2) COMPARE — his drafts → a skeleton of fixed text and slots
# ---------------------------------------------------------------------------
def _pattern_from_versions(versions: list[str]) -> list[dict]:
    """One block seen in several drafts → [{lit}|{slot}] preserving his wording.

    Keeps the spans of the first version that survive in EVERY other version;
    the gaps between them are the parts that change from case to case.
    """
    base = versions[0]
    keep = [True] * len(base)
    for other in versions[1:]:
        matched = [False] * len(base)
        for blk in difflib.SequenceMatcher(None, base, other, autojunk=False).get_matching_blocks():
            for k in range(blk.a, blk.a + blk.size):
                matched[k] = True
        keep = [a and b for a, b in zip(keep, matched)]

    parts: list[dict] = []
    buf, mode = [], keep[0] if base else True
    for ch, k in zip(base, keep):
        if k != mode:
            parts.append({"lit": "".join(buf)} if mode else {"slot": "".join(buf)})
            buf, mode = [], k
        buf.append(ch)
    if buf:
        parts.append({"lit": "".join(buf)} if mode else {"slot": "".join(buf)})

    # a very short "shared" fragment between two changing spans is coincidence
    merged: list[dict] = []
    for p in parts:
        if "lit" in p and len(p["lit"].strip()) < _MIN_LITERAL and merged and "slot" in merged[-1]:
            merged[-1]["slot"] += p["lit"]
        elif "slot" in p and merged and "slot" in merged[-1]:
            merged[-1]["slot"] += p["slot"]
        else:
            merged.append(dict(p))

    # Snap slots out to whole words. A character diff happily cuts mid-word
    # ("⟦ग⟧्राम", "⟦करहिय⟧ा"); a slot the advocate is asked to fill must be a
    # word, not a fragment.
    out: list[dict] = []
    for idx, p in enumerate(merged):
        if "lit" not in p:
            out.append(p)
            continue
        lit = p["lit"]
        prev_is_slot = bool(out) and "slot" in out[-1]
        next_is_slot = idx + 1 < len(merged) and "slot" in merged[idx + 1]
        if prev_is_slot:                       # give the tail of this literal back
            m = re.match(r"\S*", lit)          # up to the first space
            if m and m.group(0):
                out[-1]["slot"] += m.group(0)
                lit = lit[m.end():]
        if next_is_slot:                       # give its head to the next slot
            m = re.search(r"\S*$", lit)
            if m and m.group(0):
                merged[idx + 1]["slot"] = m.group(0) + merged[idx + 1]["slot"]
                lit = lit[:m.start()]
        if lit:
            out.append({"lit": lit})

    final: list[dict] = []
    for p in out:                                    # snapping can leave slots adjacent
        if not (p.get("lit") or p.get("slot")):
            continue
        if "slot" in p and final and "slot" in final[-1]:
            final[-1]["slot"] += p["slot"]
        else:
            final.append(p)
    return final


_SIM_FLOOR = 0.42        # below this two blocks are different things, not variants
_GAP = 0.32              # cost of leaving a block unpaired


def _sim(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    sm = difflib.SequenceMatcher(None, a, b, autojunk=False)
    if sm.real_quick_ratio() < _SIM_FLOOR or sm.quick_ratio() < _SIM_FLOOR:
        return 0.0
    r = sm.ratio()
    return r if r >= _SIM_FLOOR else 0.0


def _align_by_similarity(A: list[str], B: list[str]) -> dict[int, int]:
    """Global sequence alignment of two block lists (order preserved), pairing
    blocks that are similar enough to be the same block of the same document type.
    Returns {index_in_A: index_in_B}."""
    n, m = len(A), len(B)
    if not n or not m:
        return {}
    dp = [[0.0]*(m+1) for _ in range(n+1)]
    for i in range(1, n+1):
        dp[i][0] = dp[i-1][0] - _GAP
    for j in range(1, m+1):
        dp[0][j] = dp[0][j-1] - _GAP
    for i in range(1, n+1):
        ai = A[i-1]
        row, prev = dp[i], dp[i-1]
        for j in range(1, m+1):
            row[j] = max(prev[j-1] + _sim(ai, B[j-1]), prev[j] - _GAP, row[j-1] - _GAP)
    out: dict[int, int] = {}
    i, j = n, m
    while i > 0 and j > 0:
        s = _sim(A[i-1], B[j-1])
        if abs(dp[i][j] - (dp[i-1][j-1] + s)) < 1e-9:
            if s > 0:
                out[i-1] = j-1
            i, j = i-1, j-1
        elif abs(dp[i][j] - (dp[i-1][j] - _GAP)) < 1e-9:
            i -= 1
        else:
            j -= 1
    return out


def build_skeleton(docs: list[bytes], *, labels: Optional[list] = None) -> dict:
    """Two or more of the advocate's own drafts → his skeleton.

    Returns {"blocks":[{path, kind, fixed|pattern, seen}], "n_docs", "coverage"}.
    The FIRST document is the spine — it is the file that will be used as the
    template at generation time, so slots are expressed against it.
    """
    parsed = [read_blocks(d) for d in docs]
    parsed = [p for p in parsed if p]
    if not parsed:
        return {"blocks": [], "n_docs": 0}
    spine = parsed[0]
    if len(parsed) == 1:
        # nothing to compare against: treat every block as fixed, no slots
        return {"blocks": [{"path": b["path"], "kind": b["kind"], "fixed": b["text"], "seen": 1}
                           for b in spine], "n_docs": 1, "coverage": 0.0}

    # Align each other draft to the spine by SIMILARITY, not equality. The blocks
    # we care about (a cause-title carrying a different client's name) are never
    # identical, so an equality match would push them apart and mark whole
    # paragraphs as variable. Similarity alignment pairs them, and the intra-block
    # diff then isolates just the name.
    spine_keys = [_norm(b["text"]) for b in spine]
    aligned: list[list[str]] = [[b["text"]] for b in spine]
    for other in parsed[1:]:
        pairs = _align_by_similarity(spine_keys, [_norm(b["text"]) for b in other])
        for i in range(len(spine)):
            j = pairs.get(i)
            aligned[i].append(other[j]["text"] if j is not None else "")

    blocks, slot_chars, total_chars = [], 0, 0
    for b, versions in zip(spine, aligned):
        present = [v for v in versions if v.strip()]
        total_chars += len(b["text"])
        if len(present) < 2 or len(set(_norm(v) for v in present)) == 1:
            blocks.append({"path": b["path"], "kind": b["kind"],
                           "fixed": b["text"], "seen": len(present)})
        else:
            pat = _pattern_from_versions(present)
            slot_chars += sum(len(p["slot"]) for p in pat if "slot" in p)
            blocks.append({"path": b["path"], "kind": b["kind"],
                           "pattern": pat, "seen": len(present)})
    return {"blocks": blocks, "n_docs": len(parsed),
            "coverage": round(1 - (slot_chars / total_chars), 3) if total_chars else 0.0}


def slot_count(skel: dict) -> int:
    return sum(len([p for p in b["pattern"] if "slot" in p])
               for b in (skel or {}).get("blocks", []) if "pattern" in b)


def iter_slots(skel: dict):
    """(block_index, slot_index, key, slot_dict, surrounding_text) for every hole."""
    for bi, b in enumerate((skel or {}).get("blocks", [])):
        if "pattern" not in b:
            continue
        si = 0
        context = "".join(p.get("lit", "") or ("⟦…⟧") for p in b["pattern"])
        for p in b["pattern"]:
            if "slot" in p:
                yield bi, si, f"{bi}.{si}", p, context
                si += 1


# ---------------------------------------------------------------------------
# 2b) LABEL — give each hole a name, in any language
# ---------------------------------------------------------------------------
_LABEL_SYSTEM = """You name the blanks in a lawyer's own document template. Each blank is a value that
changes from case to case. Return ONLY JSON: {"labels": {"<key>": "<snake_case_field_name>"}}.

Use plain, generic field names in English regardless of the document's language, e.g.
client_name, father_name, age, occupation, address, village, police_station, district, court,
case_number, case_year, crime_number, sections, offence_date, arrest_date, filing_date,
co_accused, amount, advocate_name, opposite_party. Reuse the SAME name when two blanks clearly
hold the same value. If a blank is not a real field (stray punctuation/spacing), name it "ignore".
Judge from the surrounding sentence, not from the example value."""


def label_slots(skel: dict, *, lang: str = "hi", use_llm: bool = True) -> dict:
    """Attach a human-meaningful `label` to every slot so generated content can be
    routed into the right hole. Language-agnostic: the model reads the advocate's
    own sentence, whatever language it is in. Falls back to positional keys."""
    slots = list(iter_slots(skel))
    if not slots:
        return skel
    if use_llm:
        try:
            from headnote.llm.client import _call_deepseek_or_groq, parse_json_response
            from headnote import config
            listing = "\n".join(
                f'{key}: sentence="{ctx[:150]}" example="{(p.get("slot") or "").strip()[:40]}"'
                for _bi, _si, key, p, ctx in slots[:120])
            raw, _ = _call_deepseek_or_groq(
                _LABEL_SYSTEM, f"BLANKS:\n{listing}\n\nReturn the JSON.",
                max_tokens=2000, claude_model=config.DRAFTER_AUTHOR_MODEL, json_mode=True)
            parsed = parse_json_response(raw) or {}
            got = parsed.get("labels", parsed) if isinstance(parsed, dict) else {}
            if isinstance(got, dict):
                for _bi, _si, key, p, _ctx in slots:
                    v = got.get(key)
                    if isinstance(v, str) and v.strip():
                        p["label"] = re.sub(r"[^a-z0-9_]+", "_", v.strip().lower())[:40]
        except Exception:
            log.warning("slot labelling failed — positional keys retained", exc_info=True)
    for _bi, _si, key, p, _ctx in slots:
        p.setdefault("label", key)
    return skel


def slot_fields(skel: dict) -> list[dict]:
    """The distinct fields this template needs, for a form or for mapping content."""
    seen: dict[str, dict] = {}
    for _bi, _si, key, p, ctx in iter_slots(skel):
        lab = p.get("label") or key
        if lab == "ignore":
            continue
        if lab not in seen:
            seen[lab] = {"label": lab, "keys": [], "example": (p.get("slot") or "").strip()[:60],
                         "context": ctx[:160]}
        seen[lab]["keys"].append(key)
    return list(seen.values())


def fill_by_label(skel: dict, values: dict) -> dict:
    """Turn {field_label: value} into the per-slot {block.slot: value} map."""
    out: dict = {}
    for _bi, _si, key, p, _ctx in iter_slots(skel):
        lab = p.get("label")
        if lab and lab in values:
            out[key] = values[lab]
    return out


# ---------------------------------------------------------------------------
# 3) FILL — his own .docx + new values → a new draft, layout untouched
# ---------------------------------------------------------------------------
def fill(template: bytes, skeleton: dict, values: Optional[dict] = None,
         *, blank: str = "____") -> bytes:
    """Open HIS file and replace only the slot text. Everything else — styles,
    headers, footers, tables, borders, images, page setup — is left exactly as he
    filed it, because it is never re-created.

    `values` maps "<block_index>.<slot_index>" (or a slot's label, if one was
    assigned) to the replacement text. Missing values fall back to `blank`.
    """
    from docx import Document

    values = values or {}
    doc = Document(io.BytesIO(template))
    paras = list(doc.paragraphs)

    for bi, blk in enumerate(skeleton.get("blocks", [])):
        if "pattern" not in blk:
            continue                      # fixed boilerplate — leave it alone
        target = _resolve(doc, paras, blk["path"])
        if target is None:
            continue
        si = 0
        out = []
        for part in blk["pattern"]:
            if "lit" in part:
                out.append(part["lit"])
            else:
                key = f"{bi}.{si}"
                out.append(str(values.get(key, values.get(part.get("label", ""), blank))))
                si += 1
        _set_paragraph_text(target, "".join(out))

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _resolve(doc, paras, path):
    try:
        if path[0] == "p":
            return paras[path[1]]
        _, ti, ri, ci = path
        cell = doc.tables[ti].rows[ri].cells[ci]
        return cell.paragraphs[0] if cell.paragraphs else None
    except Exception:
        return None


def _set_paragraph_text(paragraph, text: str):
    """Replace a paragraph's text, keeping its first run's formatting (font, size,
    bold) and its paragraph properties. Legacy-font runs are re-encoded, with
    unrepresentable Latin/punctuation split into a Latin run — the same rule the
    rest of the drafter uses, so nothing renders as mojibake."""
    from headnote.drafter.layout_template import split_script_segments, _set_run_font

    runs = paragraph.runs
    if not runs:
        return
    first = runs[0]
    font = _kd._run_font(first)
    size = first.font.size.pt if first.font.size else None
    bold = bool(first.bold)

    for r in runs[1:]:
        r._element.getparent().remove(r._element)
    first.text = ""

    segments = split_script_segments(text, font)
    for i, (seg, seg_font, needs_enc) in enumerate(segments):
        if not seg:
            continue
        payload = _kd.to_krutidev(seg) if needs_enc else seg
        if i == 0:
            first.text = payload
            _set_run_font(first, seg_font, size or 12, bold)
        else:
            extra = paragraph.add_run(payload)
            _set_run_font(extra, seg_font, size or 12, bold)
