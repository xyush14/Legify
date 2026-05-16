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

# Install only the deps first (better layer caching on rebuild)
COPY requirements.txt requirements-dev.txt ./
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

COPY --from=builder /opt/venv /opt/venv

WORKDIR /app
COPY --chown=headnote:headnote . /app

USER headnote
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request, sys; \
        r = urllib.request.urlopen('http://localhost:8000/api/health', timeout=3); \
        sys.exit(0 if r.status == 200 else 1)" || exit 1

# Use exec form so SIGTERM propagates cleanly to uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
