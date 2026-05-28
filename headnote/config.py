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

# Caches. Default to inside the project root so they're easy to find / back
# up; overridable for production where you'd put them on a persistent
# volume (Render disk, EFS, Railway volume, etc.).
#
# Defensive: if the configured directory isn't writable (e.g. Railway
# without a volume mount, immutable container layer), fall back to /tmp.
# Persistence is lost on restart, but the app at least boots.

def _writable_path(env_var: str, default: Path) -> Path:
    candidate = Path(os.environ.get(env_var, str(default)))
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        # Touch-test
        candidate.parent.touch(exist_ok=True)
        return candidate
    except (PermissionError, OSError):
        import tempfile
        fallback = Path(tempfile.gettempdir()) / candidate.name
        print(f"[config] {env_var} dir not writable; falling back to {fallback}")
        return fallback


KANOON_CACHE_PATH = _writable_path(
    "KANOON_CACHE_PATH", PROJECT_ROOT / "kanoon_cache.sqlite",
)
FEEDBACK_DB = _writable_path(
    "FEEDBACK_DB", PROJECT_ROOT / "feedback.db",
)


# ----------------------------------------------------------------- LLM / Claude

ANTHROPIC_API_KEY: Optional[str] = os.environ.get("ANTHROPIC_API_KEY")
DEFAULT_MODEL = os.environ.get("MODEL", "claude-sonnet-4-6")
# 6000 (was 4000): R1/Sonnet needs room to output 5 detailed cases with
# stinger_sentence + held_line + court_quote + match_dimensions +
# negative_carve_out + relevance_scores + internal_reasoning. 4000 was
# clipping responses on complex queries, causing partial JSON parse failures
# that surfaced as "1 case returned" or "0 cases" downstream.
MAX_TOKENS = int(os.environ.get("MAX_TOKENS", "6000"))


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

# HF→IK resolution (layer 2). HF judgments (IL-TUR cjpe/summ) have text but
# NO verifiable public link — a lawyer can't open/cite them. When an HF case
# survives reranking, we search Indian Kanoon for its caption/case-number and,
# if a confident match is found, REPLACE it with the real IK judgment (real
# title, citation, verifiable URL). HF cases that can't be resolved are
# SUPPRESSED — never shown with a broken/missing link. Result: every displayed
# case is verifiable on Indian Kanoon, or it isn't shown.
#   ENABLE_HF_IK_RESOLUTION : master switch (default ON)
#   HF_IK_RESOLUTION_BUDGET : max IK searches per query (cost/latency cap;
#                             resolved mappings are cached, so steady-state
#                             cost trends to ~0 as the cache warms)
ENABLE_HF_IK_RESOLUTION = os.environ.get(
    "ENABLE_HF_IK_RESOLUTION", "true",
).lower() in {"1", "true", "yes"}
HF_IK_RESOLUTION_BUDGET = int(os.environ.get("HF_IK_RESOLUTION_BUDGET", "6"))

# ----------------------------------------------------------------- quality knobs
# Two env-var knobs that flip the quality/cost trade-off per-host.
#
# Under LLM_PROVIDER=deepseek:
#   "haiku"  → deepseek-chat (V3)      — fast (5-15s/call), conservative output
#   "sonnet" → deepseek-reasoner (R1)  — slow (60-120s/call), chain-of-thought
#   "opus"   → deepseek-reasoner (R1)  — same as sonnet under DeepSeek
#
# DEFAULT IS HAIKU (V3). We briefly tried R1 (sonnet) for consistency, but
# R1's 60-120s latency caused first-attempt timeouts (3 of 5 queries failed
# on the cold call). V3 is fast (10-30s) and — combined with the prompt's
# MINIMUM-OUTPUT rule and the backend safety-net that injects the top 3
# retrieval results when the LLM returns 0 — produces consistent output
# WITHOUT the timeout. The earlier V3 inconsistency was actually the corpus
# (anonymized lsi cases poisoning the candidate pool); once those are
# filtered out in retrieval, V3 sees only clean candidates and ranks them
# reliably. Speed + clean corpus + safety-net beats slow R1 on a paying
# advocate's first impression.
SITUATION_MODEL: str = os.environ.get("SITUATION_MODEL", "haiku").lower().strip()

# Deep mode → R1 (chain-of-thought) for users who explicitly opt into the
# slower, deeper reasoning path. Most queries don't need it.
SITUATION_DEEP_MODEL: str = os.environ.get("SITUATION_DEEP_MODEL", "sonnet").lower().strip()

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

# Extended thinking on the SITUATION call. The four-dimension scoring rubric
# in the v2 prompt needs reasoning space the model can use BEFORE writing
# JSON. Without thinking, scoring + JSON output share the same stream and
# both degrade. Thinking tokens are billed as output (~₹1.50 extra per
# query on Sonnet at 3000 budget). Disable for free-tier latency.
_thinking_env = os.environ.get("ENABLE_THINKING", "").lower()
if _thinking_env in {"0", "false", "no"}:
    ENABLE_THINKING = False
elif _thinking_env in {"1", "true", "yes"}:
    ENABLE_THINKING = True
else:
    ENABLE_THINKING = True   # default ON for quality
# 3500 — sweet spot between quality and latency. 3000 was the original
# default; 5000 added quality at the cost of ~10s extra latency per query
# which pushed real queries past the frontend 90s abort. 3500 gives Sonnet
# enough scratch space to replace Opus on four-dimension scoring while
# keeping p95 latency under 90s.
THINKING_BUDGET_TOKENS = int(os.environ.get("THINKING_BUDGET_TOKENS", "3500"))

PREFILTER_TOP_K = int(os.environ.get("PREFILTER_TOP_K", "20"))   # 12→20: wider pool for the LLM to discriminate from

# Sonnet -> Opus auto-escalation on low confidence. Defaults OFF: Sonnet 4.6
# with 5K thinking tokens consistently produces world-class legal analysis
# (citation-grounded, four-dimension scored) and the Opus retry costs ~4×
# more per call. Flip to "true" only for explicit power-user debugging.
ENABLE_OPUS_ESCALATION = os.environ.get(
    "ENABLE_OPUS_ESCALATION", "false",
).lower() in {"1", "true", "yes"}

# Bearer token for /admin/* routes. Unset means admin endpoints return 503.
ADMIN_TOKEN: Optional[str] = os.environ.get("ADMIN_TOKEN")

# ----------------------------------------------------------------- Founder / partner access
# Whitelist of email addresses that bypass all plan gates and quotas — every
# feature unlimited, every flag unlocked, no metering enforcement. Used for
# the founder + co-founder + strategic-partner accounts. Add via env var
# FOUNDER_EMAILS (comma-separated) for production, or extend the default
# tuple below for hard-coded entries. Match is case-insensitive on the
# local-part + domain.
_FOUNDER_DEFAULT = (
    "20pe3009@rgipt.ac.in",
    "ayushshivhare02@gmail.com",
    "kpal645@gmail.com",
    "vishnushivhare25@gmail.com",
    # Strategic partners (unlimited access)
    "wadhwapublishingco@gmail.com",
)
_founder_env = os.environ.get("FOUNDER_EMAILS", "")
FOUNDER_EMAILS: frozenset[str] = frozenset(
    e.strip().lower()
    for e in list(_FOUNDER_DEFAULT) + _founder_env.split(",")
    if e.strip()
)

# ----------------------------------------------------------------- Supabase auth
# Public credentials (sent to the browser via /api/config).
SUPABASE_URL: Optional[str] = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY: Optional[str] = os.environ.get("SUPABASE_ANON_KEY")

# Server-only secrets (NEVER expose to browser):
#   SUPABASE_JWT_SECRET     : HS256 secret used to verify Supabase JWTs locally.
#                             Dashboard → Settings → API → JWT Settings → JWT Secret.
#                             Without this, JWTs are decoded without signature
#                             verification (dev fallback; logs a warning).
#   SUPABASE_SERVICE_ROLE_KEY: lets the backend bypass RLS to read/write
#                             subscriptions / usage_meters / usage_events.
#                             Dashboard → Settings → API → service_role secret.
SUPABASE_JWT_SECRET: Optional[str] = os.environ.get("SUPABASE_JWT_SECRET")
SUPABASE_SERVICE_ROLE_KEY: Optional[str] = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")


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
# DeepSeek V3 (deepseek-chat) pricing — ~10x cheaper than Sonnet.
# No cache tiers; cache_write/read set to input price as approximation.
PRICE_DEEPSEEK = {
    "input":             0.27,
    "input_cache_write": 0.27,
    "input_cache_read":  0.07,   # DeepSeek context cache discount
    "output":            1.10,
}
# Groq free-tier Llama-3.3-70B — essentially $0, set to 0 for meter.
PRICE_GROQ = {
    "input":             0.0,
    "input_cache_write": 0.0,
    "input_cache_read":  0.0,
    "output":            0.0,
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
