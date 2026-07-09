#!/usr/bin/env bash
# Run the full benchmark ladder from your terminal (saves Claude tokens).
# Prereq: backend rebuilt & healthy — check with:
#   curl -s http://localhost:8000/api/health | python3 -m json.tool
#
# Usage:  cd backend && bash benchmarks/RUN_ME.sh [quick|full]
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
MODE="${1:-quick}"
if [ "$MODE" != "quick" ] && [ "$MODE" != "full" ]; then
  echo "Error: Invalid mode '$MODE'. Supported modes: quick, full." >&2
  exit 1
fi

# Benchmark-local endpoint overrides (host runs scripts, Docker uses internal hostnames).
set -a
[ -f "benchmarks/.env.benchmark" ] && source "benchmarks/.env.benchmark"
set +a

echo "=== 0. flush caches (via docker exec — flush_cache.py needs Docker hostnames) ==="
docker compose exec -T backend python3 /app/scripts/ops/flush_cache.py 2>/dev/null \
  || (echo "  ⚠️ docker exec failed; trying host-side flush..." && $PY ../scripts/ops/flush_cache.py) \
  || echo "  ⚠️ Cache flush failed — caches may be warm."

echo "=== 1. smoke (retrieval sanity, ~1min) ==="
$PY benchmarks/smoke_doctrine.py

echo "=== 2. focused regression fixes ==="
$PY benchmarks/focused_fix_test.py

if [ "$MODE" = "full" ]; then
  echo "=== 3. ruthless (adversarial, slow) ==="
  $PY benchmarks/ruthless_benchmark.py
  echo "=== 4. comprehensive + dashboard ==="
  $PY benchmarks/comprehensive_benchmark.py
  $PY benchmarks/generate_dashboard.py
else
  echo "(skipped ruthless+comprehensive — pass 'full' to run them)"
fi
echo "=== done. Key things to eyeball ==="
echo " - model_used should now be the REAL model (or null on cache/canned paths)"
echo " - cache_hit/latency_ms should be truthful on doctrine-cache answers"
echo " - comparison questions should mention BOTH teachers (KG only has 5 edges — expect weakness until backfill)"
