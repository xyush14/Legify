"""
IPC ↔ BNS / CrPC ↔ BNSS / Evidence ↔ BSA section lookup.

Powers the public /sections tool. Pure data lookup over the curated
concordance in data/statute_mappings.json — no LLM, no network. The section
mappings are hand-verified against official government concordances, so this
is the highest-trust surface in the product: it never fabricates a mapping,
and it honestly flags fields the advocate should re-check (confidence=
"verify-classification").

Query handling is deliberately forgiving:
  - bidirectional      "IPC 302" and "BNS 103" both resolve the murder pair
  - code disambiguation "302" alone returns every domain that uses 302, ranked
  - offence-name search "cheating", "anticipatory bail", "electronic evidence"
  - Devanagari digits   "४२०" == "420"
  - messy input         "s. 420 ipc", "420/IPC", "section420"
"""

from __future__ import annotations

import functools
import re

from headnote import config

# Devanagari → ASCII digits, so "४२०" is read as "420".
_HINDI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

# Old codes live on the .old side, new codes on the .new side. Used to decide
# whether a code token the user typed agrees or disagrees with a candidate.
_OLD_CODES = {"ipc", "crpc", "evidence"}
_NEW_CODES = {"bns", "bnss", "bsa"}

# Words that carry no disambiguating signal for offence-name search.
_STOPWORDS = {
    "section", "sec", "s", "u", "under", "the", "of", "for", "a", "an",
    "and", "or", "to", "is", "what", "which", "act", "code", "new", "old",
    "ipc", "crpc", "cr", "p", "c", "bns", "bnss", "bsa", "evidence", "iea",
    "indian", "penal",
}

# Human labels + display order for the classification fields in `data`.
_FIELD_LABELS = [
    ("punishment", "Punishment"),
    ("cognizable", "Cognizable"),
    ("bailable", "Bailable"),
    ("compoundable", "Compoundable"),
    ("court", "Triable by"),
]

# Curated empty-state chips. Every query here is known to resolve.
_POPULAR = [
    {"label": "IPC 302 · Murder", "query": "IPC 302"},
    {"label": "IPC 420 · Cheating", "query": "IPC 420"},
    {"label": "IPC 376 · Rape", "query": "IPC 376"},
    {"label": "IPC 498A · Cruelty", "query": "IPC 498A"},
    {"label": "IPC 304A · Death by negligence", "query": "IPC 304A"},
    {"label": "CrPC 438 · Anticipatory bail", "query": "438 CrPC"},
    {"label": "CrPC 482 · Inherent powers", "query": "482 CrPC"},
    {"label": "CrPC 154 · FIR", "query": "154 CrPC"},
    {"label": "Evidence 65B · Electronic records", "query": "65B Evidence"},
]


@functools.lru_cache(maxsize=1)
def _load() -> dict:
    return config.load_statute_mappings()


def _meta() -> dict:
    return _load().get("_meta", {})


def _mappings() -> list[dict]:
    return _load().get("mappings", [])


def _norm_code(code: str | None) -> str:
    """Collapse any code spelling to a canonical token (order matters:
    bnss before bns; 'Evidence Act'/'IEA' → evidence; 'Sakshya' → bsa)."""
    c = (code or "").lower().replace(".", "").replace(" ", "")
    if "bnss" in c:
        return "bnss"
    if "bns" in c:
        return "bns"
    if "bsa" in c or "sakshya" in c:
        return "bsa"
    if "crpc" in c:
        return "crpc"
    if "ipc" in c:
        return "ipc"
    if "evidence" in c or "iea" in c:
        return "evidence"
    return c


def _detect_code(q: str) -> str | None:
    """Find a statute code mentioned anywhere in the query. bnss matched
    before bns; CrPC tolerant of dots/spaces (cr.p.c, cr p c)."""
    ql = q.lower()
    if re.search(r"\bbnss\b", ql):
        return "bnss"
    if re.search(r"\bbns\b", ql):
        return "bns"
    if re.search(r"\bbsa\b|sakshya", ql):
        return "bsa"
    if re.search(r"\bcr\.?\s*p\.?\s*c\.?\b|\bcrpc\b", ql):
        return "crpc"
    if re.search(r"\bi\.?\s*p\.?\s*c\.?\b|\bipc\b", ql):
        return "ipc"
    if re.search(r"\bevidence\b|\biea\b", ql):
        return "evidence"
    return None


def _section_base(s: str | None) -> str:
    """Comparable key for a section string: number + single letter suffix,
    sub-section parens dropped. '304A'→'304a', '103(1)'→'103', '23(2) proviso'
    →'23', None→''."""
    m = re.match(r"\s*(\d+)\s*([A-Za-z]?)", str(s or ""))
    if not m or not m.group(1):
        return ""
    return (m.group(1) + m.group(2)).lower()


def _extract_section(q: str) -> str | None:
    """Pull the section the user typed: a number with at most one trailing
    letter (so 'BNS' is never mistaken for a suffix). '304A ipc'→'304a',
    '420/IPC'→'420', 'cheating'→None."""
    m = re.search(r"(\d+)\s*([A-Za-z](?![A-Za-z]))?", q)
    if not m:
        return None
    return (m.group(1) + (m.group(2) or "")).lower()


def _subsection(s: str | None) -> str:
    """Parenthesised sub-section, lower-cased: '103(2)'→'2', '23(2) proviso'
    →'2', '304A'→''. Used only as a tie-breaker so 'BNS 103(2)' (mob lynching)
    is not swallowed by 'BNS 103(1)' (murder)."""
    m = re.search(r"\(\s*(\d+[A-Za-z]?)\s*\)", str(s or ""))
    return m.group(1).lower() if m else ""


def _name_tokens(q: str) -> list[str]:
    """Lower-cased word tokens for offence-name search, minus stopwords,
    pure numbers, and code tokens."""
    toks = re.findall(r"[a-zA-Z]+", q.lower())
    return [t for t in toks if t not in _STOPWORDS and len(t) > 1]


def _struct_score(entry: dict, sec: str, code: str | None, sub: str = "") -> int:
    """Score a candidate on section-number match (+ code agreement, + an exact
    sub-section tie-break)."""
    old = entry.get("old") or {}
    new = entry.get("new") or {}
    old_base = _section_base(old.get("section"))
    new_base = _section_base(new.get("section"))
    old_c = _norm_code(old.get("code"))
    new_c = _norm_code(new.get("code"))

    s = 0
    if old_base and sec == old_base:
        s += 90
        if code and code == old_c:
            s += 40            # number AND old code agree — strongest
        elif code in _OLD_CODES and code != old_c:
            s -= 70            # user named a different old code — wrong domain
    if new_base and sec == new_base:
        s += 80                # reverse lookup (new → old)
        if code and code == new_c:
            s += 40
        elif code in _NEW_CODES and code != new_c:
            s -= 70

    # Sub-section tie-break: 'BNS 103(2)' should win over 'BNS 103(1)'.
    if sub and (sec == old_base or sec == new_base):
        subs = {_subsection(new.get("section")), _subsection(old.get("section"))}
        subs.discard("")
        if sub in subs:
            s += 20
        elif subs:
            s -= 12            # entry carries a different explicit sub-section
    return s


def _name_score(entry: dict, tokens: list[str]) -> int:
    """Score a candidate on offence-name / keyword overlap."""
    if not tokens:
        return 0
    old = entry.get("old") or {}
    new = entry.get("new") or {}
    old_title = (old.get("title") or "").lower()
    new_title = (new.get("title") or "").lower()
    tags = [t.lower() for t in entry.get("tags", [])]
    hay = " ".join([old_title, new_title, " ".join(tags),
                    (entry.get("summary") or "").lower()])

    s = 0
    for w in tokens:
        if w in hay:
            s += 20
        if w in tags:
            s += 25
        if w in old_title or w in new_title:
            s += 15
    return s


# In-card explanations for entries that legitimately carry no offence-
# classification grid — so a missing table reads as intentional, not broken.
_CONTEXT_NOTES = {
    "procedure": ("Procedural provision — it governs criminal process "
                  "(investigation, arrest, bail, trial), not an offence, so the "
                  "cognizable / bailable / triable-by grid does not apply."),
    "evidence": ("Rule of evidence — it governs what is admissible and how facts "
                 "are proved, not an offence, so there is no punishment or bail "
                 "classification."),
    "definition": ("Definition / general clause — it defines a term or principle "
                   "used across the code and carries no punishment or trial "
                   "classification of its own. The section that punishes it has "
                   "the grid."),
}


def _classify(entry: dict, has_grid: bool) -> tuple[str, str]:
    """Decide a card 'kind' and, where no offence grid applies, an in-card note
    explaining the absence honestly rather than leaving a blank card."""
    if entry.get("change_type") == "omitted":
        return "omitted", ""           # map row + summary already explain it
    if has_grid:
        return ("new" if entry.get("change_type") == "new" else "offence"), ""
    domain = entry.get("domain")
    if domain == "procedure":
        return "procedure", _CONTEXT_NOTES["procedure"]
    if domain == "evidence":
        return "evidence", _CONTEXT_NOTES["evidence"]
    return "definition", _CONTEXT_NOTES["definition"]


def _augment(entry: dict) -> dict:
    """Project a raw entry into the API shape: per-field diff, the fields that
    materially changed, and a 'kind' + context note that lets the UI explain why
    a card has no comparison grid."""
    data = entry.get("data") or {}
    is_new = entry.get("change_type") == "new"
    diff = []
    changed = []
    for key, label in _FIELD_LABELS:
        pair = data.get(key)
        if not pair:
            continue
        old_v = (pair.get("old") or "").strip()
        new_v = (pair.get("new") or "").strip()
        if not old_v and not new_v:
            continue
        if not new_v or new_v.lower() == "verify":
            status = "verify"
        elif is_new and not old_v:
            status = "new"             # brand-new offence — nothing to compare
        elif old_v.lower() == new_v.lower():
            status = "same"
        else:
            status = "changed"
            changed.append(label)
        diff.append({
            "field": key, "label": label,
            "old": old_v, "new": new_v, "status": status,
        })

    new = entry.get("new") or {}
    kind, context_note = _classify(entry, bool(diff))
    return {
        "id": entry.get("id"),
        "domain": entry.get("domain"),
        "old": entry.get("old"),
        "new": entry.get("new"),
        "has_successor": bool(new.get("section")),
        "change_type": entry.get("change_type"),
        "material_change": bool(entry.get("material_change")),
        "confidence": entry.get("confidence", "high"),
        "summary": entry.get("summary", ""),
        "tags": entry.get("tags", []),
        "diff": diff,
        "changed_fields": changed,
        "kind": kind,
        "context_note": context_note,
    }


def lookup(raw_query: str, limit: int = 8) -> dict:
    """Resolve a free-text query to ranked concordance entries.

    Returns {query, normalized, detected_code, count, ambiguous, results[],
    suggestions[], meta{}}. `ambiguous` is True when 2+ results tie closely on
    the top structural score (e.g. a bare number used by several codes), which
    the UI surfaces as a 'did you mean' disambiguation strip.
    """
    raw = (raw_query or "").strip()
    if not raw:
        return {
            "query": raw, "normalized": "", "detected_code": None,
            "count": 0, "ambiguous": False, "results": [],
            "suggestions": popular(), "meta": _public_meta(),
        }

    q = raw.translate(_HINDI_DIGITS)
    code = _detect_code(q)
    sec = _extract_section(q)
    sub = _subsection(q)
    tokens = _name_tokens(q)

    scored = []
    for entry in _mappings():
        s = 0
        if sec:
            s += _struct_score(entry, sec, code, sub)
        s += _name_score(entry, tokens)
        if s > 0:
            scored.append((s, entry))

    scored.sort(key=lambda x: x[0], reverse=True)
    top = scored[:limit]

    # Ambiguous when the top two are both strong and near-tied — typically a
    # bare section number shared across IPC / CrPC / Evidence.
    ambiguous = (
        len(top) >= 2
        and top[0][0] >= 80
        and (top[0][0] - top[1][0]) <= 15
        and top[1][0] >= 80
    )

    return {
        "query": raw,
        "normalized": q,
        "detected_code": code,
        "count": len(scored),
        "ambiguous": ambiguous,
        "results": [_augment(e) for _, e in top],
        "suggestions": [] if scored else popular(),
        "meta": _public_meta(),
    }


def popular() -> list[dict]:
    """Empty-state chips of the most-looked-up sections."""
    return list(_POPULAR)


def _public_meta() -> dict:
    m = _meta()
    return {
        "version": m.get("version"),
        "enforcement_date": m.get("enforcement_date"),
        "disclaimer": m.get("disclaimer"),
        "verification_status": m.get("verification_status"),
        "total_entries": len(_mappings()),
    }
