"""Headnote — uvicorn entrypoint.

The FastAPI app lives in `headnote.api.app`; this module is a thin shim so
existing deployments (Render's `uvicorn main:app`, Procfile, render.yaml)
keep working unchanged. New code should import `from headnote.api.app import app`.

Run locally:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8000
"""

from headnote.api.app import app

__all__ = ["app"]
