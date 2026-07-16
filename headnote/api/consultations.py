"""Recorder / consultations HTTP surface.

POST   /api/consultations/transcribe   audio chunk → text (Groq Whisper)
POST   /api/consultations              transcript → structured report, stored
GET    /api/consultations              list the lawyer's consultations (newest first)
GET    /api/consultations/{id}         one consultation (report + transcript)
DELETE /api/consultations/{id}         remove one

The record→report flow: the browser records the in-person conversation, POSTs
the audio to /transcribe (audio is never persisted), then POSTs the transcript
to / which builds the structured report and stores it. The report carries a
draft-handoff prompt the UI sends into the drafter.

Auth required (get_current_user). Locally (SUPABASE_URL unset) that returns the
synthetic dev user, so the flow works tokenless. Both audio calls are metered
as 'draft' features.
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, check_and_record, get_current_user
from headnote.consultations import report as report_engine
from headnote.consultations import storage as consult_storage

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/consultations", tags=["consultations"])

_AUDIO_ALLOWED_MIME = {
    "audio/webm", "audio/ogg", "audio/wav", "audio/x-wav",
    "audio/mp4", "audio/m4a", "audio/mpeg", "audio/mp3", "audio/flac",
}
_AUDIO_MAX_BYTES = 25 * 1024 * 1024  # Whisper's hard cap


@router.post("/transcribe", summary="Transcribe one recorded audio chunk → text")
async def transcribe_chunk(
    file: UploadFile = File(...),
    language: str = "hi",
    user: CurrentUser = Depends(get_current_user),
):
    """Speech-to-text for a recorded consultation via Groq's hosted Whisper.

    Audio is read into memory, sent to Groq, and discarded — never written to
    disk (matches our 'voice data not retained' privacy claim)."""
    import os
    from headnote.integrations import sarvam
    if not sarvam.enabled() and not os.environ.get("GROQ_API_KEY"):
        raise HTTPException(status_code=503,
                            detail="Transcription requires SARVAM_API_KEY or GROQ_API_KEY on the server.")

    base_mt = (file.content_type or "").lower().split(";")[0].strip()
    if base_mt not in _AUDIO_ALLOWED_MIME:
        raise HTTPException(status_code=400,
                            detail=f"unsupported audio type {file.content_type!r}")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty audio file")
    if len(data) > _AUDIO_MAX_BYTES:
        raise HTTPException(status_code=400,
                            detail="audio too large; max 25 MB per chunk")

    lang = (language or "").lower().strip()[:2] or "hi"
    with check_and_record(user.id, "draft", endpoint="consult_transcribe", email=user.email) as _record:
        # Sarvam Saarika (Indic-native) first — better on Hindi than Whisper.
        if sarvam.enabled():
            try:
                res = sarvam.transcribe(
                    data, filename=f"audio.{base_mt.split('/')[-1] or 'webm'}", mime=base_mt,
                    language_code=(f"{lang}-IN" if lang == "hi" else "unknown"))
                if res.get("text"):
                    _record(cost_paise=0, model="sarvam/saarika")
                    return {"ok": True, "text": res["text"],
                            "language": res.get("language") or lang,
                            "segments": res.get("segments") or []}
            except Exception as _se:  # noqa: BLE001 — fall back to Groq Whisper
                pass
        try:
            from groq import Groq
            client = Groq(api_key=os.environ["GROQ_API_KEY"])
            ext = {
                "audio/webm": "webm", "audio/ogg": "ogg", "audio/wav": "wav",
                "audio/x-wav": "wav", "audio/mp4": "m4a", "audio/m4a": "m4a",
                "audio/mpeg": "mp3", "audio/mp3": "mp3", "audio/flac": "flac",
            }.get(base_mt, "webm")
            resp = client.audio.transcriptions.create(
                file=(f"audio.{ext}", data, base_mt),
                model=os.environ.get("GROQ_STT_MODEL", "whisper-large-v3-turbo"),
                language=lang,
                # verbose_json returns per-segment start times → lets the report
                # engine attach a timestamp to each verbatim key quote.
                response_format="verbose_json",
                temperature=0.0,
            )
            text = (resp.text or "").strip()
            segments = []
            for s in (getattr(resp, "segments", None) or []):
                # groq SDK returns segments as dicts or objects depending on ver
                start = s.get("start") if isinstance(s, dict) else getattr(s, "start", None)
                stext = s.get("text") if isinstance(s, dict) else getattr(s, "text", None)
                if stext:
                    segments.append({"start": round(float(start or 0), 2),
                                     "text": str(stext).strip()})
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=502, detail=f"Transcription failed: {e}")
        _record(cost_paise=100, model="whisper-large-v3-turbo")
        return {"ok": True, "text": text, "language": lang, "segments": segments}


class Segment(BaseModel):
    start: float = 0.0
    text:  str = ""


class CreateBody(BaseModel):
    transcript:   str = Field(..., min_length=1, description="Full consultation transcript")
    lang:         str = Field("hi", max_length=8)
    consent:      bool = Field(False, description="Lawyer acknowledged client consent (DPDP)")
    duration_sec: int = Field(0, ge=0)
    hint:         Optional[str] = Field(None, max_length=500, description="Optional lawyer note / matter context")
    case_id:      Optional[str] = Field(None, description="Optional link to a matter")
    segments:     list[Segment] = Field(default_factory=list,
                                        description="Whisper segments (start, text) for quote timestamps")


def _timestamped(segments: list[Segment]) -> str:
    """Render segments as '[mm:ss] text' lines so the report engine can cite times."""
    lines = []
    for s in segments:
        t = int(s.start or 0)
        lines.append(f"[{t // 60:02d}:{t % 60:02d}] {s.text.strip()}")
    return "\n".join(lines)


@router.post("", summary="Build a structured report from a transcript and store it")
def create_consultation(body: CreateBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    if not body.consent:
        raise HTTPException(status_code=400,
                            detail="Consent acknowledgement is required to save a recorded consultation.")

    with check_and_record(user.id, "draft", endpoint="consult_report", email=user.email) as _record:
        report = report_engine.build_report(
            body.transcript, lang=body.lang, hint=body.hint or "",
            timestamped=_timestamped(body.segments),
        )
        _record(cost_paise=0, model="deepseek/report")

    row = consult_storage.add_consultation(
        user_id=user.id,
        title=report.get("title") or "Consultation",
        report=report,
        transcript=body.transcript,
        case_id=body.case_id,
        matter_type=report.get("matter_type"),
        parties=report.get("title"),
        court=report.get("court"),
        lang=body.lang,
        duration_sec=body.duration_sec,
        consent=body.consent,
    )
    return {"ok": True, "consultation": row}


@router.get("", summary="List the lawyer's consultations (newest first)")
def list_consultations(user: CurrentUser = Depends(get_current_user)) -> dict:
    items = consult_storage.list_consultations(user_id=user.id)
    return {"items": items, "count": len(items)}


@router.get("/{consult_id}", summary="Get one consultation (report + transcript)")
def get_consultation(consult_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    row = consult_storage.get_consultation(consult_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no consultation with id={consult_id!r}")
    return row


@router.delete("/{consult_id}", summary="Remove a consultation")
def delete_consultation(consult_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    if not consult_storage.delete_consultation(consult_id, user_id=user.id):
        raise HTTPException(status_code=404, detail=f"no consultation with id={consult_id!r}")
    return {"ok": True, "deleted": consult_id}
