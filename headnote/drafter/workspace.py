"""The drafting workspace — everything the /draft screen needs, as plain functions.

The screen is two panes: the case details on the left (the reviewed template's
OWN fields, pre-filled from the brief by `intake`), the document on the right,
re-rendered by the reviewed canonical engine on every change. Nothing here calls a
model except `enrich`, and `enrich` can only ADD a value the brief states.

    catalog(lang)                    the documents he can start from, grouped the way a chamber thinks
    schema(tid)                      the template's fields, grouped, labelled in English (Hindi alongside)
    preview(tid, fields, lang)       the document HTML with every empty blank clickable, + progress
    export_fields(tid, fields)       the same fields with filing-style blanks, for Word / print
    checks(tid, fields, lang, ev)    the junior's note: what is missing, assumed, or legally off
    enrich(brief, tid, lang, fields) a model's reading of the brief — grounded against the brief or dropped
    matter_brief(row)                a matter from his diary, written out as a brief the engine can read
"""
from __future__ import annotations

import difflib
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

from headnote.drafter import intake as IN
from headnote.drafter import template_adapter as TA

log = logging.getLogger("headnote.drafter.workspace")

# ---------------------------------------------------------------------------- catalog
# One tile per DOCUMENT. The court is a switch inside the workspace, not a separate
# tile — "Regular bail" is one thing he files, in whichever court.
_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    ("Bail & custody", [
        ("bail_sessions", "Regular bail", "जमानत आवेदन"),
        ("anticipatory_bail", "Anticipatory bail", "अग्रिम जमानत"),
        ("default_bail", "Default bail", "डिफॉल्ट जमानत"),
        ("suspension_389", "Suspension of sentence", "दण्डादेश निलंबन"),
        ("supurdgi", "Release of seized property", "सुपुर्दगी"),
        ("production_warrant", "Production warrant", "उत्पादन वारंट"),
    ]),
    ("Criminal trial", [
        ("discharge_sessions", "Discharge", "उन्मोचन"),
        ("exemption_205", "Exemption from appearance", "हाजिरी माफी"),
        ("production_magistrate", "Summon documents (S.94/91)", "दस्तावेज तलब"),
        ("recall_311", "Recall a witness", "साक्षी पुनः परीक्षण"),
        ("compounding", "Compromise / compounding", "राजीनामा"),
        ("reply_magistrate", "Reply", "जवाब"),
        ("statement_178", "Record statement", "कथन दर्ज"),
    ]),
    ("Complaints & notices", [
        ("cheque_138", "Cheque bounce complaint (S.138)", "चेक बाउंस परिवाद"),
        ("legal_notice", "Legal notice", "विधिक सूचना पत्र"),
        ("complaint_156", "FIR direction to police", "धारा 175(3) आवेदन"),
        ("parivad", "Private complaint", "परिवाद पत्र"),
        ("ni_138_dismiss", "S.138 — notice not served (accused)", "138 — सूचना तामील आपत्ति"),
    ]),
    ("Family", [
        ("maintenance", "Maintenance", "भरण-पोषण"),
        ("dv", "Domestic violence", "घरेलू हिंसा"),
        ("divorce_13", "Divorce", "विवाह विच्छेद"),
        ("restitution_9", "Restitution of conjugal rights", "दाम्पत्य पुनर्स्थापना"),
    ]),
    ("Appeals & High Court", [
        ("appeal_sessions", "Criminal appeal", "आपराधिक अपील"),
        ("revision_sessions", "Criminal revision", "पुनरीक्षण"),
        ("quashing", "Quashing (S.528 / 482)", "अभिखण्डन"),
        ("writ_petition", "Writ petition", "रिट याचिका"),
        ("habeas_corpus", "Habeas corpus", "बन्दी प्रत्यक्षीकरण"),
        ("stay_petition", "Stay application", "स्थगन आवेदन"),
        ("transfer_petition", "Transfer petition", "स्थानान्तरण"),
        ("mention_memo", "Mention memo", "स्मरण पत्र"),
    ]),
    ("Civil", [
        ("recovery_suit", "Recovery of money", "धन वसूली वाद"),
        ("injunction_suit", "Permanent injunction", "निषेधाज्ञा वाद"),
        ("specific_performance", "Specific performance", "विनिर्दिष्ट अनुपालन"),
        ("declaration_suit", "Declaration", "घोषणा वाद"),
        ("partition_suit", "Partition", "बंटवारा वाद"),
        ("eviction_suit", "Eviction & rent", "बेदखली वाद"),
        ("written_statement", "Written statement", "जवाबदावा"),
        ("consumer_complaint", "Consumer complaint", "उपभोक्ता परिवाद"),
        ("mact_166", "Motor accident claim", "दुर्घटना दावा"),
    ]),
    ("General", [
        ("vakalatnama", "Vakalatnama", "वकालतनामा"),
        ("general_affidavit", "Affidavit", "शपथ पत्र"),
    ]),
]

_COURT_LABEL = {"sessions": "Sessions Court", "magistrate": "Magistrate", "hc": "High Court",
                "family": "Family Court", "civil": "Civil Court", "consumer": "Consumer Commission", "any": ""}


def _short(tid: str) -> tuple[str, str]:
    for _g, items in _GROUPS:
        for t, en, hi in items:
            if t == tid:
                return en, hi
    base = TA.CANONICAL_MAP.get(tid, (tid,))[0]
    for _g, items in _GROUPS:
        for t, en, hi in items:
            if TA.CANONICAL_MAP.get(t, ("",))[0] == base and TA.CANONICAL_MAP[t][2] == TA.CANONICAL_MAP[tid][2]:
                return en, hi
    lab = TA.LABELS.get(tid, {"en": tid, "hi": tid})
    return lab["en"], lab["hi"]


def variants(tid: str) -> list[dict]:
    """The same document in the other courts it has a reviewed template for."""
    if tid not in TA.CANONICAL_MAP:
        return []
    base, _court, bt = TA.CANONICAL_MAP[tid]
    out = []
    for t, (b, c, v) in TA.CANONICAL_MAP.items():
        if b == base and v == bt:
            out.append({"tid": t, "court": c, "label": _COURT_LABEL.get(c, c)})
    order = {"magistrate": 0, "family": 0, "civil": 0, "sessions": 1, "hc": 2}
    return sorted(out, key=lambda x: order.get(x["court"], 3)) if len(out) > 1 else []


def title(tid: str) -> dict:
    en, hi = _short(tid)
    court = TA.CANONICAL_MAP.get(tid, ("", "", ""))[1]
    return {"tid": tid, "name": en, "name_hi": hi, "court": court,
            "court_label": _COURT_LABEL.get(court, ""), "full": TA.LABELS.get(tid, {}).get("en", en)}


def catalog() -> list[dict]:
    groups = []
    for g, items in _GROUPS:
        groups.append({"group": g, "items": [
            {"tid": t, "name": en, "name_hi": hi, "courts": [v["label"] for v in variants(t)]}
            for t, en, hi in items if TA.is_canonical(t)]})
    return groups


# ---------------------------------------------------------------------------- schema
_SECTION_LABELS = {
    "court": "Court", "parties": "Parties", "applicant": "Applicant", "respondent": "Respondent",
    "fir": "FIR & offence", "crime": "FIR & offence", "custody": "Custody", "order": "Order challenged",
    "conviction": "Conviction", "marriage": "Marriage & family", "income": "Income",
    "facts": "Facts", "grounds": "Grounds", "filing": "Filing",
}
_SECTION_ORDER = ["parties", "applicant", "respondent", "fir", "crime", "custody", "order", "conviction",
                  "marriage", "income", "facts", "court", "grounds", "filing"]


_ROLE_KEY = re.compile(r"^(applicant|accused|complainant|petitioner|respondent|respondents|plaintiff|defendant|appellant|"
                       r"revisionist|aggrieved|deponent|client|recipient|claimant|detenu|husband)_")
_ROLE_NAMES = {"applicant": "Applicant", "accused": "Accused", "complainant": "Complainant",
               "petitioner": "Petitioner", "respondent": "Respondent", "respondents": "Respondents",
               "plaintiff": "Plaintiff", "defendant": "Defendant", "appellant": "Appellant",
               "revisionist": "Revisionist", "aggrieved": "Aggrieved person", "deponent": "Deponent",
               "client": "Client", "recipient": "Recipient", "claimant": "Claimant", "detenu": "Detenu",
               "husband": "Husband"}
_GENERIC = re.compile(r"^(?:name|father|father/husband|father's name|father's/husband's name|father/husband name|age|"
                      r"occupation|address|present address|spouse name)", re.I)


def _party_label(key: str, label: str) -> str:
    """"Address" → "Accused's address" wherever the label alone does not say whose."""
    m = _ROLE_KEY.match(key)
    if not m or not _GENERIC.match(label.strip()):
        return label
    return f"{_ROLE_NAMES.get(m.group(1), m.group(1).title())}'s {label[0].lower() + label[1:]}"


def _safe_default(f: dict):
    """A reviewed spec may carry one advocate's town as a default ("place":
    "ग्वालियर"). A default is only kept when it is not a place or a person —
    an advocate in Patna must never find Gwalior pre-filled on his filing."""
    d = f.get("default")
    if d is None or f["type"] in ("toggle", "select", "number"):
        return d
    if isinstance(d, str) and (f["type"] in ("name", "address") or
                               re.search(r"place|city|court|district|station|name", f["key"])):
        return None
    return d


def schema(tid: str) -> dict:
    """The reviewed field_spec, grouped for the screen. Toggles become the Grounds
    group; fields that are derived by the engine never appear."""
    s = TA.schema(tid)
    spec = TA._spec(tid)
    hints = {t["key"]: t.get("hint", "") for t in spec.get("toggles", [])}
    groups: dict[str, list] = {}
    for f in s["fields"]:
        sec = "grounds" if f["type"] == "toggle" else (f.get("section") or "facts")
        sec = "fir" if sec == "crime" else sec
        groups.setdefault(sec, []).append({
            "key": f["key"], "label": f["label_en"], "label_hi": f["label_hi"], "type": f["type"],
            "required": bool(f.get("required")), "hint": f.get("hint") or hints.get(f["key"], ""),
            "options": f.get("options"), "default": _safe_default(f), "depends": f.get("depends"),
        })
    # "Parties" mixes both sides under identical labels ("Address", "Age") — split
    # it into one group per party so he always knows whose address he is typing
    if "parties" in groups:
        by_role: dict[str, list] = {}
        rest = []
        for fl in groups.pop("parties"):
            m = _ROLE_KEY.match(fl["key"])
            if m:
                by_role.setdefault(m.group(1), []).append(fl)
            else:
                rest.append(fl)
        for role, fl in by_role.items():
            groups[f"party:{role}"] = fl
        if rest:
            groups["court"] = rest + groups.get("court", [])
    for sid in list(groups):
        if sid.startswith("party:"):
            role = sid.split(":", 1)[1]
            for fl in groups[sid]:
                fl["label"] = _party_label(fl["key"], fl["label"])
    party_ids = [sid for sid in groups if sid.startswith("party:")]
    ordered = [{"id": sid, "label": _ROLE_NAMES.get(sid.split(":", 1)[1], sid.split(":", 1)[1].title()),
                "fields": groups[sid]} for sid in party_ids]
    def sec_label(sid: str) -> str:
        if sid == "fir":
            ks = {fl["key"] for fl in groups[sid]}
            if not ks & {"fir_number", "crime_number", "police_station", "sections", "fir_sections", "offence_sections"}:
                return "Cheque & transaction" if "cheque_no" in ks else "Details"
        return _SECTION_LABELS.get(sid, sid.title())
    ordered += [{"id": sid, "label": sec_label(sid), "fields": groups[sid]}
                for sid in _SECTION_ORDER if sid in groups]
    ordered += [{"id": sid, "label": _SECTION_LABELS.get(sid, sid.title()), "fields": fl}
                for sid, fl in groups.items() if sid not in _SECTION_ORDER and not sid.startswith("party:")]
    return {**title(tid), "sections": ordered, "variants": variants(tid)}


# ---------------------------------------------------------------------------- preview / export
_BLANKABLE_TYPES = {"text", "name", "address"}
# fields whose template default is the field's own NAME printed on the page
# ("व्यवसाय— व्यवसाय", "पुत्र श्री पिता") — in Word they get a proper filing blank
_EXPORT_BLANK = re.compile(r"(?:_name|_father|_occupation|_address|_spouse)$|^(?:police_station|district)$")
_FILING_BLANK = "__________"


def _field_map(tid: str) -> dict[str, dict]:
    return {f["key"]: f for f in TA.schema(tid)["fields"]}


def without_derived(tid: str, fields: dict) -> dict:
    """Drop values the engine derives for this template (court name, custody days …).
    A derived value carried over from another template — a Sessions court line
    arriving in a High Court bail — would otherwise override the engine and put
    the filing before the wrong court."""
    spec = TA._spec(tid)
    auto = {f["key"] for f in spec.get("fields", []) if f.get("auto")}
    return {k: v for k, v in (fields or {}).items() if k not in auto}


def _is_empty(v) -> bool:
    return v is None or (isinstance(v, str) and not v.strip()) or (isinstance(v, (list, dict)) and not v)


def preview(tid: str, fields: dict, lang: str = "hi") -> dict:
    """The document as he will file it, with every EMPTY name/address/text blank
    rendered as a clickable chip that names the field. Sentinels are digits in
    corner brackets — they pass through the templates' own transliteration and
    escaping untouched (verified on all 50 types, both languages)."""
    fmap = _field_map(tid)
    fields = dict(fields or {})
    toggles_on = {k for k, v in fields.items() if v is True}
    tokens: dict[str, str] = {}
    values = dict(fields)
    for key, f in fmap.items():
        if f["type"] not in _BLANKABLE_TYPES or key == "custom_grounds":
            continue
        if not f.get("required") and not _EXPORT_BLANK.search(key):
            continue
        if f.get("depends") and f["depends"] not in toggles_on:
            continue
        if _is_empty(values.get(key)):
            tok = f"〔{len(tokens)}〕"
            tokens[tok] = key
            values[key] = tok
    html = TA.document(tid, values, lang)

    def chip(m: re.Match) -> str:
        key = tokens.get(m.group(0))
        if not key:
            return ""
        label = fmap[key]["label_hi" if lang == "hi" else "label_en"]
        return f'<span class="hn-blank" data-k="{key}" title="Fill: {fmap[key]["label_en"]}">{label}</span>'

    html = re.sub(r"〔\d+〕", chip, html)
    return {"html": html, **progress(tid, fields)}


def progress(tid: str, fields: dict) -> dict:
    fmap = _field_map(tid)
    toggles_on = {k for k, v in (fields or {}).items() if v is True}
    req = [k for k, f in fmap.items() if f.get("required") and f["type"] != "toggle"
           and (not f.get("depends") or f["depends"] in toggles_on)]
    missing = [k for k in req if _is_empty((fields or {}).get(k))]
    return {"required": len(req), "filled": len(req) - len(missing), "missing": missing}


def export_fields(tid: str, fields: dict) -> dict:
    fmap = _field_map(tid)
    out = without_derived(tid, fields)
    toggles_on = {k for k, v in out.items() if v is True}
    for key, f in fmap.items():
        if f["type"] in _BLANKABLE_TYPES and _EXPORT_BLANK.search(key) and _is_empty(out.get(key)):
            if f.get("depends") and f["depends"] not in toggles_on:
                continue
            out[key] = _FILING_BLANK
    return out


# ---------------------------------------------------------------------------- derived values
def derive(tid: str, fields: dict, evidence: dict, lang: str) -> tuple[dict, dict]:
    """Values that are arithmetic on other values — kept in step on every render,
    but never over something he typed himself."""
    from headnote.drafter import amounts as AM
    fmap = _field_map(tid)
    fields, evidence = without_derived(tid, fields), dict(evidence or {})
    if "amount_words" in fmap:
        n = AM.parse(fields.get("amount"))
        mine = not _is_empty(fields.get("amount_words")) and (evidence.get("amount_words") or {}).get("source") != "computed"
        if n and not mine:
            fields["amount_words"] = AM.words(n, lang)
            evidence["amount_words"] = {"source": "computed", "span": "", "note": "Written out from the amount."}
        elif not n and (evidence.get("amount_words") or {}).get("source") == "computed":
            fields.pop("amount_words", None)
            evidence.pop("amount_words", None)
    return fields, evidence


# ---------------------------------------------------------------------------- the junior's note
def _parse(d: str) -> Optional[date]:
    m = re.match(r"^\s*(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})\s*$", str(d or ""))
    if not m:
        try:
            return datetime.strptime(str(d), "%Y-%m-%d").date()
        except Exception:
            return None
    dd, mm, yy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    yy = yy + 2000 if yy < 100 else yy
    try:
        return date(yy, mm, dd)
    except ValueError:
        return None


def _fmt(d: date) -> str:
    return d.strftime("%d/%m/%Y")


_NEW_CODES = date(2024, 7, 1)   # BNS / BNSS / BSA in force


def checks(tid: str, fields: dict, lang: str = "hi", evidence: Optional[dict] = None,
           today: Optional[date] = None) -> list[dict]:
    """Deterministic checks a careful junior would raise before the file goes out.
    Each: {level: 'fix'|'check'|'ok', key?, text}. No model."""
    today = today or date.today()
    fields = fields or {}
    ev = evidence or {}
    fmap = _field_map(tid)
    out: list[dict] = []

    prog = progress(tid, fields)
    for k in prog["missing"]:
        out.append({"level": "fix", "key": k, "text": f"{_party_label(k, fmap[k]['label_en'])} is not filled in."})

    converted = [k for k, e in ev.items() if e.get("source") == "converted" and k in fmap and not _is_empty(fields.get(k))]
    if converted:
        names = ", ".join(_party_label(k, fmap[k]["label_en"]) for k in converted)
        script = "Hindi" if lang == "hi" else "English"
        out.append({"level": "check", "key": converted[0],
                    "text": f"Converted to {script} from how you typed them — check the spelling: {names}."})
    for k, e in ev.items():
        if k not in fmap or _is_empty(fields.get(k)):
            continue
        if e.get("source") == "converted":
            continue
        elif e.get("source") == "inferred":
            out.append({"level": "check", "key": k, "text": e.get("note") or f"{fmap[k]['label_en']} was assumed — confirm it."})
        elif e.get("source") == "ai":
            out.append({"level": "check", "key": k,
                        "text": f"{fmap[k]['label_en']} was read from your brief by AI — confirm it."})

    # he typed English into a Hindi document (or Hindi into an English one)
    wrong_script = []
    for k, f in fmap.items():
        v = fields.get(k)
        if f["type"] in ("name", "address", "text") and isinstance(v, str) and v.strip() and k not in converted:
            has_latin, has_deva = bool(re.search(r"[A-Za-z]{3,}", v)), IN.is_deva(v)
            if (lang == "hi" and has_latin and not has_deva) or (lang == "en" and has_deva):
                wrong_script.append(k)
    if wrong_script:
        names = ", ".join(_party_label(k, fmap[k]["label_en"]) for k in wrong_script[:4])
        out.append({"level": "check", "key": wrong_script[0],
                    "text": (f"Typed in English on a Hindi document — it will print as typed: {names}."
                             if lang == "hi" else f"Typed in Hindi on an English document — it will print as typed: {names}.")})

    # dates in the future
    for k, f in fmap.items():
        if f["type"] == "date" and not _is_empty(fields.get(k)):
            d = _parse(fields[k])
            if d is None:
                out.append({"level": "fix", "key": k, "text": f"{f['label_en']} is not a valid date (use dd/mm/yyyy)."})
            elif d > today:
                out.append({"level": "fix", "key": k, "text": f"{f['label_en']} ({fields[k]}) is in the future."})

    # IPC vs BNS against the offence date
    sec_key = next((k for k in ("sections", "fir_sections", "offence_sections", "sections_convicted") if k in fmap), None)
    if sec_key and not _is_empty(fields.get(sec_key)):
        secs = fields[sec_key]
        text = " ".join(secs) if isinstance(secs, list) else str(secs)
        old = re.search(r"भा\.द\.वि\.|IPC|दं\.प्र\.सं\.|CrPC", text)
        new = re.search(r"भा\.न्या\.सं\.|BNS(?!S)|भा\.ना\.सु\.सं\.|BNSS", text)
        # the substantive law follows the date of the offence; the FIR date is the
        # nearest thing a form holds. An arrest or seizure can come much later, so
        # it is never used here.
        ref = _parse(fields.get("fir_date")) if fields.get("fir_date") else None
        fir = str(fields.get("fir_number") or fields.get("crime_number") or "")
        fy = re.search(r"/(\d{4})$", fir)
        if not old and not new:
            hint = ""
            if fy and int(fy.group(1)) >= 2025:
                hint = " The FIR is of " + fy.group(1) + ", so they will be under BNS."
            elif fy and int(fy.group(1)) <= 2023:
                hint = " The FIR is of " + fy.group(1) + ", so they will be under IPC."
            out.append({"level": "check", "key": sec_key, "text": "The sections do not say which Act." + hint})
        elif ref and old and ref >= _NEW_CODES and not new:
            out.append({"level": "check", "key": sec_key,
                        "text": f"Sections are under IPC but the date ({_fmt(ref)}) is after 1 July 2024, when BNS came in."})
        elif ref and new and ref < _NEW_CODES and not old:
            out.append({"level": "check", "key": sec_key,
                        "text": f"Sections are under BNS but the date ({_fmt(ref)}) is before 1 July 2024 — IPC would apply."})
        elif fy and old and int(fy.group(1)) >= 2025 and not new:
            out.append({"level": "check", "key": sec_key, "text": f"The FIR is of {fy.group(1)} but the sections are under IPC."})

    # custody so far
    if "arrest_date" in fmap and _parse(fields.get("arrest_date")):
        a = _parse(fields["arrest_date"])
        if a <= today:
            out.append({"level": "ok", "key": "arrest_date", "text": f"In custody for {(today - a).days} days (since {_fmt(a)})."})

    # §138 NI Act timeline — the dates a complaint lives or dies on
    if tid == "cheque_138":
        cd, dd, nd, kd = (_parse(fields.get(k)) for k in ("cheque_date", "dishonour_date", "notice_date", "notice_known_date"))
        if cd and dd:
            if dd > cd + timedelta(days=91):
                out.append({"level": "fix", "key": "dishonour_date",
                            "text": "The cheque was presented more than 3 months after its date — it was no longer valid (S.138 proviso (a))."})
        if dd and nd:
            gap = (nd - dd).days
            if gap > 30:
                out.append({"level": "fix", "key": "notice_date",
                            "text": f"The notice went {gap} days after dishonour; it must be within 30 days of learning of it (S.138 proviso (b))."})
            elif gap >= 0:
                out.append({"level": "ok", "key": "notice_date", "text": f"Notice sent {gap} days after dishonour — within 30 days."})
        if kd:
            coa = kd + timedelta(days=15)
            last = coa + timedelta(days=30)
            out.append({"level": "check" if today <= last else "fix", "key": "notice_known_date",
                        "text": (f"Cause of action arose on {_fmt(coa)} (15 days after the notice was served). "
                                 f"The complaint must be filed by {_fmt(last)} (S.142(1)(b))."
                                 + ("" if today <= last else " That date has passed — a delay-condonation application is needed."))})

    # default bail: when the statutory period ran out
    if tid == "default_bail" and _parse(fields.get("arrest_date")):
        a = _parse(fields["arrest_date"])
        days = 90 if re.search(r"90", str(fields.get("statutory_period") or "")) else (
            60 if re.search(r"60", str(fields.get("statutory_period") or "")) else None)
        if days:
            out.append({"level": "ok", "key": "arrest_date",
                        "text": f"{days} days from arrest completed on {_fmt(a + timedelta(days=days))}."})

    # a successive bail must name the order that refused it
    if fields.get("prior_mag_rejected") is True:
        for k in ("prior_court", "prior_order_date"):
            if k in fmap and _is_empty(fields.get(k)):
                out.append({"level": "fix", "key": k,
                            "text": f"This is a successive bail — {fmap[k]['label_en'].lower()} must be disclosed."})

    order = {"fix": 0, "check": 1, "ok": 2}
    seen, uniq = set(), []
    for c in sorted(out, key=lambda c: order[c["level"]]):
        sig = (c.get("key"), c["text"])
        if sig not in seen:
            seen.add(sig)
            uniq.append(c)
    return uniq


# ---------------------------------------------------------------------------- AI top-up
_ENRICH_SYSTEM = """You read an Indian advocate's brief and fill a court form.

Return ONLY a JSON object mapping field keys to values. Rules — breaking any of them makes the value useless:
1. Only a fact that is WRITTEN in the brief. If the brief does not say it, leave the key out. Never guess, never infer, never use general knowledge.
2. Names, places, numbers and dates exactly as in the brief. You may write a name or place in the document's script ({script}) — that is the only change allowed.
3. Dates as dd/mm/yyyy. Money as digits only. Section lists as a JSON array of strings like "420 IPC".
4. Only keys from the list given. Do not invent keys.
{narrative}"""

_NARRATIVE_RULE = ("5. For \"facts_narrative\": 2 to 4 plain sentences in {script}, stating only what the brief says "
                   "happened — no argument, no adjectives, no fact that is not in the brief.")


def _latin(s: str) -> str:
    from headnote.drafter import transliterate as TR
    s = s or ""
    return (TR.hi_to_en(s) if IN.is_deva(s) else s).lower()


def _grounded(value, brief: str, ftype: str) -> bool:
    """A model value is kept only if the brief actually contains it."""
    b = IN._nfc(brief)
    if isinstance(value, list):
        return all(_grounded(v, brief, "text") for v in value) and bool(value)
    v = str(value or "").strip()
    if not v:
        return False
    digits = re.findall(r"\d+", v)
    brief_digits = set(re.findall(r"\d+", b.replace(",", "")))
    if ftype in ("date", "number", "money") or (digits and len("".join(digits)) >= len(re.sub(r"\D", "", v)) * 0.6):
        if ftype == "date":
            d = _parse(v)
            if not d:
                return False
            for s_, e_, dv in IN._dates(b):
                if dv == _fmt(d):
                    return True
            return False
        return all(x.lstrip("0") in {y.lstrip("0") for y in brief_digits} or x in brief_digits for x in digits)
    if any(x not in brief_digits for x in digits):
        return False
    words = [w for w in re.findall(rf"[A-Za-z]{{3,}}|[{IN.DEVA}]{{2,}}", v)]
    if not words:
        return False
    bw = set(re.findall(rf"[A-Za-z]{{3,}}|[{IN.DEVA}]{{2,}}", b))
    bl = {_latin(w) for w in bw} | {w.lower() for w in bw}
    hit = 0
    for w in words:
        lw = _latin(w)
        if w in bw or lw in bl or difflib.get_close_matches(lw, list(bl), n=1, cutoff=0.74):
            hit += 1
    return hit / len(words) >= 0.7


def enrich(brief: str, tid: str, lang: str, fields: dict) -> dict:
    """Ask the model to read the brief for the fields still empty, then keep ONLY
    what the brief contains. Never overwrites a value already in the form."""
    from headnote.llm.client import _call_deepseek_or_groq, parse_json_response

    fmap = _field_map(tid)
    empty = {k: f for k, f in fmap.items()
             if f["type"] not in ("toggle", "table") and k not in ("custom_grounds", "advocate_name")
             and _is_empty((fields or {}).get(k))}
    if not empty or not (brief or "").strip():
        return {"fields": {}, "evidence": {}, "dropped": [], "model": None}
    script = "Hindi (Devanagari)" if lang == "hi" else "English"
    narrative = _NARRATIVE_RULE.format(script=script) if "facts_narrative" in empty else ""
    system = _ENRICH_SYSTEM.format(script=script, narrative=narrative)
    listing = "\n".join(f'- "{k}": {f["label_en"]} ({f["type"]})' for k, f in empty.items())
    user = f"FIELDS STILL EMPTY:\n{listing}\n\nBRIEF:\n{brief.strip()[:6000]}"
    raw, meta = _call_deepseek_or_groq(system, user, max_tokens=2500, claude_model="claude-haiku-4-5", json_mode=True)
    try:
        data = parse_json_response(raw) or {}
    except Exception:
        data = {}
    kept, ev, dropped = {}, {}, []
    for k, v in (data.items() if isinstance(data, dict) else []):
        if k not in empty or _is_empty(v):
            continue
        ftype = empty[k]["type"]
        if k == "facts_narrative":
            # a narrative is a re-telling; its numbers must all be the brief's
            ds = re.findall(r"\d+", str(v))
            bd = set(re.findall(r"\d+", brief.replace(",", "")))
            if all(d in bd for d in ds) and 20 <= len(str(v)) <= 1500:
                kept[k] = str(v).strip()
                ev[k] = {"source": "ai", "span": "", "note": "Written by AI from your brief — read it before filing."}
            else:
                dropped.append(k)
            continue
        if ftype == "section_list":
            v = v if isinstance(v, list) else [x.strip() for x in str(v).split(",") if x.strip()]
        if _grounded(v, brief, ftype):
            kept[k] = v
            ev[k] = {"source": "ai", "span": "", "note": ""}
        else:
            dropped.append(k)
    return {"fields": kept, "evidence": ev, "dropped": dropped, "model": (meta or {}).get("model")}


# ---------------------------------------------------------------------------- from a matter
_STATE_PARTY = re.compile(r"state|government|govt|शासन|राज्य|सरकार|police|पुलिस", re.I)


def matter_brief(row: dict) -> str:
    """A matter from his diary / the court record, written out as the kind of brief
    the intake engine reads. Only what the record holds; nothing added."""
    if not row:
        return ""
    cj = row.get("case_json") or {}
    lines: list[str] = []
    pet = cj.get("petitioner_name") or ""
    res = cj.get("respondent_name") or ""
    client = (cj.get("client") or {}).get("name") or ""
    if pet and _STATE_PARTY.search(pet) and res:
        lines.append(f"Accused: {res}.")
    elif client:
        lines.append(f"Client: {client}.")
        other = res if client.lower() in pet.lower() else pet
        if other:
            lines.append(f"Against {other}.")
    elif pet or res:
        if pet:
            lines.append(f"Petitioner: {pet}.")
        if res:
            lines.append(f"Against {res}.")
    court = row.get("court_name") or cj.get("court_name")
    if court:
        lines.append(f"Court: {court}.")
    num, yr = row.get("case_number") or cj.get("case_number"), row.get("case_year") or cj.get("case_year")
    if num:
        lines.append(f"Case no. {num}/{yr}." if yr else f"Case no. {num}.")
    ps = cj.get("police_station")
    fir, fy = cj.get("fir_number"), cj.get("fir_year")
    if ps:
        lines.append(f"Police station {ps}.")
    if fir:
        lines.append(f"FIR {fir}/{fy}." if fy and "/" not in str(fir) else f"FIR {fir}.")
    secs = cj.get("sections") or []
    if secs:
        joined = " ".join(str(s) for s in secs)
        act = ""
        for rx, hi, en in IN._ACTS_C:
            if rx.search(" " + joined):
                act = en
                break
        if re.search(r"indian\s+penal\s+code|i\.p\.c", joined, re.I):
            act = "IPC"
        elif re.search(r"bharatiya\s+nyaya\s+sanhita|b\.n\.s", joined, re.I):
            act = "BNS"
        nums = re.findall(r"(?<![\d(])(\d{1,3}[A-Za-z]?(?:\(\d+\))*)(?![\d)])", re.sub(r",\s*(?:18|19|20)\d{2}", "", joined))
        if nums:
            lines.append(f"u/s {', '.join(dict.fromkeys(nums))} {act}".strip() + ".")
    stage = row.get("stage") or cj.get("stage")
    if stage:
        lines.append(f"Stage: {stage}.")
    return " ".join(lines)
