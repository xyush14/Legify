# Headnote — Engineering Handoff

**Last updated:** 2026-05-18
**Author of this handoff:** Claude (Anthropic), via long pairing session with Ayush (founder, xyush14)
**Live URL:** https://criminal-law-ai.onrender.com (Render Free) — migrating to https://headnote.up.railway.app (Railway)
**Repo:** https://github.com/xyush14/Legify (main + claude/cost-optimization)

---

## 1. Product in one paragraph

Headnote is a verticalised AI legal research tool for Indian criminal-law advocates. The lawyer describes a factual matter; the system retrieves the most relevant precedents from a corpus (42 hand-curated cases + Indian Kanoon's ~26 lakh judgments fetched on demand), reranks via "Hidden Authorities" to surface obscure-but-relevant cases over famous landmarks, and writes a Cri.L.J.- or practitioner-format headnote with verified citations. Three modes: situation → ranked precedents (default), topic → research digest, judgment → headnote generation. The differentiator vs Jhana/Lawsome AI is the **fact-pattern-aware Hidden Authorities ranker** — they surface the same five landmark cases everyone knows; we surface the case that actually fits the lawyer's facts.

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
                     └──► SQLite (3 DBs):
                          ├─ kanoon_cache.sqlite — IK API responses (30-day search cache, forever doc cache)
                          ├─ feedback.db        — feedback table + query_telemetry table
                          └─ admin uses same feedback.db
```

**Frontend:** vanilla JS, no framework. Single-page app at `/app` with sidebar (Research / Browse / Drafting Coming Soon), composer with mode chips (hidden / famous / mixed), style chips (practitioner / cri.l.j.), jurisdiction picker, deep_mode toggle. Calm white-surface design (style.css) contrasting the loud CRED-style landing page (landing.html).

**Routes** (`headnote/api/app.py`):
- `POST /api/situation` — main retrieval+generation endpoint
- `POST /api/digest` — doctrinal topic → research digest
- `POST /api/headnote` — paste judgment text → Cri.L.J. headnotes (Opus + Haiku verifier)
- `POST /api/translate` — translate any English JSON result to Hindi via Haiku
- `POST /api/decompose` — Haiku call producing the "researching:" panel text
- `GET /api/browse/search` — direct IK passthrough with court/year/judge/statute/sort filters; falls back to curated when IK is offline
- `GET /api/browse/doc/{tid}` — single judgment fetch by IK doc id
- `POST /api/feedback` — thumbs up/down + comment
- `GET /admin/telemetry` — bearer-token-guarded cost/escalation/quality summary
- `GET /admin/cost-dashboard` — Chart.js dashboard reading the above

---

## 3. The retrieval pipeline (the most important + most contested part)

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

**Critical fixes recently shipped:**
- IK skip threshold REMOVED. Previously `Skipped IK search (saved ₹0.50): 5 cases already from curated+semantic` was firing on every query and IK never ran.
- `_distill_query` rewritten to favor legal-specific terms (acquittal, consent, voluntary, quashing, …) and aggressively dedupe + drop generic procedural English (accused, complainant, male, female, year, month). Before: `FIR POCSO Need POCSO Accused major male complainant years months Consensual`. After: `FIR POCSO Consensual rape consent acquittal majority evidentiary`.
- `_rank_search_hits` no longer produces negative scores in hidden mode (was breaking the downstream max-normalisation; curated always won).
- Per-source normalization in the CaseSummary→Candidate adapter (was global-max, curated dominated).

---

## 4. The model routing (calibrated for Render free tier)

`headnote/llm/router.py` — `route_call(task_type, payload, force_model)`

- **situation** default: Haiku 4.5 (chosen for Render free tier's ~18s budget; ~6-10s per call)
- **situation deep_mode=True**: Sonnet 4.6
- **digest** default: Sonnet 4.6
- **headnote** default: Opus 4.6 (the moat — pasting a judgment, generating proper Cri.L.J. headnotes)
- **headnote verification step**: Haiku 4.5 (cheap, ~50ms structural check)
- **translation**: Haiku 4.5
- **extraction** (decompose, query refine): Haiku 4.5

**Auto-escalation Sonnet→Opus is OFF** for the situation route. Was causing 60-90s timeouts. deep_mode is the only explicit escalation toggle.

**MODEL LADDER IS NOW ENV-VAR DRIVEN.** No code change needed when switching hosts. Three env vars:

| Var | Default | What it does |
|---|---|---|
| `SITUATION_MODEL` | `sonnet` | Model when deep_mode is OFF. Set to `haiku` on Render free for 6-10s latency. |
| `SITUATION_DEEP_MODEL` | `opus` | Model when deep_mode is ON. Set to `sonnet` on free-tier if Opus is too slow. |
| `ENABLE_SONNET_RERANKER` | `1` (on) | The single biggest case-relevance lever. Costs ~₹4 per query but turns "topically related" results into "factually aligned" results via a Sonnet fact-pattern judgment call. Set to `0` on free-tier to save the call + latency. |

Suggested presets:
- **Render Free:** `SITUATION_MODEL=haiku`, `ENABLE_SONNET_RERANKER=0`
- **Railway / Render Pro / VPS:** all defaults (Sonnet + reranker on)

---

## 5. Deployment state

**Current:** Render Free tier
- URL: https://criminal-law-ai.onrender.com
- Auto-deploys on push to `main`
- Env vars set in Render dashboard: `KANOON_API_TOKEN` (note: legacy name — code also reads `INDIAN_KANOON_TOKEN`), `ANTHROPIC_API_KEY`, `ADMIN_TOKEN`, `PYTHON_VERSION=3.11`
- **Known constraint:** request timeout ~18s, instance spins down after 15 min idle (causes cold-start 502s)

**Migrating to:** Railway
- URL: https://headnote.up.railway.app
- Env vars set in Railway: `ANTHROPIC_API_KEY`, `INDIAN_KANOON_TOKEN`, `INDIAN_KANOON_DAILY_CAP_INR=100`, `ENABLE_OPUS_ESCALATION=true`, `ADMIN_TOKEN`
- Uses Dockerfile (commit 6b1329f fixes the `$PORT` shell-expansion issue)
- Should give ~5min request budget; once stable, flip the model ladder back up

**Keepalive recommendation** (Render Free): set up cron-job.org or uptimerobot to ping `/api/health` every 5–10 min so the instance doesn't spin down.

---

## 6. The 42 curated cases

`headnote/data/cases.json` — 42 entries, hand-curated by Ayush + a senior criminal advocate.

**Known data gap:** none of the 42 cases have a `kanoon_doc_id` field. So when a curated case is returned in the result, its title isn't a clickable IK deep link. **Action item:** backfill `kanoon_doc_id` by mapping each curated case to its IK URL. A one-time ~₹21 IK search would do it (42 × ₹0.50). Until then, hidden-mode results show IK deep links and curated results don't.

---

## 7. Critical UX features shipped

- **Hidden Authorities** ranking mode (the moat) — hard-filters curated landmarks in hidden mode when IK has ≥3 candidates
- **Per-case Hindi toggle** ("हिंदी में दिखाएँ") — Haiku translation of ratio + fact-match + quote, citations stay English (per spec)
- **Bilingual strip** — when input is Devanagari, shows "आपकी क्वेरी: <orig> / translated to: <english>"
- **Progressive loading stages** — "translating → distilling → fetching judgments → reading candidates → generating → verifying" with paced timer animation
- **Outcome badges** — green for acquittal/quashed/bail-granted, red for conviction/bail-denied, neutral for dismissed/remand. LLM emits `outcome` field on each case.
- **Verified blue tick** badge — replaced earlier acid-green design after user feedback
- **Direct kanoon links** — every IK case carries `kanoon_url` and `kanoon_paragraph_url` (paragraph-anchored when LLM emits a `paragraph_anchor`)
- **Browse Judgments** view — direct IK search with court/year/judge/statute/sort filters; falls back to curated keyword search when IK is offline so the view always returns something

---

## 8. Cost model (per query, approximate)

| Mode | LLM cost | IK cost | Total |
|---|---|---|---|
| situation (Haiku, mixed mode, cache warm) | ₹0.50 | ₹0 (skip-IK fires) | ₹0.50 |
| situation (Haiku, hidden mode, cache warm) | ₹0.50 | ₹0.50 (search only) | ₹1.00 |
| situation (Haiku, hidden mode, cold cache) | ₹0.50 | ₹1.30 (₹0.50 search + 4×₹0.20 fetch) | ₹1.80 |
| situation (Sonnet, deep_mode, cold) | ₹4-6 | ₹1.30 | ₹5-7 |
| headnote (Opus + Haiku verify) | ₹15-30 | ₹0 | ₹15-30 |
| translate (Haiku, per result) | ₹0.10 | ₹0 | ₹0.10 |

**IK daily cap:** ₹100 (set in env via `INDIAN_KANOON_DAILY_CAP_INR`). KanoonClient refuses calls past this.

---

## 9. Tests

`tests/` — 138 passing.
- `test_model_router.py` — model selection, confidence parsing, cost calculation, prompt caching
- `test_endpoints_routing.py` — /api/situation, /api/digest, /api/headnote routing assertions
- `test_translation.py` — Haiku translation + citation-preservation verifier
- `test_telemetry_and_admin.py` — telemetry recording + admin endpoint auth
- `test_headnote_pipeline.py` — Opus + Haiku verify integration
- `test_hidden_authorities.py` — 21 tests for the ranker including the "moat demonstration"
- `test_cost_dashboard.py` — admin dashboard route + telemetry aggregation
- `test_parser.py` — IK HTML → ParsedJudgment
- `test_retrieval.py` — query distillation + hit ranking + hybrid pipeline
- `test_verify.py` — three-check verifier

Run: `.venv/bin/pytest tests/ -v`

---

## 10. Known issues / next-up

1. **Curated cases missing `kanoon_doc_id`** — see §6. ~30 min of manual work or one ~₹21 batch IK lookup script.
2. **Two-phase pipeline lives at `headnote/situation_pipeline.py` but isn't wired in** — the file is preserved for future use. We tried it; production showed sequential (not parallel) Phase 2 timing, suspected Anthropic SDK / httpx / Render-egress serialization. If you move to a paid Render plan or Railway, retest parallelism — it may work in those environments and unlock 5-case output without latency cost.
3. **No SSE streaming yet** — would be the right architectural fix for free-tier latency. Frontend would render cases as they arrive. ~1 day of work; flagged for v0.5.
4. **No auth / payment yet** — Supabase auth + Razorpay payments + Resend email transactional flows are the Prompts #7-11 in `~/Downloads/Headnote_Claude_Code_Prompts.md`. Pricing tiers already designed and rendered on the landing page (Free, Day Pass ₹99, Solo ₹499, Practice ₹1499).
5. **Browse view backed by curated fallback when IK is offline** — make sure the operator notices the "IK offline" warning banner in the UI.
6. **Sprint 2 spec items deferred:** comparison-table view backend (Sonnet pass to produce dedicated `fact_match` strings), per-result Hindi back-translation enhancements, judge-name auto-complete from IK.

---

## 11. The directory map (where to look first)

```
headnote/
  __init__.py            # version "0.4.0"
  config.py              # all env vars, paths, pricing constants, ADMIN_TOKEN
  api/
    app.py               # FastAPI app, all routes
    models.py            # Pydantic request models (SituationRequest, etc.)
    admin.py             # /admin/* routes (bearer-token-guarded)
    telemetry.py         # query_telemetry SQLite table + get_summary()
  llm/
    router.py            # route_call() — the model selection layer
    client.py            # raw Anthropic SDK wrapper with prompt caching
    prompts.py           # all system + user prompt templates
    translation_prompts.py
  kanoon/
    client.py            # KanoonClient — IK API wrapper with SQLite cache + cost ledger
    parser.py            # IK HTML → ParsedJudgment
    retrieval.py         # retrieve_for_situation() + _distill_query() + _rank_search_hits()
  retrieval/
    hidden_authorities.py  # rank_candidates() — the moat ranker
    embeddings.py          # fastembed BAAI/bge-small-en-v1.5 wrapper
    keyword.py             # curated corpus keyword scorer (prefilter_cases, score_case)
  translate_input.py     # Hindi → English pre-translation (Haiku + glossary)
  translate.py           # English → Hindi post-translation
  decompose.py           # Haiku query decomposition for the "researching:" panel
  situation_pipeline.py  # UNUSED — two-phase pipeline kept for future
  verify.py              # three-check verifier
  data/
    cases.json           # 42 curated cases
    legal_hindi_terms.json
static/
  index.html             # /app — the work surface (calm design)
  app.js                 # frontend logic, vanilla JS
  style.css              # calm white-surface design system
  landing.html           # / — marketing page (CRED neoPOP style)
  admin-dashboard.html   # /admin/cost-dashboard
tests/                   # 138 tests
main.py                  # 3-line shim: from headnote.api.app import app
Dockerfile               # 2-stage, port via $PORT (Railway-compatible)
render.yaml              # Render Blueprint config
Procfile                 # Render start command (uvicorn ... --port $PORT)
requirements.txt         # production deps
```

---

## 12. The founder context (so you don't ask wrong questions)

- **Ayush is a solo non-lawyer founder** based in Bhopal. Pairs with a practising senior criminal advocate for editorial review.
- **Pre-revenue.** Free tier hosting until paying subs land.
- **He's been burned three times by AI tools that confidently returned hallucinated citations.** The three-check verifier exists because of that. Never regress on verification discipline — drop cases over fabricating quotes.
- **Hidden Authorities is the moat.** Famous landmarks (Bhajan Lal, Lalita Kumari, Arnesh Kumar, Dashrath, Bhaskaran) are what every junior already knows. The product promise is to surface the case nobody else has read. If your changes pull famous cases up over obscure ones in hidden mode, you've regressed the moat.
- **Quality > speed > cost.** In that order. Don't degrade output to save ₹2.
- **He prefers being told what to do in the dashboard** rather than what to do in the CLI. He'll click through screens; he won't write shell commands.
- **He's wrestled with platform timeouts for hours.** If his next message is "still 502s", check Render's worker status before blaming the code.

---

## 13. Memory pointers for the next AI agent

If you're picking this up via Claude Code or similar:
- Read `headnote/api/app.py:api_situation` first. It's the heart of the product.
- Then `headnote/kanoon/retrieval.py:retrieve_for_situation` for the retrieval pipeline.
- Then `headnote/retrieval/hidden_authorities.py:rank_candidates` for the moat.
- The model ladder lives in `app.py` line ~340 (`force_model_choice`). That's the lever to pull when the host changes.
- The `claude/cost-optimization` branch has all the recent work; `main` is what Render/Railway deploys.
- Don't recreate the two-phase pipeline without first verifying parallel Anthropic calls work in the new host. Mock it locally first.

---

## 14. Things I tried that didn't work (so you don't re-try them)

1. **Two-phase pipeline (Haiku select + parallel Sonnet generate).** Right idea. ThreadPoolExecutor works locally. Failed on Render — generation calls serialized somehow (httpx pool? Anthropic SDK lock? Render egress?). Lost 3 hours debugging. Code preserved at `headnote/situation_pipeline.py` for future re-test on a better host.
2. **Sonnet → Opus auto-escalation on confidence<7.** Was firing on most complex queries (Sonnet honestly reports "medium" a lot). Two LLM calls stacked = 60-90s = 502. Removed structurally.
3. **Increasing candidate pool to 25 in hidden mode + fetching 10 IK docs.** Cold-cache fetches alone consumed Render's 18s budget. Cut to 4 fetches.
4. **Two IK search pages in hidden mode.** Same problem — ~2s of cold-cache search before the LLM even starts. Cut to 1 page; fame penalty in the reranker already surfaces obscure cases from page 0's 10 hits.
5. **Verifier regen retry on Opus.** When the first response fails verification, the legacy code tried to regenerate on Opus. With Sonnet default + Haiku tier, this added 30-60s of latency for marginal quality gain. Failed cases are now dropped instead.

---

**Owner of next steps:** Ayush's ML engineer per his message. Once they're in, the most useful first action is probably backfilling `kanoon_doc_id` on the 42 curated cases (§6) — fastest visible quality improvement. Then run the same POCSO acquittal query and confirm the IK results returned actually match the facts (test of the Hidden Authorities ranker end-to-end).

Feel free to ping back with questions — this handoff is mid-flight.
