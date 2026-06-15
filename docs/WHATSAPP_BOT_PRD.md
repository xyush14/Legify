---
status: draft
owner: Ayush (xyush14)
last_updated: 2026-06-15
version: 0.1
---

# Headnote WhatsApp Bot — Product Requirements Document

End-to-end research assistant for Indian advocates over WhatsApp. Lawyer
sends a natural-language legal question, bot returns verifiable citations
plus a downloadable PDF memo — all inside the chat thread.

This PRD is the contract for v1. It is written to be implementable by a
solo founder + one contractor in **3–4 focused weeks** on a **₹0–₹2,500
per month** operating budget at launch.

---

## 1. Why this exists

Indian legal professionals live on WhatsApp. Drafting a brief, asking a
junior to "find me a case on X", forwarding judgments — all of it happens
in DMs and group chats. The friction of opening a browser, logging into
a research portal, formulating a search, and copying back results means
that **most spot-research questions get a guessed answer instead of a
real one**.

Headnote already has the research engine — IK→official-source
re-anchored citations, official judgment corpus, drafter, paid tier.
What it lacks is the channel that meets lawyers where they already are.

A WhatsApp bot collapses the entire "I need a case on this" loop into
one DM:

- **Lawyer**: `s.138 NI Act recent SC on territorial jurisdiction`
- **Bot** (under 30s): 5 verified citations + 1-line ratios + PDF memo
  attached, send-forwardable to the junior.

This is the single highest-leverage distribution channel for Headnote.
The competitive observation that finalized the call: **NyayAssist has a
WhatsApp bot, but it's for file management — not research**. The
research-via-WA slot is open.

---

## 2. Goals and non-goals

### v1 goals

- **G1.** A working WhatsApp number that any Indian lawyer can DM and
  receive a citation-backed research response within 60 seconds.
- **G2.** Phone-number-based account linkage that recognizes existing
  paid Headnote users and removes their quota.
- **G3.** A free-tier funnel that lets new lawyers try 3 queries/day
  and converts them to paid via a link to headnote.in.
- **G4.** Zero net-new LLM spend per query beyond what existing
  Headnote research costs (i.e., reuse existing DeepSeek/Groq path).
- **G5.** Operate at **₹0 marginal infra cost** for the first 1,000
  service conversations per month (Meta Cloud API free tier).

### v1 non-goals (deferred to v2+)

- Voice-note transcription (Whisper/Groq integration deferred)
- Hindi / regional language input/output (English-only at v1)
- Document upload (lawyer sending a PDF and asking "find similar cases")
- Multi-turn long-form drafting inside WhatsApp
- Group-chat support (DM only at v1)
- Push notifications / proactive case alerts
- Calendar / hearing reminders
- Payments inside WhatsApp (link out to headnote.in instead)

### Explicit out-of-scope

- Replacing the Headnote web app — the bot is a channel, not a fork
- Replacing email — PDF memo is delivered in WA AND emailed for archival
- Hosting any LLM ourselves — all inference stays on existing providers

---

## 3. Target users

### Primary persona — Solo Advocate, 2–10 years PQE

- Practices in district / High Court
- Owns the matter end to end; researches for self
- Lives in WhatsApp; checks email twice a day
- Currently uses: free Indian Kanoon, sometimes SCC Online via friend's login
- Pain: spends 30–90 minutes per matter looking up precedent
- Willingness to pay: ₹500–₹1,500 / month for something that saves the hour
- This user is **the dominant Headnote ICP** and is who the bot is built for

### Secondary — Junior associate in a 5–20 lawyer firm

- Researches on partner's behalf, gets WhatsApp pings at 11pm
- Often the one who'll *forward* the bot's output to seniors
- Doesn't pay directly but is the strongest distribution multiplier

### Tertiary — Law student preparing moots

- High-frequency low-value queries
- Stays on free tier indefinitely; useful for word-of-mouth and
  long-tail conversion when they start practice

---

## 4. User stories (v1)

| # | As a… | I want to… | So that… |
|---|---|---|---|
| US1 | new lawyer | DM the bot and get a useful answer without signing up | I can evaluate it before deciding to subscribe |
| US2 | existing paid Headnote user | link my WhatsApp number once and forget about it | I get unlimited research from any device |
| US3 | lawyer in a hurry | type a 1-line question and get citations in under a minute | I can answer the partner's question on the road |
| US4 | lawyer who got a useful result | forward the response to a colleague | the colleague sees Headnote and tries it |
| US5 | lawyer who hit free quota | upgrade in two taps | I don't lose my flow |
| US6 | lawyer with a follow-up | refine my last query without re-typing context | conversation feels natural |
| US7 | lawyer who wants the full memo | get a PDF with full ratios, paragraph quotes, and links | I can use it in my brief |
| US8 | lawyer worried about privacy | trust that the bot doesn't leak my query | I keep using it on sensitive matters |

---

## 5. Conversational UX

### First-time DM (cold contact)

```
[user] Hi
[bot]  Welcome to Headnote — citation-checked legal research on WhatsApp.

       I find verified Indian case law and statutes. Try a question
       like: "Section 138 NI Act recent SC on territorial jurisdiction"
       or "doctrine of part performance latest HC view".

       You get 3 free queries per day. Existing Headnote subscribers
       get unlimited — just send LINK to connect your account.
```

### Research query (the core loop)

```
[user] section 138 NI act recent SC on territorial jurisdiction

[bot]  🔎 Searching the SC corpus…

[bot]  Found 5 SC judgments on Section 138 NI Act / territorial jurisdiction
       (last 5 years):

       1. *Dashrath Rupsingh Rathod v. State of Maharashtra*
          (2014) 9 SCC 129
          → Cheque return triggers cause of action; complaint lies
            where drawee bank is located.

       2. *Bridgestone India v. Inderpal Singh*
          (2016) 2 SCC 75
          → Clarifies post-Dashrath position after 2015 Amendment;
            place of payee's bank now central.

       3. *K. Bhaskaran v. Sankaran Vaidhyan Balan*
          (1999) 7 SCC 510
          → Five-act test, foundational pre-amendment frame.

       4. *Yogendra Pratap Singh v. Savitri Pandey*
          (2014) 10 SCC 713
          → Limitation interplay with cause of action.

       5. *M/s Yashshree Talkies v. State of Maharashtra*
          (2023) — pending judgment reference

       📎 Full memo sent: 4-page PDF with quotes, paragraph numbers,
          and direct links to indiankanoon.org + the SCI source.

       Queries left today: 2/3 free.
       Reply REFINE <new angle> to narrow this search.
       Reply UPGRADE to remove daily limit (₹999/mo).
```

### Account linkage (existing paid user)

```
[user] LINK

[bot]  Got it. Reply with the email or phone you use on headnote.in
       and I'll send a 4-digit code to confirm.

[user] kshitij@loopai.com

[bot]  Code sent. Check your headnote.in inbox or SMS.

[user] 7421

[bot]  ✅ Linked. You're on the Advocate plan — unlimited queries on
       WhatsApp from now on. Send a research question to begin.
```

### Quota exhaustion

```
[user] (4th query of the day, free tier)

[bot]  You've used your 3 free queries today. They reset at midnight IST.

       Headnote subscribers get unlimited WhatsApp research, full PDF
       memos, and access to the web app:

       → Subscribe: https://headnote.in/upgrade

       Already subscribed? Reply LINK to connect your account.
```

### Out-of-window re-engagement (24h+ later)

The 24h customer-service window is closed. Bot cannot send free-form
text. It can send an *approved utility template* like:

```
[bot] (utility template) Your daily Headnote queries have reset.
      Reply with any legal research question to begin. — Headnote
```

We will register **one** utility template at v1. Marketing pushes are
explicitly out of scope (we don't want to be the kind of bot lawyers
mute).

---

## 6. Technical architecture

```
┌────────────┐    DM       ┌──────────────┐
│ Lawyer's   │ ──────────► │ Meta Cloud   │
│ WhatsApp   │             │ API (WABA)   │
└────────────┘             └──────┬───────┘
                                  │ webhook (HTTPS POST)
                                  ▼
                          ┌───────────────────┐
                          │ FastAPI route     │
                          │ /api/whatsapp/    │
                          │   webhook         │
                          └──────┬────────────┘
                                 │
            ┌────────────────────┼────────────────────┐
            ▼                    ▼                    ▼
     ┌──────────────┐    ┌──────────────┐     ┌──────────────┐
     │ Signature    │    │ Phone → User │     │ Quota +      │
     │ verify       │    │ resolver     │     │ session      │
     │ (X-Hub HMAC) │    │ (Supabase)   │     │ (Supabase)   │
     └──────────────┘    └──────┬───────┘     └──────────────┘
                                ▼
                       ┌──────────────────┐
                       │ Intent dispatcher │
                       │ - link account    │
                       │ - research query  │
                       │ - help / unknown  │
                       └──────┬───────────┘
                              ▼
                  ┌────────────────────────────┐
                  │ Existing Headnote research │
                  │ pipeline (re-anchored      │
                  │ citations, DeepSeek/Groq)  │
                  └──────┬─────────────────────┘
                         │
                  ┌──────┴────────┐
                  ▼               ▼
         ┌─────────────┐   ┌──────────────┐
         │ Format short │   │ Render PDF  │
         │ WA response  │   │ memo        │
         └──────┬──────┘    └─────┬───────┘
                ▼                 ▼
          ┌──────────────────────────────┐
          │ Meta Cloud API send-message  │
          │ (text + media)               │
          └──────────────────────────────┘
```

### Why Meta Cloud API direct (not a BSP)

We compared 5 paths. Decision: **Meta Cloud API direct**, because at
tight budget the BSP layer is a tax we don't need yet.

| Provider | Monthly minimum | India billing | DX | Verdict |
|---|---|---|---|---|
| **Meta Cloud API direct** | **₹0** | ✓ (per-conversation, INR via Meta) | OK — write own webhook | **v1 pick** |
| AiSensy | ₹999 + convo fees | ✓ INR | UI for templates | Reconsider at scale |
| Interakt | ₹999+ | ✓ INR | Decent UI | Same as AiSensy |
| Gupshup | Pay-as-you-go | ✓ INR | Heavier integration | Enterprise sizing |
| Wati | $49+ USD/mo | ✗ USD | Best DX of all | Skip — USD pricing |
| Twilio | $0.005/msg + WA fees | ✗ USD | Cleanest API | Skip — no India edge |

A BSP is a hosted UI for managing templates, analytics, and broadcasts.
We don't need any of that yet. The Meta Cloud API gives us **1,000 free
service conversations per month** and per-conversation pricing after.
Webhook handling is one FastAPI route — we already write FastAPI.

We can move to a BSP at any time later (DNS-level change essentially).

### Code surface — what we add

```
headnote/
├── api/
│   └── whatsapp.py          # NEW — webhook, signature verify, dispatch
├── whatsapp/                # NEW package
│   ├── __init__.py
│   ├── client.py            # Meta Cloud API send-message wrapper
│   ├── handlers.py          # intent → handler map
│   ├── session.py           # conversation state, quota, linkage
│   ├── templates.py         # registered template names + senders
│   └── formatters.py        # WA-text + PDF memo rendering
└── migrations/
    └── 00X_whatsapp.sql     # users.wa_phone, wa_messages log, wa_quota
```

### Reused (zero net-new code)

- Research pipeline: `headnote/situation_pipeline.py` and
  `headnote/api/assist.py`
- LLM dispatch: existing DeepSeek/Groq path in `headnote/llm/`
- PDF generation: `headnote_caselaw_pdf.py` pattern (adapt to memo format)
- Auth: `headnote/api/auth_otpless.py` — phone-OTP already wired to
  Supabase. We piggyback the same flow for WhatsApp linking.
- DB: existing Supabase Postgres

---

## 7. Data model (delta only)

Three additions to existing schema. Migration file
`migrations/00X_whatsapp.sql`:

```sql
-- 1. Add WhatsApp phone to user profile
ALTER TABLE users
  ADD COLUMN wa_phone TEXT UNIQUE,           -- E.164, e.g. +919876543210
  ADD COLUMN wa_linked_at TIMESTAMPTZ;

CREATE INDEX users_wa_phone_idx ON users(wa_phone);

-- 2. Message log (debugging, abuse detection, analytics)
CREATE TABLE wa_messages (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  wa_phone     TEXT NOT NULL,
  direction    TEXT NOT NULL CHECK (direction IN ('in', 'out')),
  msg_type     TEXT NOT NULL,   -- text, document, template, system
  body         TEXT,            -- redacted to first 500 chars
  meta_msg_id  TEXT,            -- id from Meta payload
  user_id      UUID REFERENCES users(id),
  created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX wa_messages_phone_created_idx
  ON wa_messages(wa_phone, created_at DESC);

-- 3. Per-day quota counter for free users
CREATE TABLE wa_quota (
  wa_phone     TEXT NOT NULL,
  day          DATE NOT NULL,        -- IST day (Asia/Kolkata)
  count        INT NOT NULL DEFAULT 0,
  PRIMARY KEY (wa_phone, day)
);
```

All other state — research history, memo PDFs, payments — lives in
existing tables. No new big tables.

---

## 8. Functional requirements

### F1. Webhook ingestion

- **F1.1** Endpoint: `POST /api/whatsapp/webhook`. Public. Verifies
  Meta's `X-Hub-Signature-256` HMAC using `WA_APP_SECRET`. Reject 403
  on mismatch.
- **F1.2** Endpoint: `GET /api/whatsapp/webhook`. Used by Meta for
  initial verification handshake. Echoes `hub.challenge` if
  `hub.verify_token == WA_VERIFY_TOKEN`.
- **F1.3** All incoming messages logged to `wa_messages` (direction =
  'in') before dispatch.
- **F1.4** Bot replies within 2s "ack" (typing indicator + status
  message for queries > 5s).
- **F1.5** Idempotency: dedupe by `meta_msg_id` — Meta retries on
  failure, we must not double-process.

### F2. Intent detection

- **F2.1** Simple keyword router at v1 (not LLM-based). Patterns:
  - First-time user → onboarding flow
  - `LINK` (case-insensitive) → account linkage
  - `UPGRADE` → send upgrade link
  - `HELP` → send help text
  - `REFINE <text>` → refinement of last query (uses session memory)
  - Anything else → treat as research query
- **F2.2** Research queries go to existing `assist.py` pipeline.
- **F2.3** Unknown / unparseable input → fallback help message, do
  not consume quota.

### F3. Phone-to-account linkage

- **F3.1** First message from a new phone creates a `wa_users`
  shadow record (not a full user). They're a "trial" user.
- **F3.2** When user sends `LINK`, bot asks for email/phone used on
  headnote.in.
- **F3.3** Bot reuses existing OTPless flow: triggers an OTP send to
  that email/phone via the existing `auth_otpless.py` machinery.
- **F3.4** User replies with OTP in WhatsApp. Bot verifies via the
  existing OTPless verify endpoint, then writes
  `users.wa_phone = <sender_wa_phone>`.
- **F3.5** From then on, that WA number is treated as the linked user
  with full plan entitlements.
- **F3.6** Re-linking same WA phone to a different user requires manual
  admin action (security — prevents account hijack via SIM swap).

### F4. Quota and entitlements

- **F4.1** Linked paid users: unlimited research queries; no counter
  shown.
- **F4.2** Trial / unlinked phones: 3 research queries per IST day.
  Counter shown after every response: "Queries left today: N/3 free".
- **F4.3** On 4th query, return upgrade CTA. Do not run the research.
- **F4.4** Help / link / unknown messages do NOT consume quota.
- **F4.5** Quota reset job: nothing — natural day rollover via the
  `day` column in `wa_quota`.

### F5. Research execution

- **F5.1** Call existing situation pipeline with the user's text as the
  natural-language query.
- **F5.2** Use existing DeepSeek V3 default (V3 for fast path). Per
  user memory: **never Claude** at the bot serving path.
- **F5.3** Use Groq Llama 3.x as fallback if DeepSeek errors.
- **F5.4** Result must include: 3–5 citations with court, year, cite
  ref, 1-line ratio, and a verified link (re-anchored to official
  source per existing Headnote design).
- **F5.5** Generate a 1–3 page PDF memo using `headnote_caselaw_pdf.py`
  format. Send as document attachment in same WA reply thread.

### F6. Output formatting

- **F6.1** WhatsApp text response: under 1,000 characters when possible.
  Use *italics* for case names, plain text otherwise (no markdown
  beyond what WA renders).
- **F6.2** Citation block format:
  ```
  N. *Case Name v. Other Party*
     Citation (Year)
     → One-line ratio / holding
  ```
- **F6.3** PDF memo: 1–3 pages, Headnote branding, full quotes with
  paragraph numbers, link to source.
- **F6.4** PDF filename: `headnote_<short-query-slug>_<YYYYMMDD>.pdf`.

### F7. Conversation memory

- **F7.1** v1 keeps the **last query + last result** per WA phone in
  Supabase (column on `wa_quota` or a lightweight table).
- **F7.2** `REFINE <text>` rewrites the previous query incorporating
  the new angle, runs again. Consumes 1 quota.
- **F7.3** No multi-turn dialogue at v1 beyond REFINE.

### F8. Compliance basics

- **F8.1** Privacy notice in onboarding message + linked at
  `headnote.in/privacy`.
- **F8.2** `STOP` keyword unsubscribes (no further proactive messages).
- **F8.3** Message log retains payloads for 90 days, then purged
  automatically. Aggregate stats retained.
- **F8.4** No sharing of query content with any third party beyond the
  LLM provider used to fulfill the request (DeepSeek / Groq).

---

## 9. Non-functional requirements

| ID | Requirement | Target |
|---|---|---|
| NF1 | P50 research response latency | < 30s |
| NF2 | P95 research response latency | < 60s |
| NF3 | Citation correctness | ≥ 95% verifiable to live source |
| NF4 | Uptime | ≥ 99% (matches existing Render hobby tier) |
| NF5 | Webhook ack latency | < 2s |
| NF6 | LLM cost per query | < ₹0.10 |
| NF7 | Infra cost (excluding LLM) | ₹0 to first 1,000 conv/mo |

---

## 10. Pricing & cost model

This is the section to look at twice. Tight-budget posture throughout.

### 10.1 One-time setup costs

| Item | Cost | Notes |
|---|---|---|
| WhatsApp Business Number (new SIM) | ₹500 | Or reuse an existing non-WA-registered number. Cannot be a number currently on WhatsApp consumer app. |
| Facebook Business Verification | ₹0 | Document upload; 3–5 business days |
| WABA Display Name approval | ₹0 | Submitted via Meta Business Suite; 24–48h |
| Template approval (1 utility template) | ₹0 | 24–48h |
| Development time (solo or 1 contractor) | ₹0–₹40,000 | If outsourced: ~₹30–40k for 3 weeks |
| **Total cash setup** | **₹500–₹40,500** | Lower bound if you build it; upper if you outsource |

### 10.2 Recurring infrastructure

**Meta Cloud API conversation pricing (India, as of late 2025 — verify
on launch).** Per-conversation, free first 1,000/month.

| Conversation type | Per-conversation cost (India) | Free tier |
|---|---|---|
| Service (user-initiated, 24h window) | ~₹0.30 | 1,000 / month |
| Utility template | ~₹0.16 | shared cap |
| Marketing template | ~₹0.88 | shared cap |
| Authentication template | ~₹0.12 | shared cap |

> ⚠️ Verify exact current rates at
> https://developers.facebook.com/docs/whatsapp/pricing — Meta has
> changed pricing twice in the past two years. The PRD assumes
> "service conversations are free up to 1,000/month" which has been
> stable since 2024.

**At launch scale (≤ 1,000 service conversations / month):**

| Item | Monthly cost (INR) |
|---|---|
| Meta Cloud API conversations | ₹0 |
| Render web hosting | ₹0 (existing free tier) |
| Supabase | ₹0 (existing free tier) |
| LLM (DeepSeek V3, ~500 queries/mo @ ₹0.05) | ₹25 |
| LLM (DeepSeek R1 deep, ~50 queries/mo @ ₹0.50) | ₹25 |
| Groq fallback | ₹0 (free tier sufficient) |
| Domain / SSL | ₹0 (existing) |
| PDF storage (~50MB/mo) | ₹0 (Supabase storage free tier) |
| **Estimated launch month-1 spend** | **₹50–₹200** |

**At 5,000 conversations / month (post-PMF scale):**

| Item | Monthly cost (INR) |
|---|---|
| Meta Cloud API (4,000 paid service conv @ ₹0.30) | ₹1,200 |
| Meta Cloud API (utility template, 500 @ ₹0.16) | ₹80 |
| Render upgrade (Starter tier) | ₹600 (~$7) |
| Supabase Pro (if storage exceeded) | ₹2,100 (~$25) |
| LLM (5,000 queries, mix of V3 + R1) | ₹500–₹1,500 |
| PDF storage / CDN | ₹100 |
| **Estimated scale spend** | **₹4,500–₹5,500** |

### 10.3 LLM cost detail (per-query worked example)

Reuses existing Headnote pipeline. Per user memory: never Claude.

| Stage | Provider | Tokens (in+out) | Cost/query |
|---|---|---|---|
| Decompose query | DeepSeek V3 | ~600 | ₹0.005 |
| Retrieve (local SQLite, no LLM) | — | — | ₹0.000 |
| Rank / cluster | DeepSeek V3 | ~2,000 | ₹0.015 |
| Synthesize citation block | DeepSeek V3 | ~1,500 | ₹0.012 |
| Render memo prose | DeepSeek V3 | ~3,000 | ₹0.025 |
| **Total per fast-path query** | | **~₹0.06** | |

Deep / R1 queries (~10% of traffic if user is doing serious research):
~₹0.40 per query. Blended estimate: **₹0.08–₹0.12 per query**.

### 10.4 Revenue model (what the bot funnels into)

The bot is a **funnel to existing Headnote paid plans**. No new SKU
needed at v1.

Suggested funnel math at break-even:

- 100 lawyers DM the bot in month 1 (organic + IG-driven)
- 50 use up to free quota (50% activation)
- 20 link an existing account (good — existing users get value)
- 5 convert from cold to paid (5% cold conversion) at ₹999/mo
- Month-1 revenue lift: **₹4,995**
- Month-1 infra cost: **₹50–₹200**
- Net: **+₹4,795 in month 1** at break-even-light assumption

The economics work because Headnote has an existing paid tier. The bot
is a distribution multiplier, not a cost center.

### 10.5 When to spend more

Triggers to upgrade infra:

| Trigger | What to upgrade | New monthly cost |
|---|---|---|
| > 800 conversations / mo | Nothing yet — watch free tier | — |
| > 1,200 conversations / mo | Accept Meta paid tier (auto) | + ₹500–₹1,500 |
| P95 latency > 90s | Render Starter ($7/mo) | + ₹600 |
| > 1GB PDF storage | Move PDFs to S3 (Backblaze B2 cheaper: $0.005/GB) | + ₹50 |
| > 50 simultaneous DM users | Consider BSP (AiSensy) for queue / templates | + ₹999 |

Do not preemptively upgrade. Watch the metrics in §13 and respond.

---

## 11. Security & compliance

### 11.1 WhatsApp / Meta requirements

- **WABA verification** — Facebook Business Manager → submit
  incorporation docs (Headnote LLP/Pvt Ltd PAN, GST cert, address
  proof). Required before any bot can go live.
- **Display name approval** — "Headnote" or similar. Cannot use
  trademarked names without permission.
- **Phone number** — dedicated, never registered on WhatsApp consumer
  app. Either a fresh SIM or a number you've de-registered first via
  https://faq.whatsapp.com/.

### 11.2 Data handling

- All inbound messages stored in `wa_messages` for 90 days, then
  purged. Aggregate stats (count by day, query category) retained
  indefinitely.
- No query text or response logged with any third party beyond the
  LLM provider serving the request.
- `STOP` keyword: writes `users.wa_unsubscribed_at`, halts all
  outbound messages, retains data per retention policy.
- LLM provider data policies: DeepSeek and Groq both offer
  no-training-on-customer-data tiers; confirm setting before launch.

### 11.3 Webhook security

- HMAC verify on every inbound webhook (`X-Hub-Signature-256`).
- IP allowlist of Meta's published webhook IP ranges (optional but
  recommended at scale).
- Per-phone rate limit: 30 messages / minute, 200 / hour. Above
  threshold → log + ignore (don't bounce, since bouncing burns convo).

### 11.4 DPDPA posture (India, 2023 Act)

Not full audit at v1 — a clear privacy page at headnote.in/privacy
covering:

- Categories of personal data collected (phone, query text)
- Purpose (legal research delivery)
- Retention (90 days for messages, indefinitely for aggregates)
- User rights (access, deletion via STOP + email request)
- Cross-border transfer (LLM providers — disclose explicitly)
- Grievance officer (your name + email)

This is sufficient for solo founder posture. Full SOC2 / ISO is a
post-Series-A problem.

---

## 12. Metrics and KPIs

### 12.1 North-star

**Weekly Active Lawyers on WhatsApp** — distinct WA phones that sent
≥1 research query in the last 7 days. Tracks reach + engagement in
one number.

### 12.2 Funnel

| Stage | Metric | Target month 1 | Target month 3 |
|---|---|---|---|
| Acquisition | Unique WA phones DMing | 100 | 500 |
| Activation | % that send ≥1 research query | 70% | 80% |
| Linkage | % that send `LINK` | 20% | 30% |
| Retention | Day-7 return rate (any message) | 25% | 40% |
| Conversion | % cold → paid in 30 days | 3% | 6% |
| Revenue | New paid users / mo via WA | 3 | 30 |

### 12.3 Quality

| Metric | Target |
|---|---|
| Citation correctness (manual sample of 50/mo) | ≥ 95% verifiable |
| P50 latency | < 30s |
| P95 latency | < 60s |
| Failed responses (errors / total) | < 2% |
| Spam / abuse messages | < 5% of inbound |

### 12.4 Cost

| Metric | Target |
|---|---|
| Cost per query (LLM + infra) | < ₹0.15 |
| Cost per acquired paid user | < ₹500 |

### 12.5 Where the metrics live

- Counters: increment in `wa_messages` aggregation views
- Funnel: simple weekly SQL pulled in Supabase studio
- Latency: log on each webhook handler, daily P50/P95 via SQL
- Quality: manual review queue — 1 hour/week to spot-check 50 queries

No external analytics product at v1. Supabase + a Sunday SQL hour
covers it.

---

## 13. Rollout plan

### Phase 0 — Pre-build (week 1)

- [ ] Get a fresh SIM card not registered on WhatsApp
- [ ] Create Facebook Business account; submit business verification
  documents (PAN, GST, address proof)
- [ ] Create a WhatsApp Business App in Meta Business Suite
- [ ] Submit Display Name "Headnote" for approval
- [ ] Set up webhook URL placeholder on Render
- [ ] Note: FB verification is the **long pole** — 3–7 business days.
  Start immediately.

**Cost: ₹500 (SIM) + free**

### Phase 1 — Bare-loop bot (week 2)

- [ ] Webhook GET handshake + POST signature verify
- [ ] Echo bot: any inbound message → "Got it: <text>" outbound
- [ ] Logging to `wa_messages`
- [ ] Deploy to Render
- [ ] Test with personal WA → bot number

**Acceptance: a message sent to the bot number gets echoed back in
under 2s.**

### Phase 2 — Research pipeline integration (week 3)

- [ ] Wire research pipeline → format response + generate PDF
- [ ] Send text + PDF document attachment via Meta API
- [ ] First-time onboarding message
- [ ] Help / unknown / STOP keyword handling
- [ ] Privacy page live at headnote.in/privacy

**Acceptance: 10 representative queries (you + senior advocate) return
correct citations + PDF attachment within 60s. No critical bugs in
formatting.**

### Phase 3 — Linkage + quota (week 4)

- [ ] LINK flow reusing OTPless
- [ ] Quota table + counter
- [ ] Upgrade CTA on quota exhaustion
- [ ] REFINE last-query support
- [ ] One utility template approved + send path

**Acceptance: end-to-end test with both an existing paid user (unlimited)
and a fresh number (3-query free tier with paywall block).**

### Phase 4 — Soft launch (week 5)

- [ ] Share number with 10 friendly lawyers, 1 by 1, over a week
- [ ] Monitor every conversation manually
- [ ] Fix top 5 issues / awkwardnesses
- [ ] Collect 2-3 testimonials for landing page

**Acceptance: 8/10 friendly testers say "this is useful." Citation
correctness ≥ 95% on real queries.**

### Phase 5 — Public launch (week 6+)

- [ ] Add WA number to headnote.in landing page CTA
- [ ] Add to Instagram bio + post a launch reel
- [ ] Add to distributor onboarding email
- [ ] Add to partnership proposal as a feature
- [ ] Monitor metrics weekly

---

## 14. Risks & mitigations

| # | Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|---|
| R1 | FB Business Verification rejection | M | H | Submit clean docs first time; have alternative documents ready; budget 2 weeks for back-and-forth |
| R2 | Display name "Headnote" rejected | L | M | Have "Headnote.in" or "Headnote Research" as fallback names |
| R3 | LLM cost spike from abuse | L | M | Per-phone rate limit (F4); quota table; daily cost alert at ₹500 |
| R4 | Bot fabricates a citation | M | **H** | Use existing re-anchored pipeline; reject responses where the verifier fails; manual QA in soft launch |
| R5 | WA number gets reported / banned | L | **H** | Don't send any marketing-shaped messages; respect STOP; don't broadcast to unconsented users |
| R6 | Render free tier sleeps | M | M | Existing Headnote already handles cold start; webhook auto-wakes; if cold-start > 60s, upgrade to Starter (₹600/mo) |
| R7 | User confused by free-form WA UI | M | M | Strong onboarding message; HELP keyword; soft-launch round catches this |
| R8 | NyayAssist or competitor copies | M | M | First-mover + technical depth (re-anchoring). Citation-correctness moat is hard to copy fast |
| R9 | Lawyer asks for sensitive personal advice | L | M | Disclaimer in PDF footer ("Not legal advice; verify before relying"); don't store opaque PII |
| R10 | DeepSeek API downtime | L | M | Groq fallback already in pipeline; degrade gracefully with "service temporarily slow" |

---

## 15. Open questions

Things to resolve before or during Phase 0:

1. **Headnote pricing for v1 funnel** — current paid plan price and
   billing cadence. Need confirmed amount for the UPGRADE CTA copy.
2. **Senior advocate co-signer** — should the bot's onboarding mention
   the senior advocate (credibility) or stay anonymous?
3. **PDF branding** — does the memo show Headnote logo + footer, or
   stay plain to allow lawyer-forwarding without giveaway?
4. **Hindi by when?** — out of scope at v1, but if early users
   demand it, where does it slot in? (Estimate: v2, +2 weeks)
5. **Group-chat support** — explicitly deferred. Revisit at 1,000 WAU.
6. **Document upload** — lawyer sends a PDF, asks for similar cases.
   Powerful but heavy. Revisit at v2.
7. **Display name** — "Headnote", "Headnote.in", "Headnote Research"?
   Pick before Meta submission.

---

## 16. Acceptance criteria for v1 GA

The bot is ready for public launch when **all** the following hold:

- [ ] FB Business verified, WABA approved, display name approved
- [ ] Webhook live on production with signature verification
- [ ] 100 representative test queries returned correct citations ≥ 95%
- [ ] P50 latency ≤ 30s, P95 ≤ 60s over 100 queries
- [ ] LINK flow works end-to-end with at least 3 real paid users
- [ ] Quota enforcement blocks the 4th free query
- [ ] PDF memo renders correctly across iOS and Android WhatsApp
- [ ] STOP keyword tested and verified silencing further messages
- [ ] Privacy page live at headnote.in/privacy
- [ ] No errors above 2% over a 72-hour soak with friendly users
- [ ] Total launch-month operating cost projected ≤ ₹500

---

## 17. Summary — cost recap

| Bucket | Launch (month 1) | Scale (5k conv/mo) |
|---|---|---|
| Setup (one-time) | ₹500 (SIM) | — |
| Meta Cloud API | ₹0 (free tier) | ~₹1,300 |
| Hosting | ₹0 (Render free) | ₹600 |
| LLM | ₹50–₹200 | ₹500–₹1,500 |
| Storage / CDN | ₹0 | ₹100 |
| **Total recurring** | **₹50–₹200** | **₹2,500–₹3,500** |
| Break-even paid users (@₹999/mo) | 1 | 4 |

**TL;DR for the wallet:** ₹500 to set up. ₹50–₹200/mo to run at launch.
Pays for itself with the first converted user.

---

*End of PRD v0.1. Update this file in place as decisions land in §15.*
