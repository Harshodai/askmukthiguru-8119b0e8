#!/usr/bin/env bash
# =============================================================================
# Run Nightly Memory Dreaming Consolidation (Lance Martin / Anthropic Pattern)
#
# Executes offline sleep-time compute:
# 1. Snapshot creation (canonical_memory_compaction_snapshots)
# 2. Transcript grounding audit (prunes ungrounded memory claims)
# 3. Contradiction resolution & temporal state evolution
# 4. Mathematical decay (decay_score *= 0.97) and pruning
# 5. Layer 4 SeekerCoreDashboard re-synthesis
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$(cd "${SCRIPT_DIR}/../.." && pwd)/backend"

if [ ! -d "${BACKEND_DIR}" ]; then
  # Inside docker container where app root is /app
  BACKEND_DIR="/app"
fi

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Starting Nightly Agent Memory Dreaming Worker..."

cd "${BACKEND_DIR}"
export PYTHONPATH="${BACKEND_DIR}"

python3 -m scripts.dream_memories --all "$@"

echo "[$(date -u +"%Y-%m-%dT%H:%M:%SZ")] Nightly Memory Dreaming Consolidation Completed Successfully."
