#!/usr/bin/env python3
"""
Walk the kanoon cache + HF corpus, embed any paragraphs not yet indexed.

Idempotent — safe to run repeatedly. Cost: ₹0 (no IK calls, all local).

What it does
------------
1. **IK cache backfill** — scans ik_doc table, parses each judgment via the
   IK paragraph parser, embeds paragraphs ≥ 40 chars. Same behaviour as
   the original script.

2. **HF corpus backfill** — scans hf_judgments table (CJPE + SUMM + BAIL),
   splits each judgment's plaintext on blank lines, embeds the most
   substantive paragraphs (≥ 80 chars, capped per judgment to keep total
   runtime sane).

Runtime
-------
~41K HF judgments × ~10 paragraphs each × 15 ms per paragraph on CPU
= ~100 minutes single-threaded. Re-running is fast because already-embedded
(case_id, para_id) pairs are skipped.

Run
---
    .venv/bin/python scripts/backfill_embeddings.py              # IK + HF
    .venv/bin/python scripts/backfill_embeddings.py --skip-ik    # HF only
    .venv/bin/python scripts/backfill_embeddings.py --skip-hf    # IK only
    .venv/bin/python scripts/backfill_embeddings.py --limit 100  # first 100 of each

Production note
---------------
On Railway, run this once after `harvest_hf_corpus.py` finishes. The script
is idempotent so re-running after later imports only embeds the new rows.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

# Ensure repo root on sys.path so `from headnote.config import ...` works
# regardless of where the script is invoked from.
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from headnote.retrieval.embeddings import EmbeddingIndex
from headnote.kanoon.parser import parse_judgment
from headnote.config import KANOON_CACHE_PATH


# HF-specific tuning. Each HF judgment is plaintext split on \n\n; we embed
# only the longest/most substantive chunks to keep total backfill time bounded.
HF_MIN_PARA_CHARS = 80           # paragraphs shorter than this carry no signal
HF_MAX_PARA_CHARS = 4000         # cap pathologically-long blobs
HF_MAX_PARAS_PER_DOC = 12        # most legal content is in opening + closing
HF_TOP_K_BY_LENGTH = 30          # pre-filter candidates by length before sort


def _backfill_ik(idx: EmbeddingIndex, cache_path: Path, limit: int | None) -> int:
    """Embed paragraphs from cached IK documents (ik_doc table)."""
    conn = sqlite3.connect(cache_path)
    try:
        rows = conn.execute("SELECT tid, response FROM ik_doc").fetchall()
    except sqlite3.OperationalError as e:
        print(f"[IK] table missing or unreadable ({e}); skipping IK backfill")
        return 0
    finally:
        conn.close()

    if limit:
        rows = rows[:limit]
    print(f"[IK] scanning {len(rows)} cached docs")

    total_new = 0
    for i, (tid, response_text) in enumerate(rows, 1):
        try:
            raw = json.loads(response_text)
            parsed = parse_judgment(
                raw.get("doc", ""),
                tid=tid,
                title_hint=raw.get("title", ""),
                court_hint=raw.get("docsource", ""),
                publishdate_hint=raw.get("publishdate", ""),
            )
        except Exception as e:
            print(f"  [IK {i}/{len(rows)}] tid={tid}  parse failed: {e}")
            continue

        if not parsed.paragraphs:
            continue

        case_id = f"ik:{tid}"
        rows_for_embed = [
            (case_id, p.id, p.num, p.structure, p.text)
            for p in parsed.paragraphs
            if len(p.text) >= 40
        ]
        if not rows_for_embed:
            continue

        t0 = time.time()
        n_new = idx.upsert_paragraphs(rows_for_embed)
        elapsed = time.time() - t0
        total_new += n_new
        if n_new > 0:
            title_short = (parsed.title or "")[:48]
            print(f"  [IK {i}/{len(rows)}] {title_short:48s}  +{n_new:>3} ({elapsed:.1f}s)")

    return total_new


def _select_hf_paragraphs(text: str) -> list[tuple[int, str]]:
    """Pick the top paragraphs from an HF judgment's plaintext.

    HF rows are flat prose with no IK-style paragraph IDs. We split on blank
    lines, filter trivial/excessive lengths, and keep the top-K longest
    paragraphs (legal substance correlates with paragraph length once you've
    filtered out the boilerplate at the top/bottom).
    """
    if not text:
        return []
    chunks = [(i, p.strip()) for i, p in enumerate(text.split("\n\n"))]
    candidates = [
        (i, p) for (i, p) in chunks
        if HF_MIN_PARA_CHARS <= len(p) <= HF_MAX_PARA_CHARS
    ]
    if not candidates:
        return []
    # Sort by length DESC, take top K_BY_LENGTH, then resort to original order
    # so para_num reflects document position (better for downstream display).
    candidates.sort(key=lambda kv: -len(kv[1]))
    top = candidates[:HF_TOP_K_BY_LENGTH]
    # Now keep only the first MAX_PARAS_PER_DOC of those, restored to doc order
    top.sort(key=lambda kv: kv[0])
    return top[:HF_MAX_PARAS_PER_DOC]


def _backfill_hf(idx: EmbeddingIndex, cache_path: Path, limit: int | None) -> int:
    """Embed paragraphs from HF IL-TUR judgments (hf_judgments table)."""
    conn = sqlite3.connect(cache_path)
    try:
        # Only scan doc_ids NOT already in paragraph_embeddings for our model.
        # Using a sub-query keeps the working set small even on big tables.
        from headnote.retrieval.embeddings import EMBED_MODEL_NAME
        already = set(r[0] for r in conn.execute(
            "SELECT DISTINCT case_id FROM paragraph_embeddings WHERE model_name=?",
            (EMBED_MODEL_NAME,),
        ).fetchall())
        rows = conn.execute(
            "SELECT doc_id, title, text FROM hf_judgments"
        ).fetchall()
    except sqlite3.OperationalError as e:
        print(f"[HF] table missing or unreadable ({e}); skipping HF backfill")
        return 0
    finally:
        conn.close()

    # Skip rows whose doc_id already has embeddings (idempotency)
    pending = [(d, t, x) for (d, t, x) in rows if d not in already]
    if limit:
        pending = pending[:limit]
    print(f"[HF] total rows={len(rows)}, already-embedded={len(already)}, to-embed={len(pending)}")

    total_new = 0
    t_start = time.time()
    for i, (doc_id, title, text) in enumerate(pending, 1):
        paras = _select_hf_paragraphs(text or "")
        if not paras:
            continue

        rows_for_embed = [
            (doc_id, f"p_{idx_in_doc}", idx_in_doc + 1, "other", p)
            for idx_in_doc, p in paras
        ]
        try:
            t0 = time.time()
            n_new = idx.upsert_paragraphs(rows_for_embed)
            elapsed = time.time() - t0
            total_new += n_new
            if i % 100 == 0 or n_new > 0:
                title_short = (title or doc_id)[:48]
                eta_min = ((len(pending) - i) * (time.time() - t_start) / max(i, 1)) / 60
                print(f"  [HF {i}/{len(pending)}] {title_short:48s}  +{n_new:>3} ({elapsed:.1f}s) eta={eta_min:.0f}m")
        except Exception as e:
            print(f"  [HF {i}/{len(pending)}] {doc_id}: embed failed: {e}")
            continue

    return total_new


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(KANOON_CACHE_PATH),
                        help=f"SQLite cache path (default: {KANOON_CACHE_PATH})")
    parser.add_argument("--skip-ik", action="store_true",
                        help="Skip the IK ik_doc backfill (HF only)")
    parser.add_argument("--skip-hf", action="store_true",
                        help="Skip the HF hf_judgments backfill (IK only)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Cap rows scanned in each phase (for testing)")
    args = parser.parse_args()

    cache_path = Path(args.db)
    if not cache_path.exists():
        print(f"No cache at {cache_path}; nothing to backfill.")
        return 0

    idx = EmbeddingIndex(cache_path)
    before = idx.stats()
    print(f"Before: {before['paragraph_count']} paragraphs from {before['case_count']} cases indexed")
    print()

    total_new = 0
    if not args.skip_ik:
        total_new += _backfill_ik(idx, cache_path, args.limit)
        print()
    if not args.skip_hf:
        total_new += _backfill_hf(idx, cache_path, args.limit)
        print()

    after = idx.stats()
    print(f"After:  {after['paragraph_count']} paragraphs from {after['case_count']} cases indexed")
    print(f"New this run: {total_new}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
