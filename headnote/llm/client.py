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
    json_mode: bool = False,
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
    #   V3 (deepseek-chat)      → 90s   — normally 5-15s; the long tail
    #                                      (30-90s under DeepSeek load) is
    #                                      better waited out than fallen
    #                                      through to Groq, which produces
    #                                      poor Indian legal reasoning.
    #   R1 (deepseek-reasoner)  → 180s  — chain-of-thought normally 60-120s
    #                                      but complex legal queries can
    #                                      extend to 150s. 180s catches the
    #                                      long tail without false timeouts.
    _ds_timeout = 180.0 if model == "deepseek-reasoner" else 90.0
    client = OpenAI(
        api_key=ds_key,
        base_url="https://api.deepseek.com",
        timeout=_ds_timeout,
    )

    # R1 (deepseek-reasoner) spends part of its token budget on the hidden
    # chain-of-thought BEFORE it emits the answer. If the caller's max_tokens
    # is small (e.g. 4000 for a draft), reasoning eats the whole budget and
    # `content` comes back EMPTY — the #1 cause of the "invalid JSON /
    # Expecting value: line 1 column 1 (char 0)" 502. So give the reasoner a
    # generous output floor regardless of what the caller asked for.
    if model == "deepseek-reasoner":
        capped_max = min(max(max_tokens or 8000, 12000), 16384)
    else:
        capped_max = min(max_tokens or 4000, 8192)

    kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": capped_max,
        "temperature": 0.2,
    }
    # DeepSeek V3 (deepseek-chat) supports strict JSON mode, which stops the
    # model from wrapping the object in prose or ```json fences. The reasoner
    # does NOT support response_format, so only apply it for chat.
    if json_mode and model == "deepseek-chat":
        kwargs["response_format"] = {"type": "json_object"}

    resp = client.chat.completions.create(**kwargs)
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
    json_mode: bool = False,
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
    groq_kwargs: dict = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        "max_tokens": min(max_tokens or 4000, 8000),
        "temperature": 0.2,
        "timeout": 20.0,  # Groq free tier is fast (3-8s). 20s is generous; 60s was burning pipeline budget.
    }
    if json_mode:
        groq_kwargs["response_format"] = {"type": "json_object"}
    resp = client.chat.completions.create(**groq_kwargs)
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
    json_mode: bool = False,
) -> Tuple[str, dict]:
    """Try DeepSeek first; fall through to Groq if DeepSeek key is absent or
    the call errors. Used as the fallback path after Anthropic fails AND as
    the primary path when LLM_PROVIDER=deepseek.

    If DeepSeek returns EMPTY content (the reasoner burning its whole token
    budget on chain-of-thought is the classic cause), we treat that as a
    failure and fall through to Groq rather than handing an empty string back
    to a json.loads() that will 502.
    """
    try:
        text, meta = _call_deepseek_fallback(
            system_prompt, user_prompt,
            max_tokens=max_tokens,
            claude_model=claude_model,
            json_mode=json_mode,
        )
        if not (text or "").strip():
            raise RuntimeError("DeepSeek returned empty content (reasoner likely ran out of output budget)")
        return text, meta
    except Exception as ds_exc:
        log.warning("[llm] DeepSeek failed — trying Groq: %s", str(ds_exc)[:200])
        return _call_groq_fallback(
            system_prompt, user_prompt, max_tokens=max_tokens, json_mode=json_mode,
        )


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


def stream_chat(
    messages: list[dict],
    *,
    system_prompt: str,
    deep: bool = False,
    max_tokens: int = 4000,
):
    """Stream a multi-turn chat completion, yielding text deltas as they arrive.

    Powers the ASK-mode chat surface. Deliberately DeepSeek-only (per the
    product cost rule — chat is high-volume conversational): V3 (deepseek-chat)
    for fast answers, R1 (deepseek-reasoner) when `deep=True`. Falls through to
    Groq's free-tier Llama on any DeepSeek failure so the surface never dies.

    `messages` is an OpenAI-style history: [{"role": "user"/"assistant",
    "content": str}, ...]. The system prompt is prepended here.

    Yields
    ------
    ("reasoning", str) — a chunk of the model's chain-of-thought (R1 only; the
                         "Analysing…" trace shown live in the UI)
    ("delta", str)     — a chunk of answer text
    ("usage", dict)    — final token usage (once, at the end), for the cost meter

    Never raises inside the stream — a provider error mid-flight is caught and
    surfaced as a final ("error", message) tuple so the caller can close the
    SSE cleanly.
    """
    model = "deepseek-reasoner" if deep else "deepseek-chat"
    full_messages = [{"role": "system", "content": system_prompt}, *messages]

    ds_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if ds_key:
        try:
            from openai import OpenAI
            _timeout = 180.0 if deep else 90.0
            client = OpenAI(api_key=ds_key, base_url="https://api.deepseek.com", timeout=_timeout)
            capped = min(max_tokens, 16384 if deep else 8192)
            stream = client.chat.completions.create(
                model=model,
                messages=full_messages,
                max_tokens=capped,
                temperature=0.3,
                stream=True,
                stream_options={"include_usage": True},
            )
            usage_dict = {"model": f"deepseek:{model}", "input_tokens": 0, "output_tokens": 0,
                          "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
            for chunk in stream:
                if getattr(chunk, "usage", None):
                    u = chunk.usage
                    usage_dict["input_tokens"] = getattr(u, "prompt_tokens", 0) or 0
                    usage_dict["output_tokens"] = getattr(u, "completion_tokens", 0) or 0
                if not chunk.choices:
                    continue
                delta = chunk.choices[0].delta
                # R1 (deepseek-reasoner) streams its chain-of-thought in
                # `reasoning_content` BEFORE the answer arrives in `content`.
                rc = getattr(delta, "reasoning_content", None)
                if rc:
                    yield ("reasoning", rc)
                piece = getattr(delta, "content", None)
                if piece:
                    yield ("delta", piece)
            yield ("usage", usage_dict)
            return
        except Exception as ds_exc:
            log.warning("[llm] DeepSeek chat stream failed — trying Groq: %s", str(ds_exc)[:200])

    # Fallback: Groq streaming (free tier, lower quality but keeps chat alive).
    groq_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not groq_key:
        yield ("error", "Chat is temporarily unavailable — no LLM provider configured.")
        return
    try:
        from groq import Groq
        gmodel = os.environ.get("GROQ_FALLBACK_MODEL", "llama-3.3-70b-versatile")
        gclient = Groq(api_key=groq_key)
        stream = gclient.chat.completions.create(
            model=gmodel,
            messages=full_messages,
            max_tokens=min(max_tokens, 8000),
            temperature=0.3,
            stream=True,
        )
        for chunk in stream:
            if not chunk.choices:
                continue
            piece = getattr(chunk.choices[0].delta, "content", None)
            if piece:
                yield ("delta", piece)
        yield ("usage", {"model": f"groq:{gmodel}", "input_tokens": 0, "output_tokens": 0,
                         "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0})
    except Exception as groq_exc:
        log.warning("[llm] Groq chat stream failed: %s", str(groq_exc)[:200])
        yield ("error", "Chat is temporarily unavailable. Please try again in a moment.")


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


def _repair_truncated_json(s: str):
    """Best-effort repair of JSON cut off mid-stream. Walks the text tracking
    string/bracket state, trims the dangling fragment after the last complete
    value, closes what's open, and parses. Returns None if unrecoverable."""
    import re as _re
    stack: list[str] = []
    in_str = esc = False
    last_complete = 0   # index just past the last completed value/container
    for i, ch in enumerate(s):
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
                last_complete = i + 1
        else:
            if ch == '"':
                in_str = True
            elif ch in "{[":
                stack.append(ch)
            elif ch in "}]":
                if stack:
                    stack.pop()
                last_complete = i + 1
                if not stack:
                    break
            elif ch in "0123456789el.":   # inside a number/true/false/null literal
                last_complete = i + 1
    if not stack and last_complete:
        try:
            return json.loads(s[:last_complete])
        except json.JSONDecodeError:
            return None
    if not last_complete:
        return None
    t = s[:last_complete]
    # drop a dangling `,"key"` / `,"key":` left hanging after the cut
    t = _re.sub(r',\s*"(?:[^"\\]|\\.)*"\s*:?\s*$', "", t)
    t = _re.sub(r",\s*$", "", t)
    for ch in reversed(stack):
        t += "}" if ch == "{" else "]"
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def parse_json_response(raw: str) -> dict:
    """Parse Claude/DeepSeek response as JSON, tolerating ```json fences, a
    reasoning preamble before the object, and trailing prose. Raises
    HTTPException(502) with a human-readable message only if nothing
    JSON-shaped can be recovered."""
    text = (raw or "").strip()
    if text.startswith("```"):
        text = "\n".join(text.split("\n")[1:])
        if text.endswith("```"):
            text = text[: -3]
        text = text.strip()
    # Fast path.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Salvage: grab the largest {...} span (models sometimes wrap the object in
    # a "Here is the draft:" preamble or add a trailing note).
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    # Repair: TRUNCATED output (max_tokens hit / provider cut the stream mid-key —
    # seen live: '…"case_number": "409/2021", "case_ye'). Close the open string,
    # drop the dangling key/value fragment, close every open bracket. A partial
    # payload the renderer can degrade gracefully on beats a failed draft.
    if start != -1:
        repaired = _repair_truncated_json(text[start:])
        if repaired is not None:
            # mark that this payload was salvaged from a CUT-OFF response so the caller
            # can warn the advocate the draft is incomplete (don't present a truncated
            # draft as if it were finished).
            if isinstance(repaired, dict):
                repaired["_truncated"] = True
            return repaired
    # Give up — but with a message a lawyer (not a stack trace) can act on.
    raise HTTPException(
        status_code=502,
        detail=(
            "The drafting model didn't return a usable draft this time "
            "(it replied empty or in the wrong format). Please tap Draft it "
            "again — it usually succeeds on the retry."
        ),
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
