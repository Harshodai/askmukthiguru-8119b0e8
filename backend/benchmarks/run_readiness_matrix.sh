#!/usr/bin/env bash
set -euo pipefail

: "${LOAD_TEST_URL:?Set LOAD_TEST_URL to a local or approved staging endpoint.}"
: "${BENCHMARK_SECRET:?Set BENCHMARK_SECRET only for the local/staging test-auth path.}"

host="${LOAD_TEST_URL#http://}"
host="${host#https://}"
host="${host%%/*}"
host="${host%%:*}"

case "$host" in
  localhost|127.0.0.1|::1)
    ;;
  *)
    : "${READINESS_TARGET:?Set READINESS_TARGET=staging for a remote load test.}"
    : "${READINESS_STAGING_HOST:?Set the exact approved staging hostname.}"
    if [[ "$READINESS_TARGET" != "staging" ]]; then
      echo "Refusing remote readiness test: READINESS_TARGET must be staging." >&2
      exit 64
    fi
    if [[ "$host" != "$READINESS_STAGING_HOST" ]]; then
      echo "Refusing remote readiness test: host is not the approved staging host." >&2
      exit 64
    fi
    ;;
esac

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
