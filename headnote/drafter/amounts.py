"""Rupee amounts the way a filing writes them — "₹1,12,080" and
"एक लाख बारह हजार अस्सी रुपये" / "Rupees One Lakh Twelve Thousand Eighty".

Deterministic: an amount in words is arithmetic, not drafting, and a junior who
types it by hand gets it wrong exactly when it matters (a §138 complaint whose
figure and words disagree invites an objection). Indian grouping (lakh, crore).
"""
from __future__ import annotations

import re
from typing import Optional

_HI = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस "
       "बीस इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस "
       "पैंतीस छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस "
       "सैंतालीस अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ "
       "इकसठ बासठ तिरसठ चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर "
       "पचहत्तर छिहत्तर सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी "
       "अट्ठासी नवासी नब्बे इक्यानवे बानवे तिरानवे चौरानवे पचानवे छियानवे सत्तानवे अट्ठानवे निन्यानवे").split()
_EN_ONES = ("Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve Thirteen Fourteen Fifteen "
            "Sixteen Seventeen Eighteen Nineteen").split()
_EN_TENS = "_ _ Twenty Thirty Forty Fifty Sixty Seventy Eighty Ninety".split()

assert len(_HI) == 100


def parse(value) -> Optional[int]:
    """"₹ 1,12,080/-", "75000", "2.5 lakh" → whole rupees; None when it is not an amount."""
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(lakh|lac|लाख|crore|करोड़|thousand|हजार|हज़ार)?", s, re.I)
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    unit = (m.group(2) or "").lower()
    n *= {"lakh": 1e5, "lac": 1e5, "लाख": 1e5, "crore": 1e7, "करोड़": 1e7,
          "thousand": 1e3, "हजार": 1e3, "हज़ार": 1e3}.get(unit, 1)
    if n <= 0 or n >= 1e12:
        return None
    return int(round(n))


def group(n: int) -> str:
    """Indian digit grouping: 11208000 → 1,12,08,000."""
    s = str(int(n))
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts) + "," + tail


def display(n: int, lang: str) -> str:
    return (f"₹{group(n)}" if lang == "hi" else f"Rs. {group(n)}")


def _below_1000_hi(n: int) -> str:
    out = []
    if n >= 100:
        out.append(f"{_HI[n // 100]} सौ")
        n %= 100
    if n:
        out.append(_HI[n])
    return " ".join(out)


def _below_1000_en(n: int) -> str:
    out = []
    if n >= 100:
        out.append(f"{_EN_ONES[n // 100]} Hundred")
        n %= 100
    if n >= 20:
        out.append(_EN_TENS[n // 10] + ("" if n % 10 == 0 else " " + _EN_ONES[n % 10]))
    elif n:
        out.append(_EN_ONES[n])
    return " ".join(out)


def words(n: int, lang: str) -> str:
    """The amount in words, Indian system, the way a filing states it."""
    n = int(n)
    if n <= 0:
        return ""
    units = [(10 ** 7, "करोड़", "Crore"), (10 ** 5, "लाख", "Lakh"), (10 ** 3, "हजार", "Thousand")]
    parts = []
    rest = n
    for size, hi, en in units:
        q, rest = divmod(rest, size)
        if q:
            # beyond 99 crore the crore count itself needs words ("एक सौ पाँच करोड़")
            count = (_below_1000_hi(q) if lang == "hi" else _below_1000_en(q)) if q < 1000 else words(q, lang).replace(" रुपये", "").replace("Rupees ", "")
            parts.append(f"{count} {hi if lang == 'hi' else en}")
    if rest:
        parts.append(_below_1000_hi(rest) if lang == "hi" else _below_1000_en(rest))
    body = " ".join(parts)
    return f"{body} रुपये" if lang == "hi" else f"Rupees {body}"
