# Headnote — production Docker image.
#
# Two-stage build keeps the final image small (~250MB without embeddings,
# ~400MB with): stage 1 installs deps into a venv; stage 2 copies just the
# venv and source.
#
# Build:  docker build -t headnote:latest .
# Run:    docker run --rm -p 8000:8000 --env-file .env headnote:latest
# Health: curl http://localhost:8000/api/health
#
# To enable local embeddings (semantic search over IK cache), build with:
#   docker build --build-arg INSTALL_EMBEDDINGS=1 -t headnote:emb .
# The bge-small-en-v1.5 model (~80MB) is downloaded lazily on first use,
# not at build time, so the image stays small until the model is fetched.

# -------------------- stage 1: builder

FROM python:3.11-slim AS builder

ARG INSTALL_EMBEDDINGS=0

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Install only the deps first (better layer caching on rebuild). Note we
# DON'T copy requirements-dev.txt — it's excluded by .dockerignore and
# never installed in the production image anyway. Including it in COPY
# breaks Railway / Docker BuildKit because the file isn't in the build
# context.
COPY requirements.txt ./
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --upgrade pip \
 && /opt/venv/bin/pip install -r requirements.txt \
 && if [ "$INSTALL_EMBEDDINGS" = "1" ]; then \
        /opt/venv/bin/pip install fastembed numpy ; \
    fi

# -------------------- stage 2: runtime

FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH" \
    # Persistent cache location — mount a volume here in production so the
    # IK doc cache and embedding index survive restarts.
    KANOON_CACHE_PATH=/data/kanoon_cache.sqlite \
    FEEDBACK_DB=/data/feedback.db

# Run as a non-root user
RUN groupadd --gid 10001 headnote \
 && useradd  --uid 10001 --gid 10001 --create-home --shell /bin/bash headnote \
 && mkdir -p /data \
 && chown headnote:headnote /data

COPY --from=builder --chown=headnote:headnote /opt/venv /opt/venv

WORKDIR /app
COPY --chown=headnote:headnote . /app

USER headnote

# No EXPOSE / HEALTHCHECK directives. Both were hardcoded to port 8000 which
# breaks on hosts that inject a dynamic $PORT (Railway, fly.io, Cloud Run).
# Railway's gateway uses the PORT env var for routing; the app binds to it.
# Render uses its own out-of-band healthcheck against the URL Render assigns.

# Run as a Python script so PORT is read inside Python — bypasses every
# shell-expansion gotcha (Railway exec-form override, alpine /bin/sh
# quirks, etc.). main.py's `if __name__ == "__main__"` block reads PORT
# from env and starts uvicorn programmatically. Exec form preserves
# SIGTERM propagation for clean shutdown.
CMD ["python", "main.py"]
