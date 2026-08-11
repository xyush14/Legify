"""The exact words of a hearing reminder — assembled, never authored.

WHY THERE IS NO MODEL CALL IN THIS FILE
A reminder carries one fact the client acts on: the date he must stand in court.
Get it wrong and he travels on the wrong day, loses a day's wages, and concludes
his advocate is careless. A language model that is right 99 times out of 100 is
still the wrong tool for that sentence. So every reminder is a FIXED string with
values substituted from the matter's own stored fields.

THE SHAPE IS A WHATSAPP TEMPLATE, DELIBERATELY
Messaging a client is business-initiated, so WhatsApp will only carry it as a
pre-approved "utility template": a fixed body with numbered placeholders that
Meta has seen and cleared. That constraint is the reason the copy lives here as
a body plus an ordered list of 7 variables rather than as free prose — the same
render() feeds both lanes, so what the lawyer previews on screen is exactly what
the client receives whichever lane sends it.

Meta's rules on a template body, all satisfied below: it may not begin or end
with a placeholder, no two placeholders may sit adjacent, and every placeholder
must be filled with a non-empty value at send time.

  {{1}} client's name        {{5}} hearing date  (dd/mm/yyyy + weekday)
  {{2}} advocate's name      {{6}} when to reach the court
  {{3}} case number          {{7}} the advocate's own callback number
  {{4}} court

LANGUAGE
English is the fallback, never Hindi — a Hindi reminder to a Tamil client is
worse than an English one he can have read to him. Devanagari is the one genuine
ambiguity (Hindi and Marathi share the script); it resolves to Hindi as the
larger bar, and the sending screen lets the lawyer override per send.

hi and en are written to be sent as they stand. mr, gu and bn are drafted and
marked NEEDS_SIGNOFF: a practising advocate in that state should read them once
before they go to a client. Until then callers may still use them — the fields
they carry are numeric and script-independent, which is precisely why the date
is rendered dd/mm/yyyy rather than in month words.
"""

from __future__ import annotations

import re
from datetime import date as _date
from typing import Optional

# Languages whose wording a practising advocate in that state has not yet read.
NEEDS_SIGNOFF = ("mr", "gu", "bn")

SUPPORTED = ("en", "hi", "mr", "gu", "bn")

# How many placeholders the body carries. Asserted by the tests so a reworded
# body and the variable builder can never drift apart.
VAR_COUNT = 7


# ─────────────────────────────────────────────────────────── the bodies

# One entry per language. {{n}} markers are Meta's own placeholder syntax and are
# kept verbatim so the string here IS the string registered with Meta.
_BODY: dict[str, str] = {
    "en": (
        "Namaste {{1}}, a hearing reminder from the office of Adv. {{2}}.\n"
        "\n"
        "Case {{3}} is listed in {{4}} on {{5}}.\n"
        "Please reach the court {{6}}.\n"
        "\n"
        "If you cannot come, please call {{7}} beforehand."
    ),
    "hi": (
        "नमस्ते {{1}}, अधिवक्ता {{2}} के कार्यालय से सुनवाई की सूचना।\n"
        "\n"
        "प्रकरण {{3}} की सुनवाई {{4}} में {{5}} को है।\n"
        "कृपया न्यायालय {{6}} पहुँचें।\n"
        "\n"
        "यदि आप नहीं आ सकते, तो पहले {{7}} पर फ़ोन करें।"
    ),
    "mr": (
        "नमस्कार {{1}}, अधिवक्ता {{2}} यांच्या कार्यालयाकडून सुनावणीची सूचना.\n"
        "\n"
        "प्रकरण {{3}} ची सुनावणी {{4}} मध्ये {{5}} रोजी आहे.\n"
        "कृपया न्यायालयात {{6}} पोहोचा.\n"
        "\n"
        "आपण येऊ शकत नसल्यास, आधी {{7}} वर फोन करा."
    ),
    "gu": (
        "નમસ્તે {{1}}, અધિવક્તા {{2}} ની ઓફિસ તરફથી સુનાવણીની જાણ.\n"
        "\n"
        "કેસ {{3}} ની સુનાવણી {{4}} માં {{5}} ના રોજ છે.\n"
        "કૃપા કરીને અદાલતમાં {{6}} પહોંચો.\n"
        "\n"
        "જો તમે ન આવી શકો, તો પહેલાં {{7}} પર ફોન કરો."
    ),
    "bn": (
        "নমস্কার {{1}}, আইনজীবী {{2}} এর অফিস থেকে শুনানির খবর।\n"
        "\n"
        "মামলা {{3}} এর শুনানি {{4}} এ {{5}} তারিখে আছে।\n"
        "অনুগ্রহ করে আদালতে {{6}} পৌঁছান।\n"
        "\n"
        "আপনি আসতে না পারলে, আগে {{7}} নম্বরে ফোন করুন।"
    ),
}

# Variable 6 — when to reach. Two forms: a real time off the court's cause list,
# or the honest general instruction when the court gave none. Never invent a time.
_BY_TIME: dict[str, str] = {
    "en": "by {t}",
    "hi": "{t} तक",
    "mr": "{t} पर्यंत",
    "gu": "{t} સુધીમાં",
    "bn": "{t} এর মধ্যে",
}
_MORNING: dict[str, str] = {
    "en": "in the morning",
    "hi": "सुबह",
    "mr": "सकाळी",
    "gu": "સવારે",
    "bn": "সকালে",
}

_WEEKDAY: dict[str, tuple[str, ...]] = {
    "en": ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"),
    "hi": ("सोमवार", "मंगलवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"),
    "mr": ("सोमवार", "मंगळवार", "बुधवार", "गुरुवार", "शुक्रवार", "शनिवार", "रविवार"),
    "gu": ("સોમવાર", "મંગળવાર", "બુધવાર", "ગુરુવાર", "શુક્રવાર", "શનિવાર", "રવિવાર"),
    "bn": ("সোমবার", "মঙ্গলবার", "বুধবার", "বৃহস্পতিবার", "শুক্রবার", "শনিবার", "রবিবার"),
}

# Court-room line, appended only when the court's own cause list gave us a room.
_ROOM: dict[str, str] = {
    "en": "Court no. {n}",
    "hi": "कोर्ट नं. {n}",
    "mr": "कोर्ट क्र. {n}",
    "gu": "કોર્ટ નં. {n}",
    "bn": "কোর্ট নং {n}",
}


def lang_of(*texts: Optional[str]) -> str:
    """Pick the reminder language from the script the matter is already written in.

    Deterministic and per-client: a Gwalior advocate's clients have Devanagari
    names, a Rajkot advocate's have Gujarati ones. Latin or unrecognised script
    resolves to English — never to Hindi, which would be actively wrong for a
    Chennai or Kochi client.
    """
    blob = " ".join(t for t in texts if t)
    if re.search(r"[઀-૿]", blob):      # Gujarati
        return "gu"
    if re.search(r"[ঀ-৿]", blob):      # Bengali / Assamese
        return "bn"
    if re.search(r"[ऀ-ॿ]", blob):
        # Devanagari carries both Hindi and Marathi and the script cannot tell
        # them apart. Hindi is the larger bar; the sending screen offers the
        # override so a Maharashtra advocate fixes it once, per send.
        return "hi"
    return "en"


def normalise(lang: Optional[str]) -> str:
    l = (lang or "").strip().lower()[:2]
    return l if l in SUPPORTED else "en"


def body(lang: str) -> str:
    """The registered template body, placeholders intact. This is the exact string
    to file with Meta for this language."""
    return _BODY[normalise(lang)]


# ─────────────────────────────────────────────────────────── the variables


def _weekday(iso: str, lang: str) -> str:
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        return _WEEKDAY[lang][_date(y, m, d).weekday()]
    except Exception:  # noqa: BLE001 — an unparseable date just loses the weekday
        return ""


def date_phrase(iso: str, lang: str) -> str:
    """dd/mm/yyyy plus the weekday in words.

    Numeric-first on purpose. dd/mm/yyyy is how every Indian court writes a date
    and how eCourts returns one, so it cannot be misread even where our wording
    for that language has not been signed off yet. The weekday is the check that
    catches a typo: a client who reads "13/08/2026, गुरुवार" and knows Thursday
    is his market day will query it, where a bare number slides past.
    """
    lang = normalise(lang)
    try:
        y, m, d = (int(x) for x in iso.split("-"))
        numeric = f"{d:02d}/{m:02d}/{y:04d}"
    except Exception:  # noqa: BLE001
        return iso or ""
    wd = _weekday(iso, lang)
    return f"{numeric}, {wd}" if wd else numeric


def arrival(lang: str, *, time: Optional[str] = None) -> str:
    """Variable 6. A real listed time when the court published one, else the plain
    general instruction — we do not guess a time the court did not give."""
    lang = normalise(lang)
    t = (time or "").strip()
    return _BY_TIME[lang].format(t=t) if t else _MORNING[lang]


def court_phrase(lang: str, *, court: Optional[str], court_no: Optional[str] = None) -> str:
    """Variable 4 — the court, plus its room number when the cause list gave one."""
    lang = normalise(lang)
    c = (court or "").strip()
    n = str(court_no or "").strip()
    if c and n:
        return f"{c} ({_ROOM[lang].format(n=n)})"
    return c


def variables(*, client_name: str, advocate_name: str, case_number: str,
              court: str, hearing_iso: str, advocate_phone: str,
              lang: str, time: Optional[str] = None,
              court_no: Optional[str] = None) -> list[str]:
    """The 7 placeholder values, in Meta's order.

    Every one is a stored field of the matter or the advocate's own profile. The
    caller is responsible for having refused to send when any of them is empty —
    see service.py, which reports the gap to the lawyer instead of substituting
    something plausible.
    """
    lang = normalise(lang)
    return [
        client_name.strip(),
        advocate_name.strip(),
        case_number.strip(),
        court_phrase(lang, court=court, court_no=court_no),
        date_phrase(hearing_iso, lang),
        arrival(lang, time=time),
        advocate_phone.strip(),
    ]


def render(lang: str, vars_: list[str]) -> str:
    """Substitute the variables into the body — the plain-text form of the very
    same message the template lane sends, so the preview cannot lie about it."""
    out = body(lang)
    for i, v in enumerate(vars_, start=1):
        out = out.replace("{{%d}}" % i, v)
    return out


def missing_vars(vars_: list[str]) -> list[int]:
    """1-based positions that are empty. Meta rejects a template with a blank
    placeholder, and a message reading 'listed in  on ' is worse than none —
    so this is checked before a send, not after a failure."""
    return [i for i, v in enumerate(vars_, start=1) if not (v or "").strip()]
