#!/bin/bash
set -e

# Ensure the HuggingFace cache directory exists
mkdir -p /app/.cache

echo "Running initialization as root..."

# Fix permissions for the cache volume (mounted from host)
chown -R appuser:appuser /app/.cache || echo "Warning: Could not chown /app/.cache"

# Also fix permissions for the SQLite telemetry DB volume if it exists
mkdir -p /app/data
chown -R appuser:appuser /app/data || echo "Warning: Could not chown /app/data"

# Detect available CPU cores and set worker count
if [ -z "${WEB_CONCURRENCY}" ]; then
    # Default: 1 worker (ML-heavy: embedding model ~1.4GB per process; don't OOM)
    # Scale horizontally with multiple container replicas instead.
    WEB_CONCURRENCY="1"
    export WEB_CONCURRENCY
    echo "Auto-setting WEB_CONCURRENCY to ${WEB_CONCURRENCY}"
fi

# If the command starts with python/uvicorn, inject --workers from WEB_CONCURRENCY
if [[ "$1" == 'python' ]] || [[ "$1" == 'uvicorn' ]]; then
    echo "Starting uvicorn with WEB_CONCURRENCY=${WEB_CONCURRENCY} workers..."
    echo "Dropping privileges to appuser..."
    exec gosu appuser python -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers "${WEB_CONCURRENCY}" \
        --timeout-keep-alive 300
fi

