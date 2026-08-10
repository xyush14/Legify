"""stdin→stdout field-schema bridge so the node preview can serve the same
/api/draft/fields/{type} the prod FastAPI serves — lets ONE editor file work
both locally and in production.

stdin : {"doc_type": "...", "court": "...", "bail_type": "..."}
stdout: the type's field_spec (fields + toggles + variants + companions)
"""
import inspect
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        from headnote.drafter.bundle import module_for
        req = json.load(sys.stdin)
        mod = module_for(req.get("doc_type", ""))
        n = len(inspect.signature(mod.field_spec).parameters)
        if n >= 2:
            spec = mod.field_spec(req.get("court") or "sessions", req.get("bail_type") or "regular")
        elif n == 1:
            spec = mod.field_spec(req.get("court") or "sessions")
        else:
            spec = mod.field_spec()
        spec["ok"] = True
        out = spec
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


main()
