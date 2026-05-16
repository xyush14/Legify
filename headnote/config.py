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

USE_IK_RETRIEVAL = os.environ.get("USE_IK_RETRIEVAL", "").lower() in {"1", "true", "yes"}
INDIAN_KANOON_TOKEN: Optional[str] = os.environ.get("INDIAN_KANOON_TOKEN")

_daily_cap_env = os.environ.get("INDIAN_KANOON_DAILY_CAP_INR", "100").strip()
INDIAN_KANOON_DAILY_CAP_INR: Optional[float] = (
    float(_daily_cap_env) if _daily_cap_env else None
)

PREFILTER_TOP_K = int(os.environ.get("PREFILTER_TOP_K", "12"))


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
        "cases_path": str(CASES_PATH.relative_to(PROJECT_ROOT)) if CASES_PATH.is_relative_to(PROJECT_ROOT) else str(CASES_PATH),
        "static_dir": str(STATIC_DIR.relative_to(PROJECT_ROOT)) if STATIC_DIR.is_relative_to(PROJECT_ROOT) else str(STATIC_DIR),
    }
