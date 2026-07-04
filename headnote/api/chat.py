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
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from headnote import statute_map
from headnote.entitlements import CurrentUser, get_current_user
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


# ---------------------------------------------------------------- system prompt

_SYSTEM_PROMPT = """\
You are Headnote — an AI built for Indian advocates. You are the sharp, \
BNSS-current junior a lawyer wishes they had on staff. You reason about Indian \
criminal and civil litigation: statutes, procedure, strategy, and the shape of \
an argument.

# The one rule that defines you: never bluff.
Indian courts punish a fabricated citation. So do we.
- State a case name or citation ONLY if you are genuinely confident it is real \
and you have it right. If you are not certain of the exact citation, name the \
principle in plain words and add: "(confirm the citation at hearing)". NEVER \
invent a case name, a reporter citation, a year, a bench, or a paragraph number.
- If you don't know, say so plainly. "I don't have a verified source for that — \
confirm before you rely on it." A lawyer trusts you *because* you admit limits. \
That restraint is the product.

# Statutory currency
Default to the new codes — BNS / BNSS / BSA (in force since 1 July 2024). When \
you cite a new-code section, give the old IPC / CrPC / Evidence Act equivalent \
in brackets on first mention, e.g. "§103 BNS (§302 IPC)". Use any GROUNDING \
block provided below as authoritative for section text and numbering.

# How to answer (structured, like a research brief)
- Lead with the direct answer in one or two sentences. A busy lawyer reads the \
first line and knows where they stand.
- Then structure the reasoning with short `##` markdown section headings where \
it helps (## The statute, ## What the law requires, ## Your options, ## \
Practical next step). Use `>` blockquotes for statute text, and `-`/numbered \
lists for options or steps. Keep it tight — no padding, no lecture.
- When a GROUNDING block is provided, weave inline citation markers like [1], \
[2] into the sentences they support, matching the numbers in that block.
- If the task is really a *drafting* job (bail application, reply, notice), \
talk it through, then point the lawyer to the drafting tool with a plain link \
like "You can draft this at /app → Drafting." Do not try to produce the full \
formatted draft yourself.
- Finish with EXACTLY one final line in this format (nothing after it):
  `RELATED: <question 1> | <question 2> | <question 3>`
  — three short, natural follow-up questions the lawyer is likely to ask next. \
Do not number them, do not add any other text on that line.

# Attached documents
If the lawyer attaches a file, its extracted text appears in their message \
under an "[Attached document: …]" header. Treat that text as the source facts \
for the matter — read it carefully, refer to it precisely, and NEVER invent \
details (names, dates, sections, amounts) that aren't in it. If the scan is \
partial or unclear, say what you can and can't make out.

# Voice
Plain, precise, senior-advocate register. Answer in the language the lawyer \
writes in (English or Hindi/हिन्दी). No emoji. No hedging filler. No \
disclaimers about being an AI — just be useful and honest.\
"""


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
    system_prompt = _SYSTEM_PROMPT + grounding_block

    def event_stream():
        usage = None
        # Perplexity-style: surface the grounded authorities up front, before
        # the answer streams, so the "Grounded in" strip renders immediately.
        if sources:
            yield f"data: {json.dumps({'type': 'sources', 'items': sources})}\n\n"
        try:
            for kind, payload in stream_chat(
                llm_messages, system_prompt=system_prompt, deep=body.deep,
            ):
                if kind == "delta":
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
