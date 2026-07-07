"""Canonical question + intent extraction via Haiku 4.5.

Stage 1 of the case-law finder pipeline. Takes the normalized query and emits:

    {
      "canonical_question":   "What is the limitation period for ...",
      "intent_type":          "procedural_law_question" | "factual_matter" | "doctrinal_inquiry" | "drafting_request",
      "primary_statute":      "Section 372 of the CrPC, 1973 (proviso)",
      "secondary_statutes":   ["Limitation Act, 1963 (Article 115)"],
      "stage":                "appeal",
      "appeal_subtype":       "victim_appeal",
      "doctrines_at_issue":   ["limitation_period", "victim_right_of_appeal"],
      "factual_archetype":    null | "domestic_violence_498a" | "ndps_commercial_quantity" | ...,
      "lawyer_role":          "unspecified" | "appellant" | "respondent" | "petitioner" | "defence" | "prosecution",
      "court_level":          null | "SC" | "HC" | "Sessions" | "Magistrate",
      "expected_answer_shape": {
        "type":       "specific_period" | "yes_no_with_authorities" | "ranked_precedents" | "elements_test" | ...,
        "components": ["number_of_days", "governing_provision", "leading_authority"]
      },
      "ranking_hint":         "..."  # plain English hint for the downstream LLM
    }

Why Haiku? This is parsing + classification. Sonnet would be 7× the cost
for no measurable quality gain on a well-prompted Haiku call.

Cost: ~₹0.50 per call. Cached system prompt keeps it cheap on repeat queries
with overlapping facets (same statute family, same stage).
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field, asdict
from typing import Optional

from headnote.llm import route_call
from headnote.refine.normalize import normalize, NormalizedQuery


log = logging.getLogger(__name__)


CANONICALIZE_SYSTEM = """You are a legal query analyzer for Indian law — criminal AND civil. Your job: take a lawyer's question (possibly informal, Hindi/Hinglish, with typos or shorthand) and produce a rich structured envelope the downstream case-retrieval system can act on.

WHAT YOU DO
===========
1. Read the lawyer's input (raw + already-normalized).
2. Restate what the lawyer is asking as a single clean English sentence.
3. Classify the DOMAIN (criminal / civil / mixed) and the intent.
4. Pull out structured facets: statutes (both old + new codes where applicable), parties, circumstances, doctrines.
5. Predict the answer shape.
6. Hint the retriever about ranking priorities.

CRITICAL RULES
==============
- DO NOT answer the legal question yourself. You are a query analyzer.
- Accept Hindi/Hinglish input — restate cleanly in English for canonical_question.
- Use Indian legal terminology, not American/British.
- Statutes in formal "Act Name, Year" form (e.g., "Code of Criminal Procedure, 1973", "Transfer of Property Act, 1882").
- For sections: "Section 372 of the CrPC, 1973 (proviso)" — specific about provisos.
- doctrines_at_issue: snake_case identifiers ("last_seen_theory", "twin_conditions_bail", "lis_pendens", "part_performance", "bona_fide_purchaser").
- If procedural-only, factual_archetype = null.

DOMAIN CLASSIFICATION (drives the whole downstream pipeline — get it right)
===========================================================================
- "criminal": offences, FIR, bail, charge, trial, sentence, quashing — IPC/BNS, CrPC/BNSS, NDPS, POCSO, NI Act 138, PMLA etc.
- "civil": property, contract, specific performance, injunction, partition, succession, tenancy, recovery of money, easement, family/matrimonial (divorce, maintenance under civil law), consumer, arbitration — TPA, Contract Act, Specific Relief Act, CPC, Registration Act, Limitation Act, Hindu Succession Act etc.
- "mixed": matters with both faces — e.g. a double sale of land (civil title dispute + IPC 420/BNS 318 cheating), cheque dishonour with a contract claim, matrimonial cruelty (498A + divorce). Emit facets for BOTH faces.

FOR CIVIL MATTERS the statute + doctrine ARE the primary retrieval anchor —
identify the governing Act and section precisely (e.g. "Section 54 of the
Transfer of Property Act, 1882" for sale; "Section 19(b) of the Specific
Relief Act, 1963" for the bona fide purchaser exception; "Section 52 TPA"
for lis pendens). Common civil anchors:
  Sale / double sale / title      → TPA 1882 (S.54), Registration Act 1908 (S.17, 47-50)
  Agreement to sell / specific performance → Specific Relief Act 1963 (S.10-20), TPA S.53A (part performance)
  Bona fide purchaser             → Specific Relief Act S.19(b), TPA S.41 (ostensible owner)
  Injunction                      → Specific Relief Act S.36-42, CPC Order XXXIX
  Partition / co-ownership        → TPA S.44, Partition Act 1893, Hindu Succession Act 1956
  Recovery of money               → CPC Order XXXVII, Contract Act 1872, Limitation Act 1963 (Art. 1-55)
  Tenancy / eviction              → state Rent Acts, TPA S.106-111
  Consumer                        → Consumer Protection Act 2019
  Arbitration                     → Arbitration and Conciliation Act 1996 (S.8, 9, 11, 34)

DUAL STATUTE MAPPING (non-negotiable for Indian criminal law mid-transition)
============================================================================
For ANY IPC, CrPC, or Evidence Act section, emit BOTH the old and new
equivalent in dual_statute_map. Reference table:
  IPC 420 (cheating)              → BNS 318
  IPC 406 (criminal breach trust) → BNS 316
  IPC 376 (rape)                  → BNS 63
  IPC 498A (cruelty)              → BNS 85/86
  IPC 302 (murder)                → BNS 103
  IPC 304B (dowry death)          → BNS 80
  CrPC 156(3) (Magistrate FIR)    → BNSS 175(3)
  CrPC 482 (inherent powers)      → BNSS 528
  CrPC 437/439 (bail)             → BNSS 480/483
  CrPC 438 (anticipatory bail)    → BNSS 482
  CrPC 372 (victim appeal)        → BNSS 413
  Evidence Act 27                 → BSA 23
  Evidence Act 65B                → BSA 63
Civil statutes (TPA, Contract Act, CPC, Specific Relief Act …) have NOT been
recodified — for a purely civil query dual_statute_map may be empty.

PARTIES IDENTIFICATION
======================
Identify the parties in the lawyer's matter with their procedural roles.
Roles include: Accused, Prosecution, Petitioner, Respondent, Appellant,
Plaintiff, Defendant, Buyer, Seller, Vendor, Vendee, Landlord, Tenant,
Co-owner, Husband, Wife, Complainant, Victim, Third Party.
Each entry: {"role": "Accused", "description": "first-time offender, retired teacher"}.

CORE CIRCUMSTANCES
==================
List 3-8 facts in chronological order, neutrally stated. These will be matched
against case fact-patterns for relevance scoring.

LEGAL CONCEPTS
==============
Doctrinal terms-of-art the case turns on, in plain English (NOT snake_case).
Examples: "dishonest intent at inception", "vicarious criminal liability",
"agreement to sell vs sale deed", "compounding under Section 446B".
These are what a junior would need defined to understand the matter.

OUTPUT JSON SCHEMA
==================
{
  "canonical_question":     "string — one clean English sentence, the actual question",
  "domain":                 "criminal | civil | mixed",
  "intent_type":            "procedural_law_question | factual_matter | doctrinal_inquiry | drafting_request | judgment_summary",
  "primary_statute":        "string — formal citation (use the post-2024 code if applicable)",
  "secondary_statutes":     ["string", ...],
  "dual_statute_map": [
    {"old": "Section 420 IPC", "new": "Section 318 BNS", "subject": "cheating"},
    ...
  ],
  "parties_involved": [
    {"role": "Accused", "description": "first-time defaulter, retired schoolteacher"},
    {"role": "Prosecution", "description": "Registrar of Companies"}
  ],
  "core_circumstances":     ["string — short factual bullet, chronological order", ...],
  "legal_concepts":         ["string — plain-English doctrinal term", ...],
  "stage":                  "bail | anticipatory_bail | discharge | quash | trial | appeal | revision | writ | sentence | suit | interim_relief | execution | first_appeal | second_appeal | pre_litigation | other | null",
  "appeal_subtype":         "string | null",
  "doctrines_at_issue":     ["snake_case_identifier", ...],
  "factual_archetype":      "string | null — civil archetypes are valid too (e.g. 'double_sale_co_owned_land', 'specific_performance_agreement_to_sell', 'tenant_eviction_bona_fide_need')",
  "lawyer_role":            "unspecified | appellant | respondent | petitioner | defence | prosecution | accused | victim | plaintiff | defendant",
  "court_level":            "SC | HC | Sessions | Magistrate | null",
  "expected_answer_shape": {
    "type":       "specific_period | yes_no_with_authorities | ranked_precedents | elements_test | sentencing_range | quantum_of_evidence | other",
    "components": ["string", ...]
  },
  "ranking_hint":           "string — one sentence: what should rank highest?",
  "ik_search_queries":      ["string — see SEARCH QUERIES below", ...],
  "ambiguity_notes":        "string | null"
}

SEARCH QUERIES (this is where retrieval is won or lost)
========================================================
Emit 3-4 SHORT keyword queries (4-8 words each) for Indian Kanoon's
keyword search engine. Think like a senior advocate at the terminal: each
query is a DIFFERENT ANGLE on the matter, phrased in the words an Indian
JUDGMENT would actually use — not the lawyer's colloquial phrasing.
  1. statute + operative concept  (e.g. section 420 cheating "second sale deed")
  2. doctrine as judgments phrase it  (e.g. "sale of same property" subsequent purchaser)
  3. fact-pattern / remedy idiom  (e.g. vendor "already sold" property cheating)
  4. old-code variant when the matter has one  (e.g. 420 IPC cheating sale deed)
PRECISION RULES (these queries fail on generic words):
  - Wrap the ONE most distinctive 2-3 word phrase of each query in double
    quotes — the engine then requires that exact phrase ("double sale",
    "second sale deed", "agreement to sell").
  - AVOID bare homonyms that collide across domains: "share" alone pulls
    company-shares cases — write "share in joint property" or "co-sharer";
    "deed" alone pulls partnership deeds — write "sale deed".
  - lowercase, no other punctuation, no years, no "the lawyer's client",
    NO query longer than 8 words. Each query must stand alone.

Return ONLY the JSON. No prose, no markdown fences.
"""


CANONICALIZE_USER_TEMPLATE = """RAW INPUT (as the lawyer typed it):
{raw}

NORMALIZED INPUT (statute aliases + section shorthand already expanded):
{normalized}

Substitutions applied during normalization (for context only):
{subs_summary}

Now produce the structured envelope.
"""


@dataclass
class RefinedQuery:
    """The structured envelope produced by Stage 1."""
    raw:                  str
    normalized:           str
    canonical_question:   str
    # Which body of law the matter lives in. Drives IK query construction
    # (civil → statute-first), prerank rubric framing, and prompt examples.
    # "criminal" is the safe default — it preserves the pipeline's historical
    # behaviour exactly when detection is unavailable.
    domain:               str = "criminal"
    intent_type:          str = "factual_matter"
    primary_statute:      Optional[str] = None
    secondary_statutes:   list[str] = field(default_factory=list)
    # NEW: lexlegis-style decomposition facets ----------------------------
    dual_statute_map:     list[dict] = field(default_factory=list)
    parties_involved:     list[dict] = field(default_factory=list)
    core_circumstances:   list[str] = field(default_factory=list)
    legal_concepts:       list[str] = field(default_factory=list)
    # --------------------------------------------------------------------
    stage:                Optional[str] = None
    appeal_subtype:       Optional[str] = None
    doctrines_at_issue:   list[str] = field(default_factory=list)
    factual_archetype:    Optional[str] = None
    lawyer_role:          str = "unspecified"
    court_level:          Optional[str] = None
    expected_answer_shape: dict = field(default_factory=dict)
    ranking_hint:         str = ""
    # LLM-authored short IK queries, each a different retrieval angle phrased
    # the way judgments are indexed. Empty → retrieval falls back to the
    # deterministic facet-join query only.
    ik_search_queries:    list[str] = field(default_factory=list)
    ambiguity_notes:      Optional[str] = None
    normalization_substitutions: list[dict] = field(default_factory=list)
    cost_paise:           int = 0
    elapsed_ms:           int = 0

    def to_dict(self) -> dict:
        return asdict(self)

    def search_terms(self) -> list[str]:
        """Generate keyword search terms from the structured envelope.

        Used by retrieval to widen the candidate pool. Now includes BOTH
        the old and new code section references (CrPC + BNSS etc) so
        cases citing either are surfaced.
        """
        terms: list[str] = []
        if self.primary_statute:
            terms.append(self.primary_statute)
        terms.extend(self.secondary_statutes)
        # Dual-code lookup — include both old and new section numbers
        for ds in self.dual_statute_map:
            if isinstance(ds, dict):
                if ds.get("old"): terms.append(ds["old"])
                if ds.get("new"): terms.append(ds["new"])
        if self.stage:
            terms.append(self.stage.replace("_", " "))
        for d in self.doctrines_at_issue:
            terms.append(d.replace("_", " "))
        # Legal concepts (plain-English doctrinal terms)
        terms.extend(self.legal_concepts)
        if self.factual_archetype:
            terms.append(self.factual_archetype.replace("_", " "))
        # Always include the canonical question for embedding-based retrieval
        terms.append(self.canonical_question)
        return terms

    def statute_section_keywords(self) -> list[str]:
        """Return only the section/statute identifiers (both codes) for
        keyword-filter pre-filtering. Used by retrieval's pre-filter step
        to keep only cases mentioning at least one of these section refs.
        """
        out: list[str] = []
        if self.primary_statute:
            out.append(self.primary_statute)
        out.extend(self.secondary_statutes)
        for ds in self.dual_statute_map:
            if isinstance(ds, dict):
                if ds.get("old"): out.append(ds["old"])
                if ds.get("new"): out.append(ds["new"])
        return [s for s in out if s]


# ----------------------------------------------------------------- main API

def canonicalize(normalized: NormalizedQuery) -> RefinedQuery:
    """Run the Haiku canonicalization call. Pure function — no side effects.

    On any failure (Haiku unavailable, JSON parse error, etc.), returns a
    minimal RefinedQuery that falls back to the normalized text — pipeline
    keeps working with reduced precision.
    """
    t0 = time.time()

    subs_summary = (
        "\n".join(f"  - {s['group']}: {s['rule']} (×{s['count']})" for s in normalized.substitutions)
        or "  (none)"
    )

    user_prompt = CANONICALIZE_USER_TEMPLATE.format(
        raw=normalized.raw,
        normalized=normalized.normalized,
        subs_summary=subs_summary,
    )

    try:
        result = route_call(
            "extraction",  # → Haiku 4.5 by router
            {
                "system_prompt": CANONICALIZE_SYSTEM,
                "user_prompt":   user_prompt,
                "cache":         True,  # system prompt is static — cache it
            },
        )
    except Exception as e:
        log.warning("canonicalize: Haiku call failed (%s); falling back to normalized only", e)
        return _fallback(normalized, elapsed_ms=int((time.time() - t0) * 1000))

    parsed = _parse_json_safe(result.response)
    if not parsed:
        log.warning("canonicalize: Haiku returned non-JSON; falling back")
        return _fallback(normalized, cost_paise=result.cost_paise,
                         elapsed_ms=int((time.time() - t0) * 1000))

    return RefinedQuery(
        raw                  = normalized.raw,
        normalized           = normalized.normalized,
        canonical_question   = parsed.get("canonical_question") or normalized.normalized,
        domain               = _valid_domain(parsed.get("domain")) or _detect_domain(normalized.normalized),
        intent_type          = parsed.get("intent_type", "factual_matter"),
        primary_statute      = parsed.get("primary_statute"),
        secondary_statutes   = parsed.get("secondary_statutes") or [],
        # New lexlegis-style facets
        dual_statute_map     = parsed.get("dual_statute_map") or [],
        parties_involved     = parsed.get("parties_involved") or [],
        core_circumstances   = parsed.get("core_circumstances") or [],
        legal_concepts       = parsed.get("legal_concepts") or [],
        # Existing facets
        stage                = parsed.get("stage"),
        appeal_subtype       = parsed.get("appeal_subtype"),
        doctrines_at_issue   = parsed.get("doctrines_at_issue") or [],
        factual_archetype    = parsed.get("factual_archetype"),
        lawyer_role          = parsed.get("lawyer_role", "unspecified"),
        court_level          = parsed.get("court_level"),
        expected_answer_shape= parsed.get("expected_answer_shape") or {},
        ranking_hint         = parsed.get("ranking_hint", ""),
        ik_search_queries    = _clean_search_queries(parsed.get("ik_search_queries")),
        ambiguity_notes      = parsed.get("ambiguity_notes"),
        normalization_substitutions = normalized.substitutions,
        cost_paise           = result.cost_paise,
        elapsed_ms           = int((time.time() - t0) * 1000),
    )


def refine_query(raw: str) -> RefinedQuery:
    """Top-level entry point: normalize → canonicalize.

    Use this in API endpoints:
        refined = refine_query(req.situation)
        # refined.canonical_question is the cleaned question
        # refined.search_terms() feeds the retriever
        # refined.to_dict() goes into the API response meta
    """
    norm = normalize(raw)
    return canonicalize(norm)


def shallow_refine(raw: str) -> RefinedQuery:
    """Fast path: regex normalize + lightweight intent detection, NO Haiku call.

    Sonnet's situation prompt is already strong at query understanding,
    but the V2 prompt has a CRITICAL branch on intent_type — for
    procedural/doctrinal questions, it tells Sonnet to weight DOCTRINAL
    over FACT_ARCHETYPE (otherwise good procedural cases get dropped
    because they don't share fact patterns).

    So we keep the regex normalize (instant) + a tiny rule-based intent
    classifier (also instant) — enough to flip the right V2 switch
    without spending 3-5s on a Haiku call.

    Trade-off vs full refine_query():
      - No structured statute extraction (Sonnet does it from raw)
      - No doctrines_at_issue list (Sonnet figures it out)
      - DOES set intent_type correctly → V2 prompt's procedural branch fires
    """
    norm = normalize(raw)
    rq = _fallback(norm)
    rq.intent_type = _detect_intent(norm.normalized)
    rq.stage = _detect_stage(norm.normalized)
    rq.domain = _detect_domain(norm.normalized)
    return rq


# --- lightweight intent + stage + domain classifiers --------------------

_PROCEDURAL_NEEDLES = (
    "limitation period", "limitation days", "time limit", "time-limit",
    "deadline", "within how many days", "what is the period",
    "filing period", "appeal period", "jurisdiction of", "which court",
    "maintainability of",
)
_DOCTRINAL_NEEDLES = (
    "doctrine of", "principle of", "ratio of", "elements of",
    "ingredients of", "what constitutes",
)
_DRAFTING_NEEDLES = (
    "draft a", "draft an", "write a complaint", "prepare an application",
    "format of",
)
_JUDGMENT_SUMMARY_NEEDLES = (
    "summarize this judgment", "key holdings of", "headnote for",
)


def _detect_intent(text: str) -> str:
    t = (text or "").lower()
    if any(n in t for n in _DRAFTING_NEEDLES):
        return "drafting_request"
    if any(n in t for n in _JUDGMENT_SUMMARY_NEEDLES):
        return "judgment_summary"
    if any(n in t for n in _PROCEDURAL_NEEDLES):
        return "procedural_law_question"
    if any(n in t for n in _DOCTRINAL_NEEDLES):
        return "doctrinal_inquiry"
    return "factual_matter"


_STAGE_PATTERNS = {
    "anticipatory_bail": ("anticipatory bail", "section 438", "section 482 bnss"),
    "bail":             ("bail application", "regular bail", "section 437", "section 439", "section 480 bnss"),
    "appeal":           ("appeal against", "filing an appeal", "section 372", "section 374"),
    "revision":         ("revision against", "revision under section 397", "revisional jurisdiction"),
    "quash":            ("quash the fir", "quashing of fir", "section 482 crpc", "section 528 bnss"),
    "discharge":        ("discharge under section 227", "discharge application"),
    "writ":             ("writ petition", "habeas corpus", "article 226", "article 32"),
    # Civil procedural postures
    "interim_relief":   ("temporary injunction", "interim injunction", "order 39", "order xxxix", "stay on"),
    "suit":             ("file a suit", "civil suit", "suit for", "plaint"),
    "execution":        ("execution of decree", "execution petition", "order 21", "order xxi"),
}


def _detect_stage(text: str) -> Optional[str]:
    t = (text or "").lower()
    for stage, needles in _STAGE_PATTERNS.items():
        if any(n in t for n in needles):
            return stage
    return None


# --- domain detection (criminal / civil / mixed) ------------------------
# Keyword-based, used both as the shallow-refine classifier and as the
# backstop when the Haiku call omits/mangles the `domain` field. Errs toward
# "criminal" (the pipeline's historical assumption) when nothing matches.

# Matched with word boundaries (\b) — a bare substring check would let "fir"
# fire inside "first" and "rent" inside "current".
_CRIMINAL_NEEDLES = (
    "fir", "bail", "accused", "ipc", "bns", "crpc", "bnss", "prosecution",
    "quash", "charge sheet", "chargesheet", "acquittal", "conviction",
    "anticipatory", "custody", "arrest", "arrested", "ndps", "pocso", "pmla",
    "section 138", "cheque bounce", "cheque dishonour", "cognizable",
    "offence", "offense", "criminal", "police station", "remand",
    # bare-section shorthands lawyers actually type (unambiguously criminal)
    "498a", "304b", "302 case", "420 case", "dowry",
)
_CIVIL_NEEDLES = (
    "sale deed", "agreement to sell", "specific performance", "injunction",
    "partition", "co-owner", "co-owned", "coowner", "title dispute", "easement",
    "tenant", "landlord", "eviction", "rent", "lease", "mortgage",
    "succession", "inheritance", "probate", "testamentary", "plaintiff", "defendant",
    "decree", "civil suit", "plaint", "written statement", "recovery of money",
    "breach of contract", "damages for", "consumer", "arbitration",
    "transfer of property", "registration act", "limitation act",
    "double sale", "encroachment", "possession suit", "declaration of title",
    "divorce", "maintenance", "custody of child", "alimony",
)

_CRIMINAL_RX = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in _CRIMINAL_NEEDLES) + r")\b")
_CIVIL_RX = re.compile(r"\b(?:" + "|".join(re.escape(n) for n in _CIVIL_NEEDLES) + r")\b")


def _valid_domain(v) -> Optional[str]:
    return v if v in ("criminal", "civil", "mixed") else None


def _detect_domain(text: str) -> str:
    t = (text or "").lower()
    crim = len(_CRIMINAL_RX.findall(t))
    civ = len(_CIVIL_RX.findall(t))
    if crim and civ:
        return "mixed"
    if civ:
        return "civil"
    return "criminal"


# ---------------------------------------------------------------- helpers

def _clean_search_queries(raw) -> list[str]:
    """Validate the LLM's ik_search_queries: strings only, 3-8 words,
    lowercased, deduped, capped at 4. Double quotes are PRESERVED — IK
    treats a quoted span as an exact-phrase requirement, which is the main
    precision lever against generic-keyword noise. Unbalanced quotes are
    stripped. Anything malformed is dropped — retrieval always has the
    deterministic facet query as its floor."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for q in raw:
        if not isinstance(q, str):
            continue
        s = re.sub(r"[“”]", '"', q.lower())
        s = re.sub(r'[^\w\s()/"-]', " ", s)
        s = re.sub(r"\s+", " ", s).strip()
        if s.count('"') % 2 != 0:          # unbalanced — drop the quotes, keep the words
            s = s.replace('"', "")
        n_words = len(s.replace('"', "").split())
        if not (3 <= n_words <= 8):
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
        if len(out) >= 4:
            break
    return out


def _parse_json_safe(raw: str) -> dict:
    """Lift any well-formed JSON object out of the Haiku response."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


def _fallback(normalized: NormalizedQuery, *, cost_paise: int = 0, elapsed_ms: int = 0) -> RefinedQuery:
    """Minimal RefinedQuery when canonicalization fails — pipeline still works."""
    return RefinedQuery(
        raw                = normalized.raw,
        normalized         = normalized.normalized,
        canonical_question = normalized.normalized,
        normalization_substitutions = normalized.substitutions,
        cost_paise         = cost_paise,
        elapsed_ms         = elapsed_ms,
    )
