"""Headnote — uvicorn entrypoint.

The FastAPI app lives in `headnote.api.app`; this module is a thin shim so
existing deployments (Render's `uvicorn main:app`, Procfile, render.yaml)
keep working unchanged. New code should import `from headnote.api.app import app`.

Run locally:
    pip install -r requirements.txt
    export ANTHROPIC_API_KEY=sk-ant-...
    uvicorn main:app --reload --port 8000

Run as a Python script (preferred for Railway / hosts that override CMD with
exec-form and break shell expansion of $PORT):
    python main.py
"""

from headnote.api.app import app

__all__ = ["app"]


if __name__ == "__main__":
    # Hosts (Railway / fly.io / Cloud Run) inject $PORT dynamically. When the
    # platform overrides Dockerfile CMD with an exec-form start command, the
    # shell never expands `$PORT` and uvicorn sees the literal string '$PORT'
    # → 'is not a valid integer' error. Reading PORT directly in Python
    # sidesteps the whole shell-expansion problem.
    import os
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
