#!/usr/bin/env bash
# AskMukthiGuru loop-engineering validation runner.
# Runs independent gates, records every result, and continues after failures so
# one stalled or environment-specific check cannot hide the rest of the matrix.
set +e

ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)"
OUT_DIR="${LOOP_EVIDENCE_DIR:-$ROOT/docs/production-readiness/loop-runs/$(date -u +%Y%m%dT%H%M%SZ)}"
mkdir -p "$OUT_DIR"
SUMMARY="$OUT_DIR/summary.tsv"
: > "$SUMMARY"

run_gate() {
  local name="$1"; shift
  local logfile="$OUT_DIR/${name}.log"
  printf '\n===== %s =====\n' "$name" | tee "$logfile"
  (cd "$ROOT" && "$@") >>"$logfile" 2>&1
  local code=$?
  printf '%s\t%s\t%s\n' "$name" "$code" "$logfile" | tee -a "$SUMMARY"
  tail -n 12 "$logfile"
  return 0
}

run_shell_gate() {
  local name="$1"; shift
  local logfile="$OUT_DIR/${name}.log"
  printf '\n===== %s =====\n' "$name" | tee "$logfile"
  (cd "$ROOT" && bash -lc "$*") >>"$logfile" 2>&1
  local code=$?
  printf '%s\t%s\t%s\n' "$name" "$code" "$logfile" | tee -a "$SUMMARY"
  tail -n 12 "$logfile"
  return 0
}

run_shell_gate repository_state 'git rev-parse HEAD; git rev-parse origin/main 2>/dev/null || true; git status --short'
run_gate json_settings python3 -m json.tool .claude/settings.local.json >/dev/null
run_gate diff_check git diff --check
run_gate frontend_unit npm test -- --run
run_gate frontend_lint npm run lint
run_gate frontend_typecheck npm run typecheck
run_gate frontend_build npm run build
run_gate bundle_budget npm run bundle:check

PYTHON="$ROOT/backend/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
  PYTHON="$ROOT/backend/venv/bin/python"
fi
if [ -x "$PYTHON" ]; then
  run_gate backend_focused "$PYTHON" -m pytest \
    backend/tests/test_runtime_artifacts.py \
    backend/tests/test_health.py \
    backend/tests/test_authz_regression.py \
    backend/tests/test_attachment_retrieval_guards.py \
    backend/tests/test_chat_uploads.py \
    backend/tests/test_guardrail_self_harm_priority.py \
    backend/tests/test_distress_provider_fail_closed.py \
    backend/tests/test_second_brain_timestamps.py \
    backend/tests/test_queued_sse_completion.py \
    -q --tb=short
  run_gate backend_ruff "$PYTHON" -m ruff check backend
  run_gate backend_bandit "$PYTHON" -m bandit -r backend -c backend/.bandit -ll
  run_gate regex_safety "$PYTHON" scripts/security/check_regex_safety.py
  run_gate backend_compile "$PYTHON" -m compileall -q backend/app backend/services backend/ingest
else
  printf 'backend_dependencies\tSKIP\tbackend virtualenv unavailable\n' | tee -a "$SUMMARY"
fi

if [ "${FULL_BACKEND:-0}" = "1" ] && [ -x "$PYTHON" ]; then
  run_gate backend_full "$PYTHON" -m pytest backend/tests -q --tb=short
else
  printf 'backend_full\tSKIP\tset FULL_BACKEND=1 to run the dependency-complete full suite\n' | tee -a "$SUMMARY"
fi

printf '\nLoop evidence written to: %s\n' "$OUT_DIR"
printf '\nGate summary:\n'
cat "$SUMMARY"

if awk -F '\t' '$2 != 0 && $2 != "SKIP" { bad=1 } END { exit bad }' "$SUMMARY"; then
  echo 'LOOP_RESULT=PASS'
  exit 0
else
  echo 'LOOP_RESULT=FAIL'
  exit 1
fi
