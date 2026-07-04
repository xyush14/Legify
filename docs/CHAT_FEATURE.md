# Chat — "AI for lawyers" (build spec)

**Status:** specced 2026-06-28, not yet built. Owner: Ayush.

## What it is (and is NOT)

A **standalone, additive** conversational surface — a lawyer's chat, like opening Claude/ChatGPT but for Indian litigation. A lawyer can research, ask anything, learn about an Act, or just talk.

- It is an **addition**. It does **not** touch, wire into, or refactor any existing feature (Draft / Research / Matter / BNS↔IPC).
- It is a **conversation, not a control panel**. It does NOT dispatch into the drafter or other engines.
- When a task belongs to another feature (e.g. drafting), the chat **talks it through, maybe asks for a detail, then hands the lawyer a LINK** to that feature (`/draft/...`, etc.). Soft pointer, not integration.

### Positioning / naming
"**AI for lawyers**," NOT "GPT for lawyers." "GPT" is a liability word in this profession (hallucinated-citation reputation) and a commodity claim. The premium feeling = *the intelligence a lawyer wishes they had on staff* — brilliant, BNSS-current, and it **refuses to bluff**. The restraint IS the brand.

## Product map (Chat is one of 5 surfaces)
1. **Chat** — EXPLAIN ("what's §103 BNS?", "explain anticipatory bail under BNSS" → statute text + plain-language + leading judgment) + ASK (open legal reasoning, "client did X, what are the options?" → grounded answer + caveats). ← this doc
2. **Research** — as is
3. **Draft** — as is
4. **Matter** — CNR lookup → prefill, as is
5. **BNS↔IPC** — as is

## We do NOT train a model
Use DeepSeek (V3 fast / R1 deep) — already wired. "Better output" comes from layers around the model, not weights:
1. **Retrieval quality** (~60%) — the corpus is the moat (re-anchored IK + SC corpus + statute text + grounds libraries).
2. **System prompt + golden few-shot examples** (~20%) — embed Vishnu ji's gold-standard answers.
3. **Eval set** (~15%) — ~100–200 real lawyer Qs with known-correct answers; the real "training loop"; run on every prompt/corpus change.
4. **Fine-tune** (optional, last, via API) — tone/format only, never knowledge. Probably never needed.
Feedback flywheel: 👍/👎 + edits → good answers become few-shot examples, bad answers become eval cases.

## Build — reuse vs new
| Layer | Reuse | New |
|---|---|---|
| LLM | `call_claude_cached()` / `route_call()` (`headnote/llm/`) | `"chat"` task type + multi-turn history |
| Grounding | `statute_mappings.json`, `retrieve_for_situation()`, `KanoonClient`, `verify.py` | chat system prompt that grounds + refuses to bluff |
| API | `APIRouter` + `get_current_user` + `check_and_record` pattern | `headnote/api/chat.py` → `POST /api/chat/message` |
| Frontend | SPA shell, sidebar nav, `static/style.css` | a `chat` view (message thread) |
| Gating | `plans.py` + `check_and_record` | add a `"chat"` feature |

## Decisions (locked 2026-06-28)
- **Placement:** new **view in the SPA** (`data-view="chat"`), NOT a standalone page. Reuses auth/shell.
- **v1 grounding:** **prompt-grounded** (inject `statute_mappings.json` + no-bluff system prompt). Retrieval wiring is v1.5.

## Phasing
- **v1** (days): `headnote/api/chat.py` endpoint + multi-turn DeepSeek call + grounded no-bluff system prompt + statute-map injection + soft link-outs + SPA chat view + `"chat"` gating. Ship.
- **v1.5:** wire `retrieve_for_situation()` + `verify.py` guard so case-law answers cite real judgments with links.
- **v2:** streaming (none exists today — all sync JSON). SSE/`StreamingResponse` + EventSource for the "alive" feel.

## The one rule that makes it premium
Every answer either cites a real source it has, or says *"I don't have a verified source — confirm at hearing."* Never invents a citation. Same guard discipline as the drafter.
