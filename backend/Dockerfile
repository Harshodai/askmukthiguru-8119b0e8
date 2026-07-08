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

COPY backend/requirements.txt ./
# Install the pre-compiled requirements.txt directly
# 'uv' installs packages 10-100x faster than standard pip
RUN uv pip install --system --no-cache -r requirements.txt

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
RUN mkdir -p /app/model_cache && python3 /app/scripts/download_models.py


# Copy application code
COPY backend/ .

# Copy the entrypoint script
COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh

# Expose port
EXPOSE 8000

# Health check — long start period for ML model download/loading
HEALTHCHECK --interval=30s --timeout=10s --start-period=420s --retries=8 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

