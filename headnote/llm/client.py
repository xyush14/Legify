"""Anthropic Claude wrapper: a single typed entrypoint with prompt caching,
JSON-response parsing, and a cost meter. Pricing constants live in
headnote.config so they can be tuned without editing this module.
"""

from __future__ import annotations

import json
import os
from typing import Any, Tuple

from anthropic import Anthropic
from fastapi import HTTPException

from headnote import config


# Use Bedrock when AWS credentials are present (free with AWS credits).
_USE_BEDROCK = bool(os.environ.get("AWS_ACCESS_KEY_ID"))

# Internal model name → Bedrock cross-region inference profile ID (us-east-1).
# Override any of these in Railway env vars without a code deploy:
#   BEDROCK_HAIKU_ID, BEDROCK_SONNET_ID, BEDROCK_OPUS_ID
_BEDROCK_IDS: dict[str, str] = {
    "claude-haiku-4-5":  os.environ.get("BEDROCK_HAIKU_ID",  "anthropic.claude-haiku-4-5"),
    "claude-sonnet-4-6": os.environ.get("BEDROCK_SONNET_ID", "anthropic.claude-sonnet-4-6"),
    "claude-opus-4-6":   os.environ.get("BEDROCK_OPUS_ID",   "anthropic.claude-opus-4-6"),
}


def _to_bedrock_id(model: str) -> str:
    return _BEDROCK_IDS.get(model, model)


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

    create_kwargs = dict(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
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

    resp = client.messages.create(**create_kwargs)
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
