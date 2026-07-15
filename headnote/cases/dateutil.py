"""Date normalisation for the diary.

Case dates arrive in mixed shapes — dd/mm/yyyy and dd.mm.yyyy from the mock +
eCourts, ISO (yyyy-mm-dd) from our own writes, and sometimes Devanagari digits.
The diary groups matters by hearing date, so everything is coerced to ISO
(yyyy-mm-dd) for grouping. Anything unparseable returns None → the UI files it
under an "undated" bucket rather than crashing the whole diary.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Optional

# Devanagari → ASCII digit map (eCourts Hindi rows sometimes carry these).
_DEVA = {ord("०"): "0", ord("१"): "1", ord("२"): "2", ord("३"): "3",
         ord("४"): "4", ord("५"): "5", ord("६"): "6", ord("७"): "7",
         ord("८"): "8", ord("९"): "9"}

_ISO_RE = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})")
# dd/mm/yyyy or dd-mm-yyyy or dd.mm.yyyy (day-first — Indian convention).
_DMY_RE = re.compile(r"^(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{2,4})")


def to_iso(value) -> Optional[str]:
    """Best-effort parse of a date string → 'YYYY-MM-DD', else None."""
    if not value:
        return None
    if isinstance(value, (datetime, date)):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip().translate(_DEVA)
    if not s:
        return None

    m = _ISO_RE.match(s)
    if m:
        y, mo, d = (int(g) for g in m.groups())
    else:
        m = _DMY_RE.match(s)
        if not m:
            return None
        d, mo, y = (int(g) for g in m.groups())
        if y < 100:                 # 2-digit year → 20xx
            y += 2000
    try:
        return date(y, mo, d).strftime("%Y-%m-%d")
    except ValueError:
        return None


def today_iso() -> str:
    return date.today().strftime("%Y-%m-%d")


def week_window(anchor_iso: Optional[str] = None, *, days: int = 7) -> tuple[str, str]:
    """Return (from_iso, to_iso) for a `days`-long window starting at anchor
    (default today). Used for the diary week strip."""
    start = _parse_or_today(anchor_iso)
    return start.strftime("%Y-%m-%d"), (start + timedelta(days=days - 1)).strftime("%Y-%m-%d")


def date_range(from_iso: str, to_iso_: str) -> list[str]:
    """Inclusive list of ISO dates from → to (capped at 60 days for safety)."""
    a, b = _parse_or_today(from_iso), _parse_or_today(to_iso_)
    if b < a:
        a, b = b, a
    out, cur = [], a
    while cur <= b and len(out) < 60:
        out.append(cur.strftime("%Y-%m-%d"))
        cur += timedelta(days=1)
    return out


def _parse_or_today(iso: Optional[str]) -> date:
    if iso:
        parsed = to_iso(iso)
        if parsed:
            y, mo, d = (int(g) for g in parsed.split("-"))
            return date(y, mo, d)
    return date.today()
