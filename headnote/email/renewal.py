"""Renewal nudge email — fired ~3 days before a paid subscription expires.

Orchestrator: send_due_nudges() — runs from a cron-triggered admin endpoint
(see headnote/api/partners_admin.py → /admin/cron/send-renewal-nudges).

Per-cycle idempotency
---------------------
subscriptions.renewal_nudge_sent_for_period_end holds the period_end value
we last nudged for. The orchestrator skips any row where it already equals
the current period_end. change_plan() clears the column on a fresh
renewal so the next cycle re-arms.

Window
------
Default: subs whose period_end is between (now+2d, now+4d). A daily cron is
the assumption — the 2-day band is just a safety belt for missed runs.

Without RESEND_API_KEY this becomes a logged no-op so local dev / CI don't
break. Without SUPABASE_SERVICE_ROLE_KEY the auth.users email lookup will
fail and the row is skipped.
"""

from __future__ import annotations

import json as _json
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

import httpx

from headnote.entitlements import _supabase


log = logging.getLogger(__name__)


FROM_EMAIL   = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
REPLY_TO     = os.environ.get("WELCOME_REPLY_TO",   "hello@headnote.in")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")


_PLAN_COPY = {
    "weekly":  ("Weekly Trial",  120,   "weekly"),
    "monthly": ("Monthly",       599,   "monthly"),
    "yearly":  ("Yearly",        5999,  "yearly"),
}


def _fmt_date(iso: Optional[str]) -> str:
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return ""


def _lookup_email(user_id: str) -> tuple[str, str]:
    """Hit Supabase Auth admin API for (email, full_name) by user_id.

    Returns ("", "") on miss / config absence. Never raises — the cron
    must keep going through the rest of the batch.
    """
    base = os.environ.get("SUPABASE_URL")
    key  = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not (base and key):
        return "", ""
    url = f"{base.rstrip('/')}/auth/v1/admin/users/{user_id}"
    try:
        r = httpx.get(
            url,
            headers={"apikey": key, "Authorization": f"Bearer {key}"},
            timeout=5.0,
        )
        r.raise_for_status()
        data = r.json() or {}
        email = (data.get("email") or "").strip()
        meta  = data.get("user_metadata") or {}
        name  = meta.get("full_name") or meta.get("name") or ""
        return email, name
    except httpx.HTTPError as e:
        log.warning("renewal: auth.users lookup failed for %.8s: %s", user_id, e)
        return "", ""


def _build_html(
    *, name: str, plan: str, period_end_iso: str, days_remaining: int,
) -> str:
    first = (name or "there").split()[0] or "there"
    plan_title, list_amount_inr, _slug = _PLAN_COPY.get(plan, (plan.title(), 0, plan))
    expires_on = _fmt_date(period_end_iso)
    expires_label = (
        "today" if days_remaining <= 0
        else "tomorrow" if days_remaining == 1
        else f"in {days_remaining} days"
    )
    renew_url = f"{APP_BASE_URL}/pricing?plan={plan}&utm_source=renewal_nudge"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Your Headnote plan expires {expires_label}</title>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0a0a0a;">

<div style="display:none;max-height:0;overflow:hidden;color:transparent;opacity:0;">
  Your {plan_title} plan expires {expires_label}. One click to renew.
</div>

<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#fafafa;padding:32px 16px;">
  <tr><td align="center">

    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #ececec;box-shadow:0 6px 24px -8px rgba(0,0,0,0.06);">

      <tr>
        <td style="padding:32px 36px 24px;border-bottom:1px solid #f0f0f0;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
            <tr>
              <td style="vertical-align:middle;">
                <img src="{APP_BASE_URL}/static/headnote-logo-email.png"
                     width="120" height="21" alt="Headnote"
                     style="display:block;border:0;outline:none;text-decoration:none;height:21px;width:120px;-ms-interpolation-mode:bicubic;" />
              </td>
              <td align="right" style="font-family:'Geist Mono',monospace;font-size:11px;color:#8a8a8a;letter-spacing:0.08em;text-transform:uppercase;">
                Renewal reminder
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <tr>
        <td style="padding:48px 36px 8px;">
          <p style="margin:0 0 12px;font-family:'Geist Mono',monospace;font-size:11px;color:#8c7549;letter-spacing:0.14em;text-transform:uppercase;">Expires {expires_label}</p>
          <h1 style="margin:0 0 18px;font-family:Geist,system-ui,sans-serif;font-size:30px;line-height:1.15;font-weight:600;letter-spacing:-0.025em;color:#0a0a0a;">
            {first}, your {plan_title} plan ends on<br>
            <span style="color:#8c7549;">{expires_on or expires_label}</span>.
          </h1>
          <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#525252;">
            One tap to extend — your saved drafts, history, and templates
            stay exactly where you left them. No reconfiguration.
          </p>
        </td>
      </tr>

      <tr>
        <td style="padding:20px 36px 8px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;">
            <tr>
              <td style="padding:18px 22px 6px;">
                <p style="margin:0;font-family:'Geist Mono',monospace;font-size:10px;color:#8c7549;letter-spacing:0.1em;text-transform:uppercase;">What expires</p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 22px 14px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:13.5px;color:#0a0a0a;">
                  <tr>
                    <td style="padding:8px 0;color:#8a8a8a;width:50%;">Current plan</td>
                    <td style="padding:8px 0;text-align:right;font-weight:500;">{plan_title}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;border-top:1px solid #ececec;color:#8a8a8a;">Expires on</td>
                    <td style="padding:8px 0;border-top:1px solid #ececec;text-align:right;font-weight:500;">{expires_on or expires_label}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;border-top:1px solid #ececec;color:#8a8a8a;">Renewal price</td>
                    <td style="padding:8px 0;border-top:1px solid #ececec;text-align:right;font-weight:500;">₹ {list_amount_inr:,}</td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <tr>
        <td align="center" style="padding:24px 36px 36px;">
          <a href="{renew_url}" style="display:inline-block;background:#0a0a0a;color:#ffffff;text-decoration:none;font-family:Geist,system-ui,sans-serif;font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;letter-spacing:0.01em;">
            Renew {plan_title}
          </a>
          <p style="margin:14px 0 0;font-size:12px;color:#8a8a8a;font-family:'Geist Mono',monospace;">
            After expiry your account downgrades to Demo — research stays read-only, drafting pauses.
          </p>
        </td>
      </tr>

      <tr>
        <td style="padding:24px 36px;border-top:1px solid #f0f0f0;background:#fafafa;border-radius:0 0 16px 16px;">
          <p style="margin:0;font-size:13.5px;line-height:1.6;color:#525252;">
            <strong style="color:#0a0a0a;">Reply to this email</strong> if you don't want
            to renew, or if you found a bug that soured the trial — we read every reply
            and we'd rather hear about it before the renewal lapses.
          </p>
        </td>
      </tr>

    </table>

    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;margin-top:18px;">
      <tr>
        <td align="center" style="padding:8px 24px 24px;font-size:11px;color:#8a8a8a;line-height:1.6;">
          <p style="margin:0 0 6px;">
            <a href="{APP_BASE_URL}/terms"   style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Terms</a> ·
            <a href="{APP_BASE_URL}/privacy" style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Privacy</a> ·
            <a href="{APP_BASE_URL}/refund"  style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Refund</a> ·
            <a href="{APP_BASE_URL}/contact" style="color:#8a8a8a;text-decoration:none;margin:0 6px;">Contact</a>
          </p>
          <p style="margin:0;">
            © 2026 Headnote Private Limited · Made in Bhopal, for Indian courts<br>
            Sent to <span style="color:#525252;">{{{{TO}}}}</span> because your subscription is about to expire.
          </p>
        </td>
      </tr>
    </table>

  </td></tr>
</table>

</body></html>"""


def _build_text(
    *, name: str, plan: str, period_end_iso: str, days_remaining: int,
) -> str:
    first = (name or "there").split()[0] or "there"
    plan_title, list_amount_inr, _slug = _PLAN_COPY.get(plan, (plan.title(), 0, plan))
    expires_on = _fmt_date(period_end_iso)
    expires_label = (
        "today" if days_remaining <= 0
        else "tomorrow" if days_remaining == 1
        else f"in {days_remaining} days"
    )
    renew_url = f"{APP_BASE_URL}/pricing?plan={plan}&utm_source=renewal_nudge"
    return "\n".join([
        f"{first}, your {plan_title} plan expires {expires_label} ({expires_on}).",
        "",
        "One tap to extend — your saved drafts, history, and templates",
        "stay exactly where you left them.",
        "",
        "WHAT EXPIRES",
        f"  Current plan : {plan_title}",
        f"  Expires on   : {expires_on or expires_label}",
        f"  Renewal price: Rs. {list_amount_inr:,}",
        "",
        f"Renew: {renew_url}",
        "",
        "After expiry your account downgrades to Demo — research stays",
        "read-only, drafting pauses.",
        "",
        "Reply if you don't want to renew or found a bug — we read every reply",
        "and we'd rather hear about it before the renewal lapses.",
    ]) + "\n"


def _send_one(
    *, to_email: str, name: str, plan: str,
    period_end_iso: str, days_remaining: int,
) -> bool:
    """Resend send. Never raises."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning("renewal: RESEND_API_KEY missing — would have emailed %s", to_email)
        return False
    if not to_email or "@" not in to_email:
        return False
    try:
        import resend
    except ImportError:
        log.error("renewal: 'resend' package not installed")
        return False
    resend.api_key = api_key
    html = _build_html(
        name=name, plan=plan,
        period_end_iso=period_end_iso, days_remaining=days_remaining,
    ).replace("{{TO}}", to_email)
    text = _build_text(
        name=name, plan=plan,
        period_end_iso=period_end_iso, days_remaining=days_remaining,
    )
    plan_title = _PLAN_COPY.get(plan, (plan.title(), 0, plan))[0]
    subject = f"Your Headnote {plan_title} plan expires in {days_remaining} days"
    if days_remaining <= 0:
        subject = f"Your Headnote {plan_title} plan expires today"
    elif days_remaining == 1:
        subject = f"Your Headnote {plan_title} plan expires tomorrow"
    try:
        resend.Emails.send({
            "from":     FROM_EMAIL,
            "to":       [to_email],
            "reply_to": REPLY_TO,
            "subject":  subject,
            "html":     html,
            "text":     text,
            "tags": [
                {"name": "type",    "value": "renewal_nudge"},
                {"name": "plan",    "value": plan},
                {"name": "version", "value": "v1"},
            ],
        })
        log.info("renewal: sent to %s plan=%s days=%d", to_email, plan, days_remaining)
        return True
    except Exception as e:
        log.exception("renewal: Resend send failed for %s: %s", to_email, e)
        return False


def send_due_nudges(
    *,
    window_days_min: int = 2,
    window_days_max: int = 4,
    dry_run: bool = False,
) -> dict:
    """Find active paid subs whose period_end falls inside the window and
    nudge each one once per billing cycle. Returns a small JSON summary —
    never raises so the caller (admin cron endpoint) always gets a 200.

    `window_days_min/max` define the lookahead band. Default (2, 4) means
    a daily cron that misses one day still catches the user with one day to
    spare. Set both to the same value for an exact-day nudge.

    `dry_run=True` returns the candidates without sending or marking — useful
    for debugging the query from the admin endpoint.
    """
    now = datetime.now(timezone.utc)
    lower = (now + timedelta(days=window_days_min)).isoformat()
    upper = (now + timedelta(days=window_days_max)).isoformat()

    # PostgREST: chain filters via params. `in` for the plan list.
    rows = _supabase.select(
        "subscriptions",
        params={
            "select":      "user_id,plan,period_end,renewal_nudge_sent_for_period_end",
            "status":      "eq.active",
            "plan":        "in.(weekly,monthly,yearly)",
            "period_end":  f"gte.{lower}",
            "and":         f"(period_end.lte.{upper})",
            "limit":       "500",
        },
    )

    candidates: list[dict] = []
    for r in rows:
        period_end = r.get("period_end")
        sent_for = r.get("renewal_nudge_sent_for_period_end")
        if sent_for and period_end and sent_for == period_end:
            continue  # already nudged this cycle
        candidates.append(r)

    if dry_run:
        return {"attempted": len(candidates), "candidates": candidates, "sent": 0, "skipped": 0}

    sent = skipped = 0
    for r in candidates:
        user_id    = r["user_id"]
        plan       = r["plan"]
        period_end = r["period_end"]

        email, name = _lookup_email(user_id)
        if not email:
            log.info("renewal: no email for user=%.8s — skipping", user_id)
            skipped += 1
            continue

        try:
            pe_dt = datetime.fromisoformat(period_end.replace("Z", "+00:00"))
            days_remaining = max(0, (pe_dt - now).days)
        except Exception:
            days_remaining = window_days_min

        ok = _send_one(
            to_email=email, name=name, plan=plan,
            period_end_iso=period_end, days_remaining=days_remaining,
        )
        if ok:
            _supabase.update(
                "subscriptions",
                {"renewal_nudge_sent_for_period_end": period_end},
                params={"user_id": f"eq.{user_id}"},
            )
            sent += 1
        else:
            skipped += 1

    return {"attempted": len(candidates), "sent": sent, "skipped": skipped}
