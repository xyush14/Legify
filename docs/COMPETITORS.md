# How we differ from LexLegis and the rest of the Indian legal-AI field

A focused look at the players you're competing with, what they sell, where they overlap with us, and where we draw the line.

---

## TL;DR

> **They are horizontal. We are criminal-law-only.**
> They are priced for law firms. We are priced for the junior advocate.
> They make AI-summarised case law. We make journal-format **and** practitioner-notes-format research, with hallucination-proofing baked into the architecture and a Hindi mode for tier-2/3 lawyers.
>
> Closest competitor on positioning: **LexLegis** (₹9k/seat/month, 10M+ documents, horizontal). Closest competitor on output style: **LegitQuest's iDRAF** (4-field schema, no full headnote format). Nobody is doing the criminal-only + practitioner-notes + BNS-bridge combination we are.

---

## The five players that matter

### 1. LexLegis.AI — the well-funded horizontal

| | |
|---|---|
| Founded | 2024, Mumbai |
| Founder | Saakar Yadav |
| Stage | Series A (well-funded, public profile via India AI Summit 2026) |
| Corpus | 20B tokens, 10M+ Indian legal documents |
| Pricing | Professional ₹9,000/user/month; Enterprise ₹17,250 |
| Core product | Four pillars — Ask (research), Interact (document analysis), Draft (drafting), MIRA (215-skill agent library across 24 functional groups) |
| Target | Mid-to-large law firms, in-house counsel, tax/legal professionals |

**What they do well:** scale, document-coverage breadth, drafting + agent skills. They've done the heavy lifting of indexing the entire Indian legal corpus and built a polished platform. They will be hard to compete with on coverage.

**Where they're weak for criminal practitioners:**
- **Horizontal by design.** Criminal law is one of many practice areas; the catchword taxonomy is shallow. A search for "S. 482 quashing on settlement, heinous offence carve-out" gets generic results, not a hand-curated criminal-law index.
- **Output format is conversational.** "Ask" returns a chatbot-style answer with citations attached. It does not produce Cri.L.J.-format headnotes with the six-element schema. Lawyers can't paste the output directly into a written submission.
- **Pricing is firm-grade.** ₹9,000/user/month = ₹1,08,000/year/seat. For a junior earning ₹15-20k/month, this is impossible. LexLegis isn't trying to serve that segment; their economics depend on enterprise seats.
- **No practitioner-notes mode.** The chambers-digest format from your gold doc is not a thing they produce.
- **No explicit BNS/BNSS bridge as a UX feature.** They probably index both, but mapping IPC precedent → BNS section as a one-click tool isn't surfaced.

**How we differentiate:** criminal-only depth + chambers-digest format + price point an order of magnitude lower (~₹500/month vs. ₹9k) + Hindi.

---

### 2. SCC Online + SCC Cri. — the editorial incumbent

| | |
|---|---|
| Owner | Eastern Book Company (EBC), Lucknow |
| Pricing | Single-user web edition ~₹35,000–₹70,000/year (varies by modules). Higher with criminal-law packs. |
| Core product | Editorial-team-written headnotes, the gold standard for citation. Now with AI add-on (SCC Times AI / SCC AI Search) layered on top. |
| Target | Senior counsel, large firms, judiciary |

**What they do well:** the headnote *itself* is the gold standard — written by experienced legal editors over decades. Senior advocates trust SCC headnotes the way doctors trust JAMA. The corpus is comprehensive.

**Where they're weak:**
- **Editorial-team bottleneck.** Their moat is also their constraint. They can't expand their per-judgment headnote coverage faster than their human editors can write. The BNS/BNSS transition is exposing this — re-indexing decades of IPC case law against BNS is a multi-year effort for them.
- **Price-protected, not customer-loved.** ₹35-70k/year is a tax for legacy access, not a product lawyers actively prefer. Junior lawyers do not have this subscription; they share senior's logins or work without.
- **AI add-on is a feature, not a thesis.** Their AI search is built to keep existing customers, not to disrupt their own pricing. They will not undercut themselves at ₹500/month.

**How we differentiate:** match their format quality at 1/60th the price. We are not trying to be SCC; we are trying to be the affordable alternative that does criminal law better than their criminal modules do.

---

### 3. Manupatra — the comprehensive aggregator

| | |
|---|---|
| Pricing | ~₹20,000–₹50,000/year per practitioner package |
| Core product | Comprehensive Indian legal database; "Manupatra Legal Tech Suite" launched AI features in 2024-25; AI-powered search, summary, and drafting modules |
| Target | All practice areas; mid-tier firms |

**What they do well:** breadth, includes statutes / circulars / notifications, decent search. Has been the go-to for non-Supreme Court material (tribunals, High Courts in detail) for years.

**Where they're weak:**
- Same horizontal-scope issue as LexLegis.
- AI features are a layer on top of existing search — not a re-imagined experience.
- No journal-format output; no practitioner-notes mode.

**How we differentiate:** see LexLegis. Same answer.

---

### 4. CaseMine + AMICUS — the citation-graph specialist

| | |
|---|---|
| Founded | 2013 |
| Pricing | Tiered subscriptions, generally lower than SCC/Manupatra |
| Core product | Citation graph and visualisation; AMICUS (launched 2023) is GPT-powered Q&A on the corpus. Their thesis: "use the language of the court instead of relying on third-party headnotes." |
| Target | Litigation counsel, especially appellate practice |

**What they do well:** the citation graph is genuinely useful. CaseMine knows which cases follow / distinguish / overrule which. This is hard to build and they have a decade head start.

**Where they're weak:**
- Their thesis is the **opposite of ours.** They believe lawyers should read the language of the court directly, not editorial summaries. Our thesis is that headnotes are the foundational artefact lawyers actually use, and AI's job is to produce headnote-grade output, not bypass it.
- AMICUS is generic Q&A — not journal format, not practitioner-notes format.
- No explicit BNS/BNSS bridge product yet.

**How we differentiate:** we believe the headnote is the killer artefact. We build *for* it, not around it. Long-term we may license or rebuild a CaseMine-style citation graph as a feature, but our core wedge is the format of the output.

---

### 5. Jhana.ai — the well-funded AI-native upstart

| | |
|---|---|
| Founded | 2022 (Harvard origin); Indian operation 2024 |
| Funding | $1.6M seed Sept 2024 (Together Fund + OpenAI/Razorpay/CRED founders) |
| Revenue | ₹2.58 Cr (Mar 2025) |
| Core product | "AI paralegal" — research, drafting, document Q&A, multilingual support |
| Target | Junior associates, mid-tier firms |

**What they do well:** strong brand, capital, a slick product, and explicit positioning toward associates (not just senior counsel). Multilingual support including Hindi is already shipped. They are the most likely competitor at our segment.

**Where they're weak:**
- **Generalist product.** Same horizontal-coverage problem. Criminal-law-specific catchword taxonomy is not deep.
- **No journal-format output.** Their summaries are conversational.
- **No chambers-digest format from gold-doc-style notebooks.**
- They will probably ship a criminal-law module before we exit beta. The question is whether their generalist DNA can produce headnote-grade output. Bet: not fast.

**How we differentiate:** vertical depth. Same answer.

---

## Side-by-side table

| Dimension | LexLegis | SCC Online | Manupatra | CaseMine | Jhana | **Us (v0)** |
|---|---|---|---|---|---|---|
| Practice-area focus | Horizontal | Horizontal | Horizontal | Horizontal | Horizontal | **Criminal-only** |
| Headnote-grade output | ❌ chat | ✅ editorial | ❌ summary | ❌ chat | ❌ chat | **✅ journal + practitioner** |
| Practitioner-notes / chambers-digest format | ❌ | ❌ | ❌ | ❌ | ❌ | **✅ unique** |
| BNS/BNSS bridge as UX | ⚠️ partial | ⚠️ partial | ⚠️ partial | ⚠️ partial | ⚠️ partial | **✅ first-class** |
| Hallucination-proof citations (verified at output) | ❓ | n/a | ❓ | ❓ | ❓ | **✅ structural** |
| Hindi-native output | ❓ | ❌ | ❌ | ❌ | ✅ | **✅ on toggle** |
| Junior-affordable pricing | ❌ ₹9k+/mo | ❌ ₹3-6k/mo | ❌ ₹2-4k/mo | ⚠️ varied | ⚠️ undisclosed | **✅ targeting ₹299–₹999** |
| Corpus size | 10M+ docs | comprehensive | comprehensive | strong | growing | **42 (v0); 5,000+ (v1)** |
| Citation graph | ⚠️ basic | ✅ editorial | ✅ basic | ✅ best in class | ⚠️ basic | **🚧 v2** |
| Drafting | ✅ | ❌ | ✅ | ❌ | ✅ | **🚧 v2** |
| Document Q&A on user-uploaded files | ✅ | ❌ | ✅ | ❌ | ✅ | **🚧 v2** |

`✅` = shipped · `⚠️` = partial · `❌` = absent · `❓` = unclear / unverified · `🚧` = roadmap

---

## What this means strategically

### Where we explicitly do not compete (yet)

- **Document analysis, contract review, drafting, agent workflows.** LexLegis ships 215 agent skills; we ship 0. That's fine. We are choosing to win one specific job (case-law research for criminal lawyers) and win it deeply, not to be the "AI paralegal" everyone else is racing to be.
- **Comprehensive coverage.** LexLegis has 10M documents. We have 42 in v0. Coverage is the next 18 months of work and the biggest single capital cost.
- **Big-firm enterprise sales.** That's their channel; ours is junior advocates and bar-association partnerships.

### Where we will win (the short list)

1. **Format.** Nobody else produces journal-format AND chambers-digest output as a first-class feature. Both are exactly what lawyers actually use day-to-day. Our gold-doc study (your uploaded notebook) is a competitive moat — we know what good looks like.
2. **Trust.** After the Feb 2026 SC ruling on AI-generated fake citations as misconduct, "verified citations only, by architecture" becomes a real differentiator. Our case-id verification layer is explicit; theirs is implicit.
3. **BNS bridge.** A 24-month indexing transition opportunity. The incumbents' indexing pace is constrained by editorial teams; we can encode the IPC↔BNS mapping in the prompt and ship it tomorrow.
4. **Price.** ₹500/month vs ₹9,000/month is not an incremental difference. It opens up the 200,000+ junior-advocate segment that nobody currently serves.
5. **Hindi.** Jhana ships multilingual generally; we make Hindi a one-click toggle that preserves citations, statute names, and paragraph anchors verbatim. For a tier-2/3 advocate in Bhopal or Patna, this is a meaningful UX win.
6. **Vertical depth.** Criminal-law catchword taxonomy goes 4-5 levels deep (e.g., "Murder → Common intention vs. common object → S. 34 IPC vs. S. 149 IPC → Mere presence vs. participation → Burden on prosecution"). Nobody else encodes this.

### The honest risk

Jhana, with $1.6M seed and a year head start on us in the AI-native space, will probably ship a criminal-law module within 6-9 months. They will copy practitioner notes within a quarter of seeing it. The defensibility lives in:
- **Speed of corpus expansion.** Get to 5,000 cases in 6 months, 25,000 in 18 months.
- **Lawyer feedback flywheel.** Every 👍/👎 + correction in our SQLite is a labelled training example. Their generalist product can't accumulate criminal-law-specific signal at our density.
- **Brand owned by criminal-law trust.** Become the tool every public prosecutor and criminal advocate names when asked "how do you research case law?" That brand position is hard to dislodge once owned.

---

## What I'd do in their shoes (and how to defend)

If I were Saakar at LexLegis, I would not bother building practitioner-notes format. The juice isn't worth the squeeze for their segment.

If I were Jhana, I would build a criminal-law mode within 4-6 months. That's the real threat. The defence is: ship the corpus + format + flywheel before they do.

If I were SCC, I would price-discriminate and launch a "junior tier" at ₹999/month with reduced features. They probably won't, because it cannibalises the senior-counsel ₹70k subscriptions. The strategic immobility of their pricing is our wedge.

The play: don't get in a feature war. Get in a brand war. Own "the criminal law tool" the way Carta owns cap tables, the way Linear owns issue tracking.
