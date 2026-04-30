#!/bin/bash
set -e

# Ensure the HuggingFace cache directory exists
mkdir -p /app/.cache

# If the command starts with 'python' or 'uvicorn', run the initialization
if [[ "$1" = 'python' ]] || [[ "$1" = 'uvicorn' ]]; then
    echo "Running initialization as root..."
    
    # Fix permissions for the cache volume (mounted from host)
    chown -R appuser:appuser /app/.cache || echo "Warning: Could not chown /app/.cache"
    
    # Also fix permissions for the SQLite telemetry DB volume if it exists
    mkdir -p /app/data
    chown -R appuser:appuser /app/data || echo "Warning: Could not chown /app/data"
    
    echo "Dropping privileges to appuser..."
    # Exec gosu to run the actual command as appuser, replacing the current process (for SIGTERM)
    exec gosu appuser "$@"
fi

# Fallback: just execute the command as-is
exec "$@"
