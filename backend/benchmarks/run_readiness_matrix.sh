#!/usr/bin/env bash
set -euo pipefail

: "${LOAD_TEST_URL:?Set LOAD_TEST_URL to a non-production staging or local endpoint.}"
: "${BENCHMARK_SECRET:?Set BENCHMARK_SECRET only for the local/staging test-auth path.}"

USERS="${READINESS_USERS:-25 100 250 500}"
SPAWN_RATE="${READINESS_SPAWN_RATE:-25}"
DURATION="${READINESS_DURATION:-180s}"
MAX_P95_MS="${READINESS_MAX_P95_MS:-8000}"
MAX_FAILURE_RATE="${READINESS_MAX_FAILURE_RATE:-0.01}"
OUT_DIR="${READINESS_OUT_DIR:-benchmarks/results/readiness-$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_DIR"

for users in $USERS; do
  report="$OUT_DIR/locust-${users}.json"
  locust -f benchmarks/locustfile.py --headless -u "$users" -r "$SPAWN_RATE" \
    -t "$DURATION" --host "$LOAD_TEST_URL" --json > "$report"
  python benchmarks/readiness_gate.py --report "$report" --expected-users "$users" \
    --max-p95-ms "$MAX_P95_MS" --max-failure-rate "$MAX_FAILURE_RATE"
done

echo "Readiness matrix passed. Reports: $OUT_DIR"
