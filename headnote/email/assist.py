"""Personal-assist email — fired when a lawyer taps the in-product CTAs:

  - Research mode  → "Not satisfied? Our team will assist you personally"
                     (promise: case-law sent within 15 minutes)
  - Drafting       → "Not finding what you need?"
                     (promise: template uploaded within 2 hours, permanently)

Both flows hit the same /api/assist/* endpoints which call send_assist_request()
here. The request goes to FOUNDER_INBOX (Ayush's WhatsApp-linked inbox) — the
SLA is short (15 min / 2 hr) so this MUST land in front of a human immediately.

Resend is the transport. Without RESEND_API_KEY set, every send becomes a
logged no-op so local dev / CI don't break.
"""

from __future__ import annotations

import logging
import os
from typing import Optional


log = logging.getLogger(__name__)


# Where assist requests land. Production: the founder's inbox (Ayush).
# Override per env if a team rotation goes online.
FOUNDER_INBOX = os.environ.get("ASSIST_INBOX_EMAIL", "ayushshivhare02@gmail.com")
FROM_EMAIL    = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
APP_BASE_URL  = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")


# Per-mode copy used in the subject + intro lines. Kept in one place so the
# Resend tag stays consistent with the subject the founder sees.
_MODE_META = {
    "research": {
        "subject_prefix": "[Research assist · 15-min SLA]",
        "intro": (
            "A lawyer asked for personal case-law help after a research query. "
            "The SLA we promised on the CTA is 15 minutes — please respond "
            "(WhatsApp / email reply) before then."
        ),
        "what_to_send": "Three relevant judgments with paragraph anchors.",
    },
    "draft": {
        "subject_prefix": "[Draft assist · 2-hour SLA]",
        "intro": (
            "A lawyer asked for a draft template we don't yet have. "
            "The SLA we promised on the CTA is 2 hours — upload the template "
            "to compose_templates so it's live for them (and everyone else) by then."
        ),
        "what_to_send": "A new template (or a tuned version of an existing one) live in the app.",
    },
}


def _build_html(*, mode: str, query: str, user_email: str, user_name: str,
                user_phone: str, source_context: Optional[str]) -> str:
    """Email body the founder sees. Designed to be skimmable on a phone —
    the founder is usually replying from WhatsApp, not a desktop."""
    meta = _MODE_META.get(mode, _MODE_META["research"])
    ctx_block = ""
    if source_context:
        # The research CTA passes the lawyer's last query as context so we
        # don't have to play 20-questions on WhatsApp.
        ctx_block = f"""
        <tr>
          <td style="padding:14px 22px;background:#fafafa;border-left:3px solid #c9a96e;border-radius:0 6px 6px 0;">
            <p style="margin:0 0 4px;font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#8c7549;">Their last query / page context</p>
            <p style="margin:0;font-size:13px;line-height:1.55;color:#0a0a0a;white-space:pre-wrap;">{_escape(source_context)}</p>
          </td>
        </tr>"""

    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#fafafa;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;color:#0a0a0a;">
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="100%" style="background:#fafafa;padding:24px 16px;">
<tr><td align="center">
<table role="presentation" cellspacing="0" cellpadding="0" border="0" width="600" style="max-width:600px;background:#ffffff;border-radius:12px;border:1px solid #ececec;">
  <tr><td style="padding:22px 28px 18px;border-bottom:1px solid #f0f0f0;">
    <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:0.14em;text-transform:uppercase;color:#8c7549;">{_escape(meta['subject_prefix'])}</p>
    <h1 style="margin:0;font-size:20px;font-weight:600;letter-spacing:-0.015em;color:#0a0a0a;">A lawyer needs you within {('15 minutes' if mode == 'research' else '2 hours')}.</h1>
  </td></tr>

  <tr><td style="padding:22px 28px 8px;">
    <p style="margin:0 0 18px;font-size:14px;line-height:1.6;color:#525252;">{_escape(meta['intro'])}</p>
  </td></tr>

  <tr><td style="padding:0 28px 14px;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tr><td style="padding:14px 18px;background:#fafafa;border:1px solid #ececec;border-radius:8px;">
        <p style="margin:0 0 4px;font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#8c7549;">Lawyer</p>
        <p style="margin:0 0 10px;font-size:14.5px;color:#0a0a0a;"><strong>{_escape(user_name or '(no name on file)')}</strong></p>
        <p style="margin:0;font-size:13px;color:#525252;">
          📧 <a href="mailto:{_escape(user_email)}" style="color:#0a0a0a;">{_escape(user_email)}</a><br>
          {'📱 <a href="https://wa.me/' + _digits(user_phone) + '" style="color:#0a0a0a;">' + _escape(user_phone) + '</a>' if user_phone else '<span style="color:#8a8a8a;">no phone on file</span>'}
        </p>
      </td></tr>
    </table>
  </td></tr>

  <tr><td style="padding:0 28px 14px;">
    <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
      <tr><td style="padding:14px 18px;background:#fafafa;border:1px solid #ececec;border-radius:8px;">
        <p style="margin:0 0 4px;font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#8c7549;">Their request</p>
        <p style="margin:0;font-size:14px;line-height:1.6;color:#0a0a0a;white-space:pre-wrap;">{_escape(query)}</p>
      </td></tr>
    </table>
  </td></tr>

  {ctx_block}

  <tr><td style="padding:14px 28px 22px;">
    <p style="margin:0 0 6px;font-family:'Geist Mono',monospace;font-size:10px;letter-spacing:0.1em;text-transform:uppercase;color:#8c7549;">Deliverable</p>
    <p style="margin:0;font-size:13.5px;line-height:1.55;color:#525252;">{_escape(meta['what_to_send'])}</p>
  </td></tr>

  <tr><td style="padding:14px 28px 22px;border-top:1px solid #f0f0f0;background:#fafafa;border-radius:0 0 12px 12px;">
    <p style="margin:0;font-size:11.5px;color:#8a8a8a;line-height:1.55;">
      Reply directly to this email — it goes to the lawyer. Or WhatsApp them. The CTA SLA timer started the moment they tapped.
    </p>
  </td></tr>
</table>
</td></tr></table>
</body></html>"""


def _build_text(*, mode: str, query: str, user_email: str, user_name: str,
                user_phone: str, source_context: Optional[str]) -> str:
    meta = _MODE_META.get(mode, _MODE_META["research"])
    bits = [
        f"{meta['subject_prefix']}",
        f"",
        f"A lawyer needs you within {'15 minutes' if mode == 'research' else '2 hours'}.",
        f"",
        meta["intro"],
        f"",
        f"LAWYER",
        f"  Name:  {user_name or '(no name on file)'}",
        f"  Email: {user_email}",
        f"  Phone: {user_phone or '(none)'}",
        f"",
        f"REQUEST",
        f"  {query}",
    ]
    if source_context:
        bits.extend(["", "CONTEXT (their last query / page)", f"  {source_context}"])
    bits.extend([
        "",
        f"DELIVERABLE",
        f"  {meta['what_to_send']}",
        "",
        f"Reply directly to this email — it goes to the lawyer. Or WhatsApp them.",
    ])
    return "\n".join(bits)


def send_assist_request(
    *,
    mode: str,
    query: str,
    user_email: str,
    user_name: str = "",
    user_phone: str = "",
    source_context: Optional[str] = None,
) -> bool:
    """Send the personal-assist email to the founder inbox.

    Always returns True on best-effort attempt (the UX must not block on
    email delivery). False only on hard misconfiguration so the caller can
    log it; the user never sees the difference.

    `mode` ∈ {"research", "draft"} selects the subject + SLA copy.
    `source_context` is the lawyer's last research query (research mode)
    or the template name they were looking for (draft mode).
    """
    if mode not in _MODE_META:
        log.warning("send_assist_request: unknown mode %r; defaulting to 'research'", mode)
        mode = "research"
    if not query or not query.strip():
        log.warning("send_assist_request: empty query — skipping")
        return False
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        log.warning(
            "send_assist_request: RESEND_API_KEY not set — would have emailed "
            "%s about %s mode request: %s",
            FOUNDER_INBOX, mode, query[:140],
        )
        return False
    try:
        import resend
    except ImportError:
        log.error("send_assist_request: 'resend' package missing")
        return False

    resend.api_key = api_key
    subject = f"{_MODE_META[mode]['subject_prefix']} {query[:80]}".strip()
    html = _build_html(
        mode=mode, query=query, user_email=user_email, user_name=user_name,
        user_phone=user_phone, source_context=source_context,
    )
    text = _build_text(
        mode=mode, query=query, user_email=user_email, user_name=user_name,
        user_phone=user_phone, source_context=source_context,
    )
    try:
        resend.Emails.send({
            "from":     FROM_EMAIL,
            "to":       [FOUNDER_INBOX],
            "reply_to": user_email or FROM_EMAIL,
            "subject":  subject,
            "html":     html,
            "text":     text,
            "tags": [
                {"name": "type",   "value": "assist"},
                {"name": "mode",   "value": mode},
            ],
        })
        log.info("send_assist_request: ok mode=%s lawyer=%s query=%s",
                 mode, user_email, query[:80])
        return True
    except Exception as e:
        log.exception("send_assist_request: Resend send failed: %s", e)
        return False


# ----- tiny helpers ----------------------------------------------------

def _escape(s: str) -> str:
    return (str(s or "")
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;"))


def _digits(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())
