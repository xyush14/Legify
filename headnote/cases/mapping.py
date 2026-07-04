"""Map a normalised CNR case → drafter answers (the differentiating step).

Field keys are EXACTLY what the canonical templates consume:
  • bail      → headnote/drafter/templates/bail.py
  • discharge → headnote/drafter/templates/discharge.py

Three sources merge, most-authoritative last:
  1. the CNR case party block — name, **relation/father, occupation, address**
     (eCourts DOES carry these), plus arrest date + prior-court for successive bail;
  2. the matter's lawyer-entered CLIENT record (overrides where present);
so a draft opens with the party block already filled — review, not type.

``_accused_particulars`` picks the non-State party (the bail/discharge applicant)
and lifts its particulars. ``suggest_drafts`` reads stage/sections to recommend
which draft fits where the case is.
"""

from __future__ import annotations

SUPPORTED = ("bail", "discharge")

_STATE_TOKENS = ("state", "राज्य", "शासन", "sarkar", "govt", "u.p.", "m.p.",
                 "union of india", "cbi", "police")


def _is_state(name: str | None) -> bool:
    s = (name or "").strip().lower()
    return bool(s) and any(tok in s for tok in _STATE_TOKENS)


def _accused_particulars(case: dict) -> dict:
    """The non-State party (= the defence applicant), with full particulars."""
    pet_state, res_state = _is_state(case.get("petitioner_name")), _is_state(case.get("respondent_name"))
    if res_state and not pet_state:
        side = "petitioner"
    elif pet_state and not res_state:
        side = "respondent"
    else:
        side = "respondent" if case.get("respondent_name") else "petitioner"
    g = lambda k: case.get(f"{side}_{k}")
    advs = case.get(f"{side}_advocates") or []
    name = case.get("accused_name") or g("name")
    return {
        "name": name, "name_en": case.get("accused_name_en") or g("name_en") or name,
        "father": g("father"), "father_en": g("father_en"),
        "occupation": g("occupation"), "occupation_en": g("occupation_en"),
        "address": g("address"), "address_en": g("address_en"),
        "advocate": advs[0] if advs else None,
    }


def _client(case: dict) -> dict:
    return case.get("client") or {}


def map_case_to_answers(story_id: str, case: dict) -> dict:
    if story_id == "bail":
        return _bail(case)
    if story_id == "discharge":
        return _discharge(case)
    raise ValueError(f"no CNR→draft mapping for story '{story_id}' "
                     f"(supported: {', '.join(SUPPORTED)})")


def _bail(case: dict) -> dict:
    a = _accused_particulars(case)
    cl = _client(case)
    district = case.get("district") or case.get("court_city")
    district_en = case.get("district_en") or case.get("court_city_en")
    prior_court = case.get("prior_court")
    arrest = case.get("arrest_date")
    d = {
        "court": case.get("court_level") or "magistrate",   # magistrate|sessions|hc
        "bail_type": "regular",
        "court_city": case.get("court_city") or district, "court_city_en": case.get("court_city_en") or district_en,
        "state_name": case.get("state_name"), "state_name_en": case.get("state_name_en"),
        "case_number": case.get("case_number"), "case_year": case.get("case_year"),
        # party block — straight from the CNR
        "applicant_name": a["name"], "applicant_name_en": a["name_en"],
        "applicant_father": a["father"], "applicant_father_en": a["father_en"],
        "applicant_occupation": a["occupation"], "applicant_occupation_en": a["occupation_en"],
        "applicant_address": a["address"], "applicant_address_en": a["address_en"],
        "district": district, "district_en": district_en,
        "police_station": case.get("police_station"), "police_station_en": case.get("police_station_en"),
        "fir_number": case.get("fir_number"),
        "sections": list(case.get("sections") or []), "sections_en": list(case.get("sections_en") or []),
        "arrest_date": arrest,
        "prior_court": prior_court, "prior_bail_case": case.get("prior_bail_case"),
        "prior_order_date": case.get("prior_order_date"),
        # fact-derived grounds (not presumptuous): successive if a lower court rejected;
        # trial-delay if there's a custody/arrest date the template can clock.
        "grounds": {"prior_mag_rejected": bool(prior_court), "trial_delay": bool(arrest)},
        "advocate_name": a["advocate"],
        "_cnr": case.get("cnr"),
    }
    # lawyer-entered client wins
    if cl.get("name"):
        d["applicant_name"] = cl["name"]; d["applicant_name_en"] = cl.get("name_en") or cl["name"]
    for ck, ak in (("father", "applicant_father"), ("age", "applicant_age"),
                   ("occupation", "applicant_occupation"), ("address", "applicant_address")):
        if cl.get(ck):
            d[ak] = cl[ck]
    return d


def _discharge(case: dict) -> dict:
    a = _accused_particulars(case)
    cl = _client(case)
    level = case.get("court_level") or "magistrate"
    court = level if level in ("magistrate", "sessions") else "sessions"
    d = {
        "court": court,
        "court_city": case.get("court_city") or case.get("district"),
        "court_city_en": case.get("court_city_en") or case.get("district_en"),
        "state_name": case.get("state_name"), "state_name_en": case.get("state_name_en"),
        "case_number": case.get("case_number"), "case_year": case.get("case_year"),
        "case_type": case.get("case_type") or "आर.सी.टी.",
        "accused_names": a["name"], "accused_names_en": a["name_en"],
        "is_plural": False,
        "police_station": case.get("police_station"), "police_station_en": case.get("police_station_en"),
        "crime_number": case.get("fir_number"),             # NB: discharge uses crime_number
        "sections": list(case.get("sections") or []), "sections_en": list(case.get("sections_en") or []),
        "advocate_name": a["advocate"],
        "_cnr": case.get("cnr"),
    }
    if cl.get("name"):
        d["accused_names"] = cl["name"]; d["accused_names_en"] = cl.get("name_en") or cl["name"]
    return d


# ------------------------------------------------------------ stage-aware suggestion
_DISCHARGE_HINTS = ("charge", "आरोप", "discharge", "उन्मोचन", "262", "239", "227", "250")
_BAIL_HINTS = ("custody", "remand", "अभिरक्षा", "गिरफ्तार", "arrest", "bail",
               "जमानत", "warrant", "निरुद्ध")


def suggest_drafts(case: dict) -> list[dict]:
    stage = (case.get("stage") or "").lower()
    secs = " ".join(str(s) for s in (case.get("sections") or [])).lower()
    meta = {
        "bail":      {"story_id": "bail", "label": "Bail", "label_hi": "जमानत",
                      "reason": "secure the accused's liberty"},
        "discharge": {"story_id": "discharge", "label": "Discharge", "label_hi": "उन्मोचन",
                      "reason": "no prima-facie case — seek discharge"},
    }
    order = ["bail", "discharge"]
    if any(h in stage for h in _DISCHARGE_HINTS):
        order = ["discharge", "bail"]
        meta["discharge"]["reason"] = "matter fixed for arguments on charge"
    elif any(h in stage for h in _BAIL_HINTS):
        order = ["bail", "discharge"]
        meta["bail"]["reason"] = "accused in custody — move for bail"
    elif "498" in secs:
        order = ["discharge", "bail"]
        meta["discharge"]["reason"] = "matrimonial / 498A — commonly a discharge play"
    out = []
    for i, sid in enumerate(order):
        o = dict(meta[sid]); o["primary"] = (i == 0); out.append(o)
    return out
