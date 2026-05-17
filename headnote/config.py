"""
Centralised configuration: paths, environment-driven settings, feature flags.

Reading directly from os.environ rather than pydantic-settings to keep startup
cheap and dependencies minimal. Every setting has a sensible default; only
ANTHROPIC_API_KEY and INDIAN_KANOON_TOKEN are truly required for full function
(the app still starts without them, just with reduced capability).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

# Load .env if present (no-op if python-dotenv is missing).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ----------------------------------------------------------------- paths

# headnote/config.py  ->  parent dir = headnote/  ->  parent.parent = repo root
PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parent

CASES_PATH = PACKAGE_DIR / "data" / "cases.json"

# Static frontend served by FastAPI. Path is relative to project root, not
# package root, because the frontend is intentionally outside the package.
STATIC_DIR = PROJECT_ROOT / "static"

# Caches. Both default to inside the project root so they're easy to find /
# back up; overridable for production where you'd put them on a persistent
# volume (Render disk, EFS, etc.).
KANOON_CACHE_PATH = Path(os.environ.get(
    "KANOON_CACHE_PATH", str(PROJECT_ROOT / "kanoon_cache.sqlite"),
))
FEEDBACK_DB = Path(os.environ.get(
    "FEEDBACK_DB", str(PROJECT_ROOT / "feedback.db"),
))


# ----------------------------------------------------------------- LLM / Claude

ANTHROPIC_API_KEY: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
DEFAULT_MODEL = os.environ.get("MODEL", "claude-opus-4-6")
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "2500"))


# ----------------------------------------------------------------- IK / retrieval

# IK token: accept either INDIAN_KANOON_TOKEN (canonical) or KANOON_API_TOKEN
# (legacy alias used in some Render dashboards). Whichever is set wins.
INDIAN_KANOON_TOKEN: Optional[str] = (
    os.environ.get("INDIAN_KANOON_TOKEN")
    or os.environ.get("KANOON_API_TOKEN")
)

# USE_IK_RETRIEVAL: explicit opt-in normally, but auto-enable if a token IS
# configured — there's no good reason to have the token set and not use it.
# Set USE_IK_RETRIEVAL=0 to force-disable even with token present.
_use_ik_env = os.environ.get("USE_IK_RETRIEVAL", "").lower()
if _use_ik_env in {"0", "false", "no"}:
    USE_IK_RETRIEVAL = False
elif _use_ik_env in {"1", "true", "yes"}:
    USE_IK_RETRIEVAL = True
else:
    USE_IK_RETRIEVAL = bool(INDIAN_KANOON_TOKEN)

_daily_cap_env = os.environ.get("INDIAN_KANOON_DAILY_CAP_INR", "100").strip()
INDIAN_KANOON_DAILY_CAP_INR: Optional[float] = (
    float(_daily_cap_env) if _daily_cap_env else None
)

# ----------------------------------------------------------------- quality knobs
# Two env-var knobs that flip the quality/cost trade-off per-host.
# Cheap-and-fast preset (Render Free):  SITUATION_MODEL=haiku, ENABLE_SONNET_RERANKER=0
# Quality preset (Railway / Pro / VPS): SITUATION_MODEL=sonnet, ENABLE_SONNET_RERANKER=1  (default)

# Model the situation endpoint uses when deep_mode is OFF.
# Accepts: haiku | sonnet | opus (or a full Anthropic model id).
SITUATION_MODEL: str = os.environ.get("SITUATION_MODEL", "sonnet").lower().strip()

# When the situation endpoint is in deep_mode (the explicit "premium" toggle),
# use this model. Defaults to Opus.
SITUATION_DEEP_MODEL: str = os.environ.get("SITUATION_DEEP_MODEL", "opus").lower().strip()

# Enable Sonnet fact-pattern reranking inside Hidden Authorities. This is the
# single biggest case-relevance lever — without it the reranker only uses
# semantic similarity as a proxy for fact-pattern match. Costs ~₹4 per query
# but turns "topically related" results into "factually aligned" results.
_rerank_env = os.environ.get("ENABLE_SONNET_RERANKER", "").lower()
if _rerank_env in {"0", "false", "no"}:
    ENABLE_SONNET_RERANKER = False
elif _rerank_env in {"1", "true", "yes"}:
    ENABLE_SONNET_RERANKER = True
else:
    # Default ON. Operator can disable for free-tier latency.
    ENABLE_SONNET_RERANKER = True

PREFILTER_TOP_K = int(os.environ.get("PREFILTER_TOP_K", "12"))

# Sonnet -> Opus auto-escalation on low confidence. Set to "0" / "false" in
# env to disable the retry, e.g. during a cost-spike incident — Sonnet will
# return its first attempt regardless of confidence.
ENABLE_OPUS_ESCALATION = os.environ.get(
    "ENABLE_OPUS_ESCALATION", "true",
).lower() in {"1", "true", "yes"}

# Bearer token for /admin/* routes. Unset means admin endpoints return 503.
ADMIN_TOKEN: Optional[str] = os.environ.get("ADMIN_TOKEN")


# ----------------------------------------------------------------- pricing meter

USD_TO_INR = float(os.environ.get("USD_TO_INR", "84.0"))

# Anthropic pricing per million tokens. Update if Anthropic changes prices —
# this only affects the in-app cost meter, not actual billing.
PRICE_OPUS = {
    "input":              float(os.environ.get("PRICE_OPUS_INPUT",  "15.00")),
    "input_cache_write":  float(os.environ.get("PRICE_OPUS_CW",     "18.75")),
    "input_cache_read":   float(os.environ.get("PRICE_OPUS_CR",      "1.50")),
    "output":             float(os.environ.get("PRICE_OPUS_OUTPUT", "75.00")),
}
PRICE_HAIKU = {
    "input":             0.80,
    "input_cache_write": 1.00,
    "input_cache_read":  0.08,
    "output":            4.00,
}
PRICE_SONNET = {
    "input":             3.00,
    "input_cache_write": 3.75,
    "input_cache_read":  0.30,
    "output":           15.00,
}


# ----------------------------------------------------------------- helpers

def load_curated_corpus() -> list[dict]:
    """Read cases.json from its canonical location. Cached per-process via
    functools.lru_cache to avoid repeated disk reads in hot paths."""
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def summary() -> dict:
    """Return a dict suitable for /api/health and debug output. Does NOT
    expose secrets."""
    return {
        "version": "0.4.0",
        "model": DEFAULT_MODEL,
        "use_ik_retrieval": USE_IK_RETRIEVAL,
        "ik_token_configured": bool(INDIAN_KANOON_TOKEN),
        "ik_daily_cap_inr": INDIAN_KANOON_DAILY_CAP_INR,
        "anthropic_key_configured": bool(ANTHROPIC_API_KEY),
        "admin_configured": bool(ADMIN_TOKEN),
        "opus_escalation_enabled": ENABLE_OPUS_ESCALATION,
        "cases_path": str(CASES_PATH.relative_to(PROJECT_ROOT)) if CASES_PATH.is_relative_to(PROJECT_ROOT) else str(CASES_PATH),
        "static_dir": str(STATIC_DIR.relative_to(PROJECT_ROOT)) if STATIC_DIR.is_relative_to(PROJECT_ROOT) else str(STATIC_DIR),
    }
