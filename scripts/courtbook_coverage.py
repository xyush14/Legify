#!/usr/bin/env python3
"""Turn the courtbook research corpus into a coverage map + roadmap.

RESEARCH / COMPETITIVE-ANALYSIS ONLY. Reads the local corpus produced by
scripts/scrape_courtbook.py, compares courtbook.in's catalog against Headnote's
*real* draft registries (imported live — authoritative), and emits:

    research/courtbook/courtbook_coverage.xlsx   (sortable: Catalog + Summary sheets)
    research/courtbook/COURTBOOK_FINDINGS.md      (counts, gaps, recommended next types)

Nothing here is served or shipped. The output informs *which* native Kruti-Dev
templates to build next — built from real filed sources, never from courtbook's text.

Usage
-----
    python scripts/courtbook_coverage.py
    python scripts/courtbook_coverage.py --corpus research/courtbook/courtbook_corpus.jsonl
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Make the repo root importable so `from headnote.drafter import ...` resolves when
# this script is run directly (Python puts scripts/ on sys.path, not the repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

CORPUS_DEFAULT = Path("research/courtbook/courtbook_corpus.jsonl")
XLSX_DEFAULT = Path("research/courtbook/courtbook_coverage.xlsx")
MD_DEFAULT = Path("research/courtbook/COURTBOOK_FINDINGS.md")

# ---------------------------------------------------------------------------
# Practice-area buckets. Matched (lowercased substring) against the clean
# type_name + slug ONLY — never the body prose, which name-drops "writ",
# "Section 138" etc. incidentally and would make every bucket a catch-all.
# First matching rule wins, so order runs specific -> general.
# ---------------------------------------------------------------------------
BUCKET_RULES: list[tuple[str, list[str]]] = [
    ("motor/mact", ["motor", "mact", "accident claim"]),
    ("consumer", ["consumer"]),
    ("arbitration", ["arbitration", "arbitral"]),
    ("tax", ["income tax", "gst", "taxation", "tds", "itr"]),
    ("ip", ["copyright", "trademark", "trade mark", "patent", "intellectual property"]),
    ("labour/employment", ["labour", "labor", "industrial dispute", "apprentice",
                           "hr policies", "posh", "gratuity", "wages", "employment",
                           "job description"]),
    ("corporate/company", ["company", "incorporation", "memorandum of association",
                           "articles of association", "moa", "aoa", "resolution",
                           "shareholder", "llp", "insolvency", "ibc", "co-operative",
                           "society", "trust", "wakf"]),
    ("family", ["divorce", "maintenance", "custody", "guardian", "domestic violence",
                "matrimon", "marriage", "adoption", "conjugal", "restitution",
                "judicial separation", "family", "mentally ill", "will", "succession",
                "probate", "testamentary"]),
    ("property/conveyancing", ["sale", "gift deed", "lease", "mortgage", "partition",
                               "exchange deed", "easement", "release deed", "conveyanc",
                               "relinquish", "rent", "tenancy", "surrender", "possession",
                               "deed of"]),
    ("banking/finance", ["banking", "promissory", "bill of exchange", "letter of credit",
                         "guarantee", "indemnity", "hypothecation", "pledge", "bond",
                         "security document", "hire purchase", "surety"]),
    ("writs/constitutional", ["writ$", "habeas", "mandamus", "certiorari",
                              "public interest", "pil$"]),
    ("criminal/litigation", ["bail", "criminal", "fir", "quashing", "quash", "discharge",
                             "anticipatory", "ndps", "pocso", "offence", "cheque",
                             "dishonour", "negotiable instrument", "remand",
                             "charge sheet", "witness application", "case file"]),
    ("civil/litigation", ["civil", "plaint", "pleading", "written statement", "injunction",
                          "stay", "execution", "court application", "petition",
                          "specific relief", "service case", "revenue"]),
    ("commercial/contract", ["agreement", "contract", "mou", "franchise", "nda",
                             "non-disclosure", "partnership", "vendor", "joint venture",
                             "assignment", "business", "shipping", "transport",
                             "foreign collaboration", "service", "information technology",
                             "licence", "license"]),
    ("affidavit/oath", ["affidavit", "declaration", "undertaking", "oath"]),
    ("procedural/misc", ["vakalatnama", "power of attorney", "attorney", "notice",
                         "appointment", "memo", "receipt", "acknowledg", "noc", "appeal",
                         "revision", "application", "form", "medical"]),
]

# Wedge relevance per bucket (Headnote's wedge = MP criminal/family litigation drafting).
WEDGE = {
    "criminal/litigation": "HIGH", "family": "HIGH", "writs/constitutional": "HIGH",
    "motor/mact": "HIGH", "consumer": "HIGH",
    "civil/litigation": "MEDIUM", "procedural/misc": "MEDIUM", "affidavit/oath": "MEDIUM",
    "arbitration": "MEDIUM", "labour/employment": "MEDIUM", "tax": "MEDIUM",
    "banking/finance": "MEDIUM", "misc": "MEDIUM",
    "property/conveyancing": "LOW", "corporate/company": "LOW",
    "commercial/contract": "LOW", "ip": "LOW",
}

# Detect whether Headnote already covers a courtbook type. Each entry maps a
# Headnote concept (one or more registry keys) to keyword substrings that, if
# present in the courtbook type_name, mean we already have an equivalent.
HEADNOTE_MATCHERS: list[tuple[str, list[str]]] = [
    ("regular_bail_* / anticipatory_bail / trial_bail_437 / default_bail", ["bail"]),
    ("writ_petition / habeas_corpus_226", ["writ$", "habeas", "mandamus", "certiorari"]),
    ("quashing_petition", ["quashing", "quash"]),
    ("appeal_conviction", ["appeal"]),
    ("revision_petition / criminal_revision_sessions", ["revision"]),
    ("discharge_application / discharge_239", ["discharge"]),
    ("maintenance", ["maintenance"]),
    ("dv_act_12", ["domestic violence"]),
    ("hma_13_divorce / hma_9_restitution", ["divorce", "restitution", "conjugal",
                                            "judicial separation"]),
    ("ni_act_138 / ni_138b_dismiss", ["cheque", "negotiable instrument", "dishonour"]),
    ("production_documents_91_94 / production_warrant_91", ["production of document"]),
    ("examination_311", ["examination of witness"]),
    ("suspension_of_sentence", ["suspension of sentence"]),
    ("stay_petition_hc", ["stay order", "stay petition", "stay application"]),
    ("slp_criminal", ["special leave", "slp"]),
    ("transfer_petition_cri", ["transfer petition"]),
    ("review_petition_sc", ["review petition"]),
    ("compromise_320", ["compromise"]),
    ("vakalatnama", ["vakalatnama"]),
    ("general_affidavit / affidavit", ["affidavit"]),
    ("legal_notice", ["legal notice"]),
    ("adjournment", ["adjournment"]),
    ("delay_condonation", ["condonation"]),
    ("mention_memo", ["mention memo"]),
    ("reply_to_bail_* / reply_application / reply_notice", ["reply to", "reply notice",
                                                            "counter affidavit"]),
]


def load_headnote_baseline() -> dict:
    """Import the live registries (side-effect-free) — authoritative current coverage."""
    from headnote.drafter import compose_templates as ct
    from headnote.drafter import stories as st
    templates = {k: v.get("name_en", k) for k, v in ct.TEMPLATES.items()}
    story_keys = list(st.STORIES.keys())
    return {"templates": templates, "stories": story_keys}


def _has(keywords: list[str], text: str) -> bool:
    """Match a keyword as a word-prefix, so 'agreement' hits 'agreements' and
    'apprentice' hits 'apprenticeship'. A trailing '$' forces a whole-word match
    instead — used for false-friends like 'writ' (must NOT fire inside 'written')."""
    for kw in keywords:
        pat = rf"\b{kw[:-1]}\b" if kw.endswith("$") else rf"\b{kw}"
        if re.search(pat, text):
            return True
    return False


def bucketize(text: str) -> str:
    for bucket, kws in BUCKET_RULES:
        if _has(kws, text):
            return bucket
    return "misc"


def headnote_match(type_name_lc: str) -> str:
    for label, kws in HEADNOTE_MATCHERS:
        if _has(kws, type_name_lc):
            return label
    return ""


def classify(rec: dict) -> dict:
    name_lc = rec["type_name"].lower()
    # Bucket on the clean type_name ONLY — not the body prose (name-drops sections
    # incidentally) and not the slug (courtbook slugs have concatenation artifacts
    # like "familyforeign-colloboration-drafts").
    bucket = bucketize(name_lc)
    match = headnote_match(name_lc)
    return {
        "lang": rec["lang"],
        "type_name": rec["type_name"],
        "bucket": bucket,
        "wedge": WEDGE.get(bucket, "MEDIUM"),
        "status": "HAVE" if match else "GAP",
        "headnote_match": match,
        "n_sections": len(rec.get("sections", [])),
        "sections": "; ".join(rec.get("sections", [])[:10]),
        "word_count": rec.get("word_count", 0),
        "url": rec["url"],
    }


# ---------------------------------------------------------------------------
def write_xlsx(rows: list[dict], path: Path) -> None:
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    WEDGE_FILL = {"HIGH": "C6EFCE", "MEDIUM": "FFEB9C", "LOW": "F2F2F2"}
    STATUS_FILL = {"HAVE": "C6EFCE", "GAP": "FFC7CE"}
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="404040")

    wb = openpyxl.Workbook()

    # --- Catalog sheet -----------------------------------------------------
    ws = wb.active
    ws.title = "Catalog"
    cols = ["lang", "type_name", "bucket", "wedge", "status", "headnote_match",
            "n_sections", "sections", "word_count", "url"]
    ws.append([c.replace("_", " ").title() for c in cols])
    for cell in ws[1]:
        cell.font = header_font
        cell.fill = header_fill
    # litigation-wedge gaps float to the top, then by bucket/type.
    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    rows_sorted = sorted(
        rows, key=lambda r: (r["status"] != "GAP", order[r["wedge"]], r["bucket"],
                             r["type_name"].lower()))
    for r in rows_sorted:
        ws.append([r[c] for c in cols])
        wedge_cell = ws.cell(row=ws.max_row, column=cols.index("wedge") + 1)
        wedge_cell.fill = PatternFill("solid", fgColor=WEDGE_FILL[r["wedge"]])
        status_cell = ws.cell(row=ws.max_row, column=cols.index("status") + 1)
        status_cell.fill = PatternFill("solid", fgColor=STATUS_FILL[r["status"]])
    widths = [9, 34, 22, 8, 8, 40, 9, 46, 9, 60]
    for i, w in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(cols))}{ws.max_row}"
    for row in ws.iter_rows(min_row=2):
        row[cols.index("sections")].alignment = Alignment(wrap_text=True, vertical="top")

    # --- Summary sheet -----------------------------------------------------
    ws2 = wb.create_sheet("Summary")
    ws2.append(["Bucket", "Wedge", "Total", "Have", "Gap"])
    for cell in ws2[1]:
        cell.font = header_font
        cell.fill = header_fill
    buckets = sorted({r["bucket"] for r in rows},
                     key=lambda b: (order[WEDGE.get(b, "MEDIUM")], b))
    for b in buckets:
        sub = [r for r in rows if r["bucket"] == b]
        have = sum(1 for r in sub if r["status"] == "HAVE")
        ws2.append([b, WEDGE.get(b, "MEDIUM"), len(sub), have, len(sub) - have])
        ws2.cell(row=ws2.max_row, column=2).fill = PatternFill(
            "solid", fgColor=WEDGE_FILL[WEDGE.get(b, "MEDIUM")])
    ws2.append(["TOTAL", "", len(rows), sum(1 for r in rows if r["status"] == "HAVE"),
                sum(1 for r in rows if r["status"] == "GAP")])
    for cell in ws2[ws2.max_row]:
        cell.font = Font(bold=True)
    for i, w in enumerate([24, 9, 8, 8, 8], 1):
        ws2.column_dimensions[get_column_letter(i)].width = w
    ws2.freeze_panes = "A2"

    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)


def write_markdown(rows: list[dict], hi_count: int, baseline: dict, path: Path) -> None:
    en = rows  # already English-only
    en_have = sum(1 for r in en if r["status"] == "HAVE")
    high = [r for r in en if r["wedge"] == "HIGH"]
    high_gaps = [r for r in high if r["status"] == "GAP"]

    order = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    buckets = sorted({r["bucket"] for r in en},
                     key=lambda b: (order[WEDGE.get(b, "MEDIUM")], b))

    L = []
    L.append("# Courtbook.in/draft — coverage & roadmap (research only)")
    L.append("")
    L.append(f"_Generated by `scripts/courtbook_coverage.py` from "
             f"`courtbook_corpus.jsonl` ({len(en) + hi_count} templates: {len(en)} EN + "
             f"{hi_count} HI; English classified below). Third-party content scraped for "
             f"competitive analysis — never rehosted, served, or committed._")
    L.append("")
    L.append("## Headline")
    L.append("")
    L.append(f"- Courtbook publishes **{len(en)} English** + **{hi_count} Hindi** free "
             f"template pages — a flat, SEO-driven catalog (median ~1,030 words/page, "
             f"each page bundling an explainer + multiple sample formats).")
    L.append(f"- Headnote already ships **{len(baseline['templates'])} native template "
             f"types** + **{len(baseline['stories'])} conversational stories**.")
    L.append(f"- Against that baseline, the English catalog is **{en_have} HAVE / "
             f"{len(en) - en_have} GAP**.")
    L.append(f"- Inside Headnote's litigation wedge (criminal / family / writs / consumer "
             f"/ motor): **{len(high)} courtbook types, {len(high_gaps)} of them gaps.**")
    L.append(f"- Caveat: each courtbook entry is a broad *category* page (e.g. \"Criminal "
             f"Law\", \"Civil Pleadings\") bundling many sample formats — so these counts "
             f"measure breadth of practice areas, not one-to-one documents.")
    L.append("")
    L.append("## Coverage by practice-area bucket (English)")
    L.append("")
    L.append("| Bucket | Wedge | Total | Have | Gap |")
    L.append("|---|---|--:|--:|--:|")
    for b in buckets:
        sub = [r for r in en if r["bucket"] == b]
        have = sum(1 for r in sub if r["status"] == "HAVE")
        L.append(f"| {b} | {WEDGE.get(b,'MEDIUM')} | {len(sub)} | {have} | {len(sub)-have} |")
    L.append("")
    L.append("## Recommended next native templates (HIGH-wedge gaps)")
    L.append("")
    L.append("Courtbook types inside Headnote's litigation wedge that we don't yet cover. "
             "Build these **natively from real filed sources** (Vishnu ji's filed documents "
             "in Kruti Dev) — *not* from courtbook's text. Grouped by area:")
    L.append("")
    if high_gaps:
        by_bucket: dict[str, list[str]] = {}
        for r in high_gaps:
            by_bucket.setdefault(r["bucket"], []).append(r["type_name"])
        for b in sorted(by_bucket):
            names = sorted(set(by_bucket[b]))
            L.append(f"- **{b}** ({len(names)}): " + ", ".join(names))
    else:
        L.append("_None — Headnote already covers every HIGH-wedge type courtbook lists._")
    L.append("")
    L.append("## Lower-priority gaps (outside the litigation wedge)")
    L.append("")
    low = sorted({r["bucket"] for r in en if r["wedge"] == "LOW"})
    low_counts = {b: sum(1 for r in en if r["bucket"] == b and r["status"] == "GAP")
                  for b in low}
    L.append("Large in courtbook but transactional / non-litigation, so off-wedge for now: "
             + ", ".join(f"**{b}** ({n} gaps)" for b, n in low_counts.items() if n) + ".")
    L.append("")
    L.append("## Strategic note")
    L.append("")
    L.append("Courtbook is a **free, SEO-driven generic form bank** (4 languages, flat "
             "catalog, news section for traffic). Headnote's moat is the opposite: real "
             "*filed* MP-court documents rendered byte-faithful in **Kruti Dev**, auto-filled "
             "from an OCR'd FIR, behind a leak-gate. Re-hosting courtbook's generic text "
             "would (a) not fit that pipeline, (b) erase the differentiation a lawyer pays "
             "for, and (c) carry copyright risk. Use this map only to **prioritise which "
             "litigation types to build natively next** — the HIGH-wedge gaps above are the "
             "shortlist.")
    L.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(L), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(CORPUS_DEFAULT))
    ap.add_argument("--xlsx", default=str(XLSX_DEFAULT))
    ap.add_argument("--md", default=str(MD_DEFAULT))
    args = ap.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        raise SystemExit(f"Corpus not found: {corpus_path}. Run scrape_courtbook.py first.")

    records = [json.loads(line) for line in corpus_path.open(encoding="utf-8")]
    baseline = load_headnote_baseline()
    # The keyword rules are English; Devanagari Hindi titles can't match them, so we
    # classify the English catalog and report Hindi only as a count.
    en_records = [r for r in records if r["lang"] == "english"]
    hi_count = sum(1 for r in records if r["lang"] == "hindi")
    rows = [classify(r) for r in en_records]

    write_xlsx(rows, Path(args.xlsx))
    write_markdown(rows, hi_count, baseline, Path(args.md))

    gaps = sum(1 for r in rows if r["status"] == "GAP")
    high_gaps = sum(1 for r in rows if r["wedge"] == "HIGH" and r["status"] == "GAP")
    print(f"Classified {len(rows)} English courtbook templates "
          f"(+{hi_count} Hindi listed) against {len(baseline['templates'])} Headnote types.")
    print(f"  English: {len(rows)-gaps} HAVE / {gaps} GAP   (HIGH-wedge gaps: {high_gaps})")
    print(f"  -> {args.xlsx}")
    print(f"  -> {args.md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
