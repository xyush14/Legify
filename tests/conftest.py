"""Shared pytest fixtures. All tests run on the local kanoon_cache.sqlite —
no live IK calls, no API keys required. Run with:

    .venv/bin/pytest tests/ -v
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the project root importable as if running scripts from there.
# (Tests import from the `headnote` package; this ensures it's on sys.path
# whether you invoke pytest from the project root or elsewhere.)
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def kanoon_client():
    """A KanoonClient pointing at the local cache. Tests should only use
    cached docs — never make live API calls. We guard this by setting the
    daily cap to ₹0 so any accidental live call raises immediately.

    If the cache file doesn't exist (e.g. running in CI without the local
    SQLite cache), every test depending on this fixture is skipped — the
    pure-unit tests (regex distillation, hit ranking) still run.
    """
    from headnote.config import KANOON_CACHE_PATH
    from headnote.kanoon.client import KanoonClient
    # Need both the SQLite file AND a populated embedding index — token
    # is also required because the client refuses to construct without one.
    if not KANOON_CACHE_PATH.exists():
        pytest.skip(f"requires local kanoon cache at {KANOON_CACHE_PATH}")
    import os
    if not os.environ.get("INDIAN_KANOON_TOKEN"):
        pytest.skip("requires INDIAN_KANOON_TOKEN (cache exists but client init needs token)")
    return KanoonClient(daily_cap_inr=0.0)


@pytest.fixture(scope="session")
def curated_corpus() -> list[dict]:
    from headnote.config import load_curated_corpus
    return load_curated_corpus()


@pytest.fixture(scope="session")
def known_tids() -> dict:
    """Cases we've previously cached. Tests assume these exist in cache."""
    return {
        "bhaskaran_1999": 529907,           # old SC, sparse markup
        "dashrath_2014":  100995424,        # modern SC, rich markup
        "vijay_madanlal_2022": 14485072,    # massive judgment (PMLA)
    }
