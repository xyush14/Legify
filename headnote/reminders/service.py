"""Who is due a reminder, and the one-tap send.

THE SHAPE OF THIS FEATURE, AND WHY
A lawyer with twelve hearings tomorrow wants to tell twelve clients in one
action, not open twelve rows. So `due()` builds the whole day's list in one pass
and `send_batch()` sends every matter he ticked. But the send is still HIS tap:
these dates come off photographed cause lists as often as off the court record,
and a wrong date pushed silently to a client is the one outcome that damages an
advocate more than saying nothing. `due()` therefore reports the PROVENANCE of
every date so he is deciding with that in front of him.

NOTHING IS EVER DROPPED SILENTLY
Every matter listed for the day comes back, including the ones that cannot be
sent. A matter that quietly vanished from the list because the client has no
number on file would leave the lawyer believing that client was told. Each entry
carries a `blocker` and a sentence saying what to do about it.

THE GATES, all enforced here and not in the UI:
  * consent — the matters screen has been taking "client consents to hearing
    reminders" since the diary shipped. This is the code that finally honours it.
    No consent, no message, however much the lawyer clicks.
  * a client number to send to.
  * the advocate's OWN number, because the message tells the client who to call
    if he cannot attend, and a reminder he cannot reply to is a bad reminder.
  * not already reminded — the database holds that constraint (storage.record
    returns None), so two fast clicks cannot both get through.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Optional

from headnote.cases import dateutil as case_dates
from headnote.cases import storage as cases_storage
from headnote.notesheets import storage as ns_storage
from headnote.reminders import copy as rcopy
from headnote.reminders import storage as rstore

log = logging.getLogger(__name__)

# Meta template name. ONE name carries every language version, so this is a
# single env var rather than one per language — see meta.send_template.
TEMPLATE_NAME = os.environ.get("WA_REMINDER_TEMPLATE", "hearing_reminder")

# Twilio issues one Content SID per language, so it needs a map. Format:
# "hi:HXaaa...,en:HXbbb...". Only read when WA_PROVIDER=twilio.
_TWILIO_SIDS = os.environ.get("WA_REMINDER_CONTENT_SIDS", "")

# A real eCourts CNR is 16 alphanumerics. Diary matters carry a 14-char synthetic
# placeholder beginning "DY", which is how we know a date was typed or read off a
# photographed cause list rather than confirmed against the court's own record.
_REAL_CNR = re.compile(r"^[A-Za-z0-9]{16}$")

BLOCK_NONE = ""
BLOCK_NO_PHONE = "no_phone"
BLOCK_NO_CONSENT = "no_consent"
BLOCK_ALREADY = "already_sent"
BLOCK_NO_ADVOCATE_PHONE = "no_advocate_phone"
BLOCK_NO_DETAILS = "no_details"


# ───────────────────────────────────────────────── phone handling


def norm_phone(p: Optional[str]) -> str:
    """To +E.164, assuming India for a domestic mobile.

    Follows headnote/cases/daily_send.py::_norm_phone — one number typed by the
    lawyer has to reach the same place from the daily list and from a reminder —
    with one addition it lacks: a LEADING ZERO is dropped. "094250 12345" is an
    ordinary way to write an Indian mobile, and the older rule turned it into
    "+09425012345", which is not a number anywhere. That passed the length check
    and would have been handed to the provider as a real send.
    """
    p = (p or "").strip().replace(" ", "").replace("-", "")
    if not p:
        return ""
    if p.startswith("+"):
        return p
    digits = "".join(ch for ch in p if ch.isdigit())
    # Domestic trunk prefix: 0 + a 10-digit mobile.
    if len(digits) == 11 and digits.startswith("0"):
        digits = digits[1:]
    if len(digits) == 10:
        return "+91" + digits
    if len(digits) == 12 and digits.startswith("91"):
        return "+" + digits
    if len(digits) == 13 and digits.startswith("091"):
        return "+" + digits[1:]
    return "+" + digits if digits else ""


def plausible(phone: str) -> bool:
    """Enough of a check to stop an obvious typo becoming a message to a stranger.

    We are dialling a third party on the strength of the lawyer's data entry, so a
    9-digit number is refused rather than sent hopefully — it either fails at the
    provider (costing a credit and reporting nothing useful) or reaches whoever
    does own that number.
    """
    if phone.startswith("+0"):
        # No country code begins with 0, so this is a normalisation that gave up
        # rather than a number. Refuse it instead of paying to discover that.
        return False
    d = "".join(ch for ch in phone if ch.isdigit())
    return 10 <= len(d) <= 15


# ───────────────────────────────────────────────── channel availability


def channel_status() -> dict:
    """Which sending lane is actually live right now.

    Reported to the screen verbatim rather than assumed, because the automatic
    lane depends on things no code here can arrange: a verified WhatsApp Business
    number and a template Meta has approved. Until both exist the honest answer is
    "you can send these yourself", and the screen says so instead of offering a
    button that fails.
    """
    provider = (os.environ.get("WA_PROVIDER") or "twilio").lower()
    if provider == "meta":
        have_number = bool(os.environ.get("WA_ACCESS_TOKEN")
                           and os.environ.get("WA_PHONE_NUMBER_ID"))
        ready = have_number and bool(TEMPLATE_NAME)
        if ready:
            return {"auto": True, "provider": "meta", "template": TEMPLATE_NAME,
                    "why": ""}
        return {"auto": False, "provider": "meta", "template": TEMPLATE_NAME,
                "why": ("WhatsApp is not connected yet — set WA_ACCESS_TOKEN and "
                        "WA_PHONE_NUMBER_ID." if not have_number else
                        "No reminder template name is set (WA_REMINDER_TEMPLATE).")}
    sids = _twilio_sids()
    if sids and os.environ.get("TWILIO_ACCOUNT_SID") and os.environ.get("TWILIO_WA_FROM"):
        return {"auto": True, "provider": "twilio", "template": "content-sid",
                "why": ""}
    return {"auto": False, "provider": "twilio", "template": "",
            "why": ("Twilio needs an approved Content SID per language "
                    "(WA_REMINDER_CONTENT_SIDS, e.g. \"hi:HX…,en:HX…\"). A Twilio "
                    "sandbox number can only message people who have joined the "
                    "sandbox, so it cannot reach clients.")}


def _twilio_sids() -> dict[str, str]:
    out: dict[str, str] = {}
    for part in _TWILIO_SIDS.split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            if k.strip() and v.strip():
                out[k.strip().lower()] = v.strip()
    return out


def _template_for(lang: str, provider: str) -> str:
    if provider == "twilio":
        sids = _twilio_sids()
        return sids.get(lang) or sids.get("en") or ""
    return TEMPLATE_NAME


# ───────────────────────────────────────────────── building the list


def date_source(case: dict) -> dict:
    """Where this hearing date came from — shown beside every row.

    The lawyer is about to tell a client to travel on it. 123 of the 125 matters
    in production carry a synthetic "DY…" id because they were created by
    photographing a cause-list page, so for most matters the honest answer is
    "you entered this", and he should read it before sending rather than after a
    client turns up on the wrong day.
    """
    cnr = (case.get("cnr") or "").strip()
    if _REAL_CNR.match(cnr) and not cnr.upper().startswith("DY"):
        prep = ns_storage.get_prep(case) or {}
        if prep.get("court_no") or prep.get("judge"):
            return {"kind": "causelist",
                    "label": "From the court's cause list"}
        return {"kind": "court", "label": "From the court record"}
    return {"kind": "own", "label": "Added by you — not court-confirmed"}


def _client_of(case: dict) -> dict:
    return ((case.get("case_json") or {}).get("client") or {})


def entry_for(case: dict, *, hearing_iso: str, advocate_name: str,
              advocate_phone: str, already: bool, lang: Optional[str] = None) -> dict:
    """One row of the reminder list: who, what would be sent, and what is stopping it."""
    cl = _client_of(case)
    name = (cl.get("name") or "").strip()
    phone = norm_phone(cl.get("mobile"))
    consent = bool(cl.get("consent"))
    prep = ns_storage.get_prep(case) or {}

    chosen = rcopy.normalise(lang) if lang else rcopy.lang_of(
        name, case.get("court_name"), case.get("case_title"))

    variables = rcopy.variables(
        client_name=name or "—",
        advocate_name=advocate_name or "—",
        case_number=_case_no(case),
        court=case.get("court_name") or "",
        hearing_iso=hearing_iso,
        advocate_phone=advocate_phone or "—",
        lang=chosen,
        time=prep.get("time"),
        court_no=prep.get("court_no"),
    )

    # PER-CLIENT blockers only. The advocate's own missing number is deliberately
    # NOT one of them: it is the same fact about every row, and repeating "add your
    # office number" against all twelve clients buries the client-level problems
    # that actually differ. It is reported once, at the panel, and enforced in
    # send_batch — see `blocked_reason` on the due() payload.
    #
    # Order matters: "already reminded" comes first because there is nothing to fix.
    if already:
        blocker, fix = BLOCK_ALREADY, "This client has already been reminded about this date."
    elif not name and not phone:
        blocker, fix = BLOCK_NO_DETAILS, "No client saved on this matter yet — add a name and mobile."
    elif not phone:
        blocker, fix = BLOCK_NO_PHONE, "No mobile number for this client — add one to remind them."
    elif not plausible(phone):
        blocker, fix = BLOCK_NO_PHONE, f"“{cl.get('mobile')}” does not look like a full mobile number."
    elif not consent:
        blocker, fix = BLOCK_NO_CONSENT, "This client has not consented to reminders — tick consent on the matter first."
    else:
        blocker, fix = BLOCK_NONE, ""

    return {
        "case_id": str(case.get("id")),
        "cnr": case.get("cnr"),
        "party": name or case.get("case_title") or case.get("cnr") or "—",
        "client_name": name,
        "client_phone": phone,
        "client_phone_raw": cl.get("mobile") or "",
        "consent": consent,
        "case_number": _case_no(case),
        "court_name": case.get("court_name") or "",
        "court_no": prep.get("court_no"),
        "time": prep.get("time"),
        "hearing_date": hearing_iso,
        "date_source": date_source(case),
        "lang": chosen,
        "lang_needs_signoff": chosen in rcopy.NEEDS_SIGNOFF,
        "message": rcopy.render(chosen, variables),
        "blocker": blocker,
        "fix": fix,
        "sendable": blocker == BLOCK_NONE,
    }


def _case_no(case: dict) -> str:
    n = (case.get("case_number") or "").strip()
    y = (case.get("case_year") or "").strip()
    if n and y and not n.endswith(y):
        return f"{n}/{y}"
    return n or (case.get("cnr") or "")


def due(*, user_id: Optional[str], hearing_iso: str, advocate_name: str,
        advocate_phone: str, lang: Optional[str] = None) -> dict:
    """Everyone listed on `hearing_iso`, with the message that would go to each.

    Reads the whole docket once and filters in memory — the same shape /api/home
    already uses, so opening the panel costs no extra court or vendor calls.
    """
    cases = cases_storage.list_cases(user_id=user_id, limit=500) or []
    on_day = [c for c in cases
              if _iso(c.get("next_hearing_date")) == hearing_iso]

    ids = [str(c.get("id")) for c in on_day]
    already = rstore.sent_dates_for(user_id=user_id, case_ids=ids,
                                    hearing_date=hearing_iso)

    entries = [entry_for(c, hearing_iso=hearing_iso, advocate_name=advocate_name,
                         advocate_phone=advocate_phone,
                         already=str(c.get("id")) in already, lang=lang)
               for c in on_day]
    # Sendable first — that is the list he is about to act on. Blocked rows stay
    # visible underneath so nothing disappears, sorted by blocker so the
    # "add a number" ones group together.
    entries.sort(key=lambda e: (not e["sendable"], e["blocker"], e["party"]))

    ch = channel_status()
    # Preconditions that apply to the whole send rather than to one client. Kept
    # separate from the per-row blockers so the panel can state each exactly once.
    blocked_reason = ""
    if not (advocate_phone or "").strip():
        blocked_reason = ("Add your own office number first — every reminder tells "
                          "your client who to call if they cannot attend.")
    elif not ch.get("auto"):
        blocked_reason = ch.get("why") or "Automatic sending is not switched on."

    return {
        "date": hearing_iso,
        "channel": ch,
        "advocate": {"name": advocate_name, "phone": advocate_phone,
                     "has_number": bool((advocate_phone or "").strip())},
        # Empty when the batch can go. Non-empty means nothing will send however
        # many rows are ticked, and the panel says so instead of offering a button.
        "blocked_reason": blocked_reason,
        "can_send": not blocked_reason,
        "entries": entries,
        "counts": {
            "total": len(entries),
            "sendable": sum(1 for e in entries if e["sendable"]),
            "already": sum(1 for e in entries if e["blocker"] == BLOCK_ALREADY),
            "blocked": sum(1 for e in entries
                           if not e["sendable"] and e["blocker"] != BLOCK_ALREADY),
        },
    }


def _iso(raw) -> Optional[str]:
    if not raw:
        return None
    try:
        return case_dates.to_iso(raw)
    except Exception:  # noqa: BLE001
        return None


def summary(*, user_id: Optional[str], hearing_iso: str,
            cases: Optional[list[dict]] = None) -> dict:
    """Just the counts, for Home's nudge banner.

    `cases` is passed in by /api/home, which already holds the whole docket in
    memory — re-reading it here would double the cost of the most-loaded call in
    the product to render one line of text.

    Deliberately counts rather than builds: the banner needs a number, and
    composing 40 messages to display "12 clients to remind" is work nobody sees.
    """
    if cases is None:
        cases = cases_storage.list_cases(user_id=user_id, limit=500) or []
    on_day = [c for c in cases if _iso(c.get("next_hearing_date")) == hearing_iso]
    if not on_day:
        return {"date": hearing_iso, "total": 0, "pending": 0, "blocked": 0, "already": 0}

    ids = [str(c.get("id")) for c in on_day]
    already = rstore.sent_dates_for(user_id=user_id, case_ids=ids,
                                    hearing_date=hearing_iso)
    pending = blocked = 0
    for c in on_day:
        if str(c.get("id")) in already:
            continue
        cl = _client_of(c)
        phone = norm_phone(cl.get("mobile"))
        if phone and plausible(phone) and cl.get("consent"):
            pending += 1
        else:
            blocked += 1
    return {"date": hearing_iso, "total": len(on_day), "pending": pending,
            "blocked": blocked, "already": len(already)}


# ───────────────────────────────────────────────── sending


def send_batch(*, user_id: Optional[str], hearing_iso: str, case_ids: list[str],
               advocate_name: str, advocate_phone: str,
               lang: Optional[str] = None, dry_run: bool = False) -> dict:
    """Send to every matter in `case_ids`. One tap, N clients.

    Each client is independent: one failure does not abandon the rest, and every
    outcome — sent, refused by a gate, refused by the double-send guard, or failed
    at the provider — comes back per client with its reason. A batch that reported
    only a count would leave the lawyer unable to tell which client to phone.
    """
    wanted = set(case_ids or [])
    listing = due(user_id=user_id, hearing_iso=hearing_iso,
                  advocate_name=advocate_name, advocate_phone=advocate_phone,
                  lang=lang)
    ch = listing["channel"]
    results: list[dict] = []

    # A whole-batch precondition (no callback number, or no live sending lane) is
    # refused ONCE, here, before a single provider call. Letting it fall through to
    # the per-client loop would spend a message credit on each one only to fail.
    if listing.get("blocked_reason") and not dry_run:
        return {"ok": False, "date": hearing_iso, "dry_run": False, "channel": ch,
                "sent": 0, "failed": 0, "skipped": len(wanted),
                "blocked_reason": listing["blocked_reason"],
                "results": [{**_slim(e), "status": "skipped",
                             "reason": listing["blocked_reason"]}
                            for e in listing["entries"] if e["case_id"] in wanted]}

    for e in listing["entries"]:
        if e["case_id"] not in wanted:
            continue
        if not e["sendable"]:
            results.append({**_slim(e), "status": "skipped", "reason": e["fix"]})
            continue
        if dry_run:
            results.append({**_slim(e), "status": "would_send", "reason": ""})
            continue
        results.append(_send_one(e, user_id=user_id, channel=ch,
                                advocate_name=advocate_name,
                                advocate_phone=advocate_phone))

    sent = sum(1 for r in results if r["status"] == "sent")
    return {
        "ok": True,
        "date": hearing_iso,
        "dry_run": dry_run,
        "channel": ch,
        "sent": sent,
        "failed": sum(1 for r in results if r["status"] == "failed"),
        "skipped": sum(1 for r in results if r["status"] == "skipped"),
        "results": results,
    }


def _slim(e: dict) -> dict:
    return {"case_id": e["case_id"], "party": e["party"],
            "client_name": e["client_name"], "to": e["client_phone"]}


def _send_one(e: dict, *, user_id: Optional[str], channel: dict,
              advocate_name: str, advocate_phone: str) -> dict:
    """Send to one client and log the outcome.

    The log write comes FIRST when it is the guard's job to refuse — record()
    returns None if a successful reminder for this matter and date already exists,
    and in that case nothing is sent. Doing it the other way round (send, then
    log) would let two simultaneous clicks both send and only the second one fail
    to log, which is precisely the double message this is meant to prevent.
    """
    from headnote.whatsapp import client as wa
    from headnote.reminders import copy as _c

    lang, body = e["lang"], e["message"]
    variables = None

    if not channel.get("auto"):
        return {**_slim(e), "status": "skipped",
                "reason": "Automatic sending is not switched on — " + (channel.get("why") or "")}

    # Claim the slot. None = the guard says this client was already reminded.
    claim = rstore.record(
        user_id=user_id, case_id=e["case_id"], hearing_date=e["hearing_date"],
        to_phone=e["client_phone"], channel=rstore.CH_TEMPLATE,
        status=rstore.SENT, client_name=e["client_name"],
        consent_at_send=bool(e["consent"]), lang=lang, body=body,
        provider=channel.get("provider"),
    )
    if claim is None:
        return {**_slim(e), "status": "skipped",
                "reason": "Already reminded about this date."}

    try:
        variables = _rebuild_vars(e, advocate_name, advocate_phone)
        missing = _c.missing_vars(variables)
        if missing:
            raise ValueError(
                "the message would have blanks in it "
                f"(placeholder {', '.join(str(m) for m in missing)})")
        tpl = _template_for(lang, channel.get("provider") or "meta")
        if not tpl:
            raise ValueError(f"no approved reminder template for {lang!r}")
        resp = wa.send_template(e["client_phone"], tpl, lang, variables,
                                provider=channel.get("provider"))
        _set_msg_id(claim, resp)
        return {**_slim(e), "status": "sent", "reason": "",
                "provider_msg_id": _msg_id(resp)}
    except Exception as ex:  # noqa: BLE001 — one client's failure is not the batch's
        log.warning("reminder to %s for case %s failed: %s",
                    e["client_phone"], e["case_id"], ex)
        # Flip the claimed row to failed so the guard releases it and the lawyer
        # can retry. Leaving it as 'sent' would tell him a client was reminded
        # who was not — the worst of the available outcomes.
        _mark_failed(claim, user_id, str(ex))
        return {**_slim(e), "status": "failed", "reason": str(ex)[:300]}


def _rebuild_vars(e: dict, advocate_name: str, advocate_phone: str) -> list[str]:
    """The placeholder values behind e["message"].

    Rebuilt server-side from the matter rather than accepted from the request on
    purpose: these are the words that reach a third party, so they come from our
    own copy of the matter and never from anything the browser could have edited
    between previewing the message and pressing send.
    """
    return rcopy.variables(
        client_name=e["client_name"], advocate_name=advocate_name,
        case_number=e["case_number"], court=e["court_name"],
        hearing_iso=e["hearing_date"], advocate_phone=advocate_phone,
        lang=e["lang"], time=e.get("time"), court_no=e.get("court_no"),
    )


def _msg_id(resp) -> str:
    if not isinstance(resp, dict):
        return ""
    msgs = resp.get("messages")
    if isinstance(msgs, list) and msgs and isinstance(msgs[0], dict):
        return str(msgs[0].get("id") or "")
    return str(resp.get("sid") or "")


def _set_msg_id(row: dict, resp) -> None:
    mid = _msg_id(resp)
    if not (row and mid):
        return
    try:
        rstore.set_provider_msg_id(row, mid)
    except Exception as e:  # noqa: BLE001 — the message went; the id is bookkeeping
        log.warning("could not store provider message id: %s", e)


def _mark_failed(row: dict, user_id: Optional[str], err: str) -> None:
    try:
        rstore.mark_failed(row, user_id=user_id, error=err)
    except Exception as e:  # noqa: BLE001
        log.error("could not mark reminder %s failed — it will look sent: %s",
                  (row or {}).get("id"), e)
