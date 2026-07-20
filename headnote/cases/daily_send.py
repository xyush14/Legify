"""Send each lawyer their daily cause-list link over WhatsApp + email.

Morning: "here's today's list — print it, write next dates in court."
Evening: "back from court? upload the marked sheet so we settle your diary."

Both messages carry ONE tokenised link (headnote/cases/daily_links.py) to
/d/<token> — a no-login page that shows that date's list, prints it, and accepts
the marked-sheet upload. No PDF attachment needed (the page prints client-side).

Driven by POST /admin/cron/send-daily-causelist (external scheduler). dry_run
returns the recipient list without sending, so you can preview safely.
"""

from __future__ import annotations

import logging
import os

from headnote.cases import daily_links
from headnote.cases import storage as cases_storage
from headnote.cases import dateutil as case_dates
from headnote.entitlements import _supabase

log = logging.getLogger(__name__)

APP_BASE_URL = (os.environ.get("APP_BASE_URL") or "https://headnote.in").rstrip("/")
FROM_EMAIL = os.environ.get("WELCOME_FROM_EMAIL", "Headnote <hello@headnote.in>")
REPLY_TO = os.environ.get("WELCOME_REPLY_TO", "hello@headnote.in")


def _norm_phone(p: str) -> str:
    p = (p or "").strip().replace(" ", "").replace("-", "")
    if not p:
        return ""
    if p.startswith("+"):
        return p
    digits = "".join(ch for ch in p if ch.isdigit())
    if len(digits) == 10:            # bare Indian mobile → +91
        return "+91" + digits
    return "+" + digits


def _recipients(only_user_id=None):
    """[(user_id, phone, email, name)] for lawyers we can reach."""
    if only_user_id:
        rows = _supabase.select("user_profiles",
                                params={"id": f"eq.{only_user_id}", "select": "id,phone", "limit": "1"})
    else:
        rows = _supabase.select("user_profiles", params={"select": "id,phone", "limit": "2000"})
    out = []
    for r in rows:
        uid = r.get("id")
        if not uid:
            continue
        phone = _norm_phone(r.get("phone") or "")
        email, name = "", ""
        try:
            from headnote.email.renewal import _lookup_email
            email, name = _lookup_email(uid)
        except Exception:  # noqa: BLE001
            pass
        if phone or email:
            out.append((uid, phone, email, name))
    return out


def _day_count(user_id, date_iso: str) -> int:
    rows = cases_storage.list_cases(user_id=user_id, limit=500)
    return sum(1 for r in rows
               if case_dates.to_iso(r.get("next_hearing_date")) == date_iso)


def _copy(slot: str, name: str, date_label: str, link: str):
    hi = f" {name}" if name else ""
    if slot == "evening":
        wa = (f"🌙 Back from court{hi}? Upload today's marked cause list so we settle "
              f"your diary and roll each case to its next date:\n{link}")
        subj = f"Settle your diary — {date_label}"
    else:
        wa = (f"🌅 Good morning{hi}. Your cause list for {date_label} is ready. Print it, "
              f"and in court write each case's next date in the blank column:\n{link}")
        subj = f"Your cause list — {date_label}"
    html = (f"<div style='font-family:Arial,sans-serif;max-width:520px;margin:0 auto;color:#1a1a1a'>"
            f"<p>{wa.split(chr(10))[0]}</p>"
            f"<p><a href='{link}' style='display:inline-block;background:#1a1a1a;color:#fff;"
            f"text-decoration:none;padding:12px 20px;border-radius:8px'>Open your cause list</a></p>"
            f"<p style='color:#888;font-size:12px'>headnote · your diary, self-updating</p></div>")
    return wa, subj, html


def _send_email(to: str, subject: str, html: str, text: str) -> bool:
    if not (to and os.environ.get("RESEND_API_KEY")):
        return False
    try:
        import resend
        resend.api_key = os.environ["RESEND_API_KEY"]
        resend.Emails.send({"from": FROM_EMAIL, "to": [to], "reply_to": REPLY_TO,
                            "subject": subject, "html": html, "text": text,
                            "tags": [{"name": "type", "value": "daily_causelist"}]})
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("daily causelist email to %s failed: %s", to, e)
        return False


def _send_whatsapp(to: str, body: str) -> bool:
    if not to:
        return False
    try:
        from headnote.whatsapp import client as wa
        wa.send_text(to, body)
        return True
    except Exception as e:  # noqa: BLE001
        log.warning("daily causelist whatsapp to %s failed: %s", to, e)
        return False


def send_daily_causelists(*, slot: str = "morning", dry_run: bool = False,
                          only_user_id=None, date_iso=None) -> dict:
    """Send the daily link to every reachable lawyer who has cases listed for the
    target date (default: today). `slot` = 'morning' | 'evening' (copy only)."""
    date_iso = date_iso or case_dates.today_iso()
    date_label = case_dates.to_iso(date_iso) or date_iso
    sent_wa = sent_email = skipped = 0
    preview = []
    for uid, phone, email, name in _recipients(only_user_id):
        count = _day_count(uid, date_iso)
        if count == 0 and not only_user_id:
            skipped += 1
            continue                       # don't nudge lawyers with nothing listed
        token = daily_links.make_token(uid, date_iso)
        link = f"{APP_BASE_URL}/d/{token}"
        wa_body, subj, html = _copy(slot, name, date_label, link)
        if dry_run:
            preview.append({"user_id": uid, "phone": phone, "email": email,
                            "count": count, "link": link})
            continue
        if _send_whatsapp(phone, wa_body):
            sent_wa += 1
        if _send_email(email, subj, html, wa_body):
            sent_email += 1
    return {"ok": True, "slot": slot, "date": date_label, "dry_run": dry_run,
            "whatsapp_sent": sent_wa, "email_sent": sent_email,
            "skipped_no_cases": skipped,
            **({"preview": preview} if dry_run else {})}
