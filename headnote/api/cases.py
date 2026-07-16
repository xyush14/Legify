"""Cases ("Matters") — CNR-driven case folders that pre-fill the drafter.

POST   /api/cases/add-cnr              fetch a CNR (+ optional client), store it
GET    /api/cases                      list the lawyer's matters (with suggestions)
GET    /api/cases/{id}                 one matter (full payload + suggestions)
PATCH  /api/cases/{id}/client          save/merge client details (name/mobile/…)
DELETE /api/cases/{id}                 remove a matter
POST   /api/cases/{id}/draft/{story}   create a draft PRE-FILLED from the matter

Each matter carries `suggested`: the stage-aware ordered list of which draft
fits where the case is (primary first) — so the UI offers the right action.

Auth required (get_current_user). Locally (SUPABASE_URL unset) that returns the
synthetic dev user, so the flow works tokenless.

Cost: add-cnr in live mode spends one CASE_DETAIL credit (≈ ₹1.50); the draft
step is free (Headnote's own templates). Client details are lawyer-entered (the
CNR never has the client's phone) and power both autofill and reminders.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from headnote.entitlements import CurrentUser, get_current_user
from headnote.cases import ecourts_client, mapping
from headnote.cases import dateutil as case_dates
from headnote.cases import storage as cases_storage
from headnote.consultations import storage as consult_storage
from headnote.documents import storage as docs_storage
from headnote.drafter import storage as draft_storage, stories
from headnote.integrations import sarvam, gemini


log = logging.getLogger(__name__)
router = APIRouter(prefix="/api/cases", tags=["cases"])

_STORY_LABELS = {"bail": "जमानत", "discharge": "उन्मोचन"}


class ClientBody(BaseModel):
    """The client the lawyer represents in this matter. All optional — eCourts
    never supplies these; the lawyer fills them once for autofill + reminders."""
    name:       Optional[str] = Field(None, max_length=200)
    father:     Optional[str] = Field(None, max_length=200, description="Father/Husband name")
    age:        Optional[str] = Field(None, max_length=12)
    occupation: Optional[str] = Field(None, max_length=120)
    address:    Optional[str] = Field(None, max_length=500)
    mobile:     Optional[str] = Field(None, max_length=20)
    email:      Optional[str] = Field(None, max_length=200)
    role:       Optional[str] = Field(None, max_length=40, description="accused | complainant | applicant …")
    consent:    Optional[bool] = Field(None, description="client consents to hearing reminders (DPDP)")


class AddCnrBody(BaseModel):
    cnr:    str = Field(..., min_length=1, max_length=32,
                        description="16-character eCourts CNR (e.g. MPGW010000122021)")
    client: Optional[ClientBody] = Field(None, description="Optional client details to save with the case")


def _enrich(row: Optional[dict]) -> Optional[dict]:
    """Attach the stage-aware draft suggestions to a matter row."""
    if row:
        row["suggested"] = mapping.suggest_drafts(row.get("case_json") or {})
    return row


@router.post("/add-cnr", summary="Fetch a case by CNR (+ optional client) and store it")
def add_case_by_cnr(body: AddCnrBody, user: CurrentUser = Depends(get_current_user)) -> dict:
    try:
        case = ecourts_client.fetch_cnr(body.cnr)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001 — network / vendor errors
        log.warning("CNR lookup failed for %s: %s", body.cnr, e)
        raise HTTPException(status_code=502, detail=f"CNR lookup failed: {e}")

    if body.client is not None:
        case["client"] = body.client.model_dump(exclude_none=True)

    row = cases_storage.add_case(user_id=user.id, case=case)
    return {"ok": True, "case": _enrich(row)}


@router.get("", summary="List the lawyer's matters (newest first)")
def list_cases(user: CurrentUser = Depends(get_current_user)) -> dict:
    items = [_enrich(r) for r in cases_storage.list_cases(user_id=user.id)]
    return {"items": items, "count": len(items)}


def _diary_item(row: dict) -> dict:
    """A matter shaped for the diary: enriched + its next date normalised to ISO
    (for grouping) alongside the raw string (for display)."""
    item = _enrich(row)
    item["next_iso"] = case_dates.to_iso(row.get("next_hearing_date"))
    return item


@router.get("/diary", summary="Matters grouped by next hearing date (the diary)")
def diary(from_: Optional[str] = None, to: Optional[str] = None,
          user: CurrentUser = Depends(get_current_user)) -> dict:
    """Group the lawyer's matters by next hearing date across a window (default:
    the next 7 days from today). Unparseable/empty dates go in `undated`."""
    if not from_:
        from_, to = case_dates.week_window()
    elif not to:
        _, to = case_dates.week_window(from_)

    window = set(case_dates.date_range(from_, to))
    rows = cases_storage.list_cases(user_id=user.id, limit=500)

    by_day: dict[str, list] = {d: [] for d in sorted(window)}
    undated: list = []
    for r in rows:
        item = _diary_item(r)
        iso = item.get("next_iso")
        if iso and iso in by_day:
            by_day[iso].append(item)
        elif not iso:
            undated.append(item)
    days = [{"date": d, "count": len(by_day[d]), "items": by_day[d]}
            for d in sorted(by_day)]
    return {
        "from": from_, "to": to, "today": case_dates.today_iso(),
        "days": days, "undated": undated,
        "total": sum(d["count"] for d in days),
    }


@router.get("/diary/day", summary="Matters listed for one hearing date")
def diary_day(date: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    target = case_dates.to_iso(date) or date
    rows = cases_storage.list_cases(user_id=user.id, limit=500)
    items = [it for it in (_diary_item(r) for r in rows) if it.get("next_iso") == target]
    return {"date": target, "count": len(items), "items": items}


class AdvocateImportBody(BaseModel):
    enrolment_number: str = Field("", max_length=60, description="Bar enrolment/registration number, e.g. MP/1234/2010")
    advocate_name:    str = Field("", max_length=120, description="Fallback if no enrolment number")
    state:            str = Field("", max_length=60)
    court_code:       str = Field("", max_length=60)


@router.post("/import/advocate",
             summary="Import a lawyer's whole case list by Bar enrolment number (lawyer-centric onboarding)")
def import_by_advocate(body: AdvocateImportBody,
                       user: CurrentUser = Depends(get_current_user)) -> dict:
    if not (body.enrolment_number or body.advocate_name):
        raise HTTPException(status_code=400, detail="Give a Bar enrolment number or advocate name")
    try:
        cases = ecourts_client.import_by_advocate(
            body.enrolment_number, advocate_name=body.advocate_name,
            state=body.state, court_code=body.court_code,
        )
    except Exception as e:  # noqa: BLE001 — network / vendor errors
        log.warning("advocate import failed for %s: %s", body.enrolment_number, e)
        raise HTTPException(status_code=502, detail=f"advocate import failed: {e}")

    stored = []
    for case in cases:
        if not case.get("cnr"):
            continue
        row = cases_storage.add_case(user_id=user.id, case=case)
        if row:
            stored.append(_diary_item(row))
    return {"ok": True, "imported": len(stored), "items": stored}


class AdvocateSearchBody(BaseModel):
    advocate_name: str = Field(..., min_length=1, max_length=120)
    city:          str = Field("", max_length=80, description="City/district to scope (e.g. Gwalior)")
    court_code:    str = Field("", max_length=60)
    state:         str = Field("", max_length=60)


class AdvocateConfirmBody(BaseModel):
    cnrs: list[str] = Field(..., description="CNRs the lawyer confirmed are theirs")


# Short-lived per-user cache of the last advocate search, so 'confirm' stores the
# ticked cases without a second paid fetch. In-memory (single instance) with a
# fetch_cnr fallback on miss.
_SEARCH_CACHE: dict = {}


@router.post("/import/advocate/search",
             summary="Find an advocate's cases (candidates to confirm — NOT stored yet)")
def advocate_search(body: AdvocateSearchBody,
                    user: CurrentUser = Depends(get_current_user)) -> dict:
    """Step 1 of the disambiguating import: return the pending cases tagged to
    this advocate name so the lawyer can tick which are actually theirs. Nothing
    is saved here — same-name strangers are filtered out at the confirm step."""
    try:
        cases = ecourts_client.import_by_advocate(
            "", advocate_name=body.advocate_name, state=body.state,
            court_code=body.court_code, city=body.city)
    except Exception as e:  # noqa: BLE001
        log.warning("advocate search failed for %s: %s", body.advocate_name, e)
        raise HTTPException(status_code=502, detail=f"search failed: {e}")

    _SEARCH_CACHE[user.id] = {c["cnr"]: c for c in cases if c.get("cnr")}
    candidates = [{
        "cnr": c.get("cnr"),
        "case_title": c.get("case_title"),
        "court_name": c.get("court_name"),
        "case_number": c.get("case_number"), "case_year": c.get("case_year"),
        "next_hearing_date": c.get("next_hearing_date"),
        "stage": c.get("stage"), "case_type": c.get("case_type"),
        "sections": c.get("sections") or [],
        "petitioner_name": c.get("petitioner_name"),
        "respondent_name": c.get("respondent_name"),
        # co-advocates on the case — the disambiguation signal (his cases cluster)
        "advocates": (c.get("petitioner_advocates") or []) + (c.get("respondent_advocates") or []),
    } for c in cases]
    return {"count": len(candidates), "candidates": candidates}


@router.post("/import/advocate/confirm",
             summary="Store only the cases the lawyer confirmed are theirs")
def advocate_confirm(body: AdvocateConfirmBody,
                     user: CurrentUser = Depends(get_current_user)) -> dict:
    cache = _SEARCH_CACHE.get(user.id, {})
    stored = []
    for cnr in body.cnrs:
        case = cache.get(cnr)
        if case is None:                      # cache expired → re-fetch by CNR
            try:
                case = ecourts_client.fetch_cnr(cnr)
            except Exception:  # noqa: BLE001
                continue
        row = cases_storage.add_case(user_id=user.id, case=case)
        if row:
            stored.append(_diary_item(row))
    return {"ok": True, "imported": len(stored), "items": stored}


_DIARY_VISION_PROMPT = (
    "You are digitising ONE photographed page of an Indian advocate's HANDWRITTEN "
    "court diary — a म.प्र. जिला न्यायालय 'विधि वार्षिकी' cause-list register. The whole "
    "page is the cause list for a SINGLE date, printed in the box at the top "
    "(e.g. '16 जुलाई … 2026 गुरुवार'). Read that as page_date in dd/mm/yyyy.\n\n"
    "The register has ruled COLUMNS, left→right: [गत दि.] [न्याया. = COURT/JUDGE] "
    "[प्र.क्र. = CASE No.] [शीर्षक = PARTIES]. Each handwritten row is one matter. Use "
    "the COLUMN POSITION to decide what each token is — not just word order.\n\n"
    "Rules — the diary's grammar, follow exactly:\n"
    "1. COURT (न्याया. column, just LEFT of the case number): the court is named EITHER "
    "by a bench code — CJM, ACJM, SPJ, ADJ, '1st ADJ', ordinal benches ('6th','8th',"
    "'22nd'), 'JM', 'F.C.', 'MJCR', 'H.D.F.C', 'SC', 'JMFC' — OR, VERY COMMONLY in "
    "Sessions/District courts, by the PRESIDING JUDGE'S PERSONAL NAME (an individual's "
    "name written in the न्याया. column). Either way put it in `court`. CRITICAL: a "
    "personal name in this न्याया. position is the JUDGE — it is NOT a party. Never put "
    "a judge's name in `party`, and never put a party's name in `court`.\n"
    "2. CLIENT: the lawyer's own short tag in the far-LEFT margin (before the court "
    "column), e.g. Rajvi, Jyotsna, Ansari, Bhupendra → `client`. Distinct from the judge.\n"
    "3. case_no: the number bearing a TWO-DIGIT YEAR in the 08–26 range (e.g. 5435/24, "
    "679/25, 7910/16). If a row shows two numbers, pick the YEAR-BEARING one.\n"
    "4. PARTY (शीर्षक column): the contesting parties. Format ALWAYS as '<A> Vs <B>' — "
    "criminal is 'State Vs <accused>'; civil is '<plaintiff> Vs <defendant>'. '@' marks "
    "an alias, keep it (e.g. 'State Vs Jeetu @ Shivcharan').\n"
    "5. PREVIOUS DATE: the शीर्षक text usually embeds the PREVIOUS hearing date (गत दि.) "
    "as a DD/MM token BETWEEN the two party names, e.g. 'State 26/2 Jeetu' → parties "
    "'State Vs Jeetu', prev_date '26/2'. Pull that DD/MM into `prev_date` and keep it OUT "
    "of the party names. (A lone number with NO slash, e.g. '297', is an IPC/BNS section "
    "→ put it in `section`, it is NOT a date.)\n"
    "6. proceeding + next_date are usually BLANK on a fresh cause page (the right-hand "
    "कार्यवाही/आगे दि grid is empty — filled AFTER the hearing). Only set next_date if a "
    "future date is actually written.\n"
    "7. ✓ = attended/done, ✗ = not done → `mark` ('done' | 'pending' | '').\n"
    "8. Preserve the original script (Hindi/English). Empty string for anything "
    "unreadable. NEVER invent a row, name, case number or date.\n\n"
    "Worked examples (from real pages):\n"
    '  "Rajvi 4764/09 State 26/2 Jeetu @ Shivcharan" → '
    '{"client":"Rajvi","court":"","case_no":"4764/09","section":"",'
    '"party":"State Vs Jeetu @ Shivcharan","prev_date":"26/2","proceeding":"","next_date":"","mark":""}\n'
    '  "1st ADJ 679/25 State 9/7 Sourabh" → '
    '{"client":"","court":"1st ADJ","case_no":"679/25","section":"","party":"State Vs Sourabh",'
    '"prev_date":"9/7","proceeding":"","next_date":"","mark":""}\n'
    '  (Sessions court, JUDGE name in न्याया.) "Devendra Sharma 2073/21 State 8/7 Amit" → '
    '{"client":"","court":"Devendra Sharma","case_no":"2073/21","section":"",'
    '"party":"State Vs Amit","prev_date":"8/7","proceeding":"","next_date":"","mark":""}\n'
    '  (civil) "Pallavi 2601/26 Madhu Rattan 4/7 Ashish Rathore" → '
    '{"client":"Pallavi","court":"","case_no":"2601/26","section":"",'
    '"party":"Madhu Rattan Vs Ashish Rathore","prev_date":"4/7","proceeding":"","next_date":"","mark":""}\n\n'
    'Return ONLY this JSON object: {"page_date":"dd/mm/yyyy","rows":[ …one object per '
    'row, top-to-bottom, with keys client, court, case_no, section, party, prev_date, '
    'proceeding, next_date, mark… ]}. Read EVERY handwritten row on the page.'
)


_DIARY_JSON_SHAPE = (
    'Return ONLY a JSON object (no prose): '
    '{"page_date":"<the single date this whole cause-list page is FOR — often '
    'written at the top/header of the page, e.g. \'दिनांक 14/07/2026\' or a date '
    'heading; empty string if none is visible>",'
    '"rows":[{"client":"<margin nickname, else the non-State party name>",'
    '"case_no":"<प्र.क्र. case number, e.g. 5677/24>","court":"<न्याया. court/judge>",'
    '"title":"<शीर्षक cause title / parties>","proceeding":"<कार्यवाही stage / what '
    'is listed for>","last_date":"<गत दि. previous hearing date>",'
    '"next_date":"<आगे दि. the next hearing date, if written>"}]}. '
    "Preserve the original script (Hindi/English) for names. Use an empty string for "
    "any blank cell. Do NOT invent rows or values you cannot see."
)

_DIARY_OCR_PROMPT = (
    "You are reading one page of an Indian advocate's handwritten court diary "
    "(म.प्र. जिला न्यायालय 'विधि वार्षिकी' cause-list register). It is a ruled table, and "
    "the WHOLE page is the cause list for ONE hearing date (that date is usually "
    "written at the very top of the page). The printed column headers, LEFT to RIGHT, are:\n"
    "1. गत दि. — the PREVIOUS hearing date\n"
    "2. न्याया. — the court number / judge\n"
    "3. प्र. क्र. (प्रकरण क्रमांक) — the CASE NUMBER, e.g. '5677/24', '33CH/25', '223/22'\n"
    "4. शीर्षक — the CAUSE TITLE / parties, usually 'State <section> <name>' e.g. 'State 297 Vedprakash Tiwari'\n"
    "5. कार्यवाही / आगे दि. — the stage/proceeding and the NEXT hearing date\n"
    "The far-LEFT margin often has the lawyer's short nickname for the client (e.g. 'Rgub', 'Swati', 'GM').\n"
    "Read EVERY row, top to bottom, including the right-hand 'अतिरिक्त पृष्ठ' (additional) column if present. "
    + _DIARY_JSON_SHAPE
)


_DIARY_STRUCT_SYS = (
    "You are given OCR'd text/markdown of ONE page of an Indian advocate's court "
    "diary register (म.प्र. जिला न्यायालय 'विधि वार्षिकी'). The whole page is the cause "
    "list for ONE hearing date, usually printed at the top. Its columns are: गत दि. "
    "(the PREVIOUS hearing date) · न्याया. (court/judge) · प्र. क्र. (case number, e.g. "
    "'5677/24') · शीर्षक (cause title, e.g. 'State <section> <name>') · कार्यवाही/आगे दि. "
    "(stage + next date). The far-left margin may carry the lawyer's client nickname. "
    + _DIARY_JSON_SHAPE
)


_ROW_FIELDS = ("client", "case_no", "court", "title", "proceeding", "last_date", "next_date")


def _blank_row() -> dict:
    return {k: "" for k in _ROW_FIELDS}


def _detect_page_date(md: str) -> str:
    """Find the single date this whole cause-list page is FOR — usually written at
    the top ('दिनांक 14/07/2026', 'Date: 14/7/26', or a bare date heading). Scans the
    first ~12 non-empty lines and returns the first date-looking token, else ''."""
    import re as _re
    date_re = _re.compile(r'(\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})')
    seen = 0
    for line in (md or "").splitlines():
        s = line.strip().strip("#*| ")
        if not s:
            continue
        seen += 1
        if seen > 12:
            break
        # skip obvious table data rows (many pipes) — the header date sits above them
        if line.count("|") >= 3:
            continue
        m = date_re.search(s)
        if m:
            return m.group(1)
    return ""


def _rows_from_markdown(md: str) -> list:
    """Parse Sarvam's OCR'd diary TABLE directly (deterministic, no LLM). Each data
    row is pipe-delimited: <न्याया.> | <प्र.क्र.> | <शीर्षक> | <कार्यवाही/आगे दि.> … . The
    date embedded in शीर्षक ('State 26/2 Jeetu') is the PREVIOUS date → last_date; the
    title keeps only the parties; a date in a later cell is read as the next_date."""
    import re as _re
    case_re = _re.compile(r'\d{1,4}\s*/\s*\d{2,4}')
    dmy_re = _re.compile(r'\b(\d{1,2}[/.\-]\d{1,2}(?:[/.\-]\d{2,4})?)\b')
    skip = ("न्याया", "शीर्षक", "कार्यवाही", "आगे", "thead", "tbody", "<table", "प्र. क्र", "प्र.क्र")
    out = []
    for line in (md or "").splitlines():
        if line.count("|") < 2:
            continue
        low = line.lower()
        if any(s.lower() in low for s in skip):
            continue
        cells = [c.strip(" *✓|") for c in line.split("|")]
        cells = [c for c in cells if c != ""]
        ci = next((i for i, c in enumerate(cells) if case_re.search(c)), None)
        if ci is None:
            continue
        case_no = case_re.search(cells[ci]).group(0).replace(" ", "")
        # column BEFORE the case number is न्याया. (court/judge) — NOT the party.
        court = cells[ci - 1] if ci - 1 >= 0 else ""
        # anything further left is the गत दि. (previous date) column — grab a date.
        last_date = ""
        for lc in cells[:max(ci - 1, 0)]:
            lm = dmy_re.search(lc)
            if lm:
                last_date = lm.group(1)
                break
        # column AFTER is शीर्षक — the actual cause title / parties.
        title = cells[ci + 1] if ci + 1 < len(cells) else ""
        if not last_date:
            m = dmy_re.search(title)
            last_date = m.group(1) if m else ""
        clean_title = _re.sub(r'\s{2,}', ' ', dmy_re.sub("", title)).strip() if m else title.strip()
        # anything past the title is कार्यवाही / आगे दि. — pull a date out as next_date.
        tail = " ".join(cells[ci + 2:]) if ci + 2 < len(cells) else ""
        nm = dmy_re.search(tail)
        next_date = nm.group(1) if nm else ""
        proceeding = _re.sub(r'\s{2,}', ' ', dmy_re.sub("", tail)).strip()
        row = _blank_row()
        row.update({"case_no": case_no, "court": court, "title": clean_title,
                    "proceeding": proceeding, "last_date": last_date, "next_date": next_date})
        out.append(row)
    return out


def _clean_row(r: dict) -> dict:
    row = _blank_row()
    for k in _ROW_FIELDS:
        row[k] = (r.get(k) or "").strip()
    return row


def _parse_diary_payload(raw_text: str) -> tuple:
    """Parse an LLM/vision reply into (page_date, rows). Accepts the new
    {"page_date","rows":[…]} object AND a bare [ … ] array (back-compat)."""
    import json as _json, re as _re
    txt = (raw_text or "").strip()
    parsed = None
    obj = _re.search(r"\{.*\}", txt, _re.S)
    if obj:
        try:
            parsed = _json.loads(obj.group(0))
        except Exception:  # noqa: BLE001
            parsed = None
    if not isinstance(parsed, dict):
        arr = _re.search(r"\[.*\]", txt, _re.S)
        if arr:
            try:
                parsed = {"rows": _json.loads(arr.group(0))}
            except Exception:  # noqa: BLE001
                parsed = None
    if not isinstance(parsed, dict):
        return "", []
    page_date = (parsed.get("page_date") or "").strip()
    rows = []
    for r in parsed.get("rows") or []:
        if isinstance(r, dict) and (r.get("client") or r.get("case_no") or r.get("title")):
            rows.append(_clean_row(r))
    return page_date, rows


def _merge_rows(primary: list, secondary: list) -> list:
    """Fill empty cells of the primary (LLM) rows from the deterministic rows,
    matched on case number. Deterministic-only rows the LLM missed are appended."""
    def key(r):
        return (r.get("case_no") or "").replace(" ", "")
    sec_by_no = {key(r): r for r in secondary if key(r)}
    used = set()
    out = []
    for r in primary:
        s = sec_by_no.get(key(r))
        if s:
            used.add(key(r))
            for f in _ROW_FIELDS:
                if not r.get(f) and s.get(f):
                    r[f] = s[f]
        out.append(r)
    for s in secondary:
        if key(s) and key(s) not in used:
            out.append(s)
    return out


_COURT_CODE_RE = __import__("re").compile(
    r'^\s*(\d{1,2}(?:st|nd|rd|th)\s*ADJ|\d{1,2}(?:st|nd|rd|th)|A?CJM|SPJ|ADJ|'
    r'F\.?\s*C\.?|MJCR|H\.?\s*D\.?\s*F\.?\s*C\.?|JMFC|SDM|SC)\b\.?',
    __import__("re").I)


def _rows_from_gemini(payload) -> tuple:
    """Map Gemini's vision output {page_date, rows:[{client,court,case_no,section,
    party,proceeding,next_date,mark}]} onto our row schema."""
    if not isinstance(payload, dict):
        return "", []
    page_date = (payload.get("page_date") or "").strip()
    out = []
    for r in payload.get("rows") or []:
        if not isinstance(r, dict):
            continue
        client = (r.get("client") or "").strip()
        case_no = (r.get("case_no") or "").strip()
        party = (r.get("party") or "").strip()
        if not (client or case_no or party):
            continue
        proc = (r.get("proceeding") or "").strip()
        mark = (r.get("mark") or "").strip()
        if mark and mark.lower() not in proc.lower():
            proc = (proc + (" · " if proc else "") + mark).strip()
        row = _blank_row()
        row.update({"client": client, "case_no": case_no,
                    "court": (r.get("court") or "").strip(),
                    "title": party or client or case_no,
                    "proceeding": proc,
                    "last_date": (r.get("prev_date") or r.get("last_date") or "").strip(),
                    "next_date": (r.get("next_date") or "").strip()})
        out.append(row)
    return page_date, out


def _normalize_diary_rows(rows: list) -> list:
    """Safety net applied to every OCR path: pull a leading court code out of the
    client/title into `court`, and strip whitespace from the case number. Keeps
    the year-bearing case-number rule and court-code detection robust even if the
    model slipped."""
    import re as _re
    for r in rows:
        court = (r.get("court") or "").strip()
        # a leading court code can land in client OR title — pull it out of both
        for f in ("client", "title"):
            m = _COURT_CODE_RE.match(r.get(f) or "")
            if m:
                if not court:
                    court = m.group(1).strip()
                r[f] = r[f][m.end():].strip(" -–—:")
        r["court"] = court
        r["case_no"] = _re.sub(r"\s+", "", r.get("case_no") or "")
        # if stripping emptied the title, fall back to a sensible row label
        if not (r.get("title") or "").strip():
            r["title"] = (r.get("client") or r.get("proceeding") or r.get("case_no") or "").strip()
    return rows


def _flag_rows(rows: list) -> list:
    """Attach a `flags` list naming cells the lawyer should double-check before
    saving (blank critical fields). The review UI amber-highlights these."""
    for r in rows:
        flags = []
        if not r.get("case_no"):
            flags.append("case_no")
        if not (r.get("title") or r.get("client")):
            flags.append("title")
        if not r.get("next_date"):
            flags.append("next_date")
        r["flags"] = flags
    return rows


def _normalize_upload(data: bytes, filename: str, mime: str):
    """Accept any phone-photo format. PDF/JPEG/PNG pass through; everything else
    (HEIC/HEIF from iPhones, WebP, TIFF, GIF, BMP) is converted to JPEG so both
    Sarvam and Groq accept it."""
    import io as _io
    m, f = (mime or "").lower(), (filename or "").lower()
    if m == "application/pdf" or f.endswith(".pdf"):
        return data, (filename or "doc.pdf"), "application/pdf"
    if m in ("image/jpeg", "image/png") or f.endswith((".jpg", ".jpeg", ".png")):
        return data, (filename or "page.jpg"), ("image/png" if f.endswith(".png") else "image/jpeg")
    try:
        from PIL import Image
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except Exception:  # noqa: BLE001 — non-HEIC formats still work via PIL
            pass
        img = Image.open(_io.BytesIO(data)).convert("RGB")
        buf = _io.BytesIO()
        img.save(buf, "JPEG", quality=90)
        base = filename.rsplit(".", 1)[0] if "." in (filename or "") else "page"
        return buf.getvalue(), base + ".jpg", "image/jpeg"
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=400,
                            detail=f"Couldn't read that image format ({mime}). Try JPG, PNG, PDF or HEIC. ({e})")


def _run_diary_ocr(data: bytes, fname: str, mime: str):
    """Blocking OCR pipeline, best engine first:
      1) Gemini Flash VISION — reads the ruled columns spatially and returns
         structured rows in one call (fixes the flatten-then-guess failure);
      2) Sarvam DI text → LLM structuring + deterministic table parse (fallback);
      3) Groq vision (last resort).
    A shared validation pass (_normalize_diary_rows) then enforces the diary
    grammar (leading court code, year-bearing case number) on whatever came back.
    Runs in a threadpool so the slow vendor calls never block the event loop.

    Returns (page_date, rows, engine, err). Rows carry a `flags` list of cells to
    double-check."""
    data, fname, mime = _normalize_upload(data, fname, mime)
    rows: list = []
    page_date = ""
    engine = ""
    sarvam_err = ""
    # 1) Gemini Flash vision — the preferred path for handwritten ruled pages.
    if gemini.enabled():
        try:
            payload = gemini.generate_json(_DIARY_VISION_PROMPT, image=data, mime=mime)
            page_date, rows = _rows_from_gemini(payload)
            engine = "gemini"
        except Exception as e:  # noqa: BLE001 — degrade to Sarvam/Groq
            sarvam_err = str(e)[:300]
            log.warning("Gemini diary OCR failed, falling back: %s", e)
    if not rows and sarvam.enabled():
        try:
            md = sarvam.digitize_to_text(data, filename=fname, mime=mime)
            det_rows = _rows_from_markdown(md)      # deterministic corroboration
            try:
                from headnote.llm.client import _call_deepseek_or_groq
                structured, _m = _call_deepseek_or_groq(
                    _DIARY_STRUCT_SYS, md, max_tokens=3500, json_mode=True)
                page_date, llm_rows = _parse_diary_payload(structured)
            except Exception as e:  # noqa: BLE001 — LLM hiccup → lean on deterministic
                log.warning("diary LLM structuring failed: %s", e)
                llm_rows = []
            rows = _merge_rows(llm_rows, det_rows) if llm_rows else det_rows
            if not page_date:
                page_date = _detect_page_date(md)
            engine = "sarvam"
        except Exception as e:  # noqa: BLE001 — degrade, never hard-fail
            sarvam_err = str(e)[:300]
            log.warning("Sarvam diary OCR failed, falling back to Groq: %s", e)
    if not rows:
        from headnote.drafter.ocr import ocr_text_pages, _rasterize_pdfs
        from headnote.drafter import office
        media_pages, _o = office.collect_uploads([(data, mime, fname)], max_bytes=20 * 1024 * 1024)
        pages: list = []
        for d, mt in media_pages:
            pages.extend(_rasterize_pdfs([(d, mt)]) if mt == "application/pdf" else [(d, mt)])
        if pages:
            raw = ocr_text_pages(pages, prompt=_DIARY_OCR_PROMPT)
            pd, rows = _parse_diary_payload(raw)
            page_date = page_date or pd
            engine = engine or "groq"
    return page_date, _flag_rows(_normalize_diary_rows(rows)), engine, sarvam_err


@router.post("/import/diary-photo",
             summary="OCR a photo of the paper diary/cause-list into case rows (candidates)")
async def import_diary_photo(file: UploadFile = File(...),
                            user: CurrentUser = Depends(get_current_user)) -> dict:
    """Read a diary-page photo → parsed rows for the lawyer to review + confirm.
    Nothing is stored. Sarvam Document Intelligence (Indic-native) → deterministic
    table parse; Groq vision only as a last-resort fallback."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    fname = file.filename or "diary.jpg"
    mime = (file.content_type or "").split(";")[0].strip() or "image/jpeg"
    try:
        page_date, rows, engine, sarvam_err = await asyncio.to_thread(
            _run_diary_ocr, data, fname, mime)
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"OCR failed: {e}")
    return {"count": len(rows), "page_date": page_date, "rows": rows,
            "engine": engine, "sarvam_error": sarvam_err}


class DiaryConfirmBody(BaseModel):
    rows: list[dict] = Field(..., description="reviewed diary rows to save")
    page_date: Optional[str] = Field(
        None, description="the single hearing date this cause-list page is FOR")


def _split_caseno(case_no: str) -> tuple:
    """'5677/24' → ('5677', '24'); bare '5677' → ('5677', '')."""
    import re as _re
    m = _re.match(r"\s*(\d{1,6})\s*[/\-]\s*(\d{2,4})", case_no or "")
    if m:
        return m.group(1), m.group(2)
    m = _re.match(r"\s*(\d{2,6})", case_no or "")
    return (m.group(1) if m else ""), ""


@router.post("/import/diary-confirm", summary="Save reviewed diary-photo rows as matters")
def import_diary_confirm(body: DiaryConfirmBody,
                         user: CurrentUser = Depends(get_current_user)) -> dict:
    """Save reviewed rows. Each page is ONE hearing date's cause list, so:
      • an existing matter (matched on case number + court) gets a hearing-log
        entry (page_date → next_date) instead of a duplicate — re-importing
        successive days builds the case history automatically;
      • a new matter is created with the page's date as its last-listed date and
        the written next date as its next hearing.
    """
    import hashlib
    page_date = (body.page_date or "").strip()
    stored, logged = [], 0
    for r in body.rows:
        client = (r.get("client") or "").strip()
        case_no = (r.get("case_no") or "").strip()
        title = (r.get("title") or "").strip()
        court = (r.get("court") or "").strip()
        next_date = (r.get("next_date") or "").strip()
        # previous hearing date: prefer the per-row गत दि. the OCR pulled out, else
        # fall back to the page's own date.
        last_date = (r.get("last_date") or "").strip() or page_date
        proceeding = (r.get("proceeding") or "").strip()
        if not (client or case_no):
            continue

        num, yr = _split_caseno(case_no)
        existing = cases_storage.find_case_by_number(
            user_id=user.id, case_number=num or case_no, case_year=yr,
            court_name=court) if (num or case_no) else None
        if existing:
            # this page records another hearing of a matter we already track
            cases_storage.log_hearing(
                existing["id"], user_id=user.id,
                hearing_date=last_date or None,
                what_happened=proceeding or "listed (from diary page)",
                next_hearing_date=next_date or None, stage=proceeding or None)
            logged += 1
            stored.append(_diary_item(cases_storage.get_case(existing["id"], user_id=user.id)))
            continue

        key = hashlib.md5(f"{user.id}|{client}|{case_no}|{court}".encode()).hexdigest()[:12]
        case = {
            "cnr": "DY" + key.upper(),
            "source": "diary",
            "case_title": title or client or case_no,
            "case_number": num or case_no, "case_year": yr,
            "court_name": court,
            "stage": proceeding,
            "next_hearing_date": next_date,
            "last_listed_date": last_date,
            "sections": [],
            "client": {"name": client} if client else {},
        }
        row = cases_storage.add_case(user_id=user.id, case=case)
        if row and last_date:
            # seed the history with this page's listing so the folder timeline shows it
            cases_storage.log_hearing(
                row["id"], user_id=user.id, hearing_date=last_date,
                what_happened=proceeding or "listed (from diary page)",
                next_hearing_date=next_date or None, stage=proceeding or None)
        if row:
            stored.append(_diary_item(cases_storage.get_case(row["id"], user_id=user.id)))
    return {"ok": True, "imported": len(stored), "logged": logged, "items": stored}


@router.post("/_reset", summary="[testing] wipe this user's matters so the flow restarts fresh")
def reset_cases(user: CurrentUser = Depends(get_current_user)) -> dict:
    """Testing-mode only: clears the signed-in user's matters + hearing logs so a
    page refresh restarts the onboarding flow from empty. Remove before GA."""
    n = cases_storage.delete_all_cases(user_id=user.id)
    return {"ok": True, "cleared": n}


@router.get("/_probe", summary="[temporary] raw vendor probe to lock the live shape")
def probe(key: str, path: str = "", cnr: str = "", enrolment: str = "",
          user: CurrentUser = Depends(get_current_user)) -> dict:
    """Fire one raw GET at the vendor (auth + browser UA) and return status +
    body snippet, so we can capture the real response shape from prod. Gated by
    CNR_API_PROBE_KEY; removed once the mapping is locked."""
    from headnote import config as _cfg
    if not _cfg.CNR_API_PROBE_KEY or key != _cfg.CNR_API_PROBE_KEY:
        raise HTTPException(status_code=403, detail="probe disabled")
    target = path or _cfg.CNR_API_ADVOCATE_PATH
    params = {}
    if cnr:
        params["cnr"] = cnr
    if enrolment:
        params.update({"bar_number": enrolment, "enrolment_number": enrolment, "advocate": enrolment})
    return ecourts_client.probe_raw(target, params)


@router.get("/{case_id}", summary="Get one matter (full payload + suggestions)")
def get_case(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return _enrich(row)


@router.patch("/{case_id}/client", summary="Save/merge the client's details on a matter")
def set_client(case_id: str, body: ClientBody,
               user: CurrentUser = Depends(get_current_user)) -> dict:
    patch = body.model_dump(exclude_none=True)
    row = cases_storage.update_client(case_id, user_id=user.id, client=patch)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "case": _enrich(row)}


@router.delete("/{case_id}", summary="Remove a matter")
def delete_case(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    if not cases_storage.delete_case(case_id, user_id=user.id):
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "deleted": case_id}


@router.post("/{case_id}/draft/{story_id}",
             summary="Create a draft PRE-FILLED from this matter (the differentiator)")
def draft_for_case(case_id: str, story_id: str,
                   user: CurrentUser = Depends(get_current_user)) -> dict:
    """Load the matter → map its parties/court/sections (+ client details) onto
    the template's fields → create a real draft → hand back a link to review it."""
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")

    if story_id not in mapping.SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"draft type '{story_id}' not supported yet "
                   f"(have: {', '.join(mapping.SUPPORTED)})",
        )
    s = stories.get_story(story_id)
    if s is None:
        raise HTTPException(status_code=404, detail=f"unknown story_id={story_id!r}")

    answers = mapping.map_case_to_answers(story_id, row["case_json"])
    label = _STORY_LABELS.get(story_id, story_id)
    draft = draft_storage.create_draft(
        story_id=story_id,
        template_version=s.template_version,
        user_id=user.id,
        lang="hi",
        answers=answers,
        title=f"{label} — {row.get('case_title') or row.get('cnr')}",
        case_id=case_id,
    )
    return {
        "ok": True,
        "draft_id": draft.id,
        "story_id": story_id,
        "review_url": f"/draft/{story_id}/review?draft={draft.id}",
        "answers": answers,
    }


# ---------------------------------------------------------------- diary log
class HearingLogBody(BaseModel):
    hearing_date:      Optional[str] = Field(None, description="Date this outcome is for")
    what_happened:     Optional[str] = Field(None, max_length=2000)
    next_hearing_date: Optional[str] = Field(None, description="New next date")
    stage:             Optional[str] = Field(None, max_length=200)


@router.post("/{case_id}/hearing-log", summary="Log a hearing outcome + roll the next date")
def hearing_log(case_id: str, body: HearingLogBody,
                user: CurrentUser = Depends(get_current_user)) -> dict:
    row = cases_storage.log_hearing(
        case_id, user_id=user.id,
        hearing_date=body.hearing_date, what_happened=body.what_happened,
        next_hearing_date=body.next_hearing_date, stage=body.stage,
    )
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "case": _diary_item(row)}


@router.post("/{case_id}/refresh-next-date",
             summary="Re-fetch the case's next hearing date from the source")
def refresh_next_date(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    """Roll a matter forward: re-query the CNR source for the new next date.
    (In mock mode this is deterministic; live mode returns the fresh listing.)"""
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    cnr = row.get("cnr") or ""
    if not ecourts_client.is_valid_cnr(cnr):
        # Manual / diary-sourced matter with no real CNR — nothing to re-fetch.
        return {"ok": False, "reason": "no fetchable CNR", "case": _diary_item(row)}
    try:
        fresh = ecourts_client.fetch_cnr(cnr)
    except Exception as e:  # noqa: BLE001
        log.warning("refresh failed for %s: %s", cnr, e)
        raise HTTPException(status_code=502, detail=f"refresh failed: {e}")
    updated = cases_storage.set_next_date(
        case_id, user_id=user.id,
        next_hearing_date=fresh.get("next_hearing_date"), stage=fresh.get("stage"),
    )
    return {"ok": True, "case": _diary_item(updated)}


class NextDateBody(BaseModel):
    next_hearing_date: str = Field(..., description="the next hearing date to set (any common format)")
    stage: Optional[str] = Field(None, max_length=200)


@router.post("/{case_id}/set-next-date",
             summary="Manually set/edit a matter's next hearing date (no outcome log)")
def set_next_date(case_id: str, body: NextDateBody,
                  user: CurrentUser = Depends(get_current_user)) -> dict:
    """The manual fallback for matters with no fetchable CNR (photo/manual): the
    lawyer types the next date the judge gave and it's saved against the matter,
    re-grouping it onto that day's board. Use hearing-log when there's also an
    outcome to record; this is the quick date-only edit."""
    row = cases_storage.set_next_date(
        case_id, user_id=user.id,
        next_hearing_date=body.next_hearing_date.strip() or None, stage=body.stage)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "case": _diary_item(row)}


@router.post("/refresh-all-dates",
             summary="Re-fetch next dates for every matter with a fetchable CNR")
def refresh_all_dates(user: CurrentUser = Depends(get_current_user)) -> dict:
    """One tap to roll the whole docket forward: refresh next dates for all
    matters that have a real eCourts CNR. Photo/manual matters (no CNR) are
    skipped and reported so the lawyer knows to set those by hand."""
    refreshed, skipped, failed = 0, 0, 0
    for r in cases_storage.list_cases(user_id=user.id, limit=500):
        cnr = r.get("cnr") or ""
        if not ecourts_client.is_valid_cnr(cnr):
            skipped += 1
            continue
        try:
            fresh = ecourts_client.fetch_cnr(cnr)
            cases_storage.set_next_date(
                r["id"], user_id=user.id,
                next_hearing_date=fresh.get("next_hearing_date"), stage=fresh.get("stage"))
            refreshed += 1
        except Exception as e:  # noqa: BLE001 — one bad CNR shouldn't sink the batch
            log.warning("refresh-all: %s failed: %s", cnr, e)
            failed += 1
    return {"ok": True, "refreshed": refreshed, "skipped": skipped, "failed": failed}


class ResolveCnrBody(BaseModel):
    advocate_name: str = Field("", max_length=120, description="lawyer's name as on the cause list")
    city:          str = Field("", max_length=80)
    court_code:    str = Field("", max_length=60)
    state:         str = Field("", max_length=60)


@router.post("/{case_id}/resolve-cnr",
             summary="Find the real eCourts CNR for a diary/manual matter (candidates)")
def resolve_cnr_candidates(case_id: str, body: ResolveCnrBody,
                           user: CurrentUser = Depends(get_current_user)) -> dict:
    """Best-effort: match this matter's case number against the lawyer's eCourts
    docket to recover a real CNR, so the next date becomes API-refreshable.
    Returns candidates for the lawyer to confirm — nothing is changed yet."""
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    case_no = row.get("case_number") or ""
    if row.get("case_year"):
        case_no = f"{case_no}/{row['case_year']}"
    try:
        cands = ecourts_client.resolve_cnr(
            case_number=case_no, advocate_name=body.advocate_name, city=body.city,
            court_code=body.court_code, state=body.state,
            court_name=row.get("court_name") or "")
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"resolve failed: {e}")
    out = [{"cnr": c.get("cnr"), "case_title": c.get("case_title"),
            "court_name": c.get("court_name"),
            "case_number": c.get("case_number"), "case_year": c.get("case_year"),
            "next_hearing_date": c.get("next_hearing_date"), "stage": c.get("stage"),
            "petitioner_name": c.get("petitioner_name"),
            "respondent_name": c.get("respondent_name")} for c in cands]
    return {"count": len(out), "candidates": out}


class ResolveConfirmBody(BaseModel):
    cnr: str = Field(..., min_length=1, max_length=32)


@router.post("/{case_id}/resolve-cnr/confirm",
             summary="Upgrade a diary/manual matter to a confirmed real CNR")
def resolve_cnr_confirm(case_id: str, body: ResolveConfirmBody,
                        user: CurrentUser = Depends(get_current_user)) -> dict:
    """Apply the CNR the lawyer picked: re-fetch the full case and replace the
    matter's identity in place (same folder, logs and client preserved)."""
    if cases_storage.get_case(case_id, user_id=user.id) is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    try:
        fresh = ecourts_client.fetch_cnr(body.cnr)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"CNR lookup failed: {e}")
    row = cases_storage.replace_case_identity(case_id, user_id=user.id, case=fresh)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    return {"ok": True, "case": _diary_item(row)}


# ---------------------------------------------------------------- the folder
@router.get("/{case_id}/folder",
            summary="Everything filed under one matter (recordings/drafts/docs/case-law)")
def case_folder(case_id: str, user: CurrentUser = Depends(get_current_user)) -> dict:
    row = cases_storage.get_case(case_id, user_id=user.id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")

    recordings = consult_storage.list_consultations(user_id=user.id, case_id=case_id)
    drafts = [d.to_dict() for d in draft_storage.list_drafts(user_id=user.id, case_id=case_id, limit=100)]
    documents = docs_storage.list_documents(user_id=user.id, case_id=case_id)
    caselaw: list = []  # matter-linked case-law needs a Supabase matter_id column — deferred

    return {
        "case": _diary_item(row),
        "client": (row.get("case_json") or {}).get("client") or {},
        "recordings": recordings,
        "drafts": drafts,
        "documents": documents,
        "caselaw": caselaw,
        "hearing_logs": cases_storage.list_hearing_logs(case_id, user_id=user.id),
    }


class LinkBody(BaseModel):
    artifact_type: str = Field(..., description="recording | draft | document")
    artifact_id:   str = Field(..., min_length=1, max_length=64)


def _apply_link(kind: str, artifact_id: str, *, case_id: Optional[str], user_id) -> bool:
    if kind in ("recording", "consultation"):
        return consult_storage.set_consultation_case(artifact_id, case_id=case_id, user_id=user_id)
    if kind == "draft":
        return draft_storage.set_draft_case(artifact_id, case_id=case_id, user_id=user_id)
    if kind in ("document", "doc"):
        return docs_storage.set_document_case(artifact_id, case_id=case_id, user_id=user_id)
    raise HTTPException(status_code=400, detail=f"unknown artifact_type {kind!r}")


@router.post("/{case_id}/link", summary="File an existing recording/draft/document under this matter")
def link_artifact(case_id: str, body: LinkBody,
                  user: CurrentUser = Depends(get_current_user)) -> dict:
    if cases_storage.get_case(case_id, user_id=user.id) is None:
        raise HTTPException(status_code=404, detail=f"no case with id={case_id!r}")
    ok = _apply_link(body.artifact_type, body.artifact_id, case_id=case_id, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found or not yours")
    return {"ok": True}


@router.post("/{case_id}/unlink", summary="Remove an artifact from this matter")
def unlink_artifact(case_id: str, body: LinkBody,
                    user: CurrentUser = Depends(get_current_user)) -> dict:
    ok = _apply_link(body.artifact_type, body.artifact_id, case_id=None, user_id=user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="artifact not found or not yours")
    return {"ok": True}
