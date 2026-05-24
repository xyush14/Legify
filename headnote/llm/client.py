"""Anthropic Claude wrapper: a single typed entrypoint with prompt caching,
JSON-response parsing, and a cost meter. Pricing constants live in
headnote.config so they can be tuned without editing this module.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Tuple

from anthropic import Anthropic
from fastapi import HTTPException

from headnote import config

log = logging.getLogger(__name__)

# Use Bedrock only when BOTH AWS credentials AND an explicit opt-in are set.
# This prevents accidental Bedrock activation when AWS keys are present for
# other services (S3, etc.) but no Marketplace subscription is configured.
# To enable Bedrock, set USE_BEDROCK=true in addition to AWS_ACCESS_KEY_ID.
_USE_BEDROCK = (
    bool(os.environ.get("AWS_ACCESS_KEY_ID"))
    and os.environ.get("USE_BEDROCK", "").lower() in {"1", "true", "yes"}
)

# Internal model name → Bedrock cross-region inference profile ID.
# Override in Railway env vars without a code deploy:
#   BEDROCK_HAIKU_ID, BEDROCK_SONNET_ID, BEDROCK_OPUS_ID
_BEDROCK_IDS: dict[str, str] = {
    "claude-haiku-4-5":  os.environ.get("BEDROCK_HAIKU_ID",  "us.anthropic.claude-haiku-4-5"),
    "claude-sonnet-4-6": os.environ.get("BEDROCK_SONNET_ID", "us.anthropic.claude-sonnet-4-6"),
    "claude-opus-4-7":   os.environ.get("BEDROCK_OPUS_ID",   "us.anthropic.claude-opus-4-7"),
}


def _to_bedrock_id(model: str) -> str:
    return _BEDROCK_IDS.get(model, model)


def _to_canonical_model(bedrock_id: str) -> str:
    """Reverse-map a Bedrock model ID back to the canonical internal name."""
    reverse = {v: k for k, v in _BEDROCK_IDS.items()}
    return reverse.get(bedrock_id, config.DEFAULT_MODEL)


def _is_bedrock_recoverable_error(exc: Exception) -> bool:
    """Errors where falling back to direct Anthropic API is the right move:
    - 403 payment / Marketplace subscription issues
    - 400 invalid model identifier (Bedrock model IDs change/expire)
    - PermissionDenied / AccessDenied on the IAM role
    """
    s = str(exc)
    return any(k in s for k in (
        "INVALID_PAYMENT_INSTRUMENT",
        "payment_instrument",
        "valid payment",
        "PermissionDenied",
        "AccessDeniedException",
        "subscription",
        "Marketplace subscription",
        "provided model identifier is invalid",
        "model identifier",
        "ValidationException",
        "model not found",
        "Could not find model",
    )) or any(code in s for code in ("403 ", "404 ", "400 - {'message'"))


def _is_anthropic_no_credit_error(exc: Exception) -> bool:
    """Direct Anthropic call failed because the account has no balance.
    Recoverable via Groq fallback (cheaper, no payment required)."""
    s = str(exc).lower()
    return any(k in s for k in (
        "credit balance is too low",
        "credit balance",
        "insufficient credit",
        "out of credits",
        "billing",
        "your account does not have",
    ))


def _call_groq_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
) -> Tuple[str, dict]:
    """Last-resort fallback to Groq's free-tier Llama-3.3-70B when both
    Bedrock and direct Anthropic fail. Quality is lower than Sonnet for
    legal reasoning, but works without any payment dependency.

    Uses GROQ_API_KEY env var (already configured for OCR/drafter paths).
    Returns the same (response_text, usage_dict) shape as the Anthropic path
    so callers don't need to special-case the source.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. Set GROQ_API_KEY on Railway to enable the free fallback path.",
        )
    try:
        from groq import Groq
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"groq SDK not installed on this deploy: {e}",
        ) from e

    model = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
    log.warning("[llm] Falling back to Groq %s (Bedrock + Anthropic both failed)", model)

    client = Groq(api_key=groq_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=min(max_tokens or 4000, 8000),  # Groq caps lower than Anthropic
        temperature=0.2,
        timeout=60.0,
    )
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    return text, {
        "model": f"groq:{model}",
        "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def get_client():
    """Return AnthropicBedrock when AWS creds are present, else direct Anthropic."""
    if _USE_BEDROCK:
        from anthropic import AnthropicBedrock
        return AnthropicBedrock(
            aws_region=os.environ.get("AWS_REGION", "us-east-1"),
        )
    if not config.ANTHROPIC_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="ANTHROPIC_API_KEY is not configured on the server.",
        )
    return Anthropic(api_key=config.ANTHROPIC_API_KEY)


def call_claude_cached(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str = "",
    max_tokens: int = 0,
    cache: bool = True,
    enable_thinking: bool = False,
    thinking_budget: int = 3000,
) -> Tuple[str, dict]:
    """Send a single user message with `system_prompt` optionally cached.

    Returns (response_text, usage_dict). usage_dict has input/output/cache token
    counts; pass it to `estimate_cost_usd()` for the meter.

    Extended thinking
    -----------------
    When `enable_thinking=True`, the model gets a dedicated scratch space
    (`thinking_budget` tokens) for chain-of-thought BEFORE producing its
    JSON output. The thinking blocks are stripped from the response — the
    caller sees only the final text. Thinking tokens are billed as output.

    For the SITUATION endpoint, thinking is what gives the model room to
    actually execute the four-dimension scoring rubric (fact-archetype /
    doctrinal / outcome / authority) on every corpus case before writing
    the final JSON. Without thinking, the model has to interleave the
    reasoning with the structured output, which degrades both.

    Supported on Sonnet 4 / Opus 4 model families (claude-sonnet-4-*,
    claude-opus-4-*). Haiku 4.5 does not support extended thinking.
    When thinking is enabled, temperature is forced to 1.0 (Anthropic
    requirement).
    """
    model = model or config.DEFAULT_MODEL
    if _USE_BEDROCK:
        model = _to_bedrock_id(model)
        enable_thinking = False  # older Bedrock model IDs don't support extended thinking
    max_tokens = max_tokens or config.MAX_TOKENS
    client = get_client()
    if cache:
        system = [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system = system_prompt

    # Per-model timeouts prevent indefinite hangs but allow real-world latency.
    # Sonnet with 3500 thinking tokens + IK doc fetches + heavy system prompt
    # legitimately runs 30-90s on cold cache; 150s gives headroom for the
    # 99th-percentile case while still failing fast on genuine hangs.
    if "haiku" in model.lower():
        _timeout = 45.0
    elif "sonnet" in model.lower():
        _timeout = 150.0
    else:
        _timeout = 180.0

    create_kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
        timeout=_timeout,
    )

    if enable_thinking and "haiku" not in model.lower():
        # max_tokens must be greater than thinking budget — bump if needed
        if max_tokens <= thinking_budget:
            create_kwargs["max_tokens"] = thinking_budget + 2000
        create_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }
        create_kwargs["temperature"] = 1.0   # Required by API when thinking is on

    try:
        resp = client.messages.create(**create_kwargs)
    except Exception as exc:
        # Bedrock failure (payment / invalid model / IAM) → transparent fallback
        # to direct Anthropic API. Covers the common Railway misconfigurations.
        if _USE_BEDROCK and _is_bedrock_recoverable_error(exc):
            canonical = _to_canonical_model(create_kwargs["model"])
            log.warning(
                "Bedrock error — falling back to direct Anthropic API "
                "(bedrock_model=%s → anthropic_model=%s): %s",
                create_kwargs.get("model"), canonical, str(exc)[:250]
            )
            # Try Anthropic if we have a key, else go straight to Groq.
            if config.ANTHROPIC_API_KEY:
                try:
                    fallback_client = Anthropic(api_key=config.ANTHROPIC_API_KEY)
                    create_kwargs["model"] = canonical
                    resp = fallback_client.messages.create(**create_kwargs)
                except Exception as anth_exc:
                    # Anthropic also failed (out of credits, etc.) → final
                    # fallback to Groq's free tier. Quality drop but reliable.
                    if _is_anthropic_no_credit_error(anth_exc):
                        log.warning(
                            "Anthropic also failed (no credit) — falling back to Groq: %s",
                            str(anth_exc)[:200],
                        )
                        return _call_groq_fallback(
                            system_prompt, user_prompt,
                            max_tokens=create_kwargs.get("max_tokens", 4000),
                        )
                    raise
            else:
                # No Anthropic key at all — go straight to Groq
                return _call_groq_fallback(
                    system_prompt, user_prompt,
                    max_tokens=create_kwargs.get("max_tokens", 4000),
                )
        else:
            raise
    usage = resp.usage
    usage_dict = {
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }

    # When thinking is on, response.content may include thinking blocks
    # BEFORE the text blocks. Concatenate only the text blocks for the
    # caller — the thinking is internal scratch space.
    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    response_text = "\n".join(text_blocks) if text_blocks else (
        resp.content[0].text if resp.content else ""
    )
    return response_text, usage_dict


def estimate_cost_usd(usage: dict) -> float:
    """Estimate USD cost from a Claude usage dict, using model-specific pricing."""
    model = (usage.get("model") or "").lower()
    if "haiku" in model:
        pricing = config.PRICE_HAIKU
    elif "sonnet" in model:
        pricing = config.PRICE_SONNET
    else:
        pricing = config.PRICE_OPUS
    return (
        usage.get("input_tokens", 0) * pricing["input"] / 1_000_000
        + usage.get("cache_creation_input_tokens", 0) * pricing["input_cache_write"] / 1_000_000
        + usage.get("cache_read_input_tokens", 0) * pricing["input_cache_read"] / 1_000_000
        + usage.get("output_tokens", 0) * pricing["output"] / 1_000_000
    )


def parse_json_response(raw: str) -> dict:
    """Parse Claude's response as JSON, tolerating ```json fences. Raises
    HTTPException(502) if the response is not parseable JSON."""
    text = raw.strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Model returned invalid JSON: {e}. Raw start: {text[:200]}",
        )


def build_meta(usage: dict, elapsed: float) -> dict:
    """Build the per-response meta block (cost meter + token counts)."""
    cost_usd = estimate_cost_usd(usage)
    return {
        "elapsed_seconds": round(elapsed, 2),
        "model": usage.get("model"),
        "input_tokens": usage.get("input_tokens", 0),
        "output_tokens": usage.get("output_tokens", 0),
        "cache_read_input_tokens": usage.get("cache_read_input_tokens", 0),
        "cache_creation_input_tokens": usage.get("cache_creation_input_tokens", 0),
        "cost_usd": round(cost_usd, 6),
        "cost_inr": round(cost_usd * config.USD_TO_INR, 4),
    }
