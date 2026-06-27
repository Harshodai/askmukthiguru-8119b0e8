#!/bin/bash
# Daily backup wrapper — sources docker-compose env vars and runs snapshot_manager
set -e
DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$DIR"
# Source docker-compose env file for NEO4J_PASSWORD and other vars
if [ -f backend/.env ]; then
  set -a
  . backend/.env
  set +a
fi
exec python3 scripts/backup/snapshot_manager.py backup
