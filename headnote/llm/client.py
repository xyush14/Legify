"""LLM client wrapper with multi-provider fallback chain.

Active providers:
  1. Anthropic Claude (primary when ANTHROPIC_API_KEY has balance)
  2. DeepSeek (primary alternate when LLM_PROVIDER=deepseek, or auto-fallback
     when Anthropic is out of credits; OpenAI-compatible API at api.deepseek.com)
  3. Groq Llama-3.3-70B (free-tier last resort)

DeepSeek model routing:
  - "deep" tasks (research, headnote generation, memorandum) → deepseek-reasoner (R1)
  - "fast" tasks (translation, verification, extraction) → deepseek-chat (V3)

Bedrock has been removed — Marketplace subscription issues made it unreliable.
If/when Bedrock is fixed in the future, restore the AnthropicBedrock branch
in get_client() and the _to_bedrock_id() mapping.
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


# Provider toggle:
#   "anthropic" (default): use Claude when ANTHROPIC_API_KEY is set, fall through
#                          to DeepSeek → Groq on credit/quota errors.
#   "deepseek":           use DeepSeek as PRIMARY for every call. Claude only
#                          fires if explicitly forced via env override.
#   "auto":               same as "anthropic" but switches default to deepseek
#                          when ANTHROPIC_API_KEY is missing or empty.
_LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "auto").strip().lower()


# Map Claude model family → DeepSeek model. Sonnet/Opus → reasoner (R1) for
# better legal reasoning; Haiku → chat (V3) for fast structured output.
_CLAUDE_TO_DEEPSEEK = {
    "claude-opus-4-7":   "deepseek-reasoner",
    "claude-sonnet-4-6": "deepseek-reasoner",
    "claude-haiku-4-5":  "deepseek-chat",
}


def _deepseek_primary() -> bool:
    """Should DeepSeek handle the primary call (not just fallback)?
    True when LLM_PROVIDER=deepseek, OR when LLM_PROVIDER=auto AND no
    Anthropic key is configured.
    """
    if _LLM_PROVIDER == "deepseek":
        return True
    if _LLM_PROVIDER == "auto" and not config.ANTHROPIC_API_KEY:
        return True
    return False


def _to_deepseek_model(claude_model: str) -> str:
    """Map a Claude model name to the DeepSeek equivalent."""
    return _CLAUDE_TO_DEEPSEEK.get(claude_model, "deepseek-chat")


def _is_anthropic_no_credit_error(exc: Exception) -> bool:
    """Direct Anthropic call failed because the account has no balance.
    Recoverable via DeepSeek → Groq fallback chain."""
    s = str(exc).lower()
    return any(k in s for k in (
        "credit balance is too low",
        "credit balance",
        "insufficient credit",
        "out of credits",
        "billing",
        "your account does not have",
    ))


def _call_deepseek_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
    claude_model: str = "claude-sonnet-4-6",
) -> Tuple[str, dict]:
    """DeepSeek API call — fires as primary (when LLM_PROVIDER=deepseek) or as
    fallback when Anthropic fails.

    Routes by claude_model:
        Sonnet / Opus   → deepseek-reasoner (R1, chain-of-thought, deep)
        Haiku           → deepseek-chat (V3, fast, cheap)

    DeepSeek V3 / R1 use OpenAI-compatible API; the existing `openai` SDK
    (already in requirements.txt) works without any extra dependency.

    Requires DEEPSEEK_API_KEY env var on Railway.
    """
    ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not ds_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")

    try:
        from openai import OpenAI
    except ImportError as e:
        raise RuntimeError(f"openai SDK not installed: {e}") from e

    # Pick reasoner vs chat based on the Claude model family the caller asked for.
    model = os.environ.get(
        "DEEPSEEK_MODEL_OVERRIDE",
        _to_deepseek_model(claude_model),
    )
    log.warning("[llm] DeepSeek call (claude→ds: %s → %s)", claude_model, model)

    # Split timeout by model family:
    #   V3 (deepseek-chat)      → 90s   — normally 5-15s; if >90s, DeepSeek is
    #                                      overloaded and Groq fallback is faster.
    #   R1 (deepseek-reasoner)  → 180s  — chain-of-thought normally 60-120s.
    # Previous: flat 240s for both. Two V3 calls in the situation pipeline
    # (reranker + main) could burn 480s combined → frontend abort at 180s.
    _ds_timeout = 180.0 if model == "deepseek-reasoner" else 90.0
    client = OpenAI(
        api_key=ds_key,
        base_url="https://api.deepseek.com",
        timeout=_ds_timeout,
    )

    # R1 supports a longer max_tokens than V3
    if model == "deepseek-reasoner":
        capped_max = min(max_tokens or 8000, 16384)
    else:
        capped_max = min(max_tokens or 4000, 8192)

    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=capped_max,
        temperature=0.2,
    )
    text = resp.choices[0].message.content or ""
    usage = resp.usage
    return text, {
        "model": f"deepseek:{model}",
        "input_tokens": getattr(usage, "prompt_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "completion_tokens", 0) if usage else 0,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }


def _call_groq_fallback(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
) -> Tuple[str, dict]:
    """Last-resort fallback to Groq's free-tier Llama-3.3-70B when both
    Anthropic AND DeepSeek fail. Lowest quality for Indian legal reasoning
    but free and reliable.

    Uses GROQ_API_KEY env var.
    """
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        raise HTTPException(
            status_code=503,
            detail="LLM unavailable. All providers failed. Set DEEPSEEK_API_KEY or GROQ_API_KEY on Railway.",
        )
    try:
        from groq import Groq
    except ImportError as e:
        raise HTTPException(
            status_code=503,
            detail=f"groq SDK not installed on this deploy: {e}",
        ) from e

    model = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
    log.warning("[llm] Falling back to Groq %s (Anthropic + DeepSeek both failed)", model)

    client = Groq(api_key=groq_key)
    resp = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        max_tokens=min(max_tokens or 4000, 8000),
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


def _call_deepseek_or_groq(
    system_prompt: str,
    user_prompt: str,
    *,
    max_tokens: int,
    claude_model: str = "claude-sonnet-4-6",
) -> Tuple[str, dict]:
    """Try DeepSeek first; fall through to Groq if DeepSeek key is absent or
    the call errors. Used as the fallback path after Anthropic fails AND as
    the primary path when LLM_PROVIDER=deepseek.
    """
    try:
        return _call_deepseek_fallback(
            system_prompt, user_prompt,
            max_tokens=max_tokens,
            claude_model=claude_model,
        )
    except Exception as ds_exc:
        log.warning("[llm] DeepSeek failed — trying Groq: %s", str(ds_exc)[:200])
        return _call_groq_fallback(system_prompt, user_prompt, max_tokens=max_tokens)


def get_client():
    """Return a direct Anthropic client. Bedrock support removed — see module
    docstring. Raises 500 if no Anthropic key configured AND DeepSeek isn't
    primary (caller should route to DeepSeek before invoking get_client)."""
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

    Provider routing:
      - If LLM_PROVIDER=deepseek (or =auto and no Anthropic key), DeepSeek is
        the primary path. Sonnet/Opus → deepseek-reasoner (R1); Haiku → V3.
      - Otherwise Claude is primary. On credit failure, falls through to
        DeepSeek → Groq automatically.

    Extended thinking
    -----------------
    When `enable_thinking=True`, Claude gets a dedicated scratch space
    (`thinking_budget` tokens) for chain-of-thought BEFORE producing JSON.
    DeepSeek-Reasoner has chain-of-thought built in — no equivalent flag needed.

    Supported on Sonnet 4 / Opus 4 only. Haiku 4.5 does not support thinking.
    """
    model = model or config.DEFAULT_MODEL
    max_tokens = max_tokens or config.MAX_TOKENS

    # PATH A: DeepSeek primary mode — every call goes through DeepSeek first
    if _deepseek_primary():
        log.info("[llm] LLM_PROVIDER=%s → routing to DeepSeek primary (model=%s)",
                 _LLM_PROVIDER, model)
        return _call_deepseek_or_groq(
            system_prompt, user_prompt,
            max_tokens=max_tokens,
            claude_model=model,
        )

    # PATH B: Anthropic primary, DeepSeek/Groq as fallback
    client = get_client()
    if cache:
        system = [
            {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}
        ]
    else:
        system = system_prompt

    # Per-model timeouts
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
        if max_tokens <= thinking_budget:
            create_kwargs["max_tokens"] = thinking_budget + 2000
        create_kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget,
        }
        create_kwargs["temperature"] = 1.0

    try:
        resp = client.messages.create(**create_kwargs)
    except Exception as exc:
        if _is_anthropic_no_credit_error(exc):
            log.warning(
                "Anthropic failed (no credit) — trying DeepSeek → Groq: %s",
                str(exc)[:200],
            )
            return _call_deepseek_or_groq(
                system_prompt, user_prompt,
                max_tokens=create_kwargs.get("max_tokens", 4000),
                claude_model=model,
            )
        raise

    usage = resp.usage
    usage_dict = {
        "model": model,
        "input_tokens": getattr(usage, "input_tokens", 0),
        "output_tokens": getattr(usage, "output_tokens", 0),
        "cache_creation_input_tokens": getattr(usage, "cache_creation_input_tokens", 0),
        "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0),
    }

    text_blocks = [b.text for b in resp.content if getattr(b, "type", None) == "text"]
    response_text = "\n".join(text_blocks) if text_blocks else (
        resp.content[0].text if resp.content else ""
    )
    return response_text, usage_dict


def estimate_cost_usd(usage: dict) -> float:
    """Estimate USD cost from a usage dict. Handles Claude, DeepSeek, and Groq."""
    model = (usage.get("model") or "").lower()
    if model.startswith("deepseek:"):
        # Reasoner is slightly pricier than chat; both still ~10x cheaper than Sonnet
        if "reasoner" in model:
            # DeepSeek R1: $0.55/M input, $2.19/M output (Nov 2025 prices)
            pricing = {
                "input": 0.55,
                "input_cache_write": 0.55,
                "input_cache_read": 0.14,
                "output": 2.19,
            }
        else:
            pricing = config.PRICE_DEEPSEEK
    elif model.startswith("groq:"):
        pricing = config.PRICE_GROQ
    elif "haiku" in model:
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
    """Parse Claude/DeepSeek response as JSON, tolerating ```json fences.
    Raises HTTPException(502) if the response is not parseable JSON."""
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
