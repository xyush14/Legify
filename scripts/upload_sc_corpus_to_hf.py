#!/usr/bin/env python3
"""Upload the pre-built FULL Supreme-Court corpus to a PUBLIC Hugging Face
dataset repo, then print the ``JUDGMENTS_FULL_URL`` to set on Railway.

Why
---
``judgments_full.sqlite.gz`` (≈598 MB) carries metadata + tar offsets +
**extracted judgment text** + a deduped FTS5 index for ~28.6k Supreme Court
judgments. Setting ``JUDGMENTS_FULL_URL`` to its public URL makes the Railway
boot bootstrap (``_maybe_bootstrap_judgments_on_boot`` in
``headnote/api/app.py``) stream it, gunzip on the fly, validate the FTS index,
and atomically swap it onto the ``/data`` volume — which lights up official
Supreme-Court full-text fact-pattern discovery (retrieval **Stage 2.6,
``_sc_fulltext_cases``**). Until then that stage is a no-op and only metadata
cross-resolution / official-PDF tap works.

The corpus is official AWS Open Data (CC-BY-4.0), so a PUBLIC dataset is fine —
and REQUIRED, because the bootstrap fetches the URL unauthenticated. A private
repo would 401 the download.

Prereqs
-------
    # huggingface_hub is already installed (1.8.0). Get a WRITE token at
    #   https://huggingface.co/settings/tokens   (role: Write)
    export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx

Usage
-----
    python3 scripts/upload_sc_corpus_to_hf.py
    python3 scripts/upload_sc_corpus_to_hf.py --repo myuser/headnote-sc-corpus
    python3 scripts/upload_sc_corpus_to_hf.py --file judgments_full.sqlite.gz

Resumable: HF LFS upload resumes on re-run; re-running just re-points the same
file. Safe to interrupt.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

FILE_DEFAULT = "judgments_full.sqlite.gz"
REPO_NAME_DEFAULT = "headnote-sc-corpus"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("--file", default=FILE_DEFAULT,
                    help=f"artifact to upload (default: {FILE_DEFAULT})")
    ap.add_argument("--repo", default=None,
                    help="full repo id 'user/name' "
                         f"(default: <your-username>/{REPO_NAME_DEFAULT})")
    ap.add_argument("--private", action="store_true",
                    help="create a PRIVATE repo (NOT recommended — the Railway "
                         "bootstrap fetches unauthenticated and will 401)")
    args = ap.parse_args()

    f = Path(args.file).resolve()
    if not f.exists():
        print(f"ERROR: {f} not found.\n"
              f"  Build it first:  python scripts/build_shippable_corpus.py "
              f"--src judgments.sqlite --out judgments_full.sqlite",
              file=sys.stderr)
        return 2
    size_mb = f.stat().st_size / 1e6

    try:
        from huggingface_hub import HfApi
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: huggingface_hub not importable ({e}).\n"
              f"  pip install -U huggingface_hub", file=sys.stderr)
        return 2

    token = (os.environ.get("HF_TOKEN")
             or os.environ.get("HUGGING_FACE_HUB_TOKEN")
             or os.environ.get("HUGGINGFACE_TOKEN"))
    api = HfApi(token=token)
    try:
        me = api.whoami()
        user = me.get("name")
        if not user:
            raise RuntimeError("whoami returned no username")
    except Exception as e:  # noqa: BLE001
        print("ERROR: not authenticated to Hugging Face.\n"
              "  1. Create a WRITE token: https://huggingface.co/settings/tokens\n"
              "  2. export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxxxxxx\n"
              "  3. re-run this script\n"
              f"  (detail: {str(e)[:140]})", file=sys.stderr)
        return 2

    repo_id = args.repo or f"{user}/{REPO_NAME_DEFAULT}"
    private = bool(args.private)

    print(f"User : {user}")
    print(f"Repo : {repo_id}   ({'PRIVATE' if private else 'public'} dataset)")
    print(f"File : {f.name}   ({size_mb:,.0f} MB)")
    if private:
        print("\nWARNING: a PRIVATE dataset cannot be fetched by the unauthenticated\n"
              "         Railway bootstrap — it will fail with 401. Use public.\n")

    print("\nCreating repo (idempotent) …", flush=True)
    api.create_repo(repo_id, repo_type="dataset", private=private, exist_ok=True)

    print("Uploading over LFS — ~598 MB, a few minutes on a normal line …", flush=True)
    api.upload_file(
        path_or_fileobj=str(f),
        path_in_repo=f.name,
        repo_id=repo_id,
        repo_type="dataset",
        commit_message="Add full SC judgments corpus (metadata + text + FTS)",
    )

    # NOTE: the plain resolve URL serves the raw .gz bytes and ENDS IN .gz, which
    # is what the bootstrap checks to decide to gunzip. Do NOT append
    # '?download=true' — that breaks the .endswith('.gz') test.
    url = f"https://huggingface.co/datasets/{repo_id}/resolve/main/{f.name}"
    print("\n" + "=" * 70)
    print("DONE. Set this on Railway → your service → Variables:\n")
    print(f"  JUDGMENTS_FULL_URL={url}\n")
    print("Then make sure a Volume is mounted at /data, and Redeploy/Restart.")
    print("Verify:  curl -s https://headnote.in/api/health | python3 -m json.tool")
    print("         → sc_corpus.texts should climb to ~28,663 and")
    print("           bootstrap.detail → 'full-text live'.")
    print("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
