# HuggingFace IL-TUR Corpus Harvest

One-time bulk import of ~50K Indian legal judgments from the IL-TUR
benchmark (Exploration-Lab/IL-TUR on HuggingFace). After this, the
research endpoint has a permanent local corpus to search alongside the
42 curated cases and live IK API.

## What you get

| Subset | Court | Lang | Docs | DB size |
|--------|-------|------|------|--------|
| **CJPE** | Supreme Court | English | 34,816 | ~900 MB |
| **SUMM** | SC + High Courts | English | 7,130 | ~330 MB |
| **BAIL** | District Courts | Hindi | 176,000 | ~1,100 MB |
| **TOTAL (cjpe+summ)** | | | **~42K** | **~1.3 GB** |
| **TOTAL (all three)** | | | **~218K** | **~2.3 GB** |

## Pre-flight checklist

1. **Storage**: confirm where the SQLite file should live.
   - Local dev: defaults to `./kanoon_cache.sqlite`
   - Railway production: set `KANOON_CACHE_PATH=/data/kanoon_cache.sqlite` and mount a Volume at `/data`
   - **Railway Volume size**: 2 GB for cjpe+summ, 3 GB if you also import BAIL

2. **Disk for HF cache**: the `datasets` library caches downloaded parquet
   files in `~/.cache/huggingface/`. First run pulls ~1.6 GB; subsequent
   runs are instant. On Railway, this is ephemeral (lost on redeploy) —
   that's fine, the import is one-time.

3. **RAM**: the harvest streams rows, doesn't load full splits into
   memory. ~200 MB peak is plenty.

## Running it

### Local dev (fastest way to verify the pipeline)

```bash
cd Legify-restructure
source .venv/bin/activate
pip install -r requirements-harvest.txt

# Small test: 1000 rows from CJPE + SUMM (~3 minutes)
python scripts/harvest_hf_corpus.py --subsets cjpe summ --limit 1000

# Full English corpus (~25 minutes, ~1.3 GB)
python scripts/harvest_hf_corpus.py --subsets cjpe summ

# Full Hindi BAIL corpus (~45 minutes, +1 GB)
python scripts/harvest_hf_corpus.py --subsets bail
```

### Railway production (one-off command)

Railway's "Run Command" lets you execute a script against your service
without redeploying. From the Railway dashboard:

1. Open your Headnote service
2. Top right → **Run Command**
3. Paste:
   ```
   pip install -r requirements-harvest.txt && python scripts/harvest_hf_corpus.py --subsets cjpe summ
   ```
4. Click **Run**. Watch the logs — takes ~30 minutes for full import.

The download lands in `/data/kanoon_cache.sqlite` if your Volume is
mounted at `/data` (which is the default per the Dockerfile env vars).

### Verifying it worked

```bash
# Local dev
curl http://localhost:8000/api/health | jq .hf_corpus
# → {"total": 41946, "by_source": [{"source": "cjpe", "language": "en", "count": 34816}, ...], "configured": true}

# Production
curl https://headnote.up.railway.app/api/health | jq .hf_corpus
```

Then test a search:

```bash
curl 'http://localhost:8000/api/hf_search?q=bail+POCSO+minor+consent&source=cjpe,summ&limit=5' | jq .
```

## Re-running safely

The script uses `INSERT OR IGNORE` on `doc_id`, so re-running is
idempotent. Interrupt with Ctrl+C — partial data is committed in batches
of 500 and will not be re-fetched on the next run.

## Adding more subsets later

`_SUBSETS` in `scripts/harvest_hf_corpus.py` is a registry. Add a new
entry, give it a HF config name + court label + language, and the
existing flush logic handles the rest. The PCR (8K, prior-case
relationships) and LSI (66K, statute identification) subsets are
already documented in IL-TUR — add them when you need them.

## Wiring HF corpus into the research endpoint

This harvest only POPULATES the database. The retrieval pipeline still
defaults to curated + IK API — the HF corpus is searchable via
`/api/hf_search` and `/api/hf_doc/<id>` but isn't merged into
`/api/situation` results yet.

**To wire it in**, follow up by modifying `headnote/kanoon/retrieval.py`:

1. Import `from headnote.retrieval.hf_corpus import search as hf_search`
2. Inside the retrieval pipeline (after IK candidates collected),
   call `hf_search(query_tokens, limit=20)` and convert results to the
   same `Candidate` shape as IK hits.
3. Let the existing Hidden Authorities reranker do its job — HF results
   compete with IK + curated on the same relevance scale.

This is a deliberate Step 2 so you can validate the import + search
quality on its own before changing the production retrieval path.
