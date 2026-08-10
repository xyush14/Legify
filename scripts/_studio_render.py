"""Tiny stdin→stdout bridge so the node preview server can drive the canonical
render engine for the Drafting Studio's real-time live-sync (local testing).
On prod the studio calls the FastAPI /api/draft/render instead — same contract.

stdin : {"doc_type": "...", "data": {...}}
stdout: {"ok": true, "html_hi": "...", "html_en": "..."}
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        from headnote.drafter.bundle import module_for, assemble
        req = json.load(sys.stdin)
        mod = module_for(req.get("doc_type", ""))
        out = assemble(mod, req.get("data") or {})
    except Exception as e:  # never crash the dev server
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


main()
