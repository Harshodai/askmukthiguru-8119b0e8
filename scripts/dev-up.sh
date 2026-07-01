#!/usr/bin/env bash
# ponytail: thin wrapper, 5 lines. Upgrade: add health-wait loop if startup races bite.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
cd backend
docker compose -f docker-compose.dev.yml up -d