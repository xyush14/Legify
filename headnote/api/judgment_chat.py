"""Ask-this-judgment — grounded Q&A scoped to ONE judgment.

The research card surfaces a precedent; this endpoint lets the lawyer
interrogate that specific judgment ("does this apply if my client bought
before registration?") and get answers grounded ONLY in its text, with
paragraph anchors on every claim.

Discipline (same zero-fabrication contract as the drafter + research cards):
  - The judgment's parsed paragraphs are the ONLY source. If the judgment
    doesn't address something, the model must say so — never import outside
    law unlabelled.
  - Every legal claim carries a paragraph anchor "(Para N)" the lawyer can
    check against the full text one click away.
  - After the stream completes we run the existing verify-layer checks
    (anchor numbers exist + quotes appear verbatim) and emit a final
    `verify` event so the UI can badge the answer honestly.

Model: DeepSeek via the shared stream_chat (product cost rule) — the
judgment text is sent as the system prompt so DeepSeek's prefix cache keeps
follow-up questions cheap.

Endpoint: POST /api/judgment/chat → text/event-stream (SSE).
"""

from __future__ import annotations

import json
import logging
from typing import List, Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from headnote import config, verify
from headnote.entitlements import CurrentUser, get_current_user
from headnote.entitlements.gates import FeatureLocked, QuotaExceeded, can_use_feature
from headnote.entitlements import meters
from headnote.entitlements.plans import get_limit, period_key_for
from headnote.llm.client import estimate_cost_usd, stream_chat

log = logging.getLogger(__name__)

router = APIRouter(prefix="/api/judgment", tags=["judgment-chat"])

_MAX_HISTORY_TURNS = 10
# Cap the judgment text we inject. Long SC judgments run 100k+ chars; beyond
# this we keep the structurally important paragraphs (facts / issue /
# reasoning / conclusion first) and tell the model the text was trimmed.
_MAX_DOC_CHARS = 60_000


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=8000)


class JudgmentChatRequest(BaseModel):
    doc_id: int = Field(..., ge=1)              # Indian Kanoon tid
    messages: List[ChatTurn] = Field(..., min_length=1, max_length=30)
    deep: bool = False


_SYSTEM_TEMPLATE = """You are Headnote, answering an Indian advocate's questions about ONE specific judgment. The judgment's text is below — it is your ONLY source of law and fact for this conversation.

JUDGMENT: {title}
COURT/SOURCE: {docsource}
DATE: {publishdate}

# The rules that define this surface (non-negotiable)
1. Answer ONLY from the judgment text below. Every legal claim MUST end with its paragraph anchor, e.g. "(Para 14)" — use the paragraph numbers exactly as given.
2. If the judgment does not address the question, say plainly: "This judgment does not deal with that." You may then add ONE sentence of general orientation clearly labelled "(general position — not from this judgment; verify independently)". Never present outside law as if this judgment said it.
3. Quote the court verbatim when the exact words matter; keep quotes ≤ 40 words and anchor them.
4. Distinguish the COURT'S findings from a party's allegations or submissions. A passage beginning "it was contended/alleged…" is a party's case, not the holding — say which is which.
5. Applying it to the lawyer's facts is allowed and encouraged — but separate "what this judgment holds" from "how it may apply to your matter", and never invent facts about either.
6. Answer in the language the lawyer writes in (English or Hindi/हिन्दी). Plain, senior-advocate register. No emoji, no filler, no AI disclaimers.

# Judgment text (paragraph-numbered{trim_note})
{paragraphs}
"""


def _get_client():
    """Local lazy KanoonClient — mirrors app.py's gating without importing the
    app module (circular import). The SQLite doc cache is shared on disk, so a
    judgment fetched during research is served from cache here (₹0)."""
    if not getattr(config, "INDIAN_KANOON_TOKEN", None):
        return None
    try:
        from headnote.kanoon.client import KanoonClient
        return KanoonClient()
    except Exception as e:  # noqa: BLE001
        log.warning("judgment-chat: IK client init failed: %s", e)
        return None


def _paragraphs_block(doc) -> tuple[str, list[verify.EvidenceParagraph], bool]:
    """Render the judgment as a numbered-paragraph block + verify evidence.

    Returns (block_text, evidence_paragraphs, trimmed?). Structure-first
    trimming: if over budget, keep facts/issue/court-discussion/conclusion
    paragraphs before petitioner/respondent argument recitals.
    """
    from headnote.kanoon.parser import parse_judgment

    parsed = parse_judgment(doc.doc_html, tid=doc.tid, title_hint=doc.title)
    paras = [p for p in parsed.paragraphs if (p.text or "").strip()]

    total = sum(len(p.text) for p in paras)
    trimmed = False
    if total > _MAX_DOC_CHARS:
        trimmed = True
        # Keep the court's own voice first; drop argument recitals from the tail.
        keep_first = ("facts", "issue", "court_discussion", "conclusion", "ratio")
        primary = [p for p in paras if p.structure in keep_first]
        secondary = [p for p in paras if p.structure not in keep_first]
        kept, budget = [], _MAX_DOC_CHARS
        for p in primary + secondary:
            if budget - len(p.text) < 0:
                continue
            kept.append(p)
            budget -= len(p.text)
        # restore document order
        order = {id(p): i for i, p in enumerate(paras)}
        kept.sort(key=lambda p: order[id(p)])
        paras = kept

    lines, evidence = [], []
    for p in paras:
        label = f"Para {p.num}" if p.num is not None else p.id
        lines.append(f"[{label}] {p.text}")
        evidence.append(verify.EvidenceParagraph(
            case_id=f"ik:{doc.tid}", para_id=p.id, para_num=p.num, text=p.text,
        ))
    return "\n\n".join(lines), evidence, trimmed


def _verify_answer(answer: str, evidence: list[verify.EvidenceParagraph]) -> dict:
    """Post-stream check: anchors point at real paragraphs; quotes appear in
    the judgment. Pure verify-layer reuse — no LLM, no network."""
    claimed = verify._extract_para_numbers(answer)
    valid_nums = {e.para_num for e in evidence if e.para_num is not None}
    anchors_missing = [n for n in claimed if n not in valid_nums] if valid_nums else []

    quote_fails = 0
    quotes = verify._extract_quotes(answer)
    for q in quotes[:6]:  # bound the work — long answers, many quotes
        ratio, _, _ = verify._best_match(q, evidence)
        if ratio < verify.DEFAULT_VERBATIM_THRESHOLD:
            quote_fails += 1

    clean = not anchors_missing and quote_fails == 0
    return {
        "clean": clean,
        "anchors_claimed": len(claimed),
        "anchors_missing": anchors_missing[:10],
        "quotes_checked": min(len(quotes), 6),
        "quote_fails": quote_fails,
    }


def _record_usage(user: CurrentUser, plan: str, cost_paise: int, model) -> None:
    lim = get_limit(plan, "chat")
    try:
        if lim is not None and lim.limit not in (None, 0):
            meters.increment(user.id, "chat", period_key_for(lim.period))
    except Exception as e:  # pragma: no cover
        log.warning("judgment-chat meter failed user=%s: %s", user.id, e)
    try:
        meters.record_event(user.id, "chat", cost_paise=int(cost_paise),
                            model=model, endpoint="judgment_chat")
    except Exception as e:  # pragma: no cover
        log.warning("judgment-chat usage event failed user=%s: %s", user.id, e)


@router.post("/chat", summary="Ask questions about ONE judgment (SSE, para-anchored)")
def judgment_chat(
    body: JudgmentChatRequest,
    user: CurrentUser = Depends(get_current_user),
):
    # Same meter as ASK mode — it's the same kind of conversational spend.
    check = can_use_feature(user.id, "chat", email=user.email)
    if not check["allowed"]:
        if check["reason"] == "feature_locked":
            raise FeatureLocked("chat", check["plan"])
        raise QuotaExceeded("chat", check["plan"], check["used"], check["limit"] or 0)

    client = _get_client()
    if client is None:
        raise HTTPException(status_code=503, detail="Judgment source is not configured on this server.")
    try:
        doc = client.get_doc(int(body.doc_id))
    except Exception as e:  # noqa: BLE001 — not found / budget / network
        raise HTTPException(status_code=404, detail=f"Couldn't load this judgment ({type(e).__name__}).")

    block, evidence, trimmed = _paragraphs_block(doc)
    if not block.strip():
        raise HTTPException(status_code=422, detail="This judgment has no readable text.")

    system_prompt = _SYSTEM_TEMPLATE.format(
        title=doc.title or f"IK doc {doc.tid}",
        docsource=doc.docsource or "Indian Kanoon",
        publishdate=doc.publishdate or "unknown",
        trim_note=" — long judgment, argument recitals trimmed" if trimmed else "",
        paragraphs=block,
    )

    turns = body.messages[-_MAX_HISTORY_TURNS:]
    llm_messages = [{"role": t.role, "content": t.content} for t in turns]

    def event_stream():
        usage = None
        answer_acc: list[str] = []
        try:
            for kind, payload in stream_chat(
                llm_messages, system_prompt=system_prompt, deep=body.deep,
            ):
                if kind == "delta":
                    answer_acc.append(payload)
                    yield f"data: {json.dumps({'type': 'delta', 'text': payload})}\n\n"
                elif kind == "usage":
                    usage = payload
                elif kind == "error":
                    yield f"data: {json.dumps({'type': 'error', 'message': payload})}\n\n"
        except Exception as e:  # pragma: no cover - defensive
            log.exception("judgment-chat stream crashed: %s", e)
            yield f"data: {json.dumps({'type': 'error', 'message': 'Something went wrong. Please try again.'})}\n\n"
        finally:
            # Side-effect only — never yield in finally (GeneratorExit rule).
            cost_usd = estimate_cost_usd(usage) if usage else 0.0
            _record_usage(user, check["plan"], round(cost_usd * 100), (usage or {}).get("model"))

        # Normal completion only: verify the assembled answer against the
        # judgment and tell the UI, then close.
        try:
            report = _verify_answer("".join(answer_acc), evidence)
        except Exception:  # noqa: BLE001 — verification must never kill the stream
            report = {"clean": False, "error": "verification unavailable"}
        yield f"data: {json.dumps({'type': 'verify', 'report': report})}\n\n"
        yield f"data: {json.dumps({'type': 'done', 'model': (usage or {}).get('model')})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
