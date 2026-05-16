"""Anthropic Claude wrapper: a single typed entrypoint with prompt caching,
JSON-response parsing, and a cost meter. Pricing constants live in
headnote.config so they can be tuned without editing this module.
"""

from __future__ import annotations

import json
from typing import Any, Tuple

from anthropic import Anthropic
from fastapi import HTTPException

from headnote import config


def get_client() -> Anthropic:
    """Construct an Anthropic client from the configured key. Raises a 500
    HTTPException at request time if the key is missing — avoids crashing
    the whole app on startup when only some endpoints need Claude."""
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
) -> Tuple[str, dict]:
    """Send a single user message with `system_prompt` optionally cached.

    Returns (response_text, usage_dict). usage_dict has input/output/cache token
    counts; pass it to `estimate_cost_usd()` for the meter.
    """
    model = model or config.DEFAULT_MODEL
    max_tokens = max_tokens or config.MAX_TOKENS
    client = get_client()
    if cache:
        system = [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system = system_prompt

    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    usage = resp.usage
    usage_dict = {
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }
    return resp.content[0].text, usage_dict


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
