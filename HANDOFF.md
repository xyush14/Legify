# Headnote — Engineering Handoff

**Last updated:** 2026-05-18 (second session)
**Author of this handoff:** Claude (Anthropic), via long pairing session with Ayush (founder, xyush14)
**Live URL:** https://headnote.up.railway.app (Railway Hobby — confirmed working)
**Repo:** https://github.com/xyush14/Legify (main branch)

---

## 1. Product in one paragraph

Headnote is a verticalised AI legal research tool for Indian criminal-law advocates. The lawyer describes a factual matter; the system retrieves the most relevant precedents from a corpus (42 hand-curated cases + Indian Kanoon's ~26 lakh judgments fetched on demand + 42K HuggingFace-imported SC/HC judgments), reranks via "Hidden Authorities" to surface obscure-but-relevant cases over famous landmarks, and writes a Cri.L.J.- or practitioner-format headnote with verified citations. Three modes: situation → ranked precedents (default), topic → research digest, judgment → headnote generation. The differentiator vs Jhana/Lawsome AI is the **fact-pattern-aware Hidden Authorities ranker** — they surface the same five landmark cases everyone knows; we surface the case that actually fits the lawyer's facts.

---

## 2. Architecture

```
FastAPI (Python 3.11) ──► Anthropic Claude (Haiku 4.5 / Sonnet 4.6 / Opus 4.6)
                     │
                     ├──► Indian Kanoon API (paid: ₹0.50/search, ₹0.20/doc, ₹0.02/docmeta)
                     │    cached forever in kanoon_cache.sqlite
                     │
                     ├──► fastembed BAAI/bge-small-en-v1.5 (local, 384-dim)
                     │    semantic search over cached IK paragraphs
                     │
                     ├──► HuggingFace IL-TUR corpus (new, local)
                     │    ~42K English SC + HC judgments in hf_judgments table
                     │    populated by scripts/harvest_hf_corpus.py (one-time)
                     │
                     └──► SQLite (single DB on Railway Volume):
                          ├─ ik_search / ik_doc / ik_docmeta — IK API cache
                          ├─ hf_judgments — HF IL-TUR corpus (42K+ docs)
                          ├─ ik_spend — cost ledger
                          └─ feedback.db — feedback table + query_telemetry
```

**Frontend:** vanilla JS, no framework. Single-page app at `/app` with sidebar (Research / Browse / Drafting Coming Soon), composer with mode chips (hidden / famous / mixed), style chips (practitioner / cri.l.j.), jurisdiction picker, deep_mode toggle. Calm white-surface design (style.css).

**Routes** (`headnote/api/app.py`):
- `POST /api/situation` — main retrieval+generation endpoint
- `POST /api/digest` — doctrinal topic → research digest
- `POST /api/headnote` — paste judgment text → Cri.L.J. headnotes (Opus + Haiku verifier)
- `POST /api/translate` — translate any English JSON result to Hindi via Haiku
- `POST /api/decompose` — Haiku call producing the "researching:" panel text
- `GET /api/browse/search` — direct IK passthrough with court/year/judge/statute/sort filters
- `GET /api/browse/doc/{tid}` — single judgment fetch by IK doc id
- `POST /api/feedback` — thumbs up/down + comment
- `GET /api/hf_search` — keyword search over local HF corpus (new)
- `GET /api/hf_doc/{doc_id}` — full text fetch for a single HF judgment (new)
- `GET /api/health` — liveness + config + hf_corpus stats (updated)
- `GET /admin/telemetry` — bearer-token-guarded cost/escalation/quality summary
- `GET /admin/cost-dashboard` — Chart.js dashboard

---

## 3. The retrieval pipeline

File: `headnote/kanoon/retrieval.py` → `retrieve_for_situation()`

```
1. Hindi pre-translate (Haiku) if input is Devanagari [headnote/translate_input.py]
2. Distill query → IK-friendly keywords [_distill_query, legal-aware]
3. Curated pre-filter (free, instant) — capped at 5 in hidden/famous mode
4. Semantic search over locally-cached IK paragraphs (free, ~50ms)
5. IK live search (₹0.50/page, always runs) + doc fetches (₹0.20 each, cap 4 in hidden mode)
6. Hidden Authorities reranker [headnote/retrieval/hidden_authorities.py]
   - Per-source relevance normalization (curated peer-max ≠ IK peer-max)
   - Hidden mode HARD-FILTERS curated when ≥3 IK candidates exist
   - Mode-specific formulas: hidden penalises fame, famous boosts it, mixed neutral
7. Single Sonnet/Haiku call generates 3 cases worth of headnote
8. Verify in-process (three-check: existence + paragraph anchor + verbatim quote)
   - Failed cases are DROPPED, not regenerated (regen was 30-60s of latency)
```

**HF corpus (Phase 1 — NOT yet wired into situation):** The `hf_judgments` table and search module exist and are tested, but HF results are not yet merged into `retrieve_for_situation()`. This is intentional — validate import quality via `/api/hf_search` first, then wire in. See §8 for the Step 2 plan.

**Critical fixes shipped:**
- IK skip threshold REMOVED — IK always runs now. Previously curated pre-fill triggered a "skip IK" guard that fired on every query.
- `_distill_query` rewritten — favours legal-specific terms, aggressively drops generic procedural English.
- `_rank_search_hits` no longer produces negative scores in hidden mode.
- Per-source normalization in CaseSummary→Candidate adapter.

---

## 4. The model routing

`headnote/llm/router.py` — `route_call(task_type, payload, force_model)`

| Task | Default model |
|------|--------------|
| situation | Sonnet 4.6 |
| situation deep_mode=True | Opus 4.6 |
| digest | Sonnet 4.6 |
| headnote | Opus 4.6 |
| headnote verification | Haiku 4.5 |
| translation | Haiku 4.5 |
| extraction / decompose | Haiku 4.5 |

**ENV-VAR DRIVEN — no code change needed when switching tiers:**

| Var | Default | Notes |
|-----|---------|-------|
| `SITUATION_MODEL` | `sonnet` | Set `haiku` for free-tier / budget |
| `SITUATION_DEEP_MODEL` | `opus` | Deep mode model |
| `ENABLE_SONNET_RERANKER` | `1` (on) | Biggest quality lever. ~₹4/query. Set `0` to save cost |
| `ENABLE_THINKING` | `1` (on) | Extended thinking. ~₹1.50 extra/query. Set `0` on budget |
| `ENABLE_OPUS_ESCALATION` | `true` | Sonnet→Opus auto-retry on confidence<7. **SET TO `false` WHEN BUDGET IS TIGHT** |

**Preset for tight Anthropic budget (current recommendation):**
```
ENABLE_OPUS_ESCALATION=false
ENABLE_THINKING=false
SITUATION_MODEL=sonnet
```
→ ~$0.045/query → $5 Anthropic credit = ~110 queries

---

## 5. Hosting — Railway Hobby (confirmed working)

**Status:** Railway Hobby plan, confirmed working as of 2026-05-18.
- URL: https://headnote.up.railway.app
- Plan: Hobby ($5/month base)
- **The fix that made it work:** Clear the "Start Command" field in Railway → Settings → Deploy. Let it use CMD from Dockerfile (`python main.py`). Railway was injecting its own exec-form start command that broke `$PORT` shell expansion. `main.py` now reads `PORT` directly in Python — no shell expansion needed.

**Env vars on Railway (must-have):**
```
ANTHROPIC_API_KEY=sk-ant-...
INDIAN_KANOON_TOKEN=...
INDIAN_KANOON_DAILY_CAP_INR=100
ENABLE_OPUS_ESCALATION=false
ENABLE_THINKING=false
ADMIN_TOKEN=...
KANOON_CACHE_PATH=/data/kanoon_cache.sqlite
```

**Volume setup (required for persistent SQLite + HF corpus):**
- Railway → Headnote service → Volumes → Add Volume
- Mount path: `/data`
- Size: **2 GB** (covers IK cache + CJPE + SUMM harvest, ~1.3 GB)
- Size: **3 GB** if you also import BAIL (Hindi, 176K docs, +1 GB)
- Cost: included free in Railway Hobby (confirmed — no extra charge for volume on Hobby)

**Deployment:** Auto-deploys on every push to `main`.

---

## 6. Anthropic API budget — cost per query

**When balance hits $0 → HTTP 500** (the API returns a billing error; the app doesn't catch it specifically so it becomes a generic 500). Fix: top up the Anthropic account.

| Config | Cost/query | $5 credit gives you |
|--------|-----------|-------------------|
| Sonnet + thinking + Opus escalation (default, NOT recommended while low) | ~$0.55 | ~9 queries |
| Sonnet, no thinking, no escalation | ~$0.045 | ~110 queries |
| Haiku (SITUATION_MODEL=haiku) | ~$0.015 | ~333 queries |

**Per paying user (₹499/month, 30 queries/month):**
- Anthropic: ~$1.35 = ~₹113
- Railway share: ~₹16
- IK API: ~₹15
- **Total cost: ~₹144 / Revenue: ₹499 / Margin: ~71%**

---

## 7. The HuggingFace IL-TUR corpus (new — Phase 1 complete)

**Dataset:** [Exploration-Lab/IL-TUR](https://huggingface.co/datasets/Exploration-Lab/IL-TUR) on HuggingFace. 1.6 GB total across 8 subsets.

**What we import:**

| Subset | Court | Language | Docs | Why |
|--------|-------|----------|------|-----|
| CJPE | Supreme Court | English | 34,816 | Full text + outcome label (accepted/rejected) |
| SUMM | SC + HC | English | 7,130 | Full text + expert gold summaries — useful for headnote quality |
| BAIL | District Courts | Hindi | 176,000 | Bail applications — core use case |

**Files added:**
- `scripts/harvest_hf_corpus.py` — one-time bulk import. Streams + batches + resumable (INSERT OR IGNORE on doc_id).
- `requirements-harvest.txt` — `datasets` + `tqdm`. NOT in requirements.txt — keeps Docker image small.
- `headnote/retrieval/hf_corpus.py` — `search()`, `get_by_id()`, `corpus_stats()` functions.
- `headnote/kanoon/client.py` — `hf_judgments` table + indexes added to `_init_cache()`.

**Schema (`hf_judgments` table):**
```sql
rowid, doc_id (TEXT, UNIQUE, "hf:cjpe:115651329"),
source, court, title, text, summary, label,
district, language, word_count, raw_metadata, imported_at
```

**How to run the harvest on Railway:**
1. Add a Volume at `/data` (see §5)
2. Railway → Headnote service → Run Command:
   ```
   pip install -r requirements-harvest.txt && python scripts/harvest_hf_corpus.py --subsets cjpe summ
   ```
3. Takes ~30 minutes. Verify via:
   ```
   curl https://headnote.up.railway.app/api/health | jq .hf_corpus
   ```
   Should show `{"total": 41946, "configured": true, ...}`

**Test search after harvest:**
```
GET /api/hf_search?q=bail+POCSO+minor+consent&source=cjpe,summ&limit=5
```

**Step 2 (not done yet):** Wire HF results into `/api/situation` retrieval. See §11.

---

## 8. The 42 curated cases

`headnote/data/cases.json` — 42 entries, hand-curated.

**Known data gap:** none of the 42 cases have a `kanoon_doc_id` field. So curated results don't show IK deep links. Action: backfill by searching IK for each case title (~₹21 one-time). Script would be ~30 min of work.

---

## 9. Browse view

Direct IK search with filters. Fixed in this session:
- **Court filter was broken**: dropdown was sending "madhya pradesh" (with space) which is an invalid IK doctype token. IK silently ignored it and returned all-courts results. Fixed: dropdown values now use correct IK doctype tokens (madhyapradesh, kolkata, chennai, etc.).
- `_HC_ALIASES` map in `app.py` provides backend robustness for common aliases.
- All 25 Indian High Courts now listed with full standard names.

---

## 10. Cost model (per query, approximate)

| Mode | LLM cost | IK cost | Total |
|------|----------|---------|-------|
| situation (Sonnet, no thinking, cache warm) | ₹3.80 | ₹0 (cache hit) | ₹3.80 |
| situation (Sonnet, no thinking, cold cache) | ₹3.80 | ₹1.30 | ₹5.10 |
| situation (Sonnet + thinking, no escalation) | ₹5.00 | ₹1.30 | ₹6.30 |
| situation (Sonnet + Opus escalation fired) | ₹45.00 | ₹1.30 | ₹46.30 |
| headnote (Opus + Haiku verify) | ₹15-30 | ₹0 | ₹15-30 |
| translate (Haiku) | ₹0.10 | ₹0 | ₹0.10 |

**IK daily cap:** ₹100 via `INDIAN_KANOON_DAILY_CAP_INR`. KanoonClient refuses calls past this.

---

## 11. Tests

`tests/` — 138 passing (as of last run).
```
test_model_router.py        — model selection, confidence parsing, cost calculation
test_endpoints_routing.py   — /api/situation, /api/digest, /api/headnote routing
test_translation.py         — Haiku translation + citation-preservation
test_telemetry_and_admin.py — telemetry recording + admin endpoint auth
test_headnote_pipeline.py   — Opus + Haiku verify integration
test_hidden_authorities.py  — 21 tests including "moat demonstration"
test_cost_dashboard.py      — admin dashboard + telemetry aggregation
test_parser.py              — IK HTML → ParsedJudgment
test_retrieval.py           — query distillation + hit ranking + hybrid pipeline
test_verify.py              — three-check verifier
```

Run: `source .venv/bin/activate && pytest tests/ -v`

---

## 12. Known issues / next-up

1. **Wire HF corpus into `/api/situation`** — Phase 2. Import is done, search is tested, but HF results don't flow into the main retrieval pipeline yet. To do: in `headnote/kanoon/retrieval.py`, after IK candidates collected, call `hf_search(query_tokens, limit=20)`, convert to `Candidate` shape, let Hidden Authorities reranker rank them alongside IK + curated.

2. **Curated cases missing `kanoon_doc_id`** — see §8. ~30 min of work.

3. **No SSE streaming yet** — right architectural fix for latency. Frontend would render cases as they arrive. ~1 day of work; flagged for v0.5.

4. **No auth / payment yet** — Supabase auth + Razorpay payments + Resend email. Pricing tiers already on the landing page (Free, Day Pass ₹99, Solo ₹499, Practice ₹1499).

5. **Two-phase pipeline lives at `headnote/situation_pipeline.py` but isn't wired in** — tried it on Render, calls serialized in production. Preserved for future test on Railway.

6. **BAIL subset not imported yet** — the Hindi district-court bail corpus (176K docs, ~1 GB). Add when you have a 3 GB Railway Volume. Run: `python scripts/harvest_hf_corpus.py --subsets bail`

7. **HF corpus has no embeddings** — keyword search only right now. To enable semantic search: run `scripts/backfill_embeddings.py` against the `hf_judgments` table (needs schema adaptation). Medium priority.

---

## 13. The directory map

```
headnote/
  __init__.py            # version "0.4.0"
  config.py              # all env vars, paths, pricing constants
  api/
    app.py               # FastAPI app, all routes (including /api/hf_search)
    models.py            # Pydantic request models
    admin.py             # /admin/* routes (bearer-token-guarded)
    telemetry.py         # query_telemetry SQLite table
  llm/
    router.py            # route_call() — model selection + cost metering
    client.py            # raw Anthropic SDK wrapper with prompt caching
    prompts.py           # all system + user prompt templates (v2 rubric)
    translation_prompts.py
  kanoon/
    client.py            # KanoonClient — IK API + SQLite cache + hf_judgments DDL
    parser.py            # IK HTML → ParsedJudgment
    retrieval.py         # retrieve_for_situation() pipeline
  retrieval/
    hidden_authorities.py  # rank_candidates() — the moat ranker
    embeddings.py          # fastembed BAAI/bge-small-en-v1.5 wrapper
    keyword.py             # curated corpus multi-facet scorer
    hf_corpus.py           # HF IL-TUR corpus search (new)
  translate_input.py     # Hindi → English pre-translation
  translate.py           # English → Hindi post-translation
  decompose.py           # Haiku query decomposition
  situation_pipeline.py  # UNUSED — two-phase pipeline kept for future
  verify.py              # three-check verifier
  data/
    cases.json           # 42 curated cases
    legal_hindi_terms.json
static/
  index.html             # /app — the work surface
  app.js                 # frontend logic, vanilla JS
  style.css              # design system
  landing.html           # / — marketing page
  admin-dashboard.html   # /admin/cost-dashboard
scripts/
  harvest_hf_corpus.py   # one-time IL-TUR bulk import (new)
  HARVEST_README.md      # Volume sizing + run instructions (new)
  backfill_embeddings.py # fastembed index builder
  ingest.py              # curated cases ingestion
  smoke_kanoon.py        # IK API smoke test
tests/                   # 138 tests
main.py                  # thin uvicorn shim; reads PORT from env
Dockerfile               # 2-stage, reads PORT in Python (Railway-compatible)
Procfile                 # web: python main.py
requirements.txt         # production deps (does NOT include datasets/tqdm)
requirements-harvest.txt # harvest-only deps: datasets, tqdm (new)
```

---

## 14. The founder context

- **Ayush is a solo non-lawyer founder** based in Bhopal. Pairs with a practising senior criminal advocate.
- **Pre-revenue.** Railway Hobby ($5/mo) + Anthropic credits are the only spend right now.
- **He's been burned by AI tools that returned hallucinated citations.** The three-check verifier exists because of that. Never regress on verification.
- **Hidden Authorities is the moat.** Famous landmarks (Bhajan Lal, Lalita Kumari, Arnesh Kumar, Dashrath, Bhaskaran) are what every junior already knows. We surface the case nobody has read. Regression = pulling famous cases up over obscure ones in hidden mode.
- **Quality > speed > cost.** In that order.
- **He prefers dashboard clicks over CLI commands.** Write instructions as "click X → Y → Z" not "run this shell command."
- **IK API is the primary source.** The 42 curated cases are last-resort fallback, not the primary corpus. Always IK first.

---

## 15. Things that didn't work (don't re-try without testing)

1. **Two-phase pipeline (Haiku select + parallel Sonnet generate).** Works locally. Serializes on Render — lost 3 hours. Code at `headnote/situation_pipeline.py`. Test on Railway before wiring in.
2. **Sonnet→Opus auto-escalation on confidence<7.** Was firing on most complex queries. Two stacked LLM calls = 60-90s = 502. Removed. **Currently OFF via `ENABLE_OPUS_ESCALATION=false`.**
3. **25-candidate pool + 10 IK doc fetches.** Cold-cache fetches alone consumed Render's 18s budget. Cut to 4 fetches.
4. **Verifier regen retry on Opus.** Added 30-60s latency. Failed cases are now dropped.
5. **`$PORT` in Dockerfile CMD as shell variable.** Railway exec-form override meant shell never expanded `$PORT`. Fixed: `main.py` reads PORT in Python via `os.environ.get("PORT", "8000")`.

---

## 16. Memory pointers for the next AI agent

- `headnote/api/app.py:api_situation` — heart of the product.
- `headnote/kanoon/retrieval.py:retrieve_for_situation` — retrieval pipeline.
- `headnote/retrieval/hidden_authorities.py:rank_candidates` — the moat.
- `headnote/llm/router.py:route_call` — model selection layer.
- `headnote/retrieval/hf_corpus.py:search` — new HF corpus search (Phase 1 done, Phase 2 = wire into situation).
- The model ladder lever is in `app.py` around `force_model_choice` (~line 345).
- Don't touch the Browse dropdown values — they're now IK doctype tokens (no spaces). If you add courts, use the IK token format, not display names.
- Run `pytest tests/` before pushing anything. 138 tests, fast.

---

**Owner of next steps:** Wire HF corpus into `/api/situation` (Phase 2, ~2 hours). Then backfill curated `kanoon_doc_id` (~30 min). Then auth + payments (Prompts #7-11).
