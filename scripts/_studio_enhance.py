"""stdin→stdout AI-enhance bridge for the Drafting Studio's per-field ✨ enhancer.
Polishes the lawyer's OWN rough prose (facts/grounds paras) into clean formal legal
language — it must NOT invent facts/names/dates/sections/citations. Uses the project
LLM client (DeepSeek→Groq; Groq key present locally). Prod uses the FastAPI path.

stdin : {"text": "...", "lang": "hi"|"en"}
stdout: {"ok": true, "enhanced": "..."}
"""
import json
import os
import sys
import warnings

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

# load .env so GROQ_API_KEY / DEEPSEEK_API_KEY are available locally
_envp = os.path.join(ROOT, ".env")
if os.path.exists(_envp):
    for _line in open(_envp, encoding="utf-8"):
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip().strip('"').strip("'"))

SYS = ("You are a legal-drafting assistant for Indian court documents. Improve the clarity, "
       "grammar, flow and formal legal phrasing of the text given, keeping it in the SAME language "
       "({lang}). STRICT RULES: do NOT invent or add any facts, names, dates, amounts, section "
       "numbers, case citations or legal claims — only polish what is already present; keep it "
       "concise and court-appropriate. Return ONLY the improved text, no preamble, no quotes.")


def main():
    try:
        req = json.load(sys.stdin)
        text = (req.get("text") or "").strip()
        lang = "Hindi (Devanagari)" if req.get("lang", "hi") == "hi" else "English"
        if not text:
            sys.stdout.write(json.dumps({"ok": False, "error": "empty"})); return
        from headnote.llm.client import _call_deepseek_or_groq
        out, _meta = _call_deepseek_or_groq(SYS.replace("{lang}", lang), text, max_tokens=900)
        sys.stdout.write(json.dumps({"ok": True, "enhanced": (out or "").strip()}, ensure_ascii=False))
    except Exception as e:
        sys.stdout.write(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}, ensure_ascii=False))


main()
