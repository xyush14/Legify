"""What changed at the court since we last looked.

The CNR adapter already returns far more than we were keeping: alongside the next
date it normalises `stage`, `last_order`, `hearings[{date,purpose}]` and
`orders[{date,type,link}]`. Until now `refresh_next_date` fetched all of that and
threw everything except the date away — so a lawyer could have an order uploaded
against their matter and Headnote would never say so.

This module fetches the fresh case and DIFFS it against what we stored, turning
the difference into a short list of things a lawyer would actually want told:

    next_date · stage · purpose · new_order · new_hearing · disposed

Design rules:
  • The court is the authority. We never invent an update; each one names the old
    and the new value so the lawyer can see exactly what moved.
  • Diffing is pure — `diff()` does no I/O, so it is testable without a network.
  • Unknown → nothing. A field the vendor omits is not treated as "removed",
    otherwise a flaky payload would raise a false alarm on every sync.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from headnote.cases import dateutil as case_dates

log = logging.getLogger(__name__)

# how many updates we keep per matter — an inbox, not an audit log
_MAX_UPDATES = 30


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _norm(v: Any) -> str:
    return str(v or "").strip()


def _iso(v: Any) -> str:
    """Court dates arrive in several formats; compare on ISO so 1/8/26 and
    01/08/2026 don't read as a change."""
    s = _norm(v)
    if not s:
        return ""
    try:
        return case_dates.to_iso(s) or s
    except Exception:  # noqa: BLE001
        return s


def _order_key(o: dict) -> str:
    """Identity of an order row, so the same order re-sent isn't 'new'.

    Must read the vendor's OWN key names (`orderDate`/`orderType`/`orderUrl`) as
    well as ours: reading only date/type/link made every live order row hash to
    the same empty string, so after the first one no order could ever register as
    new."""
    return "|".join([
        _iso(o.get("date") or o.get("orderDate") or o.get("order_date")),
        _norm(o.get("type") or o.get("orderType")).lower(),
        _norm(o.get("link") or o.get("url") or o.get("orderUrl")),
    ])


def _hearing_key(h: dict) -> str:
    return "|".join([_iso(h.get("date")), _norm(h.get("purpose")).lower()])


def _rows(case: dict, key: str) -> list[dict]:
    v = case.get(key)
    return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []


def purpose_from(case: dict) -> Optional[str]:
    """What the court says the NEXT hearing is for.

    This is the input the readiness rule needs, and the court supplies it — so we
    read it rather than asking the lawyer to type it. Preference order: the
    hearing row matching the next date, then the stage sub-status, then stage.
    """
    nxt = _iso(case.get("next_hearing_date"))
    if nxt:
        for h in _rows(case, "hearings"):
            if _iso(h.get("date")) == nxt and _norm(h.get("purpose")):
                return _norm(h.get("purpose"))
    for k in ("stage_substatus", "stage"):
        if _norm(case.get(k)):
            return _norm(case.get(k))
    return None


def diff(stored: dict, fresh: dict) -> list[dict]:
    """Compare the stored case payload with a freshly fetched one.

    Returns newest-relevant-first list of {kind, text, old, new, …}. Pure: no I/O.
    """
    out: list[dict] = []
    if not isinstance(stored, dict) or not isinstance(fresh, dict):
        return out

    # --- the date the whole diary turns on
    o_date, n_date = _iso(stored.get("next_hearing_date")), _iso(fresh.get("next_hearing_date"))
    if n_date and n_date != o_date:
        out.append({"kind": "next_date", "old": stored.get("next_hearing_date"),
                    "new": fresh.get("next_hearing_date"),
                    "text": (f"Next date moved to {fresh.get('next_hearing_date')}"
                             if o_date else f"Next date listed: {fresh.get('next_hearing_date')}")})

    # --- stage, and the purpose that drives readiness
    o_stage, n_stage = _norm(stored.get("stage")), _norm(fresh.get("stage"))
    if n_stage and n_stage != o_stage:
        out.append({"kind": "stage", "old": o_stage or None, "new": n_stage,
                    "text": f"Stage is now “{n_stage}”" + (f" (was “{o_stage}”)" if o_stage else "")})

    o_purpose, n_purpose = _norm(purpose_from(stored)), _norm(purpose_from(fresh))
    if n_purpose and n_purpose != o_purpose:
        out.append({"kind": "purpose", "old": o_purpose or None, "new": n_purpose,
                    "text": f"Listed for “{n_purpose}”"})

    # --- orders: the thing a lawyer most wants to know about
    # The vendor names the order's own date `orderDate` and its document
    # `orderUrl`, so reading only date/link meant a genuinely new order was
    # skipped as having neither — and the "Save to folder" button, which the UI
    # shows only when `link` is set, could never appear.
    seen = {_order_key(o) for o in _rows(stored, "orders")}
    for o in _rows(fresh, "orders"):
        k = _order_key(o)
        from headnote.cases import ecourts_client
        when = o.get("date") or o.get("orderDate") or o.get("order_date")
        fname = ecourts_client._order_filename(o)
        if k in seen or not (when or fname):
            continue
        label = _norm(o.get("type")) or _norm(o.get("orderType")) or "Order"
        out.append({"kind": "new_order", "date": when,
                    "order_type": label, "link": o.get("link") or o.get("url"),
                    # the court's own filename — what /court-documents/fetch needs
                    "court_filename": fname,
                    "new": label,
                    "text": f"{label} dated {when or '—'} is available"})

    # --- the business/history rows behind the order sheet
    seen_h = {_hearing_key(h) for h in _rows(stored, "hearings")}
    for h in _rows(fresh, "hearings"):
        k = _hearing_key(h)
        if k in seen_h or not h.get("date"):
            continue
        out.append({"kind": "new_hearing", "date": h.get("date"),
                    "new": _norm(h.get("purpose")) or None,
                    "text": (f"Hearing recorded {h.get('date')}"
                             + (f" — {_norm(h.get('purpose'))}" if _norm(h.get("purpose")) else ""))})

    # --- disposal is the one status change that ends the matter
    o_st, n_st = _norm(stored.get("case_status")).lower(), _norm(fresh.get("case_status"))
    if n_st and n_st.lower() != o_st and "dispos" in n_st.lower():
        out.append({"kind": "disposed", "old": stored.get("case_status"), "new": n_st,
                    "text": f"Case shows as {n_st}"})

    o_last, n_last = _norm(stored.get("last_order")), _norm(fresh.get("last_order"))
    if n_last and n_last != o_last and not any(u["kind"] == "new_order" for u in out):
        out.append({"kind": "last_order", "old": o_last or None, "new": n_last,
                    "text": f"Order sheet: {n_last[:160]}"})

    return out


def merge(stored_case_json: dict, fresh: dict, updates: list[dict]) -> dict:
    """Fold a fresh fetch into the stored payload and append the updates inbox.

    The lawyer's own additions live under keys the court never sends (client,
    prep, last_listed_date), so those are preserved rather than overwritten by a
    payload that simply doesn't carry them.
    """
    merged = dict(stored_case_json or {})
    keep = {k: merged.get(k) for k in ("client", "prep", "last_listed_date") if k in merged}

    for k, v in (fresh or {}).items():
        if v in (None, "", [], {}):
            continue                      # never let a blank field erase what we hold
        merged[k] = v
    merged.update({k: v for k, v in keep.items() if v is not None})

    if updates:
        inbox = [u for u in (merged.get("updates") or []) if isinstance(u, dict)]
        stamped = [{**u, "at": _now(), "seen": False} for u in updates]
        merged["updates"] = (stamped + inbox)[:_MAX_UPDATES]
    merged["synced_at"] = _now()

    # keep prep.purpose in step with the court, unless the lawyer overrode it
    prep = dict(merged.get("prep") or {})
    court_purpose = purpose_from(merged)
    if court_purpose and not prep.get("purpose_manual"):
        prep["purpose"] = court_purpose
    merged["prep"] = prep
    return merged


def unseen(case_json: dict) -> list[dict]:
    ups = (case_json or {}).get("updates") or []
    return [u for u in ups if isinstance(u, dict) and not u.get("seen")]


# ---------------------------------------------------------------- one matter
def case_json_of(case: dict) -> dict:
    """`case_json` as a dict, whether storage handed it back parsed or as text."""
    cj = (case or {}).get("case_json") or {}
    if isinstance(cj, str):
        try:
            import json as _j
            cj = _j.loads(cj)
        except Exception:  # noqa: BLE001
            cj = {}
    return cj if isinstance(cj, dict) else {}


def sync_case(case: dict, user_id: str, *, trust_listing: bool = False) -> dict:
    """Re-read one matter from the court and fold in what changed.

    This is the single implementation behind BOTH the per-file sync button and
    the daily sweep — they must never drift, because a lawyer comparing the two
    would have no way to tell which one was lying.

    `trust_listing=True` means a cause-list entry has already settled the next
    date, so the case FILE's date is ignored here. That date is only as fresh as
    the last time the file was written; reporting it would tell the lawyer his
    hearing had moved BACKWARDS to a date the court has already superseded, and
    show two contradictory "next date" lines in the same inbox.

    Returns {id, ok, updates[], reason?}. Never raises: one unreachable matter
    must not take down a sweep over somebody's whole docket.
    """
    from headnote import config
    from headnote.cases import ecourts_client, storage as cases_storage

    # In mock mode the adapter returns the SAME fixture for every CNR. Folding
    # that into a real matter would overwrite its parties, title and dates with
    # someone else's data — so refuse rather than corrupt the file.
    if (config.CNR_API_MODE or "").lower() != "live":
        return {"id": case["id"], "ok": False,
                "reason": "court sync is off (CNR_API_MODE is not 'live')", "updates": []}
    cnr = (case.get("cnr") or "").strip()
    if not ecourts_client.is_valid_cnr(cnr):
        return {"id": case["id"], "ok": False, "reason": "no fetchable CNR", "updates": []}
    try:
        fresh = ecourts_client.fetch_cnr(cnr)
    except Exception as e:  # noqa: BLE001 — one bad matter must not fail the batch
        log.warning("court sync failed for %s: %s", cnr, e)
        return {"id": case["id"], "ok": False, "reason": str(e)[:200], "updates": []}

    stored = case_json_of(case)
    ups = diff(stored, fresh)
    if trust_listing:
        ups = [u for u in ups if u.get("kind") != "next_date"]
        fresh = {k: v for k, v in fresh.items() if k != "next_hearing_date"}
    merged = merge(stored, fresh, ups)

    payload = dict(merged)
    payload["cnr"] = cnr
    if trust_listing:
        payload["next_hearing_date"] = case.get("next_hearing_date")
    cases_storage.replace_case_identity(case["id"], user_id=user_id, case=payload)
    if fresh.get("next_hearing_date") or fresh.get("stage"):
        cases_storage.set_next_date(
            case["id"], user_id=user_id,
            next_hearing_date=None if trust_listing else fresh.get("next_hearing_date"),
            stage=fresh.get("stage"))
    return {"id": case["id"], "ok": True, "updates": ups, "purpose": purpose_from(merged)}


import re as _re
# Cause-list wording that carries no information about what the hearing is for.
_VAGUE_PURPOSE = _re.compile(r"not\s*defined|miscellan|misc\.|others?$|routine", _re.I)

# --------------------------------------------------------- the court's own board
def apply_listing(case: dict, listing: dict, user_id: str) -> dict:
    """Fold one cause-list entry into a matter.

    The cause list is the court's own board, so it outranks the case record's
    `next_hearing_date` (which is only as fresh as the last time the case file
    was written). It also carries what no case record has — the court number,
    the item/serial on that board, the judge sitting, and what it is listed for.

    Returns {id, ok, updates[]}. Never raises.
    """
    from headnote.cases import storage as cases_storage

    ups: list[dict] = []
    new_date = listing.get("date")
    old_date = case.get("next_hearing_date")
    if new_date and case_dates.to_iso(new_date) != case_dates.to_iso(old_date):
        # `text` is the key the update inbox renders — using anything else here
        # produced rows that were present but blank on Home.
        ups.append({"kind": "next_date", "old": old_date, "new": new_date,
                    "source": "causelist",
                    "text": (f"Listed for {new_date}"
                             + (f" (was {old_date})" if old_date else "")
                             + (f" · court no. {listing['court_no']}" if listing.get("court_no") else "")
                             + (f" · item {listing['item']}" if listing.get("item") is not None else ""))})

    cj = case_json_of(case)
    prep = dict(cj.get("prep") or {})

    # The court's wording for what the hearing is FOR — unless the lawyer has
    # written their own purpose by hand, which always wins.
    new_purpose = listing.get("purpose")
    # Some boards carry boilerplate that literally says nothing ("Miscellanceous
    # matters not defined otherwise" — the vendor's spelling). Letting that
    # overwrite a real purpose off the case record would drop readiness to
    # "Review" and lose what we already knew the hearing was for.
    if new_purpose and _VAGUE_PURPOSE.search(new_purpose):
        new_purpose = None
    if new_purpose and not prep.get("purpose_manual") and prep.get("purpose") != new_purpose:
        ups.append({"kind": "purpose", "old": prep.get("purpose"), "new": new_purpose,
                    "source": "causelist",
                    "text": f"Listed for “{new_purpose}”"})
        prep["purpose"] = new_purpose

    # Board position: which court room, and what number he is on that board.
    if listing.get("item") is not None and prep.get("item") != listing["item"]:
        prep["item"] = listing["item"]
    for k in ("court_no", "judge", "bench", "list_type"):
        if listing.get(k):
            prep[k] = listing[k]
    prep["listed_on"] = new_date
    prep["listing_seen_at"] = _now()

    try:
        if ups:
            # Same inbox the per-file sync writes to, so Home shows one stream.
            # This MUST happen before set_next_date: replace_case_identity mirrors
            # case_json["next_hearing_date"] into the column, so writing the date
            # first and the json second put the stale case-file date straight back
            # over the court's own board — observed doing exactly that.
            merged = dict(cj)
            inbox = [u for u in (merged.get("updates") or []) if isinstance(u, dict)]
            merged["updates"] = ([{**u, "at": _now(), "seen": False} for u in ups] + inbox)[:_MAX_UPDATES]
            merged["prep"] = prep
            merged["synced_at"] = _now()
            if new_date:
                merged["next_hearing_date"] = new_date
            merged["cnr"] = case.get("cnr")
            cases_storage.replace_case_identity(case["id"], user_id=user_id, case=merged)

        cases_storage.merge_prep(case["id"], user_id=user_id, prep=prep)
        if new_date:
            cases_storage.set_next_date(case["id"], user_id=user_id,
                                        next_hearing_date=new_date, stage=None)
    except Exception as e:  # noqa: BLE001 — one matter must not sink a sweep
        log.warning("apply_listing failed for %s: %s", case.get("cnr"), e)
        return {"id": case["id"], "ok": False, "reason": str(e)[:200], "updates": []}

    return {"id": case["id"], "ok": True, "updates": ups}
