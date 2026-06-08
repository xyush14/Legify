"""Admin endpoints — bearer-token-guarded. Mounted onto the main FastAPI app
in headnote.api.app.

Auth: every /admin/* route checks `Authorization: Bearer <ADMIN_TOKEN>`.
ADMIN_TOKEN is set via env var (see headnote.config); if unset, every
admin route returns 503 with a clear message so misconfiguration surfaces
loudly.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from headnote import config
from headnote.api.telemetry import get_summary


router = APIRouter(prefix="/admin", tags=["admin"])


def _require_admin(authorization: Optional[str]) -> None:
    """Raises HTTPException unless the header carries the configured bearer."""
    if not config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Admin routes are disabled: ADMIN_TOKEN env var is not set. "
                "Add it to .env (e.g. `ADMIN_TOKEN=<random-long-string>`) "
                "and restart."
            ),
        )
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing 'Authorization: Bearer <ADMIN_TOKEN>' header.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(None, 1)[1].strip()
    # Constant-time-ish compare. Python lacks a builtin, but for short
    # admin tokens the timing leak is academic.
    if token != config.ADMIN_TOKEN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Bearer token does not match ADMIN_TOKEN.",
        )


@router.get("/telemetry", summary="Cost / escalation / quality summary")
def admin_telemetry(
    authorization: Optional[str] = Header(default=None),
    days: int = Query(default=7, ge=1, le=90,
                      description="Window in days (1-90). Defaults to last 7 days."),
):
    """Return aggregate telemetry over the last `days` days.

    Authentication: `Authorization: Bearer <ADMIN_TOKEN>`.

    The payload powers a future operator dashboard. For now, curl it:

        curl -H "Authorization: Bearer $ADMIN_TOKEN" \\
             https://your-deploy/admin/telemetry?days=7

    Key signals:
      - escalation_rate_pct: if this climbs > 30%, Sonnet is failing too
        often and a prompt tweak (or threshold change) is overdue.
      - avg_cost_paise_per_call: trend down should be the goal as cache
        hits and Sonnet defaults dominate over time.
      - avg_confidence_by_task: Sonnet self-rated confidence on
        situation/digest. Low averages indicate prompt quality issues.
    """
    _require_admin(authorization)
    return get_summary(days=days)


@router.post("/backfill_facts", summary="Backfill facts_json for hf_judgments rows")
def admin_backfill_facts(
    authorization: Optional[str] = Header(default=None),
    redo: bool = Query(default=False, description="Re-extract for ALL rows, not just NULL ones"),
    batch_size: int = Query(default=1000, ge=100, le=10000),
    limit: Optional[int] = Query(default=None, ge=1,
        description="Cap rows processed this call (for incremental runs). Omit = all."),
):
    """Run the regex fact extractor over every hf_judgments row where
    facts_json IS NULL and persist the result. Idempotent.

    This is the HTTP equivalent of `python scripts/backfill_facts.py`,
    exposed so Railway deploys without shell access can still trigger it.

    Authentication: `Authorization: Bearer <ADMIN_TOKEN>`.

    The call BLOCKS for the full run (no background task) — at 42K rows
    this completes in 1-3 minutes, well within HTTP timeouts on Railway.
    Larger corpora should use `--limit` to chunk the work across calls.

    curl example:

        curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
             https://your-deploy/admin/backfill_facts

    Re-extract everything after an extractor patch:

        curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
             "https://your-deploy/admin/backfill_facts?redo=true"
    """
    _require_admin(authorization)

    # Local imports so the heavy fact_extractor module isn't pulled at
    # app boot time — it's only loaded the first time someone runs the
    # backfill or hits /api/hf_search.
    import json as _json
    import sqlite3 as _sqlite3
    import time as _time
    from headnote.retrieval.fact_extractor import extract_facts as _extract_facts
    from headnote.config import KANOON_CACHE_PATH as _DB_PATH

    t_start = _time.monotonic()
    conn = _sqlite3.connect(_DB_PATH, timeout=30)
    try:
        # First, confirm the hf_judgments table exists at all. If the
        # harvest hasn't run on this Railway deploy (or the volume was
        # reset), bail with a clear error instead of a raw SQLite trace.
        table_exists = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='hf_judgments'"
        ).fetchone()
        if not table_exists:
            return {
                "ok": False,
                "error": "hf_judgments table missing — corpus has not been imported on this deploy.",
                "db_path": str(_DB_PATH),
                "hint": (
                    "Either the Railway Volume is empty (fresh mount, or got reset on a redeploy), "
                    "or KANOON_CACHE_PATH is pointing at a different file than the one the harvest "
                    "wrote to. Check /api/health → hf_corpus.total to confirm. "
                    "To harvest from scratch: see scripts/HARVEST_README.md."
                ),
            }

        # Make sure facts_json column exists before we try to use it
        try:
            conn.execute("ALTER TABLE hf_judgments ADD COLUMN facts_json TEXT")
            conn.commit()
            column_added = True
        except _sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e).lower():
                raise
            column_added = False

        where = "" if redo else "WHERE facts_json IS NULL"
        select_sql = f"SELECT doc_id, title, summary, text FROM hf_judgments {where}"
        if limit:
            select_sql += f" LIMIT {int(limit)}"

        try:
            total_target = conn.execute(
                f"SELECT COUNT(*) FROM hf_judgments {where}"
            ).fetchone()[0]
        except _sqlite3.OperationalError:
            return {"ok": False, "error": "hf_judgments table missing — run harvest first."}

        if total_target == 0:
            return {
                "ok": True,
                "message": "Nothing to backfill — every row already has facts_json.",
                "processed": 0,
                "with_facts": 0,
                "column_added": column_added,
            }

        if limit:
            total_target = min(total_target, int(limit))

        cur = conn.execute(select_sql)
        processed = 0
        with_facts = 0
        batch: list[tuple[str, str]] = []

        for row in cur:
            doc_id, title, summary, text = row
            fact_input = ""
            if summary:
                fact_input += summary + "\n\n"
            if title:
                fact_input += title + "\n\n"
            fact_input += (text or "")[:20000]

            try:
                facts = _extract_facts(fact_input)
                facts_json = _json.dumps(facts, ensure_ascii=False) if facts else ""
            except Exception:
                facts_json = ""

            if facts_json:
                with_facts += 1
            batch.append((facts_json, doc_id))
            processed += 1

            if len(batch) >= batch_size:
                conn.executemany(
                    "UPDATE hf_judgments SET facts_json = ? WHERE doc_id = ?",
                    batch,
                )
                conn.commit()
                batch = []

        # Flush tail
        if batch:
            conn.executemany(
                "UPDATE hf_judgments SET facts_json = ? WHERE doc_id = ?",
                batch,
            )
            conn.commit()

        elapsed = _time.monotonic() - t_start

        # Re-stat to give the caller a complete picture
        total_rows = conn.execute("SELECT COUNT(*) FROM hf_judgments").fetchone()[0]
        populated = conn.execute(
            "SELECT COUNT(*) FROM hf_judgments WHERE facts_json IS NOT NULL AND facts_json != ''"
        ).fetchone()[0]

        return {
            "ok": True,
            "processed": processed,
            "with_facts": with_facts,
            "elapsed_seconds": round(elapsed, 1),
            "docs_per_sec": round(processed / elapsed, 1) if elapsed > 0 else None,
            "redo": redo,
            "column_added": column_added,
            "corpus_after": {
                "total_rows": total_rows,
                "facts_populated": populated,
                "facts_pct": round(100.0 * populated / total_rows, 1) if total_rows else 0,
            },
        }
    finally:
        conn.close()


@router.post("/import_corpus_from_url",
             summary="Download a SQLite corpus from a URL onto the Railway Volume")
def admin_import_corpus(
    url: str = Query(..., description="HTTPS URL pointing at a kanoon_cache.sqlite file"),
    authorization: Optional[str] = Header(default=None),
    source_auth_token: Optional[str] = Query(default=None,
        description="Optional bearer token sent as Authorization header when fetching `url`. "
                    "Use for private HuggingFace dataset downloads."),
    expected_min_size_mb: int = Query(default=10, ge=1,
        description="Sanity check: refuse if download is smaller than this (probably an error page)"),
    expected_min_rows: int = Query(default=100, ge=1,
        description="Sanity check: refuse to swap if downloaded DB has < this many hf_judgments rows"),
):
    """Download a remote SQLite file (typically a kanoon_cache.sqlite full of
    harvested IL-TUR rows) and atomically swap it into the path the app
    reads from (config.KANOON_CACHE_PATH).

    The endpoint is HTTP-only because Railway Hobby doesn't expose a shell
    for `scp` or `railway run`. Stream the file, write to a tempfile, then
    rename — so a half-download never corrupts the live DB.

    Authentication: `Authorization: Bearer <ADMIN_TOKEN>`.

    Sanity gates:
      - Refuses URLs that don't look like SQLite (header magic check).
      - Refuses downloads smaller than `expected_min_size_mb` (1.3 GB of
        IL-TUR shouldn't shrink to a 5KB error page).
      - Refuses to swap if the downloaded DB has fewer than
        `expected_min_rows` rows in hf_judgments.

    curl example:

        curl -X POST -H "Authorization: Bearer $ADMIN_TOKEN" \\
             "https://headnote.in/admin/import_corpus_from_url?url=https://example.com/kanoon_cache.sqlite"

    Use a public URL (HuggingFace dataset, GitHub release, S3, R2).
    The file is downloaded by Railway's egress so the URL must be
    reachable from the Railway data center.
    """
    _require_admin(authorization)

    import os as _os
    import shutil as _shutil
    import sqlite3 as _sqlite3
    import tempfile as _tempfile
    import time as _time
    import urllib.request as _urlreq
    from headnote.config import KANOON_CACHE_PATH as _DB_PATH

    db_path = config.KANOON_CACHE_PATH
    target_dir = _os.path.dirname(str(db_path)) or "."
    _os.makedirs(target_dir, exist_ok=True)

    # Write to a tempfile in the SAME directory as the target so the final
    # os.replace is atomic (cross-filesystem moves can't be atomic).
    fd, tmp_path = _tempfile.mkstemp(prefix="kanoon_cache_inbound_", suffix=".sqlite",
                                     dir=target_dir)
    _os.close(fd)

    t_start = _time.monotonic()
    bytes_downloaded = 0

    try:
        # Stream download. urllib's default chunk size is fine; we use a
        # 1MB buffer to minimise syscall overhead.
        req_headers = {"User-Agent": "Headnote-Importer/1.0"}
        if source_auth_token:
            req_headers["Authorization"] = f"Bearer {source_auth_token}"
        req = _urlreq.Request(url, headers=req_headers)
        with _urlreq.urlopen(req, timeout=300) as resp, open(tmp_path, "wb") as out:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                out.write(chunk)
                bytes_downloaded += len(chunk)

        size_mb = bytes_downloaded / (1024 * 1024)
        if size_mb < expected_min_size_mb:
            return {
                "ok": False,
                "error": f"Downloaded only {size_mb:.2f} MB; expected >= {expected_min_size_mb} MB. "
                         f"URL probably returned an error page or wrong file.",
                "size_mb": round(size_mb, 2),
            }

        # SQLite magic number check: every SQLite file begins with the
        # ASCII string "SQLite format 3\000". Catches HTML / JSON / plain
        # text downloaded by mistake.
        with open(tmp_path, "rb") as f:
            magic = f.read(16)
        if magic != b"SQLite format 3\x00":
            return {
                "ok": False,
                "error": "Downloaded file is not a SQLite database (magic header mismatch).",
                "size_mb": round(size_mb, 2),
                "magic_bytes": magic.hex(),
            }

        # Open the downloaded DB and verify it has rows. We DON'T trust
        # the URL host; the operator owns this gate.
        try:
            inbound = _sqlite3.connect(tmp_path, timeout=15)
            inbound_rows = inbound.execute(
                "SELECT COUNT(*) FROM hf_judgments"
            ).fetchone()[0]
            inbound.close()
        except _sqlite3.OperationalError as e:
            return {
                "ok": False,
                "error": f"Downloaded SQLite has no hf_judgments table: {e}",
                "size_mb": round(size_mb, 2),
            }

        if inbound_rows < expected_min_rows:
            return {
                "ok": False,
                "error": f"Downloaded DB has only {inbound_rows} hf_judgments rows; "
                         f"expected >= {expected_min_rows}.",
                "inbound_rows": inbound_rows,
            }

        # Backup the existing DB (if any) before the swap. We rename rather
        # than delete so the operator can roll back manually.
        backup_path = str(db_path) + ".bak"
        if _os.path.exists(str(db_path)):
            try:
                _shutil.move(str(db_path), backup_path)
                backed_up = True
            except OSError as e:
                # If we can't move, the original might be locked by SQLite
                # connections. Best-effort: try a copy + truncate.
                _shutil.copyfile(str(db_path), backup_path)
                backed_up = True
        else:
            backed_up = False

        # Atomic move into place. os.replace is atomic on POSIX when both
        # paths are on the same filesystem (we ensured this with mkstemp
        # dir=target_dir above).
        _os.replace(tmp_path, str(db_path))

        elapsed = _time.monotonic() - t_start
        return {
            "ok": True,
            "url": url,
            "db_path": str(db_path),
            "size_mb": round(size_mb, 2),
            "inbound_rows": inbound_rows,
            "elapsed_seconds": round(elapsed, 1),
            "throughput_mb_per_sec": round(size_mb / elapsed, 2) if elapsed > 0 else None,
            "backed_up": backed_up,
            "backup_path": backup_path if backed_up else None,
            "next_step": "Hit /api/health to confirm hf_corpus.total matches inbound_rows.",
        }
    except Exception as e:
        # Cleanup tempfile on any error
        if _os.path.exists(tmp_path):
            try:
                _os.remove(tmp_path)
            except OSError:
                pass
        return {
            "ok": False,
            "error": f"Import failed: {type(e).__name__}: {e}",
            "bytes_downloaded": bytes_downloaded,
        }


# ===================================================================== #
# Access-grants: founder / partner whitelist management from the UI.    #
# ===================================================================== #

@router.get("/access-grants", summary="List founder + partner access grants")
def admin_list_grants(authorization: Optional[str] = Header(default=None)):
    """Returns all access grants: hardcoded config entries (read-only,
    source='config') AND DB-stored grants (source='db', deletable)."""
    _require_admin(authorization)
    from headnote.entitlements.grants import list_grants, list_hardcoded
    return {"grants": list_hardcoded() + list_grants()}


@router.post("/access-grants", summary="Grant founder or partner access")
def admin_add_grant(
    payload: dict,
    authorization: Optional[str] = Header(default=None),
):
    """Body: {"email": "...", "role": "founder"|"partner", "notes": "..."}.
    Refuses if the email is already in the hardcoded config (root tier)."""
    _require_admin(authorization)
    from headnote.entitlements.grants import add_grant
    email = (payload or {}).get("email", "")
    role  = (payload or {}).get("role", "")
    notes = (payload or {}).get("notes", "") or ""
    try:
        row = add_grant(email, role, notes=notes, granted_by="admin")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True, "grant": row}


@router.post("/access/invite", summary="Grant access + send invite email in one shot")
def admin_grant_and_invite(
    payload: dict,
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """One-shot: add a row to access_grants AND send a tailored invite email.

    Body
    ----
    {
      "email": "lawyer@example.com",      # required
      "name":  "Adv. Aditya Shinde",      # optional, used in salutation
      "role":  "monthly",                 # monthly | yearly | founder | partner
      "note":  "Comped 1 month — saw your tweet about Headnote",  # optional
    }

    Idempotent on email: re-calling overwrites the existing grant row and
    re-sends the invite. Refuses to grant a role to an email already in the
    hardcoded config tier (FOUNDER_EMAILS / PARTNER_EMAILS) — those are
    managed via headnote/config.py and shouldn't be DB-shadowed.

    Returns: {"granted": {...row...}, "email_sent": bool}.

    Example
    -------
    curl -X POST https://headnote.in/admin/access/invite \\
         -H "Authorization: Bearer $ADMIN_TOKEN" \\
         -H "Content-Type: application/json" \\
         -d '{"email":"adv.adityashinde10@gmail.com","name":"Aditya Shinde","role":"monthly","note":"Welcome to Headnote!"}'
    """
    _require_admin(authorization)
    email = (payload or {}).get("email", "").strip().lower()
    name  = (payload or {}).get("name", "") or ""
    role  = (payload or {}).get("role", "monthly").strip().lower()
    note  = (payload or {}).get("note", "") or ""

    if not email or "@" not in email:
        raise HTTPException(400, "email must be a valid address")
    if role not in ("monthly", "yearly", "founder", "partner"):
        raise HTTPException(400, "role must be monthly | yearly | founder | partner")

    from headnote.entitlements.grants import add_grant
    from headnote.email import send_access_invite

    try:
        row = add_grant(email, role, notes=note, granted_by="admin_invite")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    email_sent = send_access_invite(
        to_email=email, name=name, role=role, note=note,
    )
    return {"granted": row, "email_sent": email_sent}


@router.delete("/access-grants/{email}", summary="Revoke a DB-stored grant")
def admin_remove_grant(
    email: str,
    authorization: Optional[str] = Header(default=None),
):
    """Removes the DB grant for `email`. Hardcoded config entries are NOT
    removable from here — edit headnote/config.py for those."""
    _require_admin(authorization)
    from headnote.entitlements.grants import remove_grant
    ok = remove_grant(email)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail=f"No DB-stored grant found for {email!r} "
                   "(hardcoded entries cannot be removed via this API)",
        )
    return {"ok": True}


@router.get("/cost-dashboard", summary="HTML dashboard rendering telemetry charts",
            include_in_schema=False)
def admin_cost_dashboard():
    """Serve the cost dashboard HTML page.

    The page shell itself is unauthenticated — it asks for the
    ADMIN_TOKEN in-browser on first load, stores it in localStorage,
    and uses it as a Bearer header when calling /admin/telemetry.
    The token is the actual access control; the HTML is inert without it.

    Open in browser: https://<your-deploy>/admin/cost-dashboard
    """
    return FileResponse(config.STATIC_DIR / "admin-dashboard.html")


# ---------------------------------------------------------------------------
# Personal-assist queue — the backend workspace for "Not satisfied? our team
# will help" requests. Lawyers fire these from /api/assist/*; the founder works
# them here: see the open queries, WhatsApp/email the lawyer the case-law, then
# mark the request answered with a note of what was sent.
# ---------------------------------------------------------------------------

@router.get("/assist/requests", summary="List personal-assist requests (the lawyer help queue)")
def admin_list_assist_requests(
    authorization: Optional[str] = Header(default=None),
    status_filter: str = Query(
        default="open", alias="status", pattern="^(open|answered|closed|all)$",
        description="Filter by status, or 'all'. Defaults to the open queue.",
    ),
    limit: int = Query(default=100, ge=1, le=500),
):
    """Return assist requests newest-first. Authentication: Bearer ADMIN_TOKEN."""
    _require_admin(authorization)
    from headnote.entitlements import _supabase

    params = {"select": "*", "order": "created_at.desc", "limit": str(limit)}
    if status_filter != "all":
        params["status"] = f"eq.{status_filter}"
    rows = _supabase.select("assist_requests", params=params)
    return {"requests": rows, "count": len(rows), "status": status_filter}


class _ResolveAssistBody(BaseModel):
    status: str = Field(
        default="answered", pattern="^(answered|closed|open)$",
        description="answered = case-law delivered; closed = dismissed; open = reopen.",
    )
    note: Optional[str] = Field(
        default=None, max_length=4000,
        description="What case-law / notes you delivered, logged on the record.",
    )


@router.post("/assist/requests/{request_id}/resolve",
             summary="Mark an assist request answered/closed (logs the delivered note)")
def admin_resolve_assist_request(
    request_id: int,
    body: _ResolveAssistBody,
    authorization: Optional[str] = Header(default=None),
):
    """Move a request along its lifecycle and log what was sent.

    answered -> stamps answered_at/answered_by and stores `note`.
    Authentication: Bearer ADMIN_TOKEN.
    """
    _require_admin(authorization)
    from datetime import datetime, timezone
    from headnote.entitlements import _supabase

    now_iso = datetime.now(timezone.utc).isoformat()
    payload: dict = {"status": body.status, "updated_at": now_iso}
    if body.status == "answered":
        payload["answered_at"] = now_iso
        payload["answered_by"] = "admin"
    elif body.status == "open":
        # Reopening clears the resolution stamps so the queue reads cleanly.
        payload["answered_at"] = None
        payload["answered_by"] = None
    if body.note is not None:
        payload["answer_note"] = body.note.strip() or None

    rows = _supabase.update("assist_requests", payload, params={"id": f"eq.{request_id}"})
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(f"No assist request id={request_id} updated "
                    "(unknown id, or Supabase not configured on this deploy)."),
        )
    return {"ok": True, "request": rows[0]}


@router.get("/assist", summary="HTML queue for personal-assist requests",
            include_in_schema=False)
def admin_assist_page():
    """Serve the assist-queue HTML page.

    Same auth model as the cost dashboard: the shell is inert and asks for the
    ADMIN_TOKEN in-browser (stored in localStorage, shared with the cost
    dashboard), then calls /admin/assist/* with it as a Bearer header.

    Open in browser: https://<your-deploy>/admin/assist
    """
    return FileResponse(config.STATIC_DIR / "admin-assist.html")


# ---------------------------------------------------------------- cron
# Endpoints meant to be invoked by an external scheduler (Railway cron job,
# GitHub Actions, cron-job.org). All bearer-gated; no user JWT required.

@router.post("/cron/send-renewal-nudges",
             summary="Send the 3-days-before-expiry renewal email (cron)")
def cron_send_renewal_nudges(
    authorization: Optional[str] = Header(default=None),
    window_min: int = Query(2, ge=0, le=14, description="Lookahead window start (days from now)"),
    window_max: int = Query(4, ge=0, le=14, description="Lookahead window end (days from now)"),
    dry_run: bool = Query(False, description="Return candidates without sending"),
) -> dict:
    """Wire this to a daily cron with the ADMIN_TOKEN.

    Per-cycle idempotency lives in subscriptions.renewal_nudge_sent_for_period_end —
    safe to invoke multiple times a day; only fires once per billing cycle.

    Example (daily at 09:30 IST = 04:00 UTC):
      curl -X POST https://headnote.in/admin/cron/send-renewal-nudges \\
           -H "Authorization: Bearer $ADMIN_TOKEN"
    """
    _require_admin(authorization)
    if window_min > window_max:
        raise HTTPException(400, "window_min must be <= window_max")
    from headnote.email import send_due_renewal_nudges
    return send_due_renewal_nudges(
        window_days_min=window_min,
        window_days_max=window_max,
        dry_run=dry_run,
    )


# ---------------------------------------------------------------- email diagnostics
# "Are signup / subscription emails actually working in production?"
# These two endpoints answer that without needing to fake a signup or read
# Railway logs.

@router.get("/email/status",
            summary="Email diagnostics — is Resend configured + headnote.in verified?")
def email_status(authorization: Optional[str] = Header(default=None)) -> dict:
    """Returns the live state of the transactional email pipe.

    Reports:
      - resend_api_key_present  (bool) + last 4 chars (sanity only, not the key)
      - from_email              (the From: header used by every send)
      - resend_api_reachable    (bool) — did a GET /domains succeed?
      - domains[]               — Resend's view of our domains + verification state
      - headnote_in_verified    (bool) — convenience flag for the headnote.in domain

    If `headnote_in_verified` is false, ALL transactional emails are silently
    rejected by Resend at send time. That is the #1 reason users don't receive
    welcome / receipt mails after deploy.
    """
    import os as _os
    _require_admin(authorization)

    api_key = _os.environ.get("RESEND_API_KEY", "")
    from_email = _os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")

    out: dict = {
        "resend_api_key_present": bool(api_key),
        "resend_api_key_last4":   api_key[-4:] if api_key else "",
        "from_email":             from_email,
        "resend_api_reachable":   False,
        "domains":                [],
        "headnote_in_verified":   False,
        "error":                  None,
    }

    if not api_key:
        out["error"] = "RESEND_API_KEY not set — every send is a logged no-op."
        return out

    import httpx as _httpx
    try:
        r = _httpx.get(
            "https://api.resend.com/domains",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=6.0,
        )
        out["resend_api_reachable"] = True
        if r.status_code != 200:
            out["error"] = f"Resend /domains returned {r.status_code}: {r.text[:200]}"
            return out
        body = r.json() or {}
        domains = body.get("data") or []
        # Normalize to a small public view
        out["domains"] = [
            {
                "name":    d.get("name"),
                "status":  d.get("status"),   # not_started | pending | verified | failure | temporary_failure
                "region":  d.get("region"),
                "created": d.get("created_at"),
            }
            for d in domains
        ]
        for d in domains:
            if (d.get("name") or "").lower() == "headnote.in" and (d.get("status") or "").lower() == "verified":
                out["headnote_in_verified"] = True
                break
        if not out["headnote_in_verified"]:
            out["error"] = (
                "headnote.in is NOT verified in Resend. Sends from "
                "hello@headnote.in will be rejected. Add the SPF/DKIM/DMARC "
                "DNS records shown in the Resend dashboard."
            )
    except _httpx.HTTPError as e:
        out["error"] = f"Could not reach Resend API: {e}"
    return out


@router.post("/email/test-send",
             summary="Fire a real test email through the production code path")
def email_test_send(
    authorization: Optional[str] = Header(default=None),
    to: str = Query(..., description="Recipient email — your own inbox for verification."),
    template: str = Query("welcome",
                          description="welcome | subscription | renewal — which template to render."),
    name: str = Query("Test User", description="Display name to render in the template."),
) -> dict:
    """Sends a REAL email through the same code path production uses. The only
    thing this skips is the idempotency check (welcome_sent flag / payment_ref
    dedupe / renewal_nudge column) so you can re-fire safely.

    Use this to confirm:
      1. Resend is reachable from this deploy
      2. headnote.in is verified (otherwise: 'Email address not allowed')
      3. Templates render without errors
      4. The email lands in your inbox (not spam!)

    Example:
      curl -X POST "https://headnote.in/admin/email/test-send?to=you@gmail.com&template=welcome" \\
           -H "Authorization: Bearer $ADMIN_TOKEN"
    """
    _require_admin(authorization)
    if "@" not in to:
        raise HTTPException(400, "to= must be a valid email address")
    template = template.lower().strip()
    if template not in ("welcome", "subscription", "renewal"):
        raise HTTPException(400, "template must be one of: welcome | subscription | renewal")

    from headnote.email import (
        send_welcome,
        send_subscription_confirmation,
    )
    from headnote.email.renewal import _send_one as _send_renewal_one

    if template == "welcome":
        ok = send_welcome(to_email=to, name=name)
        return {"ok": ok, "template": "welcome", "to": to}

    if template == "subscription":
        ok = send_subscription_confirmation(
            to_email=to,
            name=name,
            plan="monthly",
            amount_inr=599,
            order_id="test_order_diagnostic",
            # period_end ~30 days out so the receipt renders a real date
            period_end_iso=__import__("datetime").datetime.utcnow().isoformat() + "Z",
        )
        return {"ok": ok, "template": "subscription", "to": to}

    # renewal
    ok = _send_renewal_one(
        to_email=to, name=name, plan="monthly",
        period_end_iso=(
            __import__("datetime").datetime.utcnow()
            + __import__("datetime").timedelta(days=3)
        ).isoformat() + "Z",
        days_remaining=3,
    )
    return {"ok": ok, "template": "renewal", "to": to}
