# syntax=docker/dockerfile:1
# ============================================================
# Mukthi Guru — Backend Dockerfile
# Multi-stage build for minimal image size
# ============================================================

FROM python:3.12-slim AS base

# System deps for sentence-transformers, scikit-learn, umap, lightrag, and gosu for dropping privileges
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    ffmpeg \
    zlib1g-dev \
    gosu \
    && rm -rf /var/lib/apt/lists/*

# Create a non-root user
RUN useradd -m -s /bin/bash appuser


WORKDIR /app

# --- Stage 1: Install Python dependencies ---
FROM base AS deps

# Install 'uv' for state-of-the-art fast dependency installation
RUN pip install --no-cache-dir uv

# Pre-install CPU-only PyTorch and torchvision wheels from official PyTorch repository
# to prevent PyPI Linux default wheels from downloading 3.5+ GB of unnecessary NVIDIA CUDA 13 packages.
RUN uv pip install --system --no-cache --index-url https://download.pytorch.org/whl/cpu torch torchvision

COPY backend/requirements.lock ./
# Install the committed requirements.lock directly
# 'uv' installs packages 10-100x faster than standard pip
RUN uv pip install --system --no-cache -r requirements.lock

# --- Stage 2: Final image ---
FROM base AS final

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Fix Docker overlay2 mmap issue with cryptography's _rust.abi3.so:
# COPY places .so files in a readonly overlay layer; mmap fails there.
# Rewrite every .so file through a temp copy to force into writable layer.
RUN find /usr/local/lib/python3.12/site-packages -name '_rust.abi3.so' -exec sh -c 'cp "$1" /tmp/sofix && cp /tmp/sofix "$1" && rm /tmp/sofix' _ {} \;
RUN python3 -c "from cryptography.hazmat.bindings._rust import exceptions; print('crypto .so fixed, imports OK')"

# Pre-download embedding models to overlay filesystem (avoids Docker Desktop
# gRPC-FUSE mmap failures on named volumes for large .safetensors files).
# Downloaded to /app/model_cache which is NOT shadowed by hf_model_cache volume.
# Pre-download embedding models to BOTH caches:
# 1. sentence_transformers cache (for SentenceTransformer API)
# 2. huggingface hub cache (for BGEM3FlagModel / FlagEmbedding API)
#
# Docker Desktop gRPC-FUSE causes SSL malloc failures in httpx (used by huggingface_hub v0.36+).
# Workaround: configure huggingface_hub to use an httpx client with verify=False.
COPY backend/scripts/download_models.py /app/scripts/download_models.py
# --secret keeps HF_TOKEN out of the image layers entirely (unlike ARG/ENV, which
# would bake it into layer history, extractable via `docker history`). Optional
# (required=false): every existing build invocation (docker-compose, skaffold,
# CI) that doesn't pass --secret keeps working exactly as before — the gated
# Llama-Guard-3-1B download just stays skipped, same graceful-degradation
# behavior download_models.py already has. Pass it with:
#   docker build --secret id=hf_token,env=HF_TOKEN ...
ENV QUANTIZED_ONLY=true
RUN --mount=type=secret,id=hf_token,env=HF_TOKEN,required=false \
    mkdir -p /app/model_cache && python3 /app/scripts/download_models.py

# L-INTENT-ENCODER-1: docker-compose bind-mounts ./.model_cache over /app/model_cache, which
# hides the models baked above on any machine whose host directory is empty (clean checkout).
# Keep a pristine copy; docker-entrypoint.sh seeds the mount from it without overwriting.
RUN cp -a /app/model_cache /opt/model_cache_seed


# Copy application code
COPY backend/ .

# The OKF compiled index lives at the repo root, not under backend/, but
# rag/nodes/retrieval.py resolves it to /app/memory/okf/compiled.json inside the
# image. Without this the loader caches an empty index and OKF injection
# (rag_okf_injection_enabled, default True) contributes nothing.
COPY memory/ ./memory/

# Owner-approved crisis helplines (config/helplines.yaml at the repo root).
# services/crisis_helplines.py resolves this to /config/helplines.yaml inside
# the image (Path(__file__).resolve().parents[2] from /app/services/, i.e.
# filesystem root, not /app/config/) -- without it the safety path silently
# serves the in-code fallback list instead of the reviewed one.
COPY config/helplines.yaml /config/helplines.yaml

# Copy the entrypoint script
COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh

# Expose port
EXPOSE 8000

# Health check — long start period for ML model download/loading
HEALTHCHECK --interval=30s --timeout=10s --start-period=420s --retries=8 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Drop privileges (entrypoint starts as root for chown, then gosu drops to appuser)
USER root

ENTRYPOINT ["/app/docker-entrypoint.sh"]
# glibc per-thread malloc arenas reserve virtual memory that RLIMIT_DATA counts;
# cap them so the virtual footprint tracks RSS (2026-09-26).
ENV MALLOC_ARENA_MAX=2
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
