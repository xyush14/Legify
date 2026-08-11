# AGENTS.md — read this first, then read CLAUDE.md in full

This file exists so that any coding agent — Codex, Cursor, Copilot, Gemini CLI, Claude Code,
or a human on their first day — lands on the same brief. It is a pointer, not the brief.

## Do this before anything else

**Read [`CLAUDE.md`](CLAUDE.md) in this repository, in full.** It is long and dense on purpose.
Its `CURRENT STATE` section is the authoritative anchor and **outranks any older note, any
comment in the code, and any impression you form by reading files.**

Then, if you have filesystem access, read `~/Documents/Headnote-AI-Archive/memory/MEMORY.md` —
the index of everything learned across ~143 past sessions. See
[`docs/AI_CONTINUITY.md`](docs/AI_CONTINUITY.md) for what that archive is and how to search it.

## The one thing every model gets wrong

**Headnote is an AI junior advocate for Indian litigators — "the smartest junior in the chamber."
It is NOT a drafting tool.** Do not describe, position, build, or reason about it as "a drafter."

There is a lot of drafting code in this repo, and that volume is exactly why past sessions kept
collapsing Headnote into "a drafting tool." Drafting is the loudest room in the house, not the
house. Headnote does four things: **remember** (case memory, matter diary, hearing dates, the
consultation recorder), **manage** (matters, CNR resolution, daily brief, document vault),
**research** (verified Indian case law, statute maps), and **draft** (in the advocate's own
court format).

Most users are solo, vernacular, district-and-High-Court advocates who cannot afford or find a
good human junior at ₹15–30k/month. Headnote is that junior, in software, in their own language
and their own court's format.

## Non-negotiables

- **Zero fabrication.** Never invent case law, facts, dates, money, or names. This is a day-1
  promise to lawyers who file what we produce. It is enforced by deterministic guards in code,
  not by prompt wording — keep it that way.
- **Build for every advocate, not one.** The ground truth so far came from one senior advocate's
  filed drafts. Never default to Hindi, to Kruti Dev, to legal-size paper, or to Madhya Pradesh.
  Prove a change across several languages before calling it done.
- **Plain language.** The founder is non-technical. Lead with the decision. Keep code and jargon
  out of explanations unless asked for them.
- **Design before code** for anything a user sees. Propose it, confirm it, then build it.
- **The repo is PUBLIC** (`github.com/xyush14/Legify`). Check what you are about to stage. Client
  documents, contact lists, fundraise material and AI session transcripts must never be
  committed — a public commit cannot be un-published.

## Where things are

| | |
|---|---|
| The brief | `CLAUDE.md` |
| Continuity, backups, moving to another AI tool | `docs/AI_CONTINUITY.md` |
| Run it locally | `docs/ONBOARDING.md` |
| How it is built / shipped | `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md` |
| Deploy target | **Fly.io**, app `headnote`, region `bom`. Code comments saying "Railway" are stale. |
| Tests | `pytest tests/` — ~617 pass. 26 pre-existing failures in 4 files are stale model-name expectations, not regressions; compare against a stash before blaming your change. |
