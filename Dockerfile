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
    FEEDBACK_DB=/data/feedback.db \
    # Official SC judgment corpus lives on the SAME persistent volume so the
    # metadata + offset index (and, later, extracted text) survive deploys.
    # On first boot the app seeds this from the ~14MB core baked into the
    # image (see _maybe_bootstrap_judgments_on_boot in app.py). The PDF LRU
    # cache is left at its ephemeral default (/app/.pdf_cache) on purpose —
    # PDFs re-fetch in one Range GET on a miss, so it needn't burn volume space.
    JUDGMENTS_DB=/data/judgments.sqlite

# Set up /data with permissive permissions for the persistent volume.
# We run as root in this image — the security trade-off (non-root user vs
# Railway-volume-mount permissions) lost: Railway mounts the volume as root
# and the headnote user (UID 10001) couldn't write to it, so the code kept
# falling back to /tmp and losing data on every restart. Running as root
# means root inside the container only — Railway's container sandbox already
# isolates this from the host. No real security regression for our scale.
RUN mkdir -p /data && chmod 777 /data

# WeasyPrint runtime libs + fonts for server-side PDF export (/api/draft/pdf).
# WeasyPrint >=53 dropped Cairo/GDK — it needs Pango (+ HarfBuzz, FontConfig,
# FreeType, GLib, pulled transitively) to shape text and emit a real, text-
# selectable PDF. Fonts: fonts-noto-core supplies Noto Serif/Sans Devanagari
# (correct Hindi conjuncts); fonts-liberation gives a Times-metric serif for
# the Latin / statute text. Kept as its own layer (rarely changes → caches).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      libpango-1.0-0 libpangoft2-1.0-0 libharfbuzz0b \
      libfontconfig1 libfreetype6 libglib2.0-0 \
      fonts-liberation fonts-noto-core \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY . /app

# No EXPOSE / HEALTHCHECK directives. Both were hardcoded to port 8000 which
# breaks on hosts that inject a dynamic $PORT (Railway, fly.io, Cloud Run).
# Railway's gateway uses the PORT env var for routing; the app binds to it.

# Run as a Python script so PORT is read inside Python — bypasses every
# shell-expansion gotcha (Railway exec-form override, alpine /bin/sh
# quirks, etc.). main.py's `if __name__ == "__main__"` block reads PORT
# from env and starts uvicorn programmatically. Exec form preserves
# SIGTERM propagation for clean shutdown.
CMD ["python", "main.py"]
