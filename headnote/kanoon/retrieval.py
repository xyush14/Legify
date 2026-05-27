"""
Indian-Kanoon-backed retrieval pipeline for the situation endpoint.

Given a lawyer's situation description, returns the most relevant cases
(curated + IK-fetched) along with paragraph-level evidence ready to feed
to Claude and later verified by verify.py.

Pipeline
========
  1. Query understanding (cheap, in-process):
        - Pull out statute references ("S. 138", "Article 21")
        - Pull out statute names ("NI Act", "IPC")
        - Build the IK search formInput (text + filters)

  2. Curated-corpus pre-filter (existing retrieval.py, free):
        - Pick top-K curated cases that match the query.
        - These are highest-trust (editorial supervision).

  3. IK search (paid: 1 × ₹0.50):
        - Filtered to Supreme Court + High Courts by default
          (criminal practice; configurable).
        - Returns up to 10 hits per page.

  4. Hit ranking (free, in-process):
        - Combine: query keyword overlap on headline,
                   citation weight (numcitedby),
                   recency boost,
                   whether IK already returned a category tag matching query.
        - De-dupe vs curated (don't fetch what's already curated).

  5. Doc fetch for top-N (paid: N × ₹0.20, but cached after first time):
        - Hard cap on new fetches per query (default 5) to control cost.
        - Cache hits cost ₹0.

  6. Paragraph-level ranking (free):
        - Each paragraph gets a score = structure_prior + keyword_match + statute_match
        - Structure prior boosts Conclusion / CDiscource (court discussion)
          paragraphs; these are where the ratio lives.

  7. Return RetrievalResult:
        - cases: list of CaseSummary (mixed curated + IK)
        - evidence: flat list of EvidenceParagraph (ready for verify.py)
        - meta: cost incurred, cache hit rate, sources used

Cost discipline
===============
Every IK live call is logged via kanoon_client's spend ledger. The retrieval
function never fetches more than `max_new_fetches_per_query` new judgments
in a single call (default 5 = ~₹1 worst case). Cached fetches don't count
against the budget.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field
from typing import Iterable, Optional

from headnote.kanoon.client import (
    KanoonBudgetExceeded,
    KanoonClient,
    KanoonError,
    KanoonNotFound,
    SearchHit,
)
from headnote.kanoon.parser import ParsedJudgment, Paragraph, parse_judgment, extract_statutes
from headnote.retrieval.keyword import score_case as score_curated_case
from headnote.verify import EvidenceParagraph

# Embeddings are optional — if the embeddings module / model is unavailable
# (e.g. fastembed not installed), the retrieval pipeline degrades gracefully
# to keyword-only.
try:
    from headnote.retrieval.embeddings import EmbeddingIndex, EmbeddingHit
    _EMBEDDINGS_AVAILABLE = True
except Exception as _emb_err:
    _EMBEDDINGS_AVAILABLE = False
    EmbeddingIndex = None  # type: ignore
    EmbeddingHit = None    # type: ignore


# ---------------------------------------------------------------- config / DTOs

# Filters to apply to IK searches by default. Criminal-law practitioners want
# SC + HC mostly — district courts and tribunals are noisy. Override via
# search_filters= when needed.
DEFAULT_SEARCH_FILTERS = "doctypes:supremecourt,highcourts"

# Per-call caps. Tune in main.py once we have real usage data.
DEFAULT_TOP_CASES = 5           # back to 5: lawyers want options; HF corpus carries the load
DEFAULT_CANDIDATE_POOL = 25     # candidates to collect before hidden_authorities reranking
DEFAULT_TOP_PARAGRAPHS_PER_CASE = 2   # 4→2: shorter Phase 2 prompts, faster generation
# IK doc-fetch caps. With parallel fetches (ThreadPoolExecutor), the
# serial-wait penalty no longer scales linearly — bumping from 4 → 6
# costs ~1 extra second total, not 6.
import os as _os
DEFAULT_MAX_NEW_FETCHES = int(_os.environ.get("MAX_IK_FETCHES", "3"))
DEFAULT_MAX_NEW_FETCHES_HIDDEN = int(_os.environ.get("MAX_IK_FETCHES_HIDDEN", "4"))
# 6 → 4 parallel: stays under IK's rate limit while keeping latency low.
# IK doc fetch parallelism. 8 = comfortable for IK's rate limits (they
# allow up to 10 concurrent connections per IP without throttling) and
# cuts wall-clock time from ~15s (sequential) to ~3s (parallel) for a
# typical 8-10 doc cold-cache fetch.
DEFAULT_IK_FETCH_PARALLELISM = int(_os.environ.get("IK_FETCH_PARALLELISM", "8"))

# Skip the paid IK live search when free local sources (HF corpus 42K +
# semantic cache + curated 42) have already filled the pool with enough
# substantive cases. Counts ONLY ik-semantic + hf + curated; the IK live
# branch hasn't run yet at this check.
#
# Raised 3 → 8: IK has 2.6 crore judgments — vastly more than HF's 290K.
# Skipping IK because local pool has 3 cases means the lawyer never sees
# the broader IK universe. The whole point of IK integration is access
# to authorities our local corpus doesn't have. We now keep IK running
# unless the local pool ALREADY has a strong 8+ candidate set (in which
# case the LLM has enough to discriminate from).
DEFAULT_SKIP_IK_SEARCH_IF_CASES_AT_LEAST = int(_os.environ.get("SKIP_IK_IF_CASES", "8"))

# Structural priors for paragraph ranking. Higher = more likely to carry the ratio.
STRUCTURE_PRIOR: dict[str, float] = {
    "conclusion": 4.0,
    "ratio": 4.0,
    "court_discussion": 2.5,
    "section_discussion": 1.5,
    "issue": 1.2,
    "precedent": 1.0,
    "facts": 0.6,
    "petitioner_argument": 0.4,
    "respondent_argument": 0.4,
    "other": 0.3,
}


@dataclass
class CaseSummary:
    """One case in the retrieval result. Provenance shown to the lawyer."""
    case_id: str                # "BHASK-1999-SC" (curated) or "ik:529907"
    title: str
    court: str
    year: str | int
    citation: str
    bench: str = ""
    source: str = "ik"          # "curated" | "ik" | "hf-semantic" | "hf-keyword"
    numcitedby: int = 0
    relevance_score: float = 0.0
    paragraphs: list[Paragraph] = field(default_factory=list)
    statutes: list[str] = field(default_factory=list)
    # New: outcome and district pulled from HF judgment metadata so the
    # frontend can render a real disposition badge + jurisdiction.
    outcome: str = ""           # "bail-granted" | "bail-denied" | "acquittal" | ...
    district: str = ""          # Only for BAIL subset cases (e.g., "agra")


# ----------------------------------------------------------------- HF helpers

def _looks_like_section_marker(s: str) -> bool:
    """A line like `=== Facts And Arguments ===` is a section header injected
    during HF text flattening, NOT a real case title. The harvest script's
    `_synthesize_title` had a bug where these section markers got picked as
    the title; fix at retrieval time so we don't need to re-import."""
    s = (s or "").strip()
    return bool(s) and (s.startswith("===") or s.endswith("==="))


def _hf_label_to_outcome(label, subset: str) -> str:
    """Map IL-TUR labels to the outcome enum the frontend renders.

    BAIL labels:
      "GRANTED" / 1  → bail-granted
      "REJECTED"/ "DENIED" / 0 → bail-denied
    CJPE labels (binary appeal accepted/rejected):
      1 / "ACCEPTED"  → quashed     (appeal accepted ≈ relief granted)
      0 / "REJECTED"  → dismissed
    SUMM has no outcome label — return "".
    """
    if label is None or label == "":
        return ""
    s = str(label).strip().upper()
    if subset == "bail":
        if s in {"1", "GRANTED", "TRUE", "YES"}: return "bail-granted"
        if s in {"0", "REJECTED", "DENIED", "FALSE", "NO"}: return "bail-denied"
        return ""
    if subset == "cjpe":
        if s in {"1", "ACCEPTED", "ALLOWED", "TRUE"}: return "quashed"
        if s in {"0", "REJECTED", "DISMISSED", "FALSE"}: return "dismissed"
        return ""
    return ""


def _hf_court_label(court: str, district: str | None, case_metadata: dict | None = None) -> str:
    """Build a properly-formatted court label.

    Priority:
      1. Extracted court from case_metadata_json (e.g., "High Court of Madhya Pradesh, Gwalior Bench")
      2. district + subset-court combination (BAIL: "Agra District Court")
      3. Hardcoded subset-to-label map
    """
    # 1. Prefer extracted court if metadata gives it
    if case_metadata:
        ext_court = (case_metadata.get("court") or "").strip()
        bench = (case_metadata.get("bench") or "").strip()
        if ext_court:
            # If extractor split bench into separate field, append it cleanly
            if bench and bench.lower() not in ext_court.lower():
                return f"{ext_court}, {bench}"
            return ext_court

    base = {
        "supreme_court":         "Supreme Court",
        "supreme_court_or_hc":   "Supreme Court / High Court",
        "high_court":            "High Court",
        "district_court":        "District Court",
    }.get(court or "", court or "")
    if court == "district_court" and district:
        return f"{district.strip().title()} District Court"
    return base


# IL-TUR anonymization tokens. The `lsi` subset (Legal Statute Identification)
# masks every entity/act/section for its ML benchmark — <ACT>, <ENTITY>,
# <SECTION>, <COURT>, <PETITIONER>, etc. Such judgments are UNUSABLE for legal
# display: the lawyer can't identify the case, the law, or cite it. We detect
# and exclude them from retrieval entirely.
_ANON_TOKEN_RE = re.compile(r"<[A-Z][A-Z_]{1,20}>")

# A real, identifiable title has a party caption ("X v. Y") OR a recognisable
# case-number pattern. Anything else (a body sentence) is not show-worthy.
_CAPTION_RE = re.compile(r"\sv(?:s|\.|s\.)?\s", re.IGNORECASE)
_CASENO_RE = re.compile(
    r"(?:criminal|civil)\s+appeal\s+no|appeal\s+no\.?\s*\d|"
    r"petition\s+no|w\.?\s*p\.?\s*[\(\.]|s\.?\s*l\.?\s*p|cr\.?\s*a\.?\s*no|"
    r"writ\s+petition|special\s+leave|m\.?cr\.?c|bail\s+appl",
    re.IGNORECASE,
)


def _is_anonymized(text: str, threshold: int = 2) -> bool:
    """True if `text` contains IL-TUR anonymization tokens (>= threshold).

    A single stray '<...>' could be legitimate (rare), so we require at least
    two masking tokens before treating a judgment as anonymized.
    """
    if not text:
        return False
    return len(_ANON_TOKEN_RE.findall(text)) >= threshold


def _hf_clean_title(hj, case_id: str) -> Optional[str]:
    """Return an identifiable title for an HF judgment, or None to SUPPRESS it.

    A lawyer must be able to recognise and cite the case. We only accept:
      1. A real party caption ("X v. State of Y") from metadata, or
      2. A stored title that is itself a caption or a case-number, or
      3. An extracted case number.
    Body-sentence titles ("This appeal has been filed...", "Certified copy
    of the statement...") return None → the case is dropped rather than shown
    with an unrecognisable title. Better to surface fewer, verifiable IK
    judgments than messy HF ones.
    """
    md = getattr(hj, "case_metadata", None) or {}
    # 1. Real party caption from extracted metadata
    parties = (md.get("parties") or "").strip()
    if parties and 5 <= len(parties) <= 200 and _CAPTION_RE.search(parties):
        return parties
    # 2. Stored title IF it is itself an identifiable caption / case number
    src = (hj.title or "").strip()
    if src and 10 <= len(src) <= 200:
        if _CAPTION_RE.search(src) or _CASENO_RE.search(src):
            return src
    # 3. Extracted case number
    case_no = (md.get("case_number") or "").strip()
    if case_no and _CASENO_RE.search(case_no):
        return case_no
    # Nothing identifiable — suppress.
    return None


def _hf_synthesize_title(hj, case_id: str) -> str:
    """Build a presentable title for an HF judgment.

    Priority order:
      1. Extracted parties from case_metadata_json (cleanest — real "X v. Y")
      2. case_number from metadata (e.g. "Criminal Appeal No. 1234 of 2023")
      3. Original stored title IF it looks usable (>10 chars, no section markers)
      4. Subset-specific fallback (BAIL → "Bail Application — <district> · <verdict>")
    """
    md = getattr(hj, "case_metadata", None) or {}
    # 1. Best: extracted parties caption
    parties = (md.get("parties") or "").strip()
    if parties and 5 <= len(parties) <= 200 and " v. " in parties:
        return parties
    # 2. Fall back to case number if we extracted one
    case_no = (md.get("case_number") or "").strip()
    if case_no and 10 <= len(case_no) <= 200:
        return case_no

    # 3. Original stored title (only if it looks clean)
    src = (hj.title or "").strip()
    if src and not _looks_like_section_marker(src) and len(src) > 10 and "===" not in src:
        # Reject titles that look like body sentences
        body_starts = (
            "on a ", "in the matter ", "the petitioner ", "the appellant ",
            "the respondent ", "this is ", "by this ", "the present ",
            "facts ", "brief facts ",
        )
        if not src.lower().startswith(body_starts):
            return src

    # 4. Subset-specific reconstruction
    subset = (case_id.split(":")[1] if case_id.startswith("hf:") and ":" in case_id[3:] else "")
    short_id = (case_id.rsplit(":", 1)[-1] or "").replace("_", " ")
    if subset == "bail":
        district = (getattr(hj, "district", None) or "").strip()
        # Prefer extracted court label if metadata has it
        ext_court = (md.get("court") or "").strip()
        label = (getattr(hj, "label", None) or "").strip().upper()
        verdict = ""
        if label in {"GRANTED", "1"}:
            verdict = " · BAIL GRANTED"
        elif label in {"REJECTED", "DENIED", "0"}:
            verdict = " · BAIL REJECTED"
        loc = ext_court if ext_court else (district.title() if district else "District Court")
        return f"Bail Application — {loc}{verdict} (#{short_id[:40]})"
    # For other subsets — use extracted court if available, else generic
    ext_court = (md.get("court") or "").strip()
    if ext_court:
        return f"{ext_court} — {short_id[:60]}"
    if subset == "cjpe":
        return f"Supreme Court Judgment (CJPE) — {short_id[:80]}"
    if subset == "summ":
        return f"Supreme/High Court Judgment (SUMM) — {short_id[:80]}"
    return f"Judgment {short_id[:80]}"


@dataclass
class RetrievalMeta:
    elapsed_seconds: float
    ik_search_calls: int = 0
    ik_fetch_calls: int = 0
    cache_hits: int = 0
    semantic_hits: int = 0                  # paragraphs surfaced from local embedding index
    inr_spent_this_call: float = 0.0
    notes: list[str] = field(default_factory=list)


@dataclass
class RetrievalResult:
    cases: list[CaseSummary]
    evidence: list[EvidenceParagraph]
    meta: RetrievalMeta


# ----------------------------------------------------------- query understanding

# Statute and section markers we recognise in lawyer situations
_STATUTE_HINT_RX = re.compile(
    r"\b(BNS|BNSS|BSA|IPC|CrPC|PMLA|UAPA|NDPS|POCSO|FIR|ECIR|MCOCA|TADA|"
    r"NI\s+Act|Negotiable\s+Instruments(?:\s+Act)?|Penal\s+Code|"
    r"Evidence\s+Act|Indian\s+Evidence\s+Act|"
    r"Code\s+of\s+Criminal\s+Procedure|"
    r"Bharatiya\s+Nyaya\s+Sanhita|Bharatiya\s+Nagarik\s+Suraksha\s+Sanhita)\b",
    re.IGNORECASE,
)
_SECTION_HINT_RX = re.compile(
    r"\b(?:S\.?|Sec\.?|Section)\s*(\d+[A-Z]?(?:\([\d\w]+\))?)",
    re.IGNORECASE,
)
_ARTICLE_HINT_RX = re.compile(r"\bArt(?:icle)?\.?\s*(\d+[A-Z]?(?:\([\d\w]+\))?)", re.IGNORECASE)

# Stopwords that add noise to IK search if passed verbatim. Includes:
#   - English function words (the, a, of, ...)
#   - Generic legal procedural nouns that match too many docs (accused,
#     complainant, person, party, year, month, age)
#   - First-person framing words from a lawyer's prose (client, my, his)
_QUERY_STOPWORDS = {
    # function words
    "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "of",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "this", "that", "these", "those", "what", "which",
    "who", "whether", "when", "where", "while", "such",
    # generic procedural nouns (match thousands of docs)
    "case", "cases", "court", "courts", "judgment", "judgments", "law",
    "client", "lawyer", "matter", "situation", "facts", "fact", "question",
    "accused", "complainant", "victim", "person", "party", "parties",
    "year", "years", "month", "months", "day", "days", "age", "old",
    "male", "female", "boy", "girl", "man", "woman", "child",
    "rep", "representative", "deputy", "officer",
    # framing verbs from prose
    "wants", "needs", "need", "looking", "find", "needed", "want",
    "precedents", "precedent", "ruling", "rulings", "ratio", "principle",
    "principles", "leading", "important", "key", "main", "alleged",
    "alleging", "claims", "claiming", "stated", "states",
    # possessives + pronouns
    "my", "his", "her", "their", "our", "your",
}

# High-signal legal terms — when present, KEEP them even if short. These
# are the words that actually distinguish a POCSO acquittal case from a
# general quashing case.
_LEGAL_KEEP_TERMS = {
    # statutes + procedural acts
    "pocso", "ndps", "pmla", "uapa", "ipc", "crpc", "bns", "bnss", "bsa",
    "mcoca", "tada", "fir", "ecir",
    # remedies / dispositions (the lawyer's actual ask)
    "acquittal", "acquitted", "conviction", "convicted",
    "quashing", "quashed", "bail", "anticipatory", "discharge", "discharged",
    "remand", "revision", "appeal", "review", "stay", "suspension",
    # substantive triggers
    "consent", "consensual", "minor", "majority", "voluntary",
    "cruelty", "dowry", "domestic", "rape", "murder", "homicide",
    "circumstantial", "dishonour", "cheque", "maintenance",
    "custody", "remand", "chargesheet", "discharge", "compromise",
    # evidentiary terms
    "evidence", "evidentiary", "testimony", "corroboration", "delay",
    "improvement", "contradiction", "hearsay", "electronic",
    "chats", "messages", "calls", "records",
    # outcome favorability
    "false", "implication", "malicious",
}

# Proper-noun detector: capitalised tokens with at least 2 chars, not at
# sentence start only (to capture "Vijay Madanlal Choudhary" but not "My").
_PROPER_NOUN_RX = re.compile(r"\b([A-Z][a-zA-Z]{2,})(?:\s+([A-Z][a-zA-Z]{2,}))+\b")


def _distill_query(situation: str, *, max_tokens: int = 8) -> str:
    """Turn a lawyer's natural-language situation into an IK-friendly search.

    IK's search is keyword-boolean. The previous distiller produced queries
    like "FIR POCSO Need POCSO Accused major male complainant years months
    Consensual" — over-constrained on generic procedural words, under-
    specific on the actual legal question. Result: IK returned generic
    quashing cases instead of POCSO acquittal cases.

    New strategy, in priority order (best signal first):

      1. Statute names (POCSO, NDPS, NI Act, ...) — most distinguishing
      2. Section / article refs (S. 138, Art. 21)
      3. High-signal legal terms from _LEGAL_KEEP_TERMS (acquittal,
         consent, quashing, ...) — the lawyer's actual ask
      4. Multi-word proper nouns (specific case names)
      5. Residual long content words (a fallback)

    Deduplication is case-insensitive, including across categories.
    """
    tokens: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> bool:
        t = tok.strip()
        if not t:
            return False
        key = t.lower()
        # Reject duplicates and substring duplicates ("POCSO" + "pocso" + "POCSO Act")
        if key in seen:
            return False
        for prev in seen:
            if key == prev or (len(key) > 3 and key in prev) or (len(prev) > 3 and prev in key):
                return False
        seen.add(key)
        tokens.append(t)
        return True

    # 1. Statute names (canonical) — deduplicate aggressively
    for m in _STATUTE_HINT_RX.finditer(situation):
        add(m.group(0).strip())

    # 2. Section + article refs
    for m in _SECTION_HINT_RX.finditer(situation):
        add(f"Section {m.group(1)}")
    for m in _ARTICLE_HINT_RX.finditer(situation):
        add(f"Article {m.group(1)}")

    # 3. High-signal legal terms — the words that actually distinguish
    # the lawyer's matter from a generic case
    for w in re.findall(r"[A-Za-z][A-Za-z\-]+", situation):
        if len(tokens) >= max_tokens:
            break
        wl = w.lower()
        if wl in _LEGAL_KEEP_TERMS:
            add(w)

    # 4. Multi-word proper nouns (case names like "Vijay Madanlal Choudhary")
    if len(tokens) < max_tokens:
        for m in _PROPER_NOUN_RX.finditer(situation):
            if len(tokens) >= max_tokens:
                break
            add(m.group(0).strip())

    # 5. Residual content words (last resort — only longish words, not stop)
    if len(tokens) < max_tokens:
        for w in re.findall(r"[A-Za-z][A-Za-z\-]+", situation):
            if len(tokens) >= max_tokens:
                break
            wl = w.lower()
            if len(w) < 5 or wl in _QUERY_STOPWORDS:
                continue
            add(w)

    return " ".join(tokens[:max_tokens])


def _build_search_input(
    situation: str,
    extra_filters: str = "",
    refined_query: Optional[dict] = None,
) -> str:
    """Compose the IK search formInput from the lawyer's situation.

    PHILOSOPHY: Lawyers don't search by section number — they search by
    FACT PATTERN, LEGAL ISSUE, and DOCTRINAL PRINCIPLE. IK's API is
    keyword-based but the keywords we send don't have to be section
    numbers. We construct an IK query rich in fact-pattern phrases and
    plain-English doctrinal terms; the statute reference is included as
    an anchor (helps narrow) but is NOT what leads the search.

    Query construction order (most important first for IK keyword scoring):
      1. factual_archetype       — high-level fact-pattern label
      2. core_circumstances      — 2 specific fact phrases
      3. legal_concepts          — plain-English doctrinal terms
      4. doctrines_at_issue      — formal doctrine names
      5. stage                   — procedural posture
      6. primary_statute         — statute anchor (LAST, single mention)
      7. dual_statute (old code) — for pre-2024 cases on the same concept

    Falls back to _distill_query when refined_query is None.
    The raw situation is NEVER sent verbatim — IK's keyword search returns
    zero hits for long natural-language queries.
    """
    if refined_query:
        parts: list[str] = []
        # ── FACTS first ──
        if refined_query.get("factual_archetype"):
            fa = str(refined_query["factual_archetype"]).replace("_", " ")
            if fa: parts.append(fa)
        for circ in (refined_query.get("core_circumstances") or [])[:2]:
            if circ:
                # IK API has a length limit on formInput; keep each phrase short
                s = str(circ).strip()
                if 6 <= len(s) <= 80:
                    parts.append(s)
        # ── ISSUE / DOCTRINE ──
        for lc in (refined_query.get("legal_concepts") or [])[:3]:
            if lc:
                s = str(lc).replace("_", " ").strip()
                if s and s not in parts: parts.append(s)
        for d in (refined_query.get("doctrines_at_issue") or [])[:2]:
            if d:
                s = str(d).replace("_", " ").strip()
                if s and s not in parts: parts.append(s)
        # ── Procedural posture ──
        if refined_query.get("stage"):
            stg = str(refined_query["stage"]).replace("_", " ")
            if stg and stg not in parts: parts.append(stg)
        # ── Statute anchor LAST (single primary mention) ──
        if refined_query.get("primary_statute"):
            ps = str(refined_query["primary_statute"]).strip()
            if ps and ps not in parts: parts.append(ps)
        # Include one secondary statute IF present (helps when primary is
        # generic like "IPC" and secondary specifies "Section 376"):
        for s in (refined_query.get("secondary_statutes") or [])[:1]:
            if s and str(s).strip() not in parts:
                parts.append(str(s).strip())
        # Dual-code old form (for pre-2024 cases citing IPC/CrPC):
        for ds in (refined_query.get("dual_statute_map") or [])[:1]:
            if isinstance(ds, dict):
                old = ds.get("old")
                if old and str(old).strip() not in parts:
                    parts.append(str(old).strip())
        distilled = " ".join(parts[:12])  # cap at 12 tokens for IK formInput length
    else:
        distilled = _distill_query(situation)

    if not distilled:
        # Last-resort fallback: take the first 8 alpha words >3 chars
        words = [w for w in re.findall(r"[A-Za-z]{4,}", situation) if w.lower() not in _QUERY_STOPWORDS][:8]
        distilled = " ".join(words)

    filters = extra_filters or DEFAULT_SEARCH_FILTERS
    return f"{distilled} {filters}".strip() if filters else distilled


# ----------------------------------------------------------- hit ranking

def _rank_search_hits(
    hits: list[SearchHit], query: str, *, curated_titles_lc: set[str],
    mode: str = "mixed",
) -> list[tuple[float, SearchHit]]:
    """Return hits sorted by composite relevance score (highest first).

    The mode parameter controls how citation count (fame) is weighted:
      mixed  — citation weight positive (log×1.5); classic authority ranking.
      famous — citation weight strongly boosted (log×2.5); returns landmarks.
      hidden — citation weight PENALISED (log×−0.5); obscure-but-relevant
               cases bubble up. Headline keyword match is the primary signal.

    Always drops hits already in the curated corpus (no point paying ₹0.20
    to re-fetch what we already have verbatim).
    """
    import math

    query_tokens = set(_tokens(query))
    scored: list[tuple[float, SearchHit]] = []
    for h in hits:
        title_lc = h.title.lower()
        if any(ct in title_lc or title_lc in ct for ct in curated_titles_lc):
            continue

        headline_score = len(query_tokens & set(_tokens(h.headline))) * 1.0
        court_bonus = 1.5 if "supreme court" in h.docsource.lower() else 0.0

        # IMPORTANT: in hidden mode we do NOT penalise citations here. Producing
        # negative scores breaks downstream normalisation (max_rel becomes
        # dominated by curated cases' positive keyword scores; IK gets pushed
        # to the bottom). Fame is penalised in rank_candidates() instead, where
        # the per-source-normalised relevance keeps the math fair.
        if mode == "famous":
            citation_score = math.log1p(h.numcitedby) * 2.5
        elif mode == "hidden":
            citation_score = 0.5            # constant; reranker handles fame
        else:  # mixed
            citation_score = math.log1p(h.numcitedby) * 1.0

        # Always-positive base so normalisation across sources is comparable
        score = max(0.5, citation_score + headline_score + court_bonus)
        scored.append((score, h))
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored


_WORD_RX = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return _WORD_RX.findall((text or "").lower())


# ----------------------------------------------------------- paragraph ranking

def _rank_paragraphs(
    paragraphs: list[Paragraph], query: str, top_k: int
) -> list[Paragraph]:
    """Pick the top_k most relevant paragraphs for the headnote evidence pack.

    Score = structure_prior * (1 + keyword_match) + statute_match_bonus.
    Always include at least one Conclusion paragraph if any exist (so the
    LLM has the ratio).
    """
    q_tokens = set(_tokens(query))
    q_sections = set(_section_refs(query))

    scored: list[tuple[float, Paragraph]] = []
    for p in paragraphs:
        prior = STRUCTURE_PRIOR.get(p.structure, 0.3)
        keyword_match = len(q_tokens & set(_tokens(p.text))) / max(1, len(q_tokens) or 1)
        statute_match = len(q_sections & set(_section_refs(p.text))) * 2.0
        score = prior * (1.0 + keyword_match) + statute_match
        scored.append((score, p))

    # Always reserve one slot for top-scored Conclusion if not already in top_k
    scored.sort(key=lambda t: -t[0])
    top = [p for _s, p in scored[:top_k]]
    if not any(p.structure in ("conclusion", "ratio") for p in top):
        for s, p in scored:
            if p.structure in ("conclusion", "ratio"):
                top = top[:top_k - 1] + [p]
                break
    return top


def _section_refs(text: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r"\b(?:S\.|Sec\.?|Section)\s*(\d+[A-Z]?(?:\([^\)]+\))?)", text or "", re.IGNORECASE):
        out.append(m.group(1).lower())
    return out


# ----------------------------------------------------------- curated bridge

def _curated_to_summary(c: dict, score: float) -> CaseSummary:
    return CaseSummary(
        case_id=c["id"],
        title=c["title"],
        court=c.get("court", ""),
        year=c.get("year", ""),
        citation=c.get("citation", ""),
        bench=c.get("bench", ""),
        source="curated",
        numcitedby=0,           # we don't track this for curated; could backfill
        relevance_score=score,
        paragraphs=[],          # curated cases use the corpus entry's fields, not paragraphs
        statutes=c.get("statutes", []),
    )


def _curated_to_evidence(c: dict) -> list[EvidenceParagraph]:
    """Synthesise paragraph evidence from curated corpus entry fields so the
    same verifier can validate citations against curated cases too.

    We treat the holding/facts/key_paras text as a small synthetic paragraph
    set with the case's id and no para_num (the curated entries don't carry
    paragraph numbers consistently).
    """
    out: list[EvidenceParagraph] = []
    for field_name in ("holding", "facts"):
        v = c.get(field_name)
        if isinstance(v, str) and v.strip():
            out.append(EvidenceParagraph(
                case_id=c["id"], para_id=f"curated:{field_name}",
                para_num=None, text=v.strip(),
            ))
    issues = c.get("issues") or []
    if isinstance(issues, list):
        for i, iss in enumerate(issues):
            if isinstance(iss, str) and iss.strip():
                out.append(EvidenceParagraph(
                    case_id=c["id"], para_id=f"curated:issue:{i}",
                    para_num=None, text=iss.strip(),
                ))
    return out


# ----------------------------------------------------------- main entry point

def retrieve_for_situation(
    situation: str,
    *,
    client: KanoonClient,
    curated_corpus: list[dict],
    top_cases: int = DEFAULT_TOP_CASES,
    candidate_pool: int = DEFAULT_CANDIDATE_POOL,
    top_paragraphs_per_case: int = DEFAULT_TOP_PARAGRAPHS_PER_CASE,
    max_new_fetches: int = DEFAULT_MAX_NEW_FETCHES,
    search_filters: str = DEFAULT_SEARCH_FILTERS,
    use_embeddings: bool = True,
    embedding_index: "EmbeddingIndex | None" = None,
    skip_ik_search_if_cases_at_least: int = DEFAULT_SKIP_IK_SEARCH_IF_CASES_AT_LEAST,
    mode: str = "mixed",
    jurisdiction: Optional[str] = None,
    refined_query: Optional[dict] = None,
    time_budget_seconds: float = 120.0,
) -> RetrievalResult:
    """End-to-end retrieval for a lawyer's situation query.

    Pipeline (cheapest first):
      1. Curated pre-filter (free, instant)
      2. Semantic search over locally-cached paragraphs (free, ~20ms)
      3. IK live search (₹0.50/page) + top-N fetch (₹0.20 each, capped)
           - hidden/famous: always runs IK (never skipped) to guarantee
             non-curated candidates enter the pool.
           - hidden: fetches page 1 as well (deeper, less-cited results).
           - mixed: skips IK when curated+semantic already filled the threshold.
      4. hidden_authorities reranker picks top_cases from the full pool.

    Separation of concerns:
      - candidate_pool (default 25): how many docs to collect before reranking.
      - top_cases (default 5): how many to return to the LLM after reranking.

    time_budget_seconds: wall-clock cap for the retrieval phase. If retrieval
    has already consumed most of the budget by the time the Sonnet reranker
    would fire, the reranker is skipped to prevent the downstream LLM call
    from timing out.  Caller (app.py) sets this based on the overall pipeline
    deadline minus the LLM call budget.

    Never raises on IK errors — falls back to whatever we have so far.
    """
    t0 = time.time()
    spend_before = client.spend_summary()

    # candidate_pool must be at least top_cases
    candidate_pool = max(candidate_pool, top_cases)

    meta = RetrievalMeta(elapsed_seconds=0.0)
    cases: list[CaseSummary] = []
    evidence: list[EvidenceParagraph] = []

    # Circuit breaker: if the auto-rebuild worker is currently writing to
    # the SQLite file (harvest, embedding backfill, or metadata backfill),
    # skip HF corpus reads entirely. The single-writer lock would otherwise
    # queue every read behind the rebuild's writes, blowing past timeouts.
    # Curated + IK live retrieval is unaffected — they don't touch
    # hf_judgments or paragraph_embeddings.
    _rebuild_active = False
    try:
        from headnote.api.app import autorebuild_in_progress as _arp
        _rebuild_active = _arp()
    except Exception:
        _rebuild_active = False
    if _rebuild_active:
        use_embeddings = False
        meta.notes.append("HF reads skipped — autorebuild in progress")

    # Lazy embedding index (singleton-ish via param)
    emb_idx = embedding_index
    if use_embeddings and emb_idx is None and _EMBEDDINGS_AVAILABLE:
        try:
            emb_idx = EmbeddingIndex()
        except Exception as e:
            meta.notes.append(f"embedding index unavailable: {e}")
            emb_idx = None

    # 1. Curated pre-filter — minimal in all modes.
    # The 42-case curated corpus is a FALLBACK for when IK is unavailable
    # or returns nothing. When IK is configured, the lawyer wants the
    # 26-lakh judgment universe, not a handful of famous landmarks every
    # tool already surfaces. So we collect at most 3 curated cases here
    # to keep the pool seeded; the rerank step (after IK runs) will drop
    # curated entirely if IK contributed ≥3 cases.
    max_curated = 3

    curated_scored = [(score_curated_case(c, situation), c) for c in curated_corpus]
    curated_scored.sort(key=lambda t: -t[0])
    curated_used: list[str] = []
    curated_case_ids: set[str] = set()
    curated_count = 0
    for score, c in curated_scored:
        if score <= 0:
            break
        cases.append(_curated_to_summary(c, score))
        evidence.extend(_curated_to_evidence(c))
        curated_used.append(c["title"].lower())
        curated_case_ids.add(c["id"])
        curated_count += 1
        if curated_count >= max_curated:
            break
        if len(cases) >= candidate_pool:
            break

    # 2. Semantic search over locally-cached paragraphs (free) + HF corpus.
    # Surfaces IK/HF cases that keyword search would miss.
    #
    # PHILOSOPHY: A lawyer doesn't search by section number. They search by
    # FACT PATTERN ("consensual relationship where marriage was promised"),
    # LEGAL ISSUE ("can court go below mandatory minimum"), and DOCTRINAL
    # PRINCIPLE ("adequate and special reasons for sentence reduction").
    #
    # The embedding query must therefore lead with FACTUAL/ISSUE content,
    # not statute keywords. Statute references in the query DROWN OUT the
    # fact signal in the embedding because they're prominent technical
    # terms that match every case citing that section — including ones
    # with zero factual relevance.
    #
    # New query construction order (most important first):
    #   1. factual_archetype        — the high-level pattern label
    #   2. core_circumstances       — factual chronology bullets
    #   3. legal_concepts           — plain-English doctrinal terms
    #   4. doctrines_at_issue       — formal doctrine names
    #   5. canonical_question       — cleaned question (issue framing)
    #   6. raw situation            — fact-pattern signal the envelope misses
    #   7. stage                    — procedural posture
    #   8. statute (LAST, minimal)  — just for disambiguation, not retrieval
    semantic_query = situation
    if refined_query:
        parts: list[str] = []
        # FACT-FIRST signals
        if refined_query.get("factual_archetype"):
            parts.append(str(refined_query["factual_archetype"]).replace("_", " "))
        for circ in (refined_query.get("core_circumstances") or [])[:5]:
            if circ: parts.append(str(circ))
        # ISSUE / DOCTRINE signals (plain English)
        for lc in (refined_query.get("legal_concepts") or [])[:4]:
            if lc: parts.append(str(lc).replace("_", " "))
        for d in (refined_query.get("doctrines_at_issue") or [])[:3]:
            if d: parts.append(str(d).replace("_", " "))
        # Question framing
        cq = (refined_query.get("canonical_question") or "").strip()
        if cq and cq != situation.strip():
            parts.append(cq)
        # Procedural posture (helps surface cases at the same stage)
        if refined_query.get("stage"):
            parts.append(str(refined_query["stage"]).replace("_", " "))
        # Statute LAST — and we only include one form (not both old + new)
        # to avoid keyword dominance. Embeddings match factual paragraphs,
        # not statute indexes; the statute is for the LLM reranker, not the
        # embedding search.
        if refined_query.get("primary_statute"):
            parts.append(str(refined_query["primary_statute"]))
        composite = " ".join(p for p in parts if p).strip()
        if composite:
            # Raw situation appended LAST — carries the most specific facts
            # the structured envelope couldn't fully capture.
            semantic_query = f"{composite}. {situation}".strip()

    semantic_case_ids: set[str] = set()
    if emb_idx is not None and len(cases) < candidate_pool:
        try:
            # top_k=80 (was 40): wider net to surface fact-pattern matches that
            # may rank lower on lexical overlap but higher on semantic similarity.
            # min_similarity=0.45 (was 0.55): a 0.55 threshold drops fact-pattern
            # matches whenever the lawyer's wording diverges from how a judgment
            # paragraph phrases the same principle. 0.45 lets paraphrased
            # fact patterns through; the LLM reranker downstream still has
            # the final say on what reaches the output.
            sem_hits = emb_idx.search(semantic_query, top_k=80, min_similarity=0.45)
            meta.semantic_hits = len(sem_hits)
            by_case: dict[str, list[EmbeddingHit]] = {}
            for h in sem_hits:
                if h.case_id in curated_case_ids:
                    continue
                by_case.setdefault(h.case_id, []).append(h)

            case_rank = sorted(
                by_case.items(),
                key=lambda kv: -(max(h.similarity for h in kv[1]) + 0.05 * (len(kv[1]) - 1)),
            )
            for case_id, hits_for_case in case_rank:
                if len(cases) >= candidate_pool:
                    break

                # Branch on case_id prefix — semantic index now contains
                # both IK-cached judgments (ik:<tid>) and HF IL-TUR
                # judgments (hf:<subset>:<id>). HF rows don't need IK fetch.
                if case_id.startswith("ik:"):
                    try:
                        tid = int(case_id.split(":", 1)[1])
                        doc = client.get_doc(tid)      # cache hit → ₹0
                        meta.cache_hits += 1
                    except (KanoonError, ValueError) as e:
                        meta.notes.append(f"semantic-cache-hit miss for {case_id}: {e}")
                        continue
                    parsed = parse_judgment(
                        doc.doc_html, tid=tid,
                        title_hint=doc.title, court_hint=doc.docsource,
                        publishdate_hint=doc.publishdate,
                    )
                    top_paras = [
                        p for p in parsed.paragraphs
                        if any(h.para_id == p.id for h in hits_for_case)
                    ][:top_paragraphs_per_case]
                    if not top_paras:
                        top_paras = _rank_paragraphs(parsed.paragraphs, situation, top_paragraphs_per_case)

                    top_sim = max(h.similarity for h in hits_for_case)
                    cases.append(CaseSummary(
                        case_id=case_id,
                        title=parsed.title or doc.title,
                        court=parsed.court or doc.docsource,
                        year=parsed.date_of_decision[:4] if parsed.date_of_decision else "",
                        citation=parsed.primary_citation,
                        bench=", ".join(parsed.bench),
                        source="ik-semantic",
                        numcitedby=doc.numcitedby,
                        relevance_score=round(top_sim * 10, 2),
                        paragraphs=top_paras,
                        statutes=parsed.statutes,
                    ))
                    for p in top_paras:
                        evidence.append(EvidenceParagraph(
                            case_id=case_id, para_id=p.id, para_num=p.num, text=p.text,
                        ))
                    semantic_case_ids.add(case_id)

                elif case_id.startswith("hf:"):
                    # HF semantic hit — pull row from hf_judgments and
                    # reuse the paragraphs already embedded (no further
                    # parsing needed).
                    try:
                        from headnote.retrieval.hf_corpus import get_by_id as _hf_get
                        hj = _hf_get(case_id)
                    except Exception as e:
                        meta.notes.append(f"hf-semantic-hit fetch failed for {case_id}: {e}")
                        continue
                    if not hj:
                        continue

                    # GATE 1 — anonymized? IL-TUR lsi masks entities/acts/
                    # sections; such judgments can't be identified or cited.
                    _hit_text = " ".join((h.text or "") for h in hits_for_case[:3])
                    if _is_anonymized(_hit_text) or _is_anonymized(getattr(hj, "text", "")[:2000]):
                        meta.notes.append(f"skipped {case_id} — anonymized (IL-TUR masking)")
                        continue

                    # GATE 2 — identifiable title? A lawyer must recognise the
                    # case. Body-sentence titles are suppressed.
                    fixed_title = _hf_clean_title(hj, case_id)
                    if not fixed_title:
                        meta.notes.append(f"skipped {case_id} — no identifiable title")
                        continue

                    top_sim = max(h.similarity for h in hits_for_case)
                    # Build Paragraph objects from the embedding hits — the
                    # embedding store already has the text and our para_id
                    # scheme (p_<idx>) from the backfill.
                    para_objs: list = []
                    for h in hits_for_case[:top_paragraphs_per_case]:
                        para_objs.append(Paragraph(
                            id=h.para_id, num=h.para_num or 0,
                            structure=h.structure or "other", text=h.text,
                        ))
                        evidence.append(EvidenceParagraph(
                            case_id=case_id, para_id=h.para_id,
                            para_num=h.para_num or 0, text=h.text,
                        ))

                    # Identify subset from case_id (hf:<subset>:<id>)
                    _parts = case_id.split(":", 2)
                    _subset = _parts[1] if len(_parts) >= 3 else ""
                    _md = getattr(hj, "case_metadata", None) or {}
                    court_label = _hf_court_label(
                        hj.court, getattr(hj, "district", None),
                        case_metadata=_md,
                    )
                    outcome = _hf_label_to_outcome(getattr(hj, "label", None), _subset)
                    # Pull citation from metadata if extractor found one — used
                    # by the LLM prompt + frontend.
                    _ext_citation = (_md.get("citation") or "")
                    _ext_year = ""
                    _ext_date = (_md.get("date") or "")
                    if _ext_date and len(_ext_date) >= 4:
                        _ext_year = _ext_date[:4]
                    _ext_bench = ", ".join(_md.get("judges") or [])[:200]

                    cases.append(CaseSummary(
                        case_id=case_id,
                        title=fixed_title,
                        court=court_label,
                        year=_ext_year,
                        citation=_ext_citation,
                        bench=_ext_bench,
                        source="hf-semantic",
                        numcitedby=0,
                        relevance_score=round(top_sim * 10, 2),
                        paragraphs=para_objs,
                        statutes=(hj.facts or {}).get("statutes", []),
                        outcome=outcome,
                        district=getattr(hj, "district", "") or "",
                    ))
                    semantic_case_ids.add(case_id)
                else:
                    # Unknown case_id prefix; skip.
                    continue
        except Exception as e:
            meta.notes.append(f"semantic search failed: {e}")

    # 2.5. HF corpus search (free, ~50-200ms over 42K Supreme Court +
    # gold-summary judgments). Lives between semantic and live-IK because
    # it's:
    #   - free: no IK API spend
    #   - local: just SQLite
    #   - precise: fact-vector scoring on the imported facts_json column
    # The Hidden Authorities reranker downstream still has the final say;
    # HF results compete with curated + semantic + IK on the same scale.
    hf_case_ids: set[str] = set()
    # Circuit breaker: skip HF keyword search during active autorebuild
    # to avoid SQLite write/read contention. Same flag as semantic block.
    if _rebuild_active:
        pass  # skip HF keyword search entirely
    elif len(cases) < candidate_pool:
        try:
            from headnote.retrieval.hf_corpus import search as _hf_search

            # Build tokens from FACT and ISSUE language, not from raw whitespace
            # split of the situation. A whitespace split treats "section" and
            # "376" as separate tokens — useless for SQL LIKE. Instead we pull
            # high-signal tokens from refined_query's factual and doctrinal
            # facets (which are short noun phrases) and from the situation
            # itself as fallback.
            _hf_stop = {"the", "and", "for", "with", "from", "that", "this",
                        "into", "what", "when", "where", "which", "have", "has",
                        "been", "will", "must", "should", "could", "would",
                        "case", "matter", "client", "your", "their", "they",
                        "court", "section", "under"}
            tokens: list[str] = []
            if refined_query:
                # Pull tokens from factual_archetype, core_circumstances,
                # legal_concepts, doctrines — these are already curated noun
                # phrases that index well via LIKE on facts_json.
                _seeds: list[str] = []
                if refined_query.get("factual_archetype"):
                    _seeds.append(str(refined_query["factual_archetype"]))
                _seeds.extend(refined_query.get("core_circumstances") or [])
                _seeds.extend(refined_query.get("legal_concepts") or [])
                _seeds.extend(refined_query.get("doctrines_at_issue") or [])
                for s in _seeds:
                    for w in str(s).lower().replace("_", " ").split():
                        w = re.sub(r"[^a-z0-9]", "", w)
                        if len(w) > 3 and w not in _hf_stop and w not in tokens:
                            tokens.append(w)
                        if len(tokens) >= 12: break
                    if len(tokens) >= 12: break
            # Fallback: situation-derived tokens (filtered)
            if len(tokens) < 6:
                for w in situation.lower().split():
                    w = re.sub(r"[^a-z0-9]", "", w)
                    if len(w) > 3 and w not in _hf_stop and w not in tokens:
                        tokens.append(w)
                    if len(tokens) >= 12: break
            if tokens:
                hf_hits = _hf_search(
                    tokens,
                    situation=situation,
                    language="en",
                    limit=15,           # 8 → 15: HF carries the load now; let it fill the pool
                )
                meta.notes.append(f"hf_corpus surfaced {len(hf_hits)} cases")
                for j in hf_hits:
                    if j.doc_id in curated_case_ids or j.doc_id in semantic_case_ids:
                        continue
                    if len(cases) >= candidate_pool:
                        break

                    # GATE 1 — anonymized judgment (IL-TUR lsi masking)? Skip.
                    if _is_anonymized((j.text or "")[:2000]):
                        meta.notes.append(f"skipped {j.doc_id} — anonymized (IL-TUR masking)")
                        continue
                    # GATE 2 — identifiable title? Suppress body-sentence titles.
                    fixed_title = _hf_clean_title(j, j.doc_id)
                    if not fixed_title:
                        meta.notes.append(f"skipped {j.doc_id} — no identifiable title")
                        continue

                    # Synthesise paragraph objects from the raw judgment
                    # text. HF rows are flat plaintext (no IK paragraph
                    # ids), so we split on blank lines, filter very short
                    # / junk lines, and assign p_<idx> ids. The downstream
                    # verifier only needs (case_id, para_id, text) so this
                    # is enough.
                    para_objs: list = []
                    para_strs = [
                        p.strip()
                        for p in (j.text or "").split("\n\n")
                        if 60 <= len(p.strip()) <= 4000
                    ]
                    # Score paragraphs by keyword overlap with the
                    # situation; take top top_paragraphs_per_case.
                    needles = [t for t in tokens if len(t) > 3]
                    def _para_score(s: str) -> int:
                        sl = s.lower()
                        return sum(1 for t in needles if t in sl)
                    scored_paras = sorted(
                        enumerate(para_strs),
                        key=lambda kv: -_para_score(kv[1]),
                    )[:top_paragraphs_per_case]
                    # If no needle hits, just take the first paragraphs —
                    # better than empty evidence which would auto-drop
                    # this case at the verification stage.
                    if not scored_paras and para_strs:
                        scored_paras = list(enumerate(para_strs[:top_paragraphs_per_case]))

                    for idx, text in scored_paras:
                        para_id = f"hfp_{idx}"
                        para_objs.append(Paragraph(
                            id=para_id, num=idx + 1,
                            structure="other", text=text,
                        ))
                        evidence.append(EvidenceParagraph(
                            case_id=j.doc_id, para_id=para_id,
                            para_num=idx + 1, text=text,
                        ))

                    # Court level → readable label (now includes district for BAIL,
                    # AND prefers extracted metadata when available)
                    _md = getattr(j, "case_metadata", None) or {}
                    court_label = _hf_court_label(
                        j.court, getattr(j, "district", None),
                        case_metadata=_md,
                    )
                    # Subset from doc_id: "hf:<subset>:<id>"
                    _parts = j.doc_id.split(":", 2)
                    _subset = _parts[1] if len(_parts) >= 3 else ""
                    # fixed_title already set by GATE 2 above
                    outcome = _hf_label_to_outcome(getattr(j, "label", None), _subset)
                    _ext_citation = (_md.get("citation") or "")
                    _ext_date = (_md.get("date") or "")
                    _ext_year = _ext_date[:4] if _ext_date and len(_ext_date) >= 4 else ""
                    _ext_bench = ", ".join(_md.get("judges") or [])[:200]

                    cases.append(CaseSummary(
                        case_id=j.doc_id,
                        title=fixed_title,
                        court=court_label,
                        year=_ext_year,
                        citation=_ext_citation,
                        bench=_ext_bench,
                        source="hf",
                        numcitedby=0,                  # HF doesn't expose this
                        relevance_score=round(j.fact_score, 2),
                        paragraphs=para_objs,
                        statutes=(j.facts or {}).get("statutes", []),
                        outcome=outcome,
                        district=getattr(j, "district", "") or "",
                    ))
                    hf_case_ids.add(j.doc_id)
        except Exception as e:
            meta.notes.append(f"hf_corpus search failed: {e}")

    # 3. IK live search (paid) — conditional on the free local pool size.
    #
    # The free local pool is: curated (42 vetted) + semantic (cached IK
    # paragraphs) + HF corpus (42K Supreme Court + gold-summary judgments).
    # If they collectively returned >= SKIP_IK_IF_CASES cases, the user
    # already has a strong, diverse pool — IK live adds latency (8-15s
    # of doc fetches) without proportional quality gain.
    #
    # `hidden` and `famous` modes still ALWAYS run IK so the reranker
    # has fresh non-curated candidates to surface.
    non_curated_count = sum(1 for c in cases if c.source != "curated")
    if mode in ("hidden", "famous"):
        run_ik_search = True
    elif non_curated_count >= skip_ik_search_if_cases_at_least:
        run_ik_search = False
        meta.notes.append(
            f"skipped IK live search — free pool already has "
            f"{non_curated_count} non-curated cases (>= {skip_ik_search_if_cases_at_least})"
        )
    else:
        run_ik_search = True

    if run_ik_search:
        form_input = _build_search_input(situation, extra_filters=search_filters, refined_query=refined_query)
        all_hits: list[SearchHit] = []

        # Single IK search page per query to stay inside Render's request
        # budget. A second page was being fetched in hidden mode to surface
        # lower-cited results, but the extra ₹0.50 + ~1.5s round-trip wasn't
        # worth pushing past the 25s timeout. The fame penalty in the
        # reranker already pulls obscure cases up from page 0 results.
        pages_to_fetch = 1
        for page_n in range(pages_to_fetch):
            try:
                page = client.search(form_input, pagenum=page_n)
                meta.ik_search_calls += 1
                all_hits.extend(page.hits)
            except KanoonBudgetExceeded as e:
                if page_n == 0:
                    meta.notes.append(f"IK budget exceeded; using curated+semantic only: {e}")
                    return _finalise(cases, evidence, meta, t0, client, spend_before)
                else:
                    meta.notes.append(f"IK page {page_n} budget exceeded; using page 0 results only")
                    break
            except KanoonError as e:
                if page_n == 0:
                    meta.notes.append(
                        f"IK search failed ({type(e).__name__}); using curated+semantic only: {e}"
                    )
                    return _finalise(cases, evidence, meta, t0, client, spend_before)
                else:
                    meta.notes.append(f"IK search page {page_n} failed: {e}")
                    break

        ranked = _rank_search_hits(
            all_hits, situation,
            curated_titles_lc=set(curated_used),
            mode=mode,
        )
        ranked = [(s, h) for s, h in ranked if f"ik:{h.tid}" not in semantic_case_ids]

        # hidden/famous: allow more new fetches to build a wider candidate pool.
        effective_max_fetches = (
            DEFAULT_MAX_NEW_FETCHES_HIDDEN if mode in ("hidden", "famous") else max_new_fetches
        )

        # PARALLEL IK doc fetches. Each fetch is an HTTP round-trip to
        # indiankanoon.org (~1-3s); doing them sequentially is the single
        # biggest source of latency on cold-cache queries. Bounded
        # ThreadPoolExecutor caps concurrent connections so we don't
        # hammer IK or exhaust connection pools.
        to_attempt = ranked[:effective_max_fetches]

        def _fetch_one(item):
            score, hit = item
            try:
                was_cached = _doc_was_cached(client, hit.tid)
                doc = client.get_doc(hit.tid)
                return (score, hit, doc, was_cached, None)
            except KanoonBudgetExceeded as e:
                return (score, hit, None, False, ("budget", e))
            except KanoonNotFound:
                return (score, hit, None, False, ("notfound", None))
            except KanoonError as e:
                return (score, hit, None, False, ("error", e))
            except Exception as e:
                return (score, hit, None, False, ("error", e))

        from concurrent.futures import ThreadPoolExecutor

        fetch_results: list = []
        if to_attempt:
            workers = max(1, min(DEFAULT_IK_FETCH_PARALLELISM, len(to_attempt)))
            with ThreadPoolExecutor(max_workers=workers) as pool:
                # Submit all and collect in original order so the reranker
                # sees a stable sequence (parallelism doesn't change the
                # eventual order — just compresses wall-clock time).
                futures = [pool.submit(_fetch_one, item) for item in to_attempt]
                for fut in futures:
                    try:
                        fetch_results.append(fut.result(timeout=25))
                    except Exception as e:
                        meta.notes.append(f"IK parallel fetch error: {e}")

        # Sequential post-processing (parse + embed + add to cases). The
        # parsing is CPU-bound but cheap (~10-50ms each); no need to
        # parallelise that too.
        budget_exhausted = False
        for score, hit, doc, was_cached, err in fetch_results:
            if budget_exhausted:
                break
            if len(cases) >= candidate_pool:
                break
            if err is not None:
                kind, exc = err
                if kind == "budget":
                    meta.notes.append(f"IK budget exhausted mid-fetch: {exc}")
                    budget_exhausted = True
                    break
                if kind == "notfound":
                    continue
                meta.notes.append(f"IK fetch failed for tid={hit.tid}: {exc}")
                continue
            if was_cached:
                meta.cache_hits += 1
            else:
                meta.ik_fetch_calls += 1

            parsed = parse_judgment(
                doc.doc_html, tid=hit.tid,
                title_hint=doc.title, court_hint=doc.docsource,
                publishdate_hint=doc.publishdate,
            )
            top_paras = _rank_paragraphs(parsed.paragraphs, situation, top_paragraphs_per_case)
            case_id = f"ik:{hit.tid}"

            # Auto-embed all paragraphs so future semantic searches benefit.
            if emb_idx is not None and parsed.paragraphs and not was_cached:
                try:
                    emb_idx.upsert_paragraphs([
                        (case_id, p.id, p.num, p.structure, p.text)
                        for p in parsed.paragraphs
                        if len(p.text) >= 40
                    ])
                except Exception as e:
                    meta.notes.append(f"auto-embed failed for tid={hit.tid}: {e}")

            cases.append(CaseSummary(
                case_id=case_id,
                title=parsed.title or hit.title,
                court=parsed.court or hit.docsource,
                year=parsed.date_of_decision[:4] if parsed.date_of_decision else "",
                citation=parsed.primary_citation,
                bench=", ".join(parsed.bench),
                source="ik",
                numcitedby=hit.numcitedby,
                relevance_score=score,
                paragraphs=top_paras,
                statutes=parsed.statutes,
            ))
            for p in top_paras:
                evidence.append(EvidenceParagraph(
                    case_id=case_id, para_id=p.id, para_num=p.num, text=p.text,
                ))

    # 4. Hidden-authorities reranking: score the full candidate pool by mode,
    # then trim to top_cases. This is the step that lets obscure-but-relevant
    # cases beat famous-but-less-relevant ones in hidden mode.
    if len(cases) > top_cases or mode != "mixed":
        pool_size = len(cases)
        try:
            from headnote.retrieval.hidden_authorities import rank_candidates, Candidate

            # HIDDEN MODE — hard-filter curated when we have enough IK cases.
            # ALL MODES — curated is a last-resort fallback. When IK has
            # contributed ≥3 candidates, drop curated entirely. The 42
            # curated cases are famous landmarks (Bhajan Lal, Lalita
            # Kumari, Arnesh Kumar, Bhaskaran...) — every junior already
            # knows them. The product promise is the 26-lakh IK universe;
            # curated only surfaces when IK is unavailable / empty.
            ik_only = [c for c in cases if c.source != "curated"]
            if len(ik_only) >= 3:
                dropped_count = len(cases) - len(ik_only)
                cases = ik_only
                meta.notes.append(
                    f"dropped {dropped_count} curated landmarks, ranking over "
                    f"{len(cases)} IK candidates only (mode={mode})"
                )

            # PER-SOURCE relevance normalisation. The old global-max approach
            # divided IK relevance scores (mixed scale, can be small or
            # negative pre-fix) by the same denominator as curated keyword
            # scores (0-15) — IK always got rel ≈ 0.1, curated got rel ≈ 1.0,
            # curated won every time. Now each source is normalised against
            # its own peer max so cross-source comparison stays fair.
            rel_by_src: dict[str, float] = {}
            for c in cases:
                rel_by_src[c.source] = max(rel_by_src.get(c.source, 0.0), float(c.relevance_score))
            rel_by_src = {k: (v or 1.0) for k, v in rel_by_src.items()}

            def _summary(cs: CaseSummary) -> str:
                if cs.paragraphs:
                    return " ".join(p.text for p in cs.paragraphs[:2])[:600]
                return cs.title

            candidates = [
                Candidate(
                    case_id=cs.case_id,
                    title=cs.title,
                    court=cs.court,
                    year=int(str(cs.year)[:4]) if str(cs.year)[:4].isdigit() else 0,
                    citation=cs.citation,
                    numcitedby=cs.numcitedby,
                    semantic_similarity=max(
                        0.0,
                        min(1.0, cs.relevance_score / (rel_by_src.get(cs.source) or 1.0)),
                    ),
                    summary=_summary(cs),
                    source=cs.source,
                )
                for cs in cases
            ]

            # Time-budget gate: if retrieval has already consumed most of the
            # allotted time, skip the Sonnet/DeepSeek reranker LLM call
            # (5-30s) to leave room for the downstream main LLM call. The
            # reranker improves quality but the response getting to the user
            # at all is more important than perfect ranking.
            _retrieval_elapsed = time.time() - t0
            _skip_rerank_time = _retrieval_elapsed > (time_budget_seconds * 0.7)
            if _skip_rerank_time:
                print(
                    f"[retrieval] time budget gate: {_retrieval_elapsed:.1f}s elapsed "
                    f"vs {time_budget_seconds:.0f}s budget — skipping Sonnet reranker"
                )
                meta.notes.append(
                    f"Sonnet reranker skipped (time budget: {_retrieval_elapsed:.1f}s "
                    f"of {time_budget_seconds:.0f}s used)"
                )

            # The Sonnet fact-pattern reranker is the single biggest case-
            # relevance lever. When enabled, Sonnet judges how well each
            # candidate's facts actually align with the lawyer's situation
            # (~₹4 extra per query). When disabled, the reranker falls back
            # to semantic_similarity as a proxy, which is faster + free but
            # produces "topically related" rather than "factually aligned"
            # results. Operator picks via the ENABLE_SONNET_RERANKER env var.
            from headnote import config as _hncfg
            _force_skip_rerank = _skip_rerank_time or not _hncfg.ENABLE_SONNET_RERANKER
            scored = rank_candidates(
                situation,
                candidates,
                mode,
                query_jurisdiction=jurisdiction,
                result_top_k=top_cases,
                skip_sonnet_rerank=_force_skip_rerank,
            )

            # Map scored results back to CaseSummary (preserving paragraph data).
            case_by_id = {cs.case_id: cs for cs in cases}
            cases = [case_by_id[sc.candidate.case_id]
                     for sc in scored if sc.candidate.case_id in case_by_id]

            # Trim evidence to match selected cases.
            selected_ids = {c.case_id for c in cases}
            evidence = [e for e in evidence if e.case_id in selected_ids]
            meta.notes.append(
                f"hidden_authorities reranker applied (mode={mode}, pool={pool_size}→top={len(cases)})"
            )
        except Exception as e:
            # Reranker failure is non-fatal — use collection order with a hard trim.
            meta.notes.append(f"hidden_authorities reranker failed ({e}); using collection order")
            cases = cases[:top_cases]
            selected_ids = {c.case_id for c in cases}
            evidence = [e for e in evidence if e.case_id in selected_ids]

    return _finalise(cases, evidence, meta, t0, client, spend_before)


# ----- helpers around cache-hit detection (so we can accurately attribute cost)

def _was_cached(client: KanoonClient, page) -> bool:
    """SearchPage doesn't carry a cached flag. Approximate via spend delta in
    the post-call check by _finalise; here just return False to be conservative.
    Cache-vs-live for search is reflected in spend totals."""
    return False


def _doc_was_cached(client: KanoonClient, tid: int) -> bool:
    return client._get_cached_doc(tid) is not None  # noqa: SLF001 (internal access OK)


def _finalise(
    cases: list[CaseSummary],
    evidence: list[EvidenceParagraph],
    meta: RetrievalMeta,
    t0: float,
    client: KanoonClient,
    spend_before: dict,
) -> RetrievalResult:
    meta.elapsed_seconds = round(time.time() - t0, 3)
    spend_after = client.spend_summary()
    meta.inr_spent_this_call = round(
        float(spend_after["today_total_inr"]) - float(spend_before["today_total_inr"]),
        4,
    )
    return RetrievalResult(cases=cases, evidence=evidence, meta=meta)


# ====================================================================
# Adapter: convert RetrievalResult into the JSON-corpus format the
# existing situation prompt expects. Curated cases pass through unchanged;
# IK cases are synthesised from paragraph evidence.
# ====================================================================

def result_to_prompt_corpus_json(
    result: RetrievalResult, curated_lookup: dict[str, dict]
) -> str:
    """Build the JSON-corpus string the situation prompt is currently caching.

    Curated entries are passed through verbatim (they have hand-written
    `holding`, `bns_mapping`, `topics`, `key_paras`). IK entries get a
    synthesised entry plus an `_ik_paragraphs` array so the LLM can quote
    from raw paragraphs and produce correct `paragraph_anchor`s.
    """
    entries: list[dict] = []
    for cs in result.cases:
        if cs.source == "curated":
            entry = dict(curated_lookup.get(cs.case_id) or {})
            entry.setdefault("_source", "curated")
            entries.append(entry)
            continue

        # IK case — synthesise corpus-shaped entry from parsed paragraphs.
        facts_paras = [p for p in cs.paragraphs if p.structure == "facts"]
        issue_paras = [p for p in cs.paragraphs if p.structure == "issue"]
        conc_paras = [p for p in cs.paragraphs if p.structure in ("conclusion", "ratio")]

        facts_text = " ".join(p.text for p in facts_paras).strip() or "(see _ik_paragraphs)"
        holding_text = " ".join(p.text for p in conc_paras).strip() or "(see _ik_paragraphs for the ratio)"
        issues_list = [p.text for p in issue_paras] or ["(see _ik_paragraphs)"]
        key_paras_text = ", ".join(
            f"Para {p.num}" if p.num is not None else p.id
            for p in conc_paras
        ) or "(none structurally tagged)"

        entries.append({
            "id": cs.case_id,
            "title": cs.title,
            "citation": cs.citation,
            "court": cs.court,
            "year": cs.year,
            "bench": cs.bench,
            "statutes": cs.statutes,
            "bns_mapping": [],   # not curated for IK / HF entries
            "topics": [],
            "facts": facts_text,
            "issues": issues_list,
            "holding": holding_text,
            "key_paras": key_paras_text,
            "subsequent_treatment": "",
            # NEW: verified outcome + district from BAIL/CJPE labels.
            # Critical — without these the LLM hallucinates outcomes
            # (e.g. "bail-granted" when source label said REJECTED).
            "outcome": getattr(cs, "outcome", "") or "",
            "district": getattr(cs, "district", "") or "",
            # Preserve the actual source ('ik' / 'ik-semantic' / 'hf') so
            # the UI can label the badge correctly. HF entries carry the
            # 'hf' source so the front-end can show 'IL-TUR' instead of
            # 'Indian Kanoon'.
            "_source": cs.source or "ik",
            "_numcitedby": cs.numcitedby,
            # Cap each paragraph at ~700 chars so a heavy judgment doesn't
            # blow the prompt budget — Opus latency scales with input size
            # and Render's request timeout is the binding constraint here.
            "_ik_paragraphs": [
                {
                    "id": p.id,
                    "num": p.num,
                    "structure": p.structure,
                    "text": p.text[:700] + ("…" if len(p.text) > 700 else ""),
                }
                for p in cs.paragraphs
            ],
        })
    return json.dumps(entries, ensure_ascii=False)


# Extra prompt instructions for the IK-mixed path. Appended to the existing
# situation system prompt so the LLM knows how to handle IK entries.
IK_PROMPT_ADDENDUM = """

ADDITIONAL RULES FOR MIXED CURATED + INDIAN KANOON CORPUS:

Each case in the corpus has a `_source` field:
  - `_source: "curated"`: editorially vetted entry. Use `holding`, `key_paras`,
    and `bns_mapping` as given.
  - `_source: "ik"`: fetched from Indian Kanoon. The `holding`, `facts`,
    `issues` fields are auto-synthesised from raw judgment paragraphs.
    The authoritative source is the `_ik_paragraphs` array — each paragraph
    has an `id` (like "p_24"), a human paragraph `num` (may be null for
    older judgments), a `structure` tag (facts/issue/conclusion/...), and
    the verbatim `text` from the judgment.

For IK-sourced cases:
  - Treat `_ik_paragraphs` as your evidence. NEVER quote anything that
    does not appear verbatim in one of these paragraphs.
  - `paragraph_anchor`: use the para `num` (e.g. "(Para 24)") if non-null;
    otherwise use the para `id` (e.g. "(p_24)").
  - `ratio`: derive from paragraphs with `structure: "conclusion"` (or
    `"court_discussion"` if no conclusion is tagged). Compress to 1-3
    sentences; do not invent.
  - For IK entries you cannot speak to `bns_mapping` confidently — leave
    `bns_note` empty or write "BNS mapping pending editorial review" rather
    than guessing.

Quote rule applies across both sources: every `quotable_phrase` must appear
verbatim (modulo whitespace) in the curated entry's `holding`/`facts`/`key_paras`
OR in the IK entry's `_ik_paragraphs`.
"""
