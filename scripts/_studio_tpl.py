"""Local bridge so the node preview can serve the EXISTING editor's two endpoints
against the V2 canonical engine:
  GET  /api/draft/template-schema/{id}  → {"template": <editor-shape schema>}
  POST /api/draft/render-template        → {"ok": true, "document": <bundle html>}

stdin : {"mode": "schema"|"render", "doc_type": "...", "fields": {...}, "lang": "hi"}
(mode defaults to "render" when absent — that's the POST body shape.)
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        from headnote.drafter import template_adapter as TA
        req = json.load(sys.stdin)
        tid = req.get("doc_type") or req.get("id") or ""
        if not TA.is_canonical(tid):
            out = {"ok": False, "error": f"'{tid}' is not a canonical V2 type"}
        elif req.get("mode") == "schema":
            out = {"template": TA.schema(tid)}
        else:
            out = {"ok": True, "document": TA.document(tid, req.get("fields") or {}, req.get("lang") or "hi")}
    except Exception as e:
        out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    sys.stdout.write(json.dumps(out, ensure_ascii=False))


main()
