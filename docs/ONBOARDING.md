> **Headnote — End-to-End Engineering & Operations Onboarding**
>
> The single living document for anyone (human or AI) joining Headnote. Read this first.
> It explains **what we're building, what's live, what's in flight, what we use, how to run it,
> and how to restore your AI pair-programmer ("Claude") on a new subscription or machine.**
>
> | | |
> |---|---|
> | **Live app** | <https://headnote.in> |
> | **Repo** | <https://github.com/xyush14/Legify> (`main` branch) |
> | **Hosting** | Railway — auto-deploys on every push to `main` |
> | **Stage** | v0.4 — paid SaaS (auth + payments + drafter + verified research) |
> | **Maintainer** | Ayush Shivhare ([@xyush14](https://github.com/xyush14)) |
> | **This doc last updated** | 2026-06-18 |

---

## 0. How this doc is maintained (read me)

This is the **source of truth for orientation**, not a code mirror. It links out to the deeper
docs instead of duplicating them. Keep it alive:

- **When anything structural changes** (a new product surface, a deploy change, a workstream starts/finishes,
  a provider swap, a new convention), update the affected section **and** add a dated line to the
  [Changelog](#15-changelog-living) at the bottom.
- The fastest way to keep it current: at the end of a working session, ask Claude *"update docs/ONBOARDING.md
  with what we changed today."* It already has the context and will edit the right sections + append the changelog.
- **Do not** paste secrets, API keys, or tokens here. Environment variables are referred to by **name only**.
- Other docs this one points to (all in `docs/` unless noted): `ARCHITECTURE.md`, `DEPLOYMENT.md`,
  `COMPETITORS.md`, `WHATSAPP_BOT_PRD.md`, `DRAFTING_ARCHITECTURE.md`, plus `README.md`, `HANDOFF.md`
  and `VISHNU_REVIEW.md` at the repo root.

> ⚠️ **Where the older docs are stale.** `README.md` and `docs/DEPLOYMENT.md` still say "Render" and
> `criminal-law-ai.onrender.com`, and describe a 42-case free beta with no auth. **That is out of date.**
> The truth as of today: hosting is **Railway** (`headnote.in`), it's a **paid SaaS** with Supabase auth +
> Cashfree payments, and there's a **38,277-judgment Supreme Court corpus** on top of the curated cases.
> `render.yaml` / `Procfile` in the repo are stale leftovers — ignore them. This doc is the corrected view.

---

## 1. What Headnote is (the product in plain English)

**Headnote is a vertical AI tool for Indian criminal-law advocates.** Tagline: *"Journal-grade case
research with every citation verified to source paragraph."*

A lawyer describes a matter in plain English (or Hindi); Headnote returns the most relevant precedents
with structured, court-style headnotes — and **every cited case, paragraph anchor, and quoted phrase is
verified against the source before it's shown.** It also drafts court-ready litigation documents.

**Two moats:**

1. **Verification-as-product (the regulatory moat).** Every research answer passes a three-check verifier
   (existence → anchor → verbatim). This exists because of a real regulatory shift — see §6.3.
2. **Hidden Authorities (the discovery moat).** The reranker is built to surface the *obscure-but-on-point*
   judgment that fits the lawyer's facts, not the five landmark cases every junior already knows.

**Stage & pricing:** v0.4 paid SaaS. Plans: Demo 14d free / Weekly ₹120 / Monthly ₹499 / Yearly ₹4,999
(public brochure pitches ~₹5,999/yr). Positioned ~8–12× cheaper than SCC Online (₹36–72k/yr) and
Manupatra (₹24–48k/yr). A dormant "Partner" tier exists for law publishers.

**Competitors:** see `docs/COMPETITORS.md`. The benchmark incumbent is **SCC Online** (its AI product is
SCC Online AI Pro, RAG-grounded, no post-hoc verification). The differentiation thesis is *not* to clone
SCC — it's to win the full criminal-litigator workflow (research → verify → draft → file → cite) **in Hindi,
at solo price, with verification as the product.**

---

## 2. The team & who does what

| Who | Role | Notes |
|---|---|---|
| **Ayush Shivhare** ([@xyush14](https://github.com/xyush14)) | Solo founder, full-stack builder | Based in Bhopal, MP. **Non-lawyer** building in the legal vertical — frame legal-domain assumptions explicitly. Cares about regulatory defensibility and per-call cost economics (tracks $ and ₹). Prefers dashboard clicks over CLI where possible. |
| **Senior advocate ("Vishnu ji")** | Editorial supervisor | Practising criminal advocate, ~26 years at the Bar. His **real filed documents** are the gold standard for the drafting engine. Relationship locked, not yet on cap table (founder TODO). |
| **Claude (Anthropic)** | AI pair-programmer | Most code + docs are produced in long pairing sessions. See §14 for how to restore this collaborator on a new account/machine. |

---

## 3. Tech stack at a glance

| Layer | Choice |
|---|---|
| **Language / runtime** | Python 3.11 (pinned in `runtime.txt`) |
| **Web framework** | FastAPI + Uvicorn |
| **Frontend** | Vanilla HTML / CSS / JS — **no framework, no build step**. Served from `static/`. |
| **Datastores** | SQLite everywhere: `kanoon_cache.sqlite` (IK + embeddings cache), `feedback.db` (feedback + telemetry), `judgments.sqlite` / `judgments_core.sqlite` (SC open-data corpus) |
| **Auth** | Supabase (JWT) |
| **Payments** | Cashfree |
| **Email** | Resend (transactional: welcome, subscription, renewal, access grants) |
| **LLM (product calls)** | **DeepSeek-first** (V3 fast / R1 deep). Groq Llama-3.3-70B free fallback. Gemini fallback. Claude configured but used sparingly (cost). See §8. |
| **Embeddings** | Local `fastembed` (`BAAI/bge-small-en-v1.5`, 384-dim) — ₹0, ~20ms |
| **PDF export** | WeasyPrint (+ Pango/HarfBuzz for Devanagari shaping) |
| **Word `.docx`** | `docxtpl` (Jinja2 + python-docx) + **Kruti Dev 010** legacy-font encoding for MP court filings |
| **Case retrieval** | Indian Kanoon API (discovery) + AWS Open Data SC/HC corpora (court-accepted) |
| **Distribution** | WhatsApp (Meta Cloud API / Twilio) + Bolna voice agent |
| **Hosting / CI** | Railway (Docker) + GitHub Actions (`pytest` + `ruff`) |

---

## 4. Run it locally

```bash
# 1. Clone & set up
git clone https://github.com/xyush14/Legify.git
cd Legify
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Configure
cp .env.example .env
# Edit .env — at minimum the keys you want to exercise (see §13). Product LLM calls
# want DEEPSEEK_API_KEY; case retrieval wants INDIAN_KANOON_TOKEN.

# 3. Run
python main.py            # reads $PORT (default 8000); or:
uvicorn main:app --reload --port 8000
open http://localhost:8000

# 4. Test
pytest tests/ -v
```

`main.py` is a thin shim that reads `PORT` from the environment (this is what makes Railway happy — see §10).
VS Code launch configs live in `.claude/launch.json` (`hn`, `app`, etc., all on port 8099).

> **Local-dev gotchas (important):**
> - **LLM/OCR keys live only in prod** (Railway env), *not* in local `.env`. So live LLM drafting, FIR OCR
>   (Groq), and PDF generation can't be fully exercised locally — verify those on prod or with stubs/`TestClient`.
> - Running under `~/Downloads/...` can hit a macOS sandbox issue where `uvloop`/`h11` are blocked. If a
>   dev server won't boot, fall back to FastAPI `TestClient` or `python3 -m uvicorn main:app`.
> - **LibreOffice is not required/used** — `.docx` is produced via `docxtpl`, not a conversion server.

---

## 5. Repository map

```
.
├── headnote/                     ← the application package
│   ├── config.py                 single source of truth for settings (env-driven)
│   ├── verify.py                 three-check citation verification (the regulatory moat)
│   ├── translate.py              free Hindi (deep-translator/Google)
│   ├── statute_map.py            IPC↔BNS / CrPC↔BNSS / Evidence↔BSA concordance
│   ├── api/                      FastAPI routes
│   │   ├── app.py                main app + research/admin endpoints  ← heart of the product
│   │   ├── payments.py           Cashfree create-order / webhook / verify
│   │   ├── whatsapp.py           WhatsApp webhooks (Meta + Twilio)
│   │   ├── bolna.py              Bolna voice-agent endpoints
│   │   └── pdf.py, case_viewer.py, admin.py, telemetry.py, ratelimit.py …
│   ├── llm/                      client.py (multi-provider + fallback), router.py (model routing), prompts.py
│   ├── kanoon/                   client.py (IK API + cache + cost ledger), parser.py, retrieval.py
│   ├── retrieval/                hidden_authorities.py (the ranker), embeddings.py, keyword.py, hf_corpus.py
│   ├── judgments/                opendata.py (SC corpus + FTS5 full-text), resolver.py (Range-GET PDFs)
│   ├── drafter/                  the drafting engine — see §6.4
│   ├── whatsapp/                 bot logic + providers/{meta,twilio}.py
│   ├── email/                    Resend templates
│   ├── entitlements/             Supabase subscription / plans
│   ├── payments/                 cashfree.py, referrals.py
│   └── data/                     cases.json (curated landmark set), statute_mappings.json
├── static/                       vanilla-JS frontend (landing, /app, draft-*.html, case-viewer, admin)
├── scripts/                      one-off CLIs: corpus ingest/extract, harvest, scrapers, Bolna push
├── tests/                        pytest suite
├── docs/                         ARCHITECTURE, DEPLOYMENT, COMPETITORS, WHATSAPP_BOT_PRD, this file …
├── .claude/                      skills/ (headnote-legal-drafting), launch.json, settings.local.json
├── migrations/                   SQL migrations (e.g. 007_bolna_sales_pipeline.sql)
├── legacy/                       v0.2 Streamlit prototype (reference only)
├── main.py                       uvicorn entrypoint (reads $PORT)
├── Dockerfile                    production image (CMD ["python","main.py"])
├── render.yaml / Procfile        ⚠️ STALE — not used; deploy is Railway
└── judgments_core.sqlite         ~14MB SC core, tracked in git + baked into the image (see §6.2)
```

Deeper structure & history: `README.md` (partly stale, see §0) and `HANDOFF.md` (May 2026 engineering handoff
— good for the retrieval pipeline & model-routing internals, predates payments + the SC corpus).

---

## 6. How the system works

### 6.1 Research pipeline (the core)

```
Browser → FastAPI (/api/situation) → Retrieval → LLM generation → Three-check verification → respond
                                      ├ 1. curated keyword (42 cases, ₹0)
                                      ├ 2. local semantic (fastembed, ₹0)
                                      ├ 2.6 SC full-text (FTS5 over the open-data corpus)
                                      └ 3. Indian Kanoon live (paid, capped)
                                      → Hidden Authorities reranker (fact-pattern aware)
```

Entry point: `headnote/api/app.py` → pipeline in `headnote/kanoon/retrieval.py::retrieve_for_situation`.
The ranker is `headnote/retrieval/hidden_authorities.py`. Full diagram + rationale: `docs/ARCHITECTURE.md`.

**Three research modes:**

| Mode | Endpoint | What it does |
|---|---|---|
| Situation → Cases | `POST /api/situation` | scenario → 3–5 precedents with structured headnotes |
| Topic → Digest | `POST /api/digest` | doctrinal topic → grouped research digest |
| Judgment → Headnote | `POST /api/headnote` | full judgment → lettered Cri.L.J. headnotes + practitioner notes |

The **six-element journal headnote schema** is the format moat: `statute_index`, `catchword_chain`, `ratio`,
`negative_carve_out`, `paragraph_anchor`, `per_judge_attribution` (+ a parallel practitioner block).

### 6.2 The Supreme Court open-data corpus (court-accepted layer)

Headnote ships its own **court-accepted source layer** alongside Indian Kanoon, because *IK is a research
aggregator, not an authorized report* — a citation "verified to IK" is a crack a judge can reject.

- **38,277 reported SC judgments, 1950–2026**, each with the **neutral citation** (`2024INSC735`) +
  **SCR citation** + CNR + parties/judges/date. Ingested from the AWS Open Data bucket
  `indian-supreme-court-judgments` (CC-BY-4.0).
- **Tap → official signed PDF**: PDFs live in per-year `english.tar` on S3; we store each PDF's byte
  offset/size and serve it with a single HTTP **Range GET** (LRU-cached on disk) — **zero of the ~52GB
  stored on our server.**
- **Cross-resolution:** every SC case the pipeline finds via IK is matched into the corpus (neutral → SCR →
  parties+year), so an aggregator hit gets returned *with* its official copy + an "⚖ official SC copy" badge.
- **SC-first ordering** enforced in retrieval's choke point and again on the final result list.
- **Full-text discovery (Stage 2.6):** an FTS5 (BM25) index over extracted judgment text makes the SC corpus
  a first-class fact-pattern source. Code: `headnote/judgments/opendata.py`.

**Shipping shape (matters for deploy):** the full text-bearing DB is ~1GB, too big for the volume. So prod
gets a **~14MB core** (`judgments_core.sqlite`, tracked in git + baked into the image) that lights up
SC-first ordering + official citations + tap-to-PDF immediately. Full-text discovery is **inert until
`JUDGMENTS_FULL_URL`** points at a hosted text DB (a public HuggingFace dataset). See §11 for the live status.

### 6.3 Why verification is mandatory (the regulatory anchor)

*Gummadi Usha Rani v. Sure Mallikarjuna Rao*, **2026 SCC OnLine SC 341**, decided **2026-02-27**
(Narasimha & Aradhe JJ.). The Court — ruling on a matter where a **trial-court judge** cited four fabricated
judgments — observed that relying on fake citations *"would be a misconduct,"* issued notices to the Bar
Council of India, and (May 2026) sought a BCI AI expert panel.

> **Nuance / messaging guardrail:** there are **no formal BCI AI guidelines yet**. Marketing copy that says
> "filing AI citations = disbarment" **overstates** it — soften such claims. Fight on verification + Hindi +
> price, not fear. (Logged because the brochure has done this.)

This is why **verification never regresses**: accuracy under the misconduct standard outranks UX polish.

### 6.4 Drafting engine

The drafting strategy has **pivoted** to a clear, founder-locked principle:

> **Reproduce a real filed document verbatim as a deterministic, paragraph-by-paragraph template.
> Hard-code the fixed legal language exactly from Vishnu ji's filing; only the client *variables* and the
> case-specific *facts narrative* fill in; conditional grounds are toggles. NO LLM writes legal text** —
> OCR/voice only *read* uploads. The bar is `headnote/drafter/templates/bail_application.py` and the page
> `/draft/bail`. Court format/CSS must match it exactly.

Why: earlier approaches (a) LLM-generating the whole document from a prose spec, and (b) an auto-templatizer
that re-encoded whole lines, both lost verbatim fidelity and were rejected. The rule is dead simple: **keep
the filing exactly, change only the variables.**

There are **three render modes** in the codebase, in order of preference:

1. **Deterministic verbatim templates** (preferred) — `headnote/drafter/templates/*.py`, e.g.
   `bail_application.py`, `discharge_239.py`. Pages: `/draft/bail`, `/draft/discharge` (with charge-sheet/FIR
   OCR, live preview, save/resume, PDF, voice, EN/HI). **Live on `main`.**
2. **Deterministic client-side JS builders** — instant, no LLM (the latency cure); high-traffic docs migrate here.
3. **LLM template engine** (`headnote/drafter/compose.py`, `/draft/template/{type}`) — 41 templates, but it
   regenerates the whole doc via DeepSeek on every edit → **5–15s blocking latency = the #1 demo drop-off**.
   Being retired in favour of (1)/(2).

Indian-court specifics: MP district filings use the legacy **Kruti Dev 010** font (ASCII-mapped, *not*
Unicode). Pipeline = Unicode field values → transliterate English names to Devanagari → Kruti Dev encode →
`docxtpl` fill. The `.docx`/auto-templatizer lane ("Option A") is **parked off-`main` on branch
`drafting-rebuild`** — not deployed. Full spec: `docs/DRAFTING_ARCHITECTURE.md`. Type-by-type review tracker:
`VISHNU_REVIEW.md`.

> **Drafting review discipline (don't trip on these):** judge correctness against the
> `headnote-legal-drafting` skill + the real filings, **not** your own idea of "correct Hindi." Two things
> that look like bugs but are **intentional court conventions**: `यहकि` written solid, and `____` underscore
> fill-blanks. Vishnu ji's gold-standard filings are gitignored under `templates_reference/` and already
> transcribed into the skill — **don't re-ask for them.**

---

## 7. Product surfaces & routes

| Area | Routes (representative) | Notes |
|---|---|---|
| **ASK mode** | `/api/chat/message` (SSE) | "AI for lawyers" chat; DeepSeek→Groq stream, statute-map grounded, no-bluff; SPA `data-view="ask"`. See §15 (2026-07-04) |
| **Research** | `/api/situation`, `/api/digest`, `/api/headnote`, `/api/browse/*`, `/api/hf_search`, `/api/judgment/*` | core engine; SC corpus endpoints under `/api/judgment` |
| **Drafting** | `/draft/bail`, `/draft/discharge`, `/draft/template/{type}`, `/api/draft/*` (start, render-live, pdf, ocr-fir, transcribe) | see §6.4 |
| **Auth** | `/api/me`, `/api/auth-verify` | Supabase JWT |
| **Payments** | `/api/payments/create-order`, `/api/payments/webhook`, `/api/payments/verify` | Cashfree |
| **WhatsApp** | `/api/whatsapp/webhook` (Meta), `/api/whatsapp/twilio/webhook` | research + drafting over DMs |
| **Voice (sales)** | `/api/bolna/webhook`, `/api/bolna/tools/*` | outbound sales agent |
| **Admin / ops** | `/api/health`, `/api/spend`, `/api/config`, `/admin/*` | `/api/health` = liveness + config summary (no secrets); `/api/spend` = IK cost ledger |

---

## 8. LLM providers & cost policy

**Policy (founder directive):** product LLM calls **default to DeepSeek, not Claude** — *"claude is very
expensive, I'll not switch to claude."* Use:

- `deepseek-reasoner` (R1) for **deep** tasks (research, headnote generation).
- `deepseek-chat` (V3) for **fast/latency-sensitive** tasks (live-preview drafting, translation, extraction) —
  R1's 60–180s is too slow there.
- **Groq** Llama-3.3-70B as the **free last-resort fallback** (and the primary engine for FIR OCR).
- **Gemini** as an additional fallback.
- **Claude** is kept configured but only used when explicitly asked — it is **not** the product default.

Implementation: the multi-provider client + auto-fallback chain is `headnote/llm/client.py`
(`call_claude_cached` / the DeepSeek/Groq path); model routing is `headnote/llm/router.py`. Provider is
env-driven (`LLM_PROVIDER`; prod runs `deepseek`), so switching tiers needs **no code change**.

> Historical note: `HANDOFF.md` (May 2026) documents a Claude Sonnet/Opus routing table and Anthropic cost
> economics. That predates the DeepSeek-first cost decision — treat the **DeepSeek-first policy above as
> current**. Some config *defaults* in code may still name Claude; verify against this policy before relying on them.

---

## 9. External integrations & accounts

| Service | Used for | Where | Env vars (names only) |
|---|---|---|---|
| **DeepSeek** | primary product LLM | `headnote/llm/client.py` | `DEEPSEEK_API_KEY`, `LLM_PROVIDER` |
| **Groq** | free LLM fallback + FIR OCR | `headnote/drafter/ocr.py`, llm client | `GROQ_API_KEY` |
| **Anthropic / Gemini** | LLM (sparing / fallback) | llm client | `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` |
| **Indian Kanoon API** | case discovery (₹0.50 search / ₹0.20 doc) — **discovery only, not authoritative**; attribute "powered by IKanoon" | `headnote/kanoon/client.py` | `INDIAN_KANOON_TOKEN`, `INDIAN_KANOON_DAILY_CAP_INR` |
| **AWS Open Data (S3)** | official SC/HC judgment PDFs (no creds; Range GET) | `headnote/judgments/resolver.py` | — |
| **HuggingFace** | hosts the shippable full-text corpus + IL-TUR import | bootstrap + `scripts/` | `HF_TOKEN`, `JUDGMENTS_FULL_URL` |
| **Supabase** | auth + subscriptions/entitlements | `headnote/entitlements/_supabase.py` | `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET`, `SUPABASE_SERVICE_ROLE_KEY` |
| **Cashfree** | payments | `headnote/payments/cashfree.py` | `CASHFREE_APP_ID`, `CASHFREE_SECRET_KEY`, `CASHFREE_ENV`, `CASHFREE_WEBHOOK_SECRET` |
| **Resend** | transactional email | `headnote/email/*` | `RESEND_API_KEY`, `WELCOME_FROM_EMAIL`, `APP_BASE_URL` |
| **Meta / Twilio** | WhatsApp delivery | `headnote/whatsapp/providers/*` | `WA_PROVIDER`, Meta: `WA_*`; Twilio: `TWILIO_WA_*` |
| **Bolna** | outbound voice sales | `headnote/api/bolna.py` | `BOLNA_API_KEY`, `BOLNA_AGENT_ID`, `BOLNA_API_BASE`, `BOLNA_WEBHOOK_SECRET` |

Access control / comps: `ADMIN_TOKEN`, `FOUNDER_EMAILS`, `PARTNER_EMAILS`, `YEARLY_GRANT_EMAILS`,
`MONTHLY_GRANT_EMAILS`.

---

## 10. Deployment & ops

- **Hosting is Railway** (Hobby plan). Live at **headnote.in**. Deploy = Dockerfile
  (`CMD ["python","main.py"]`) + a **`/data` volume** for the SQLite DBs.
- **Deploy trigger:** `git push origin main` → Railway auto-deploys. **CI does *not* gate the deploy** — the
  GitHub Actions workflow (`.github/workflows/tests.yml`: import check + `pytest` on 3.11/3.12 + `ruff`) runs
  on push but ships regardless. Run `pytest tests/` locally before pushing.
- **The Railway fix that made it work:** clear the "Start Command" field in Railway → Settings → Deploy so it
  uses the Dockerfile `CMD`. Railway's injected exec-form command broke `$PORT` shell expansion; `main.py`
  reads `PORT` in Python to sidestep that.
- **Required Railway env vars** (set in the dashboard, not in git): the LLM keys, `INDIAN_KANOON_TOKEN`,
  `ADMIN_TOKEN`, `KANOON_CACHE_PATH=/data/...`, `JUDGMENTS_DB=/data/judgments.sqlite`, Supabase/Cashfree/Resend
  keys. Full table in §13 and `docs/DEPLOYMENT.md`.
- **Static-asset gotcha:** page/CSS changes need a browser **hard-refresh (Cmd+Shift+R)** to bypass cache.
  (E.g. the drafting header restyle only renders on a *generated draft document*, not the empty form.)
- **Ignore `render.yaml` / `Procfile`** — stale.

---

## 11. Active workstreams (what's happening right now)

> Status as of 2026-06-18. Keep this section honest — it's the "what's in flight" a new dev most needs.

| Workstream | Status | Where / next step |
|---|---|---|
| **Drafting rebuild** (verbatim deterministic templates) | **Live** for bail + §239/498A discharge on `main` | `/draft/bail`, `/draft/discharge`. Next: build more types as Ayush sends real filings; get Vishnu's feedback. |
| **Drafting catalogue audit** (`/draft/template` LLM engine) | Fixes done **static-only, uncommitted** | Sanitizer + 3 cause-titles + `दं.प्र.सं.` standardized + 3 dedupe redirects. Blocking item: latency (full-doc regen) → migrate high-traffic docs to deterministic JS builders. Pending Vishnu sign-off in `VISHNU_REVIEW.md`. |
| **`.docx` native drafter** ("Option A") | **Parked off-`main`** on branch `drafting-rebuild` | Superseded by the verbatim-template approach; not deployed. |
| **SC full-text moat → prod** | **Blocked on 3 things** | (1) text extraction finishing; (2) build + upload `judgments_full.sqlite.gz` to a public HF dataset (`HF_TOKEN` needed); (3) **set Railway env `JUDGMENTS_FULL_URL`**. Until then prod runs "healthy degraded" (SC-first + official copies work; full-text discovery is dark). |
| **WhatsApp bot** (distribution) | PRD landed; dev path chosen | Full PRD: `docs/WHATSAPP_BOT_PRD.md`. Dev/soft-launch on **Twilio sandbox**; prod path is Meta Cloud API direct (gated on FB Business Verification). v1 scope is tight — don't expand it. |
| **Bolna voice sales** (distribution) | Scaffolded, **not yet dialing** | `headnote/api/bolna.py` (6 endpoints), `migrations/007_*.sql`, prompts in `docs/bolna_agent_*.md`. Blocked on a phone number + filling `.env` placeholders, then re-run `scripts/push_bolna_agent.py`. Always check `dnd_list` before dialing (TRAI/DND). |
| **Case memory** (idea, not committed) | Brainstorm | Record client intake → structured, searchable case record. The transcribe primitive already ships (`/api/draft/transcribe`). Real gate = long-form async + consent/privilege/DPDP. |
| **Courtbook roadmap** | Research done | `courtbook.in` is a free generic template bank — **do not clone its text**. Use only as a roadmap of draft types to build natively (family, consumer/CPA, MACT, PIL gaps). |
| **IK re-anchoring + SCC benchmarking** | Ongoing strategic threads | Re-anchor verification on neutral citations + official text (see §6.2); position against SCC on verification + Hindi + price (see §1). |

---

## 12. Conventions, taste & hard rules

- **Verification never regresses.** The three-check verifier is the moat and the regulatory floor (§6.3).
- **Product LLM calls default to DeepSeek, never Claude** unless explicitly asked (§8).
- **Drafting = verbatim, deterministic.** No LLM writes legal text; keep the filing exactly, change only
  variables (§6.4). Verify Hindi against the skill, not intuition.
- **Design aesthetic:** reject the generic "AI-SaaS" look (dark neon-gradient hero, pulsing status dots,
  mono-everything). Favour a **light, editorial, paper-first** aesthetic in the spirit of `neatlogs.com`:
  ivory/cream backgrounds, **Geist** sans body with **JetBrains Mono** reserved for labels/eyebrows/citations,
  a restrained **deep-gold** accent, green for "verified", dark sections only as occasional contrast. For UI
  work, show a rendered screenshot for reaction — don't declare done from a diff.
- **CTAs:** one clear primary CTA per viewport, rendered as **static HTML above the fold at first paint**
  (never JS-gated/auto-hidden). Lead the free offer with **"Start free — no card"**, *not* the trial duration.
- **Brand/PDF pipeline:** logo is `static/headnote-logo.svg` (use the file, don't retype). Marketing PDFs are
  built HTML → headless Chrome → PDF. Details + palette: memory note `reference_brand_collateral`.
- **Founder priorities, in order:** **quality > speed > cost.**

---

## 13. Environment variables reference (names only)

Set these in `.env` locally (only what you exercise) and in the **Railway dashboard** for prod. **Never commit
real values.** Full descriptions in `docs/DEPLOYMENT.md`.

```
# Core
LLM_PROVIDER  MODEL  MAX_TOKENS
DEEPSEEK_API_KEY  GROQ_API_KEY  ANTHROPIC_API_KEY  GEMINI_API_KEY

# Retrieval / corpus
INDIAN_KANOON_TOKEN  USE_IK_RETRIEVAL  INDIAN_KANOON_DAILY_CAP_INR
JUDGMENTS_DB  JUDGMENTS_CORE_URL  JUDGMENTS_FULL_URL  HF_TOKEN
KANOON_CACHE_PATH  FEEDBACK_DB  JUDGMENTS_PDF_CACHE  JUDGMENTS_PDF_CACHE_MB

# Research tuning (env-driven, no code change to flip)
SITUATION_MODEL  SITUATION_DEEP_MODEL  ENABLE_SONNET_RERANKER
ENABLE_THINKING  THINKING_BUDGET_TOKENS  ENABLE_OPUS_ESCALATION  PREFILTER_TOP_K

# Auth / entitlements
SUPABASE_URL  SUPABASE_ANON_KEY  SUPABASE_JWT_SECRET  SUPABASE_SERVICE_ROLE_KEY
ADMIN_TOKEN  FOUNDER_EMAILS  PARTNER_EMAILS  YEARLY_GRANT_EMAILS  MONTHLY_GRANT_EMAILS

# Payments / email
CASHFREE_APP_ID  CASHFREE_SECRET_KEY  CASHFREE_ENV  CASHFREE_WEBHOOK_SECRET
RESEND_API_KEY  WELCOME_FROM_EMAIL  WELCOME_REPLY_TO  APP_BASE_URL

# WhatsApp / voice
WA_PROVIDER  WA_VERIFY_TOKEN  WA_ACCESS_TOKEN  WA_PHONE_NUMBER_ID  WA_APP_SECRET  WA_API_VERSION
TWILIO_WA_FROM  TWILIO_WA_MEDIA_BASE_URL
BOLNA_API_KEY  BOLNA_AGENT_ID  BOLNA_API_BASE  BOLNA_WEBHOOK_SECRET
```

---

## 14. ⭐ How to "get Claude back" on a new subscription or machine

> This is the part the founder specifically asked for. **Read this once so a subscription change never scares you.**

### 14.1 The one idea that makes this easy

Your **Claude subscription / account is just authentication + billing + model access.** It is
**interchangeable.** Logging in with a different account does **not** erase or change "Claude" for this project.

Everything that makes Claude *your* informed collaborator on Headnote lives in **plain files on your machine
and in this Git repo** — none of it is stored inside the subscription. Back those files up and you can
reconstitute Claude on **any machine with any account in minutes.**

### 14.2 The four things that *are* "Claude" for Headnote

| # | What | Where it lives | Travels with…|
|---|---|---|---|
| 1 | **Memory** (the accumulated knowledge of you, the project, decisions, preferences — ~17 fact files + an index) | `~/.claude/projects/<project-path>/memory/` | **Your machine.** Not the account. |
| 2 | **Skills** (e.g. `headnote-legal-drafting` — the legal knowledge moat) | `.claude/skills/` **inside this repo** | **Git** ✅ (auto) |
| 3 | **MCP servers** (connected tools: the Outline/Loop wiki, Fireflies, Chrome, Preview, scheduled-tasks…) | `~/.claude.json` (per-project keys) — **contains secrets/tokens** | Your machine (secrets) |
| 4 | **Settings & permissions** | `~/.claude/settings.json` (global) + `.claude/settings.local.json` (this repo's command allowlist) | mixed |

There is currently **no `CLAUDE.md`** in the repo — this `docs/ONBOARDING.md` + the memory files play that
role. (You can add a `CLAUDE.md`; being in git, it would travel automatically.)

**The exact memory path for this project right now:**

```
/Users/ayushshivhare/.claude/projects/-Users-ayushshivhare-Downloads-Legify-0bb187ba264e218517be944dbf64c433be6ae19d/memory/
```

That long folder name is **just the project's absolute path with `/` replaced by `-`**
(`/Users/ayushshivhare/Downloads/Legify-0bb187…` → `-Users-ayushshivhare-Downloads-Legify-0bb187…`). It is
**deterministic from the folder path** — which matters for restore (below).

### 14.3 Scenario A — same machine, new Claude subscription/account

**Nothing to restore. It just works.** Switching the account you log in with does not touch `~/.claude/` or
the repo.

1. Keep Claude Code installed. Run `claude` (or `/login`) and sign in with the **new** account.
2. Make sure the new plan includes the model you use (Opus-class models need the higher Pro/Max tier; or set
   an Anthropic **API key** instead of a subscription login).
3. Open this project folder. Claude automatically loads the memory for this path + the repo's skills. **"Claude
   is back," fully.**

### 14.4 Scenario B — new machine (or new folder path)

Memory is keyed by the **absolute folder path** (§14.2). On a fresh machine — or if you clone the repo to a
different path — the memory won't auto-match unless you bring it across. Steps:

1. **Install Claude Code** and log in (any account).
2. **Get the repo:** `git clone https://github.com/xyush14/Legify.git`. This restores items #2 and #4 above
   (skills + `settings.local.json`, if tracked) for free.
3. **Restore memory (#1):** copy your backed-up `memory/` files into the new machine's project memory dir.
   Two reliable ways:
   - **Match the path:** clone to the *same absolute path* you used before, so the auto-generated memory folder
     name matches and Claude picks it up automatically; then drop the files in.
   - **Or just ask Claude:** put the old `memory/` files anywhere, start Claude in the project, and say *"import
     these memory files into your memory for this project"* — it will recreate them at the right location.
4. **Restore MCP servers (#3):** either copy `~/.claude.json` across (then re-authenticate — see below), or
   re-add each server with `claude mcp add …`. The ones connected today: the **Outline/Loop wiki**, **Fireflies**,
   **Chrome control**, **Claude Preview**, **scheduled-tasks**, **mcp-registry**.
5. **Re-authenticate OAuth MCP servers.** Tokens in `~/.claude.json` are often account/device-bound and may not
   transfer — expect to re-login to the wiki, Fireflies, etc.

### 14.5 Your backup checklist (do this now, once)

The whole point: a subscription lapse should never cost you context.

- ✅ **Keep the repo pushed to GitHub.** Skills, this onboarding doc, `docs/`, and `settings.local.json` all
  travel with it.
- ✅ **Back up `~/.claude/` periodically** — especially `~/.claude/projects/<this-project>/memory/`. A simple
  copy to a private, encrypted location (private Git repo, the Loop Outline, or an encrypted archive) is enough.
- ✅ **Back up `~/.claude.json` securely** (it has MCP tokens — treat like secrets; encrypt it).
- ⚠️ **Do NOT commit `~/.claude/memory/` or `~/.claude.json` into this repo.** The repo is public-style and the
  memory holds business strategy + the MCP file holds tokens. Keep those in a **private** backup.

> Want this bulletproof? Ask Claude to *"set up a private backup of my Claude memory and MCP config."* It can
> script a one-command export of the memory folder (and a redacted inventory of the MCP servers) to a private
> destination you choose.

### 14.6 TL;DR

**The subscription is replaceable; your context is in files you own.** Push the repo to GitHub + back up
`~/.claude/` and `~/.claude.json`, and you can bring Claude back — with all of Headnote's history — on any
machine with any account, in minutes.

---

## 15. Changelog (living)

> Append a dated line whenever something structural changes. Newest on top.

- **2026-07-04** — **Civil drafting is now DETERMINISTIC — 8 CPC-plaint templates (the biggest civil-quality jump).**
  Civil matters were previously LLM-authored (good, but review-heavy); now the eight civil suit types render
  as verbatim, zero-fabrication deterministic plaints, the same moat model as bail/discharge. New shared
  **`headnote/drafter/templates/_civil.py`** engine builds the whole CPC Order VII skeleton — cause-title
  (pan-India via compose_court_name), parties, type-specific facts, cause of action, jurisdiction, valuation
  & court-fee, limitation, lettered PRAYER (सहायता अ/ब/स…), and verification (Order VI Rule 15) — bilingual,
  no LLM. Eight thin modules supply only their statute + fact/prayer paras: `recovery_suit` (§34 interest),
  `injunction_suit` (§38 SRA + O39 companion), `specific_performance` (§10 SRA — §16(c) readiness averment
  hard-coded so it's never omitted), `declaration_suit` (§34 SRA proviso), `partition_suit` (two-decree),
  `eviction_suit` (State rent-control Act — never assumes MP), `consumer_complaint` (§35 CPA 2019, District
  Commission), `written_statement` (Order VIII — objections + para-wise reply + special pleas, signed by the
  defendant). Wired through the full stack: `template_adapter.CANONICAL_MAP`/`LABELS` (editor + schema),
  `from_prompt._DETERMINISTIC` + `_FORCE_COURT` (the classifier now routes civil matters to these instead of
  the authored engine), and a new **Civil Court (7) + Consumer Commission (1)** group in the browse catalogue
  (`compose_templates.py`). Total canonical templates 42 → 50. Verified: all 8 render bilingual (sample +
  empty), editor schema + full document render, prompt-first routing (non-MP cause-title, facts filled, no MP
  leak); civil bodies carry NO case-law (cite-at-hearing only) — deterministic assembly means nothing is
  fabricated. Follow-up: build these from Vishnu's real filed civil formats where available; verified civil
  citation ledger still pending.

- **2026-07-04** — **ASK mode shipped — the "AI for lawyers" chat (uncommitted).** New flagship surface in the
  /app SPA (`data-view="ask"`, first sidebar + bottom-nav item); research/drafting/etc. untouched. Streamed
  token-by-token over **SSE**: `POST /api/chat/message` in `headnote/api/chat.py` → events `{type:delta|error|done}`;
  new `stream_chat()` in `headnote/llm/client.py` (DeepSeek `stream=True`, V3 fast / R1 via a `deep` toggle,
  Groq fallback — never raises). Grounded, not trained: `_grounding_block()` injects authoritative BNS/BNSS rows
  from `statute_map.lookup()` into a **no-bluff** system prompt (never invents a citation → "confirm at hearing").
  Gated up-front via `can_use_feature` (SSE can't 402 mid-stream); meter recorded in `finally` (never `yield` there);
  `PlanLimit("chat",20,"lifetime")` on DEMO only (funnel; unlimited on paid). Frontend ASK module (app.js IIFE):
  `fetch`+ReadableStream (not EventSource — needs Bearer), safe mini-markdown renderer where `##` → mono uppercase
  section labels and `>` → statute blockquote, blinking caret, action rail (copy · 👍/👎 · gold "Draft this"
  link-out). Presentation = the structured-brief look (mono labels + blockquote, gold scoped to the draft link).
  Verified live in preview (real Groq stream, section headings + blockquote render, zero console errors). v1.5 TODO:
  wire `verify.py` for real Verified badges + case-law links; persist thread; 👍/👎 → eval set.
- **2026-07-04** — **Pan-India Phase 2: the 34 canonical templates are now State-driven too.** Follow-up to
  the pan-India engine below — the criminal/family/civil canonical template modules no longer default to MP.
  Every `compose_court_name(..., "म.प्र."/"M.P.")` and every `a.get("state_name") or "म.प्र."` fallback across
  31 template files was changed to read the matter's `state_name` (blank placeholder when absent, never MP);
  hardcoded fallback court-strings with a placeholder city dropped "(म.प्र.)". A `state_name` field (and, where
  the composer needs it, `court_city`) was added to the 9 live templates that read state but hadn't declared it
  (writ, complaint_156, habeas, ni_138_dismiss, restitution, divorce_13, stay, reply, mention_memo) so the
  field-extractor fills it from the prompt. `quashing` (which hardcoded an MP HC string) now composes from the
  State + bench; `vakalatnama`'s MP default was neutralised. Verified: all 32 registered modules render with
  NO MP leak on non-MP data (e.g. UP bail → "…इलाहाबाद खण्डपीठ लखनऊ", Rajasthan writ → "…राजस्थान खण्डपीठ जयपुर",
  Tamil Nadu maintenance → "…Chennai (Tamil Nadu)"), MP back-compat exact, 21 drafter tests still pass. Sample
  DEFAULTS keep MP cities (illustrative demo data only). `cheque`/`mact` take `court_name` as a direct field by
  design (no composition). The 4 legacy bail/discharge variant modules are off the live registry.
- **2026-07-04** — **Drafter went PAN-INDIA — no more Madhya Pradesh hardcoding.** Headnote now serves
  advocates in every State/UT, so the drafting engine had to stop assuming MP. The MP assumption funnelled
  through one chokepoint — `compose_court_name()` in `headnote/drafter/templates/_doc_header.py`, whose HC
  branch *ignored the state entirely* and always emitted "मध्यप्रदेश खण्डपीठ …" (a Rajasthan or Tripura writ
  came out as MP High Court). Fix: a new `_HIGH_COURTS` directory (all 25 HCs — Hindi+English name, principal
  seat, benches) + `_STATE_TO_HC` (every State/UT/abbrev → its HC) + `_hc_record`/`_hc_seat`/`_compose_hc`.
  `compose_court_name(level, city, state, …)` is now state-aware: the State selects the correct High Court,
  the district selects its bench ("In the High Court of Bombay at Bombay, Nagpur Bench"; Allahabad→Lucknow;
  Madras→Madurai; Rajasthan→Jaipur/Jodhpur; Gauhati→Kohima/Aizawl/Itanagar; P&H; J&K wings; Calcutta circuit
  benches). Nothing defaults to MP — unknown State/city ⇒ blank `____` placeholder (never a wrong-forum guess,
  per [[feedback_court_location]]). MP back-compat preserved exactly (MP Hindi bench cause-title still renders
  "माननीय उच्च न्यायालय मध्यप्रदेश खण्डपीठ ग्वालियर" — Vishnu's format). Prompts de-MP'd: `HOUSE_STYLE`
  (author.py) now says "across ALL States/UTs", carries a State→HC map + "never write Madhya Pradesh for a
  non-MP matter", and language follows the forum's region (Hindi-belt → Devanagari, else formal court English)
  instead of "default Hindi"; the CIVIL addendum + eviction brief use the matter's State rent-control/court-fee
  Act (MP Accommodation Control Act is now just one example among Maharashtra/Delhi/WB/TN/Rajasthan); the
  classifier (`from_prompt.py`) and the सुझाव reviewer (`suggest.py`) are pan-India. NOTE (follow-up): the ~34
  criminal/family canonical template modules are still MP-idiom (Vishnu's filed formats) — they now compose the
  RIGHT HC via the chokepoint when a State is passed, but their call sites still default `state="म.प्र."`;
  threading the matter's State into all 34 field-specs is Phase 2. Legacy `compose.py`/`compose_templates*.py`
  prompt-builders still name MP but are off the live authored/canonical path.
- **2026-07-03** — **App-wide fact-grounding guard — the drafter can no longer silently invent facts.**
  During a demo a civil draft invented an entire fact pattern (a "deceased wife", "parents as defendants",
  names/dates/amounts) that was nowhere in the lawyer's matter — the exact failure the zero-fabrication rule
  exists to prevent. Root cause: the drafter had a hard guard for invented **citations** and **BNSS↔CrPC
  section pairs**, but **nothing checked invented facts** — and when an LLM is handed a rich draft skeleton
  and a thin brief, the pressure to look complete overrides any "don't invent" instruction. Fix is the fact
  analog of the citation guard, in `headnote/drafter/author.py`: `_ground_index()` indexes the advocate's
  own input (typed brief / OCR'd case papers); `_mark_grounding()` scans the generated draft for concrete
  **fact atoms** — specific dates (`dd.mm.yyyy`), money amounts (`Rs …`, `…/-`), and person-names after a
  relationship/`namely` marker — and wraps any atom NOT traceable to the input in `<mark class="fab">`,
  accumulating them; `_grounding_warnings()` emits one aggregated ⚠ line. Placeholders (`____`) never flag;
  a generic-role stoplist keeps "the plaintiff" etc. from flagging; **empty source ⇒ every fact flags**
  (a draft built from no facts is unverifiable by definition). Wired into **all four generation paths** —
  `render_authored` (authored + refine) and `render_mirrored` (reference + refine), each threading the
  right `source` (brief for authoring/mirror — the reference's own facts are another client's case and
  NEVER count as verification; prior-draft+instruction for refine). Canonical templates are unaffected
  (they render only user-entered fields — no LLM invention). Result dicts now carry `ungrounded: [...]`.
  UI (`static/index.html`, style `?v=20260703b`): a loud red `.pd-note--fab` "Verify these details" card
  pinned above suggestions, listing each atom, mirrored by the inline amber highlights in the draft (kept
  as an underline in print). Prompt hardened too: the ZERO-FABRICATION block gained a "GROUNDING CONTRACT"
  ("when the input is thin, write a thin draft — a draft full of ____ is correct; an invented story is a
  career-ending fabrication"). Known tradeoff (deliberate): an amount/date written in WORDS in the brief
  but DIGITS in the draft may false-flag — biased to flag, because a false flag costs one glance and a
  missed fabrication costs the lawyer's licence.
- **2026-07-03** — **Reference-mirror rebuilt to full fidelity + print CSS fixed (a lawyer's complaint).**
  A lawyer uploaded his filed Agartala plaint as a style reference and got back a mismatched draft
  (house MP header instead of his recital-first cause-title, invented facts, missing schedule/affidavit/
  list-of-documents, and a printout with no margins from page 2). Root causes: the reference was
  compressed to a ~10-line "skeleton" and then force-rendered through the fixed `render_header()` house
  format, and `doc_page()` had no `@media print`/`@page` at all. Fix: new **mirror engine** in
  `author.py` — `MIRROR_SYSTEM` + `mirror_document()` (model sees the reference **verbatim**, returns
  the whole document as typed layout blocks) + `render_mirrored()` (deterministic mr-* renderer:
  recital-first labels, party blocks with the designation pinned right, auto-numbered paras, lettered
  prayer items, tables, page-broken companion pages; same citation/section guards). Two-source rule in
  the prompt: structure/boilerplate from the reference, **facts only from the typed brief**, `____` for
  unknowns, never invent. `from_prompt.py` reference path tries mirror first (draft language follows
  the reference), falls back to the old skeleton path; `/refine` detects `mr-doc` markup and revises
  through the block engine so a refine never strips the matched format (`revise_mirrored()`).
  `_doc_header.py` gained `PRINT_CSS` (A4 `@page` 1-inch margins on **every** printed page, card
  chrome stripped in print, break-inside/break-after hygiene) and `doc_page(title=…)` so the browser
  print header shows the draft's name. Gotcha found on the way: a CSS comment containing `hdr-*/cb-*`
  terminates at the inner `*/` and silently eats the next rule.
- **2026-07-03** — **सुझाव rail shipped — live drafting suggestions beside every prompt-drafted document.**
  New `headnote/drafter/suggest.py` + `POST /api/draft/suggest`: sections check (expected provision +
  BNSS↔CrPC pair guard + criminal-code-in-civil flag), missing mandatory paras (one guarded DeepSeek
  call diffing the draft against the type's skeleton — degrades to a "limited" note offline), a
  per-type limitation clock, companions and labelled authorities. Frontend: `fetchSuggestions()` in
  `static/index.html` renders a `pd-note--sug` card atop the result notes (CSS in `style.css`,
  `?v=20260703a` cache-bust); **+ जोड़ें** routes the suggested para through the existing guarded
  `/refine` path — nothing ever auto-inserts, the advocate is the gate. Canonical drafts skip the LLM
  missing-check (`llm:false` — their paras are complete by construction).
- **2026-07-03** — **Civil drafting upgraded from one generic bucket to eight first-class suit types.**
  The prompt-drafter's `other_civil` catch-all is now the true residual: the classifier
  (`from_prompt.py`) gained specific keys — `recovery_suit`, `injunction_suit`, `specific_performance`,
  `declaration_suit`, `partition_suit`, `eviction_suit`, `written_statement`, `consumer_complaint` — each
  with its own `TYPE_BRIEFS` entry in `author.py` (controlling test + mandatory CPC plaint paras +
  companions + curated `cite_candidates` offered to **cite-at-hearing only**; civil body whitelist stays
  empty until Vishnu ji verifies a civil ledger). A `CIVIL DRAFTING ADDENDUM` is injected into the
  authoring prompt for civil types (O7 plaint paras, मूल्यांकन/न्यायशुल्क, §34 CPC interest, O6 R15
  verification, lettered सहायता prayer, "no BNSS/CrPC in a civil pleading" + a render-time guard that
  flags it). `_doc_header.py` gained **civil / district_judge / consumer** cause-titles, and
  `_authored_court()` stops the classifier's criminal-forum guess from leaking a Sessions/Magistrate
  cause-title onto a plaint. Also fixed: the `writ` heuristic matching the substring in "written
  statement". Verified: offline suite green + live Groq classify 5/5.
  Office files aren't images, so they take a **separate path**: extract text directly (python-docx for
  Word, openpyxl for Excel → Markdown tables) and **skip vision OCR**; the extracted text then feeds the
  same downstream flow (draft prefill / field extraction / searchable vault). New module
  **`headnote/drafter/office.py`** (`office_kind`, `extract_office_text`, and `collect_uploads`, the shared
  validate-and-split helper). `ocr.py` gained a text field-extractor (`_extract_fields_from_text`) and an
  `office_text=` kwarg threaded through `_run_ocr` + all `ocr_*_pages` + `ocr_text_pages`. Wired into all
  drafter OCR endpoints (`from-document`, `ocr-fir`, `ocr-bail-order`, `ocr-impugned-order`, `ocr-generic`),
  the **document vault** (`/api/documents/upload` — office docs stored as text-only, no page image), the
  **WhatsApp** bail flow (`ocr_for_draft`), and every frontend `accept=` string (7 inputs + 8
  `compose_templates` zones + the `draft-template.html` dynamic default). Modern formats only — legacy
  `.doc/.xls` return a clear "save as .docx/.xlsx" message. `openpyxl>=3.1` added to `requirements.txt`.
  Verified live: Hindi FIR + English cheque-matter `.docx`/`.xlsx` extract to correct structured fields.
- **2026-06-27** — Smart Drafter **rebranded onto the app design system** + **language auto-detect**. The voice
  page (`static/draft-smart.html`, `/draft/smart`) was a one-off **dark** theme (Inter, custom `--bg-0`
  palette) that clashed with the rest of the app; rewrote its inline CSS to the canonical light system
  (`style.css` tokens — `--bg #fafaf9`, Geist + Geist Mono, hairline borders, calm monochrome, **gold scoped
  to the drafting signature**: the orb is now a gold sphere on light, the mic is gold, hands-free-on is gold).
  Same visual language as `cases.html`/`index.html`; self-contained (no `style.css` link — avoids `.composer`/
  `.chip`/`.toast`/`.topbar` class collisions, the established per-draft-page convention). **Language now
  auto-detects from the lawyer's first words** (`detectLang` = any Devanagari → `hi`, else `en`; `maybeAutoSwitchLang`
  in `sendMessage`): page opens in **English** by default, flips the whole UI to Hindi the moment they speak/type
  Hindi (and back); the EN/हिं toggle still works and sets `state.autoLang = false` to lock their manual choice.
  Verified via node preview (light theme, EN default, auto-switch both ways, manual-lock, a real Groq conductor
  turn, mobile) — zero console errors. The conductor itself is unchanged. NOTE: for local browser testing without
  full-app/auth, `.preview_tmp/server.js` now stands in `GET /api/draft/templates`, `POST /api/draft/compose`
  (real conductor on the Groq key, via `scripts/_studio_voice.py`), and `/api/config`+`/api/lawyer-profile` stubs.
- **2026-06-26** — Voice: shipped a shared client engine **`static/voice.js`** (`window.HeadnoteVoice`) and
  rewired the broken voice input across the draft section. One dual-path STT (Web Speech API primary +
  MediaRecorder → `POST /api/draft/transcribe` Groq-Whisper fallback) so the mic now works on **every**
  browser, not just Chrome — plus TTS read-back (`speechSynthesis`, hi-IN/en-IN) and barge-in. The **Smart
  Drafter** (`static/draft-smart.html`, `/draft/smart`) gained a true **hands-free conversation loop**:
  assistant speaks each conductor question → auto-opens the mic → transcribes → advances; new hands-free +
  speaker-mute toggles in the composer, `#btn-mic` is push-to-talk/interrupt, orb gains an `is-speaking`
  state. The per-field mics in the **template editor** (`static/draft-template.html`) now use the same engine
  (previously returned early when `SpeechRecognition` was absent, so they never rendered on Firefox/webviews).
  **No backend change** — `/api/draft/transcribe` (Whisper) and `/api/draft/compose` (conductor) already
  existed and work (`GROQ_API_KEY` set). NEXT (flagged, not done): wire the conductor's final generation to
  the canonical V2 engine (`template_adapter.document`) so a talked-through draft matches template-editor
  quality — needs a doc-type + field-key map between `compose.py` TEMPLATES and `template_adapter.CANONICAL_MAP`.
- **2026-06-23** — Drafting: added 4 deterministic builders to the bail/discharge standard —
  `templates/anticipatory_bail.py` (§482/438), `maintenance.py` (§144/125, कुटुम्ब-न्यायालय), `appeal_conviction.py`
  (§415/374), `vakalatnama.py`, plus a shared `templates/_review_shell.py` (DRY court-paper CSS). Anticipatory,
  maintenance and appeal are **verbatim-reconciled** against Vishnu ji's real `.docx` (decoded via
  `scripts/kruti_to_unicode.py`); vakalatnama is a standard form (no filing). Registered in `stories.py`
  **`ready=False`** (out of the product picker — proposals pending advocate sign-off), each reviewable at
  `/draft/{anticipatory,maintenance,appeal,vakalatnama}/review`. House-style now locked: `यहकि` solid, `बनाम`,
  party label on the right, no `प्रार्थना` heading. NEXT: Vishnu review → flip `ready=True` + build the full
  form/OCR pages (like `/draft/discharge`).
- **2026-06-18** — Created this onboarding doc. Captured current truth (Railway not Render; DeepSeek-first not
  Claude; v0.4 paid SaaS with Supabase auth + Cashfree; 38,277-judgment SC corpus with the full-text moat
  still gated on `JUDGMENTS_FULL_URL`). Documented the verbatim-template drafting pivot, the active
  distribution threads (WhatsApp, Bolna), and the full "get Claude back" playbook (§14).

---

## 16. Glossary (for a dev new to the Indian legal domain)

| Term | Meaning |
|---|---|
| **BNS / BNSS / BSA** | The 2023 codes that replace **IPC / CrPC / Evidence Act**. `headnote/statute_map.py` holds the concordance. |
| **Cri.L.J.** | Criminal Law Journal — the journal-headnote house style Headnote emulates. |
| **Headnote** | (the legal term) the editor-written summary at the top of a reported judgment. Also our product name. |
| **Neutral citation** | A court-assigned, publisher-independent citation (SC: `2024INSC735`) — the court-accepted anchor we re-anchor on. |
| **SCR** | Supreme Court Reports — the official report series; its citation form (`[2024] 10 S.C.R. 108`). |
| **Indian Kanoon (IK)** | A judgment **aggregator** with a paid API. Great for discovery; **not** court-accepted as authoritative. |
| **Kruti Dev 010** | A legacy ASCII-mapped Hindi font that MP district-court filings use (not Unicode). Drafts must encode to it. |
| **§437/§438/§439 / §239** | Bail (regular/anticipatory) and discharge provisions — the highest-volume draft types. |
| **Vakalatnama** | The document authorising an advocate to appear for a client. |
| **Hidden Authorities** | Our reranker that surfaces obscure-but-on-point judgments over famous landmarks. |
| **e-SCR / digiscr / ecourts** | Official, signed, free judgment sources (the court-accepted text layer). |
