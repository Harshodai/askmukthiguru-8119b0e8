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
    # Default: 2 workers per pod (lightweight, scale horizontally with HPA)
    WEB_CONCURRENCY="2"
    export WEB_CONCURRENCY
    echo "Auto-setting WEB_CONCURRENCY to ${WEB_CONCURRENCY}"
fi

# If the command starts with python, uvicorn, or gunicorn, apply privilege drop
if [[ "$1" == 'python' ]] || [[ "$1" == 'uvicorn' ]] || [[ "$1" == 'gunicorn' ]]; then
    echo "Dropping privileges to appuser..."
    # Exec gosu to run the actual command as appuser, replacing the current process (for SIGTERM)
    exec gosu appuser "$@"
fi

# Fallback: just execute the command as-is
exec "$@"
