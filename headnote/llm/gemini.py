"""
Gemini fallback for Anthropic call failures.

When does this fire?
--------------------
The wrapper in router.py catches:
  - anthropic.RateLimitError (429)
  - anthropic.APIStatusError where status == 529 (overloaded)
  - anthropic.InternalServerError (5xx)
  - anthropic.APIConnectionError (network blip)

…and falls back to Gemini with the same prompts. The fallback exists so a
single Anthropic outage or rate-limit doesn't take Headnote down at 11pm
on a Sunday when the founder can't intervene. It is NOT meant as a
permanent cost-saving tactic — Gemini's quality on Indian legal prose is
weaker than Sonnet, and the verifier downstream will drop most cases the
model hallucinates.

Free tier ceiling
-----------------
Gemini 2.0 Flash free tier: 15 req/min, 1500 req/day, no cost. Enough for
the rare-spike fallback case but a hard ceiling on sustained traffic. If
Headnote ever sees > 1500 fallback calls/day we have bigger problems
(Anthropic deeply broken) — degrade to a 'service degraded, try again
soon' banner rather than burning through a paid tier silently.

Module is a soft dependency: if google-genai isn't installed (e.g. on
older requirements.txt deploys), call_gemini raises a clean
RuntimeError and the caller falls through to its own error path.

Setup
-----
  1. Get an API key at https://aistudio.google.com/apikey
  2. Set GEMINI_API_KEY in the Railway Variables tab (or .env locally)
  3. Add `google-genai>=0.3` to requirements.txt
  4. Redeploy

Without the key, the wrapper silently no-ops and Anthropic errors bubble
up unchanged — exactly the behaviour before this module existed.
"""

from __future__ import annotations

import logging
import os
from typing import Tuple

log = logging.getLogger(__name__)


# Use Flash (cheapest + fastest) by default. Operators can override to
# gemini-2.5-pro for better quality at higher rate-limit risk.
DEFAULT_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")


def _is_configured() -> bool:
    """True when both the API key is set and google-genai is importable.

    We don't import google-genai at module load — that adds ~200ms to
    every cold start even when fallback never fires. Lazy-import inside
    call_gemini() instead.
    """
    if not os.environ.get("GEMINI_API_KEY"):
        return False
    try:
        import google.genai  # noqa: F401
    except ImportError:
        return False
    return True


def call_gemini(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = "",
    max_tokens: int = 4000,
) -> Tuple[str, dict]:
    """Match call_claude_cached's signature so route_call can drop us in
    as a fallback.

    Differences worth noting (we paper over them, but they exist):
      - No prompt caching (Gemini's caching API is different).
      - No extended thinking (Gemini doesn't expose one).
      - The system + user prompts are concatenated; Gemini's GenerationConfig
        does have a 'system_instruction' field on the new SDK but the
        contract is subtly different, so we play it safe.
      - Token-usage counts have different field names; we normalise to
        the Anthropic shape so the existing cost-meter doesn't break,
        though cost_paise computation against Anthropic pricing tables
        will be wrong by definition (we mark these calls explicitly).
    """
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("GEMINI_API_KEY not configured; cannot fallback to Gemini.")

    try:
        from google import genai
        from google.genai import types
    except ImportError as e:
        raise RuntimeError(
            "google-genai not installed; add `google-genai>=0.3` to "
            "requirements.txt and redeploy. Falling back is disabled."
        ) from e

    chosen_model = model or DEFAULT_GEMINI_MODEL
    log.warning("Gemini fallback firing: model=%s prompt_len=%d",
                chosen_model, len(system_prompt) + len(user_prompt))

    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    # Compose the prompt. Gemini's chat model expects a list of Content
    # objects but for our single-turn case we can pass a flat string.
    combined = f"{system_prompt}\n\n----\n\n{user_prompt}"

    resp = client.models.generate_content(
        model=chosen_model,
        contents=combined,
        config=types.GenerateContentConfig(
            max_output_tokens=max_tokens,
            # Lower temperature than the model's default — legal drafting
            # benefits from consistency, and we're already only firing
            # this when Anthropic is unavailable.
            temperature=0.3,
        ),
    )

    text = (resp.text or "").strip()

    # Normalise usage to the Anthropic shape so build_meta / cost_paise
    # callers don't crash. The fields below come from GenerateContentResponse
    # in google-genai >= 0.3; defensively .get() everything.
    usage_meta = getattr(resp, "usage_metadata", None)
    input_tokens = getattr(usage_meta, "prompt_token_count", 0) or 0
    output_tokens = getattr(usage_meta, "candidates_token_count", 0) or 0
    return text, {
        "model": f"gemini::{chosen_model}",
        "input_tokens": int(input_tokens),
        "output_tokens": int(output_tokens),
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
        # Flag so downstream cost meter shows "Gemini fallback" not
        # Anthropic pricing.
        "fallback_provider": "gemini",
    }
