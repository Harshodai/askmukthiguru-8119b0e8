#!/usr/bin/env bash
# ponytail: thin wrapper, 5 lines. Upgrade: add volume prune flag if disk pressure hits.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
cd backend
docker compose -f docker-compose.dev.yml down