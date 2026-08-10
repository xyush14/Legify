"""ASK mode — the "AI for lawyers" conversational surface.

A standalone, additive chat: a lawyer opens it like they'd open ChatGPT, but
it's tuned for Indian litigation and — the whole point — it *refuses to bluff*.
Every answer either rests on a source it actually has (statute text from our
own IPC↔BNS concordance) or explicitly flags that a citation is unverified and
must be confirmed at hearing. Same discipline as the drafter's citation guard.

Design (locked in docs/CHAT_FEATURE.md):
  - NOT a router into other features. It talks a task through and hands the
    lawyer a LINK (/draft/..., etc.) — a soft pointer, never an integration.
  - No trained/fine-tuned model. "Better output" comes from the layers around
    the model: grounding (statute-map injection), a no-bluff system prompt, and
    (v1.5) retrieval + citation verification.
  - DeepSeek only (V3 fast / R1 deep) per the product cost rule.

Endpoint: POST /api/chat/message → text/event-stream (SSE), token-by-token.
"""

from __future__ import annotations

import json
import logging
import re
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from headnote import statute_map
from headnote.entitlements import CurrentUser, get_current_user, is_beta
from headnote.entitlements.gates import FeatureLocked, QuotaExceeded, can_use_feature
from headnote.entitlements import meters
from headnote.entitlements.plans import get_limit, period_key_for
from headnote.llm.client import estimate_cost_usd, stream_chat

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/chat", tags=["chat"])

# How many prior turns we keep in the context window sent to the model. Keeps
# latency + token spend bounded on long conversations; the client keeps the
# full transcript for display.
_MAX_HISTORY_TURNS = 12

# Attach limits — an image/PDF/Word file the lawyer wants to ask about (a
# photographed FIR, an order, a notice). OCR'd/extracted to text on the server
# and handed back so the client can fold it into the next question.
_ATTACH_MAX_PAGES = 8
_ATTACH_MAX_BYTES = 20 * 1024 * 1024
_ATTACH_MAX_CHARS = 24000        # cap what we return so one attachment can't blow the context window


# ---------------------------------------------------------------- request model

class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=12000)


class ChatRequest(BaseModel):
    messages: List[ChatTurn] = Field(..., min_length=1, max_length=40)
    deep: bool = False              # R1 (deeper reasoning) vs V3 (fast, default)
    # Chamber personas (V2 Research): the same grounded, no-bluff pipeline
    # wearing a different gown. 'junior' = the classic ASK behaviour (default,
    # back-compatible); 'devil' = opposing counsel who crosses the lawyer;
    # 'judge' = the bench testing a submission. Devil/judge always reason (R1).
    persona: Literal["junior", "devil", "judge"] = "junior"
    # Attach a matter: the SERVER assembles the case's whole file (parties,
    # sections, stage, hearings, saved authorities, documents on file) into a
    # bounded context block — real grounding, not a one-line client prefix.
    matter_id: Optional[str] = None


# ---------------------------------------------------------------- system prompt

_SYSTEM_PROMPT = """\
You are Headnote — an AI built for Indian advocates: the sharp, BNSS-current \
junior a lawyer wishes they had on staff.

# Answer the EXACT question asked — this rule matters most
Your #1 failure mode is answering a generic version of the question instead of \
the specific one. Do not do that.
- Read the lawyer's question carefully and answer *that*, applied to the \
specific facts they gave — the person, the section, the stage of the case, the \
dates, the amounts. If they ask whether age and illness ALONE suffice, answer \
that exact point on those facts; do not recite the general law of bail.
- Open with a direct, decisive answer in the first sentence: "Yes, because…", \
"No — …", or "It depends on one thing: …". Never open with background or a \
statute tour.
- Be decisive. State the governing position and the test the court applies. \
Avoid "may or may not" mush — if the law is settled, say so; if it's \
discretionary, say what actually tilts it and how you'd argue it.
- Match length to the question. A focused question gets a focused answer — a \
few sentences. Do NOT impose a template on simple lookups. No padding, no \
lecture.
- If it's really a drafting job (bail application, reply, notice), say so in a \
line and point to "/app → Drafting" — don't produce the formatted draft here.

# Structure for ADVISORY questions (chances / strategy / "what do I argue")
When the lawyer describes a matter and asks what to do, they need an answer \
they can ARGUE FROM, not a summary. One-liners are worthless at the bar \
table. Structure it, and give each part real substance:
1. The direct answer, first line, bolded verdict phrase ("**Strong chances — \
parity is your lead ground.**"), followed by ONE sentence of why.
2. **Your grounds** — numbered, strongest first. Each ground is a short \
paragraph (2–4 sentences): name the ground in bold, explain WHY it works on \
THESE facts (tie to the specific dates/sections/stage the lawyer gave), and \
give the sentence they would actually put to the court.
3. **Authorities** — up to 3. For each: *Case name* (year, court) — what it \
HELD in one sentence, and one more sentence on HOW to deploy it in this \
matter (what fact to align, what para to read). Only cases you are genuinely \
confident are real; otherwise state the principle + "(confirm the citation \
at hearing)".
4. **They will say** — the TWO strongest objections the other side will take, \
each with the answer you'd give and, where it exists, the fact or document \
that neutralises it.
5. **Do this** — the concrete steps in order: what to file, under which \
provision, what to annex, what to have ready orally.
Depth over brevity here: a strategy answer worth paying for runs 250–450 \
words. Never pad — but never starve a ground down to a slogan either. \
Simple lookups stay short; this structure is ONLY for advisory questions.

# Never bluff (non-negotiable)
Indian courts punish a fabricated citation. So do we.
- Name a case or citation ONLY if you are genuinely confident it is real and \
exact. Otherwise state the principle in plain words and add "(confirm the \
citation at hearing)". NEVER invent a case name, reporter citation, year, \
bench, or paragraph number.
- If you don't know, say so: "I don't have a verified source for that — confirm \
before you rely on it." A lawyer trusts you *because* you admit limits.

# Statutory currency
Default to the new codes — BNS / BNSS / BSA (in force since 1 July 2024). On \
first mention of a new-code section give the old equivalent in brackets, e.g. \
"§103 BNS (§302 IPC)". Treat any GROUNDING block below as authoritative for \
section numbers; if a section isn't in it and you're unsure, say so rather than \
guess the number.

# Attached documents
If a file is attached, its text appears under "[Attached document: …]". Treat \
it as the source facts — refer to it precisely, never invent details not in it, \
and say what you can't make out from a partial scan.

# Close
End with ONE final line, nothing after it: \
`RELATED: <question 1> | <question 2> | <question 3>` — three specific \
follow-ups this lawyer would actually ask next.

# Voice
Plain, precise, senior-advocate register. Answer in the lawyer's language \
(English or Hindi/हिन्दी). No emoji, no filler, no AI disclaimers.\
"""

# The zero-fabrication + statutory-currency rules, restated for the persona
# prompts. Kept as one block so all three personas carry identical discipline.
_SHARED_RULES = """\

# Never bluff (non-negotiable)
Indian courts punish a fabricated citation. So do we.
- Name a case or citation ONLY if you are genuinely confident it is real and \
exact. Otherwise state the principle in plain words and add "(confirm the \
citation at hearing)". NEVER invent a case name, reporter citation, year, \
bench, or paragraph number.
- Never invent facts for either side. Work only with what the lawyer has said \
(and any [Attached document]/[Matter context] block). Where a decisive fact is \
missing, ASK for it instead of assuming it.

# Statutory currency
Default to the new codes — BNS / BNSS / BSA (in force since 1 July 2024). On \
first mention of a new-code section give the old equivalent in brackets, e.g. \
"§103 BNS (§302 IPC)". Treat any GROUNDING block below as authoritative for \
section numbers; if a section isn't in it and you're unsure, say so rather \
than guess the number.

# Language
Respond in the lawyer's language (English or Hindi/हिन्दी). No emoji, no \
filler, no AI disclaimers.\
"""

_DEVIL_PROMPT = """\
You are Headnote in DEVIL'S ADVOCATE mode — the opposing counsel this lawyer \
must beat at the next hearing. They will state their case, side, or argument; \
you take the OTHER side and argue it like a seasoned opponent, so they walk \
into court already having heard the worst.

# How you behave
- First identify their position and its single weakest point — then attack \
there. Prefer the classic angles in this order, whichever bite on these facts: \
maintainability · limitation · jurisdiction · suppression/conduct of their own \
client · gaps in evidence · weaknesses in their authorities.
- Cross like an opponent: put pointed, specific questions ("What is your \
answer when I put to you that…?"), and in later turns press on anything they \
evaded. Develop each attack properly — 2–3 sentences: the argument, the \
material on record it rests on, and the question you will put. A one-line \
jab teaches nothing; a developed attack is what they'll actually face in \
court. Two or three developed attacks per turn, strongest first.
- Distinguish their authorities the way a real opponent would (different \
facts, different stage, later ruling) — but only with real, verifiable \
points; never conjure a counter-judgment.
- If they concede or their answer is weak, say plainly how a court would read \
that concession; if their answer is strong, concede the point like a \
professional and move to the next attack.
- End EVERY reply with the one hardest question they must be ready for, alone \
on the last line, exactly as: `CROSS: <question>`
""" + _SHARED_RULES

_JUDGE_PROMPT = """\
You are Headnote in JUDGE mode — the bench this matter will be argued before. \
The lawyer practises their submission on you; you respond exactly as a \
working Indian judge would: brief, pointed, interested only in what actually \
decides the matter. You preside — you do not argue for either side and you do \
not coach.

# How you behave
- Take the threshold questions first, the way a court does: maintainability, \
jurisdiction, limitation, locus, alternative remedy — before any merits.
- Ask short, specific questions, at most two or three per turn: "Counsel, \
which provision gives this court the power at this stage?" · "Where in the \
record is that?" · "Your own document says otherwise — explain that." After \
each question, add ONE sentence of what turns on it — why the court asks — \
so counsel understands what a weak answer costs them.
- Test the WEAKEST link in the submission, not the strongest. When an \
authority is cited, ask what it actually held and how its facts compare.
- A judge indicates: when a submission is sound, say what would satisfy the \
court ("If that recovery memo is on record, the court would be inclined…"). \
When it fails, say why in a sentence, citing the provision or principle.
- Do not decide the whole case, and if asked to draft or argue, redirect in \
one line: that is counsel's work — put the submission and the court will \
test it.
- Judicial register: measured, courteous, occasionally dry. Address the \
lawyer as "Counsel".
""" + _SHARED_RULES

_PERSONA_PROMPTS = {
    "junior": _SYSTEM_PROMPT,       # the tuned ASK behaviour, unchanged
    "devil": _DEVIL_PROMPT,
    "judge": _JUDGE_PROMPT,
}


# A quick, cheap lookup vs. analysis router. Bare definitional/section lookups
# stay on fast V3; anything that asks the model to reason about facts, a
# strategy, a "can/should/whether", or a multi-fact scenario goes to R1 (the
# reasoning model) so it genuinely analyses — with a visible "Analysing…" trace.
_LOOKUP_RE = re.compile(
    r"^\s*(what\s+is|what'?s|define|meaning\s+of|full\s+form|expand|"
    r"which\s+section|section\s+\d+|§\s*\d+|punishment\s+for)\b",
    re.I,
)
_ANALYSIS_HINTS = re.compile(
    r"\b(can|could|should|would|whether|maintainable|argue|argument|options?|"
    r"strateg|advise|advice|how\s+do|how\s+can|why|challenge|quash|defend|"
    r"chance|likely|bail|anticipatory|discharge|client|accused|complainant|"
    r"vs\.?|versus|difference|compare|draft|reply|notice)\b",
    re.I,
)


def _wants_reasoning(text: str, multi_turn: bool) -> bool:
    """Route: True → R1 (deep analysis + visible reasoning); False → fast V3.

    Bias toward reasoning (the lawyer wants analysis), fast-path only obvious
    short definitional lookups."""
    t = (text or "").strip()
    words = len(t.split())
    if multi_turn:                       # a follow-up in a live thread → analytical
        return True
    if words <= 12 and _LOOKUP_RE.search(t) and not _ANALYSIS_HINTS.search(t):
        return False                     # e.g. "what is §103 BNS", "define anticipatory bail"
    if words <= 6 and not _ANALYSIS_HINTS.search(t):
        return False                     # very short factual ask
    return True


def _grounding(query: str) -> tuple[list[dict], str]:
    """Pull authoritative statute-concordance rows for anything section-shaped
    in the lawyer's latest message. Returns (sources, block_text):
      - `sources`: structured rows the client renders as a "Grounded in" strip
        (Perplexity-style) — these are REAL (from our IPC↔BNS concordance), the
        honest v1 stand-in for retrieved citations.
      - `block_text`: the same rows formatted as a GROUNDING block injected into
        the system prompt so section numbers are never guessed.
    This is the v1 'retrieval' — cheap, deterministic, no fabrication."""
    try:
        hit = statute_map.lookup(query, limit=4)
    except Exception:
        return [], ""
    results = hit.get("results") or []
    if not results:
        return [], ""
    sources, lines = [], []
    for i, r in enumerate(results, 1):
        old = r.get("old") or {}
        new = r.get("new") or {}
        new_ref = f"{new.get('code', '')} §{new.get('section', '')}".strip()
        old_ref = f"{old.get('code', '')} §{old.get('section', '')}".strip()
        title = new.get("title") or old.get("title") or ""
        summary = (r.get("summary") or "").strip()
        sources.append({"n": i, "new_ref": new_ref, "old_ref": old_ref, "title": title})
        piece = f"[{i}] {new_ref} (was {old_ref}) — {title}."
        if summary:
            piece += f" {summary}"
        lines.append(piece)
    block = (
        "\n\n# GROUNDING (authoritative — from Headnote's IPC↔BNS concordance; "
        "use these section numbers verbatim, and cite them inline as [1], [2] "
        "where relevant)\n" + "\n".join(lines)
    )
    return sources, block


_MATTER_CTX_MAX_CHARS = 7000   # bounded — the matter file must never crowd out the question


def _matter_context(user_id: str, matter_id: str) -> str:
    """Assemble one matter's WHOLE file into a grounded context block for the
    model — the server-side answer to "attach a matter". Pulls the same stores
    the case folder shows the lawyer (identity, sections, stage, hearings,
    prep, saved authorities, documents, recordings), so what the model knows
    is exactly what the folder shows — nothing more, nothing invented.

    Fails soft: any missing store contributes nothing; an unknown/foreign
    matter_id yields "" (get_case is user-scoped, so no cross-user leak).
    """
    try:
        from headnote.cases import storage as cases_storage
        row = cases_storage.get_case(matter_id, user_id=user_id)
    except Exception:
        row = None
    if not row:
        return ""

    cj = row.get("case_json") or {}
    lines: list[str] = []

    def add(label: str, val) -> None:
        v = str(val or "").strip()
        if v:
            lines.append(f"{label}: {v}")

    add("Matter", row.get("case_title"))
    num = row.get("case_number")
    if num:
        add("Case no.", f"{num}/{row.get('case_year') or ''}".rstrip("/"))
    add("Court", row.get("court_name"))
    add("CNR", row.get("cnr"))
    add("Stage", row.get("stage"))
    add("Next hearing", row.get("next_hearing_date"))
    prep = cj.get("prep") or {}
    add("Next hearing listed for", prep.get("purpose"))
    client = cj.get("client") or {}
    if client.get("name"):
        add("Client", f"{client.get('name')} ({client.get('role') or 'party'})")
    add("Petitioner", cj.get("petitioner_name"))
    add("Respondent", cj.get("respondent_name"))
    secs = cj.get("sections") or []
    acts = cj.get("acts") or []
    if secs or acts:
        add("Sections", ", ".join(str(s) for s in secs)
            + (f"  [{'; '.join(str(a) for a in acts)}]" if acts else ""))

    # The court's own record of what happened, newest first, capped.
    try:
        logs = cases_storage.list_hearing_logs(matter_id, user_id=user_id) or []
    except Exception:
        logs = []
    if logs:
        lines.append("Hearing history (court record):")
        for h in logs[:6]:
            d = str(h.get("hearing_date") or "").strip()
            w = str(h.get("what_happened") or "").strip()
            if d or w:
                lines.append(f"  - {d}: {w}")

    # Authorities the lawyer already saved against this matter — the model
    # should build on them, not re-find them.
    try:
        from headnote.api.saved_caselaw import list_for_matter
        auth = list_for_matter(user_id, matter_id, limit=8)
    except Exception:
        auth = []
    if auth:
        lines.append("Authorities already saved on this matter:")
        for a in auth:
            t = str(a.get("title") or a.get("case_id") or "").strip()
            held = str(((a.get("case_json") or {}).get("held_line")) or "").strip()
            cite = str(a.get("citation") or "").strip()
            piece = f"  - {t}" + (f" [{cite}]" if cite else "")
            if held:
                piece += f" — held: {held}"
            lines.append(piece)

    # What's on file — titles only (the lawyer attaches a document's text
    # explicitly when they want it read; listing titles keeps this bounded).
    try:
        from headnote.documents import storage as docs_storage
        docs = docs_storage.list_documents(user_id=user_id, case_id=matter_id) or []
    except Exception:
        docs = []
    if docs:
        names = [str(d.get("title") or "document").strip() for d in docs[:10]]
        lines.append("Documents on file: " + " · ".join(names))
    try:
        from headnote.consultations import storage as consult_storage
        recs = consult_storage.list_consultations(user_id=user_id, case_id=matter_id) or []
    except Exception:
        recs = []
    if recs:
        names = [str(r.get("title") or "consultation").strip() for r in recs[:5]]
        lines.append("Client consultations recorded: " + " · ".join(names))

    if not lines:
        return ""
    block = (
        "\n\n# MATTER CONTEXT (this conversation is about THIS case — its file, "
        "as recorded in Headnote; treat these as the source facts, apply the "
        "law to THEM, and never contradict or invent beyond them)\n"
        + "\n".join(lines)
    )
    return block[:_MATTER_CTX_MAX_CHARS]


def _record_usage(user: CurrentUser, plan: str, cost_paise: int, model: Optional[str]) -> None:
    """Increment the chat meter (only where the plan gates it) and log the
    usage event. Mirrors what check_and_record does on its success path — done
    here by hand because SSE can't use the context manager cleanly (the gate
    must run before the 200 stream starts)."""
    lim = get_limit(plan, "chat")
    try:
        if lim is not None and lim.limit not in (None, 0):
            meters.increment(user.id, "chat", period_key_for(lim.period))
    except Exception as e:  # pragma: no cover - metering must never break chat
        log.warning("chat meter increment failed user=%s: %s", user.id, e)
    try:
        meters.record_event(user.id, "chat", cost_paise=int(cost_paise),
                            model=model, endpoint="chat_message")
    except Exception as e:  # pragma: no cover
        log.warning("chat usage event failed user=%s: %s", user.id, e)


# ---------------------------------------------------------------- endpoint

@router.post("/message", summary="ASK mode — streamed grounded chat answer (SSE)")
def chat_message(
    body: ChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    # Gate BEFORE the stream opens — once we return a 200 event-stream we can no
    # longer surface a 402. can_use_feature raises nothing; we translate.
    check = can_use_feature(user.id, "chat", email=user.email)
    if not check["allowed"]:
        if check["reason"] == "feature_locked":
            raise FeatureLocked("chat", check["plan"])
        raise QuotaExceeded("chat", check["plan"], check["used"], check["limit"] or 0)

    # Trim to the last N turns for the model; the client holds the full thread.
    turns = body.messages[-_MAX_HISTORY_TURNS:]
    llm_messages = [{"role": t.role, "content": t.content} for t in turns]

    last_user = next((t.content for t in reversed(turns) if t.role == "user"), "")
    sources, grounding_block = _grounding(last_user)
    matter_block = _matter_context(user.id, body.matter_id) if body.matter_id else ""
    system_prompt = _PERSONA_PROMPTS.get(body.persona, _SYSTEM_PROMPT) + matter_block + grounding_block

    # Route: analysis-grade questions get R1 (reasoning) with a live trace;
    # bare lookups stay on fast V3. `body.deep` forces reasoning if ever sent.
    # Devil/judge are sparring partners — always analytical, always R1.
    #
    # The _wants_reasoning auto-route is BETA-ONLY on purpose. It biases toward
    # R1, which is slower (180s timeout vs 90s), pricier, and streams its whole
    # chain-of-thought before any answer text. The old /app Ask surface sends
    # neither `persona` nor `deep`, so without this guard every existing user's
    # everyday question would silently move to R1 the moment V2 deploys — and a
    # browser still holding a cached app.js, which ignores `reasoning` events,
    # would show a blank pane for tens of seconds. Beta testers opt into that
    # trade; paying users on /app keep the speed they have today. Setting
    # V2_PUBLIC=1 makes is_beta() true for everyone, so the ship switch covers
    # this too — no code change needed on the day V2 goes public.
    multi_turn = sum(1 for t in turns if t.role == "user") > 1
    reasoning = (body.persona != "junior") or bool(body.deep) \
        or (is_beta(user.email) and _wants_reasoning(last_user, multi_turn))

    def event_stream():
        usage = None
        # Tell the client which mode we're in so it can show the "Analysing…"
        # trace affordance for reasoning answers.
        yield f"data: {json.dumps({'type': 'meta', 'reasoning': reasoning})}\n\n"
        # Perplexity-style: surface the grounded authorities up front, before
        # the answer streams, so the "Grounded in" strip renders immediately.
        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'items': sources})}\n\n"
        try:
            for kind, payload in stream_chat(
                llm_messages, system_prompt=system_prompt, deep=reasoning,
            ):
                if kind == "reasoning":
                    yield f"data: {json.dumps({'type': 'reasoning', 'text': payload})}\n\n"
                elif kind == "delta":
                    yield f"data: {json.dumps({'type': 'delta', 'text': payload})}\n\n"
                elif kind == "usage":
                    usage = payload
                elif kind == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': payload})}\n\n"
        except Exception as e:  # pragma: no cover - defensive
            log.exception("chat stream crashed: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Something went wrong. Please try again.'})}\n\n"
        finally:
            # Side-effect only — NEVER yield here. On client disconnect a
            # GeneratorExit is raised at the yield above; yielding again inside
            # finally is illegal ("generator ignored GeneratorExit").
            cost_usd = estimate_cost_usd(usage) if usage else 0.0
            model = (usage or {}).get("model")
            _record_usage(user, check["plan"], round(cost_usd * 100), model)

        # Reached only on normal completion (a mid-stream disconnect propagates
        # GeneratorExit out of the finally above and skips this).
        model = (usage or {}).get("model")
        yield f"data: {json.dumps({'type': 'done', 'model': model})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",   # disable nginx/proxy buffering so tokens flush live
        },
    )


@router.post("/attach", summary="OCR/extract an attached file → text the lawyer can ask about")
async def chat_attach(
    file: UploadFile = File(...),
    user: CurrentUser = Depends(get_current_user),
):
    """Read one attached document (image / PDF / Word / Excel) and return its
    text. The client folds that text into the next chat question as context —
    so a lawyer can photograph an FIR or paste an order and just ask about it.

    Reuses the drafter's Groq-vision OCR + office extraction (same as the
    Document Vault). Not metered on its own — the follow-up question is.
    """
    from headnote.drafter import office
    from headnote.drafter.ocr import ocr_text_pages, _rasterize_pdfs, OCR_MARKDOWN_PROMPT

    name = file.filename or "attachment"
    data = await file.read()
    try:
        media_pages, office_text = office.collect_uploads(
            [(data, file.content_type or "", name)], max_bytes=_ATTACH_MAX_BYTES,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    pages: list[tuple[bytes, str]] = []
    for pdata, mt in media_pages:
        if mt == "application/pdf":
            pages.extend(_rasterize_pdfs([(pdata, mt)]))
        else:
            pages.append((pdata, mt))
    pages = pages[:_ATTACH_MAX_PAGES]
    if not pages and not (office_text or "").strip():
        raise HTTPException(status_code=400, detail="No readable content in that file.")

    try:
        text = ocr_text_pages(pages, prompt=OCR_MARKDOWN_PROMPT, office_text=office_text) if pages else office_text
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Couldn't read the file: {e}")

    text = (text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="Couldn't read any text — try a clearer scan.")
    truncated = len(text) > _ATTACH_MAX_CHARS
    if truncated:
        text = text[:_ATTACH_MAX_CHARS]

    return {"filename": name, "text": text, "chars": len(text), "truncated": truncated}
