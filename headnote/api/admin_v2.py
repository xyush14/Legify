"""Admin v2: user/subscription management endpoints.

These supplement the bearer-token-guarded admin.py with user-facing admin
flows. Auth is dual-mode:
  - either Authorization: Bearer <ADMIN_TOKEN>  (legacy, ops scripts)
  - or a Supabase JWT for a user listed in public.admin_users (UI flow)

Endpoints:
  GET    /admin/v2/users                    List users + their subscription
  GET    /admin/v2/users/{user_id}          One user's full state
  POST   /admin/v2/users/{user_id}/grant    Manually upgrade a user to a plan
  POST   /admin/v2/users/{user_id}/cancel   Cancel a user's subscription
  GET    /admin/v2/usage                    Aggregate usage stats (7/30/90 days)
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel

from headnote import config
from headnote.entitlements import _supabase
from headnote.entitlements.auth import optional_user
from headnote.entitlements.plans import PLANS
from headnote.entitlements.state import get_user_state
from headnote.entitlements.subscription import change_plan, cancel_subscription, is_admin


router = APIRouter(prefix="/admin/v2", tags=["admin"])


# ---------------------------------------------------------------- dual auth

def _admin_guard(
    authorization: Optional[str] = Header(default=None),
    user=Depends(optional_user),
) -> str:
    """Allow either Bearer ADMIN_TOKEN OR a JWT for an admin_users row.

    Returns the actor id (admin user id, or 'ops' for token-based access).
    """
    # Bearer ADMIN_TOKEN path
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(None, 1)[1].strip()
        if config.ADMIN_TOKEN and token == config.ADMIN_TOKEN:
            return "ops"
    # JWT path
    if user and is_admin(user.id):
        return user.id
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Admin access required.",
    )


# ---------------------------------------------------------------- models

class GrantRequest(BaseModel):
    plan: str
    duration_days: Optional[int] = None
    note: Optional[str] = None


# ---------------------------------------------------------------- endpoints

@router.get("/users", summary="List users + their subscriptions")
def list_users(
    actor: str = Depends(_admin_guard),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    plan: Optional[str] = Query(None, description="Filter to one plan"),
) -> dict:
    """Returns a paginated list of users with subscription state and recent usage.

    Combines auth.users (via Supabase admin API) with subscriptions table.
    """
    params: dict[str, str] = {
        "select":  "*",
        "order":   "updated_at.desc",
        "limit":   str(limit),
        "offset":  str(offset),
    }
    if plan:
        params["plan"] = f"eq.{plan}"

    subs = _supabase.select("subscriptions", params=params)
    return {"users": subs, "count": len(subs)}


@router.get("/users/{user_id}", summary="Full state for one user")
def get_user(user_id: str, actor: str = Depends(_admin_guard)) -> dict:
    state = get_user_state(user_id)

    # Last 50 events for context
    events = _supabase.select(
        "usage_events",
        params={
            "user_id": f"eq.{user_id}",
            "select":  "*",
            "order":   "created_at.desc",
            "limit":   "50",
        },
    )
    state["recent_events"] = events
    return state


@router.post("/users/{user_id}/grant", summary="Manually upgrade a user")
def grant_plan(
    user_id: str,
    body: GrantRequest,
    actor: str = Depends(_admin_guard),
) -> dict:
    if body.plan not in PLANS:
        raise HTTPException(400, f"Unknown plan: {body.plan}")
    updated = change_plan(
        user_id,
        body.plan,
        duration_days=body.duration_days,
        payment_provider="manual",
        payment_ref=f"granted_by:{actor}",
        granted_by_admin=True,
    )
    return {"ok": True, "subscription": updated, "granted_by": actor}


@router.post("/users/{user_id}/cancel", summary="Cancel a user's subscription")
def cancel_user(user_id: str, actor: str = Depends(_admin_guard)) -> dict:
    sub = cancel_subscription(user_id)
    return {"ok": True, "subscription": sub, "cancelled_by": actor}


@router.get("/usage", summary="Aggregate usage stats")
def aggregate_usage(
    actor: str = Depends(_admin_guard),
    days: int = Query(7, ge=1, le=90),
) -> dict:
    """Returns per-feature totals + per-user top consumers."""
    from datetime import datetime, timezone, timedelta

    since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
    events = _supabase.select(
        "usage_events",
        params={
            "select":     "user_id,feature,cost_paise,model",
            "created_at": f"gte.{since}",
            "limit":      "5000",
        },
    )

    by_feature: dict[str, dict] = {}
    by_user: dict[str, int] = {}
    total_paise = 0
    for ev in events:
        f = ev.get("feature", "?")
        c = int(ev.get("cost_paise", 0) or 0)
        total_paise += c
        bf = by_feature.setdefault(f, {"calls": 0, "cost_paise": 0})
        bf["calls"] += 1
        bf["cost_paise"] += c
        if ev.get("user_id"):
            by_user[ev["user_id"]] = by_user.get(ev["user_id"], 0) + c

    top_users = sorted(by_user.items(), key=lambda x: -x[1])[:20]

    return {
        "window_days":     days,
        "total_calls":     len(events),
        "total_cost_inr":  round(total_paise / 100, 2),
        "by_feature":      by_feature,
        "top_users":       [{"user_id": u, "cost_paise": c} for u, c in top_users],
    }


# ---------------------------------------------------------------- corpus mgmt
# Founder-only endpoints to trigger the long-running corpus pipeline from
# anywhere (phone, laptop). Scripts run as background subprocesses; output
# goes to Railway logs. Both scripts are idempotent — safe to re-run.

import logging as _logging
import os as _corpus_os
import subprocess as _subprocess
import threading as _threading
import time as _time
from pathlib import Path as _Path

_corpus_log = _logging.getLogger(__name__)

# In-memory job registry. Cleared on restart — Railway logs are the source
# of truth for full output. This is just for the status endpoint.
_CORPUS_JOBS: dict[str, dict] = {}


def _run_corpus_script(
    job_id: str,
    cmd: list[str],
    *,
    extra_requirements: Optional[str] = None,
) -> None:
    """Spawn a long-running script in a thread, capture summary to _CORPUS_JOBS.

    If `extra_requirements` is set (e.g. 'requirements-harvest.txt'), pip
    installs those deps first. Used for harvest which needs `datasets`+`tqdm`
    (~200MB) that we don't ship in the base image.
    """
    repo_root = _Path(__file__).resolve().parent.parent.parent
    job = _CORPUS_JOBS[job_id]
    job["started_at"] = _time.time()
    job["status"] = "running"
    job["cmd"] = " ".join(cmd)
    tail: list[str] = []

    def _stream_proc(proc) -> int:
        """Read stdout line by line into the rolling tail."""
        for line in proc.stdout:  # type: ignore[union-attr]
            _corpus_log.info("[corpus:%s] %s", job_id, line.rstrip())
            tail.append(line.rstrip())
            if len(tail) > 50:
                tail.pop(0)
            job["last_lines"] = tail[-30:]
        proc.wait()
        return proc.returncode

    try:
        # Phase 1: install extra deps if needed (30-90s typical)
        if extra_requirements:
            req_path = repo_root / extra_requirements
            if req_path.exists():
                job["phase"] = f"installing {extra_requirements}"
                tail.append(f"$ pip install -r {extra_requirements}")
                job["last_lines"] = tail[-30:]
                pip_proc = _subprocess.Popen(
                    ["pip", "install", "--no-cache-dir", "-r", str(req_path)],
                    cwd=str(repo_root),
                    stdout=_subprocess.PIPE,
                    stderr=_subprocess.STDOUT,
                    text=True,
                    bufsize=1,
                )
                rc = _stream_proc(pip_proc)
                if rc != 0:
                    job["status"] = "failed"
                    job["return_code"] = rc
                    job["error"] = "pip install of extra requirements failed"
                    return
                tail.append("$ pip install complete — starting script")
                job["last_lines"] = tail[-30:]
            else:
                tail.append(f"WARNING: {extra_requirements} not found, skipping pre-install")
                job["last_lines"] = tail[-30:]

        # Phase 2: run the actual script
        job["phase"] = "running script"
        proc = _subprocess.Popen(
            cmd,
            cwd=str(repo_root),
            stdout=_subprocess.PIPE,
            stderr=_subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        job["pid"] = proc.pid
        rc = _stream_proc(proc)
        job["return_code"] = rc
        job["status"] = "completed" if rc == 0 else "failed"
    except Exception as e:
        job["status"] = "errored"
        job["error"] = str(e)[:500]
    finally:
        job["finished_at"] = _time.time()
        job["elapsed_seconds"] = round(job["finished_at"] - job["started_at"], 1)


@router.post("/corpus/harvest", summary="Trigger HF corpus harvest (founder-only, runs in background)")
def admin_trigger_harvest(
    subsets: str = Query(default="cjpe,summ",
                         description="Comma-separated IL-TUR subsets: cjpe, summ, bail, lsi, pcr"),
    limit: Optional[int] = Query(default=None,
                                 description="Cap rows per subset (testing only)"),
    actor: str = Depends(_admin_guard),
) -> dict:
    """Spawn `python scripts/harvest_hf_corpus.py --subsets <s1> <s2>` in the
    background. Returns immediately with a job_id; poll /admin/v2/corpus/status
    or watch Railway logs for progress. Idempotent — re-runs skip rows already
    in hf_judgments."""
    subset_list = [s.strip() for s in subsets.split(",") if s.strip()]
    valid = {"cjpe", "summ", "bail", "lsi", "pcr"}
    if not all(s in valid for s in subset_list):
        raise HTTPException(400, f"Invalid subsets. Valid: {sorted(valid)}")

    job_id = f"harvest-{int(_time.time())}"
    cmd = ["python", "scripts/harvest_hf_corpus.py", "--subsets", *subset_list]
    if limit is not None:
        cmd += ["--limit", str(int(limit))]

    _CORPUS_JOBS[job_id] = {"job_id": job_id, "kind": "harvest", "status": "queued"}
    # `datasets` + `tqdm` are baked into the base image (requirements.txt)
    # so no runtime pip install is needed — eliminates the Railway-restart
    # race where the harvest job ID would be lost mid-install.
    t = _threading.Thread(
        target=_run_corpus_script,
        args=(job_id, cmd),
        daemon=True,
    )
    t.start()

    return {
        "ok": True,
        "job_id": job_id,
        "command": " ".join(cmd),
        "note": "Running in background. Poll GET /admin/v2/corpus/status/" + job_id,
        "estimated_minutes": 30 if "bail" not in subset_list else 90,
    }


@router.post("/corpus/backfill-embeddings", summary="Trigger embedding backfill (founder-only)")
def admin_trigger_backfill(
    skip_ik: bool = Query(default=True,
                          description="Skip IK cases (only embed HF corpus). Default: True"),
    actor: str = Depends(_admin_guard),
) -> dict:
    """Spawn `python scripts/backfill_embeddings.py --skip-ik` in the
    background. Run AFTER /corpus/harvest has finished. Idempotent — only
    embeds rows not already in paragraph_embeddings table."""
    job_id = f"backfill-{int(_time.time())}"
    cmd = ["python", "scripts/backfill_embeddings.py"]
    if skip_ik:
        cmd.append("--skip-ik")

    _CORPUS_JOBS[job_id] = {"job_id": job_id, "kind": "backfill", "status": "queued"}
    t = _threading.Thread(target=_run_corpus_script, args=(job_id, cmd), daemon=True)
    t.start()

    return {
        "ok": True,
        "job_id": job_id,
        "command": " ".join(cmd),
        "note": "Running in background. Poll GET /admin/v2/corpus/status/" + job_id,
        "estimated_minutes": 20,
    }


@router.get("/corpus/status", summary="List all corpus jobs in this process")
def admin_corpus_status_all(actor: str = Depends(_admin_guard)) -> dict:
    return {
        "jobs": list(_CORPUS_JOBS.values()),
        "active_count": sum(1 for j in _CORPUS_JOBS.values() if j.get("status") == "running"),
    }


@router.get("/corpus/status/{job_id}", summary="Status of a single corpus job")
def admin_corpus_status_one(
    job_id: str,
    actor: str = Depends(_admin_guard),
) -> dict:
    job = _CORPUS_JOBS.get(job_id)
    if not job:
        raise HTTPException(404, f"No such job: {job_id} (lost on Railway restart — check logs)")
    return job


@router.get("/corpus/totals", summary="Current corpus + embedding totals (no auth needed but logged)")
def admin_corpus_totals(actor: str = Depends(_admin_guard)) -> dict:
    """Quick health check: how many cases imported, how many embedded."""
    try:
        from headnote.retrieval.hf_corpus import corpus_stats
        hf = corpus_stats()
    except Exception as e:
        hf = {"error": str(e)[:200]}
    try:
        from headnote.retrieval.embeddings import EmbeddingIndex
        emb = EmbeddingIndex().stats()
    except Exception as e:
        emb = {"error": str(e)[:200]}
    return {"hf_corpus": hf, "embeddings": emb}
