# WhatsApp Capture — the chamber's inbox

**Status:** design only, not built. Written 2026-08-06.
**Companion doc:** `docs/WHATSAPP_BOT_PRD.md` (the *outbound* research/draft
bot — different product, same webhook).
**Sequencing decision (Ayush, 2026-08-06):** design now, build later. This
does **not** go into the V2 branch. It is V2.1 at the earliest.

---

## 1. The idea in one line

The lawyer never opens Headnote to put information *in*. They WhatsApp us,
and it lands in their account, filed to the right matter.

Today the flow is: walk out of court → remember to open Headnote → find the
matter → type the diary entry → upload the order sheet. Four steps that
mostly don't happen. District advocates live in WhatsApp all day. If capture
happens where they already are, it happens. If it needs an app, it doesn't.

This is a **retention** feature, not an acquisition one. The existing
WhatsApp bot (research + bail drafting) is a funnel for strangers. This turns
the same number into the daily habit surface for paying users.

---

## 2. What already exists, and what's actually missing

Most of the plumbing is built. Three things are not.

### Already built (reuse, do not rebuild)

| Piece | Where |
|---|---|
| Meta + Twilio inbound webhook, signature verify, dedupe | `headnote/api/whatsapp.py` (`/api/whatsapp/webhook`) |
| Background dispatch (webhook acks fast, work runs after) | `whatsapp.py:45` `_spawn_bg` |
| Outbound send with provider fallback | `whatsapp.py:908` `_try_send_with_fallback` |
| Inbound image handling + OCR into a flow | `whatsapp.py:762` `_ocr_and_advance` |
| Matters / diary: cases, hearing logs, next date | `headnote/cases/storage.py`, `/api/cases/diary` |
| Diary photo → OCR → review → save | `/api/cases/import/diary-photo`, `/diary-confirm` |
| Document Vault upload + OCR | `/api/documents/upload` |
| Phone on the account + Indian-number normaliser | `user_profiles.phone`; `headnote/api/payments.py:62` |
| Hindi/handwriting OCR | Gemini primary, Sarvam+DeepSeek fallback |
| Voice transcription | Groq Whisper, already used by the Recorder |

### The three gaps

**Gap 1 — the bot has no idea who is texting.**
Every inbound message is keyed to a bare phone number. `LINK` is a stub that
replies *"account linking is coming soon"* (`whatsapp.py:619`). Nothing the
bot does today reaches anybody's Headnote account. This is the entire feature
and it is also the smallest piece of work, because the lawyer signed up with
a phone number and WhatsApp **is** a phone number.

**Gap 2 — expenses do not exist anywhere in the product.**
Not in matters, not in cases, nowhere. Genuinely net-new: one table, one
parser, one screen.

**Gap 3 — the message router is a stub.**
`_handle_inbound_message` (`whatsapp.py:563`) treats any text over 10
characters as a research query. It needs to distinguish diary from expense
from document from research from draft.

---

## 3. Identity — the auto-link

**Rule: no linking ceremony.** The lawyer signed up with +91XXXXXXXXXX. They
are messaging us from +91XXXXXXXXXX. We match those. Their first message
already works.

```
inbound wa_phone
  → normalise to 10 digits (reuse payments.py:62 normaliser)
  → SELECT user_id FROM user_profiles WHERE phone_digits = ?
  → hit  : this is a linked lawyer, full capture unlocked
  → miss : anonymous — existing research/draft bot behaviour, unchanged,
           plus one line: "Using Headnote on a different number?
           Reply LINK."
```

`LINK` (the fallback path, for a second SIM or a chamber phone):
bot asks for the signup number → OTP goes to *that* number through the
existing OTPless machinery → lawyer pastes the code into WhatsApp → link
written. Reuses `headnote/api/auth_otpless.py`, no new auth code.

### Security rules, non-negotiable

- **One WhatsApp number maps to exactly one account.** Unique index.
- **Re-linking an already-linked number to a different account requires
  admin action.** This blocks SIM-swap account takeover. A lawyer who
  genuinely changed numbers contacts support.
- **Capture only, never disclosure.** An unverified inbound number can *add*
  to an account but must never be able to *read* it back. "Show me the Sharma
  file" over WhatsApp is a data-leak vector on a stolen phone. Reads are
  deferred to a later phase behind a re-auth, and are out of scope here.
- Message bodies are logged truncated to 500 chars, as today.

---

## 4. The capture loop

One message in, one receipt out. That's the whole interaction.

**Lawyer sends** (typed, or a 20-second voice note in Hindi):

> रमेश vs स्टेट, आज तारीख पड़ी 14 अगस्त, जज ने बेल बांड मांगा,
> 500 court fee 200 auto

**Headnote replies in ~3 seconds:**

```
✅ Filed to Ramesh v. State of MP — Sessions Court, Bhopal
📅 Next date: 14 Aug 2026  (was today)
📝 Diary: judge asked for bail bond
💰 ₹500 court fee · ₹200 travel → case total ₹4,300

[✓ Correct]   [Wrong matter]   [Undo]
```

Those are WhatsApp interactive buttons, free inside the service window.

### When it isn't sure which matter

It asks. It does not guess.

```
Which matter?
1️⃣ Ramesh v. State of MP — Sessions, Bhopal (next: today)
2️⃣ Ramesh Kumar v. LIC — Civil Judge, Bhopal
3️⃣ New matter
Reply with the number.
```

### The receipt is the product

The receipt is not politeness, it is the safety mechanism. It is how a
lawyer catches a mis-filed entry in the two seconds they still remember what
they sent. Silent success is worse than a wrong guess the lawyer can see.

---

## 5. What v1 accepts

**All four input types, in v1.** They are not separable in a messaging
interface: a lawyer will send a voice note whether or not we planned for one,
and a bot that answers *"I can only read text"* is a dead feature. The
back-end after transcription/OCR is a single shared pipeline, so the marginal
cost of each extra lane is small.

| Lane | Path | Reuses |
|---|---|---|
| **Text** | parse → classify → file | new parser |
| **Voice note** | Whisper (hi/en) → same text pipeline | Recorder's Groq Whisper |
| **Photo** | OCR → classify (order sheet / receipt / notice) → Vault + matter | `documents.py`, `diary-photo` OCR |
| **PDF forward** | order copy, notice → Vault + matter | `/api/documents/upload` |

**Voice is the one that decides adoption.** These advocates will not type
Devanagari on a phone. They will talk for twenty seconds walking to the car.
Hindi voice → filed diary entry is the single highest-value path in this doc.

### What gets captured

**Diary entry** → a hearing log on the matter: what happened, what the judge
said, what's needed next. Updates the matter's next date if a date is
present. This feeds the existing daily brief and the V2 Home readiness view
for free.

**Expense** → a row against the matter (see §7).

**Document** → Document Vault, attached to the matter, OCR'd and searchable.

Everything else (a legal question, `DRAFT BAIL`) falls through to the
existing bot behaviour, untouched.

---

## 6. Matter matching

The hard problem is not the webhook, it's *which case is this*.

Matching signals, in order:
1. **CNR or case number** in the message — exact, done.
2. **Party name** fuzzy-matched against the lawyer's matters
   (transliteration-aware: "रमेश" must match "Ramesh").
3. **Today's cause list.** If the lawyer has three hearings today and says
   "tareekh pad gayi", it is almost certainly one of those three. This is the
   strongest signal and the cheapest.
4. **Last matter this lawyer captured to**, within a short window — sending
   two messages in a row about the same case is the norm.

**Confidence ladder:**

| Confidence | Behaviour |
|---|---|
| High (CNR, or one strong name match) | File it, show the receipt |
| Medium (2–3 candidates) | Numbered list, wait for a tap |
| Low / none | "Which matter? Reply with the name, or NEW to create one" |

Never file to a guessed matter. A diary entry in the wrong file is worse
than no diary entry, because the lawyer will trust it at the next hearing.

---

## 7. Expenses

Net-new. Small table, big retention payoff.

```sql
CREATE TABLE matter_expenses (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id     UUID NOT NULL,
  matter_id   UUID,                    -- nullable: unattached expense
  amount_paise BIGINT NOT NULL,        -- integer paise, never float
  head        TEXT NOT NULL,           -- court_fee | clerk | travel |
                                       -- photocopy | stamp | misc
  note        TEXT,
  incurred_on DATE NOT NULL,
  source      TEXT NOT NULL,           -- whatsapp | web | receipt_ocr
  billable    BOOLEAN NOT NULL DEFAULT TRUE,
  billed_at   TIMESTAMPTZ,             -- null = unbilled
  created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX matter_expenses_user_matter_idx
  ON matter_expenses(user_id, matter_id, incurred_on DESC);
```

Money as **integer paise**. Never floats, never strings.

**Parsing rules (zero-fabrication applies):**
- An amount is recorded only if a number appears in the message. Never
  inferred, never estimated, never rounded.
- Head is inferred from the words present ("court fee", "कोर्ट फीस",
  "clerk", "auto"/"travel", "photocopy"/"xerox"). No match → `misc`,
  and the receipt says `misc` so the lawyer can correct it.
- A bare number with no context is **not** an expense. "Section 420" and
  "500 court fee" must not both become ₹500. When ambiguous, ask.

**The payoff — this is why expenses matter more than they look.** District
advocates bleed money on untracked kharcha: ₹300 here, ₹1,500 clerk fee
there, never written down, never billed. At month end Headnote produces a
per-client statement of unbilled expenses that they can actually send. That
is money in their pocket that they did not have before, attributable to us.
It is also the stickiest data in the product: once a year of expenses is in,
they do not leave.

**New screens:** an Expenses tab on the matter, and a per-client statement
(print/PDF, reuse the existing PDF path). Both follow the white dense work
surface rules in `feedback_app_ui_direction`.

---

## 8. Safety rules

The zero-fabrication promise, applied to capture:

1. **Never invent a value.** Dates, amounts, names, next hearing dates exist
   only if the lawyer said them. An unparseable message gets a question, not
   a best guess.
2. **Never file silently.** Every write produces a receipt with `Undo`.
3. **Never file to a guessed matter.** Ambiguity → ask.
4. **Undo is real.** Soft-delete with a reversal, not a tombstone the lawyer
   can't see. Undo window: until the next message, minimum 15 minutes.
5. **Capture only, no reads** (see §3).
6. **The extraction model is a parser, not an author.** It labels spans of
   the lawyer's own words. It never writes prose into a diary entry.

---

## 9. Cost

Every message here is **lawyer-initiated**, so it rides the 24-hour service
window: free up to 1,000 conversations/month, then roughly ₹0.30 per
conversation (verify current rates at launch — Meta has changed pricing
twice in two years). A conversation is 24 hours, not a message, so a lawyer
sending eight diary entries in a day costs one conversation.

**The capture channel is effectively free to run.**

Per-message compute: Whisper transcription and OCR are already in the stack;
extraction is a small DeepSeek V3 call, well under ₹0.05.

Contrast with pushing *out* (an 8 pm "tomorrow's board" message): that is
business-initiated, needs an approved utility template, ~₹0.16 per
conversation, and Meta approval lead time. Deferred — see §11.

---

## 10. Technical delta

```
headnote/
├── api/
│   └── whatsapp.py          # MODIFY — resolve phone→user before dispatch;
│                            #   route to capture when linked
├── whatsapp/
│   ├── identity.py          # NEW — normalise, resolve, LINK/OTP flow
│   ├── capture.py           # NEW — classify → extract → match → file
│   ├── matcher.py           # NEW — matter matching + confidence ladder
│   └── receipts.py          # NEW — receipt text + interactive buttons
├── expenses/
│   ├── __init__.py          # NEW
│   └── storage.py           # NEW — CRUD + per-matter/per-client rollups
├── api/
│   └── expenses.py          # NEW router — /api/expenses/*
└── migrations/
    ├── 014_wa_identity.sql  # user_profiles.wa_phone + unique index
    └── 015_expenses.sql     # matter_expenses
```

Reused unchanged: the webhook and its signature verification, `_spawn_bg`,
the send/fallback path, Groq Whisper, the OCR stack, `cases/storage.py`,
`documents/storage.py`, OTPless.

**Note on storage:** expenses must go to **Postgres**, not the SQLite
volume. Cases are already on Supabase; putting money on the single-machine
SQLite volume repeats the split that `project_home_cockpit` flags as needing
consolidation.

---

## 11. Build order

| Phase | What | Ships value on its own? |
|---|---|---|
| **1** | Identity: phone→account auto-link + `LINK` fallback | Yes — the existing research/draft bot immediately starts writing to real accounts |
| **2** | Capture pipeline: classify → extract → match → receipt → file. Diary + expenses. Text and voice. | Yes — this is the feature |
| **3** | Photos and forwarded PDFs → Vault + matter | Yes |
| **4** | Expenses UI: matter tab + client statement PDF | Yes — the billing payoff |
| **5** | Push back out: 8 pm "tomorrow's board" utility template | Needs Meta template approval |

Phase 1 is independently useful and low risk. Phases 2–4 are the product.

---

## 12. Decisions still open (need Ayush)

1. **Provider.** Both Meta and Twilio paths exist in code. Which is the
   production number, and is it a verified WABA on a dedicated number? A
   capture channel cannot run on a test number.
2. **Sequencing against V2.** Confirmed: *after* V2 ships. Restate when V2
   is out.
3. **Number strategy.** Same WhatsApp number for the public research bot and
   for paying users' capture? Recommend yes — one number to remember, and
   linked vs anonymous is decided by lookup, not by number.
4. **Expense heads.** The six above are a guess. Vishnu ji should confirm
   what an MP district advocate actually books.
5. **Group chats.** Explicitly out of scope. A lawyer forwarding a client's
   group message is a privacy question we have not answered.

---

## 13. Explicitly not in scope

- Reading data back out over WhatsApp (§3, security)
- Group chat support
- Client-facing WhatsApp (clients messaging the lawyer through Headnote)
- Payment collection over WhatsApp
- Anything that writes to a matter without a receipt
