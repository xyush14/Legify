#!/usr/bin/env python3
"""Upload kanoon_cache.sqlite to a private HuggingFace dataset so Railway
can fetch it via /admin/import_corpus_from_url.

Why HuggingFace as a delivery channel? Three reasons:
1. We already use HF for the source corpus, the token is already configured.
2. HF datasets handle multi-GB uploads cleanly (chunked, resumable).
3. The returned URL is a stable HTTPS endpoint Railway can pull from.

USAGE
-----
    export HF_TOKEN=hf_...
    python scripts/upload_corpus_to_hf.py --repo your-hf-username/headnote-corpus

To upload to a new repo (created automatically if it doesn't exist):

    python scripts/upload_corpus_to_hf.py \\
        --repo your-hf-username/headnote-corpus \\
        --private \\
        --create-if-missing

The script prints the download URL on success. Pipe that into the
/admin/import_corpus_from_url endpoint.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--repo",
        required=True,
        help="HF repo id in form 'username/repo-name'",
    )
    parser.add_argument(
        "--db",
        default=str(_REPO_ROOT / "kanoon_cache.sqlite"),
        help="Path to the SQLite file to upload (default: ./kanoon_cache.sqlite)",
    )
    parser.add_argument(
        "--filename",
        default="kanoon_cache.sqlite",
        help="Filename inside the HF repo (default: kanoon_cache.sqlite)",
    )
    parser.add_argument(
        "--private",
        action="store_true",
        help="If creating the repo, make it private (recommended)",
    )
    parser.add_argument(
        "--create-if-missing",
        action="store_true",
        help="Create the HF dataset repo if it doesn't exist",
    )
    parser.add_argument(
        "--token",
        default=os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN"),
        help="HF token (defaults to $HF_TOKEN). Must have write access.",
    )
    args = parser.parse_args()

    if not args.token:
        print("ERROR: HF token missing. Set $HF_TOKEN or pass --token.")
        return 1

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"ERROR: SQLite file not found at {db_path}")
        return 1

    size_mb = db_path.stat().st_size / (1024 * 1024)
    print(f"Uploading {db_path} ({size_mb:.1f} MB) to {args.repo} ...")

    try:
        from huggingface_hub import HfApi
    except ImportError:
        print("ERROR: huggingface_hub not installed. Run: pip install huggingface_hub")
        return 1

    api = HfApi(token=args.token)

    if args.create_if_missing:
        try:
            api.create_repo(
                repo_id=args.repo,
                repo_type="dataset",
                private=args.private,
                exist_ok=True,
            )
            print(f"  Repo {args.repo} ready (private={args.private}).")
        except Exception as e:
            print(f"WARN: create_repo failed ({e}); attempting upload anyway.")

    print("  Uploading file (this can take a few minutes for 1+ GB)...")
    try:
        api.upload_file(
            path_or_fileobj=str(db_path),
            path_in_repo=args.filename,
            repo_id=args.repo,
            repo_type="dataset",
        )
    except Exception as e:
        print(f"ERROR: upload failed: {e}")
        return 1

    # Public file URL pattern HF exposes for non-LFS files. For files >
    # ~10 MB HF auto-uses LFS; the same /resolve/main/ URL pattern still
    # works (it redirects to the LFS object storage).
    url = f"https://huggingface.co/datasets/{args.repo}/resolve/main/{args.filename}"

    print()
    print("=" * 60)
    print("  UPLOAD COMPLETE")
    print("=" * 60)
    print(f"  Repo:  {args.repo}")
    print(f"  File:  {args.filename}")
    print(f"  Size:  {size_mb:.1f} MB")
    print()
    print(f"  Download URL:")
    print(f"  {url}")
    print()
    if args.private:
        print("  Note: dataset is PRIVATE. The download URL requires an")
        print("  Authorization: Bearer <HF_TOKEN> header. Pass the same HF")
        print("  token to /admin/import_corpus_from_url via a future")
        print("  ?auth_token= param.")
    else:
        print("  Public dataset — any HTTPS client can download.")
    print()
    print("  Next: hit /admin/import_corpus_from_url with this URL.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
