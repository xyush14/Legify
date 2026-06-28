"""Legal Lens — annotate document text with explainable legal terms + statute refs.

POST /api/lexicon/annotate {text} -> {matches: [...]}

Every annotation is built from CURATED / VERIFIED data only — no LLM, no
fabrication:
  - statute references  → statute_map concordance (IPC↔BNS / CrPC↔BNSS / IEA↔BSA),
                          incl. the "repealed → new section" advisory + attributes
  - legal terms         → headnote/data/legal_lexicon.json (advocate-reviewable defs)
  - leading cases       → headnote/data/cases.json (hand-verified; shown only if a
                          real match exists, else omitted)

The client wraps occurrences of each `match` string in the rendered text and
shows the payload on click. Matches are returned longest-first so a section
phrase ("Section 302 IPC") wins over any substring.
"""

from __future__ import annotations

import functools
import json
import re

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from headnote import config, statute_map
from headnote.entitlements import CurrentUser, get_current_user
from headnote.retrieval.fact_extractor import _STATUTE_THEN_NUMBER


router = APIRouter(prefix="/api/lexicon", tags=["lexicon"])

_HINDI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")
_OLD_CODES = {"IPC", "CrPC", "Evidence Act", "Evidence", "IEA"}

# Only these families live in the IPC↔BNS / CrPC↔BNSS / IEA↔BSA concordance.
# A special-law ref (NI Act, POCSO, NDPS …) must NOT be run through it — a bare
# number would mis-resolve to an unrelated penal section.
_CONCORDANCE_FAMILIES = {"ipc", "crpc", "evidence", "bns", "bnss", "bsa"}

# Section reference where any code is DIRECTLY attached (trailing) — so the code
# can't bleed in from a neighbouring clause. "Section 302 IPC", "u/s 420",
# "Section 138 NI Act", "S. 34". Bare numbers (no attached code) are read as IPC.
_SECTION_FULL = re.compile(
    r"(?:\b(?:S\.|Sec\.?|Section|u/s|U/Sec|U/S|S/)|धारा|दफ़ा|दफा)\s*"
    r"(\d{1,4}[A-Z]{0,3}(?:\([\dA-Za-z]+\))*)"
    r"(?:\s*(IPC|Cr\.?P\.?C\.?|CrPC|BNSS|BNS|BSA|Evidence\s*Act|IEA|NI\s*Act|"
    r"POCSO|NDPS|PMLA|UAPA|Arms\s*Act|MV\s*Act|IT\s*Act|JJ\s*Act|DV\s*Act|"
    r"PC\s*Act|Companies\s*Act))?",
    re.IGNORECASE,
)

# Map a statute code/name to a coarse family token used to match cases.json.
_FAMILY = {
    "ipc": "ipc", "penal": "ipc",
    "crpc": "crpc", "code of criminal procedure": "crpc",
    "bns": "bns", "bnss": "bnss", "bsa": "bsa",
    "evidence": "evidence", "iea": "evidence",
    "ni": "ni", "negotiable": "ni",
    "pocso": "pocso", "ndps": "ndps", "pmla": "pmla", "uapa": "uapa",
    "constitution": "constitution",
}


def _sec_base(s: str) -> str:
    """'304A'→'304a', '103(2)'→'103', '138'→'138'."""
    m = re.match(r"\s*(\d+)\s*([A-Za-z]?)", str(s or ""))
    return (m.group(1) + (m.group(2) or "")).lower() if m else ""


def _family(name: str) -> str:
    n = (name or "").lower()
    for key, fam in _FAMILY.items():
        if key in n:
            return fam
    return ""


# --------------------------------------------------------------- case index

@functools.lru_cache(maxsize=1)
def _case_index() -> dict:
    """(family, section_base) -> list of {title, citation}. Built from the
    hand-verified cases.json so we only ever surface real, locatable cases."""
    idx: dict[tuple[str, str], list[dict]] = {}
    try:
        cases = config.load_curated_corpus()
    except Exception:  # noqa: BLE001
        return idx
    for c in cases:
        title, cite = c.get("title"), c.get("citation")
        if not title:
            continue
        for st in (c.get("statutes") or []):
            fam = _family(st)
            if not fam:
                continue
            for secm in re.finditer(r"\bS\.?\s*(\d+[A-Za-z]?)", st):
                key = (fam, _sec_base(secm.group(1)))
                idx.setdefault(key, [])
                if not any(x["title"] == title for x in idx[key]):
                    idx[key].append({"title": title, "citation": cite})
    return idx


def _find_case(*families: str, sec: str) -> dict | None:
    base = _sec_base(sec)
    if not base:
        return None
    idx = _case_index()
    for fam in families:
        hits = idx.get((fam, base))
        if hits:
            return hits[0]
    return None


# --------------------------------------------------------------- lexicon

@functools.lru_cache(maxsize=1)
def _lexicon() -> list[tuple[re.Pattern, dict]]:
    """Compile (word-boundary regex, payload) for every term + alias + hindi."""
    path = config.PACKAGE_DIR / "data" / "legal_lexicon.json"
    try:
        terms = json.loads(path.read_text(encoding="utf-8")).get("terms", [])
    except Exception:  # noqa: BLE001
        return []
    out: list[tuple[re.Pattern, dict]] = []
    for t in terms:
        payload = {
            "kind": "term",
            "term": t.get("term", ""),
            "hi": t.get("hi", ""),
            "definition": t.get("def", ""),
            "section": t.get("section", ""),
        }
        forms = [t.get("term", "")] + list(t.get("aliases") or [])
        if t.get("hi"):
            forms.append(t["hi"])
        for f in forms:
            f = (f or "").strip()
            if len(f) < 3:
                continue
            # \b is unreliable around Devanagari; allow either word-boundary or
            # non-letter neighbours.
            rx = re.compile(r"(?<![\wऀ-ॿ])" + re.escape(f) + r"(?![\wऀ-ॿ])",
                            re.IGNORECASE)
            out.append((rx, payload))
    # longest forms first so multi-word terms beat their parts
    out.sort(key=lambda x: -len(x[0].pattern))
    return out


@functools.lru_cache(maxsize=1)
def _lexicon_lookup() -> dict:
    """normalised term/alias/hi -> payload, for exact 'select → Explain' hits."""
    path = config.PACKAGE_DIR / "data" / "legal_lexicon.json"
    try:
        terms = json.loads(path.read_text(encoding="utf-8")).get("terms", [])
    except Exception:  # noqa: BLE001
        return {}
    idx: dict = {}
    for t in terms:
        payload = {"term": t.get("term", ""), "hi": t.get("hi", ""),
                   "definition": t.get("def", ""), "section": t.get("section", "")}
        for f in [t.get("term", "")] + list(t.get("aliases") or []) + ([t["hi"]] if t.get("hi") else []):
            k = re.sub(r"\s+", " ", (f or "").strip().lower())
            if k:
                idx[k] = payload
    return idx


# --------------------------------------------------------------- sections

def _attrs_from_result(res: dict) -> list[dict]:
    out = []
    for d in (res.get("diff") or []):
        if d["field"] in ("cognizable", "bailable", "court"):
            val = (d.get("new") or d.get("old") or "").strip()
            if val and val.lower() != "verify":
                out.append({"label": d["label"], "value": val})
    return out


def _section_payload(code: str | None, sec: str, label: str,
                     assumed: bool = False) -> dict | None:
    """Resolve a detected statute ref to an explanation via the concordance.

    `assumed` means no code was written next to the number and we read it as IPC
    (the default in a criminal document). To avoid a confidently-wrong mapping
    (e.g. a bare "Section 34" resolving to Evidence Act), an assumed ref is only
    accepted when it lands on a Penal-Code provision.
    """
    # Only consult the concordance for codes it actually covers; a special-law
    # ref relies on the verified case index instead (never a guessed mapping).
    res = None
    if _family(code) in _CONCORDANCE_FAMILIES:
        try:
            hits = statute_map.lookup(f"{sec} {code}", limit=1).get("results") or []
            res = hits[0] if hits else None
        except Exception:  # noqa: BLE001
            res = None

    if assumed and (not res or res.get("domain") != "penal"):
        return None

    old = (res or {}).get("old") or {}
    new = (res or {}).get("new") or {}
    old_code = (old.get("code") or "").strip()
    repealed = bool(old_code in _OLD_CODES and new.get("section"))

    # case: try the detected family, then the mapped (old/new) families
    fams = []
    if code:
        fams.append(_family(code))
    fams += [_family(old_code), _family(new.get("code") or "")]
    fams = [f for f in dict.fromkeys(fams) if f]
    case = None
    for s in (sec, old.get("section"), new.get("section")):
        if s:
            case = _find_case(*fams, sec=s)
            if case:
                break

    if not res and not case:
        return None  # nothing verified to say — don't underline

    return {
        "kind": "section",
        "display": label,
        "title": old.get("title") or new.get("title") or "",
        "repealed": repealed,
        "old": {"code": old_code, "section": old.get("section", "")} if old else None,
        "new": {"code": (new.get("code") or ""), "section": new.get("section", "")} if new.get("section") else None,
        "attrs": _attrs_from_result(res or {}),
        "summary": (res or {}).get("summary", ""),
        "confidence": (res or {}).get("confidence", ""),
        "assumed": assumed,
        "case": case,
    }


def _detect_sections(text: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()

    def add(match_text: str, code: str | None, sec: str):
        key = match_text.lower()
        if key in seen:
            return
        # No code written next to the number → read as IPC (criminal default),
        # accepted only if it resolves to a Penal-Code provision.
        assumed = code is None
        payload = _section_payload(code or "IPC", sec, match_text.strip(), assumed=assumed)
        if payload:
            payload["match"] = match_text.strip()
            out.append(payload)
            seen.add(key)

    # Detect on a digit-normalised copy (४२० → 420), but return the literal from
    # the ORIGINAL text (translate() is 1:1 so offsets line up) — so the client
    # can still find "धारा ४२०" with its Devanagari digits in the rendered text.
    norm = text.translate(_HINDI_DIGITS)

    # "IPC 302", "BNS 103", "NI Act 138" — code-first form
    for m in _STATUTE_THEN_NUMBER.finditer(norm):
        add(text[m.start():m.end()], m.group(1), m.group(2))

    # "Section 302 IPC", "u/s 420", "धारा 420", "S. 34" — code (if any) captured
    # ONLY when directly attached; otherwise None → read as IPC.
    for m in _SECTION_FULL.finditer(norm):
        add(text[m.start():m.end()].strip(), m.group(2), m.group(1))

    return out


def _detect_terms(text: str, taken: list[str]) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    taken_low = " ".join(taken).lower()
    for rx, payload in _lexicon():
        m = rx.search(text)
        if not m:
            continue
        lit = m.group(0)
        key = lit.lower()
        if key in seen or key in taken_low:
            continue
        seen.add(key)
        out.append({**payload, "match": lit})
    return out


_EXPLAIN_SYSTEM = (
    "You are a precise legal assistant for Indian advocates. The user selected a "
    "term or short phrase from a legal or medico-legal document (e.g. an FIR, "
    "bail order, post-mortem / injury report) and wants to understand it. Define "
    "it in plain language in 2-4 short sentences. If it is a medical / forensic "
    "term, say what it is and why it matters in a legal context (e.g. its bearing "
    "on cause of death, injury severity, or intent). Be accurate and neutral. "
    "Do NOT cite cases, do NOT invent statute or section numbers, do NOT add "
    "disclaimers. If you are not certain what the term means, say so plainly. "
    "Output only the explanation text."
)


class ExplainBody(BaseModel):
    term: str = Field("", max_length=160)
    context: str = Field("", max_length=600)


@router.post("/explain", summary="Explain a selected term — curated first, AI fallback (labelled)")
def explain(body: ExplainBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    term = re.sub(r"\s+", " ", (body.term or "").strip()).strip(" .,:;\"'()[]")
    if len(term) < 2:
        return {"source": "none", "term": term, "definition": ""}

    # 1) verified glossary (instant, free)
    hit = _lexicon_lookup().get(term.lower())
    if hit:
        return {"source": "curated", "term": hit["term"] or term,
                "definition": hit["definition"], "hi": hit["hi"], "section": hit["section"]}

    # 2) labelled AI fallback (cheap model: DeepSeek → free Groq). Definitions
    # only — the system prompt forbids cases / fabricated sections.
    try:
        from headnote.llm.client import _call_deepseek_or_groq
        user_prompt = f'Term: "{term}"'
        if body.context:
            user_prompt += f'\nSurrounding text: "{body.context.strip()[:500]}"'
        user_prompt += "\nExplain this term."
        text, _meta = _call_deepseek_or_groq(
            _EXPLAIN_SYSTEM, user_prompt, max_tokens=240,
            claude_model="claude-haiku-4-5-20251001",
        )
        definition = re.sub(r"\s+\n", "\n", (text or "").strip())
        if not definition:
            raise RuntimeError("empty")
        return {"source": "ai", "term": term, "definition": definition}
    except Exception:  # noqa: BLE001
        return {"source": "none", "term": term,
                "definition": "Couldn't fetch an explanation right now — try again."}


class AnnotateBody(BaseModel):
    text: str = Field("", max_length=200_000)


@router.post("/annotate", summary="Detect explainable legal terms + statute refs in text")
def annotate(body: AnnotateBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    text = body.text or ""
    if not text.strip():
        return {"matches": []}
    sections = _detect_sections(text)
    terms = _detect_terms(text, taken=[s["match"] for s in sections])
    matches = sections + terms
    # longest match first → client wraps the longest span and skips substrings
    matches.sort(key=lambda x: -len(x.get("match", "")))
    return {"matches": matches}
