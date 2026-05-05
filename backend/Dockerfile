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

COPY backend/pyproject.toml .
# Compile the modern pyproject.toml into a strict lockfile and install it
# 'uv' installs packages 10-100x faster than standard pip
RUN uv pip compile pyproject.toml -o requirements.txt && \
    uv pip install --system --no-cache -r requirements.txt

# --- Stage 2: Final image ---
FROM base AS final

# Copy installed packages from deps stage
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin

# Copy application code
# Copy application code
COPY backend/ .
# Copy Ingestion UI static files
COPY ingest-ui/ /app/ingest-ui/
# Copy Chat UI static files
COPY chat-ui/ /app/chat-ui/

# Copy the entrypoint script
COPY backend/docker-entrypoint.sh /app/docker-entrypoint.sh

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

# Run with entrypoint
ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

