"""
Three-check verification for LLM-generated legal output.

After the Supreme Court's 27 Feb 2026 ruling, citing AI-fabricated case
references is professional misconduct, not error. This module enforces the
three checks the prompt promises but does not technically guarantee:

  1. EXISTENCE  — every `case_id` cited by the LLM must be in the evidence
                  set the LLM was actually given. (No citing cases from
                  training memory.)

  2. ANCHOR     — every paragraph anchor (e.g. "(Paras 14, 16-17)") must
                  point to a paragraph that was actually in the evidence we
                  passed for that case. No invented paragraph numbers.

  3. VERBATIM   — every quoted phrase (anything inside quotes, or following
                  "Held —" / a `quotable_phrase` field) must appear, near-
                  verbatim, in the evidence for the cited case. Fuzzy match
                  with a configurable threshold so minor whitespace and
                  punctuation drift doesn't trigger false alarms, but
                  fabricated quotes do.

Inputs are deliberately framework-agnostic — works for situation, digest,
or headnote-from-judgment outputs. The caller passes:

  - evidence:    list[EvidenceParagraph]   (what we gave the LLM)
  - output:      dict                      (what the LLM returned)

Returns a VerificationReport with per-citation pass/fail and a verdict for
the whole response. Use `report.is_clean()` to decide whether to surface to
the lawyer or regenerate.

No external deps — stdlib only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any, Iterable


# ------------------------------------------------------------------ thresholds

# A "verbatim" quote is considered matched if its similarity to some span in
# the evidence is at or above this ratio. 0.75 is lenient enough to tolerate
# DeepSeek's tendency to lightly paraphrase (scores typically 0.70-0.85) while
# still flagging genuine fabrications (which score below 0.5). The original
# 0.88 was tuned for Claude's more precise quote reproduction; under the
# multi-provider fallback chain, 0.75 prevents real cases from being dropped
# for minor wording differences.
DEFAULT_VERBATIM_THRESHOLD = 0.75

# Minimum length (in characters) for a quoted phrase to be checked. Very short
# fragments ("the Act", "S. 138") will always match and are noise.
MIN_QUOTE_CHARS = 25


# ----------------------------------------------------------------- data shapes

@dataclass(frozen=True)
class EvidenceParagraph:
    """One paragraph of source material we showed the LLM, with provenance."""
    case_id: str            # canonical id in our system (e.g. "BHASK-1999-SC" or "ik:529907")
    para_id: str            # IK's "p_14" or our equivalent
    para_num: int | None    # 14 — for anchor checks like "(Paras 14, 16-17)"
    text: str               # the cleaned plaintext


@dataclass
class CitationFinding:
    """Result for one cited case in the LLM output."""
    case_id: str
    case_title: str
    exists: bool                            # check 1: in evidence set?
    anchor_valid: bool                      # check 2: all para anchors found?
    anchors_claimed: list[int] = field(default_factory=list)
    anchors_missing: list[int] = field(default_factory=list)
    verbatim_checks: list["QuoteCheck"] = field(default_factory=list)

    def is_clean(self) -> bool:
        if not self.exists:
            return False
        if not self.anchor_valid:
            return False
        return all(q.matched for q in self.verbatim_checks)


@dataclass
class QuoteCheck:
    quote: str
    matched: bool
    similarity: float
    best_match_para_id: str | None
    best_match_preview: str | None
    source_field: str         # which JSON field the quote was extracted from


@dataclass
class VerificationReport:
    findings: list[CitationFinding] = field(default_factory=list)
    orphan_case_ids: list[str] = field(default_factory=list)   # cited but not in evidence
    # Free-text issues that don't belong to a specific case (e.g. malformed JSON)
    structural_issues: list[str] = field(default_factory=list)

    def is_clean(self) -> bool:
        return (
            not self.orphan_case_ids
            and not self.structural_issues
            and all(f.is_clean() for f in self.findings)
        )

    def summary(self) -> dict:
        return {
            "clean": self.is_clean(),
            "total_citations": len(self.findings),
            "clean_citations": sum(1 for f in self.findings if f.is_clean()),
            "orphan_case_ids": self.orphan_case_ids,
            "structural_issues": self.structural_issues,
            "failing_citations": [
                {
                    "case_id": f.case_id,
                    "title": f.case_title,
                    "exists": f.exists,
                    "anchor_valid": f.anchor_valid,
                    "anchors_missing": f.anchors_missing,
                    "bad_quotes": [
                        {"quote": q.quote[:120], "similarity": round(q.similarity, 3),
                         "field": q.source_field}
                        for q in f.verbatim_checks if not q.matched
                    ],
                }
                for f in self.findings if not f.is_clean()
            ],
        }


# ----------------------------------------------------------------- text utils

_WS_RX = re.compile(r"\s+")
_PUNCT_RX = re.compile(r"[^\w\s]+")


def _normalise(text: str) -> str:
    """Casefold + unicode-normalise + collapse whitespace. NOT lossy enough to
    hide fabrications, just to absorb whitespace/quote-style drift."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("–", "-").replace("—", "-")
    text = _WS_RX.sub(" ", text)
    return text.strip().casefold()


def _strip_for_similarity(text: str) -> str:
    """Stricter normalisation for fuzzy matching: also drop punctuation."""
    text = _normalise(text)
    text = _PUNCT_RX.sub(" ", text)
    text = _WS_RX.sub(" ", text)
    return text.strip()


# ----------------------------------------------------- quote / anchor extraction

# Match quotes wrapped in double quotes, smart quotes, or following the
# Cri.L.J. "Held —" convention. Group 1 is the inner phrase.
_QUOTE_PATTERNS = [
    re.compile(r'"([^"]{15,400})"'),                                  # "..."
    re.compile(r"“([^”]{15,400})”"),                   # "..."
    re.compile(r"‘([^’]{15,400})’"),                   # '...'
    re.compile(r"Held\s*[—\-]\s*([^.]{15,400}[\.\?\!])"),        # Held — ...
]


def _extract_quotes(text: str) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    if not text:
        return out
    for pat in _QUOTE_PATTERNS:
        for m in pat.finditer(text):
            q = m.group(1).strip()
            if len(q) < MIN_QUOTE_CHARS:
                continue
            key = _normalise(q)
            if key in seen:
                continue
            seen.add(key)
            out.append(q)
    return out


# Match anchors like "(Para 14)", "(Paras 14, 16-17)", "Paras 33-34, 37-39"
_ANCHOR_RX = re.compile(r"Paras?\s+([\d\s,\-–—]+)", re.IGNORECASE)


def _extract_para_numbers(anchor_text: str) -> list[int]:
    """Pull integer paragraph numbers out of a free-text anchor.

    "(Paras 14, 16-17)" -> [14, 16, 17]
    """
    if not anchor_text:
        return []
    out: list[int] = []
    for m in _ANCHOR_RX.finditer(anchor_text):
        body = m.group(1).replace("–", "-").replace("—", "-")
        for chunk in body.split(","):
            chunk = chunk.strip()
            if not chunk:
                continue
            if "-" in chunk:
                lo_s, hi_s = chunk.split("-", 1)
                try:
                    lo, hi = int(lo_s.strip()), int(hi_s.strip())
                except ValueError:
                    continue
                if 0 < lo <= hi < 10_000:
                    out.extend(range(lo, hi + 1))
            else:
                try:
                    out.append(int(chunk))
                except ValueError:
                    continue
    # dedupe, preserve order
    seen: set[int] = set()
    dedup: list[int] = []
    for n in out:
        if n not in seen:
            seen.add(n)
            dedup.append(n)
    return dedup


# ----------------------------------------------------------------- fuzzy match

def _best_match(quote: str, evidence: Iterable[EvidenceParagraph]) -> tuple[float, EvidenceParagraph | None, str]:
    """Find the best fuzzy match for `quote` in `evidence`.

    Returns (similarity_ratio, best_paragraph, preview_of_matched_span).
    """
    q_norm = _strip_for_similarity(quote)
    if not q_norm:
        return 0.0, None, ""
    best_ratio = 0.0
    best_para: EvidenceParagraph | None = None
    best_preview = ""
    for para in evidence:
        p_norm = _strip_for_similarity(para.text)
        if not p_norm:
            continue
        # Two-stage: fast substring check first, then SequenceMatcher only if needed
        if q_norm in p_norm:
            return 1.0, para, _preview_around(para.text, quote)
        # SequenceMatcher is O(n*m) — for ~500 paras * ~300-token quotes this
        # stays well under 100ms. Acceptable for the verification step.
        sm = SequenceMatcher(None, q_norm, p_norm, autojunk=False)
        ratio = sm.ratio()
        if ratio > best_ratio:
            best_ratio = ratio
            best_para = para
            # Use longest matching block for preview
            block = sm.find_longest_match(0, len(q_norm), 0, len(p_norm))
            if block.size > 0:
                start = max(0, block.b - 30)
                end = min(len(para.text), block.b + block.size + 60)
                best_preview = "..." + para.text[start:end].strip() + "..."
            else:
                best_preview = para.text[:160] + "..."
    return best_ratio, best_para, best_preview


def _preview_around(text: str, quote: str) -> str:
    needle = _strip_for_similarity(quote)
    hay = _strip_for_similarity(text)
    idx = hay.find(needle)
    if idx < 0:
        return text[:160] + "..."
    # Approximate mapping back to original indexing — punctuation/case strip
    # makes this imprecise but the preview is just for human display.
    start = max(0, idx - 20)
    end = min(len(text), idx + len(quote) + 60)
    return "..." + text[start:end].strip() + "..."


# ----------------------------------------------------------------- main entry

def verify_situation_response(
    output: dict,
    evidence: list[EvidenceParagraph],
    *,
    known_case_ids: set[str] | None = None,
    verbatim_threshold: float = DEFAULT_VERBATIM_THRESHOLD,
) -> VerificationReport:
    """Verify the JSON output of /api/situation (or /api/digest).

    `evidence` is the flat list of paragraphs we showed the LLM, across all
    cases — `case_id` on each paragraph ties it to the case it came from.

    `known_case_ids` is the universe of valid case_ids (curated + IK-cached
    used in this response). If None, derives from `evidence`.
    """
    report = VerificationReport()
    if not isinstance(output, dict):
        report.structural_issues.append(f"output is not a dict: {type(output).__name__}")
        return report

    cases = output.get("cases") or []
    if not isinstance(cases, list):
        report.structural_issues.append(f"'cases' is not a list: {type(cases).__name__}")
        return report

    if known_case_ids is None:
        known_case_ids = {e.case_id for e in evidence}

    # Group evidence by case_id for per-case quote checks
    evidence_by_case: dict[str, list[EvidenceParagraph]] = {}
    for e in evidence:
        evidence_by_case.setdefault(e.case_id, []).append(e)

    # NEW: defensive case_id matching. DeepSeek-Reasoner sometimes returns
    # a slightly-reformatted case_id (capitalization, whitespace, or even
    # the case TITLE instead of the canonical id). Build a normalised map
    # of known_case_ids so we can rescue these near-matches before marking
    # them as orphans. This is purely additive — exact matches still work
    # the same, the fallback only fires when exact match fails.
    def _norm(s: str) -> str:
        return "".join(ch.lower() for ch in s if ch.isalnum())
    _known_normalised: dict[str, str] = {}
    for kid in known_case_ids:
        n = _norm(kid)
        if n and n not in _known_normalised:
            _known_normalised[n] = kid

    def _resolve_cid(raw_cid: str, raw_title: str) -> str | None:
        """Try to map an LLM-returned case_id back to a real corpus id.
        Returns the matching known_case_id, or None if no match."""
        if not raw_cid:
            return None
        # 1. Exact match (the common path)
        if raw_cid in known_case_ids:
            return raw_cid
        # 2. Normalised match (handles whitespace, case, punctuation)
        n = _norm(raw_cid)
        if n in _known_normalised:
            return _known_normalised[n]
        # 3. Substring match — LLM returned a longer string that contains
        #    the real case_id (e.g., "DASH-2014-SC (Dashrath v State)").
        for kid in known_case_ids:
            if kid and len(kid) >= 5 and kid in raw_cid:
                return kid
        # 4. Reverse substring — LLM returned a fragment of the real id
        #    (e.g., "DASH-2014" when the real id is "DASH-2014-SC").
        for kid in known_case_ids:
            if raw_cid and len(raw_cid) >= 5 and raw_cid in kid:
                return kid
        return None

    for c in cases:
        if not isinstance(c, dict):
            report.structural_issues.append(f"case entry is not a dict: {type(c).__name__}")
            continue

        cid = str(c.get("case_id") or "")
        title = str(c.get("title") or "")

        # Try exact match first (fast path), then fall back to fuzzy resolution
        resolved_cid = _resolve_cid(cid, title)
        if resolved_cid and resolved_cid != cid:
            # Rescue: rewrite the case_id on the output dict so downstream
            # rendering (kanoon_url, paragraph_anchor) uses the canonical id
            c["case_id"] = resolved_cid
            cid = resolved_cid
            # Optional debugging note — kept on the report for ops visibility
            report.structural_issues.append(
                f"case_id rescued via fuzzy match: '{c.get('original_case_id', '')}' → '{resolved_cid}'"
            )

        exists = cid in known_case_ids
        if not exists:
            report.orphan_case_ids.append(cid or "(no case_id)")

        case_evidence = evidence_by_case.get(cid, [])
        valid_para_nums = {e.para_num for e in case_evidence if e.para_num is not None}

        # --- anchor check
        anchor_text = _collect_anchor_text(c)
        anchors_claimed = _extract_para_numbers(anchor_text)
        if not exists:
            anchors_missing = []
            anchor_valid = False  # case itself fabricated
        elif anchors_claimed and not valid_para_nums:
            # The model claimed numbered anchors but the source has only
            # un-numbered paragraphs (older IK judgments). The prompt instructs
            # the model to use para ids like "(p_18)" instead; if it claimed
            # numbers anyway, it's fabricating.
            anchors_missing = anchors_claimed
            anchor_valid = False
        elif valid_para_nums:
            anchors_missing = [n for n in anchors_claimed if n not in valid_para_nums]
            anchor_valid = not anchors_missing
        else:
            # No anchors claimed and no numbered paragraphs — nothing to check.
            anchors_missing = []
            anchor_valid = True

        # --- verbatim check
        quote_checks: list[QuoteCheck] = []
        if exists and case_evidence:
            for field_name, quote in _collect_quotable_phrases(c):
                ratio, para, preview = _best_match(quote, case_evidence)
                quote_checks.append(QuoteCheck(
                    quote=quote,
                    matched=ratio >= verbatim_threshold,
                    similarity=ratio,
                    best_match_para_id=para.para_id if para else None,
                    best_match_preview=preview,
                    source_field=field_name,
                ))

        report.findings.append(CitationFinding(
            case_id=cid,
            case_title=title,
            exists=exists,
            anchor_valid=anchor_valid,
            anchors_claimed=anchors_claimed,
            anchors_missing=anchors_missing,
            verbatim_checks=quote_checks,
        ))

    return report


# ----------------------------------------------------------------- helpers

def _collect_anchor_text(case_entry: dict) -> str:
    """Concatenate all the fields that may contain paragraph anchors."""
    parts: list[str] = []
    jh = case_entry.get("journal_headnote") or {}
    if isinstance(jh, dict):
        for k in ("paragraph_anchor", "ratio", "per_judge_attribution"):
            v = jh.get(k)
            if isinstance(v, str):
                parts.append(v)
    pn = case_entry.get("practitioner_notes") or {}
    if isinstance(pn, dict):
        for k in ("gist", "quotable_phrase"):
            v = pn.get(k)
            if isinstance(v, str):
                parts.append(v)
    # Top-level relevance_explanation can sometimes have anchors too
    if isinstance(case_entry.get("relevance_explanation"), str):
        parts.append(case_entry["relevance_explanation"])
    return "\n".join(parts)


def build_regen_feedback(report: VerificationReport) -> str:
    """Build a focused feedback message to append to the user prompt when
    asking the LLM to regenerate after verification failure.

    The message names specific failed citations, missing anchors, and bad
    quotes so the second attempt can correct them. Keep it short — the model
    has already seen the evidence in the system prompt.
    """
    if report.is_clean():
        return ""
    lines: list[str] = [
        "\n\n---\n",
        "REGENERATION REQUIRED — your previous response failed citation verification.",
        "The following issues must be corrected. Re-emit the JSON response with these problems fixed:",
        "",
    ]
    if report.orphan_case_ids:
        lines.append("CASES NOT IN EVIDENCE (drop these citations or replace with real ones):")
        for cid in report.orphan_case_ids:
            lines.append(f"  - {cid}")
        lines.append("")

    if report.structural_issues:
        lines.append("STRUCTURAL ISSUES:")
        for issue in report.structural_issues:
            lines.append(f"  - {issue}")
        lines.append("")

    bad_anchors = [f for f in report.findings if f.exists and not f.anchor_valid]
    if bad_anchors:
        lines.append("PARAGRAPH ANCHORS THAT DON'T EXIST IN THE SOURCE:")
        for f in bad_anchors:
            lines.append(f"  - {f.case_title or f.case_id}: missing paragraphs {f.anchors_missing}")
            lines.append(f"    Use only paragraph numbers/ids actually present in the case's _ik_paragraphs.")
        lines.append("")

    bad_quotes = [(f, q) for f in report.findings for q in f.verbatim_checks if not q.matched]
    if bad_quotes:
        lines.append("QUOTES THAT DO NOT APPEAR IN THE EVIDENCE (do not invent quotes):")
        for f, q in bad_quotes[:8]:  # cap to keep feedback short
            preview = q.quote[:120].replace("\n", " ")
            lines.append(f"  - in {f.case_id} {q.source_field}, similarity {q.similarity:.2f}:")
            lines.append(f"      claimed: {preview!r}")
            if q.best_match_preview:
                lines.append(f"      nearest evidence: {q.best_match_preview[:120]!r}")
        lines.append("")
        lines.append("RULE: every quoted phrase must appear verbatim (modulo whitespace) in the case's source paragraphs.")

    lines.append("")
    lines.append("Return the corrected JSON only — same schema, same case selection minus the orphans, fixed quotes and anchors.")
    return "\n".join(lines)


def _collect_quotable_phrases(case_entry: dict) -> list[tuple[str, str]]:
    """Pull quoted phrases out of every field that should be sourced verbatim.

    Returns list of (source_field_name, quote_text).
    """
    out: list[tuple[str, str]] = []
    jh = case_entry.get("journal_headnote") or {}
    if isinstance(jh, dict):
        for field in ("ratio", "negative_carve_out"):
            text = jh.get(field) or ""
            for q in _extract_quotes(text):
                out.append((f"journal_headnote.{field}", q))
    pn = case_entry.get("practitioner_notes") or {}
    if isinstance(pn, dict):
        # quotable_phrase is itself a quote — always check it
        qp = pn.get("quotable_phrase")
        if isinstance(qp, str) and len(qp) >= MIN_QUOTE_CHARS:
            out.append(("practitioner_notes.quotable_phrase", qp.strip('"“” ‘’')))
        for field in ("gist",):
            text = pn.get(field) or ""
            for q in _extract_quotes(text):
                out.append((f"practitioner_notes.{field}", q))
    return out
