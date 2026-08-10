# Drafter Quality & Corpus Roadmap

**Owner:** Ayush · **Drafted:** 2026-07-05 · **Status:** Phase 0 started — authoring routed to R1 (done)

> **Decision (2026-07-05):** staying on **DeepSeek** — no Gemini / Sonnet / Opus swap.
> The V3→R1 move is *within* DeepSeek (reasoning tier of the model we already use), not a
> provider switch. Gemini/Sonnet/Opus comparisons below are kept for reference/future only;
> the A/B is now **V3 vs R1**.

The plan for closing the gap between what Headnote's drafter produces today and what
a practising advocate will actually file. Captures the diagnosis, the model strategy,
the quality system, and the corpus/retrieval strategy worked out on 2026-07-05.

---

## 0. The thesis

> We are ~80% good. The last 20% — a wrong section, a cause-title that disagrees
> between page 1 and page 3, flat idiom, a generic ground where a specific one was
> needed — is what kills trust. In litigation, 80% right is **not** 80% useful: the
> lawyer has to re-check everything, which defeats the point. The bar is *"I can file
> this with minor edits."*

Two truths that shape everything below:

1. **The model is not the moat.** Anyone can call DeepSeek/Gemini/Claude. The
   defensible product is a **cleaned, anonymised, pan-India corpus of real filings +
   a retrieval layer + a quality/eval loop.** This is exactly what every serious
   player does (CoCounsel, Harvey, Bloomberg, and India's Jhana with its 16M-doc
   "National Legal Archive"). None of them fine-tune on documents — they **retrieve**.
2. **"Train ourselves" ≠ fine-tune.** Fine-tuning DeepSeek is impractical for us
   (hosted API, no realistic fine-tune path, can't train locally). The effective
   substitute — and the industry standard — is **in-context learning**: full skill +
   real matter-specific exemplars + retrieval. Gets ~90% of what fine-tuning would, at
   ~zero training cost.

---

## 1. Diagnosis — why platform output ≠ direct-Claude output

When Ayush prompts Claude directly he gets a 9/10 draft. The platform gives 5–6/10 on
the part that matters (the "यह कि …" grounds). Three compounding causes, biggest first:

| Factor | Direct-to-Claude | Platform today | Impact |
|---|---|---|---|
| **Model** | Opus 4.8 / Sonnet 4.6 | DeepSeek **V3** (`deepseek-chat`, the *cheapest, no-reasoning* tier) | ★★★ |
| **Skill context** | Full `headnote-legal-drafting` skill auto-injected | Only a hand-copied slice in `_MIRROR_SYSTEM` etc. | ★★★ |
| **Reasoning** | Extended/adaptive thinking before writing | Single stateless call, temp 0.2, no thinking | ★★ |

**Root cause in code:** every authoring path routes straight to
`_call_deepseek_or_groq(..., claude_model="claude-haiku-4-5")`, which maps to
`deepseek-chat` (V3) — the *weakest* DeepSeek tier — and skips Claude entirely.
See `headnote/drafter/author.py:1345`, `from_prompt.py:497`, `suggest.py:140`,
mapping at `headnote/llm/client.py:45`.

---

## 2. Decisions made in this chat

- **Stay on a cheap model for now** (no raise required to improve quality — most of the
  gap is skill + reasoning + retrieval, not the model tier).
- **The moat is the corpus + retrieval + eval loop**, not the model.
- **One `.env`-switchable model router** so drafting can flip cheap → premium without
  touching drafting code.
- **Vishnu ji's drafts are reference knowledge, not the industry.** Breadth comes from
  a multi-source corpus (below), not one lawyer's folder.
- **Zero-fabrication and existing deterministic guards stay** regardless of model.

---

## 3. Model strategy

### 3a. Fix the stale price first (do immediately)
`config.py:326` has `PRICE_OPUS` at **$15/$75** — that's Opus-3-era pricing and it
**overstates Opus 4.8 by 3×** on the in-app cost meter. Real Opus 4.8 = **$5/$25**
(and now 1M context at standard price). Fix the constant so the meter tells the truth.

### 3b. Per-draft economics (warm cache; ~32K in / 6K out; ₹84/USD)

| Model | In / Out ($/M) | ≈ ₹/draft | Hindi-legal fit | Role |
|---|---|---|---|---|
| Gemini 2.5 Flash-Lite | 0.10 / 0.40 | ₹0.5 | Good | cheap classify/suggest |
| **DeepSeek V3** (today) | 0.27 / 1.10 | ₹0.8 | Mediocre (flat) | what we ship now |
| **DeepSeek R1** (reasoner) | 0.55 / 2.19 | ₹2.6 | Better (CoT) | **cheap authoring upgrade** |
| **Gemini 2.5 Flash** | ~0.30 / ~2.50 | ₹2.1 | **Strong** (Google's Indic lead) | **best cheap authoring candidate** |
| GPT-5 mini | 0.25 / 2.00 | ₹1.7 | Decent | alt |
| Sonnet 4.6 | 3.00 / 15.00 | ₹8.8 | Excellent | **post-raise / premium** |
| Opus 4.8 | 5.00 / 25.00 | ₹14.7 | Best | hardest drafts / max toggle |

### 3c. The routing plan
- **Now (no raise):** authoring → **DeepSeek R1** (not V3) *and/or* **Gemini 2.5 Flash**
  (Google leads on Indic languages; likely a real step up over V3 at ~₹2/draft).
  Prove which with the A/B (see §5c).
- **Post-raise / premium tier:** flip one env var → **Sonnet 4.6**.
- **Keep DeepSeek → Groq** as the automatic fallback so the surface never goes dark.
- **Keep cheap tier (DeepSeek V3 / Gemini Flash-Lite)** for classify/suggest/chat —
  no reason to pay more there.

**Every player validated this:** retrieve-then-write with a grounded model beats a
bigger model writing from nothing.

---

## 4. Making the current model "best" — without fine-tuning

Highest-leverage first. All are in-context (no training), cheap, model-agnostic.

1. **Route authoring to R1, not V3** — one-line change per call site. Biggest free win.
2. **Inject the full skill, cached** — pipe the entire `headnote-legal-drafting` skill
   (grounds libraries, BNSS↔CrPC maps, format rules) into the authoring system prompt
   as a stable, cached prefix. DeepSeek context-cache reads it at ~$0.07/M → nearly
   free on repeat drafts. This is *half* the quality gap.
3. **Few-shot gold exemplars** — 1–3 real, matter-matched drafts in the prompt. This is
   the true substitute for "training" — it teaches register and idiom. (Seed from
   Vishnu ji's reviewed grounds; expand from the corpus in §6.)
4. **Tighten the authoring system prompt** — advocate persona, two-source rule
   (reference = format, brief = facts, never invent), explicit structure.
5. **Matter-aware retrieval** — pull only the relevant grounds/template slice for the
   detected matter type (bridges into §6).

---

## 5. The quality system — the engine that gets us 80 → 98

You can't prompt your way to the last 2%, and you can't eyeball it either. Legal
quality is a **trust gate**, not an average. Two distinct failure classes, two fixes:

### 5a. "Small things" (mechanical) → a self-check / critic layer
Deterministic, catchable **before the lawyer sees the draft**:
- Section mismatch (IPC/BNS, CrPC/BNSS) → check vs section map
- Court / cause-title disagreeing across sheets (already hit: bail Index=Gwalior vs
  App=Jabalpur — see the court-location rule)
- Prayer not matching the relief sought
- Dates / money / names not traceable to the brief → fact-grounding guard
- Placeholder / party-designation / formatting slips → draft-page quality bar

Build a **second-pass validator** (deterministic checks + a cheap reasoning self-critique)
that auto-fixes or flags each. Model-agnostic; helps every model equally.

### 5b. "Smart understanding" (judgment) → reasoning + right exemplars
Matter-appropriate grounds, the argument a real advocate would make, correct register.
Fixed by R1/thinking + matter-specific few-shot + retrieval (§4, §6).

### 5c. The measurement loop → an eval harness
A fixed panel of ~20–30 test briefs with expected matter type / sections / grounds /
format. Every prompt/model/example change is **scored**, so improvement is provable and
regressions are blocked. This is the difference between "feels better" and
"correctness 81% → 94% on the panel." **The A/B (DeepSeek V3 vs R1 vs Gemini Flash vs
Sonnet, full skill injected) is the first use of this harness.**

### 5d. Failure taxonomy
Label the small errors on real generated drafts → build the self-check checklist from
evidence, not assumption. Feeds 5a and the few-shot set.

---

## 6. Corpus & retrieval strategy — the moat

**Industry evidence (all retrieve, none fine-tune on docs):** CoCounsel/Thomson Reuters,
Harvey, Bloomberg; academic RAG-for-drafting; Jhana's 16M-doc archive + verifier/graph
models; DraftBotPro's reference-mirror (which is *our existing mirror engine*).

We already own most of the parts: **bge-small embeddings** (Document Vault), **Groq OCR**,
the **mirror engine**, the **skill**. This is assembly + data acquisition, not greenfield.

### 6a. Three sourcing tiers
- **Tier 1 — free & authoritative (start here):** NALSA / State Legal Services Authority
  formats (free, government, pan-India by design); bar-council & law-school drafting
  corpora (DU Law Faculty, ICSI); courtbook.in for the *coverage map* only (don't clone
  text); eCourts/published judgments for verified citations.
- **Tier 2 — purchased advocate folders (breadth engine):** buy practising advocates'
  precedent folders **with explicit usage rights**. Fastest route to real, filed,
  matter-diverse drafts across states. (Non-code track — Ayush can start negotiating now.)
- **Tier 3 — consent flywheel (the real moat):** capture lawyers' final filed drafts +
  edits **with consent** back into the corpus. Compounds; uncopyable.

### 6b. Two hard guardrails (non-negotiable)
1. **Anonymise before ingesting** — strip PII (party names, facts, addresses) for the
   DPDP Act + professional confidentiality, *and* so client data never leaks into a
   generated draft. Learn structure/idiom, never carry the parties.
2. **Respect IP** — formats/boilerplate are largely functional (weak protection);
   curated collections and drafted arguments are not. Learn patterns from everything,
   redistribute nobody's folder verbatim, get written rights on anything purchased.

### 6c. The pipeline ("training ourselves" = this)
```
acquire
  → anonymise + normalise into {matter_type, state, court, sections,
      cause_title, grounds[], prayer, format}
  → embed into a retrieval corpus (reuse bge-small), keyed by matter/state/court
  → at draft time: retrieve the closest real filing, put it in front of the model
  → generate → guards + self-check validate → show provenance
```
This is how you get "smart understanding across the industry" without fine-tuning:
the model always has a real, relevant, human-drafted exemplar for exactly this matter.

---

## 7. Sequenced roadmap

Legend: 🛠️ code · 📄 spec/data · 💰 acquisition (non-code)

**Phase 0 — quick wins (days)**
- ✅ **Route authoring V3 → R1** — DONE 2026-07-05. New `config.DRAFTER_AUTHOR_MODEL`
  (default `claude-sonnet-4-6` → DeepSeek `deepseek-reasoner`) wired into `author_payload`,
  `revise_document`, `mirror_document`, `revise_mirrored` in `headnote/drafter/author.py`.
  Extraction/classify/suggest/skeleton stay on V3. Env escape hatch: set
  `DRAFTER_AUTHOR_MODEL=claude-haiku-4-5` to fall back to V3 if latency hurts a demo.
- ✅ **FULL skill injection** — DONE 2026-07-05. Correction to the earlier note: only a
  *distilled slice* was present (`HOUSE_STYLE` slotted the section map + per-type brief +
  skeleton + verified cites). The **entire** `headnote-legal-drafting` skill (SKILL.md +
  court-formats + legal-frameworks + application-frameworks + bail grounds library +
  taxonomy, ~14K tokens) now prepends the authoring system prompt as a **stable, cached
  prefix** via `headnote/drafter/skill_context.py`, wired into `_author_system()`
  (`author.py`). Stable-first ordering → DeepSeek prefix-cache hits (~$0.07/M on repeats).
  `.claude/skills/` is gitignored (not deployed) so the refs are mirrored into
  `headnote/drafter/skill_refs/` (tracked); re-sync with `python scripts/sync_skill_refs.py`.
  Toggle off with `DRAFTER_INJECT_SKILL=0`. Mirror path left untouched (reference = format).
  Guards (`guard_sections`, `_guard_citations`, grounding) unchanged and still fire.
- ✅ **Invalid-JSON 502 crash fixed** — DONE 2026-07-05. The "Model returned invalid JSON:
  Expecting value: line 1 column 1 (char 0)" 502 was R1 (`deepseek-reasoner`) spending its
  whole 4K-token budget on chain-of-thought and returning EMPTY content → `json.loads("")`.
  Fixes in `headnote/llm/client.py`: (1) reasoner gets a 12K-token output floor so it can
  actually emit the draft; (2) empty content is treated as a failure → Groq fallback, never
  handed to the parser; (3) `response_format={"type":"json_object"}` on V3/Groq JSON calls;
  (4) `parse_json_response` salvages the largest `{...}` span and, on total failure, raises a
  human "tap Draft it again" message, not a raw stack trace. Also fixed a latent twin bug:
  `prompt_tweak` was sending R1 only 500 tokens (guaranteed empty) → moved to V3.
- ✅ **Eval harness built** — `scripts/eval_drafter_ab.py`. Runs a fixed brief panel
  (bail · maintenance · recovery suit · a Sharma→Verma **mirror** leak-test) through V3
  and R1, scores the mechanical "small things" (grounds count, closer line, prayer,
  correct statute, body-citation leaks, ungrounded facts, reference-fact leak), prints a
  side-by-side table, and writes both drafts to `eval_out/` for eyeballing register.
  Requires a real `DEEPSEEK_API_KEY` (guarded — without it both tiers collapse to Groq
  and the A/B is meaningless). **Run pending** a DeepSeek key in the environment.
- 🔎 **First self-check finding (from a dry run):** the mandatory oral-arguments closer
  ("…अन्य तर्क वक्त बहस…") was missing from every draft → becomes a Phase-1 self-check
  gate (deterministic, auto-appendable). Also `closer` scorer confirmed working.
- ⬜ (Optional) fix stale `PRICE_OPUS` meter constant — low priority, we're not using Opus.

**Phase 1 — quality system (1–2 weeks)**
- 🛠️ Self-check / critic layer for the mechanical failure class (§5a)
- 📄 Failure taxonomy from real drafts (§5d)
- 🛠️ Model router behind one env var (cheap ↔ premium) (§3c)
- 🛠️ Few-shot exemplar bank wired into authoring (§4.3)

**Phase 2 — corpus & retrieval (2–4 weeks + ongoing)**
- 📄 Corpus schema + anonymisation rules + consent language (§6b/6c)
- 🛠️ Ingestion/anonymisation pipeline; retrieval layer on bge-small (§6c)
- 🛠️ Wire retrieval into the drafter (nearest exemplar + provenance) (§6c)
- 📄💰 Seed Tier 1 (free authoritative); begin Tier 2 folder acquisition (§6a)
- 🛠️ Turn on Tier 3 consent flywheel from day one (§6a)

**Phase 3 — compounding**
- Feed caught failures → few-shot + guards; grow the eval panel; widen coverage by
  matter type / state / court (use courtbook coverage map for the roadmap).

---

## 8. Open decisions / what's needed from Ayush

- **A/B verdict:** which cheap model wins on *our* Hindi legal drafts — R1 or Gemini Flash?
  (The harness will tell us; needs a go on building it.)
- **Tier 2 budget & rights:** willing to pay advocates for precedent folders + get usage
  rights? Which practice areas/states first?
- **Consent language:** are we comfortable capturing users' final drafts (anonymised,
  opt-in) into the corpus? Needs a one-line ToS/consent decision.
- **Anonymisation bar:** auto-redact + human spot-check, or human-in-loop for the first batch?

---

## Appendix — sources
- Thomson Reuters, *AI-powered legal drafting* — https://legal.thomsonreuters.com/en/insights/white-papers/ai-powered-legal-drafting-the-definitive-guide-for-legal-professionals
- Harvey, *AI for legal drafting* — https://www.harvey.ai/blog/ai-for-legal-drafting
- RAG for legal document building (ScienceDirect) — https://www.sciencedirect.com/science/article/pii/S2212473X25001014
- Jhana (National Legal Archive) — https://jhana.ai/
- DraftBotPro — https://www.draftbotpro.com/
- Gemini pricing — https://ai.google.dev/gemini-api/docs/pricing · Flash-Lite $0.10/$0.40 — https://devtk.ai/en/models/gemini-2-5-flash-lite/
- OpenAI pricing — https://developers.openai.com/api/docs/pricing
- DU Law Faculty pleadings material — https://lawfaculty.du.ac.in/userfiles/downloads/LLBCM/Drafting-Pleadings-and-Conveyancing.pdf
- ICSI drafting programme — https://www.icsi.edu/media/webmodules/Drafting_Apperances_Pleadings_NewSyllabus.pdf.pdf
