# Criminal Law AI — v0.3

A polished, fully responsive web app for AI-powered Indian criminal-law research. Three modes (find cases / topic digest / paste-judgment-to-headnote), two output styles (journal headnote and practitioner notes), one-click Hindi translation, hallucination-proof citation verification, and a per-call cost meter.

Built on **FastAPI + Claude Opus 4.6** with prompt caching enabled for cost efficiency.

> 📊 **Comparison with LexLegis, SCC, Manupatra, CaseMine, Jhana** → see [COMPETITORS.md](./COMPETITORS.md)

---

## Files

```
criminal_law_ai_v0/
├── main.py                       # FastAPI backend (v0.3 — primary)
├── prompts.py                    # All prompt templates (situation, digest, headnote, translate)
├── cases.json                    # 42-case corpus
├── static/
│   ├── index.html                # Responsive UI
│   ├── style.css                 # Light theme, mobile-first
│   └── app.js                    # Frontend logic
├── requirements.txt
├── Procfile                      # For Heroku-style deploy
├── render.yaml                   # Render.com one-click deploy
├── runtime.txt                   # Python version pin
├── .env.example                  # Template — copy to .env
├── .gitignore
├── COMPETITORS.md                # How we differ from the field
├── README.md                     # This file
│
└── app.py                        # legacy v0.2 Streamlit app (kept for reference)
```

---

# 🔑 Where to put your API key

You have your `sk-ant-...` key. There are **only two places it should ever go**: a local `.env` file (for running on your laptop) or a hosting platform's secrets UI (for sharing with lawyers). Never commit it, never paste it in chat, never put it in a URL.

## Option A — Local (running on your laptop)

```bash
# In the project folder:
cp .env.example .env
```

Open `.env` in any editor and replace the placeholder line with your real key:

```
ANTHROPIC_API_KEY=sk-ant-api03-YOUR-REAL-KEY-HERE
```

Save and close. The `.env` file is in `.gitignore`, so it won't be committed if you push to GitHub.

Then:

```bash
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

Open <http://localhost:8000> in your browser. Done.

## Option B — Render.com (the recommended deploy for sharing with 4-5 lawyers)

This gives you a public URL like `https://criminal-law-ai.onrender.com` that any lawyer can open from their phone, free.

1. **Push code to GitHub** (private repo recommended):
   ```bash
   git init && git add . && git commit -m "v0.3"
   git branch -M main
   git remote add origin git@github.com:YOUR_HANDLE/criminal-law-ai.git
   git push -u origin main
   ```
   Confirm `.env` is **not** in the push — `.gitignore` excludes it. Double-check on GitHub before going further.

2. **Sign up at <https://render.com>** with your GitHub account.

3. **Create a Blueprint:**
   - Click **New** → **Blueprint**
   - Pick your `criminal-law-ai` repo
   - Render reads `render.yaml` and creates the service

4. **Add the API key** *before* first deploy:
   - In the Render dashboard, go to your new service → **Environment**
   - Click **Add Environment Variable**
   - Key: `ANTHROPIC_API_KEY`
   - Value: paste your `sk-ant-...` key
   - Click **Save**

5. **First deploy** runs automatically. Wait ~2 minutes. You'll see a green "Live" status and a URL: `https://criminal-law-ai-XXXX.onrender.com`.

6. Share that URL with your lawyers.

> **Render free tier note:** the app sleeps after 15 minutes of inactivity. First request after sleep takes ~30 seconds to wake. Tell your lawyers about this — or upgrade to the $7/month Starter tier for always-on.

## Option C — Other hosting (Railway, Fly.io)

Same pattern: push to GitHub, point the host at `main.py`, set `ANTHROPIC_API_KEY` as an environment variable in the host's dashboard. Use the `Procfile` (`web: uvicorn main:app --host 0.0.0.0 --port $PORT`).

---

# 💰 Cost — what your API budget actually buys

The app uses Claude Opus 4.6 with Anthropic prompt caching enabled. The corpus + system prompt (~16k tokens) is sent as a cached block; subsequent calls within ~5 minutes hit the cache and pay 10% of normal input price.

| Call type | Cost / call |
|---|---|
| First call (cache write) | ~$0.45 (₹38) |
| Subsequent cached calls | ~$0.18 (₹15) |
| Hindi translation (Haiku, no cache) | ~$0.005 (₹0.40) |

**Realistic budget math:**

| Budget | Approximate queries | Sufficient for |
|---|---|---|
| **$5** | ~25 queries | Quick taste-test, 5 lawyers × ~5 queries each |
| **$10** (recommended) | ~55 queries | Comfortable round-1 testing, 5 lawyers × ~11 queries |
| **$20** | ~115 queries | Round-1 + iteration, 5 lawyers × 20+ queries |

> **Tip to stretch the budget:** brief lawyers to do their queries in one sitting. The cache stays warm within 5-minute windows; scattered queries across a day re-pay the cache-write premium each time.

The app shows live cost meter on every result (`≈ $0.18 (₹15)`) so you can watch the budget burn in real time.

---

# 🇮🇳 Hindi translation

After any English result, click the **🇮🇳 हिन्दी (Hindi)** button. The result re-renders in Devanagari Hindi with:
- Case titles preserved in English (e.g., *Dashrath Rupsingh Rathod v. State of Maharashtra*)
- Citations preserved verbatim (e.g., `(2014) 9 SCC 129 : 2014 Cri.L.J. 4350`)
- Statute names with section numbers preserved (e.g., `Negotiable Instruments Act, 1881, S. 138`)
- Paragraph anchors preserved (e.g., `(Paras 14, 16-17)`)
- Only the prose explanation, ratio, and gist translated to natural Hindi-legal register

Click **🇬🇧 English** to revert. Translations use Claude Haiku (cheap and fast — about ₹0.40 per translation).

---

# What's in the app

## Mode 1 — Find cases for my situation
Type a legal problem in plain English. Pick output style:
- **Journal headnote** (Cri.L.J. format) — for written submissions
- **Practitioner notes** (chambers digest) — for working files

Returns 3-5 most relevant cases from the corpus with full structured output, "why this matches" explanation, and BNS/BNSS mapping note.

## Mode 2 — Topic digest
Type a doctrinal topic ("circumstantial evidence requirements", "S. 482 quashing on settlement"). Returns a topic-organised digest grouping cases under sub-topic headings — exactly the format your gold-doc notebook uses.

## Mode 3 — Generate headnote from judgment
Paste full judgment text. Returns lettered headnotes (one per discrete point of law) with both Cri.L.J. journal version and parallel practitioner-notes version, plus a list of cases referred with treatment classification.

## Plus across all modes
- **Hindi translation** on every result (per above)
- **Copy-to-clipboard** on every case card
- **WhatsApp share** for mobile lawyers
- **Print** with a clean print stylesheet (no UI chrome, court-document-style layout)
- **Search history** in localStorage — re-run any past query in one click
- **Browse corpus** drawer — search/filter all 42 cases
- **Per-call cost meter** in $ and ₹
- **Keyboard shortcut** Ctrl/Cmd+Enter to submit
- **Hallucination guards** — every cited case_id verified against corpus before display
- **Loading skeletons**, **toast notifications**, **error boundaries**

---

# Brief lawyers like this

> Hi [name], I'm testing an early prototype of an AI tool for Indian criminal-law research.
>
> URL: `https://your-app.onrender.com`
>
> Three modes to try:
> 1. **Find cases** — type a real legal situation you've researched recently. Choose journal headnote or practitioner notes (the chambers-digest format senior advocates' associates use).
> 2. **Topic digest** — type a doctrinal topic ("circumstantial evidence requirements"). You get a topic-organised research notebook.
> 3. **Headnote** — paste any criminal judgment text. Get back Cri.L.J.-format headnote + practitioner notes side by side.
>
> Quick asks:
> - Click 👍 / 👎 on each result. Even one click is useful data.
> - One-line comment if anything looks off — wrong citation, weird Hindi translation, missing case, format that doesn't feel right.
>
> Quick caveats:
> - Corpus is only 42 landmark Supreme Court cases (v0). Don't rely on it for actual matters yet — verify every citation in the source judgment, especially after the SC's Feb 2026 ruling on AI-generated fake citations as misconduct.
> - The app sleeps after 15 min on the free tier; first request takes ~30 sec to wake.

---

# Reading the feedback after testing

```bash
# Local
python3 -c "
import sqlite3
conn = sqlite3.connect('feedback.db')
rows = conn.execute('SELECT ts, mode, lawyer_handle, rating, correction, input_text FROM feedback ORDER BY ts DESC').fetchall()
for ts, mode, who, rating, correction, inp in rows:
    flag = '👍' if rating == 1 else '👎'
    print(f'{ts}  {flag}  [{mode}]  {who or \"(anon)\"}')
    print(f'   input: {inp[:120]}...')
    if correction: print(f'   note:  {correction}')
    print()
"
```

On Render free tier the SQLite DB is on ephemeral disk and gets wiped on every restart. If you need persistent feedback, set the env var `FEEDBACK_DB=/var/data/feedback.db` and add a paid disk, or swap SQLite for Supabase (free tier, 30 mins to wire up).

---

# Limitations (deliberate v0)

- **Corpus is 42 landmark cases.** Production target: 50,000+. With Opus's 200k context you can scale corpus to ~150k tokens (~2,000 cases) before needing a vector retrieval layer.
- **No PDF upload yet** — paste-text only. Half a day of work to add `pypdf` after lawyer feedback confirms it's wanted.
- **No login / per-lawyer accounts** — single shared instance for testing.
- **No drafting / contract review yet** — that's v0.4 territory if lawyer feedback says it's wanted.
- **No document upload + Q&A on user files** — same.

---

# Architecture in one paragraph

FastAPI backend serves four endpoints (`/api/situation`, `/api/digest`, `/api/headnote`, `/api/translate`) plus a static frontend (`/` and `/static/*`). Each endpoint builds a system prompt that includes the full corpus, sends to Anthropic with prompt caching enabled, parses JSON, and verifies every returned `case_id` against the corpus before returning to the client. The frontend is vanilla HTML/CSS/JS (no build step, no framework), uses CSS variables for the light theme, is fully responsive at 320px / 640px / 1024px / 1280px breakpoints, and stores search history in `localStorage`. SQLite for feedback. Hindi translation runs on Claude Haiku for ~25× lower cost than Opus, with a separate prompt that explicitly preserves citations, case names, statute references, and paragraph anchors verbatim.

---

# What's next (roadmap)

- **v0.4** — PDF upload, corpus expansion to 500 cases, lawyer accounts.
- **v0.5** — citation graph (overruled / followed / distinguished), eCourts ingestion, draft generation.
- **v1.0** — corpus 5,000+ cases, paid plans, bar-association partnerships.
