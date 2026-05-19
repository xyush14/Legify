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


CANONICALIZE_SYSTEM = """You are a legal query analyzer for Indian criminal law. Your job: take a lawyer's question (possibly informal, with typos, shorthand, or grammar issues) and produce a structured envelope the downstream case-retrieval system can act on.

WHAT YOU DO
===========
1. Read the lawyer's input (raw + already-normalized for shorthand expansion).
2. Identify what the lawyer is actually asking — restate it as a single clean question.
3. Classify the intent.
4. Pull out structured facets: statutes, stage, doctrines, etc.
5. Predict what shape the answer should take (specific days? ranked cases? elements test?).
6. Hint the downstream retriever about ranking priorities.

CRITICAL RULES
==============
- DO NOT answer the legal question yourself. You are a query analyzer, not a research assistant.
- If the input is ambiguous, set "ambiguity_notes" but still produce your best canonical question.
- Use Indian legal terminology, not American/British equivalents.
- Statute names should be the formal "Act Name, Year" form (e.g., "Code of Criminal Procedure, 1973", not "CrPC").
- For sections: "Section 372 of the CrPC, 1973 (proviso)" — be specific about provisos / subsections / explanations.
- doctrines_at_issue: short snake_case identifiers (e.g., "limitation_period", "victim_right_of_appeal", "twin_conditions_bail", "last_seen_theory", "circumstantial_evidence_five_golden_principles").
- If the question is purely procedural (limitation, jurisdiction, bail conditions), set factual_archetype to null. Procedural questions don't have fact archetypes.
- If a fact pattern IS present, name the archetype (e.g., "domestic_violence_498a_settlement", "ndps_commercial_quantity_no_recovery_memo", "pocso_age_proximity_consensual").

OUTPUT JSON SCHEMA
==================
{
  "canonical_question":     "string — one clean sentence, the actual question",
  "intent_type":            "procedural_law_question | factual_matter | doctrinal_inquiry | drafting_request | judgment_summary",
  "primary_statute":        "string — formal citation",
  "secondary_statutes":     ["string", ...],
  "stage":                  "bail | anticipatory_bail | discharge | quash | trial | appeal | revision | writ | sentence | other | null",
  "appeal_subtype":         "string | null  — e.g., 'victim_appeal', 'state_appeal_against_acquittal'",
  "doctrines_at_issue":     ["snake_case_identifier", ...],
  "factual_archetype":      "string | null",
  "lawyer_role":            "unspecified | appellant | respondent | petitioner | defence | prosecution | accused | victim",
  "court_level":            "SC | HC | Sessions | Magistrate | null",
  "expected_answer_shape": {
    "type":       "specific_period | yes_no_with_authorities | ranked_precedents | elements_test | sentencing_range | quantum_of_evidence | other",
    "components": ["string", ...]
  },
  "ranking_hint":           "string — one sentence: what should rank highest? what should rank lower?",
  "ambiguity_notes":        "string | null — flag any genuine ambiguity in the input"
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

        Used by retrieval to widen the candidate pool beyond the raw input's
        literal words. Combines statute references + stage + doctrines.
        """
        terms: list[str] = []
        if self.primary_statute:
            terms.append(self.primary_statute)
        terms.extend(self.secondary_statutes)
        if self.stage:
            terms.append(self.stage.replace("_", " "))
        for d in self.doctrines_at_issue:
            terms.append(d.replace("_", " "))
        if self.factual_archetype:
            terms.append(self.factual_archetype.replace("_", " "))
        # Always include the canonical question for embedding-based retrieval
        terms.append(self.canonical_question)
        return terms


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
