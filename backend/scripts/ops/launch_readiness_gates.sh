#!/usr/bin/env bash
# Runs the automatable launch-readiness gate scripts. Exits non-zero if any
# gate reports a BLOCKER/HIGH failure. See docs/audits/LAUNCH_READINESS_GATES_2026-09-13.md
# for the gates NOT covered here — most of the full spec is not automatable
# in a single script (load tests, chaos injection, human golden-set review).
set -uo pipefail
cd "$(dirname "$0")/../.."

FAILED=0

echo "=== KG readiness gate ==="
NEO4J_PASSWORD="${NEO4J_PASSWORD:-$(grep NEO4J_PASSWORD .env 2>/dev/null | head -1 | cut -d= -f2)}" \
  .venv/bin/python scripts/ops/launch_gate_kg_readiness.py || FAILED=1

echo
echo "=== Qdrant data-integrity gate ==="
.venv/bin/python scripts/ops/launch_gate_qdrant_integrity.py || FAILED=1

echo
if [ "$FAILED" -ne 0 ]; then
  echo "LAUNCH GATE: BLOCKER/HIGH failures found above. Do not launch until resolved or explicitly waived."
  exit 1
fi
echo "LAUNCH GATE: automatable checks passed. This does NOT cover load, chaos, or golden-set review — see the full gate doc."
exit 0
