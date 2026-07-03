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
if [ -n "${UVICORN_WORKERS_OVERRIDE}" ] && [ "${UVICORN_WORKERS_OVERRIDE}" -gt 0 ] 2>/dev/null; then
    # Explicit override — use as-is (prod tuning without OOM on dev machines)
    WEB_CONCURRENCY="${UVICORN_WORKERS_OVERRIDE}"
    export WEB_CONCURRENCY
    echo "Using UVICORN_WORKERS_OVERRIDE=${WEB_CONCURRENCY} workers"
elif [ -z "${WEB_CONCURRENCY}" ]; then
    # Auto: ML models are large (~1.4 GB each). Cap at min(CPU cores, 2) to avoid OOM.
    # Scale horizontally with multiple container replicas for higher throughput.
    CPU_CORES=$(nproc 2>/dev/null || sysctl -n hw.ncpu 2>/dev/null || echo 1)
    WEB_CONCURRENCY=$(( CPU_CORES < 2 ? CPU_CORES : 2 ))
    export WEB_CONCURRENCY
    echo "Auto-setting WEB_CONCURRENCY to ${WEB_CONCURRENCY} (detected ${CPU_CORES} CPU cores)"
fi


# If the command starts with python/uvicorn, inject --workers from WEB_CONCURRENCY
if [[ "$1" == 'python' ]] || [[ "$1" == 'uvicorn' ]]; then
    echo "Warming cache in the background..."
    gosu appuser python -m scripts.warm_cache > /app/data/warm_cache.log 2>&1 &

    echo "Starting uvicorn with WEB_CONCURRENCY=${WEB_CONCURRENCY} workers..."
    echo "Dropping privileges to appuser..."
    exec gosu appuser python -m uvicorn app.main:app \
        --host 0.0.0.0 \
        --port 8000 \
        --workers "${WEB_CONCURRENCY}" \
        --timeout-keep-alive 300
fi

# Celery worker — drop privileges like uvicorn
if [[ "$1" == 'celery' ]]; then
    echo "Starting Celery worker..."
    echo "Dropping privileges to appuser..."
    exec gosu appuser "$@"
fi

