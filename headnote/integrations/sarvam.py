"""Sarvam AI — Indic-native speech-to-text (Saarika) + Document Intelligence OCR.

Chosen over Groq for the two Indic-heavy paths: Hindi handwriting OCR (court
diary pages) and Hindi consultation speech. Sarvam Vision + Saarika are trained
on Indian scripts, so they read Devanagari far better than Groq's Llama-4-Scout.

Enabled only when SARVAM_API_KEY is set (on Railway). When it's absent (local
dev) `enabled()` is False and callers fall back to Groq — so nothing breaks.

Docs: https://docs.sarvam.ai  ·  base https://api.sarvam.ai  ·  auth header
`api-subscription-key`. Document Intelligence is an async job:
initialise → upload-links → PUT file → start → poll status → download-links → GET.
"""

from __future__ import annotations

import io
import os
import time
import zipfile

import httpx

_BASE = os.environ.get("SARVAM_BASE_URL", "https://api.sarvam.ai").rstrip("/")
_STT_MODEL = os.environ.get("SARVAM_STT_MODEL", "saarika:v2.5")
_DI = "/doc-digitization/job/v1"
_DONE = {"completed", "partiallycompleted", "success", "partialsuccess", "complete"}
_FAIL = {"failed", "error"}


def _key() -> str:
    return os.environ.get("SARVAM_API_KEY", "").strip()


def enabled() -> bool:
    return bool(_key())


def _hdr(json: bool = False) -> dict:
    h = {"api-subscription-key": _key()}
    if json:
        h["Content-Type"] = "application/json"
    return h


# --------------------------------------------------------------- speech-to-text
def transcribe(audio: bytes, *, filename: str = "audio.webm",
               mime: str = "audio/webm", language_code: str = "unknown") -> dict:
    """POST /speech-to-text (sync, audio < 30s — fits the recorder's chunks).
    Returns {text, language, segments}. Raises on non-200."""
    r = httpx.post(
        f"{_BASE}/speech-to-text",
        headers={"api-subscription-key": _key()},
        data={"model": _STT_MODEL, "language_code": language_code},
        files={"file": (filename, audio, mime)},
        timeout=60.0,
    )
    if r.status_code != 200:
        raise RuntimeError(f"Sarvam STT {r.status_code}: {r.text[:300]}")
    j = r.json() or {}
    return {"text": (j.get("transcript") or "").strip(),
            "language": j.get("language_code") or "",
            "segments": []}   # sync endpoint has no per-segment timestamps


# ------------------------------------------------------ document intelligence OCR
def _first_url(mapping: dict, prefer: str = "") -> str | None:
    """Pull a presigned URL out of an {name: {file_url}} (or {name: url}) map."""
    if not isinstance(mapping, dict) or not mapping:
        return None
    det = mapping.get(prefer) if prefer in mapping else next(iter(mapping.values()))
    if isinstance(det, dict):
        return det.get("file_url") or det.get("url")
    return det if isinstance(det, str) else None


def digitize_to_text(data: bytes, *, filename: str = "page.jpg",
                     mime: str = "image/jpeg", language: str = "hi-IN",
                     poll_timeout: float = 80.0) -> str:
    """Run one document (image or PDF) through Sarvam Document Intelligence →
    return extracted Markdown text. Upload accepts PDF or ZIP: a PDF is sent as-is,
    an image is zipped."""
    if not _key():
        raise RuntimeError("SARVAM_API_KEY not set")
    is_pdf = mime == "application/pdf" or filename.lower().endswith(".pdf")
    if is_pdf:
        upload_bytes, zip_name, put_ctype = data, (os.path.basename(filename) or "doc.pdf"), "application/pdf"
    else:
        zbuf = io.BytesIO()
        with zipfile.ZipFile(zbuf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(filename, data)
        upload_bytes, zip_name, put_ctype = zbuf.getvalue(), "diary.zip", "application/zip"

    # 1) initialise — body wraps the config under `job_parameters` (per the API's
    #    400 "body.job_parameters : Field required"); field is `language`, format `md`.
    r = httpx.post(f"{_BASE}{_DI}", headers=_hdr(True),
                   json={"job_parameters": {"language": language, "output_format": "md"}},
                   timeout=30.0)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Sarvam init {r.status_code}: {r.text[:300]}")
    j = r.json() or {}
    job_id = j.get("job_id") or j.get("jobId") or j.get("id")
    if not job_id:
        raise RuntimeError(f"Sarvam init: no job_id in {r.text[:300]}")

    # 2) upload links
    r = httpx.post(f"{_BASE}{_DI}/upload-files", headers=_hdr(True),
                   json={"job_id": job_id, "files": [zip_name]}, timeout=30.0)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Sarvam upload-links {r.status_code}: {r.text[:300]}")
    up = r.json() or {}
    put_url = _first_url(up.get("upload_urls") or up.get("urls") or {}, prefer=zip_name)
    if not put_url:
        raise RuntimeError(f"Sarvam upload-links: no url in {r.text[:300]}")

    # 3) PUT the zip to the presigned URL
    # presigned target is Azure Blob → requires the x-ms-blob-type header
    pr = httpx.put(put_url, content=upload_bytes,
                   headers={"Content-Type": put_ctype, "x-ms-blob-type": "BlockBlob"},
                   timeout=90.0)
    if pr.status_code not in (200, 201, 204):
        raise RuntimeError(f"Sarvam upload PUT {pr.status_code}: {pr.text[:200]}")

    # 4) start
    r = httpx.post(f"{_BASE}{_DI}/{job_id}/start", headers=_hdr(True), json={}, timeout=30.0)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Sarvam start {r.status_code}: {r.text[:300]}")

    # 5) poll status
    end, state = time.time() + poll_timeout, ""
    while time.time() < end:
        s = httpx.get(f"{_BASE}{_DI}/{job_id}/status", headers=_hdr(), timeout=30.0)
        if s.status_code == 200:
            body = s.json() or {}
            state = str(body.get("job_state") or body.get("status") or "").lower()
            if state in _DONE:
                break
            if state in _FAIL:
                raise RuntimeError(f"Sarvam job failed: {s.text[:300]}")
        time.sleep(2.5)
    if state not in _DONE:
        raise RuntimeError(f"Sarvam job not finished in {poll_timeout:.0f}s (state={state or 'unknown'})")

    # 6) download links
    r = httpx.post(f"{_BASE}{_DI}/{job_id}/download-files", headers=_hdr(True), json={}, timeout=30.0)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"Sarvam download-links {r.status_code}: {r.text[:300]}")
    dl = (r.json() or {}).get("download_urls") or {}

    # 7) fetch outputs, concatenate any markdown/text (unzip if zipped)
    texts: list[str] = []
    for name, det in (dl.items() if isinstance(dl, dict) else []):
        url = det.get("file_url") if isinstance(det, dict) else det
        if not url:
            continue
        try:
            fr = httpx.get(url, timeout=60.0)
            if fr.status_code != 200:
                continue
            if name.lower().endswith(".zip"):
                zf = zipfile.ZipFile(io.BytesIO(fr.content))
                for n in zf.namelist():
                    if n.lower().endswith((".md", ".txt", ".html")):
                        texts.append(zf.read(n).decode("utf-8", "ignore"))
            elif name.lower().endswith((".md", ".txt", ".html", ".json")):
                texts.append(fr.text)
        except Exception:  # noqa: BLE001 — skip an unreadable output file
            continue
    out = "\n\n".join(t for t in texts if t).strip()
    if not out:
        raise RuntimeError("Sarvam produced no readable text output")
    return out
