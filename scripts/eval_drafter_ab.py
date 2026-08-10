"""Drafter A/B eval harness — DeepSeek V3 vs R1 on a fixed brief panel.

Purpose (roadmap §5c + seeds §5a):
  Prove the V3→R1 quality lift on real output, repeatably, with deterministic
  scorers that ALSO become the self-check layer. For each brief we generate the
  draft twice — once on V3 (claude-haiku-4-5 → deepseek-chat) and once on R1
  (claude-sonnet-4-6 → deepseek-reasoner) — score both on the "small things that
  kill a draft", and print a side-by-side table. Full drafts are written to
  ./eval_out/ so you can eyeball register/idiom too.

Run (where DEEPSEEK_API_KEY is set — e.g. locally with .env, or on the box):
    export DEEPSEEK_API_KEY=sk-...        # R1/V3 both need this
    export GROQ_API_KEY=gsk-...           # optional; only used if DeepSeek fails
    python3 scripts/eval_drafter_ab.py

Notes:
  • R1 is slow (~60–180s/draft); a full panel on both models takes a few minutes.
  • This calls the REAL drafting engine (author_document / mirror_document), so it
    exercises the same guards (citation/section/grounding) the product uses.
"""
import os
import re
import sys
import time
import html as _html

REPO = "/Users/ayushshivhare/Downloads/Legify-0bb187ba264e218517be944dbf64c433be6ae19d"
sys.path.insert(0, REPO)

from headnote import config
from headnote.drafter.author import author_document, mirror_document
from headnote.llm.client import estimate_cost_usd

# The two DeepSeek tiers, addressed via the Claude alias the router maps from.
MODELS = {
    "V3": "claude-haiku-4-5",    # deepseek-chat  — cheap, no reasoning (today's default was this)
    "R1": "claude-sonnet-4-6",   # deepseek-reasoner — chain-of-thought (the new default)
}

OUT_DIR = os.path.join(os.getcwd(), "eval_out")


# ---------------------------------------------------------------------------
# The brief panel. Keep it small, real, and matter-diverse. Grow over time —
# each entry is a gold test case for every future prompt/model change.
# `expect_sections` = tokens that MUST appear (correct statute for the matter).
# For mirror briefs, `ref_must_not_leak` = the reference's own facts that must
# NEVER survive into the new draft (the confidentiality/fabrication guard).
# ---------------------------------------------------------------------------
PANEL = [
    {
        "id": "bail_cheating",
        "kind": "author", "doc_type": "bail", "lang": "hi",
        "matter": (
            "नियमित जमानत। अभियुक्त राकेश, 45 दिन से न्यायिक अभिरक्षा में, धारा 420/406 आईपीसी, "
            "आरोप पत्र न्यायालय में प्रस्तुत हो चुका है, कोई पूर्व आपराधिक रिकॉर्ड नहीं।"
        ),
        "expect_sections": ["483"],   # bail = BNSS 483 (439 CrPC)
    },
    {
        "id": "maintenance_wife",
        "kind": "author", "doc_type": "maintenance", "lang": "hi",
        "matter": (
            "पत्नी की ओर से भरण-पोषण आवेदन। पति सरकारी नौकरी में, आवेदिका के पास आय का कोई साधन नहीं, "
            "एक नाबालिग पुत्र आवेदिका के साथ रहता है।"
        ),
        "expect_sections": ["144"],   # maintenance = BNSS 144 (125 CrPC)
    },
    {
        "id": "recovery_suit",
        "kind": "author", "doc_type": "recovery_suit", "lang": "hi",
        "matter": (
            "वसूली का वाद। वादी ने प्रतिवादी को माल उधार दिया, राशि ₹7,20,000 बकाया, चेक अनादरित, "
            "विधिक सूचना के बाद भी भुगतान नहीं।"
        ),
        "expect_sections": [],        # civil — no BNSS; scorer skips section check
    },
    {
        "id": "mirror_recovery",
        "kind": "mirror", "doc_type": "recovery_suit", "lang": "hi",
        # A short, clearly-synthetic reference (ANOTHER client's case). We test that
        # its facts do NOT leak and the new matter's facts DO land.
        "reference_text": (
            "न्यायालय माननीय व्यवहार न्यायाधीश वर्ग-1, इन्दौर (मध्यप्रदेश)\n"
            "व्यवहार वाद क्रमांक ____/2025\n"
            "मेसर्स शर्मा ट्रेडर्स, द्वारा प्रोपराइटर, निवासी इन्दौर ......... वादी\n"
            "बनाम\n"
            "श्री गुप्ता, पुत्र श्री ____, निवासी इन्दौर ......... प्रतिवादी\n"
            "वाद अन्तर्गत आदेश 37 सी.पी.सी.\n"
            "1. यह कि वादी एक पंजीकृत फर्म है।\n"
            "2. यह कि प्रतिवादी ने दिनांक 12.03.2025 को वादी से ₹4,50,000 उधार लिया।\n"
            "3. यह कि प्रतिवादी द्वारा जारी चेक अनादरित हुआ।\n"
            "अतः प्रार्थना है कि ₹4,50,000 ब्याज सहित दिलायी जावे।"
        ),
        "matter": (
            "वसूली का वाद, आदेश 37 सी.पी.सी. वादी मेसर्स वर्मा स्टील। प्रतिवादी अनिल कुमार। "
            "बकाया राशि ₹7,20,000। चेक दिनांक 05.06.2026 को अनादरित हुआ।"
        ),
        "ref_must_not_leak": ["शर्मा", "गुप्ता", "4,50,000", "12.03.2025"],
        "new_must_appear": ["वर्मा", "अनिल", "7,20,000"],
        "expect_sections": [],
    },
]


_TAG = re.compile(r"<[^>]+>")


def _text(html: str) -> str:
    """Rendered HTML → plain text for scoring."""
    return _html.unescape(_TAG.sub(" ", html or ""))


def score(brief: dict, result: dict) -> dict:
    """Deterministic scorers — the 'small things that kill a draft'. This is the
    seed of the self-check layer: each check is a would-be pre-delivery gate."""
    txt = _text(result.get("html", ""))
    checks: dict = {}

    # grounds present (each numbered para opens with यह कि / यहकि)
    grounds = len(re.findall(r"यह\s?कि", txt))
    checks["grounds"] = grounds
    checks["has_grounds"] = grounds >= 3

    # the mandatory oral-arguments closer (house style)
    checks["closer"] = ("अन्य तर्क" in txt and "बहस" in txt)

    # prayer present
    checks["prayer"] = ("प्रार्थना" in txt)

    # correct statute for the matter (skip for civil / no expectation)
    exp = brief.get("expect_sections") or []
    checks["section_ok"] = (all(s in txt for s in exp) if exp else None)

    # zero-fabrication signals surfaced by the engine's own guards
    checks["warnings"] = len(result.get("warnings") or [])
    checks["ungrounded"] = len(result.get("ungrounded") or [])
    checks["body_citations"] = len(_CITE.findall(txt))   # should be 0 unless whitelisted

    # mirror-only: reference facts must NOT leak; new facts MUST appear
    if brief["kind"] == "mirror":
        leaked = [f for f in brief.get("ref_must_not_leak", []) if f in txt]
        missing_new = [f for f in brief.get("new_must_appear", []) if f not in txt]
        checks["ref_leak"] = leaked            # [] is good
        checks["missing_new_facts"] = missing_new  # [] is good
    return checks


_CITE = re.compile(
    r"\(?\d{4}\)?\s*\d*\s*(?:SCC|INSC|AIR|एस\.?सी\.?सी\.?)", re.IGNORECASE
)


def run_one(brief: dict, alias: str) -> dict:
    config.DRAFTER_AUTHOR_MODEL = alias   # author.py reads this at call time
    t0 = time.perf_counter()
    if brief["kind"] == "mirror":
        res = mirror_document(brief["matter"], brief["reference_text"],
                              brief["doc_type"], brief.get("lang", "hi"))
    else:
        res = author_document(brief["matter"], brief["doc_type"], brief.get("lang", "hi"))
    dt = time.perf_counter() - t0
    meta = res.get("meta") or {}
    usd = estimate_cost_usd(meta) if meta else 0.0
    return {"res": res, "secs": dt, "inr": usd * config.USD_TO_INR,
            "model": meta.get("model", "?"),
            "out_tok": meta.get("output_tokens", 0)}


def main() -> None:
    # The A/B compares two DeepSeek TIERS (V3 vs R1). It ONLY makes sense with a
    # real DeepSeek key — without one, both aliases fall through to the SAME Groq
    # model and every row looks identical (a meaningless "tie"). Require it.
    if not os.environ.get("DEEPSEEK_API_KEY", "").strip():
        print("\n  ⚠  DEEPSEEK_API_KEY is not set — the V3-vs-R1 A/B needs it.")
        print("     Without it both tiers fall back to the same Groq model and the")
        print("     comparison is meaningless. Run where your DeepSeek key is set:\n")
        print("       export DEEPSEEK_API_KEY=sk-...")
        print("       python3 scripts/eval_drafter_ab.py\n")
        sys.exit(1)

    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"\nDrafter A/B — V3 vs R1 · {len(PANEL)} briefs · full drafts → {OUT_DIR}\n")

    for brief in PANEL:
        print("=" * 78)
        print(f"[{brief['id']}]  {brief['kind']}/{brief['doc_type']}  ({brief.get('lang','hi')})")
        row = {}
        for tag, alias in MODELS.items():
            try:
                out = run_one(brief, alias)
                sc = score(brief, out["res"])
                row[tag] = {**out, "score": sc}
                path = os.path.join(OUT_DIR, f"{brief['id']}__{tag}.html")
                with open(path, "w", encoding="utf-8") as f:
                    f.write(out["res"].get("html", ""))
            except Exception as e:
                row[tag] = {"error": f"{type(e).__name__}: {e}"}

        # side-by-side
        keys = ["grounds", "has_grounds", "closer", "prayer", "section_ok",
                "body_citations", "warnings", "ungrounded"]
        if brief["kind"] == "mirror":
            keys += ["ref_leak", "missing_new_facts"]
        print(f"    {'check':<20} {'V3':<26} {'R1':<26}")
        for k in keys:
            v3 = row.get("V3", {}).get("score", {}).get(k, "—") if "error" not in row.get("V3", {}) else "ERR"
            r1 = row.get("R1", {}).get("score", {}).get(k, "—") if "error" not in row.get("R1", {}) else "ERR"
            print(f"    {k:<20} {str(v3):<26} {str(r1):<26}")
        for tag in ("V3", "R1"):
            d = row.get(tag, {})
            if "error" in d:
                print(f"    {tag}: ERROR — {d['error']}")
            else:
                print(f"    {tag}: {d['secs']:.0f}s · {d['out_tok']} out-tok · ~₹{d['inr']:.2f} · {d['model']}")
        print()

    print("=" * 78)
    print(f"Done. Open the HTML pairs in {OUT_DIR}/ to compare register & idiom by eye.")
    print("Read the tables above for the mechanical 'small things' (the self-check gates).\n")


if __name__ == "__main__":
    main()
