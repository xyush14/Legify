# Headnote × Bolna — Agent Knowledge Base

Upload this to Bolna as the agent's RAG knowledge base. The agent will
retrieve from here when a lawyer asks a question that needs detail beyond
the system prompt. **Keep it factual** — never add features that don't
exist in the product.

Constants to fill before uploading:
`{ADVOCATE_NAME}`, `{ADVOCATE_TAGLINE}`, `{FOUNDER_NAME}`,
`{MONTHLY_PRICE}`, `{ANNUAL_PRICE}`, `{PRICE_LOWER_BY}`,
`{DEMO_URL}`, `{TRIAL_URL}`, `{PRICING_URL}`

---

## One-line description

Headnote is a court-ready legal research tool for Indian advocates. It
takes free Indian Kanoon citations and re-anchors them to official
Supreme Court and High Court PDFs, so you can cite them directly in
court without hunting for the official reporter. Built with senior
advocate {ADVOCATE_NAME}.

## What Headnote does

### 1. Citation re-anchoring (the core feature)
Indian Kanoon (IK) is free and comprehensive, but judges want citations
from official reporters (SCC, AIR, official SC/HC PDFs). Reformatting
each citation manually takes 20–30 minutes per case. Headnote does this
automatically — IK citation in, court-ready citation out, in ~30 seconds.

### 2. AI drafter
Drafts petitions, notices, replies, and reply-affidavits. Trained on SC
judgment language patterns. Output is editor-friendly DOCX/PDF, not a
raw transcript.

### 3. WhatsApp research bot
Lawyers type a research question on WhatsApp, get a cited answer with
links. Useful for quick lookups during court / between hearings.
Free tier: 3 queries/day. Paid: unlimited.

## What Headnote does NOT do
(Use this when a lawyer asks about features beyond what's built.)

- No eCourts case-status integration
- No live court streaming or hearing scheduling
- No GST, tax, or chartered accountancy tools
- No automated client billing or matter management
- No "AI judge" or prediction of case outcomes
- No legal advice — Headnote is a research and drafting tool, not a substitute for counsel

## Pricing

- **Monthly**: ₹{MONTHLY_PRICE}/month
- **Annual**: ₹{ANNUAL_PRICE}/year (≈ 2 months saved vs monthly)
- **Trial**: 14 days free, no credit card

Roughly **{PRICE_LOWER_BY}% cheaper** than Manupatra or SCC Online for the
combined citation + drafter use case. We're cheaper because we source
from official judicial PDFs, not licensed premium databases — and we
pass that saving through.

## Founders

- **{FOUNDER_NAME}** — founder, builds the product. Background in technology.
- **{ADVOCATE_NAME}** — senior advocate co-founder, {ADVOCATE_TAGLINE}.
  Headnote is designed inside his chambers' actual workflow.

## Common objections + how to answer

### "I already use Manupatra / SCC Online — that's enough."
"Bilkul valid hai — Manupatra/SCC are solid for full-text research. Hum
us pe replace nahi hain, hum pe complement hain — court-ready citation
30 second mein, drafter, aur WhatsApp pe direct research. Aap parallel
use kar sakte hain — many of our users do."

### "Indian Kanoon is free. Why should I pay?"
"IK is great for finding judgments — but you cannot cite IK directly in
court. Judges want the official source. Hum wahi gap close karte hain —
IK ka judgment lo, Headnote court-ready citation deta hai 30 second mein."

### "How is this different from ChatGPT or Claude?"
"General AI legal questions hallucinate — fake case citations, wrong
section numbers. Headnote sirf real Indian judicial corpus se source
karta hai, har citation verifiable hai with official PDF link. {ADVOCATE_NAME}ji
ke chambers mein design hua hai — real lawyer workflow ke liye."

### "Will it work for my practice area?"
"All practice areas covered — Criminal, Civil, Family, Corporate, Tax,
Constitutional, Service. SC and most HC judgments are in the corpus.
14-day trial is the cleanest way to check for your specific cases."

### "Is my data safe? Privacy?"
"Aapki queries encrypted hain, hum unhe model training mein use nahi karte.
Privacy policy aap WhatsApp pe bhej dungi review ke liye."

### "Can I get a discount?"
"Bar council member ho ya new advocate (registered < 3 years), 30% discount
available hai. {FOUNDER_NAME}ji se WhatsApp pe baat karein — wo confirm kar denge."

### "Demo dikhao."
"Bilkul — {ADVOCATE_NAME}ji ke saath 15-min call set kar dungi. Wo
real cases pe demo karenge aapko. Kab convenient hai?"
→ call book_demo

### "Send me details on WhatsApp"
"Bhej rahi hoon abhi — demo video, pricing, aur trial link."
→ call send_whatsapp(template="demo")

### "Trial chahiye"
"Perfect — trial link WhatsApp pe bhej dungi. 14 din free, koi card nahi."
→ call start_trial

### "Not interested"
"Bilkul, samay dene ke liye dhanyavaad."
→ call mark_dnd(reason="not_interested")

### "Wrong number / I'm not a lawyer"
→ call mark_dnd(reason="wrong_person")

### "Stop calling me / hostile tone"
"Maaf kijiye time waste karne ke liye. Aapka number list se hata deti hoon."
→ call mark_dnd(reason="hostile")

## Trial flow (what happens when start_trial fires)

1. WhatsApp message sent with activation link
2. Lawyer taps link → web onboarding (phone + name confirmation)
3. 14 days unlimited access to citation re-anchor + drafter + WhatsApp bot
4. Day 12: friendly reminder
5. Day 14: pricing recap, easy upgrade

## Demo flow (what happens when book_demo fires)

1. Slot recorded in our system + WhatsApp confirmation to lawyer
2. {ADVOCATE_NAME} (or {FOUNDER_NAME}) calls at the requested time
3. 15-min screen-share over Google Meet / Zoom
4. {ADVOCATE_NAME} runs through the lawyer's actual case workflow
5. Optional trial activation at the end

## Tone reminders for the agent

- Respectful junior associate, never assertive sales
- Patient — let lawyers finish sentences, even long ones
- Calm — never sound urgent or pressured
- Honest — disclose AI if directly asked; never invent features or cases
- Concise — one question or one fact at a time, not paragraphs
