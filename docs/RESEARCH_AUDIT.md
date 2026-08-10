# Research flow — QA + product audit (2026-08-05)

Scope: `/research` (static/research.html), its backend (`headnote/api/chat.py`,
`app.py` situation endpoints + `/api/translate`, `saved_caselaw.py`,
`judgment_chat.py`, `drafter/api.py::transcribe`, `llm/prompts.py`), and the
integration points (home.html folder link, statute-palette.js, voice.js).
Method: three independent code reviews (frontend state, backend contracts,
user journeys) cross-checked, with the top races reproduced live in the
browser. **No code was changed.** Fixes suggested are minimal and preserve the
existing architecture.

Severity: **P0** = money/data/trust, fix before ship · **P1** = a lawyer gets
stuck or the flow breaks · **P2** = polish, correctness hardening.

---

## P0 — money, data loss, or a false "verified"

1. **Broken stream = double quota charge + double LLM spend.**
   `app.py:3042–3063` — on a mid-stream client/proxy disconnect the generator's
   `finally` still charges `deep_search` (the `errored` flag is only set by
   worker-reported errors), and the frontend then falls back to classic
   `/api/situation`, which charges again. The stream is silent for the whole
   10–30 s LLM phase, so idle-timeout kills are realistic on mobile.
   *Fix:* mark `delivered=True` only after yielding a `result` event; on
   `GeneratorExit`/exceptions call `_cm.__exit__` with the exception so no
   charge happens. Also give `bus.get()` (3045) a timeout, and consider an
   idempotency key so the classic fallback of the same query isn't re-charged.

2. **Saved-caselaw writes fail silently — `ok:true` on failure.**
   `entitlements/_supabase.py:71–73` swallows `httpx.HTTPError` and returns
   `[]`, so `saved_caselaw.py` save/PATCH/DELETE (110, 145, 159) report success
   when nothing was written. A lawyer "saves" an authority and it's gone.
   *Fix:* in saved_caselaw, treat an empty upsert result as failure → 502 (or
   add a `raise_on_error` variant in `_supabase`).

3. **Judgment-chat verification fails OPEN.**
   `judgment_chat.py:141–143` — when the parsed judgment has no numbered
   paragraphs, `anchors_missing` is forced empty and the answer can badge
   `clean:true` — a green badge on anchors nobody checked.
   *Fix:* if `claimed` is non-empty and `valid_nums` is empty → `clean:false`
   with a `no_numbered_paragraphs` note.

4. **Missing verify event renders no badge at all** (reads as clean).
   `research.html:1618` — badge only renders `if(verify)`; the drawer's hint
   promises every answer is checked. *Fix:* default to the amber "⚠ not checked
   against the judgment" chip when the stream ends without a verify report.

5. **One real script-injection hole.**
   `research.html:1769` — `onclick="stSet('${esc(s.query)}')"`: `esc()` doesn't
   escape single quotes inside a JS-string context; a crafted
   `/api/mapping/popular` value could execute JS. *Fix:* render with
   `data-q` + addEventListener like every other list on the page.

6. **Research has no working LLM fallback** (known, re-confirmed).
   Live test: `/api/situation/stream` retrieves 6 real IK shells, then 413s on
   the Groq free tier (16k-token analysis prompt > 12k TPM). If DeepSeek is
   down, research is down. *Fix:* slim-retry prompt for the fallback engine
   (same medicine as the drafter's 2026-07-06 fix).

## P1 — a lawyer gets stuck / the flow breaks

7. **No in-flight guards on any send path** *(browser-verified)*.
   `findGo` (⌘Enter at 1991 and the exclusion-bar button both bypass the
   disabled button), `askGo` (Enter at 1993), `sendJdrawer` (1996, `#jd-go`
   never disabled). Concurrent streams interleave into the same containers,
   both mutate `LAST`/`askThread`, and error paths `pop()` the wrong message.
   *Fix:* one busy-flag pattern on all three (check at function top, clear in
   `finally`).

8. **New chat / persona switch / open-recent mid-stream corrupts state**
   *(browser-verified)*. `research.html:929–933, 800–801, 966` — the streaming
   answer writes into detached DOM (visually swallowed), the completed turn is
   filed under the NEW thread id/persona with mismatched `messages`.
   *Fix:* while a turn is streaming, refuse newChat/setPersona/openRecent (or
   abort the stream first); in `runChatTurn` capture the turn's `TURNS`/
   `THREAD_ID` at entry.

9. **FCTX (carried research context) leaks into unrelated threads.**
   `research.html:772, 929, 1155, 1636` — set by Continue-in-Chamber/Compare,
   only consumed on the next first-send; `newChat()`/`openRecent()` don't clear
   it, and example tiles can send it glued to an unrelated question. The user
   never sees the prefix. *Fix:* `FCTX=''` in `newChat()` and `openRecent()`;
   while FCTX is pending, don't re-render example tiles.

10. **Shortlist tray unreachable in two major states.**
    (a) Mobile/small screens: `#mside` hides <1180px — ＋Shortlist buttons still
    collect items but Save-all/Compare/Copy don't exist on a phone.
    (b) Matter attached: the rail shows the matter file instead; `toggleSL`
    only repaints when `!SEED`. The flagship flow (attach matter → search →
    shortlist) hides the tray. *Fix:* (a) floating "Shortlist · N" chip opening
    the actions in the existing sheet; (b) compact shortlist strip under the
    matter file when `SL.length`.

11. **Saved items can't be opened.** `research.html:1268–1287` — Library rows
    (cases, statute mappings, saved Chamber answers) have file/delete/note but
    no way to VIEW content; a saved answer is write-only. *Fix:* title click →
    cases open `kanoon_url`; answers/statutes expand inline (`mdlite` of the
    stored content).

12. **Zero-matters picker is a dead end** *(browser-verified)*.
    "No matter matches." with no create path — the first-time user's first ⊕
    click hits a wall. *Fix:* empty state → "No matters yet — create one on
    Home →" (keep "Library only" for save mode).

13. **Foreign/invalid `?matter=` attaches nothing, silently.**
    `research.html:1027` — no pill, no toast; the lawyer from Home believes
    every search is grounded. *Fix:* toast when the URL/click seed resolves to
    null. Related: results searched WITH a matter carry no "grounded in X"
    marker in the header (add to `rhead`).

14. **Load failures masquerade as empty states.**
    `loadSaved` (1230) → "Nothing saved yet" on network error;
    `loadMatters` (1014) caches `[]` forever after one failure (never retries).
    *Fix:* error-state with Retry for the Library; reset `MATTERS=null` on
    error.

15. **Bulk save partial failure loses the failed items.**
    `research.html:1136` — any success clears the whole shortlist including
    failed POSTs. *Fix:* keep failures in `SL`.

16. **Attachment fragility.** No client size pre-check (a 60 MB scan uploads
    then 400s); 401 leaves a stuck "reading…" chip (867); on a failed/402 turn
    the folded OCR text is destroyed with `messages.pop()` — re-upload
    required. *Fix:* pre-check ~15 MB; remove chip before `gate()`; restore
    `askAtts`/input text on error.

17. **Drawer bookkeeping.** 402 returns without `st.messages.pop()` (1612) →
    dangling consecutive user turns (silently downgrades deepseek-reasoner to
    the weakest fallback via the 400→fallback path); opening judgment B while A
    streams detaches A's answer into a thread the user never saw (1560–1583).
    *Fix:* pop on 402; one-drawer-stream-at-a-time guard.

## P2 — hardening and polish

18. **Final unterminated stream line is dropped.** `readNdjson`/`readSSE`
    discard leftover `buf` at EOF — a server that ends without a trailing
    newline loses the `result` event → "search ended without a result" after a
    successful search. *Fix:* flush-parse remaining buf after the loop.
19. **Stale exclusions on restored searches.** `openRecent` (986) doesn't reset
    `EXCL`; unrelated restored results show pre-dimmed entries. *Fix:* reset in
    the search branch.
20. **3-minute search has no Stop and a jargon timeout.** Raw AbortError text
    surfaces (1506). *Fix:* friendly timeout copy + a Stop control wired to the
    existing AbortController.
21. **402s are dead ends** — no plans/upgrade link anywhere `quotaMsg` renders.
22. **"0 verified" renders green** in the results header (252/1529) — wrong
    signal; make zero-verified amber.
23. **Session-storage identity flip.** `uid()` falls to `'anon'` if the token
    expires mid-session → Recent/shortlist "vanish" under a different key
    (901–905); quota-full `writeStore` fails silently while full case_json
    arrays are persisted (907, 921). *Fix:* cache first real uid; prune+retry
    then toast on quota.
24. **Meters charge on failed chat/judgment streams.** `chat.py:495–504`,
    `judgment_chat.py:228–231` — increment even when zero deltas were
    delivered. *Fix:* skip increment when no delta (keep event logging).
25. **Matter context latency.** `chat.py:317–422` — 5 sequential store calls
    per turn before the SSE opens (~0.5–1.5 s typical, ~15 s worst on
    timeouts). *Fix:* cache the block per (user, matter) for a few minutes.
26. **Prompt schema contradiction.** `prompts.py:355–359` hardcodes
    `practitioner_notes: null` while the practitioner style block (the V2
    default) instructs populating it — `quotable_phrase`/`grounds` placement is
    model's-choice. *Fix:* schema says "populate exactly one per style;
    statute_index required in both".
27. **Chamber niceties.** Persona-switch parks the thread with no toast (801);
    failed turn wipes the typed question with no retry (1652); first-turn 402
    leaves the hero hidden + stale failed turn (1653/1720).
28. **Library niceties.** Instant delete with no undo (1291); failed note save
    discards the typed note (1314).
29. **Navigation.** Refresh mid-thread boots to Find law — the open thread
    isn't reopened (persist `THREAD_ID` as open); back/forward doesn't close
    open overlays (drawer/palette/compare) on popstate.
30. **Statute surfaces.** Three doors behave differently (tab saves, palette
    only copies); debounced lookups have no stale-response guard (1763,
    1856) — fast typers can get older results painted last, and palette Enter
    can copy the wrong section. *Fix:* sequence-number the requests; add
    "open in Statute tab" from the palette.
31. **Transcribe metering & semantics.** Each utterance burns a full `draft`
    credit (1274) — 20 mic taps = 20 drafts (re-decide the meter);
    empty Whisper text returns charged `ok:true, text:""` (1308); `auto`
    reports `language:"hi"` regardless of what was spoken; explicit non-Hindi
    hints never reach Sarvam.
32. **saved_caselaw hygiene.** `matter_id` ownership isn't validated (foreign
    id = orphaned row, malformed id = fake success via #2); re-saving a card
    without a query nulls the stored `source_query`.
33. **Translate gate.** 402 copy says "Hindi PDF export" for the card toggle;
    endpoint is check-only — unmetered LLM calls (≤5/case, ×2 on retry).
34. **Recent/threads edge.** Deleting the OPEN thread resurrects it on the
    next turn (956); restoring a matterless thread keeps the currently
    attached SEED riding its turns (964).
35. **Sign-in gate loses the return path.** `href="/app"` drops
    `?matter=`/tab (611) — add a `next` param.
36. **First-run teaching.** Find law has no example chips (Chamber does);
    empty-state parity is cheap.
37. **Accessibility.** Overlays lack `role="dialog"`/focus trap/focus return;
    Recent ✕ is a span inside a button (invalid + not keyboard-operable);
    `.rtabs`/`.pchips` declare tablist without tab semantics; `#v-q`/`#palq`
    miss the Devanagari font stack; no `prefers-reduced-motion` guard.

## Verified solid (checked, no action)

- Zero-fabrication rendering: verified badge strictly gated; every model
  string escaped at render (one exception: #5); quotes never translated.
- Cross-user isolation on matter context, folder, saved list (all
  user_id-scoped).
- `_seed_situation_from_matter` clamp math, jurisdiction fill, no-500 paths.
- PATCH `model_fields_set` semantics (pydantic ≥2.6); upsert does NOT clobber
  matter filing/notes on re-save.
- `/api/translate` contract matches the frontend payload/response.
- `journal_headnote` object tolerated by all parsers (null or object).
- Abort timer cleanup in findGo; malformed stream lines skipped; store shape
  migration for `.shortlist`; demo timers on hidden tabs; Safari audio/mp4.

## Suggested fix order (when the fix session opens)

1. P0 #1–#6 (one day: metering guard, raise-on-error saves, fail-closed
   verify + default amber badge, stSet rebind, fallback slim-retry).
2. P1 #7–#9 (one busy-flag pattern + FCTX clears — kills the whole race
   family).
3. P1 #10–#17 (shortlist reachability, openable saved items, dead ends,
   attachment fragility).
4. P2 in listed order; #18–#24 first (stream flush, meters, uid cache).
