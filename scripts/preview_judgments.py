#!/usr/bin/env python3
"""Tiny standalone preview server for the official SC judgment corpus.

Mounts ONLY the judgment + case-viewer routers, so you can see the real
in-app judgment viewer (with the official PDF embedded) without booting the
full app (no Supabase / payments / jwt needed). Great for a quick demo.

    python scripts/preview_judgments.py            # serves on :8077
    python scripts/preview_judgments.py --port 9000

Then open in a browser:
    http://127.0.0.1:8077/case/sc:2024_8_1047_1060      (full viewer)
    http://127.0.0.1:8077/api/judgment/pdf/sc:2024_8_1047_1060   (raw PDF)
    http://127.0.0.1:8077/api/judgment/search?q=murder          (search JSON)
    http://127.0.0.1:8077/                                       (index w/ links)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import FastAPI                                  # noqa: E402
from fastapi.responses import HTMLResponse                  # noqa: E402

from headnote.api.judgments import router as judgments_router      # noqa: E402
from headnote.api.case_viewer import router as case_viewer_router  # noqa: E402
from headnote.judgments import opendata                     # noqa: E402

app = FastAPI(title="Headnote — judgment corpus preview")
app.include_router(judgments_router)
app.include_router(case_viewer_router)


@app.get("/", response_class=HTMLResponse)
def index():
    stats = opendata.corpus_stats()
    # A few recognisable criminal matters to click into.
    samples, seen = [], set()
    for term in ["MURDER", "BAIL", "POCSO", "STATE OF"]:
        for j in opendata.search(term, limit=6):
            if j.year < 2024 or j.doc_id in seen:
                continue
            seen.add(j.doc_id)
            samples.append(j)
            if len(samples) >= 8:
                break
        if len(samples) >= 8:
            break
    rows = "".join(
        f'<li><a href="/case/{j.doc_id}">{(j.title or j.doc_id)[:80]}</a>'
        f'<br><small>{j.best_citation or ""} · {j.decision_date or ""} · '
        f'{j.judge or ""}</small></li>'
        for j in samples
    )
    return f"""
    <html><head><meta charset="utf-8"><title>Headnote judgment preview</title>
    <style>body{{font:16px/1.5 -apple-system,system-ui,sans-serif;max-width:780px;
    margin:40px auto;padding:0 16px;color:#1d1d1f}}
    h1{{font-size:22px}} .stat{{background:#f5f5f7;padding:12px 16px;border-radius:8px;
    margin:16px 0;font-size:14px}} li{{margin:14px 0}} small{{color:#666}}
    a{{color:#0066cc;text-decoration:none}} a:hover{{text-decoration:underline}}
    input{{padding:8px 12px;width:60%;border:1px solid #ccc;border-radius:6px}}</style>
    </head><body>
    <h1>Headnote — official Supreme Court judgment corpus</h1>
    <div class="stat"><b>{stats['judgments']:,}</b> reported judgments
    ({stats['year_min']}–{stats['year_max']}) ·
    <b>{stats['years_indexed']}</b> year(s) PDF-indexed ·
    <b>{stats['offsets']:,}</b> PDFs servable right now<br>
    <small>Source: Supreme Court of India / AWS Open Data, CC-BY-4.0 ·
    tap a case → real official PDF</small></div>
    <form action="/case-search" method="get">
      <input name="q" placeholder="Search parties or neutral citation, e.g. 'murder' or '2024 INSC 613'">
      <button>Search</button>
    </form>
    <h3>Sample criminal matters (click to open the viewer):</h3>
    <ul>{rows}</ul>
    </body></html>"""


@app.get("/case-search", response_class=HTMLResponse)
def case_search(q: str = ""):
    hits = opendata.search(q, limit=30) if q else []
    rows = "".join(
        f'<li><a href="/case/{j.doc_id}">{(j.title or j.doc_id)[:90]}</a>'
        f'<br><small>{j.best_citation or ""} · {j.decision_date or ""}</small></li>'
        for j in hits
    )
    return (f'<html><body style="font:16px/1.5 -apple-system,sans-serif;'
            f'max-width:780px;margin:40px auto"><a href="/">&larr; back</a>'
            f'<h2>{len(hits)} results for "{q}"</h2><ul>{rows}</ul></body></html>')


if __name__ == "__main__":
    import uvicorn
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8077)
    args = ap.parse_args()
    print(f"\n  Preview at  http://127.0.0.1:{args.port}/\n")
    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
