"""stdin→stdout translation bridge for the Drafting Studio's live language sync.
Uses headnote.translate._translate_string (free Google Translate → MyMemory →
original), so it needs NO API key and works on the local preview. Prod uses the
FastAPI /api/draft/translate-fields, same contract.

stdin : {"fields": {"key": "value", ...}, "target": "hi"|"en"}
stdout: {"ok": true, "translated": {"key": "translated", ...}}
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    try:
        from headnote.translate import _translate_string
        req = json.load(sys.stdin)
        fields = req.get("fields") or {}
        target = req.get("target", "hi")
        out = {}
        for k, v in fields.items():
            out[k] = _translate_string(v, target) if isinstance(v, str) and v.strip() else v
        res = {"ok": True, "translated": out}
    except Exception as e:
        res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
    sys.stdout.write(json.dumps(res, ensure_ascii=False))


main()
