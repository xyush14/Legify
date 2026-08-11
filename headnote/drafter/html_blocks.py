"""Rendered court document (HTML) → Draft DNA role-tagged blocks.

Why this module exists
----------------------
Draft DNA renders a `.docx` in the advocate's OWN captured layout from
role-tagged blocks — `[(role, text), …]` (see `dna_layout.render_blocks`). Until
now the only producer of those blocks was the LLM authoring path
(`dna_blocks.from_authored`, which reads an authored JSON payload). Every other
way a lawyer actually gets a draft — the fields screen at `/draft/template/<id>`,
the reviewed canonical templates, and the deterministic floors in `from_prompt` —
produces **HTML**, not an authored payload. So those documents had no blocks, and
"Download .docx in my format" was unreachable from the screens most advocates use.

This module closes that seam: it reads the document HTML the deterministic engine
already emits and recovers the same role vocabulary, with **no LLM call**.

Universal by construction
-------------------------
The mapping keys on the ENGINE'S OWN CSS CLASSES and on document structure — never
on Hindi words, never on any one advocate's phrasing. `_doc_header.py` and the
civil `_civil.py` builders emit the identical class vocabulary for every language
they render (hi · en · mr · bn · gu) and for every one of the reviewed types, so a
Chennai advocate drafting in English and a Pune advocate drafting in Marathi go
down the exact same code path and get the exact same roles. Adding a language
requires no change here; adding a new *builder* only requires it to use the shared
document classes, which it already must in order to render at all.

The role vocabulary is `layout_template.ROLES` — the same one the capture side
tags the advocate's own filings with, which is what makes his format apply.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

log = logging.getLogger("headnote.drafter.html_blocks")

# ---------------------------------------------------------------------------
# CLASS → ROLE. Structural, language-neutral. Left column is what the document
# builders emit; right column is `layout_template.ROLES` (the capture vocabulary).
#
#   hdr-*  cause title, from templates/_doc_header.py
#   cb-*   body blocks, from templates/_doc_header.py (all reviewed types)
#   bd-*   the legacy bail_application.py builder (/draft/bail), same shapes
# ---------------------------------------------------------------------------
_CLASS_ROLE: dict[str, str] = {
    # ---- cause title -------------------------------------------------------
    "hdr-side":        "side_label",
    "bd-side":         "side_label",
    "hdr-court":       "court",
    "bd-court":        "court",
    "hdr-case":        "caseno",
    "bd-caseno":       "caseno",
    "hdr-versus":      "versus",
    "bd-versus":       "versus",
    "hdr-title":       "section_heading",
    "bd-app-title":    "section_heading",
    # ---- body --------------------------------------------------------------
    "cb-prelude":      "intro",
    "bd-prelude":      "intro",
    "cb-head":         "ground_head",
    "cb-block-label":  "ground_head",
    "bd-section-label": "ground_head",
    "cb-note":         "intro",
    "cb-prayer":       "prayer",
    "bd-prayer":       "prayer",
    "cb-relief":       "prayer",
    "cb-witlist":      "intro",
}

# Party blocks carry a label ("Applicant ——") and a description; both belong to
# the same role so the advocate's captured party format governs the whole block.
_PARTY_ROLE: dict[str, str] = {
    "hdr-party--p": "applicant",
    "hdr-party--r": "respondent",
    "bd-party":     "applicant",   # refined below by position (see _party_role)
}

# Containers we descend into rather than emit.
_CONTAINERS = ("v2-bundle", "doc-a4", "doc-hdr", "doc-body", "bail-doc",
               "bd-header", "bd-parties", "bd-paras", "bd-facts-block",
               "bd-grounds-block", "bd-subparas", "cb-relief-list")

# Numbered-argument lists. Every reviewed builder emits its grounds as <li> here.
_GROUND_LISTS = ("cb-paras", "bd-paras", "bd-subparas")

_TABLE_CLASSES = ("cb-table", "bd-table")
_SIG_CLASSES = ("cb-sig", "bd-sig")

# A page break between the sheets of a filing bundle (Application / Affidavit /
# Index …). `render_into_layout` understands this pseudo-role.
PAGE_BREAK = ("page_break", "")


def _classes(el) -> list[str]:
    c = el.get("class")
    if not c:
        return []
    return list(c) if isinstance(c, (list, tuple)) else str(c).split()


def _text(el) -> str:
    """Visible text of one element, with <br> as a line break and NBSPs normalised.

    Placeholder spans (`.ph`) are kept: on screen they are the greyed blanks the
    lawyer still has to fill, and the .docx must show the same blanks in the same
    places — silently dropping them would hand him a document that reads as
    complete when it is not.
    """
    parts: list[str] = []
    for node in el.descendants:
        name = getattr(node, "name", None)
        if name == "br":
            parts.append("\n")
        elif name is None:                      # NavigableString
            parts.append(str(node))
    txt = "".join(parts).replace(" ", " ")
    txt = re.sub(r"[ \t]+", " ", txt)
    txt = re.sub(r" *\n *", "\n", txt)
    return txt.strip()


def _lines(el) -> list[str]:
    """One element → its visual lines. A cause-title party block is several lines
    in the advocate's format, and each must be its own paragraph in the .docx."""
    return [ln for ln in _text(el).split("\n") if ln.strip()]


def _party_role(el, seen: dict) -> str:
    """Role for a party block. Class-driven where the builder says which side it
    is; otherwise by position — the first party block in a cause title is the
    moving party, the next is the opposite party. That ordering is universal to
    Indian pleadings and does not depend on the words used for either side."""
    cl = _classes(el)
    for k, role in _PARTY_ROLE.items():
        if k in cl and k != "bd-party":
            return role
    seen["n"] = seen.get("n", 0) + 1
    return "applicant" if seen["n"] == 1 else "respondent"


def _table_block(el) -> Optional[tuple]:
    """A document table → the ("table", {...}) block `render_into_layout` emits
    with the advocate's own column widths."""
    rows: list[list[str]] = []
    for tr in el.find_all("tr"):
        cells = [_text(td).replace("\n", " ") for td in tr.find_all(["td", "th"])]
        if any(c.strip() for c in cells):
            rows.append(cells)
    if not rows:
        return None
    return ("table", {"widths": [], "rows": rows})


def _sig_blocks(el) -> list[tuple]:
    """The signature foot → dateline (left column) + signature (right column).

    Structural, not lexical: the builders put place/date in `.l` and the
    signatures in `.r`, and mark the start of the advocate's own block with an
    inline top margin. So we never look for the word "advocate" in any language —
    we read where the builder put things.
    """
    out: list[tuple] = []
    for left in el.select(".l, .bd-sig-left"):
        for ln in _lines(left):
            out.append(("dateline", ln))
    for right in el.select(".r, .bd-sig-right"):
        after_gap = False
        for child in right.find_all(["div", "p"], recursive=False):
            gap = "margin-top" in (child.get("style") or "")
            lines = _lines(child)
            if not lines:
                continue
            if gap and not after_gap:
                after_gap = True
                out.append(("sig_by", lines[0]))
                for ln in lines[1:]:
                    out.append(("advocate", ln))
                continue
            role = "advocate" if after_gap else "sig_party"
            for ln in lines:
                out.append((role, ln))
        if not right.find(["div", "p"], recursive=False):
            for ln in _lines(right):
                out.append(("sig_party", ln))
    return out


def from_document_html(html: str, *, number_grounds: bool = True) -> list[tuple]:
    """Rendered document HTML → `[(role, content), …]` for `dna_layout`.

    Returns [] when nothing recognisable is present, so a caller can fall back
    rather than write an empty .docx.
    """
    if not html or not html.strip():
        return []
    try:
        from bs4 import BeautifulSoup
    except Exception:                                  # pragma: no cover
        log.warning("bs4 unavailable — cannot derive layout blocks from HTML")
        return []

    soup = BeautifulSoup(html, "html.parser")
    for junk in soup.find_all(["style", "script"]):
        junk.decompose()

    blocks: list[tuple] = []
    party_seen: dict = {}
    sheet_no = {"n": 0}

    def walk(el) -> None:
        for child in el.find_all(True, recursive=False):
            cl = _classes(child)
            name = child.name or ""

            # a new sheet of the filing bundle starts on its own page
            if "doc-a4" in cl:
                sheet_no["n"] += 1
                if sheet_no["n"] > 1:
                    blocks.append(PAGE_BREAK)
                party_seen.clear()
                walk(child)
                continue

            if any(t in cl for t in _TABLE_CLASSES) or name == "table":
                tb = _table_block(child)
                if tb:
                    blocks.append(tb)
                continue

            if any(s in cl for s in _SIG_CLASSES):
                blocks.extend(_sig_blocks(child))
                continue

            if any(g in cl for g in _GROUND_LISTS) or name in ("ol", "ul"):
                items = child.find_all("li", recursive=False)
                for i, li in enumerate(items, 1):
                    txt = _text(li).replace("\n", " ")
                    if not txt:
                        continue
                    # The advocate's captured `ground` format carries his own
                    # numbering geometry (hanging indent / tab). The number itself
                    # is content, so it has to be written in.
                    blocks.append(("ground", f"{i}. {txt}" if number_grounds else txt))
                continue

            if any(p in cl for p in _PARTY_ROLE):
                role = _party_role(child, party_seen)
                for ln in _lines(child):
                    blocks.append((role, ln))
                continue

            role = next((_CLASS_ROLE[c] for c in cl if c in _CLASS_ROLE), None)
            if role:
                for ln in _lines(child):
                    blocks.append((role, ln))
                continue

            if any(c in _CONTAINERS for c in cl) or name in ("div", "section", "main", "body"):
                walk(child)
                continue

            # A paragraph the builder did not class — keep it rather than lose it.
            if name in ("p", "h1", "h2", "h3", "h4"):
                for ln in _lines(child):
                    blocks.append(("intro", ln))

    walk(soup)
    return [b for b in blocks if b == PAGE_BREAK or b[0] == "table" or str(b[1]).strip()]


def is_empty(blocks) -> bool:
    """True when there is no real content — only breaks or blank text."""
    for role, content in blocks or []:
        if role == "page_break":
            continue
        if role == "table":
            if (content or {}).get("rows"):
                return False
            continue
        if str(content or "").strip():
            return False
    return True
