"""
Smart model router for Claude calls.

Wraps `headnote.llm.client.call_claude_cached` with a routing layer that picks
the right model per task type, asks generation models to self-rate confidence,
and auto-upgrades Sonnet → Opus on low confidence.

Routing rules
-------------
    Haiku  4.5  ─ translation, verification, extraction
                  (cheap, simple parsing / classification tasks)

    Sonnet 4.6  ─ situation, digest, rerank          (default for generation)

    Opus   4.6  ─ headnote                           (the unique workflow / moat)
                  + Sonnet → Opus retry on confidence < 7
                  + force_model="opus" override

Confidence is injected into the user prompt for generation tasks
(`situation`, `digest`, `headnote`) per the spec:

    "After your answer, on a new line, output: CONFIDENCE: <integer 1-10>
     based on how certain you are this output is accurate and high-quality."

The score is parsed from the model's response and stripped before the text
is returned to the caller. If the model declines to provide a score or
the score isn't parseable, `confidence_score` is `None` and no retry is
triggered.

The router does NOT modify the existing API endpoints. Callers wire it in
when they're ready.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Literal, NamedTuple, Optional

from headnote import config
from headnote.llm.client import call_claude_cached
from headnote.llm.gemini import call_gemini as _call_gemini, _is_configured as _gemini_configured


# Anthropic error types we treat as "try Gemini next." Imported lazily so a
# stale anthropic SDK doesn't blow up module load. Network errors covered
# explicitly via APIConnectionError; rate-limit / overloaded covered via
# RateLimitError + APIStatusError.
# Substrings in an Anthropic error message that mean "out of credits /
# billing" rather than "your request is broken." A BadRequestError (HTTP
# 400) for these reasons SHOULD trigger Gemini fallback — the request
# itself was valid, the account just can't pay.
_BILLING_NEEDLES = (
    "credit balance is too low",
    "insufficient credits",
    "billing",
    "out of credits",
    "credit balance",
    "your account does not have",     # forward-compatible
    "purchase credits",
)


def _is_anthropic_transient_error(err: Exception) -> bool:
    """True iff `err` is the kind of Anthropic failure where Gemini fallback
    is the right move. Anything else (auth, schema, bad request that's
    actually our bug) bubbles up unchanged.

    Catches:
      - RateLimitError (429)
      - APIConnectionError (network blip)
      - InternalServerError (5xx)
      - APIStatusError where status is 429 OR 5xx
      - BadRequestError (400) where the message mentions billing / credits
        — this is the 'Your credit balance is too low' case. Real schema
        errors don't mention credit/billing so this filter is safe.
    """
    try:
        from anthropic import (
            RateLimitError, APIConnectionError, APIStatusError,
            InternalServerError, BadRequestError,
        )
    except ImportError:
        return False

    if isinstance(err, (RateLimitError, APIConnectionError, InternalServerError)):
        return True

    if isinstance(err, BadRequestError):
        # 400s for billing-related reasons get the fallback; 400s for
        # actual bad requests (wrong model, broken schema) bubble up so
        # the bug is visible.
        msg = (str(err) or "").lower()
        if any(needle in msg for needle in _BILLING_NEEDLES):
            return True
        return False

    if isinstance(err, APIStatusError):
        status = getattr(err, "status_code", None)
        if status == 429 or (status is not None and 500 <= status < 600):
            return True
        # Sometimes generic APIStatusError is raised with status_code=400
        # carrying a billing message — same logic as above.
        if status == 400:
            msg = (str(err) or "").lower()
            if any(needle in msg for needle in _BILLING_NEEDLES):
                return True
        return False

    return False


def _call_claude_with_gemini_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str,
    cache: bool,
    enable_thinking: bool,
    thinking_budget: int,
):
    """Single point where the LLM is called.

    When DeepSeek is primary (LLM_PROVIDER=deepseek), short-circuits the
    Anthropic-retry path entirely — call_claude_cached internally handles
    DeepSeek → Groq fallback, no need for additional retry layers here.

    When Anthropic is primary, retries transient failures up to twice with
    exponential backoff. call_claude_cached itself falls through to DeepSeek
    → Groq on Anthropic credit failures.

    Strategy on transient failure (rate-limit / 5xx / connection blip):
      1. Up to 2 retries with exponential backoff (Anthropic 429s usually
         clear in 5-15s for tier 1 accounts).
      2. call_claude_cached takes over for credit-balance errors by
         routing to DeepSeek → Groq automatically.
    """
    import os
    import time as _time
    from headnote.llm.client import _deepseek_primary

    # PATH A: DeepSeek primary — single call, no anthropic-retry. DeepSeek's
    # SDK has 180s timeout; Groq fallback inside call_claude_cached handles
    # any DeepSeek failure.
    if _deepseek_primary():
        return call_claude_cached(
            system_prompt, user_prompt,
            model=model, cache=cache,
            enable_thinking=enable_thinking,
            thinking_budget=thinking_budget,
        )

    # PATH B: Anthropic primary with retry-on-transient
    last_exc: Optional[Exception] = None
    backoff_seconds = (2.0, 6.0)  # two retries spaced at 2s and 6s
    for attempt in range(len(backoff_seconds) + 1):
        try:
            return call_claude_cached(
                system_prompt, user_prompt,
                model=model, cache=cache,
                enable_thinking=enable_thinking,
                thinking_budget=thinking_budget,
            )
        except Exception as e:
            last_exc = e
            if not _is_anthropic_transient_error(e):
                raise
            if attempt >= len(backoff_seconds):
                break  # retries exhausted
            sleep_s = backoff_seconds[attempt]
            log.warning(
                "Anthropic transient error (%s); retry %d/%d in %.1fs",
                type(e).__name__, attempt + 1, len(backoff_seconds), sleep_s,
            )
            _time.sleep(sleep_s)

    raise last_exc


log = logging.getLogger(__name__)

# ----------------------------------------------------------------- types

TaskType = Literal[
    "translation",   # English ↔ Hindi prose, citations preserved
    "verification",  # claim/evidence Y/N, structural checks
    "extraction",    # statute/section/topic extraction from raw text
    "situation",     # lawyer's situation → ranked precedents w/ headnotes
    "digest",        # doctrinal topic → topical case digest
    "rerank",        # candidate cases → score-sorted list
    "headnote",      # full judgment → Cri.L.J. headnotes (the moat)
]


class RouteResult(NamedTuple):
    """Result of a single `route_call`.

    Unpacks as a 4-tuple `(model_name, response, cost_paise, confidence_score)`
    per the spec, with named-attribute access for callers who want clarity.

    `cost_paise` is the **total** spend on this call, including any retry —
    if Sonnet returned low confidence and the router upgraded to Opus, both
    costs are summed here. Individual costs are also logged at INFO level.
    """
    model_name: str
    response: str
    cost_paise: int
    confidence_score: Optional[int]


# ----------------------------------------------------------------- models

# Short, stable model IDs (match `config.DEFAULT_MODEL` convention).
HAIKU_MODEL = "claude-haiku-4-5"
SONNET_MODEL = "claude-sonnet-4-6"
OPUS_MODEL = "claude-opus-4-7"  # 4-6 never shipped; current Opus is 4-7

_MODEL_ALIASES: dict[str, str] = {
    "haiku":  HAIKU_MODEL,
    "sonnet": SONNET_MODEL,
    "opus":   OPUS_MODEL,
}

# Task → default model (overridable via `force_model`).
# Sonnet 4.6 + extended thinking handles every generation task at world-class
# quality. Opus was here historically for `headnote` (case-summary synthesis)
# but adds ~4× cost without measurable quality gain — Sonnet matched it on
# our 42-case regression set. Keep OPUS_MODEL reachable via force_model="opus".
#
# Task → model routing.
#
# When LLM_PROVIDER=deepseek (current production state), the model names
# get rewritten in client.py:
#   SONNET_MODEL → deepseek-reasoner (R1) — chain-of-thought, slow (60-120s)
#   HAIKU_MODEL  → deepseek-chat (V3) — fast (5-15s), still high quality
#
# Light tasks (translation/verification/extraction/situation_main) use
# V3 because:
#   1. Speed — V3 is 3-4× faster than R1 for the same input
#   2. The full pipeline runs 5+ LLM calls in sequence. With R1 at each
#      stage we'd hit 5+ min total; with V3 we get ~40-70s total.
#   3. Quality on legal JSON extraction is comparable — R1's chain-of-
#      thought helps math/coding tasks more than structured legal output.
#
# Heavy tasks (headnote generation, deep_mode situation) keep R1 because
# the depth of reasoning genuinely shows in the output quality.
_ROUTING: dict[str, str] = {
    "translation":  HAIKU_MODEL,    # V3 — fast prose translation
    "verification": HAIKU_MODEL,    # V3 — yes/no claim checks
    "extraction":   HAIKU_MODEL,    # V3 — pull statutes/parties from text
    "situation":    HAIKU_MODEL,    # V3 — ranks 20→5 candidates; speed > depth
    "digest":       HAIKU_MODEL,    # V3 — topical case digest
    "rerank":       HAIKU_MODEL,    # V3 — final reorder pass
    "headnote":     SONNET_MODEL,   # R1 — Cri.L.J.-grade headnote from full judgment
}

# Tasks that require a quality answer the user will read directly.
# Only these get the confidence prompt + potential Sonnet→Opus retry.
_GENERATION_TASKS: set[str] = {"situation", "digest", "headnote"}

# Below this score, auto-upgrade Sonnet → Opus for generation tasks.
CONFIDENCE_RETRY_THRESHOLD = 7


# ----------------------------------------------------------------- pricing

# Per-million-token rates. Pulled from `headnote.config` so updating prices
# only needs one edit. Cache tiers preserved per the "keep caching enabled"
# constraint.
_PRICING_BY_MODEL: dict[str, dict[str, float]] = {
    HAIKU_MODEL:  config.PRICE_HAIKU,
    SONNET_MODEL: config.PRICE_SONNET,
    OPUS_MODEL:   config.PRICE_OPUS,
}


def _pricing_for(model: str) -> dict[str, float]:
    """Pick the pricing tier that matches a model id. Falls back to substring
    match (e.g. `claude-opus-4-7` matches Opus pricing) and finally to Opus
    so we don't undercount when a new model lands."""
    if model in _PRICING_BY_MODEL:
        return _PRICING_BY_MODEL[model]
    m = model.lower()
    if "haiku" in m:
        return config.PRICE_HAIKU
    if "sonnet" in m:
        return config.PRICE_SONNET
    return config.PRICE_OPUS


def build_router_meta(result: "RouteResult", elapsed_seconds: float) -> dict:
    """Build the meta block FastAPI endpoints return alongside the response.

    Replaces the old `headnote.llm.client.build_meta` for endpoints that go
    through the router. Includes the routing decision (`model`), cost in
    paise (the primary cost unit), USD/INR derived for frontend backward
    compatibility, and the confidence score for the UI badge.

    Token-level fields are deliberately omitted — the router abstracts away
    the per-call token mechanics. If you need them for debugging, set the
    log level to INFO and `route_call` will emit per-call token counts.
    """
    paise = result.cost_paise
    cost_inr = paise / 100
    cost_usd = cost_inr / config.USD_TO_INR
    return {
        "elapsed_seconds": round(elapsed_seconds, 2),
        "model": result.model_name,
        "cost_paise": paise,
        "cost_inr": round(cost_inr, 4),
        "cost_usd": round(cost_usd, 6),
        "confidence_score": result.confidence_score,
    }


def calculate_cost_paise(usage: dict, model: str) -> int:
    """Cost in paise (1 paise = ₹0.01) for a single Anthropic call.

    Reads input/output/cache_creation/cache_read token counts from the
    usage dict returned by `call_claude_cached`. Multiplies by per-model
    per-million rates, converts USD → INR at `config.USD_TO_INR`, and
    rounds to the nearest paise.
    """
    p = _pricing_for(model)
    cost_usd = (
        usage.get("input_tokens", 0) * p["input"] / 1_000_000
        + usage.get("output_tokens", 0) * p["output"] / 1_000_000
        + usage.get("cache_creation_input_tokens", 0) * p["input_cache_write"] / 1_000_000
        + usage.get("cache_read_input_tokens", 0) * p["input_cache_read"] / 1_000_000
    )
    return round(cost_usd * config.USD_TO_INR * 100)


# ------------------------------------------------------- confidence parsing

# The confidence suffix appended to user prompts for generation tasks.
# Verbatim per spec, with two minor robustness tweaks: a hard `\n\n`
# separator so the line is clearly distinct, and explicit phrasing that
# this is the FINAL line (helps when the response is JSON).
CONFIDENCE_PROMPT_SUFFIX = (
    "\n\nAfter your answer, on a new line, output: "
    "CONFIDENCE: <integer 1-10> based on how certain you are this output "
    "is accurate and high-quality."
)

# Anchored to end of response (after rstrip) so we don't false-positive on
# "CONFIDENCE" appearing inside a JSON value. Requires a newline before
# CONFIDENCE; the line content is `CONFIDENCE: <int>` optionally followed
# by trailing whitespace, then end of text.
_CONFIDENCE_RX = re.compile(
    r"\n\s*CONFIDENCE:\s*(\d{1,2})\s*$",
    re.IGNORECASE,
)


def parse_and_strip_confidence(text: str) -> tuple[str, Optional[int]]:
    """Pull `CONFIDENCE: <n>` off the end of a model response.

    Returns `(stripped_text, score)`. If no score is found, the score is
    invalid (outside 1-10), or the line isn't at the end, returns
    `(original_text, None)` — the response is left untouched and no retry
    is triggered upstream.
    """
    trimmed = text.rstrip()
    m = _CONFIDENCE_RX.search(trimmed)
    if not m:
        return text, None
    try:
        score = int(m.group(1))
    except ValueError:
        return text, None
    if not 1 <= score <= 10:
        return text, None
    stripped = trimmed[: m.start()].rstrip()
    return stripped, score


# ----------------------------------------------------------------- routing

def _resolve_force_model(force: Optional[str]) -> Optional[str]:
    """Translate `haiku|sonnet|opus` shortcuts to full model ids.

    Accepts a full Anthropic model id passthrough (anything starting with
    `claude-`). Raises ValueError for unrecognised inputs so typos surface
    as 5xx, not as silent fallthrough to a different model.
    """
    if force is None:
        return None
    key = force.strip().lower()
    if key in _MODEL_ALIASES:
        return _MODEL_ALIASES[key]
    if key.startswith("claude-"):
        return force
    raise ValueError(
        f"force_model={force!r} not recognised. Use 'haiku' | 'sonnet' | 'opus' "
        f"or a full Anthropic model id starting with 'claude-'."
    )


def _select_model(task_type: str, force_model: Optional[str]) -> str:
    forced = _resolve_force_model(force_model)
    if forced is not None:
        return forced
    try:
        return _ROUTING[task_type]
    except KeyError as e:
        raise ValueError(
            f"Unknown task_type={task_type!r}. Valid: {sorted(_ROUTING)}"
        ) from e


def _should_retry_with_opus(
    *,
    model: str,
    confidence: Optional[int],
    task_type: str,
    force_model: Optional[str],
) -> bool:
    """The narrow conditions under which we auto-upgrade Sonnet → Opus.

    Defaults to False — Sonnet 4.6 with 5K thinking tokens delivers
    world-class four-dimension scoring. Flip config.ENABLE_OPUS_ESCALATION
    to re-enable the retry for power-user debugging.

    When enabled, the retry fires iff ALL hold:
      - global escalation flag is on
      - the call ran on Sonnet
      - the task is a generation task (situation/digest/headnote)
      - the model returned a parseable confidence < 7
      - the caller did NOT force a model (force respects user intent)
    """
    if not config.ENABLE_OPUS_ESCALATION:
        return False
    if force_model is not None:
        return False
    if model != SONNET_MODEL:
        return False
    if task_type not in _GENERATION_TASKS:
        return False
    if confidence is None:
        return False
    return confidence < CONFIDENCE_RETRY_THRESHOLD


# ----------------------------------------------------------------- main API

def route_call(
    task_type: TaskType,
    payload: dict,
    force_model: Optional[str] = None,
) -> RouteResult:
    """Make a single Claude call with smart model selection.

    Arguments:
      task_type: one of the seven TaskType values. Determines the default model.
      payload:   dict with at least `system_prompt` and `user_prompt` strings.
                 Optional `cache` (bool, default True) controls prompt caching
                 on the system block.
      force_model: optional override. Accepts `"haiku" | "sonnet" | "opus"`
                 (short aliases) or a full Anthropic model id starting with
                 `claude-`. When set, disables the auto-upgrade retry.

    Returns:
      RouteResult NamedTuple — unpacks as
      `(model_name, response, cost_paise, confidence_score)`.

    Behaviour notes:
      - Generation tasks (situation/digest/headnote) get a confidence prompt
        appended. The score is parsed from the response and stripped.
      - If a Sonnet generation call returns confidence < 7 and no model was
        forced, the same call is re-issued with Opus. The Opus response is
        returned as the final result; `cost_paise` is the sum.
      - Network/API errors bubble up unchanged.
    """
    system_prompt = payload["system_prompt"]
    user_prompt = payload["user_prompt"]
    use_cache = bool(payload.get("cache", True))
    enable_thinking = bool(payload.get("enable_thinking", False))
    thinking_budget = int(payload.get("thinking_budget", 3000))

    model = _select_model(task_type, force_model)
    is_generation = task_type in _GENERATION_TASKS

    # Confidence prompt is appended to the USER prompt (not system) so the
    # system-prompt cache key doesn't drift across calls and we keep cache hits.
    # Skip the confidence prompt when extended thinking is enabled — the
    # model's reasoning is already happening in the thinking block, no need
    # to also force a "CONFIDENCE: N" suffix that has been observed to
    # interfere with the model's JSON output discipline.
    augmented_user_prompt = user_prompt
    if is_generation and not enable_thinking:
        augmented_user_prompt = user_prompt + CONFIDENCE_PROMPT_SUFFIX

    log.info("route_call task=%s model=%s force=%s thinking=%s",
             task_type, model, force_model, enable_thinking)

    raw, usage = _call_claude_with_gemini_fallback(
        system_prompt,
        augmented_user_prompt,
        model=model,
        cache=use_cache,
        enable_thinking=enable_thinking,
        thinking_budget=thinking_budget,
    )
    first_cost = calculate_cost_paise(usage, model)

    response_text = raw
    confidence: Optional[int] = None
    if is_generation:
        response_text, confidence = parse_and_strip_confidence(raw)
        if confidence is None:
            log.warning(
                "route_call task=%s model=%s: no parseable confidence (response %d chars)",
                task_type, model, len(raw),
            )

    if not _should_retry_with_opus(
        model=model, confidence=confidence,
        task_type=task_type, force_model=force_model,
    ):
        return RouteResult(
            model_name=model,
            response=response_text,
            cost_paise=first_cost,
            confidence_score=confidence,
        )

    # Sonnet returned low confidence → re-issue with Opus.
    log.info(
        "route_call task=%s: Sonnet confidence=%s < %s, upgrading to Opus",
        task_type, confidence, CONFIDENCE_RETRY_THRESHOLD,
    )
    raw_opus, usage_opus = _call_claude_with_gemini_fallback(
        system_prompt,
        augmented_user_prompt,
        model=OPUS_MODEL,
        cache=use_cache,
        enable_thinking=False,
        thinking_budget=0,
    )
    second_cost = calculate_cost_paise(usage_opus, OPUS_MODEL)
    opus_response, opus_confidence = parse_and_strip_confidence(raw_opus)

    total_cost = first_cost + second_cost
    log.info(
        "route_call retry breakdown: sonnet=%d paise, opus=%d paise, total=%d paise",
        first_cost, second_cost, total_cost,
    )

    return RouteResult(
        model_name=OPUS_MODEL,
        response=opus_response,
        cost_paise=total_cost,
        confidence_score=opus_confidence,
    )


# ----------------------------------------------------------------- demo

# Representative payloads — small enough to keep total demo cost under ~₹5.
_DEMO_PAYLOADS: dict[str, dict[str, str]] = {
    "translation": {
        "system_prompt": (
            "You translate Indian legal text from English to Hindi. "
            "Preserve all citations, section numbers, and case names "
            "character-for-character in English."
        ),
        "user_prompt": (
            "Translate the following to Hindi: \"Held — the offence under "
            "S. 138 NI Act is constituted only when the drawee bank "
            "dishonours the cheque.\""
        ),
    },
    "verification": {
        "system_prompt": (
            "Given a claim and source evidence, reply with a single token: "
            "YES if the evidence supports the claim verbatim, NO otherwise."
        ),
        "user_prompt": (
            "Claim: K. Bhaskaran was decided by K.T. Thomas and M. Srinivasan, JJ.\n"
            "Evidence: 'K. Bhaskaran v. Sankaran Vaidhyan Balan, decided by "
            "K.T. Thomas, J. and M. Srinivasan, J. on 29 September 1999.'"
        ),
    },
    "extraction": {
        "system_prompt": (
            "Extract statute and section references from the text. Output a "
            "JSON array of strings, each in the format "
            "'<Act name>, <year>, S. <number>'."
        ),
        "user_prompt": (
            "The accused was charged under Section 138 of the Negotiable "
            "Instruments Act, 1881 and Section 420 of the Indian Penal "
            "Code, 1860."
        ),
    },
    "rerank": {
        "system_prompt": (
            "Re-rank these case candidates by relevance to the query. "
            "Output a JSON array of objects with keys `id` and `score` "
            "(0.0-1.0). Highest score first."
        ),
        "user_prompt": (
            "Query: PMLA twin conditions for bail.\n"
            "Candidates: ["
            "{\"id\":\"A\",\"title\":\"Vijay Madanlal Choudhary v. Union of India\"},"
            "{\"id\":\"B\",\"title\":\"Some unrelated income-tax case\"}]"
        ),
    },
    "situation": {
        "system_prompt": (
            "You are a legal research assistant. For the lawyer's situation, "
            "name 2 illustrative landmark precedents (you may use general "
            "knowledge for this demo). Output JSON: "
            '{"cases": [{"title": str, "ratio": str}]}.'
        ),
        "user_prompt": (
            "Situation: A cheque was dishonoured in Mumbai. The complainant "
            "filed the complaint in Delhi where he received the cheque. "
            "What are the territorial-jurisdiction precedents?"
        ),
    },
    "digest": {
        "system_prompt": (
            "Produce a topical digest. Output JSON: "
            '{"topic": str, "sub_topics": [{"heading": str, "cases": [{"title": str}]}]}.'
        ),
        "user_prompt": "Topic: Five golden principles of circumstantial evidence in Indian criminal law.",
    },
    "headnote": {
        "system_prompt": (
            "Produce a Cri.L.J.-format headnote. Output JSON: "
            '{"statute_index": str, "catchword_chain": str, "ratio": str, '
            '"paragraph_anchor": str}.'
        ),
        "user_prompt": (
            "Judgment (excerpt):\n"
            "1. The appellant was charged under S. 138 NI Act for a cheque "
            "that bounced.\n"
            "14. Held — the offence under S. 138 is constituted only at "
            "the place where the drawee bank dishonours the cheque. The "
            "place of presentation by the payee is not relevant to "
            "territorial jurisdiction."
        ),
    },
}


def _run_demo() -> None:
    """Run one call per task type, printing routing + cost telemetry.

    Real API calls — requires `ANTHROPIC_API_KEY` in the environment.
    Total cost roughly ₹3-7 depending on whether confidence retry fires.
    """
    import os
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit(
            "ANTHROPIC_API_KEY not set. Add it to .env or export before running this demo."
        )

    print(f"{'task':<14} {'model':<22} {'paise':>7}  {'conf':>4}  response preview")
    print("-" * 92)
    total_paise = 0
    for task in ["translation", "verification", "extraction", "rerank",
                 "situation", "digest", "headnote"]:
        try:
            result = route_call(task, _DEMO_PAYLOADS[task])
        except Exception as e:
            print(f"{task:<14} ERROR: {e}")
            continue
        total_paise += result.cost_paise
        preview = (result.response[:60] + "…") if len(result.response) > 60 else result.response
        preview = preview.replace("\n", " ")
        conf = "—" if result.confidence_score is None else str(result.confidence_score)
        print(f"{task:<14} {result.model_name:<22} {result.cost_paise:>7}  {conf:>4}  {preview}")
    print("-" * 92)
    print(f"{'TOTAL':<14} {'':<22} {total_paise:>7}  paise  (~₹{total_paise / 100:.2f})")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    _run_demo()
