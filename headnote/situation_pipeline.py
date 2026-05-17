"""
Two-phase situation pipeline.

Why two phases?
================
The original /api/situation endpoint asked Sonnet to do six jobs in one call:
case selection, relevance reasoning, ratio extraction, carve-out drafting,
paragraph anchoring, statute indexing — for ALL five returned cases at once.
That's ~3,500 output tokens at Sonnet's ~50 tok/s ≈ 70 seconds. No model
upgrade fixes output volume; the answer is to split the work.

Phase 1 — candidate filtering (Haiku, ~3s, single call):
  Pick the 3-5 most factually relevant case_ids from the 5-25 candidate pool.
  Input is light (title + 1-line summary per candidate). Output is just IDs
  plus a one-line rationale per case.

Phase 2 — per-case headnote generation (Sonnet, parallel, ~5-8s each):
  For each selected case, ONE focused Sonnet call generates the full
  relevance_explanation + journal_headnote OR practitioner_notes for that
  single case. Calls run concurrently via ThreadPoolExecutor.

Phase 3 — stitching + verification:
  Combine per-case outputs into the response shape the UI expects, then
  run the three-check verifier. Done in-process, microseconds.

Total wall-clock: ~10-15s for a typical 4-case response. Each individual
LLM call stays small enough that we never blow past Render's request budget.
"""

from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from headnote.llm import route_call
from headnote.llm.prompts import (
    SELECT_CANDIDATES_SYSTEM,
    build_select_candidates_user,
    PER_CASE_HEADNOTE_SYSTEM,
    build_per_case_user,
)


def _parse_json_safe(raw: str) -> dict:
    """Best-effort JSON parse — strips code fences, picks first { ... } block."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        return json.loads(text)
    except Exception:
        # Try to extract the first balanced JSON object
        m = re.search(r"\{.*\}", text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {}


# ----------------------------------------------------------------- Phase 1

def select_candidates(
    situation: str,
    candidates: list[dict],
    max_cases: int = 5,
) -> tuple[list[str], int]:
    """Phase 1: ask Haiku which 3-5 case_ids in `candidates` are most relevant.

    `candidates` is a list of dicts with keys: id, title, citation, court,
    year, numcitedby (optional), holding (or 1-line summary).

    Returns (selected_case_ids, cost_paise). The IDs are guaranteed to be a
    subset of input candidate IDs (we filter Haiku's output against the
    candidate map before returning).
    """
    if not candidates:
        return [], 0
    # If the candidate pool is already at or under the target, skip Phase 1.
    if len(candidates) <= max_cases:
        return [c.get("id") for c in candidates if c.get("id")], 0

    valid_ids = {c.get("id") for c in candidates if c.get("id")}

    try:
        result = route_call(
            "extraction",  # cheap Haiku tier
            {
                "system_prompt": SELECT_CANDIDATES_SYSTEM,
                "user_prompt": build_select_candidates_user(situation, candidates, max_cases),
                "cache": True,
            },
        )
    except Exception as e:
        print(f"[situation_pipeline] phase 1 (Haiku select) failed: {e}")
        # Fall back to candidate order — already reranked by hidden_authorities
        return [c.get("id") for c in candidates[:max_cases] if c.get("id")], 0

    parsed = _parse_json_safe(result.response)
    raw_ids = parsed.get("selected_case_ids") or parsed.get("selected") or []
    selected = []
    for cid in raw_ids:
        if isinstance(cid, dict):
            cid = cid.get("case_id") or cid.get("id")
        if cid in valid_ids and cid not in selected:
            selected.append(cid)
        if len(selected) >= max_cases:
            break

    # Backfill if Haiku returned too few valid IDs
    if len(selected) < min(3, len(candidates)):
        for c in candidates:
            cid = c.get("id")
            if cid and cid in valid_ids and cid not in selected:
                selected.append(cid)
                if len(selected) >= max_cases:
                    break

    return selected, result.cost_paise


# ----------------------------------------------------------------- Phase 2

def _generate_one(
    situation: str,
    case_entry: dict,
    style: str,
    cache_key: str,
    force_model: Optional[str] = "sonnet",
) -> tuple[dict, int]:
    """Generate the full per-case JSON block for a single case. Sonnet call
    by default; honours `force_model="opus"` when deep_mode is on."""
    try:
        result = route_call(
            "situation",  # default tier
            {
                "system_prompt": PER_CASE_HEADNOTE_SYSTEM,
                "user_prompt": build_per_case_user(situation, case_entry, style),
                "cache": True,
            },
            force_model=force_model,
        )
    except Exception as e:
        return {"_error": str(e), "case_id": case_entry.get("id")}, 0

    parsed = _parse_json_safe(result.response)
    # Make sure case_id is the corpus id (sometimes the LLM emits the title)
    parsed["case_id"] = case_entry.get("id") or parsed.get("case_id")
    # Sensible defaults the UI expects
    if "title" not in parsed:
        parsed["title"] = case_entry.get("title", "")
    if "citation" not in parsed:
        parsed["citation"] = case_entry.get("citation", "")
    if "court" not in parsed:
        parsed["court"] = case_entry.get("court", "")
    if "year" not in parsed:
        parsed["year"] = case_entry.get("year")
    return parsed, result.cost_paise


def generate_cases_parallel(
    situation: str,
    selected_entries: list[dict],
    style: str,
    max_workers: int = 5,
    force_model: Optional[str] = "sonnet",
) -> tuple[list[dict], int]:
    """Phase 2: generate per-case headnotes in parallel.

    Returns (list_of_case_dicts, total_cost_paise). The list is ordered to
    match `selected_entries` order (preserving Hidden-Authorities rank).
    """
    if not selected_entries:
        return [], 0

    results_by_id: dict[str, dict] = {}
    total_paise = 0
    cache_key = f"v1-{style}"

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {
            pool.submit(_generate_one, situation, entry, style, cache_key, force_model): entry.get("id")
            for entry in selected_entries
        }
        for fut in as_completed(futures):
            cid = futures[fut]
            try:
                parsed, paise = fut.result()
                total_paise += int(paise or 0)
                if isinstance(parsed, dict) and not parsed.get("_error"):
                    results_by_id[cid] = parsed
            except Exception as e:
                print(f"[situation_pipeline] phase 2 worker failed for {cid}: {e}")

    # Re-order to match the input ordering (preserves reranker decisions)
    ordered = [results_by_id[e.get("id")] for e in selected_entries if e.get("id") in results_by_id]
    return ordered, total_paise


# ----------------------------------------------------------------- orchestrator

def run_two_phase_pipeline(
    situation: str,
    candidates_for_prompt: list[dict],
    style: str = "practitioner",
    max_cases: int = 5,
    force_model: Optional[str] = "sonnet",
) -> dict:
    """End-to-end: Phase 1 (select) → Phase 2 (parallel generate) → assemble.

    `candidates_for_prompt` is the corpus-shaped list from
    result_to_prompt_corpus_json (already reranked + trimmed).

    Returns a dict shaped like the legacy single-call response:
      {
        "confidence": "high" | "medium" | "low",
        "style": style,
        "cases": [ ... per-case dicts ... ],
        "_phase_costs": {"select_paise": ..., "generate_paise": ...},
        "_phase_elapsed": {"select_seconds": ..., "generate_seconds": ...},
      }
    """
    t1 = time.time()
    selected_ids, select_paise = select_candidates(situation, candidates_for_prompt, max_cases=max_cases)
    select_elapsed = round(time.time() - t1, 2)

    by_id = {c.get("id"): c for c in candidates_for_prompt if c.get("id")}
    selected_entries = [by_id[cid] for cid in selected_ids if cid in by_id]

    t2 = time.time()
    cases, gen_paise = generate_cases_parallel(
        situation, selected_entries, style=style, force_model=force_model,
    )
    gen_elapsed = round(time.time() - t2, 2)

    confidence = "high" if len(cases) >= 3 else ("medium" if cases else "low")

    return {
        "confidence": confidence,
        "style": style,
        "cases": cases,
        "_phase_costs": {"select_paise": select_paise, "generate_paise": gen_paise},
        "_phase_elapsed": {"select_seconds": select_elapsed, "generate_seconds": gen_elapsed},
    }
