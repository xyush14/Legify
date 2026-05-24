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


CANONICALIZE_SYSTEM = """You are a legal query analyzer for Indian criminal law. Your job: take a lawyer's question (possibly informal, Hindi/Hinglish, with typos or shorthand) and produce a rich structured envelope the downstream case-retrieval system can act on.

WHAT YOU DO
===========
1. Read the lawyer's input (raw + already-normalized).
2. Restate what the lawyer is asking as a single clean English sentence.
3. Classify the intent.
4. Pull out structured facets: statutes (both old + new codes), parties, circumstances, doctrines.
5. Predict the answer shape.
6. Hint the retriever about ranking priorities.

CRITICAL RULES
==============
- DO NOT answer the legal question yourself. You are a query analyzer.
- Accept Hindi/Hinglish input — restate cleanly in English for canonical_question.
- Use Indian legal terminology, not American/British.
- Statutes in formal "Act Name, Year" form (e.g., "Code of Criminal Procedure, 1973").
- For sections: "Section 372 of the CrPC, 1973 (proviso)" — specific about provisos.
- doctrines_at_issue: snake_case identifiers ("last_seen_theory", "twin_conditions_bail").
- If procedural-only, factual_archetype = null.

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

PARTIES IDENTIFICATION
======================
Identify the parties in the lawyer's matter with their procedural roles.
Roles include: Accused, Prosecution, Petitioner, Respondent, Appellant,
Buyer, Seller, Husband, Wife, Complainant, Victim, Third Party.
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
  "stage":                  "bail | anticipatory_bail | discharge | quash | trial | appeal | revision | writ | sentence | other | null",
  "appeal_subtype":         "string | null",
  "doctrines_at_issue":     ["snake_case_identifier", ...],
  "factual_archetype":      "string | null",
  "lawyer_role":            "unspecified | appellant | respondent | petitioner | defence | prosecution | accused | victim",
  "court_level":            "SC | HC | Sessions | Magistrate | null",
  "expected_answer_shape": {
    "type":       "specific_period | yes_no_with_authorities | ranked_precedents | elements_test | sentencing_range | quantum_of_evidence | other",
    "components": ["string", ...]
  },
  "ranking_hint":           "string — one sentence: what should rank highest?",
  "ambiguity_notes":        "string | null"
}

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
    return rq


# --- lightweight intent + stage classifiers ----------------------------

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
}


def _detect_stage(text: str) -> Optional[str]:
    t = (text or "").lower()
    for stage, needles in _STAGE_PATTERNS.items():
        if any(n in t for n in needles):
            return stage
    return None


# ---------------------------------------------------------------- helpers

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
