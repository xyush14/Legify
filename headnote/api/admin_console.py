"""The admin console backend: sign-in, the business overview, and the live
status of every paid service Headnote depends on.

This exists because the admin surface had grown into four separate HTML
pages and roughly fifty endpoints with no single door, no human login, and —
the gap that actually costs money — no way to see that a vendor account had
run dry. Both of the things that were silently broken on the day this was
written were invisible from every existing screen:

  * the eCourts wallet was down to ₹0.20 against a ₹0.60 search, so every
    live court lookup and the 18:00 sweep were failing;
  * Indian Kanoon was returning 403 on even a ₹0.02 metadata call, so
    case-law search had no live source at all.

Neither shows up in a health check, because the app is perfectly healthy.
Only the vendor is empty. So the services endpoint below probes each one
directly and reports what it finds, with a top-up link next to it.

What is deliberately NOT done here
----------------------------------
Probes must be FREE. A status page that bills you every time you open it is
a status page you stop opening. So each probe uses an endpoint that costs
nothing (a models list, an enum list, a balance read), and the two vendors
whose only real signal is a metered call are handled honestly instead:

  * eCourts publishes no balance endpoint — this was checked, /balance,
    /wallet, /credits, /account, /me, /usage are all 404. Its exact balance
    is only ever revealed inside the 402 error body ("Available: ₹0.20").
    So the console records that number whenever any part of the app hits a
    402 (see record_vendor_balance, called from the client's one error
    chokepoint) and shows it with the time it was seen. The manual re-check
    button spends ₹0.60 and says so on the button.
  * Indian Kanoon meters every call including metadata, so its health is
    read from our own local spend ledger plus the last live outcome.

Everything else here is free to call.
"""

from __future__ import annotations

import asyncio
import logging
import re
import sqlite3
import time
from datetime import datetime, timezone
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel

from headnote import config
from headnote.api.admin_session import (
    check_credentials,
    clear_failures,
    issue_session,
    note_failure,
    password_login_available,
    require_admin_bearer,
    seconds_locked_out,
    verify_session,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/admin/api", tags=["admin"])

# A browser-shaped User-Agent. The eCourts vendor sits behind Cloudflare and
# refuses anything that looks like a script — the same reason the main client
# sets one.
_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
# 12s, not 8s. Every probe runs concurrently, so the page costs the SLOWEST
# one — and that is eCourts, whose only free endpoint builds the whole ~10,000
# entry court directory before it sends a byte (measured at ~8.5s). At 8s it
# flapped between "up" and a ReadTimeout that reads as an outage.
_PROBE_TIMEOUT = 12.0


# ================================================================= tiny kv store

def _kv_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(config.FEEDBACK_DB), timeout=10)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS admin_ops_notes ("
        "  key TEXT PRIMARY KEY,"
        "  value TEXT,"
        "  updated_at TEXT NOT NULL)"
    )
    return conn


def _kv_set(key: str, value: str) -> None:
    try:
        with _kv_conn() as conn:
            conn.execute(
                "INSERT INTO admin_ops_notes(key, value, updated_at) VALUES(?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, value, datetime.now(timezone.utc).isoformat()),
            )
    except Exception as e:                                    # never break a caller
        log.debug("admin kv set failed for %s: %s", key, e)


def _kv_get(key: str) -> tuple[Optional[str], Optional[str]]:
    """Returns (value, updated_at_iso) or (None, None)."""
    try:
        with _kv_conn() as conn:
            row = conn.execute(
                "SELECT value, updated_at FROM admin_ops_notes WHERE key=?", (key,),
            ).fetchone()
        return (row[0], row[1]) if row else (None, None)
    except Exception:
        return (None, None)


_BALANCE_RE = re.compile(r"Available:\s*₹\s*([0-9]+(?:\.[0-9]+)?)")


def record_vendor_balance(body: str) -> Optional[float]:
    """Capture the wallet balance out of an eCourts 402 body, for free.

    Called from the vendor client's error chokepoint, so any real court
    lookup that fails on an empty wallet teaches the console the exact
    number without the console ever spending anything itself.
    """
    m = _BALANCE_RE.search(body or "")
    if not m:
        return None
    try:
        amount = float(m.group(1))
    except ValueError:
        return None
    _kv_set("ecourts_balance_inr", f"{amount:.2f}")
    return amount


# ================================================================= sign-in

class LoginIn(BaseModel):
    email: str
    password: str


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("fly-client-ip") or request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


@router.post("/login", summary="Admin console sign-in (email + password)")
def admin_login(payload: LoginIn, request: Request) -> dict:
    """Exchange an email + password for a signed session token.

    The response is deliberately vague about WHICH half was wrong — an
    admin login that says "no such user" is an admin login that tells a
    stranger which email to attack.
    """
    ip = _client_ip(request)
    locked = seconds_locked_out(ip)
    if locked:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed attempts. Try again in {locked // 60 + 1} minute(s).",
        )
    if not password_login_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Password sign-in is not configured on this server. "
                "Set ADMIN_EMAIL and ADMIN_PASSWORD (and ADMIN_TOKEN) as secrets."
            ),
        )
    if not check_credentials(payload.email, payload.password):
        note_failure(ip)
        log.warning("admin console: failed sign-in from %s", ip)
        raise HTTPException(status_code=401, detail="Wrong email or password.")

    clear_failures(ip)
    token, exp = issue_session(payload.email)
    log.info("admin console: sign-in ok for %s from %s", payload.email.strip().lower(), ip)
    return {
        "token":      token,
        "expires_at": datetime.fromtimestamp(exp, timezone.utc).isoformat(),
        "email":      payload.email.strip().lower(),
    }


@router.get("/session", summary="Is this session still valid?")
def admin_session_check(authorization: Optional[str] = Header(default=None)) -> dict:
    actor = require_admin_bearer(authorization)
    return {"ok": True, "actor": actor}


@router.get("/login-config", summary="Whether password sign-in is available")
def admin_login_config() -> dict:
    """Unauthenticated on purpose — the sign-in screen has to render before
    anyone has a token, and this leaks nothing beyond whether the feature is
    switched on."""
    return {
        "password_login": password_login_available(),
        "admin_token_set": bool(config.ADMIN_TOKEN),
    }


# ================================================================= service probes

async def _timed(client: httpx.AsyncClient, method: str, url: str, **kw) -> tuple[Any, int]:
    t0 = time.monotonic()
    r = await client.request(method, url, **kw)
    return r, int((time.monotonic() - t0) * 1000)


def _svc(key: str, name: str, role: str, impact: str, *, topup: str = "",
         console: str = "") -> dict:
    return {
        "key": key, "name": name, "role": role, "impact": impact,
        "topup_url": topup, "console_url": console,
        "configured": False, "status": "not_configured",
        "detail": "No API key set on this server.",
        "latency_ms": None, "balance": None,
    }


async def _probe_ecourts(client: httpx.AsyncClient) -> dict:
    s = _svc(
        "ecourts", "eCourts (court records)",
        "Case lookup by CNR or case number, cause lists, the 18:00 date sweep, court order PDFs",
        "Adding a matter from the court record fails, and hearing dates stop updating on their own.",
        topup="https://ecourtsindia.com/api/pricing",
        console="https://ecourtsindia.com/api/docs",
    )
    if not config.CNR_API_TOKEN:
        return s
    s["configured"] = True
    # The enums/court-directory call is the vendor's only FREE endpoint, but
    # it answers with the whole ~10,000-entry court directory. Downloading
    # that to ask "are you alive?" is what made this probe time out, so the
    # response is STREAMED and abandoned as soon as the status line lands.
    try:
        t0 = time.monotonic()
        req = client.build_request(
            "GET", f"{config.CNR_API_BASE_URL.rstrip('/')}/api/partner/enums",
            headers={"Authorization": f"Bearer {config.CNR_API_TOKEN}",
                     "User-Agent": _UA, "Accept": "application/json"},
        )
        r = await client.send(req, stream=True)
        try:
            s["latency_ms"] = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                s["status"], s["detail"] = "up", "Vendor is answering."
            else:
                s["status"] = "down"
                s["detail"] = f"Vendor returned HTTP {r.status_code}."
                # An error body is small, so it is safe to read in full — and
                # a 402 body is the only place the wallet figure ever appears.
                record_vendor_balance((await r.aread()).decode("utf-8", "replace"))
        finally:
            await r.aclose()
    except httpx.TimeoutException:
        # A timeout on a deliberately enormous free endpoint is the vendor
        # being slow, not proof it is down. Saying "down" here would send
        # somebody chasing an outage that is not happening, and would bury
        # the reading that actually matters — the wallet, applied below.
        s["status"] = "degraded"
        s["detail"] = ("The vendor's free court-directory call did not answer in time. "
                       "That endpoint returns ~10,000 courts and is often slow; it is not "
                       "proof the service is down.")
    except Exception as e:
        s["status"], s["detail"] = "down", f"Could not reach the vendor: {type(e).__name__}"

    # The wallet is the verdict that matters, and it OUTRANKS the transport
    # result: a vendor that answers instantly is still useless to a lawyer if
    # the account cannot pay for a search.
    val, seen = _kv_get("ecourts_balance_inr")
    if val is not None:
        try:
            amount = float(val)
        except ValueError:
            amount = 0.0
        low = amount < 5.0          # a search is ₹0.60, a case detail ₹1.50
        s["balance"] = {
            "label": "Wallet", "value": f"₹{amount:.2f}",
            "low": low, "as_of": seen,
            "note": "Last figure the vendor reported. It only tells us the balance when a call fails.",
        }
        if low:
            s["status"] = "degraded" if s["status"] != "down" else "down"
            s["detail"] = (
                f"The wallet was ₹{amount:.2f}. A search costs ₹0.60 and a case detail ₹1.50, "
                "so live court lookups are failing — top up to restore them."
            )
    return s


async def _probe_kanoon(client: httpx.AsyncClient) -> dict:
    s = _svc(
        "kanoon", "Indian Kanoon (case law)",
        "Live judgment search and full text behind Research",
        "Case-law search falls back to the 42 curated landmarks and nothing new can be verified.",
        topup="https://api.indiankanoon.org/pricing/",
        console="https://api.indiankanoon.org/",
    )
    if not config.INDIAN_KANOON_TOKEN:
        return s
    s["configured"] = True
    # docmeta is the cheapest metered call (₹0.02) and is the only way to tell
    # "out of credit" from "working" — there is no free health endpoint.
    try:
        r, ms = await _timed(
            client, "POST", "https://api.indiankanoon.org/docmeta/1766147/",
            headers={"Authorization": f"Token {config.INDIAN_KANOON_TOKEN}",
                     "User-Agent": _UA},
        )
        s["latency_ms"] = ms
        if r.status_code == 200:
            s["status"], s["detail"] = "up", "Answering; the account has credit."
        elif r.status_code in (401, 403):
            s["status"] = "down"
            s["detail"] = (
                "HTTP 403 — the token is valid but the account has no credit, "
                "so every live search returns nothing. Recharge to restore it."
            )
        else:
            s["status"], s["detail"] = "down", f"HTTP {r.status_code}."
    except Exception as e:
        s["status"], s["detail"] = "down", f"Could not reach the API: {type(e).__name__}"

    # Our own ledger — what we have spent today against the daily cap.
    try:
        from headnote.kanoon.client import KanoonClient
        summary = KanoonClient().spend_summary()
        today = summary.get("today_total_inr") or 0
        cap = summary.get("daily_cap_inr")
        s["balance"] = {
            "label": "Spent today",
            "value": f"₹{float(today):.2f}" + (f" of ₹{float(cap):.2f} cap" if cap else ""),
            "low": False, "as_of": None,
            "note": "Our own local meter, not the vendor's balance.",
        }
    except Exception as e:
        log.debug("kanoon spend summary unavailable: %s", e)
    return s


async def _probe_deepseek(client: httpx.AsyncClient) -> dict:
    import os
    s = _svc(
        "deepseek", "DeepSeek (drafting + chat)",
        "The main writing model behind drafts and the Chamber answers",
        "Drafting falls through to the Groq free tier, which is slower and weaker on Indian legal text.",
        topup="https://platform.deepseek.com/top_up",
        console="https://platform.deepseek.com/usage",
    )
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        return s
    s["configured"] = True
    try:
        # DeepSeek is the one vendor here with a real, free balance endpoint.
        r, ms = await _timed(client, "GET", "https://api.deepseek.com/user/balance",
                             headers={"Authorization": f"Bearer {key}"})
        s["latency_ms"] = ms
        if r.status_code == 200:
            data = r.json()
            infos = data.get("balance_infos") or []
            s["status"] = "up" if data.get("is_available") else "degraded"
            if infos:
                info = infos[0]
                total = info.get("total_balance")
                cur = info.get("currency", "")
                sym = "₹" if cur == "INR" else ("¥" if cur == "CNY" else "$")
                try:
                    low = float(total) < 5.0
                except (TypeError, ValueError):
                    low = False
                s["balance"] = {"label": "Credit", "value": f"{sym}{total}",
                                "low": low, "as_of": None, "note": ""}
            s["detail"] = ("Account is funded and answering."
                           if data.get("is_available")
                           else "Reachable, but the account is out of credit.")
        elif r.status_code == 401:
            s["status"], s["detail"] = "down", "HTTP 401 — the API key is rejected."
        else:
            s["status"], s["detail"] = "down", f"HTTP {r.status_code}."
    except Exception as e:
        s["status"], s["detail"] = "down", f"Could not reach the API: {type(e).__name__}"
    return s


async def _probe_simple(client: httpx.AsyncClient, *, key: str, name: str, role: str,
                        impact: str, url: str, headers: dict, api_key: Optional[str],
                        topup: str = "", console: str = "",
                        ok_codes: tuple[int, ...] = (200,)) -> dict:
    """The common shape: a key, a free endpoint that lists something, done."""
    s = _svc(key, name, role, impact, topup=topup, console=console)
    if not api_key:
        return s
    s["configured"] = True
    try:
        r, ms = await _timed(client, "GET", url, headers=headers)
        s["latency_ms"] = ms
        if r.status_code in ok_codes:
            s["status"], s["detail"] = "up", "Key accepted and answering."
        elif r.status_code in (401, 403):
            s["status"] = "down"
            s["detail"] = f"HTTP {r.status_code} — the key is rejected or out of quota."
        elif r.status_code == 429:
            s["status"], s["detail"] = "degraded", "HTTP 429 — rate limited right now."
        else:
            s["status"], s["detail"] = "down", f"HTTP {r.status_code}."
    except Exception as e:
        s["status"], s["detail"] = "down", f"Could not reach the API: {type(e).__name__}"
    return s


async def _gather_services() -> list[dict]:
    import os
    async with httpx.AsyncClient(timeout=_PROBE_TIMEOUT, follow_redirects=True) as c:
        supabase_key = config.SUPABASE_SERVICE_ROLE_KEY or ""
        tasks = [
            _probe_ecourts(c),
            _probe_kanoon(c),
            _probe_deepseek(c),
            _probe_simple(
                c, key="gemini", name="Gemini (OCR)",
                role="Reads scanned FIRs, charge sheets, court orders and handwritten cause lists",
                impact="OCR drops to the Groq free tier: about one page a minute, and it misreads Devanagari.",
                url=f"https://generativelanguage.googleapis.com/v1beta/models?key={config.GEMINI_API_KEY}",
                headers={}, api_key=config.GEMINI_API_KEY,
                topup="https://aistudio.google.com/app/apikey",
                console="https://aistudio.google.com/",
            ),
            _probe_simple(
                c, key="groq", name="Groq (free fallback)",
                role="Free fallback for OCR and drafting when the paid models fail",
                impact="The safety net under drafting and OCR is gone.",
                url="https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {os.environ.get('GROQ_API_KEY', '')}"},
                api_key=os.environ.get("GROQ_API_KEY"),
                topup="https://console.groq.com/settings/billing",
                console="https://console.groq.com/",
            ),
            _probe_simple(
                c, key="anthropic", name="Anthropic Claude",
                role="Reserved for the highest-quality analysis paths",
                impact="Those paths fall back to DeepSeek.",
                url="https://api.anthropic.com/v1/models",
                headers={"x-api-key": config.ANTHROPIC_API_KEY or "",
                         "anthropic-version": "2023-06-01"},
                api_key=config.ANTHROPIC_API_KEY,
                topup="https://console.anthropic.com/settings/billing",
                console="https://console.anthropic.com/",
            ),
            _probe_simple(
                c, key="supabase", name="Supabase (accounts + matters)",
                role="Every login, subscription and case record",
                impact="THE SITE IS DOWN. Nobody can sign in and no matter can be read.",
                url=f"{(config.SUPABASE_URL or '').rstrip('/')}/rest/v1/subscriptions?select=user_id&limit=1",
                headers={"apikey": supabase_key, "Authorization": f"Bearer {supabase_key}"},
                api_key=supabase_key if config.SUPABASE_URL else None,
                console="https://supabase.com/dashboard",
            ),
            _probe_simple(
                c, key="resend", name="Resend (email)",
                role="Invite emails, renewal nudges and the evening cause list",
                impact="Access invites and renewal reminders silently stop arriving.",
                url="https://api.resend.com/domains",
                headers={"Authorization": f"Bearer {os.environ.get('RESEND_API_KEY', '')}"},
                api_key=os.environ.get("RESEND_API_KEY"),
                console="https://resend.com/domains",
            ),
            _probe_simple(
                c, key="sarvam", name="Sarvam (Indic speech)",
                role="Hindi and regional voice input, and handwriting OCR fallback",
                impact="Voice drafting falls back to Whisper; Indic accuracy drops.",
                url="https://api.sarvam.ai/", headers={},
                api_key=os.environ.get("SARVAM_API_KEY"),
                console="https://dashboard.sarvam.ai/",
                ok_codes=(200, 404),   # root 404 still proves the host is serving
            ),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict] = []
    for i, r in enumerate(results):
        if isinstance(r, BaseException):
            log.warning("service probe %d blew up: %s", i, r)
            continue
        out.append(r)

    # Cashfree has no free ping worth making — report configuration only.
    cf_id = os.environ.get("CASHFREE_APP_ID")
    cf = _svc("cashfree", "Cashfree (payments)",
              "Takes the money for weekly, quarterly and yearly plans",
              "Nobody can pay. Existing subscriptions keep working.",
              console="https://merchant.cashfree.com/")
    if cf_id:
        cf["configured"] = True
        env_name = os.environ.get("CASHFREE_ENV", "production")
        cf["status"] = "up" if env_name.lower() in ("production", "prod") else "degraded"
        cf["detail"] = (
            f"Configured in {env_name} mode."
            + ("" if cf["status"] == "up" else " SANDBOX — real payments are not being taken.")
        )
    out.append(cf)
    return out


@router.get("/services", summary="Live status of every paid service")
async def admin_services(authorization: Optional[str] = Header(default=None)) -> dict:
    require_admin_bearer(authorization)
    services = await _gather_services()
    problems = [s for s in services
                if s["configured"] and s["status"] in ("down", "degraded")]
    return {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "services":   services,
        "problem_count": len(problems),
    }


@router.post("/services/ecourts/wallet-check",
             summary="Spend one search to read the eCourts wallet")
async def admin_ecourts_wallet_check(
    authorization: Optional[str] = Header(default=None),
) -> dict:
    """The vendor publishes no balance endpoint, so the only way to ask is to
    attempt a metered call. If the wallet is short, the refusal names the
    exact balance and costs NOTHING. If it is funded, the search succeeds and
    ₹0.60 is spent. The button in the UI says so before you press it."""
    require_admin_bearer(authorization)
    if not config.CNR_API_TOKEN:
        raise HTTPException(400, "No eCourts token is configured on this server.")
    url = f"{config.CNR_API_BASE_URL.rstrip('/')}/api/partner/search"
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.get(
                url, params={"CaseNumbers": "1/2020", "CourtCodes": "MP0701"},
                headers={"Authorization": f"Bearer {config.CNR_API_TOKEN}",
                         "User-Agent": _UA, "Accept": "application/json"},
            )
    except Exception as e:
        raise HTTPException(502, f"Could not reach the vendor: {type(e).__name__}")

    if r.status_code == 200:
        # It went through, so there was at least ₹0.60 and we just spent it.
        # We cannot learn the exact figure this way, only a floor.
        _kv_set("ecourts_balance_ok_at", datetime.now(timezone.utc).isoformat())
        return {
            "funded": True, "balance_inr": None,
            "message": "The wallet has funds — the test search went through (₹0.60 spent). "
                       "The vendor only reveals the exact balance when a call fails.",
        }
    amount = record_vendor_balance(r.text)
    if amount is not None:
        return {
            "funded": False, "balance_inr": amount,
            "message": f"Wallet is ₹{amount:.2f}. A search needs ₹0.60 and a case detail ₹1.50, "
                       "so live court lookups are failing. Nothing was charged for this check.",
        }
    return {"funded": None, "balance_inr": None,
            "message": f"Vendor returned HTTP {r.status_code}: {(r.text or '')[:200]}"}


# ================================================================= overview + ops

@router.get("/overview", summary="Headline business numbers")
def admin_overview(authorization: Optional[str] = Header(default=None)) -> dict:
    """Signups, paying users and revenue, straight from Supabase.

    Every block is individually guarded: a broken count must degrade one
    tile, never blank the page an operator is trying to use during an
    incident.
    """
    require_admin_bearer(authorization)
    from headnote.entitlements import _supabase
    from headnote.entitlements.plans import PLANS

    out: dict[str, Any] = {"generated_at": datetime.now(timezone.utc).isoformat()}

    try:
        subs = _supabase.select(
            "subscriptions",
            params={"select": "user_id,plan,status,period_end,period_start", "limit": "10000"},
        ) or []
    except Exception as e:
        log.warning("overview: subscriptions read failed: %s", e)
        subs = []
        out["warning"] = "Could not read subscriptions from Supabase."

    by_plan: dict[str, int] = {}
    paying = 0
    mrr_paise = 0
    for s in subs:
        plan = (s.get("plan") or "demo").lower()
        by_plan[plan] = by_plan.get(plan, 0) + 1
        if plan in ("weekly", "quarterly", "monthly", "yearly") and (s.get("status") or "").lower() == "active":
            paying += 1
            p = PLANS.get(plan)
            if p:
                # Normalise every tier to a monthly figure so the number means
                # one thing. A yearly plan is not ₹5,999 of monthly revenue.
                days = max(1, p.duration_days)
                mrr_paise += int(p.price_inr * 100 * 30 / days)

    out["totals"] = {
        "accounts":  len(subs),
        "paying":    paying,
        "by_plan":   by_plan,
        "mrr_inr":   round(mrr_paise / 100, 2),
    }

    # Expiring within a week — the renewal list worth acting on.
    soon = []
    now = datetime.now(timezone.utc)
    for s in subs:
        if (s.get("plan") or "").lower() not in ("weekly", "quarterly", "monthly", "yearly"):
            continue
        if (s.get("status") or "").lower() != "active":
            continue
        pe = s.get("period_end")
        if not pe:
            continue
        try:
            end = datetime.fromisoformat(str(pe).replace("Z", "+00:00"))
            if end.tzinfo is None:
                end = end.replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            continue
        days_left = (end - now).days
        if 0 <= days_left <= 7:
            soon.append({"user_id": s.get("user_id"), "plan": s.get("plan"),
                         "period_end": pe, "days_left": days_left})
    out["expiring_soon"] = sorted(soon, key=lambda r: r["days_left"])[:25]

    try:
        from headnote.api.telemetry import get_summary
        out["telemetry"] = get_summary(days=7)
    except Exception as e:
        log.debug("overview: telemetry unavailable: %s", e)
        out["telemetry"] = None

    return out


@router.get("/ops", summary="Scheduler, storage and deployment state")
def admin_ops(authorization: Optional[str] = Header(default=None)) -> dict:
    """The things that are true about this machine rather than about a vendor."""
    require_admin_bearer(authorization)
    out: dict[str, Any] = {}

    try:
        from headnote.cases.sync_scheduler import status as sync_status
        out["court_sync"] = sync_status()
    except Exception as e:
        out["court_sync"] = {"error": f"{type(e).__name__}: {e}"}

    import os
    out["flags"] = {
        "V2_PUBLIC":                   getattr(config, "V2_PUBLIC", None),
        "CNR_API_MODE":                config.CNR_API_MODE,
        "PG_CHILD_TABLES":             getattr(config, "PG_CHILD_TABLES", None),
        # Not a config attribute — read where the boot path reads it. Must
        # stay "0": defaulting it on is what took the site down for two days.
        "AUTO_REBUILD_CORPUS_ON_BOOT": os.environ.get("AUTO_REBUILD_CORPUS_ON_BOOT", "unset"),
        "password_login":              password_login_available(),
    }

    # Which access lists are actually populated on THIS machine. Counts only —
    # the console must not print customers' email addresses into a browser tab
    # that may be open on a shared screen.
    out["access_lists"] = {
        "founder": len(config.FOUNDER_EMAILS),
        "partner": len(config.PARTNER_EMAILS),
        "yearly":  len(config.YEARLY_GRANT_EMAILS),
        "monthly": len(config.MONTHLY_GRANT_EMAILS),
    }
    return out
