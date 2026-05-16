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
from typing import Iterable

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
DEFAULT_TOP_CASES = 6
DEFAULT_TOP_PARAGRAPHS_PER_CASE = 4
DEFAULT_MAX_NEW_FETCHES = 5     # never fetch more than this many NEW docs per query

# Cost-saving: don't burn ₹0.50 on an IK search if curated+semantic already
# filled at least this many slots. Tunable per call.
DEFAULT_SKIP_IK_SEARCH_IF_CASES_AT_LEAST = 3

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
    source: str = "ik"          # "curated" | "ik"
    numcitedby: int = 0
    relevance_score: float = 0.0
    paragraphs: list[Paragraph] = field(default_factory=list)
    statutes: list[str] = field(default_factory=list)


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

# Stopwords that add noise to IK search if passed verbatim
_QUERY_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "in", "on", "at", "to", "of",
    "for", "with", "by", "from", "as", "is", "are", "was", "were", "be",
    "been", "being", "this", "that", "these", "those", "what", "which",
    "who", "whether", "case", "court", "judgment", "law", "client",
    "lawyer", "wants", "needs", "looking", "find", "precedents", "ruling",
    "rulings", "matter", "situation", "facts", "question", "my", "his",
    "her", "their",
}

# Proper-noun detector: capitalised tokens with at least 2 chars, not at
# sentence start only (to capture "Vijay Madanlal Choudhary" but not "My").
_PROPER_NOUN_RX = re.compile(r"\b([A-Z][a-zA-Z]{2,})(?:\s+([A-Z][a-zA-Z]{2,}))+\b")


def _distill_query(situation: str, *, max_tokens: int = 10) -> str:
    """Turn a lawyer's natural-language situation into an IK-friendly search.

    IK's search is closer to Boolean keyword retrieval than semantic search.
    Sending 30+ words of prose typically returns zero hits because every term
    is treated as a constraint. We extract the signal-bearing tokens:

      1. Statute names (PMLA, NI Act, ...)
      2. Section/article refs (S. 138, Art. 21)
      3. Multi-word proper nouns (case names like "Vijay Madanlal Choudhary")
      4. A few residual content words (filtered through stopwords)

    Returns a space-joined token string of length <= max_tokens.
    """
    tokens: list[str] = []
    seen: set[str] = set()

    def add(tok: str) -> None:
        t = tok.strip()
        if not t:
            return
        key = t.lower()
        if key in seen:
            return
        seen.add(key)
        tokens.append(t)

    # 1. Statute names (lowercased canonical)
    for m in _STATUTE_HINT_RX.finditer(situation):
        add(m.group(0).strip())

    # 2. Section + article refs
    for m in _SECTION_HINT_RX.finditer(situation):
        add(f"Section {m.group(1)}")
    for m in _ARTICLE_HINT_RX.finditer(situation):
        add(f"Article {m.group(1)}")

    # 3. Multi-word proper nouns (likely case party names)
    for m in _PROPER_NOUN_RX.finditer(situation):
        # Reconstruct the full match (m.group(0) covers the whole proper-noun span)
        add(m.group(0).strip())

    # 4. Fill remaining budget with content words (alpha tokens, not stop)
    if len(tokens) < max_tokens:
        for w in re.findall(r"[A-Za-z][A-Za-z\-]+", situation):
            if len(tokens) >= max_tokens:
                break
            wl = w.lower()
            if len(w) < 4 or wl in _QUERY_STOPWORDS or wl in seen:
                continue
            # skip if already covered by a token we added
            if any(wl in tk.lower() for tk in tokens):
                continue
            add(w)

    return " ".join(tokens[:max_tokens])


def _build_search_input(situation: str, extra_filters: str = "") -> str:
    """Compose the IK search formInput from the lawyer's situation.

    Calls _distill_query to extract signal-bearing tokens, then appends the
    doctype filter. The raw situation is NEVER sent verbatim — IK's keyword
    search returns zero hits for long natural-language queries.
    """
    distilled = _distill_query(situation)
    if not distilled:
        # Last-resort fallback: take the first 8 alpha words >3 chars
        words = [w for w in re.findall(r"[A-Za-z]{4,}", situation) if w.lower() not in _QUERY_STOPWORDS][:8]
        distilled = " ".join(words)

    filters = extra_filters or DEFAULT_SEARCH_FILTERS
    return f"{distilled} {filters}".strip() if filters else distilled


# ----------------------------------------------------------- hit ranking

def _rank_search_hits(
    hits: list[SearchHit], query: str, *, curated_titles_lc: set[str]
) -> list[tuple[float, SearchHit]]:
    """Return hits sorted by composite relevance score (highest first).

    Components:
      - Citation weight (log-scaled numcitedby): a 3,000-citation case is
        much more likely the precedent the lawyer wants than a 0-citation
        recent decision.
      - Keyword overlap on the headline snippet (free; IK already highlighted
        the matches).
      - Recency neutral by default — we let citation weight dominate, since
        legal research usually wants authority, not freshness. If you want a
        recency tilt later, add it here.

    Drops hits whose title (lowercased) is already in the curated corpus —
    no point spending ₹0.20 to fetch what we already have.
    """
    import math

    query_tokens = set(_tokens(query))
    scored: list[tuple[float, SearchHit]] = []
    for h in hits:
        title_lc = h.title.lower()
        if any(ct in title_lc or title_lc in ct for ct in curated_titles_lc):
            # Curated copy already exists — don't pay to refetch
            continue

        citation_score = math.log1p(h.numcitedby) * 1.5     # log-scaled authority
        headline_score = len(query_tokens & set(_tokens(h.headline))) * 0.5
        # Small bonus if IK classifies the doc as SC (most authoritative)
        court_bonus = 2.0 if "supreme court" in h.docsource.lower() else 0.0
        score = citation_score + headline_score + court_bonus
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
    top_paragraphs_per_case: int = DEFAULT_TOP_PARAGRAPHS_PER_CASE,
    max_new_fetches: int = DEFAULT_MAX_NEW_FETCHES,
    search_filters: str = DEFAULT_SEARCH_FILTERS,
    use_embeddings: bool = True,
    embedding_index: "EmbeddingIndex | None" = None,
    skip_ik_search_if_cases_at_least: int = DEFAULT_SKIP_IK_SEARCH_IF_CASES_AT_LEAST,
) -> RetrievalResult:
    """End-to-end retrieval for a lawyer's situation query.

    Pipeline (cheapest first; bails early when slots are filled):
      1. Curated pre-filter (free, instant)
      2. Semantic search over locally-cached paragraphs (free, ~20ms)
         - Surfaces relevant cached IK cases not in curated
         - Critical for paraphrased queries where keywords don't overlap
      3. IK live search (₹0.50) + top-N fetch (₹0.20 each, capped)
         - Only entered if slots remain after steps 1+2
      4. Newly-fetched paragraphs are embedded for future calls
         (the cache + embedding index self-grow with usage)

    Never raises on IK errors — falls back to whatever we have so far and
    records the failure in meta.notes. Lawyer always sees *something*.
    """
    t0 = time.time()
    spend_before = client.spend_summary()

    meta = RetrievalMeta(elapsed_seconds=0.0)
    cases: list[CaseSummary] = []
    evidence: list[EvidenceParagraph] = []

    # Lazy embedding index (singleton-ish via param)
    emb_idx = embedding_index
    if use_embeddings and emb_idx is None and _EMBEDDINGS_AVAILABLE:
        try:
            emb_idx = EmbeddingIndex()
        except Exception as e:
            meta.notes.append(f"embedding index unavailable: {e}")
            emb_idx = None

    # 1. Curated pre-filter (always; free)
    curated_scored = [(score_curated_case(c, situation), c) for c in curated_corpus]
    curated_scored.sort(key=lambda t: -t[0])
    curated_used: list[str] = []
    curated_case_ids: set[str] = set()
    for score, c in curated_scored:
        if score <= 0:
            break
        cases.append(_curated_to_summary(c, score))
        evidence.extend(_curated_to_evidence(c))
        curated_used.append(c["title"].lower())
        curated_case_ids.add(c["id"])
        if len(cases) >= top_cases:
            break

    # 2. Semantic search over locally-cached paragraphs (free)
    # Surfaces relevant IK cases already in cache that keyword search would miss.
    semantic_case_ids: set[str] = set()
    if emb_idx is not None and len(cases) < top_cases:
        try:
            # Pull more hits than slots so we can aggregate by case
            sem_hits = emb_idx.search(situation, top_k=40, min_similarity=0.55)
            meta.semantic_hits = len(sem_hits)
            # Group hits by case_id; keep top per case
            by_case: dict[str, list[EmbeddingHit]] = {}
            for h in sem_hits:
                if h.case_id in curated_case_ids:
                    continue  # already covered by curated path
                by_case.setdefault(h.case_id, []).append(h)

            # Rank cases by max sim (top hit) + a small boost for multiple hits
            case_rank = sorted(
                by_case.items(),
                key=lambda kv: -(max(h.similarity for h in kv[1]) + 0.05 * (len(kv[1]) - 1)),
            )
            for case_id, hits_for_case in case_rank:
                if len(cases) >= top_cases:
                    break
                if not case_id.startswith("ik:"):
                    continue
                tid = int(case_id.split(":", 1)[1])
                # We already have this in IK doc cache (semantic hits only come
                # from cached docs); fetch metadata cheaply via the cached doc.
                try:
                    doc = client.get_doc(tid)              # cache hit → ₹0
                    meta.cache_hits += 1
                except KanoonError as e:
                    meta.notes.append(f"semantic-cache-hit miss for tid={tid}: {e}")
                    continue
                parsed = parse_judgment(
                    doc.doc_html, tid=tid,
                    title_hint=doc.title, court_hint=doc.docsource,
                    publishdate_hint=doc.publishdate,
                )
                # Use the semantic hits as the evidence — they're already
                # the most relevant paragraphs by definition. Map to Paragraph
                # objects so the downstream code is identical.
                top_paras = [
                    p for p in parsed.paragraphs
                    if any(h.para_id == p.id for h in hits_for_case)
                ][:top_paragraphs_per_case]
                # Fallback: if mapping failed (shouldn't), use structural ranking
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
                    source="ik-semantic",   # distinguishable in UI from fresh-fetched ik
                    numcitedby=doc.numcitedby,
                    relevance_score=round(top_sim * 10, 2),  # scale for display
                    paragraphs=top_paras,
                    statutes=parsed.statutes,
                ))
                for p in top_paras:
                    evidence.append(EvidenceParagraph(
                        case_id=case_id, para_id=p.id, para_num=p.num, text=p.text,
                    ))
                semantic_case_ids.add(case_id)
        except Exception as e:
            meta.notes.append(f"semantic search failed: {e}")

    # 3. IK live search (paid) — only if we still need more cases AND we
    # don't already have enough from curated + semantic. Saves ₹0.50 per
    # query once the cache is sufficiently warm.
    remaining_slots = max(0, top_cases - len(cases))
    if remaining_slots > 0 and len(cases) >= skip_ik_search_if_cases_at_least:
        meta.notes.append(
            f"Skipped IK search (saved ₹0.50): {len(cases)} cases already from "
            f"curated+semantic, above min threshold of {skip_ik_search_if_cases_at_least}"
        )
    elif remaining_slots > 0:
        form_input = _build_search_input(situation, extra_filters=search_filters)
        try:
            page = client.search(form_input)
            meta.ik_search_calls += 1  # actual spend tracked by ledger; this is informational
        except KanoonBudgetExceeded as e:
            meta.notes.append(f"IK budget exceeded; using curated+semantic only: {e}")
            return _finalise(cases, evidence, meta, t0, client, spend_before)
        except KanoonError as e:
            meta.notes.append(f"IK search failed ({type(e).__name__}); using curated+semantic only: {e}")
            return _finalise(cases, evidence, meta, t0, client, spend_before)

        ranked = _rank_search_hits(
            page.hits, situation,
            curated_titles_lc=set(curated_used),
        )
        # Also drop hits we already added via semantic path
        ranked = [(s, h) for s, h in ranked if f"ik:{h.tid}" not in semantic_case_ids]

        fetched_new = 0
        for score, hit in ranked:
            if len(cases) >= top_cases:
                break
            if fetched_new >= max_new_fetches:
                meta.notes.append(
                    f"hit max_new_fetches={max_new_fetches}; stopping. Cache will warm over time."
                )
                break
            try:
                was_cached = _doc_was_cached(client, hit.tid)
                doc = client.get_doc(hit.tid)
                if was_cached:
                    meta.cache_hits += 1
                else:
                    meta.ik_fetch_calls += 1
                    fetched_new += 1
            except KanoonBudgetExceeded as e:
                meta.notes.append(f"IK budget exhausted mid-fetch: {e}")
                break
            except KanoonNotFound:
                continue
            except KanoonError as e:
                meta.notes.append(f"IK fetch failed for tid={hit.tid}: {e}")
                continue

            parsed = parse_judgment(
                doc.doc_html, tid=hit.tid,
                title_hint=doc.title, court_hint=doc.docsource,
                publishdate_hint=doc.publishdate,
            )
            top_paras = _rank_paragraphs(parsed.paragraphs, situation, top_paragraphs_per_case)
            case_id = f"ik:{hit.tid}"

            # Auto-embed all paragraphs (not just top_paras) so future
            # semantic searches benefit. Free, runs in ~1-3s for a typical doc.
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
            "bns_mapping": [],   # not curated for IK entries
            "topics": [],
            "facts": facts_text,
            "issues": issues_list,
            "holding": holding_text,
            "key_paras": key_paras_text,
            "subsequent_treatment": "",
            "_source": "ik",
            "_numcitedby": cs.numcitedby,
            "_ik_paragraphs": [
                {
                    "id": p.id,
                    "num": p.num,
                    "structure": p.structure,
                    "text": p.text,
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
