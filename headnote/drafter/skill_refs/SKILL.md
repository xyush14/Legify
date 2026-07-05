---
name: headnote-legal-drafting
description: >
  Author or improve court-ready Indian litigation draft TEMPLATES for Headnote —
  bail, anticipatory bail, discharge, revision, appeal, maintenance, domestic
  violence, §94 production, vakalatnama, reply/जवाब, etc. Use this skill whenever
  drafting, editing, reviewing, or reasoning about a legal application template,
  its grounds (the "यह कि …" arguments), the legal principles/tests/sections it
  must satisfy, the leading judgments behind it, or its court formatting. It
  holds the per-type drafting specs, the reviewed grounds libraries, the
  BNSS↔CrPC section maps, candidate leading judgments, and the Kruti Dev court
  format rules. ALWAYS consult this skill before authoring or modifying any
  Headnote draft template or its grounds — do not draft Indian legal applications
  from general knowledge alone.
---

# Headnote legal drafting

This skill is the **knowledge layer** of the Headnote drafting engine (see
`docs/DRAFTING_ARCHITECTURE.md`). It exists for the **offline authoring step**:
Claude uses it to draft and improve canonical templates, which the advocate
(Vishnu ji) then reviews. It is NOT used at runtime — runtime only fills the
reviewed template deterministically.

## The non-negotiable rules

1. **Format comes from real filings, not from you.** The skeleton, spacing, and
   Kruti Dev formatting come from Vishnu ji's actual filed `.docx` (the Template
   layer). You supply the *grounds and legal substance*, not the layout.
2. **Never fabricate case law.** A judgment may be written into a template only
   if it is `verified: true` with a real Indian Kanoon / SCC URL and Vishnu ji
   has confirmed it is apposite. Unverified citations live in the "cite at
   hearing" list, flagged — never in the document body. See `references/*` —
   every citation here is a CANDIDATE to verify, not a confirmed pinpoint.
3. **Grounds are genericised.** Never carry a real client's name, police station,
   place, or dates into a template. Case-specifics are placeholders (` ____ `)
   or fields. Reusable legal arguments are the substance.
4. **Sections current.** Lead with BNSS, keep CrPC in brackets for pending
   matters — e.g. `धारा 483 बी.एन.एस.एस. (439 दं.प्र.सं.)`.
5. **Advocate review is the gate.** Everything you author is a *proposal* for
   Vishnu ji to approve, edit, or reject. Mark new grounds `reviewed: false`.

## How to author a canonical template (the method)

1. Read the doc type's spec in the relevant reference file (start: `references/bail.md`).
2. Take the **structure** and the **court format** as fixed (from the spec +
   `references/court-formats.md`).
3. Assemble the **grounds** from the grounds library: include all `always`
   grounds in order; include `conditional` grounds whose tag matches the matter
   (e.g. `applicant_is_woman`, `successive_bail`, `delay_in_trial`). Leave the
   case-specific ground (usually ground 1) as placeholders.
4. Map **sections** to BNSS (+CrPC).
5. Compile the **cite-at-hearing list** from `citations` — flagged for verification.
6. Output a proposal: structure + grounds (numbered, court Hindi) + sections +
   citation list, each item tagged `source` and `reviewed: false` where new.
7. Hand to Vishnu ji for review. After approval, the grounds get baked into the
   template (the Template layer / `build_<type>.py`).

## What this skill contains

- `references/taxonomy.md` — the full application taxonomy (category → type) and
  which are built / planned.
- `references/court-formats.md` — Kruti Dev, page geometry, cause-title per court.
- `references/legal-frameworks.md` — **the reasoning layer**: controlling tests per
  type (bail triple-test + Antil categories + default bail + §479; maintenance Rajnesh;
  appeal panchsheel; discharge grave-suspicion), the **research-verified** judgment ledger
  (real SCC pinpoints, `verified:false` for body until Vishnu confirms apposite), the full
  **BNSS↔CrPC section map + the §482/§528, §173/§193, §438 inversions** an LLM gets wrong,
  and the "best drafter" thesis. CONSULT THIS to get the grounds & sections legally right.
- `references/application-frameworks.md` — **the body STRUCTURE layer**: the
  mirror-first method (Vishnu's filings → court-rule validation → legal correctness);
  per-court scaffolding (light subordinate-court vs the MP HC Rules 2008 Ch. X heavy
  petition with index/synopsis/annexures/affidavit); the **per-type fixed para skeleton**
  (which para is facts, which is grounds) for every type; the **SC-mandated bail
  disclosure block on affidavit** (Zeba Khan 2026 INSC 144); and the procedural-
  completeness checklist (the 12 gaps that get a draft bounced). CONSULT THIS for *how
  the application is laid out below the header.*
- `references/bail.md` — **bail family** (regular §483/439, magistrate §480/437,
  anticipatory §482/438): drafting specs, the reviewed grounds library with
  conditional tags, legal tests, candidate leading judgments, OCR mapping.
- (Phase 2+: `discharge.md`, `revision.md`, `appeal.md`, `family.md`,
  `procedural.md` — added one category at a time, each advocate-reviewed.)

Scope today (Phase 1): **bail family only**. Other categories are stubs in the
taxonomy and get their own reference file as they are authored and reviewed.
