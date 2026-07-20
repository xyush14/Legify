# Draft DNA — per-advocate drafting personalization

**Status:** BUILT end-to-end (Phases 1–3), 2026-07-20. Ships dark — engages only for an
account with a saved profile; no-DNA output is byte-identical (§7 golden-master test green).
Code: `headnote/drafter/style_profile.py` (StyleProfile, format_slots, apply_format, analyze_style,
load/save), parameterized `HOUSE_STYLE` + `style=` thread in `author.py`, `user_id` + apply_format
chokepoint in `from_prompt.py`, `/api/draft-dna` router (`headnote/api/draft_dna.py`), Phase-2
reveal/confirm UI in `static/settings.html`, live chip in `static/draft-editor.html`,
`migrations/010_draft_dna.sql`, tests in `tests/test_draft_dna.py`. Phase 4 (continuous
learning from /refine + hand-edit diffs) and the v2 DNA-as-synthetic-reference path remain.
**Owner:** Ayush · reviewer: Vishnu ji
**One line:** an advocate drops 2–3 of their filed drafts in the **Profile** section; Headnote
learns their court, format and voice, and thereafter *every* draft it produces — including
prompt-based ones — comes out in their exact formatting, framing and register. Facts are never
learned or reused.

---

## 1. Why & positioning

US legal-AI (Spellbook Library, Harvey firm-training, CoCounsel precedent-drafting) personalizes
from a **firm's DMS** full of clean English Word docs. The gap Headnote owns: a **solo, vernacular,
district-court advocate** personalizing from ~3 scanned Kruti Dev drafts, where **format fidelity
*is* the product**, and where the profile gets sharper every time they draft. Nobody serves this.

Research reality check (arXiv 2509.14543): LLMs still struggle to imitate *implicit* writing style
from samples. So we do **not** rely on "feed drafts → model writes like you" magic. We split the
problem into what we can *enforce* deterministically vs what we can only *steer*.

---

## 2. The core principle: format is ENFORCED, voice is STEERED

| Aspect | Examples | How | Guarantee |
| --- | --- | --- | --- |
| **Format** | numbering (`यह कि` vs `1.` vs `That`), prayer wrapper, closer line, verification block, advocate signature block, cause-title idiom, font | deterministic post-render pass | **guaranteed**, on every path |
| **Voice** | register, parity-first ordering, paragraph rhythm, phrasing | prompt injection | **best-effort**, LLM paths only |

This is the honest contract and it drives everything below. The UI copy must reflect it: *"your
format, applied exactly; your voice, closely matched."*

---

## 3. The three generation paths (what we're personalizing)

`from_prompt.draft_from_prompt()` ([headnote/drafter/from_prompt.py:505](../headnote/drafter/from_prompt.py))
routes a prompt to one of three engines:

1. **Canonical / deterministic** — `_DETERMINISTIC` map → `mod.render_hi()`. Pure Python templates;
   no LLM writes prose. Persona fields substituted via `compose.py`. Format is fixed by the template.
   → Personalization here = persona fields + **format normalizer on the boilerplate**. Paragraph
   *structure* stays fixed (rigid templates). Voice N/A.
2. **Authored house-style** — `author.author_document()` → `_author_system()` builds the `HOUSE_STYLE`
   prompt ([author.py:795](../headnote/drafter/author.py)) → LLM → JSON → house renderer. **This is the
   prompt-based long-tail + all civil.** Currently hardcodes one house style.
   → Personalization = **prompt parameterization** (voice + format) **+ normalizer** (format).
3. **Mirror** — `author.mirror_document()` → `MIRROR_SYSTEM` with the reference *verbatim* → typed
   `mr-*` blocks ([author.py:1594](../headnote/drafter/author.py)). Highest fidelity, but needs a fresh
   upload every time.
   → **Key insight: the stored Draft DNA is a persistent, distilled version of this reference.** v2 can
   route prompt drafts through a DNA-as-synthetic-reference variant for max fidelity.

> **2026-07-06 update:** routing has since flipped — authored (path 2) is now PRIMARY for all types with
> the canonical template injected as a prescribed-format specimen; canonical (path 1) is the never-fail
> floor. DNA's mechanisms are unchanged, but the prompt-parameterization surface (path 2) now carries
> nearly all traffic, which makes Phase 3 higher-leverage than originally scoped.

### 3b. Format-source precedence (decided 2026-07-06 — Ayush)

When a draft is generated, the FORMAT comes from exactly one source, highest priority first:

1. **An explicitly attached reference (this draft)** — the advocate attaching a document is saying
   "match THIS one, this time". It ALWAYS beats the saved profile, even after Draft DNA is live.
   References legitimately differ per matter (a notice on the office letterhead, a bail application in
   court format) — the per-draft signal is the freshest statement of intent.
2. **The saved Draft DNA profile** — applies to every draft where no reference is attached.
3. **The house style / canonical prescribed format** — when neither exists.

FACTS are orthogonal and never move: the advocate's input (typed brief + case papers) is the only fact
source under every precedence level; reference and DNA are format-side only (§8 two-source rule).

Implementation note for Phase 3: in `draft_from_prompt`, the reference branch must be checked BEFORE
`load_style(user_id)` is applied to the mirror prompt — a loaded StyleProfile must not leak its tokens
into a reference-mirrored draft (at most, DNA may fill gaps the reference doesn't show, e.g. the
advocate's enrolment number, and only additively).

---

## 4. Architecture — two mechanisms + one chokepoint

### Mechanism 1 — Prompt parameterization (steers voice; paths 2 & 3)

Today `HOUSE_STYLE` *asserts* one style as law (`यह कि`, fixed closer, fixed prayer). Refactor the
style-specific lines into **slots**:

```
{para_prefix}   {closer}   {prayer_open}   {prayer_close}
{verification}  {party_labels}   {style_overlay}   {exemplars}
```

- Each slot **defaults to today's exact string** when the user has no DNA → existing behavior stays
  byte-identical (see §7 regression safety).
- `_author_system(doc_type, lang, style=None)` fills the slots from the loaded profile.
- `{style_overlay}` carries the Layer-2 prose; `{exemplars}` (2–3, capped for cost) go into the **user**
  prompt as "how this advocate wrote a similar ground."

We parameterize rather than append an override block, because bolting conflicting instructions onto a
long, assertive prompt confuses the model — slots that *replace* the default are unambiguous.

### Mechanism 2 — Deterministic format normalizer (guarantees format; all paths)

New pure-Python `apply_format(html, style)` runs on the rendered output of **every** path and rewrites
boilerplate to the advocate's tokens: paragraph-prefix swap, prayer opener/closer, appended
verification + advocate signature block, font class. Deterministic ⇒ guarantees format even when (a)
the LLM drifts or (b) the draft came from a rigid canonical template the prompt layer can't touch.
**This is what delivers "prompt-based output follows their exact format."**

### The chokepoint

- **New module `headnote/drafter/style_profile.py`** — `load_style(user_id) -> StyleProfile | None`.
- **Thread `user_id` through `draft_from_prompt()`** (it currently takes none) — the only routing change.
  Load once, hand to the firing path + to the normalizer.

Total surface area: 1 new module, 1 new column, 1 threaded param, 1 parameterized prompt, 1 post-pass.
Everything else is reuse.

---

## 5. Data model

Add one column to `public.user_profiles` (alongside the existing 5 persona columns in
[lawyer_profile.py:45](../headnote/api/lawyer_profile.py)):

```
draft_style  jsonb   -- the whole StyleProfile; null until the advocate sets it up
```

One nested column, not N discrete ones — the shape is variable/nested (exemplars list, directive list).

```jsonc
StyleProfile = {
  "format": {
    "para_prefix": "यह कि",
    "closer": "यह कि, अन्य तर्क वक्त बहस …",
    "prayer_open": "अतः श्रीमान न्यायालय से प्रार्थना है कि",
    "prayer_close": "… करने की कृपा करें।",
    "verification": "<their standard सत्यापन>",
    "party_labels": { "applicant": "आवेदक", "respondent": "अनावेदक" },
    "font": "kruti_dev" | "devanagari" | "serif",
    "cause_title": { "sessions": "…", "magistrate": "…" },
    "advocate_block": ["Adv. …", "enrol …", "bar …", "chamber …"]
  },
  "style_prose": "Formal legal Hindi; parity-first in bail; short single-issue paras; …",
  "directives": [ {"key": "framing", "value": "parity_first"}, … ],
  "exemplars": [ {"doc_type": "bail", "kind": "ground", "text": "यह कि आवेदक …"} ],
  "source_meta": { "n_drafts": 3, "extracted_at": "…", "confidence": {…} }
}
```

Read/write via a small `draft_style` router (or extend `lawyer_profile.py`): GET returns it for the
confirm/edit UI; PATCH writes the edited profile back (confirm + light-edit model).

---

## 6. Extraction pipeline (Profile section)

1. Upload 2–3 drafts via existing `/from-document?role=reference` OCR.
2. `extract_reference_skeleton()` (exists) for structure.
3. **New `analyze_style(texts) -> StyleProfile`:**
   - **Layer 1 (format)** — regex/heuristic for font + numbering (reliable) + LLM for cause-title,
     prayer, verification, party labels.
   - **Layer 2 (prose)** — "style analyst" LLM pass → the editable description.
   - **Layer 3 (exemplars)** — pull representative grounds/paras, deduped.
4. Aggregate across the uploads (most-common court, dedupe exemplars, keep confidence per field).
5. **Extract-then-discard** — OCR text stays in memory; persist only the `StyleProfile`. No original
   files stored (lowest PII risk).
6. Reveal the 3-layer card → advocate confirms / light-edits → save. (Cold start: pick an archetype.)

Cost: extraction is one-time per upload → can use a stronger model (R1). Per-draft overlay is
~300–500 extra prompt tokens → negligible; drafting stays on DeepSeek V3 per the cost line.

---

## 7. Regression safety for the HOUSE_STYLE refactor  ⚠️ load-bearing

`HOUSE_STYLE` sits under *every* authored draft. The refactor must not shift output for the ~thousands
of users with no DNA. Plan:

1. **Defaults are the current literals.** Every new slot defaults to the exact string it replaced.
   With `style=None`, the assembled prompt must be **character-for-character identical** to today's.
2. **Golden-master assert.** A unit test builds `_author_system(dt, lang)` for every `doc_type` × lang
   and asserts equality against a snapshot of today's prompt. The refactor is only "done" when this
   passes with zero diff.
3. **Before/after eval on sample matters.** Run a fixed set of representative prompts (bail, discharge,
   a civil suit, a long-tail criminal) through `author_document()` on `main` vs the branch with
   `style=None`; diff the rendered HTML. Expect **no change**. (Reuse the eval harness in
   `scripts/eval_drafter_ab.py`.)
4. **Feature-gated.** Personalization only engages when `load_style(user_id)` returns non-null; the
   `None` path is the untouched status quo. Ship dark, enable per-account.
5. **A separate before/after eval WITH a sample StyleProfile** to sanity-check that the personalized
   output is coherent (not just different) — reviewed by Vishnu ji.

---

## 8. Zero-fabrication interplay

DNA/exemplars are **format/framing samples**, so they live on the *reference* side of the two-source
rule — **never a fact source**. `render_mirrored()` already grounds facts against `source=matter`, not
the reference ([author.py:1612](../headnote/drafter/author.py)). Concretely: style/exemplars fill the
style slots; `matter` remains the sole fact input to the grounding guard. No new guard needed — DNA
slots onto the existing "format" side.

---

## 9. Phased build

- **Phase 1 — capture & extract.** `analyze_style()` + `draft_style` column + `style_profile.py` +
  extraction endpoint (reuse OCR path). Extract-then-discard.
- **Phase 2 — reveal & confirm UI (in Profile).** The 3-layer card, confirm + light-edit, save.
  *(Phases 1–2 together are the demo.)*
- **Phase 3 — apply at draft time.** Parameterize `HOUSE_STYLE` (with §7 safety), `apply_format()`
  normalizer, thread `user_id` through `draft_from_prompt()`, exemplar injection.
- **Phase 4 — continuous learning.** Capture `/refine` + hand-edit diffs → sharpen the profile.
- **v2 fidelity** — route prompt drafts through DNA-as-synthetic-reference (path 3) for max format
  fidelity per doc_type.

---

## 10. Known limitations (eyes-open)

- **Canonical templates are rigid** — normalizer fixes boilerplate, not paragraph structure. Full
  canonical personalization is a later effort.
- **Voice is best-effort; format is guaranteed** — reflect in UI copy.
- **Cold start / OCR** — needs 2–3 drafts; Kruti Dev OCR fidelity is the real extraction risk.
- **One profile per advocate** — no per-bench / per-court-type style variants in v1 (a natural v2).

---

## 11. Open questions

- Per-doc-type format overrides, or one profile across all types? (v1: one profile.)
- Do we let the advocate keep multiple named styles (e.g. "my HC style" vs "my district style")? (v2.)
- Continuous-learning threshold — how many confirming edits before we auto-update a directive?
