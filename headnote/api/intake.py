"""Client document intake — a write-only link per matter, with an approval gate.

Lawyer side (auth required):
  GET    /api/matters/{id}/intake-link            the active link (or none)
  POST   /api/matters/{id}/intake-link            mint one (revokes the previous)
  DELETE /api/matters/{id}/intake-link            revoke
  GET    /api/matters/{id}/intake                 the pending tray
  GET    /api/matters/{id}/intake/{uid}/file      preview (signed URL or bytes)
  POST   /api/matters/{id}/intake/{uid}/approve   file it into the case folder
  POST   /api/matters/{id}/intake/{uid}/discard   delete it for good

Client side (NO login — the token is the authorisation):
  GET    /api/intake/{token}          what to show on the upload page
  POST   /api/intake/{token}/upload   accept a file into the pending tray

The public endpoints are deliberately WRITE-ONLY. `GET /api/intake/{token}`
returns only the case caption and the upload rules — never the documents on file,
never the order sheet, never another matter. A leaked link cannot leak the case;
the worst it can do is put junk in a tray the lawyer discards.

See migrations/013_client_intake.sql for the full reasoning.
"""

from __future__ import annotations

import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from headnote import filestore
from headnote.cases import storage as cases_storage
from headnote.documents import storage as docs_storage
from headnote.entitlements import CurrentUser, get_current_user
from headnote.intake import storage as intake_storage

log = logging.getLogger(__name__)
router = APIRouter(tags=["intake"])

# A client photographs documents on a phone. Accept what phones produce, and
# nothing executable.
ALLOWED = {"image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif",
           "image/webp", "application/pdf"}
MAX_BYTES = 25 * 1024 * 1024          # one file
MAX_NOTE = 500


def _party(case: dict) -> str:
    cj = case.get("case_json") or {}
    if isinstance(cj, dict):
        nm = (cj.get("client") or {}).get("name")
        if nm:
            return nm
    return case.get("case_title") or "your matter"


def _caption(case: dict) -> dict:
    """The ONLY case information the public page is allowed to see."""
    return {
        "party": _party(case),
        "case_number": (f"{case.get('case_number')}/{case.get('case_year')}"
                        if case.get("case_number") else None),
        "court_name": case.get("court_name"),
    }


def _disposed(case: dict) -> bool:
    cj = case.get("case_json") or {}
    st = str((cj.get("case_status") if isinstance(cj, dict) else "") or "")
    return "dispos" in st.lower()


def _own_case(case_id: str, user_id: str) -> dict:
    case = cases_storage.get_case(case_id, user_id=user_id)
    if not case:
        raise HTTPException(status_code=404, detail="matter not found")
    return case


# ============================================================ lawyer side

class LinkBody(BaseModel):
    label: Optional[str] = Field(None, max_length=120)
    expires_days: Optional[int] = Field(
        None, ge=1, le=3650,
        description="Optional. Left unset the link lives as long as the matter — "
                    "a case runs for years and a link that dies in a fortnight "
                    "just gets re-sent.")
    max_per_day: int = Field(20, ge=1, le=200)


def _link_out(link: Optional[dict], base: str = "") -> Optional[dict]:
    if not link:
        return None
    return {
        "id": link.get("id"),
        "url": f"{base}/intake/{link.get('token')}",
        "label": link.get("label"),
        "expires_at": link.get("expires_at"),
        "max_per_day": link.get("max_per_day"),
        "created_at": link.get("created_at"),
        "last_used_at": link.get("last_used_at"),
    }


@router.get("/api/matters/{case_id}/intake-link", summary="The matter's active client-upload link")
def get_link(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    _own_case(case_id, user.id)
    link = intake_storage.active_link(case_id, user.id)
    return {"link": _link_out(link)}


@router.post("/api/matters/{case_id}/intake-link", summary="Mint a client-upload link (revokes the old one)")
def make_link(case_id: str, body: LinkBody,
              user: CurrentUser = Depends(get_current_user)) -> dict:
    case = _own_case(case_id, user.id)
    link = intake_storage.create_link(
        case_id, user.id, label=body.label or f"Client — {_party(case)}",
        expires_days=body.expires_days, max_per_day=body.max_per_day)
    if not link:
        raise HTTPException(status_code=500, detail="could not create the link")
    return {"ok": True, "link": _link_out(link),
            "share_text": (f"Namaste. Please upload the documents for "
                           f"{_party(case)} here — it opens without any login.")}


@router.delete("/api/matters/{case_id}/intake-link", summary="Revoke the link immediately")
def kill_link(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    _own_case(case_id, user.id)
    n = intake_storage.revoke_active(case_id, user.id)
    return {"ok": True, "revoked": n}


@router.get("/api/matters/{case_id}/intake", summary="Documents the client sent, awaiting review")
def tray(case_id: str, status: str = "pending",
         user: CurrentUser = Depends(get_current_user)) -> dict:
    _own_case(case_id, user.id)
    rows = intake_storage.list_uploads(user.id, case_id=case_id, status=status)
    return {"count": len(rows), "status": status, "uploads": [{
        "id": r.get("id"), "filename": r.get("filename"), "mime": r.get("mime"),
        "size_bytes": r.get("size_bytes"), "note": r.get("note"),
        "uploader_name": r.get("uploader_name"), "uploader_phone": r.get("uploader_phone"),
        "created_at": r.get("created_at"), "status": r.get("status"),
        "document_id": r.get("document_id"),
    } for r in rows]}


@router.get("/api/matters/{case_id}/intake/{upload_id}/file",
            summary="Preview what the client sent (private; short-lived link)")
def preview(case_id: str, upload_id: str, user: CurrentUser = Depends(get_current_user)):
    _own_case(case_id, user.id)
    up = intake_storage.get_upload(upload_id, user.id)
    if not up or str(up.get("case_id")) != str(case_id):
        raise HTTPException(status_code=404, detail="upload not found")
    url = filestore.signed_url(up.get("object_path") or "", seconds=300)
    if url:
        return {"url": url, "mime": up.get("mime"), "expires_in": 300}
    data = filestore.get(up.get("object_path") or "")
    if data is None:
        raise HTTPException(status_code=410, detail="the file is no longer available")
    from fastapi.responses import Response
    return Response(content=data, media_type=up.get("mime") or "application/octet-stream")


class ApproveBody(BaseModel):
    title: Optional[str] = Field(None, max_length=200)
    doc_type: Optional[str] = Field(None, max_length=40)
    ocr: bool = Field(True, description="Read the document so it is searchable")


@router.post("/api/matters/{case_id}/intake/{upload_id}/approve",
             summary="Save a client upload into the case folder")
async def approve(case_id: str, upload_id: str, body: ApproveBody,
                  user: CurrentUser = Depends(get_current_user)) -> dict:
    """The approval gate: only here does a client's file enter the record, and it
    goes in through the ordinary Document Vault so the reader, search and Legal
    Lens all work on it exactly as they would for a document the lawyer scanned."""
    _own_case(case_id, user.id)
    up = intake_storage.get_upload(upload_id, user.id)
    if not up or str(up.get("case_id")) != str(case_id):
        raise HTTPException(status_code=404, detail="upload not found")
    if up.get("status") != intake_storage.PENDING:
        raise HTTPException(status_code=409, detail=f"already {up.get('status')}")

    data = filestore.get(up.get("object_path") or "")
    if not data:
        raise HTTPException(status_code=410, detail="the file is no longer available")

    mime = up.get("mime") or "application/octet-stream"
    text, pages = "", []
    if body.ocr:
        try:
            import asyncio
            from headnote.drafter.ocr import ocr_text_pages, _rasterize_pdfs
            pages = _rasterize_pdfs([(data, mime)]) if "pdf" in mime else [(data, mime)]
            text = await asyncio.to_thread(ocr_text_pages, pages) or ""
        except Exception as e:  # noqa: BLE001 — filing it matters more than reading it
            log.warning("intake OCR skipped for %s: %s", upload_id, e)

    doc = docs_storage.add_document(
        user_id=user.id, title=(body.title or up.get("filename") or "Client document"),
        full_text=text, doc_type=body.doc_type or "client-upload",
        original_filename=up.get("filename"), mime=mime, case_id=case_id,
        pages=pages or None,
        metadata={"source": "client-intake", "uploader_name": up.get("uploader_name"),
                  "uploader_phone": up.get("uploader_phone"), "note": up.get("note"),
                  "received_at": up.get("created_at")})
    if not doc:
        raise HTTPException(status_code=500, detail="could not file the document")

    intake_storage.set_status(upload_id, user.id, intake_storage.SAVED,
                             document_id=str(doc.get("id")))
    return {"ok": True, "document": {"id": doc.get("id"), "title": doc.get("title")},
            "ocr": bool(text)}


@router.post("/api/matters/{case_id}/intake/{upload_id}/discard",
             summary="Discard a client upload — the file is deleted")
def discard(case_id: str, upload_id: str,
            user: CurrentUser = Depends(get_current_user)) -> dict:
    _own_case(case_id, user.id)
    up = intake_storage.get_upload(upload_id, user.id)
    if not up or str(up.get("case_id")) != str(case_id):
        raise HTTPException(status_code=404, detail="upload not found")
    # Discard has to mean gone, not hidden: the bytes are removed, and only the
    # audit row (who sent what, when) is kept.
    filestore.delete(up.get("object_path") or "")
    intake_storage.set_status(upload_id, user.id, intake_storage.DISCARDED)
    return {"ok": True}


# ============================================================ client side (no login)

def _resolve(token: str) -> tuple[dict, dict]:
    """Token → (link, case). Raises the same 404 for every failure mode so the
    endpoint cannot be used to probe which tokens exist."""
    link = intake_storage.link_by_token(token)
    if not link or link.get("revoked_at"):
        raise HTTPException(status_code=404, detail="This upload link is no longer active.")
    exp = link.get("expires_at")
    if exp:
        try:
            if datetime.fromisoformat(str(exp).replace("Z", "+00:00")) < datetime.now(timezone.utc):
                raise HTTPException(status_code=404, detail="This upload link has expired.")
        except HTTPException:
            raise
        except Exception:  # noqa: BLE001 — an unparseable date must not open the link
            raise HTTPException(status_code=404, detail="This upload link is no longer active.")
    case = cases_storage.get_case(str(link["case_id"]), user_id=str(link["user_id"]))
    if not case:
        raise HTTPException(status_code=404, detail="This upload link is no longer active.")
    if _disposed(case):
        raise HTTPException(status_code=404, detail="This case is closed, so the link is no longer active.")
    return link, case


@router.get("/api/intake/{token}", summary="Public: what the client's upload page shows")
def intake_info(token: str) -> dict:
    link, case = _resolve(token)
    return {"ok": True, "case": _caption(case),
            "accepts": sorted(ALLOWED), "max_mb": MAX_BYTES // (1024 * 1024),
            "consent": ("These documents go only to your advocate for your case. "
                        "Your advocate decides what is placed on the court file.")}


@router.post("/api/intake/{token}/upload", summary="Public: send a document to the advocate")
async def intake_upload(token: str, file: UploadFile = File(...),
                        note: str = Form(""), uploader_name: str = Form(""),
                        uploader_phone: str = Form("")) -> dict:
    link, case = _resolve(token)

    used = intake_storage.count_today(str(link["id"]), str(link["user_id"]))
    if used >= int(link.get("max_per_day") or 20):
        raise HTTPException(status_code=429,
                            detail="Too many files sent today. Please try again tomorrow.")

    mime = (file.content_type or "").split(";")[0].strip().lower()
    if mime not in ALLOWED:
        raise HTTPException(status_code=415,
                            detail="Please send a photo (JPG/PNG/HEIC) or a PDF.")
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="That file was empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(status_code=413,
                            detail=f"That file is too large (limit {MAX_BYTES // (1024*1024)} MB).")

    safe = re.sub(r"[^A-Za-z0-9._-]", "_", (file.filename or "upload"))[:80]
    path = f"{link['user_id']}/{link['case_id']}/{uuid.uuid4().hex}_{safe}"
    if not filestore.put(path, data, mime=mime):
        raise HTTPException(status_code=502, detail="Could not receive that file. Please try again.")

    row = intake_storage.add_upload(
        user_id=str(link["user_id"]), case_id=str(link["case_id"]), link_id=str(link["id"]),
        filename=safe, mime=mime, size_bytes=len(data), object_path=path,
        note=(note or "")[:MAX_NOTE], uploader_name=(uploader_name or "")[:80],
        uploader_phone=(uploader_phone or "")[:20])
    if not row:
        filestore.delete(path)
        raise HTTPException(status_code=500, detail="Could not record that file. Please try again.")
    intake_storage.touch_link(link)
    return {"ok": True, "received": safe,
            "message": "Sent to your advocate. They will confirm what goes on the file."}
