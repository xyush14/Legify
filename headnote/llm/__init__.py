"""LLM prompt templates + Claude client wrapper."""

from .prompts import (
    build_situation_system_prompt,
    SITUATION_USER_TEMPLATE,
    HEADNOTE_SYSTEM_PROMPT,
    HEADNOTE_USER_TEMPLATE,
    build_digest_system_prompt,
    DIGEST_USER_TEMPLATE,
)
from .client import (
    get_client,
    call_claude_cached,
    estimate_cost_usd,
    parse_json_response,
    build_meta,
)

__all__ = [
    "build_situation_system_prompt",
    "SITUATION_USER_TEMPLATE",
    "HEADNOTE_SYSTEM_PROMPT",
    "HEADNOTE_USER_TEMPLATE",
    "build_digest_system_prompt",
    "DIGEST_USER_TEMPLATE",
    "get_client",
    "call_claude_cached",
    "estimate_cost_usd",
    "parse_json_response",
    "build_meta",
]
