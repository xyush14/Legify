"""eCourts CNR lookup — third-party API adapter (swappable vendor).

Sourcing: there is NO official self-serve eCourts API (portal is CAPTCHA-gated,
NJDG aggregate-only, nothing on API Setu). We use a licensed third-party API
(default: eCourtsIndia) that sources from the official portal. Swapping vendors
= re-point CNR_API_BASE_URL/CNR_API_CASE_PATH + adjust ``_normalise_live`` only.

Modes (config.CNR_API_MODE):
  • "mock" — no network; returns a RICH, realistic fixture (default w/o token,
            and the only mode that works from a WAF-blocked dev box). The mock
            mirrors a real eCourts case sheet (party occupation/address/father,
            custody date, prior-court, IAs, orders, category) so the whole
            "add case → draft" flow is testable end-to-end with no key.
  • "live" — calls the vendor's CASE_DETAIL endpoint. Confirm the exact request
            + response shape against the dashboard API Docs on the first real
            call; ``_normalise_live`` is the only place that then changes.

``fetch_cnr(cnr)`` always returns the SAME normalised dict regardless of mode.
"""

from __future__ import annotations

import re

import httpx

from headnote import config


_CNR_RE = re.compile(r"^[A-Z0-9]{16}$")


def clean_cnr(cnr: str | None) -> str:
    return re.sub(r"\s+", "", (cnr or "")).upper()


def is_valid_cnr(cnr: str | None) -> bool:
    """eCourts CNR = exactly 16 alphanumeric chars (e.g. MPGW010000122021)."""
    return bool(_CNR_RE.match(clean_cnr(cnr)))


# ------------------------------------------------------------ normalised shape
# The single contract every consumer relies on. Mock + live both fill this.
def _blank_case(cnr: str) -> dict:
    return {
        "cnr": cnr,
        "source": "mock",
        "case_title": None, "case_title_en": None,
        "case_type": None, "case_status": None,
        "case_number": None, "case_year": None,
        "registration_number": None, "filing_number": None, "filing_date": None,
        "court_name": None, "court_name_en": None,
        "court_level": "magistrate",          # magistrate | sessions | hc (inferred)
        "bench": None, "dealing_assistant": None,
        "district": None, "district_en": None,
        "court_city": None, "court_city_en": None,
        "state_name": None, "state_name_en": None,
        "judge": None,
        "stage": None, "stage_substatus": None,
        "next_hearing_date": None, "last_listed_date": None, "last_order": None,
        # parties — full particulars (eCourts DOES expose occupation + address + relation)
        "petitioner_name": None, "petitioner_name_en": None, "petitioner_father": None,
        "petitioner_occupation": None, "petitioner_address": None, "petitioner_advocates": [],
        "respondent_name": None, "respondent_name_en": None, "respondent_father": None,
        "respondent_occupation": None, "respondent_address": None, "respondent_advocates": [],
        "accused_name": None, "accused_name_en": None,   # explicit override if known
        # crime / criminal
        "police_station": None, "police_station_en": None,
        "fir_number": None, "fir_year": None, "arrest_date": None,
        # successive / impugned (bail-rejection or revision/appeal source)
        "prior_court": None, "prior_bail_case": None, "prior_order_date": None,
        "earlier_court": None,                # {court, case_no, order_date, nature}
        # rich sections
        "ias": [],                            # [{number, purpose, status}]
        "orders": [],                         # [{date, type, link}]
        "hearings": [],                       # [{date, purpose}]
        "connected": [],                      # connected case numbers
        "category": None,                     # structured statute path
        "caveat": None,
        "sections": [], "sections_en": [], "acts": [],
        "raw": {},
    }


def _infer_level(court_name: str | None, case_type: str | None = None) -> str:
    """Map an eCourts court / case-type → a drafter court variant.

    CNR data is overwhelmingly DISTRICT courts (Sessions + Magistrate) — the
    bread-and-butter of the district advocate, and exactly who this serves. High
    Court (M.Cr.C./MCRC, writ) is the exception. We read BOTH the court name and
    the case type because the case type ("Sessions Trial", "RCT", "Bail Appln")
    is often the clearer signal. Default = magistrate (where most district
    matters originate)."""
    s = f"{court_name or ''} {case_type or ''}".lower()
    if any(k in s for k in ("high court", "उच्च न्यायालय", "m.cr.c", "mcrc", "writ", "w.p.")):
        return "hc"
    if any(k in s for k in ("sessions", "सत्र", "special judge", "spl. judge", "विशेष न्यायाधीश",
                            "addl. sess", "अपर सत्र", "s.t. ", "sessions trial", "spl.sc",
                            "ndps", "pocso", "atrocit")):  # special courts run at sessions level
        return "sessions"
    # JMFC / CJM / Judicial Magistrate / RCT / complaint / summary / दण्डाधिकारी → magistrate
    return "magistrate"


# ------------------------------------------------------------ public entry
def fetch_cnr(cnr: str) -> dict:
    """Look up a CNR and return the normalised case dict.

    Raises ValueError on a malformed CNR (live mode) and RuntimeError if live
    mode is selected without a token. Mock mode is lenient on the CNR so the
    flow is friction-free to test."""
    cnr = clean_cnr(cnr)
    if not cnr:
        raise ValueError("CNR is required")

    if config.CNR_API_MODE == "live":
        if not config.CNR_API_TOKEN:
            raise RuntimeError("CNR_API_MODE=live but CNR_API_TOKEN is not set")
        if not is_valid_cnr(cnr):
            raise ValueError(f"'{cnr}' is not a valid 16-character CNR")
        return _fetch_live(cnr)

    return _fetch_mock(cnr)


# ------------------------------------------------------------ live
def _fetch_live(cnr: str) -> dict:
    """Call the vendor's CASE_DETAIL endpoint. Confirm path/auth/shape against
    https://ecourtsindia.com/api/docs on the first real call, then tune
    ``_normalise_live``."""
    url = config.CNR_API_BASE_URL.rstrip("/") + config.CNR_API_CASE_PATH
    headers = {
        "Authorization": f"Bearer {config.CNR_API_TOKEN}",
        "x-api-key": config.CNR_API_TOKEN or "",
        "Accept": "application/json",
    }
    r = httpx.get(url, params={"cnr": cnr}, headers=headers, timeout=25.0)
    r.raise_for_status()
    return _normalise_live(r.json() or {}, cnr)


def _first(d: dict, *keys, default=None):
    for k in keys:
        v = (d or {}).get(k)
        if v not in (None, "", [], {}):
            return v
    return default


def _party(p) -> dict:
    """Normalise a vendor party object (dict or bare string) → our shape."""
    if isinstance(p, str):
        return {"name": p}
    if isinstance(p, list):
        p = p[0] if p else {}
    p = p or {}
    return {
        "name": _first(p, "name", "party_name"),
        "father": _first(p, "father", "father_name", "relation", "fathersHusband", "s_d_w"),
        "occupation": _first(p, "occupation", "profession"),
        "address": _first(p, "address", "addr"),
        "advocates": _first(p, "advocates", "advocate", default=[]),
    }


def _normalise_live(payload: dict, cnr: str) -> dict:
    """Best-effort map of a generic eCourts JSON → our shape. Defensive .get()
    chains over the key names vendors commonly use; full payload kept in raw."""
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    c = _blank_case(cnr)
    c["source"] = "ecourtsindia"
    c["raw"] = payload

    c["case_type"] = _first(data, "case_type", "type")
    c["case_status"] = _first(data, "status", "case_status")
    c["case_number"] = _first(data, "case_number", "reg_number", "registration_number")
    c["case_year"] = _first(data, "case_year", "reg_year", "year")
    c["registration_number"] = _first(data, "registration_number", "reg_no")
    c["filing_number"] = _first(data, "filing_number", "filing_no")
    c["filing_date"] = _first(data, "filing_date", "date_of_filing")
    c["court_name"] = _first(data, "court_name", "court", "court_establishment")
    c["bench"] = _first(data, "bench", "coram", "before")
    c["district"] = _first(data, "district", "district_name")
    c["state_name"] = _first(data, "state", "state_name")
    c["court_city"] = c["district"]
    c["judge"] = _first(data, "judge", "judge_name")
    c["stage"] = _first(data, "stage", "case_stage")
    c["next_hearing_date"] = _first(data, "next_hearing_date", "next_date", "next_hearing")
    c["last_listed_date"] = _first(data, "last_listed", "last_listed_on")
    c["last_order"] = _first(data, "last_order")
    c["court_level"] = _infer_level(c["court_name"], c["case_type"])

    pet = _party(_first(data, "petitioner", "petitioners", "petitioner_name", default={}))
    res = _party(_first(data, "respondent", "respondents", "respondent_name", default={}))
    for side, src in (("petitioner", pet), ("respondent", res)):
        c[f"{side}_name"] = src.get("name")
        c[f"{side}_father"] = src.get("father")
        c[f"{side}_occupation"] = src.get("occupation")
        c[f"{side}_address"] = src.get("address")
        adv = src.get("advocates")
        c[f"{side}_advocates"] = adv if isinstance(adv, list) else ([adv] if adv else [])

    fir = data.get("fir") if isinstance(data.get("fir"), dict) else data
    c["police_station"] = _first(fir, "police_station", "ps_name", "police_station_name")
    c["fir_number"] = _first(fir, "fir_number", "fir_no", "crime_number")
    c["fir_year"] = _first(fir, "fir_year")
    c["ias"] = _first(data, "ias", "interim_applications", default=[])
    c["orders"] = _first(data, "orders", "order_list", default=[])
    c["hearings"] = _first(data, "history", "case_history", "hearings", default=[])
    c["connected"] = _first(data, "connected", "connected_cases", default=[])
    c["category"] = _first(data, "category")
    earlier = _first(data, "earlier_court", "lower_court", "subordinate_court")
    if earlier:
        c["earlier_court"] = earlier

    acts = _first(data, "acts", "acts_sections", "act", default=[])
    if isinstance(acts, dict):
        c["acts"] = list(acts.keys())
        c["sections"] = [s for v in acts.values() for s in str(v).split(",") if s.strip()]
    elif isinstance(acts, list):
        c["acts"] = [str(a) for a in acts]
    sections = _first(data, "sections", "under_section")
    if sections:
        c["sections"] = sections if isinstance(sections, list) else [s.strip() for s in str(sections).split(",") if s.strip()]

    for base in ("case_title", "court_name", "district", "court_city", "state_name",
                 "petitioner_name", "respondent_name", "police_station"):
        c[f"{base}_en"] = c.get(base)
    c["sections_en"] = list(c["sections"])
    if not c["case_title"] and (c["petitioner_name"] or c["respondent_name"]):
        c["case_title"] = f"{c.get('petitioner_name') or '—'} vs {c.get('respondent_name') or '—'}"
        c["case_title_en"] = c["case_title"]
    return c


# ------------------------------------------------------------ mock (rich)
# Deterministic off the CNR (no randomness) so a given CNR always returns the
# same case — and different CNRs return visibly different ones for demos.
# father stored WITHOUT the "श्री"/"Shri" honorific — templates add "पुत्र श्री" / "S/o".
_NAMES = [
    ("राकेश पाल", "Rakesh Pal", "बृजमोहन पाल", "Brijmohan Pal"),
    ("सुनील कुशवाह", "Sunil Kushwah", "रामू कुशवाह", "Ramu Kushwah"),
    ("दीपक यादव", "Deepak Yadav", "हरिराम यादव", "Hariram Yadav"),
    ("अरविंद शर्मा", "Arvind Sharma", "मोहनलाल शर्मा", "Mohanlal Sharma"),
    ("इमरान खान", "Imran Khan", "यूसुफ खान", "Yusuf Khan"),
]
_VILLAGES = ["पनिहार", "डबरा", "भितरवार", "मोहना", "घाटीगाँव"]


def _fetch_mock(cnr: str) -> dict:
    cs = sum(ord(ch) for ch in cnr)
    nm = _NAMES[cs % len(_NAMES)]
    vill = _VILLAGES[(cs // 5) % len(_VILLAGES)]
    case_no = str(400 + cs % 9000)
    fir_no = f"{120 + cs % 700}/{'2024' if cs % 2 == 0 else '2021'}"
    name_hi, name_en, father_hi, father_en = nm
    c = _blank_case(cnr)

    if cs % 2 == 0:
        # ---- Sessions, accused in custody → BAIL (successive) ----
        c.update({
            "case_title": f"म.प्र. राज्य बनाम {name_hi}",
            "case_title_en": f"State of M.P. vs {name_en}",
            "case_type": "सत्र प्रकरण", "case_status": "विचाराधीन (Pending)",
            "case_number": case_no, "case_year": "2024",
            "registration_number": f"S.T./{case_no}/2024", "filing_date": "14/03/2024",
            "court_name": "न्यायालय तृतीय अपर सत्र न्यायाधीश, ग्वालियर (म.प्र.)",
            "court_name_en": "Court of IIIrd Addl. Sessions Judge, Gwalior (M.P.)",
            "bench": "तृतीय अपर सत्र न्यायाधीश", "dealing_assistant": "रीडर — सत्र शाखा",
            "district": "ग्वालियर", "district_en": "Gwalior",
            "court_city": "ग्वालियर", "court_city_en": "Gwalior",
            "state_name": "म.प्र.", "state_name_en": "M.P.",
            "judge": "श्री ______ अपर सत्र न्यायाधीश",
            "stage": "जमानत आवेदन विचाराधीन", "stage_substatus": "अभियोजन साक्ष्य",
            "next_hearing_date": "22/07/2026", "last_listed_date": "08/07/2026",
            "last_order": "जमानत आवेदन — सुनवाई हेतु नियत दि. 22/07/2026",
            "petitioner_name": "म.प्र. राज्य", "petitioner_name_en": "State of M.P.",
            "respondent_name": name_hi, "respondent_name_en": name_en,
            "respondent_father": father_hi, "respondent_father_en": father_en,
            "respondent_occupation": "मजदूरी", "respondent_occupation_en": "labour",
            "respondent_address": f"ग्राम {vill}, थाना {vill}",
            "respondent_address_en": f"Vill. {vill}, P.S. {vill}",
            "respondent_advocates": ["श्री ____ अधिवक्ता"],
            "police_station": vill, "police_station_en": vill,
            "fir_number": fir_no, "fir_year": fir_no.split("/")[-1], "arrest_date": "10.02.2026",
            "prior_court": "विद्वान न्यायिक दण्डाधिकारी प्रथम श्रेणी, ग्वालियर",
            "prior_bail_case": f"{case_no}/2026", "prior_order_date": "18.04.2026",
            "ias": [{"number": f"IA-{300 + cs % 600}/2026", "purpose": "जमानत आवेदन", "status": "विचाराधीन"}],
            "category": "आपराधिक विधि एवं प्रक्रिया » भा.न्या.सं. 2023 » धारा 103/309",
            "sections": ["103(1) भा.न्या.सं.", "309(4) भा.न्या.सं."],
            "sections_en": ["S.103(1) BNS", "S.309(4) BNS"],
            "acts": ["भारतीय न्याय संहिता, 2023"],
        })
    else:
        # ---- Magistrate, charge stage → DISCHARGE (498A) ----
        c.update({
            "case_title": f"म.प्र. राज्य बनाम {name_hi} व अन्य",
            "case_title_en": f"State of M.P. vs {name_en} & Ors.",
            "case_type": "आर.सी.टी.", "case_status": "विचाराधीन (Pending)",
            "case_number": case_no, "case_year": "2021",
            "registration_number": f"RCT/{case_no}/2021", "filing_date": "12/08/2021",
            "court_name": "न्यायालय न्यायिक दण्डाधिकारी प्रथम श्रेणी, उज्जैन (म.प्र.)",
            "court_name_en": "Court of the JMFC, Ujjain (M.P.)",
            "bench": "न्यायिक दण्डाधिकारी प्रथम श्रेणी", "dealing_assistant": "रीडर",
            "district": "उज्जैन", "district_en": "Ujjain",
            "court_city": "उज्जैन", "court_city_en": "Ujjain",
            "state_name": "म.प्र.", "state_name_en": "M.P.",
            "judge": "श्री ______ न्या.दं.प्र.श्रे.",
            "stage": "आरोप तर्क हेतु नियत", "stage_substatus": "आरोप विरचन",
            "next_hearing_date": "15/07/2026", "last_listed_date": "01/07/2026",
            "last_order": "आरोप पर बहस हेतु नियत",
            "petitioner_name": "म.प्र. राज्य", "petitioner_name_en": "State of M.P.",
            "respondent_name": name_hi, "respondent_name_en": name_en,
            "respondent_father": father_hi, "respondent_father_en": father_en,
            "respondent_occupation": "कृषि", "respondent_occupation_en": "agriculture",
            "respondent_address": f"ग्राम {vill}, जिला उज्जैन (म.प्र.)",
            "respondent_address_en": f"Vill. {vill}, Distt. Ujjain (M.P.)",
            "respondent_advocates": ["श्री ____ अधिवक्ता"],
            "police_station": f"महिला थाना, उज्जैन", "police_station_en": "Mahila Thana, Ujjain",
            "fir_number": fir_no.replace("2024", "2021"), "fir_year": "2021",
            "ias": [{"number": f"IA-{200 + cs % 400}/2026", "purpose": "उन्मोचन आवेदन", "status": "विचाराधीन"}],
            "category": "आपराधिक विधि » भा.द.वि. » धारा 498ए | दहेज प्रतिषेध अधिनियम, 1961",
            "sections": ["498ए भा.द.वि.", "3/4 दहेज प्रतिषेध अधिनियम"],
            "sections_en": ["498A IPC", "3/4 Dowry Prohibition Act"],
            "acts": ["भारतीय दण्ड संहिता, 1860", "दहेज प्रतिषेध अधिनियम, 1961"],
        })

    c["accused_name"] = name_hi
    c["accused_name_en"] = name_en
    c["court_level"] = _infer_level(c["court_name"], c["case_type"])
    c["raw"] = {"_mock": True, "cnr": cnr, "shape": "bail" if cs % 2 == 0 else "discharge"}
    return c
