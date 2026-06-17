#!/usr/bin/env bash
# Light smoke load test — ~50 RPS for 2 min against /healthz + chat rate-limit burst.
# Usage:
#   PROJECT_REF=fynkjimvuimakgtidvuq ANON_KEY=... ./scripts/benchmarks/smoke.sh
# Requires: curl, optionally `hey` (https://github.com/rakyll/hey) for richer percentiles.

set -euo pipefail

: "${PROJECT_REF:?set PROJECT_REF (Supabase project ref)}"
: "${ANON_KEY:?set ANON_KEY (Supabase anon/publishable key)}"

BASE="https://${PROJECT_REF}.supabase.co/functions/v1"
HEALTH="${BASE}/healthz"
CHAT="${BASE}/chat-rate-limit"

OUT_DIR="${OUT_DIR:-docs/load-test-output}"
mkdir -p "$OUT_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"

echo "==> Phase 1: /healthz warmup (5 sequential calls)"
for i in 1 2 3 4 5; do
  t=$(curl -sS -o /dev/null -w '%{http_code} %{time_total}\n' \
        -H "apikey: $ANON_KEY" "$HEALTH")
  echo "  hit $i: $t"
done

echo "==> Phase 2: /healthz sustained ~50 RPS for 120s"
if command -v hey >/dev/null 2>&1; then
  hey -z 120s -q 50 -c 10 -H "apikey: $ANON_KEY" "$HEALTH" \
    | tee "$OUT_DIR/healthz-${STAMP}.txt"
else
  echo "  (hey not found — falling back to curl loop, no percentiles)"
  END=$((SECONDS+120)); N=0; FAIL=0
  while [ $SECONDS -lt $END ]; do
    code=$(curl -sS -o /dev/null -w '%{http_code}' \
            -H "apikey: $ANON_KEY" "$HEALTH" || echo 000)
    [ "$code" = "200" ] || FAIL=$((FAIL+1))
    N=$((N+1))
    # ~50 RPS pacing with 10 parallel curl-loops would be ideal; here we just hammer single-threaded.
  done
  echo "  total=$N fail=$FAIL" | tee "$OUT_DIR/healthz-${STAMP}.txt"
fi

echo "==> Phase 3: chat-rate-limit burst (60 req in 10s, expect 429 after bucket drained)"
SUCCESS=0; LIMITED=0; OTHER=0
for i in $(seq 1 60); do
  code=$(curl -sS -o /dev/null -w '%{http_code}' \
          -H "apikey: $ANON_KEY" \
          -H "Authorization: Bearer ${TEST_USER_JWT:-$ANON_KEY}" \
          -H "Content-Type: application/json" \
          -d '{"messages":[{"role":"user","content":"smoke"}]}' \
          "$CHAT" || echo 000)
  case "$code" in
    200) SUCCESS=$((SUCCESS+1));;
    429) LIMITED=$((LIMITED+1));;
    *)   OTHER=$((OTHER+1));;
  esac
  sleep 0.16   # ~6 rps for 10s
done
echo "  success=$SUCCESS limited=$LIMITED other=$OTHER" \
  | tee "$OUT_DIR/ratelimit-${STAMP}.txt"

echo "==> Done. Results in $OUT_DIR/"
