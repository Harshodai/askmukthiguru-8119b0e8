#!/usr/bin/env bash
# Phase 0 + Phase 1 verification transcript for the first-person v10 public-release
# remediation (2026-10-21). Every command's real exit code is recorded.
#
# Read-only: no Qdrant write, no alias change, no env change, no deployment.
set -u
cd "$(dirname "$0")/../../.." || exit 99
REPO="$PWD"
PY="$REPO/backend/.venv/bin/python"
TRANSCRIPT="$REPO/audits/evidence/public_release_phase1_verification_2026-10-21.txt"
mkdir -p "$(dirname "$TRANSCRIPT")"

run() {
  local label="$1"; shift
  local dir="$1"; shift
  echo "===================================================================" >> "$TRANSCRIPT"
  echo "phase: $label" >> "$TRANSCRIPT"
  echo "command: $*" >> "$TRANSCRIPT"
  echo "cwd: $dir" >> "$TRANSCRIPT"
  local start end code
  start="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "start_utc: $start" >> "$TRANSCRIPT"
  ( cd "$dir" && "$@" ) >> "$TRANSCRIPT" 2>&1
  code=$?
  end="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "end_utc: $end" >> "$TRANSCRIPT"
  echo "exit_code: $code" >> "$TRANSCRIPT"
  echo "" >> "$TRANSCRIPT"
  echo "### $label -> exit $code"
  return $code
}

: > "$TRANSCRIPT"

run "phase0: state capture" "$REPO" \
  "$PY" backend/scripts/ops/capture_public_release_phase0_state.py \
  --output audits/evidence/public_release_phase0_state_2026-10-21.json

run "phase1: py_compile" "$REPO" \
  "$PY" -m py_compile backend/scripts/ops/reconcile_v10_ecapa_verdicts.py

run "phase1: focused tests" "$REPO/backend" \
  "$PY" -m pytest tests/test_reconcile_v10_ecapa_verdicts.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase1: --help" "$REPO" \
  "$PY" backend/scripts/ops/reconcile_v10_ecapa_verdicts.py --help

run "phase1: dry-run release_grade" "$REPO" \
  "$PY" backend/scripts/ops/reconcile_v10_ecapa_verdicts.py \
    --v10-points .work/public_release/v10_points_export.json \
    --legacy-points .work/fp_context/v9_points.json \
    --verdicts .work/fp_context/speaker_verdicts.json \
    --asr-manifest .work/fp_context/asr_manifest_existing.json \
    --out .work/public_release/reconciliation_v10_ecapa.jsonl \
    --summary audits/evidence/public_release_v10_ecapa_reconciliation_summary_2026-10-21.json

run "phase1: dry-run legacy_v1" "$REPO" \
  "$PY" backend/scripts/ops/reconcile_v10_ecapa_verdicts.py \
    --v10-points .work/public_release/v10_points_export.json \
    --legacy-points .work/fp_context/v9_points.json \
    --verdicts .work/fp_context/speaker_verdicts.json \
    --asr-manifest .work/fp_context/asr_manifest_existing.json \
    --verdict-schema-policy legacy_v1 \
    --out .work/public_release/reconciliation_v10_ecapa_legacy_v1.jsonl \
    --summary audits/evidence/public_release_v10_ecapa_reconciliation_summary_legacy_v1_2026-10-21.json

run "phase1: determinism repeat (pinned timestamp)" "$REPO" \
  "$PY" backend/scripts/ops/reconcile_v10_ecapa_verdicts.py \
    --v10-points .work/public_release/v10_points_export.json \
    --legacy-points .work/fp_context/v9_points.json \
    --verdicts .work/fp_context/speaker_verdicts.json \
    --asr-manifest .work/fp_context/asr_manifest_existing.json \
    --generated-at-utc "2026-10-21T00:00:00+00:00" \
    --out .work/public_release/reconciliation_v10_ecapa_repeat.jsonl \
    --summary .work/public_release/reconciliation_v10_ecapa_repeat.summary.json

run "phase1: ruff" "$REPO/backend" \
  "$PY" -m ruff check scripts/ops/reconcile_v10_ecapa_verdicts.py \
    scripts/ops/capture_public_release_phase0_state.py tests/test_reconcile_v10_ecapa_verdicts.py

run "phase1: repo layout" "$REPO/backend" \
  "$PY" -m pytest tests/test_repo_layout.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase1: git diff --check" "$REPO" git diff --check

echo "transcript: $TRANSCRIPT"
