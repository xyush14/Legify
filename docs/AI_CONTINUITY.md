# Continuity — keeping Headnote's AI sessions after Claude Code

**Written:** 2026-08-11, in the last Claude Code session for this project.
**Who this is for:** Ayush, and any AI assistant on any platform that picks this project up next.

This is the answer to three questions you asked, in order:

1. Where is every session saved on this machine, and how do I keep it?
2. If I log in to Claude Code with a **different account on this same Mac**, will these sessions still be there?
3. If I open this project in **Codex, Cursor, ChatGPT, Gemini** or anything else, how do I give it everything?

---

## 1. The short answers

**Q: Are my sessions saved locally?**
Yes. Every session you have ever had in this project is already on this Mac as a file. Nothing was in the cloud only. There are **143 sessions** for this project, **431 MB** of raw transcript.

**Q: If I log in with a new Claude ID on this same Mac, will I still see them?**
**Yes.** Your login and your history are stored in two completely separate places:

| Thing | Where it lives | Tied to your account? |
|---|---|---|
| Your login | macOS Keychain, item `Claude Code-credentials` | **Yes** |
| Your session history | `~/.claude/projects/<project-folder>/*.jsonl` | **No** — plain files on disk |

The history files contain no account id, no email, no user key. They are filed **by project folder path only**. So a different Claude account, signed in on this same macOS user, opens this same folder and sees the same list of past sessions. Same for a Pro → Max change, a re-login, or a subscription lapse.

**Three things WOULD lose them** — this is the real risk, not the account:

- **Renaming or moving the project folder.** The history key is the folder's absolute path, slugified. `~/Downloads/Legify-0bb187ba…` becomes `-Users-ayushshivhare-Downloads-Legify-0bb187ba…`. Rename the folder and Claude Code looks in a directory that does not exist, and reports zero past sessions — the files are still there, just unreachable. If you ever move it, move the history folder to match, or re-export first.
- **A different macOS user account, or a different Mac.** `~/.claude` is per-user. Nothing syncs it.
- **Deleting `~/.claude`,** or a disk wipe / new laptop with no Time Machine restore.

**Q: Can other tools read them?**
Not in their native form — `.jsonl` transcripts are Claude Code's own format. That is why they are now **also exported as plain Markdown**, which anything can read.

---

## 2. The archive — what was made, and where

```
~/Documents/Headnote-AI-Archive/
├── INDEX.md            143 sessions, newest first, one clickable row each
├── CLAUDE.md           copy of the project brief as of today
├── sessions/           143 Markdown files — the readable conversations (11 MB)
│   └── 2026-08-11--fix-home-and-draft-loading-performance--208d546b.md
├── memory/             88 memory files (MEMORY.md + every project_*/feedback_* note)
└── raw/
    ├── claude-projects-raw-20260811.tar.gz   245 MB — every original .jsonl
    └── claude-settings.json
```

Deliberately **outside** the repo. `github.com/xyush14/Legify` is public, and these transcripts contain whatever was on screen during a session: `.env` values, OCR of real charge-sheets, client and advocate emails. **Never commit the archive.**

Each Markdown session carries a header (session id, date range, git branch, Claude Code version, turn count), then the conversation: your prompts in full, Claude's answers in full, and every tool call as a one-line `→ Edit — path/to/file`. Claude's internal reasoning is dropped by default because it triples the size and rarely matters after the fact.

### Re-run the export any time

The exporter is committed with the project: [scripts/export_claude_sessions.py](../scripts/export_claude_sessions.py). It only ever **reads** `~/.claude`.

```bash
cd ~/Downloads/Legify-0bb187ba264e218517be944dbf64c433be6ae19d

python3 scripts/export_claude_sessions.py                 # this project
python3 scripts/export_claude_sessions.py --all-projects   # every project on this Mac
python3 scripts/export_claude_sessions.py --thinking       # include reasoning
python3 scripts/export_claude_sessions.py --out ~/Desktop/backup
```

Re-running is safe — it overwrites the same filenames and rebuilds `INDEX.md`.

### Restoring the raw transcripts

If `~/.claude` is ever lost and you want Claude Code's own history back (so `resume` works, not just reading):

```bash
tar -xzf ~/Documents/Headnote-AI-Archive/raw/claude-projects-raw-20260811.tar.gz -C ~/.claude
```

That restores `projects/`, `plans/`, `tasks/` and `settings.json`. It only works if the project folder still sits at the same absolute path.

### Get it off this Mac — do this, it is the one gap left

Right now the archive exists on exactly one disk, the same disk as the originals. One drive failure loses both. Pick one:

- **Simplest:** copy the whole `Headnote-AI-Archive` folder into iCloud Drive, Google Drive or Dropbox. It is 269 MB.
- **Best for AI use later:** a **private** git repo of just the archive — then any tool on any machine can clone it.

  ```bash
  cd ~/Documents/Headnote-AI-Archive
  printf 'raw/\n' > .gitignore          # skip the 245 MB tarball; too big for git
  git init && git add . && git commit -m "Headnote AI session archive"
  gh repo create headnote-ai-archive --private --source=. --push
  ```

  Keep it **private**. Everything in section 2's warning applies.
- **Also:** confirm Time Machine is on and includes `~/Documents` and `~/.claude`.

---

## 3. Searching your own history

The archive is plain text, so ordinary tools work. This is how you find "what did we decide about X".

```bash
cd ~/Documents/Headnote-AI-Archive

# every session that touched the eCourts wallet
grep -ril "INSUFFICIENT_CREDITS" sessions/

# with context
grep -ri -A5 -B5 "PG_CHILD_TABLES" sessions/ | less

# what did I say (not Claude) about drafting
grep -rn -A10 "🧑 Ayush" sessions/ | grep -i "drafting"

# sessions in a date range
ls sessions/ | grep "2026-08-"
```

Or open `INDEX.md` in any Markdown viewer and click through titles.

---

## 4. Continuing on another platform

Whatever the tool, the recipe is the same three steps.

**Step 1 — give it the brief.** [CLAUDE.md](../CLAUDE.md) at the repo root is the real handover document: what Headnote is, the hard rules, and a `CURRENT STATE` section that outranks everything else. [AGENTS.md](../AGENTS.md) is a short pointer to it, because that is the filename Codex, Cursor and most newer tools look for automatically.

**Step 2 — give it the memory.** `~/Documents/Headnote-AI-Archive/memory/` — start with `MEMORY.md`, the index; each line points at one file.

**Step 3 — give it the history only when needed.** 143 sessions will not fit in any context window. Do not paste them. Grep for the relevant one and paste that single file, or tell the tool the folder path and let it search.

### Tool by tool

**OpenAI Codex CLI** — reads `AGENTS.md` from the repo root automatically.
```bash
npm install -g @openai/codex
cd ~/Downloads/Legify-0bb187ba264e218517be944dbf64c433be6ae19d
codex
```
First message: *"Read AGENTS.md and CLAUDE.md in full before doing anything. Past session history is Markdown in ~/Documents/Headnote-AI-Archive/sessions — grep it rather than reading it all."*
Codex keeps its own history in `~/.codex/sessions/` — a different format again, so export from there too if you settle on it.

**Cursor / Windsurf / VS Code + Copilot** — open the folder; they pick up `AGENTS.md` (Cursor also reads `.cursorrules`). Add `~/Documents/Headnote-AI-Archive` as a second workspace folder to make the archive searchable in-editor.

**Gemini CLI** — reads `GEMINI.md`. Make one that just points at the real brief:
```bash
printf 'Read CLAUDE.md in this repository in full. It is the authoritative brief.\n' > GEMINI.md
```

**Claude on the web / Desktop chat (no Claude Code)** — no filesystem access. Upload `CLAUDE.md`, `memory/MEMORY.md`, and the two or three specific memory files that matter for the task. Still the cheapest way to keep the same brief.

**ChatGPT / any chat UI** — same as above. Upload `CLAUDE.md` first, ask it to confirm the positioning back to you before it starts. Headnote is an **AI junior advocate**, never "a drafting tool" — every model that has not read the brief gets this wrong, which is exactly why the brief exists.

**Claude Code again later** — nothing to do. Same Mac, same folder, any account: `resume` and the list is there.

---

## 5. Handing over the project itself

If a person or a new assistant is starting cold, read these in this order:

1. **[CLAUDE.md](../CLAUDE.md)** — positioning, hard rules, and `CURRENT STATE`. Long, dense, and worth every line. The `CURRENT STATE` section outranks any older note.
2. **[docs/ONBOARDING.md](ONBOARDING.md)** — how to run the app locally.
3. **[docs/ARCHITECTURE.md](ARCHITECTURE.md)** and **[docs/DEPLOYMENT.md](DEPLOYMENT.md)** — how it is built, how it ships. Note: comments in code still say "Railway"; the real deploy target is **Fly.io**, app `headnote`, region `bom`.
4. `~/Documents/Headnote-AI-Archive/memory/MEMORY.md` — the index of everything learned, one line per note.

### Open items as of today, most urgent first

These are live, none are code problems that another session fixes — they need your hands or your money.

1. **The eCourts vendor wallet has ₹0.50 in it.** A search costs ₹0.60. So add-by-CNR, add-by-case-number and the nightly 18:00 court sweep all fail in production right now. Top up the eCourtsIndia account.
2. **`GEMINI_API_KEY` may not be set as a Fly secret.** It is set locally. OCR now uses Gemini as its primary; without that secret in production, OCR silently degrades to Groq's free tier at roughly one page a minute, and misreads Devanagari legal abbreviations. Check with `fly secrets list`. `flyctl` is not installed on this Mac — install it: `brew install flyctl`.
3. **No uptime monitoring.** headnote.in has been down twice, and both times you found out by trying to open it yourself — once for two days. A free external monitor (UptimeRobot, Better Stack) pinging `https://headnote.in/api/live` every five minutes is the single highest-value thing left on this list, and it takes ten minutes.
4. **`static/auth.js` and `static/analytics.js` still hardcode four founder email addresses**, and they are served to every visitor at `headnote.in/static/auth.js`. The access lists in `config.py` were already moved to Fly secrets; these two files were not. The fix is to read `/api/me` → `subscription.plan === "founder"` instead.
5. **Git history still contains real user email addresses**, and the repo is public. The only real remedies are making the repo private or accepting it. Your call.
6. **12 commits on `seo/geo-visibility` have never been pushed.** They exist only on this Mac. Same single-disk risk as the archive.

---

## 6. Quick reference

| What | Where |
|---|---|
| Raw session transcripts | `~/.claude/projects/-Users-ayushshivhare-Downloads-Legify-0bb187…/*.jsonl` |
| Readable export | `~/Documents/Headnote-AI-Archive/sessions/` |
| Session index | `~/Documents/Headnote-AI-Archive/INDEX.md` |
| Project memory | `~/Documents/Headnote-AI-Archive/memory/` (live copy under `~/.claude/projects/…/memory/`) |
| Full backup tarball | `~/Documents/Headnote-AI-Archive/raw/claude-projects-raw-20260811.tar.gz` |
| Claude login | macOS Keychain → `Claude Code-credentials` |
| Claude settings | `~/.claude/settings.json` |
| The brief every AI must read | `CLAUDE.md` (repo root), pointed at by `AGENTS.md` |
| Exporter script | `scripts/export_claude_sessions.py` |

**If you take one thing from this document:** the sessions are safe from a re-login and safe from a new account, but they are not safe from a lost laptop. Copy `~/Documents/Headnote-AI-Archive` somewhere that is not this disk.
