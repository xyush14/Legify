"""Subscription confirmation email — fired once after a paid order succeeds.

Triggered from headnote.api.payments._upgrade_from_paid_order, which is the
single chokepoint for both the Cashfree webhook AND the /verify redirect.
Idempotency is enforced by the caller (compares the subscription's existing
payment_ref to this order_id before sending).

Design mirrors welcome.py:
  - Table-based layout (Gmail / Outlook strip flex / grid).
  - Inline CSS only.
  - Single-column on mobile (max-width 600px).
  - Plain-text fallback for spam-filter heuristics.

Resend docs: https://resend.com/docs/send-with-python
"""

from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Optional


log = logging.getLogger(__name__)


FROM_EMAIL   = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
REPLY_TO     = os.environ.get("WELCOME_REPLY_TO",   "hello@headnote.in")
APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")


_PLAN_COPY = {
    "weekly":  ("Weekly Trial",  "7 days of full access."),
    "monthly": ("Monthly",       "30 days of unlimited research and drafting."),
    "yearly":  ("Yearly",        "365 days of unlimited research and drafting."),
    "sections": ("Section Finder", "Lifetime unlock — never expires."),
}


def _fmt_date(iso: Optional[str]) -> str:
    """ISO-8601 → '04 Jun 2026'. Returns '' on parse failure."""
    if not iso:
        return ""
    try:
        return datetime.fromisoformat(iso.replace("Z", "+00:00")).strftime("%d %b %Y")
    except Exception:
        return ""


def _build_html(
    *, name: str, plan: str, amount_inr: int,
    order_id: str, period_end_iso: Optional[str],
) -> str:
    first = (name or "there").split()[0] or "there"
    plan_title, plan_blurb = _PLAN_COPY.get(plan, (plan.title(), ""))
    period_end = _fmt_date(period_end_iso)
    is_addon = plan == "sections"

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Payment received — Headnote</title>
</head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0a0a0a;">

<div style="display:none;max-height:0;overflow:hidden;color:transparent;opacity:0;">
  Payment received. Your Headnote {plan_title} plan is now active.
</div>

<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#fafafa;padding:32px 16px;">
  <tr><td align="center">

    <table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:16px;border:1px solid #ececec;box-shadow:0 6px 24px -8px rgba(0,0,0,0.06);">

      <!-- Header band -->
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
                Receipt
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- Hero -->
      <tr>
        <td style="padding:48px 36px 8px;">
          <p style="margin:0 0 12px;font-family:'Geist Mono',monospace;font-size:11px;color:#8c7549;letter-spacing:0.14em;text-transform:uppercase;">Payment received</p>
          <h1 style="margin:0 0 18px;font-family:Geist,system-ui,sans-serif;font-size:32px;line-height:1.1;font-weight:600;letter-spacing:-0.025em;color:#0a0a0a;">
            Thank you, {first}.<br>
            <span style="color:#8c7549;">Your {plan_title} plan is live.</span>
          </h1>
          <p style="margin:0 0 8px;font-size:15px;line-height:1.6;color:#525252;">
            {plan_blurb} {"Treat this email as your receipt." if not is_addon else "This add-on is attached to your account permanently — keep this email as your receipt."}
          </p>
        </td>
      </tr>

      <!-- Receipt table -->
      <tr>
        <td style="padding:20px 36px 8px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#fafafa;border:1px solid #ececec;border-radius:12px;">
            <tr>
              <td style="padding:18px 22px 6px;">
                <p style="margin:0;font-family:'Geist Mono',monospace;font-size:10px;color:#8c7549;letter-spacing:0.1em;text-transform:uppercase;">Order summary</p>
              </td>
            </tr>
            <tr>
              <td style="padding:0 22px 4px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="font-size:13.5px;color:#0a0a0a;">
                  <tr>
                    <td style="padding:8px 0;color:#8a8a8a;width:42%;">Plan</td>
                    <td style="padding:8px 0;text-align:right;font-weight:500;">{plan_title}</td>
                  </tr>
                  <tr>
                    <td style="padding:8px 0;border-top:1px solid #ececec;color:#8a8a8a;">Amount</td>
                    <td style="padding:8px 0;border-top:1px solid #ececec;text-align:right;font-weight:500;">₹ {amount_inr:,}</td>
                  </tr>
                  {("<tr><td style='padding:8px 0;border-top:1px solid #ececec;color:#8a8a8a;'>Valid until</td><td style='padding:8px 0;border-top:1px solid #ececec;text-align:right;font-weight:500;'>" + period_end + "</td></tr>") if period_end and not is_addon else ""}
                  <tr>
                    <td style="padding:8px 0 14px;border-top:1px solid #ececec;color:#8a8a8a;">Order ID</td>
                    <td style="padding:8px 0 14px;border-top:1px solid #ececec;text-align:right;font-family:'Geist Mono',monospace;font-size:12px;color:#525252;">{order_id}</td>
                  </tr>
                </table>
              </td>
            </tr>
          </table>
        </td>
      </tr>

      <!-- CTA -->
      <tr>
        <td align="center" style="padding:24px 36px 40px;">
          <a href="{APP_BASE_URL}/app" style="display:inline-block;background:#0a0a0a;color:#ffffff;text-decoration:none;font-family:Geist,system-ui,sans-serif;font-size:15px;font-weight:600;padding:14px 32px;border-radius:10px;letter-spacing:0.01em;">
            Open Headnote
          </a>
          <p style="margin:14px 0 0;font-size:12px;color:#8a8a8a;font-family:'Geist Mono',monospace;">
            GST invoice on request — reply to this email.
          </p>
        </td>
      </tr>

      <!-- Reply prompt -->
      <tr>
        <td style="padding:24px 36px;border-top:1px solid #f0f0f0;background:#fafafa;border-radius:0 0 16px 16px;">
          <p style="margin:0;font-size:13.5px;line-height:1.6;color:#525252;">
            <strong style="color:#0a0a0a;">Reply to this email</strong> if anything's off with the
            payment or you need a tax invoice. We read every reply.
          </p>
        </td>
      </tr>

    </table>

    <!-- Footer -->
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
            Sent to <span style="color:#525252;">{{{{TO}}}}</span> because you completed a purchase on headnote.in.
          </p>
        </td>
      </tr>
    </table>

  </td></tr>
</table>

</body>
</html>"""


def _build_text(
    *, name: str, plan: str, amount_inr: int,
    order_id: str, period_end_iso: Optional[str],
) -> str:
    first = (name or "there").split()[0] or "there"
    plan_title, plan_blurb = _PLAN_COPY.get(plan, (plan.title(), ""))
    period_end = _fmt_date(period_end_iso)
    is_addon = plan == "sections"

    lines = [
        f"Thank you, {first}.",
        f"Your {plan_title} plan is live.",
        "",
        plan_blurb,
        "",
        "ORDER SUMMARY",
        f"  Plan       : {plan_title}",
        f"  Amount     : Rs. {amount_inr:,}",
    ]
    if period_end and not is_addon:
        lines.append(f"  Valid until: {period_end}")
    lines.extend([
        f"  Order ID   : {order_id}",
        "",
        f"Open Headnote: {APP_BASE_URL}/app",
        "",
        "GST invoice on request — just reply to this email.",
        "",
        "Reply to this email if anything's off with the payment.",
        "We read every reply.",
        "",
        "---",
        f"Terms:   {APP_BASE_URL}/terms",
        f"Privacy: {APP_BASE_URL}/privacy",
        f"Refund:  {APP_BASE_URL}/refund",
        f"Contact: {APP_BASE_URL}/contact",
        "(c) 2026 Headnote Private Limited",
    ])
    return "\n".join(lines)


def send_subscription_confirmation(
    *,
    to_email: str,
    name: Optional[str] = None,
    plan: str,
    amount_inr: int,
    order_id: str,
    period_end_iso: Optional[str] = None,
) -> bool:
    """Send the subscription confirmation / receipt email.

    Idempotency is enforced by the caller (see _upgrade_from_paid_order —
    it compares the subscription's existing payment_ref to order_id before
    triggering this).

    Returns True if the send was attempted successfully, False on hard
    failure / missing config. Never raises — email failures must not block
    the payment success flow.
    """
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning(
            "send_subscription_confirmation: RESEND_API_KEY not set — skipping email to %s (order=%s).",
            to_email, order_id,
        )
        return False
    if not to_email or "@" not in to_email:
        log.warning("send_subscription_confirmation: invalid recipient %r — skipping", to_email)
        return False

    try:
        import resend
    except ImportError:
        log.error("send_subscription_confirmation: 'resend' package not installed")
        return False

    resend.api_key = api_key
    html = _build_html(
        name=name or "", plan=plan, amount_inr=amount_inr,
        order_id=order_id, period_end_iso=period_end_iso,
    ).replace("{{TO}}", to_email)
    text = _build_text(
        name=name or "", plan=plan, amount_inr=amount_inr,
        order_id=order_id, period_end_iso=period_end_iso,
    )
    plan_title = _PLAN_COPY.get(plan, (plan.title(), ""))[0]
    subject = f"Payment received — Headnote {plan_title} is live"

    try:
        resend.Emails.send({
            "from":     FROM_EMAIL,
            "to":       [to_email],
            "reply_to": REPLY_TO,
            "subject":  subject,
            "html":     html,
            "text":     text,
            "tags": [
                {"name": "type",    "value": "subscription_confirmation"},
                {"name": "plan",    "value": plan},
                {"name": "version", "value": "v1"},
            ],
        })
        log.info(
            "send_subscription_confirmation: sent to %s plan=%s order=%s",
            to_email, plan, order_id,
        )
        return True
    except Exception as e:
        log.exception(
            "send_subscription_confirmation: Resend API call failed for %s order=%s: %s",
            to_email, order_id, e,
        )
        return False
