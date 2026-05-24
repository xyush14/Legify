# Headnote — Deployment

> Three supported paths: Render (current), Docker (portable), local dev.

## Required configuration

Set these as environment variables (in `.env` locally, in the hosting
platform's secrets UI in production). **Never commit the `.env` file.**

| Variable | Required? | Default | Notes |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | Yes | — | `sk-ant-...` |
| `INDIAN_KANOON_TOKEN` | Yes (for IK retrieval) | — | Get / rotate at <https://api.indiankanoon.org/> |
| `USE_IK_RETRIEVAL` | No | `false` | `1` to enable the IK+semantic pipeline |
| `INDIAN_KANOON_DAILY_CAP_INR` | No | `100` | Per-day spend cap; blank = no cap |
| `KANOON_CACHE_PATH` | No | `./kanoon_cache.sqlite` | **Must point to persistent storage in production** |
| `FEEDBACK_DB` | No | `./feedback.db` | Same — needs persistent storage |
| `MODEL` | No | `claude-opus-4-6` | Override to test other models |
| `MAX_TOKENS` | No | `2500` | Per-response token cap |

## Path A — Render.com (current deploy at criminal-law-ai.onrender.com)

```bash
# 1. Push to GitHub (private repo recommended).
git push origin main

# 2. In the Render dashboard:
#    New -> Blueprint -> connect repo
#    Render reads render.yaml and creates the service.

# 3. Add env vars in: service -> Environment
#    ANTHROPIC_API_KEY = sk-ant-...
#    INDIAN_KANOON_TOKEN = ...
#    USE_IK_RETRIEVAL = 1
#    INDIAN_KANOON_DAILY_CAP_INR = 100
```

**Free tier caveat:** Render free instances sleep after 15 min idle and
have **ephemeral disk** — the kanoon cache + feedback DB are wiped on
every restart. For real use:

- Upgrade to Starter ($7/mo) for always-on.
- Add a Persistent Disk and set `KANOON_CACHE_PATH=/data/kanoon_cache.sqlite`,
  `FEEDBACK_DB=/data/feedback.db`.

## Path B — Docker (portable)

```bash
# Build (without local embeddings — smaller image)
docker build -t headnote:latest .

# Build with embeddings support (~150MB larger)
docker build --build-arg INSTALL_EMBEDDINGS=1 -t headnote:emb .

# Run, mounting persistent storage for the SQLite caches
docker run --rm -p 8000:8000 \
  --env-file .env \
  -v $(pwd)/data:/data \
  headnote:emb

# Health check
curl http://localhost:8000/api/health
```

The image:
- Runs as non-root `headnote` UID 10001
- Has a `HEALTHCHECK` directive (`/api/health` every 30s)
- Reads `KANOON_CACHE_PATH=/data/kanoon_cache.sqlite` and `FEEDBACK_DB=/data/feedback.db`
- Listens on `0.0.0.0:8000`

### Deploying the Docker image

| Target | How |
|---|---|
| Fly.io | `fly launch` from project root; it'll pick up the `Dockerfile`. |
| Google Cloud Run | `gcloud run deploy --source .` |
| AWS App Runner | Point at the GitHub repo; auto-build from `Dockerfile`. |
| Render | Set runtime to Docker in dashboard (alternative to the Python builder). |

## Path C — Local development

```bash
# 1. Clone
git clone https://github.com/xyush14/Legify.git
cd Legify

# 2. Set up venv
python3.11 -m venv .venv
source .venv/bin/activate

# 3. Install
pip install -r requirements.txt -r requirements-dev.txt

# 4. Configure
cp .env.example .env
# Edit .env to add ANTHROPIC_API_KEY and INDIAN_KANOON_TOKEN

# 5. Run
uvicorn main:app --reload --port 8000

# 6. Test
pytest tests/ -v
```

## Smoke checks after every deploy

```bash
BASE=https://your-deploy.com   # or http://localhost:8000

# Liveness + config visibility (no secrets exposed)
curl -s $BASE/api/health | python3 -m json.tool

# Curated corpus count
curl -s $BASE/api/corpus | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["count"], "cases")'

# IK cost ledger (only if USE_IK_RETRIEVAL=1)
curl -s $BASE/api/spend | python3 -m json.tool

# A real request (uses ~₹20 of Claude tokens, may use IK)
curl -s -X POST $BASE/api/situation \
  -H 'Content-Type: application/json' \
  -d '{"situation":"Cheque dishonour notice sent to wrong address","style":"journal"}' \
  | python3 -m json.tool
```

## Monitoring & alerts (recommendations)

| Concern | What to watch | Where |
|---|---|---|
| Cost runaway | `today_total_inr` from `/api/spend` | Add a cron that pings `/api/spend` every 15 min, alert if `today_remaining_inr < 10`. |
| Verification failures | `meta.verification.clean == false` | Log every response; track failure rate. Goal: <5%. |
| Cold-start latency | First request after restart | Render free tier wakes in ~30s. Switch to paid for SLA. |
| Cache hit rate | `meta.ik_cache_hits / (ik_cache_hits + ik_fetch_calls)` | Should rise over time. If flat, the cache may be on ephemeral disk. |

## Rotating secrets

| Secret | How to rotate |
|---|---|
| `ANTHROPIC_API_KEY` | <https://console.anthropic.com/> → rotate → update env var → no restart needed (lazy client init). |
| `INDIAN_KANOON_TOKEN` | <https://api.indiankanoon.org/> → regenerate → update env var → **restart** to drop the cached `KanoonClient` singleton. |

## AWS Bedrock — using AWS credits instead of Anthropic API

Headnote supports AWS Bedrock as a drop-in replacement for direct Anthropic API
calls. When configured, every LLM call (Sonnet, Haiku) is invoiced against your
AWS account / credits instead of Anthropic. Direct Anthropic remains the
automatic fallback if Bedrock errors are recoverable.

**Why use it**: AWS credits (free-tier, Activate, Marketplace credits) cover
Bedrock model invocations. If you have unused AWS credits, switching saves real
money — typical Indian early-stage AWS accounts have ₹10K–₹1L of unused credits
sitting idle.

### One-time AWS Console setup

1. **Subscribe to Claude models in your region**
   AWS Console → Amazon Bedrock → Model access → "Manage model access" →
   subscribe to **Claude Sonnet 4.6** and **Claude Haiku 4.5**.
   (Opus 4.7 is US-only at the time of writing; skip it — direct Anthropic
   handles Opus as fallback.)

2. **Verify the model works**
   Bedrock → Playground → pick Claude Sonnet 4.6 → ask "test". You should see
   a response. If you get "model access denied", the subscription is still
   pending (usually 1–5 minutes).

3. **Confirm a payment method is on file**
   Even with credits, AWS Marketplace requires a payment instrument. UPI
   AutoPay works for Indian accounts and may take 24–48 hours for the first
   AutoPay cycle to register — Bedrock still works during that window
   (credits are drawn first; the warning banner is cosmetic).

4. **Create an IAM user with these permissions**
   - `bedrock:InvokeModel`
   - `bedrock:InvokeModelWithResponseStream`
   Note the access key ID and secret.

### Railway environment variables

Add these to your Railway service (Service → Variables → Raw editor):

```
USE_BEDROCK=true
AWS_ACCESS_KEY_ID=<from step 4>
AWS_SECRET_ACCESS_KEY=<from step 4>

# Region your Bedrock model access is subscribed in
# (check AWS Console top-right; common Indian setups use Sydney)
AWS_REGION=ap-southeast-2

# Inference profile IDs (region prefix MUST match AWS_REGION)
# For APAC regions (Sydney, Mumbai, Tokyo, Singapore):
BEDROCK_SONNET_ID=apac.anthropic.claude-sonnet-4-6
BEDROCK_HAIKU_ID=apac.anthropic.claude-haiku-4-5

# For US regions (Virginia, Oregon):
# BEDROCK_SONNET_ID=us.anthropic.claude-sonnet-4-6
# BEDROCK_HAIKU_ID=us.anthropic.claude-haiku-4-5

# For EU regions (Frankfurt, Ireland):
# BEDROCK_SONNET_ID=eu.anthropic.claude-sonnet-4-6
# BEDROCK_HAIKU_ID=eu.anthropic.claude-haiku-4-5
```

### Verification

After deploying, hit `/api/situation` with any test query and check Railway
logs. You should see:

```
[client] using AnthropicBedrock client (region=ap-southeast-2)
```

If you instead see a Bedrock-error fallback warning like:

```
Bedrock error — falling back to direct Anthropic API
(bedrock_model=apac.anthropic.claude-sonnet-4-6 → anthropic_model=claude-sonnet-4-6): ...
```

the problem is one of: (a) wrong region prefix on `BEDROCK_*_ID`, (b) model
access not yet granted, (c) IAM permissions missing. The error message after
the colon points to which.

### Disabling Bedrock

Set `USE_BEDROCK=false` or unset `AWS_ACCESS_KEY_ID`. Direct Anthropic API
resumes immediately (no restart needed; the client is checked per call).

## Disaster recovery

The repo + a backup of `kanoon_cache.sqlite` + `feedback.db` is the
whole state. To restore from a fresh box:

```bash
git clone https://github.com/xyush14/Legify.git
cd Legify
pip install -r requirements.txt
cp /backup/kanoon_cache.sqlite ./
cp /backup/feedback.db ./
# put secrets in .env
uvicorn main:app
```

Everything else (LLM responses, embeddings) is regenerated on demand.
