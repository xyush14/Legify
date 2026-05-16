# Contributing to Headnote

Small project, lean process. The main goals: don't break verification,
don't burn IK budget unnecessarily, don't ship code that hallucinates.

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env
# Add ANTHROPIC_API_KEY and INDIAN_KANOON_TOKEN to .env
pytest tests/ -v
```

## Before opening a PR

```bash
# 1. Tests must pass locally (running on cached data — no IK / Claude cost)
pytest tests/ -v

# 2. Lint
ruff check headnote/ tests/ scripts/

# 3. If you touched a prompt or the verification logic, manually verify
#    with a real query against a deployed instance and confirm the
#    `meta.verification.clean == true` for a clean response and
#    `clean == false` with correct `failing_citations` for a contrived
#    bad one. Tests can't catch every regression in prompt behaviour.

# 4. If your change affects the IK pipeline, run the smoke script
#    (will spend a small amount of IK budget for live verification)
python scripts/smoke_kanoon.py
```

## Code conventions

- **Type hints on all public functions.** Use `Optional[X]` not `X | None`
  for anything Pydantic touches (works on Py 3.9 without `eval_type_backport`).
- **Docstrings explain *why*, not what.** The code says what; the docstring
  should add context the reader can't get from the implementation.
- **No new external dependencies** without weighing the cost. Add via
  `pyproject.toml` + `requirements.txt`, document why in the PR.
- **Cost-affecting changes get extra scrutiny.** If a PR could increase
  per-query Claude or IK spend, name the new cost in the PR description.

## Testing philosophy

- Unit tests run on cached data (`tests/conftest.py` skips gracefully
  in CI if the cache is absent).
- Integration tests against live APIs are reserved for the smoke
  script (`scripts/smoke_kanoon.py`) — invoked manually, costs real
  IK/Claude credits.
- Anything touching `verify.py` MUST have a test for both a clean
  response and a contrived fabricated one.

## Touching the curated corpus

`headnote/data/cases.json` is hand-edited by the editorial supervisor.
**Do not auto-modify.** If you find a curation error, file an issue
with the case `id` and the proposed correction.

## Reporting a hallucination in production

If a lawyer reports a fabricated citation that wasn't caught:

1. Save the full response (the `raw` field plus `meta.verification`).
2. Reproduce locally with the same situation + the same cache state.
3. Add a regression test in `tests/test_verify.py` (or `test_retrieval.py`
   if the issue is retrieval-side).
4. Fix the code so the test passes.
5. Ship.

Verification gaps are the highest-priority bug class. Drop everything for them.
