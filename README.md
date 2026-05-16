# Headnote

> Verified AI legal research for Indian criminal advocates. Journal-grade
> case research with every citation verified to source paragraph.

**Live beta:** <https://criminal-law-ai.onrender.com/>
**Stack:** Python 3.11 · FastAPI · Claude Opus 4.6 · Indian Kanoon API · local fastembed
**Status:** v0.4 — production-ready architecture; ~50 cached judgments growing organically with usage

---

## What it does

A lawyer describes a matter in plain English. Headnote returns the most
relevant precedents with structured headnotes, in either Cri.L.J. journal
format or compressed practitioner-notes format. Every cited case, paragraph
anchor, and quoted phrase is verified against source paragraphs before
being shown.

Three modes:

| Mode | Endpoint | What it does |
|---|---|---|
| Situation → Cases | `POST /api/situation` | Plain-English scenario → 3-5 most relevant precedents with structured headnotes |
| Topic → Digest | `POST /api/digest` | Doctrinal topic → research digest with cases grouped under sub-topic headings |
| Judgment → Headnote | `POST /api/headnote` | Full judgment text → lettered Cri.L.J. headnotes + practitioner notes |

Plus `/api/translate` (free Hindi via Google Translate, citations preserved
verbatim), `/api/feedback` (lawyer 👍/👎 to SQLite), `/api/spend` (live IK
cost ledger), and `/api/health` (config summary, no secrets).

---

## Why verification matters

On **27 Feb 2026** the Supreme Court (Narasimha & Aradhe JJ.) ruled that
citing AI-generated fake judgments constitutes **professional misconduct**,
not error — Bar Council can suspend or disbar.

Most legal-AI products treat citation verification as a "feature." Headnote
treats it as the floor. See [`headnote/verify.py`](headnote/verify.py).

The three checks, applied to every response:

1. **Existence** — every cited `case_id` must be in the evidence the LLM
   was actually shown. No citing cases from training memory.
2. **Anchor** — every `(Paras X, Y-Z)` must point to a paragraph that
   exists in the source. For older judgments lacking numbered paragraphs,
   the LLM is required to use `(p_NN)` IK paragraph IDs instead.
3. **Verbatim** — every quoted phrase is fuzzy-matched against the source
   paragraphs (threshold 0.88 — tolerates whitespace/punctuation drift,
   rejects fabrications which score < 0.6).

On failure: one regeneration retry with targeted feedback. Cache stays
warm so the retry costs ~₹15 vs ~₹38 for the original call.

---

## Architecture in one diagram

```
Browser ────► FastAPI ────► Retrieval ────► Claude Opus ────► Verification
              (app.py)      ┌─────────────┐                   ┌──────────┐
                            │ 1. Curated  │                   │ existence│
                            │ 2. Semantic │                   │ anchor   │
                            │ 3. IK live  │                   │ verbatim │
                            └─────────────┘                   └──────────┘
                              │                                    │
                              ▼                                    ▼ (if fails)
                       kanoon_cache.sqlite                  regen with feedback
                       (cache + embeddings)                       │
                                                                  ▼
                                                              respond
```

Full details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

---

## Quick start

```bash
# 1. Set up
git clone https://github.com/xyush14/Legify.git
cd Legify
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# 2. Configure
cp .env.example .env
# Edit .env: add ANTHROPIC_API_KEY and INDIAN_KANOON_TOKEN

# 3. Run
uvicorn main:app --reload --port 8000
open http://localhost:8000

# 4. Test
pytest tests/ -v
```

---

## Repository layout

```
.
├── headnote/                    Application package
│   ├── config.py                Single source of truth for settings
│   ├── verify.py                Three-check citation verification
│   ├── translate.py             Free Hindi (Google Translate)
│   ├── api/
│   │   ├── app.py               FastAPI app + routes
│   │   └── models.py            Pydantic request models
│   ├── kanoon/
│   │   ├── client.py            IK API client (cache, cost ledger, daily cap)
│   │   ├── parser.py            IK HTML → ParsedJudgment with paragraph tags
│   │   └── retrieval.py         Hybrid retrieval pipeline + prompt adapter
│   ├── retrieval/
│   │   ├── keyword.py           Curated-corpus keyword scorer
│   │   └── embeddings.py        Local fastembed + cosine search
│   ├── llm/
│   │   ├── client.py            Claude wrapper (caching, cost meter)
│   │   └── prompts.py           System + user prompt templates
│   └── data/
│       └── cases.json           42 hand-curated landmark judgments
├── static/                      Vanilla HTML/CSS/JS frontend (no build)
├── scripts/                     One-off CLI tools (backfill, ingest, smoke)
├── tests/                       Pytest suite (21 tests, ~2s)
├── docs/                        ARCHITECTURE, DEPLOYMENT, COMPETITORS
├── legacy/                      v0.2 Streamlit prototype (reference)
├── main.py                      uvicorn entrypoint (thin shim)
├── pyproject.toml               Modern packaging metadata
├── requirements.txt             Runtime deps (used by Render)
├── requirements-dev.txt         Dev deps (pytest, fastembed, etc.)
├── Dockerfile                   Two-stage production image
├── .dockerignore
├── .github/workflows/tests.yml  CI: pytest + ruff on every PR
├── render.yaml                  Render.com one-click deploy
├── Procfile                     Heroku-style deploy
├── runtime.txt                  Python version pin (3.11)
└── .env.example                 Template for local secrets
```

---

## Cost model

| Action | Cost | Notes |
|---|---|---|
| Curated keyword retrieval | ₹0 | 42 cases, instant |
| Semantic search | ₹0 | Local fastembed, ~20ms over 10k+ paragraphs |
| IK search call | ₹0.50 | Per /api/situation when curated+semantic isn't enough |
| IK doc fetch | ₹0.20 | Per *new* judgment; free forever after caching |
| Claude Opus (cache write) | ~₹38 | First call of session |
| Claude Opus (cache read) | ~₹15 | Subsequent calls within 5 min |
| Regeneration retry | ~₹15 | Only when verification fails |
| Hindi translation | ₹0 | Google Translate, no LLM call |

**Per-query typical (warm cache, no regen): ~₹15.**

Daily IK cap enforced *before* each call: default `₹100/day`, override
via `INDIAN_KANOON_DAILY_CAP_INR` in `.env`. See `/api/spend` for the
live ledger.

---

## Deploying

- Render (current production): set env vars, push to GitHub, done. See
  [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the persistent-disk
  setup so the IK cache survives restarts.
- Docker: `docker build -t headnote .` → portable to Fly.io, Cloud Run,
  App Runner, etc.
- Local: `uvicorn main:app --reload`.

Full instructions: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## Configuration

All settings via environment variables (or `.env`). See
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for the full table; the
essentials:

```dotenv
ANTHROPIC_API_KEY=sk-ant-...
INDIAN_KANOON_TOKEN=...
USE_IK_RETRIEVAL=1                    # turn on the IK+semantic pipeline
INDIAN_KANOON_DAILY_CAP_INR=100       # safety cap, in INR
```

Optional overrides: `KANOON_CACHE_PATH`, `FEEDBACK_DB`, `MODEL`, `MAX_TOKENS`.

---

## Limitations (honest list)

- **Curated corpus is 42 cases.** Indian Kanoon access brings ~26 lakh
  judgments within reach, but the cache only contains what's been queried.
  After ~1 month of usage at 50 queries/day, you'd have ~5,000 cached
  judgments — at which point the semantic index becomes genuinely useful.
- **Embedding model is general-purpose.** `BAAI/bge-small-en-v1.5` is a
  baseline. Swap to a legal-tuned model (e.g. Voyage `voyage-law-2`) for
  better Indian-legal-English semantics when ready to spend $5-10/mo.
- **No auth, no rate limiting, no monitoring yet.** All v0.5+.
- **SQLite for everything.** Single-writer; fine through ~100 concurrent
  lawyers, will need Postgres after that. See `docs/ARCHITECTURE.md`.
- **Render free tier has ephemeral disk.** Set
  `KANOON_CACHE_PATH=/data/...` and add a persistent disk, or accept that
  the cache rebuilds on every restart.

---

## Comparison with other Indian legal-AI tools

See [`docs/COMPETITORS.md`](docs/COMPETITORS.md) for how Headnote differs
from LexLegis, SCC, Manupatra, CaseMine, and Jhana.

---

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

[MIT](LICENSE) © 2026 Ayush Shivhare.

## Disclaimer

Experimental prototype. Always verify citations against the source judgment
before relying on them in court. After the Supreme Court's February 2026
ruling on AI-generated fake citations as professional misconduct, this
verification step is mandatory.
