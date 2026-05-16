# Headnote — Architecture

> System map and rationale for the legal-research pipeline. Updated 2026-05.

## One-sentence summary

A lawyer types a situation in plain English; Headnote retrieves the most
relevant precedents from a hybrid corpus (42 curated landmarks + ~26 lakh
judgments accessible via Indian Kanoon), generates a journal-format headnote
with Claude, and verifies every cited case, paragraph anchor, and quoted
phrase against the source paragraphs before showing it to the lawyer.

## Why this exists

On 27 Feb 2026, the Supreme Court (Narasimha & Aradhe JJ.) ruled that citing
AI-generated fake judgments constitutes **professional misconduct, not
error** — Bar Council can suspend or disbar. Verified citations went from
"feature" to "floor". Most legal-AI products still treat verification as
post-hoc. Headnote treats it as part of the response cycle.

## Stack at a glance

```
┌─────────────────────────────────────────────────────────────────┐
│  Browser (vanilla HTML/CSS/JS, no framework, no build step)      │
│  - 3 modes (situation / digest / headnote)                       │
│  - source badges (curated / IK / IK-cache)                       │
│  - per-citation verification status                              │
└──────────────────────────────┬──────────────────────────────────┘
                               │  HTTPS / JSON
                               ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI  (headnote.api.app)                                     │
│  - /api/situation / /api/digest / /api/headnote                  │
│  - /api/translate (free, Google Translate via deep-translator)   │
│  - /api/feedback (SQLite)                                        │
│  - /api/spend (IK cost ledger)                                   │
│  - /api/health (config summary, no secrets)                      │
└────────┬─────────────────────────────────────────────┬──────────┘
         │                                             │
         ▼                                             ▼
┌──────────────────┐                       ┌─────────────────────┐
│ Retrieval        │                       │ Claude (Opus 4.6)   │
│ (headnote.kanoon)│                       │ - prompt caching    │
│                  │                       │ - structured JSON   │
│ 1. Curated       │                       │ - max 1 regen retry │
│    (42 cases)    │                       └──────────┬──────────┘
│ 2. Semantic      │                                  │
│    (local emb)   │                                  ▼
│ 3. IK live       │                       ┌─────────────────────┐
│    (~26 lakh)    │                       │ Verification        │
└────┬─────────────┘                       │ (headnote.verify)   │
     │                                     │                     │
     │                                     │ 1. case_id exists?  │
     ▼                                     │ 2. anchor valid?    │
┌──────────────────┐                       │ 3. quote verbatim?  │
│ kanoon_cache.    │                       │                     │
│ sqlite           │←──── auto-embed ─────│ + regen feedback    │
│ - IK doc cache   │      on new fetch     └─────────────────────┘
│ - search cache   │
│ - cost ledger    │
│ - paragraph      │
│   embeddings     │
└──────────────────┘
```

## Modules

```
headnote/
├── config.py                  ← single source of truth for settings
├── verify.py                  ← three-check verification + regen feedback
├── translate.py               ← free Hindi (Google Translate, no LLM)
├── api/
│   ├── app.py                 ← FastAPI app, all endpoints
│   └── models.py              ← Pydantic request models (Optional[str] for Py 3.9)
├── kanoon/
│   ├── client.py              ← IK API client (cache, cost ledger, daily cap)
│   ├── parser.py              ← IK HTML → ParsedJudgment with paragraph tags
│   └── retrieval.py           ← hybrid pipeline + adapter to prompt format
├── retrieval/
│   ├── keyword.py             ← curated-corpus keyword scorer
│   └── embeddings.py          ← local fastembed + cosine search
├── llm/
│   ├── client.py              ← Claude wrapper (caching, cost meter, JSON parse)
│   └── prompts.py             ← system/user prompt templates
└── data/
    └── cases.json             ← curated corpus (hand-edited)
```

## The retrieval pipeline (most-asked question)

For every `POST /api/situation` request, the system runs three stages
in order, bailing early when enough relevant cases are found:

### Stage 1 — Curated keyword (free, instant, highest trust)

The 42-case curated corpus is scored with a weighted keyword scorer
(`headnote.retrieval.keyword.score_case`). Statute references (`S. 138`)
and topic-tag overlap dominate; raw token overlap is a tiebreaker.

Why first: editorial supervision is the strongest trust signal. If the
matter is in the curated set, that's the answer.

### Stage 2 — Semantic search over locally-cached paragraphs (free, ~20ms)

If slots remain, the lawyer's situation is embedded with
`BAAI/bge-small-en-v1.5` (384-dim, ONNX, runs on CPU) and compared via
cosine similarity to ~10,000+ paragraph embeddings stored as BLOBs in
the kanoon SQLite cache.

Why this matters: keyword search misses paraphrases. A query like
*"bank refused payment instrument, drawer denies demand letter"* doesn't
contain `S. 138` or `cheque` but should still match K. Bhaskaran — the
foundational S.138 NI Act case. Semantic search makes that work.

The embedding index grows organically: every new judgment fetched via
the IK live path is auto-embedded for future queries.

### Stage 3 — IK live search + fetch (paid, capped)

If slots still remain AND fewer than 3 cases were found in stages 1-2,
the system distills the situation into IK-friendly keywords and calls
the IK Search API (`₹0.50`). Top-N results that aren't already covered
are fetched (`₹0.20` each, hard cap of 5 per query).

Critical guardrails:
- Daily spend cap (default `₹100/day`) enforced **before** each call,
  not after. Configurable via `INDIAN_KANOON_DAILY_CAP_INR`.
- Cache means each judgment is paid for at most once — repeat queries
  on the same case are free forever.
- IK is keyword-Boolean, not semantic. Sending the lawyer's raw English
  sentence returns 0 hits. The query distiller (`_distill_query`)
  extracts statute names, sections, multi-word proper nouns, and
  high-signal content words. See `headnote/kanoon/retrieval.py:_distill_query`.

## Verification (the regulatory moat)

After Claude responds, `headnote.verify.verify_situation_response` runs
three checks per cited case:

| Check | What it catches | Implementation |
|---|---|---|
| **Existence** | Case fabricated whole-cloth | `case_id ∈ evidence_set` |
| **Anchor** | Paragraph number invented | Extracts `(Paras X, Y-Z)`; checks against actual paragraph numbers. If source has only unnumbered paragraphs (older judgments), rejects any numeric anchor — model is instructed to use the IK paragraph id `(p_18)` instead. |
| **Verbatim** | Quote made up or paraphrased | Fuzzy match (`difflib.SequenceMatcher`) of each quoted phrase against the source paragraphs. Threshold `0.88` (tolerates whitespace/punctuation drift; rejects fabrications which usually score < 0.6). |

If any check fails, `verify.build_regen_feedback` constructs a targeted
feedback message and Claude is called **once more** with the original
system prompt (cache hit, ~₹15) plus the feedback. The retry is only
swapped in if it has strictly fewer failures. Avoids infinite loops and
prevents regressions.

## Cost model

| Action | Cost | Notes |
|---|---|---|
| IK search | ₹0.50 | Per /api/situation call when needed |
| IK doc fetch | ₹0.20 | Per *new* judgment; cached forever after |
| Claude Opus 4.6 (cache write) | ~₹38 | First call of session |
| Claude Opus 4.6 (cache read) | ~₹15 | Subsequent calls within 5 min |
| Regeneration retry | ~₹15 | Cache stays warm; only triggered on verify failure |
| Hindi translation | ₹0 | Google Translate via deep-translator |
| Embedding (per new doc) | ₹0 | Runs locally on CPU |
| Embedding cosine search | ₹0 | ~20ms over 10k paragraphs |

**Per-query worst case** (cold cache, regen needed): ~₹55.
**Per-query typical** (warm cache, no regen): ~₹15.
**Per-query best** (semantic-only, cached): ~₹15 (just Claude).

## Storage

| What | Where | Persistence |
|---|---|---|
| Curated corpus | `headnote/data/cases.json` | Git-versioned |
| IK doc cache | `kanoon_cache.sqlite` (or `KANOON_CACHE_PATH`) | Local SQLite |
| Embedding index | Same file, `paragraph_embeddings` table | Local SQLite |
| Cost ledger | Same file, `ik_spend` table | Local SQLite |
| Feedback | `feedback.db` (or `FEEDBACK_DB`) | Local SQLite |

For production deployment, mount a persistent volume at the path you
set in `KANOON_CACHE_PATH` and `FEEDBACK_DB`. Render's free tier has
ephemeral disk — see `docs/DEPLOYMENT.md` for the migration paths.

## What's deliberately NOT built (and why)

- **Authentication.** v0 has none. Add when you onboard beta lawyers
  beyond the personal network. Simple bearer tokens + a "users" table
  in SQLite will hold for the first 1,000 lawyers.
- **Rate limiting.** None yet. Add when abuse becomes a real risk (free
  beta means anyone can hammer the endpoints).
- **Multi-tenant feedback storage.** SQLite is single-writer; fine for
  beta, will need migration to Postgres around 100 concurrent lawyers.
- **Background workers.** Everything is request-scoped today. When
  embedding-on-fetch becomes too slow for the user-facing path, push
  it to a background queue.
- **External vector store.** SQLite + numpy brute-force scales to ~200k
  paragraphs. Beyond that, swap to sqlite-vec or pgvector. One module
  to change: `headnote/retrieval/embeddings.py`.

## Adding a new endpoint

1. Define the Pydantic request model in `headnote/api/models.py`.
2. Add the handler in `headnote/api/app.py` using the existing
   `call_claude_cached`, `parse_json_response`, `build_meta` helpers.
3. If it uses Claude, add a prompt to `headnote/llm/prompts.py`.
4. Add a test in `tests/` — use cached IK docs (free) where possible.

## Adding a new judgment to the curated corpus

1. Fetch with `python scripts/ingest.py <kanoon-url>` to get an
   auto-extracted JSON entry.
2. Edit by hand (BNS mapping, topics, holding require editorial work).
3. Append to `headnote/data/cases.json`.
4. Increment `headnote/__init__.py` `__version__` if it changes the
   public surface.

No re-deploy is needed for corpus changes if you `git pull` on the
deployed instance — the corpus is read fresh on each request.
