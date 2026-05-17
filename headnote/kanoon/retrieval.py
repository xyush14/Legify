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
DEFAULT_TOP_CASES = 3           # 5→3: smaller output volume keeps Sonnet under 25s budget
DEFAULT_CANDIDATE_POOL = 25     # candidates to collect before hidden_authorities reranking
DEFAULT_TOP_PARAGRAPHS_PER_CASE = 2   # 4→2: shorter Phase 2 prompts, faster generation
DEFAULT_MAX_NEW_FETCHES = 5         # mixed mode: max new IK doc fetches (₹0.20 each)
# Render free-tier kills requests around 25s. Cold-cache IK doc fetches take
# ~1-1.5s each — 10 fetches alone burn the entire request budget. Cap hidden
# mode at 4 cold fetches so Phase 1 + Phase 2 actually get to run.
DEFAULT_MAX_NEW_FETCHES_HIDDEN = 4

# Cost-saving for mixed mode: don't burn ₹0.50 on an IK search if curated+semantic
# already filled at least this many slots. Ignored for hidden/famous modes.
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

    Never raises on IK errors — falls back to whatever we have so far.
    """
    t0 = time.time()
    spend_before = client.spend_summary()

    # candidate_pool must be at least top_cases
    candidate_pool = max(candidate_pool, top_cases)

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
    # IMPORTANT: For hidden/famous modes, cap curated count so IK cases get
    # room in the candidate pool. Without this cap, the 42 curated cases
    # (all famous landmarks) fill all 25 slots, IK never contributes, and
    # the Hidden Authorities reranker has nothing obscure to surface.
    if mode in ("hidden", "famous"):
        max_curated = 5
    else:
        max_curated = candidate_pool

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

    # 2. Semantic search over locally-cached paragraphs (free)
    # Surfaces IK cases already in cache that keyword search would miss.
    semantic_case_ids: set[str] = set()
    if emb_idx is not None and len(cases) < candidate_pool:
        try:
            sem_hits = emb_idx.search(situation, top_k=40, min_similarity=0.55)
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
                if not case_id.startswith("ik:"):
                    continue
                tid = int(case_id.split(":", 1)[1])
                try:
                    doc = client.get_doc(tid)          # cache hit → ₹0
                    meta.cache_hits += 1
                except KanoonError as e:
                    meta.notes.append(f"semantic-cache-hit miss for tid={tid}: {e}")
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
        except Exception as e:
            meta.notes.append(f"semantic search failed: {e}")

    # 3. IK live search (paid) — ALWAYS run regardless of mode.
    #
    # Previously, mixed mode skipped IK once curated+semantic returned a
    # threshold count of cases. In practice, the 42 curated cases match
    # 3+ keywords for almost every criminal query, so IK never ran and
    # the result pool was always 100% famous landmarks. The product can't
    # claim "Hidden Authorities" if the IK retrieval doesn't fire.
    #
    # Cost: ₹0.50 per search (cached 30 days), so the same query in the
    # next 30 days is free. Worth it.
    run_ik_search = True

    if run_ik_search:
        form_input = _build_search_input(situation, extra_filters=search_filters)
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

        fetched_new = 0
        for score, hit in ranked:
            if len(cases) >= candidate_pool:
                break
            if fetched_new >= effective_max_fetches:
                meta.notes.append(
                    f"hit max_new_fetches={effective_max_fetches} (mode={mode}); "
                    "stopping. Cache will warm over time."
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
            # The 42 curated cases are famous landmarks; surfacing them is
            # the OPPOSITE of the Hidden Authorities promise. Curated stays
            # only as a last-resort fallback (when IK has <3 candidates).
            if mode == "hidden":
                ik_only = [c for c in cases if c.source != "curated"]
                if len(ik_only) >= 3:
                    cases = ik_only
                    meta.notes.append(
                        f"hidden mode: dropped curated landmarks, "
                        f"ranking over {len(cases)} IK candidates only"
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

            # skip_sonnet_rerank=True avoids an extra ~₹4 Sonnet call per query.
            # semantic_similarity (normalised relevance) is used as the fact-match
            # proxy; a good enough approximation for the retrieval use-case.
            scored = rank_candidates(
                situation,
                candidates,
                mode,
                query_jurisdiction=jurisdiction,
                result_top_k=top_cases,
                skip_sonnet_rerank=True,
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
            "bns_mapping": [],   # not curated for IK entries
            "topics": [],
            "facts": facts_text,
            "issues": issues_list,
            "holding": holding_text,
            "key_paras": key_paras_text,
            "subsequent_treatment": "",
            "_source": "ik",
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
