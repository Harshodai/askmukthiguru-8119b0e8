#!/usr/bin/env bash
# ponytail: thin wrapper, wipe volumes then recreate. Upgrade: snapshot before wipe if data loss stings.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
cd backend
docker compose -f docker-compose.dev.yml down -v
docker compose -f docker-compose.dev.yml up -d