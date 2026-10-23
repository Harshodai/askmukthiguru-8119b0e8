#!/usr/bin/env bash
# Phase 3 verification transcript for the first-person v10 public-release
# remediation (2026-10-21). Every command's real exit code is recorded.
#
# Read-only: no Qdrant write, no alias change, no env change, no deployment.
set -u
cd "$(dirname "$0")/../../.." || exit 99
REPO="$PWD"
PY="$REPO/backend/.venv/bin/python"
TRANSCRIPT="$REPO/audits/evidence/public_release_phase3_verification_2026-10-21.txt"
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

run "phase3: py_compile" "$REPO" \
  "$PY" -m py_compile backend/scripts/ops/rebuild_v10_asr_coordinates.py

run "phase3: focused tests" "$REPO/backend" \
  "$PY" -m pytest tests/test_rebuild_v10_asr_coordinates.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase3: --help" "$REPO" \
  "$PY" backend/scripts/ops/rebuild_v10_asr_coordinates.py --help

run "phase3: rebuild (exact policy, default)" "$REPO" \
  "$PY" backend/scripts/ops/rebuild_v10_asr_coordinates.py \
    --v10-points .work/public_release/v10_points_export.json \
    --attr-root /Users/harshodaikolluru/mukthiguru_attribution_data \
    --out .work/public_release/phase3_candidate.jsonl \
    --parents .work/public_release/phase3_parents.jsonl \
    --quarantine .work/public_release/phase3_quarantine.jsonl \
    --variants .work/public_release/phase3_variants.jsonl \
    --summary audits/evidence/public_release_phase3_summary_2026-10-21.json

run "phase3: rebuild (coverage policy, comparability)" "$REPO" \
  "$PY" backend/scripts/ops/rebuild_v10_asr_coordinates.py \
    --v10-points .work/public_release/v10_points_export.json \
    --attr-root /Users/harshodaikolluru/mukthiguru_attribution_data \
    --reconstruction-policy coverage \
    --out .work/public_release/phase3_candidate_coverage.jsonl \
    --parents .work/public_release/phase3_parents_coverage.jsonl \
    --quarantine .work/public_release/phase3_quarantine_coverage.jsonl \
    --variants .work/public_release/phase3_variants_coverage.jsonl \
    --summary audits/evidence/public_release_phase3_summary_coverage_2026-10-21.json

run "phase3: determinism repeat (pinned timestamp)" "$REPO" \
  "$PY" backend/scripts/ops/rebuild_v10_asr_coordinates.py \
    --v10-points .work/public_release/v10_points_export.json \
    --attr-root /Users/harshodaikolluru/mukthiguru_attribution_data \
    --generated-at-utc "2026-10-21T00:00:00+00:00" \
    --out .work/public_release/phase3_candidate_rep.jsonl \
    --parents .work/public_release/phase3_parents_rep.jsonl \
    --quarantine .work/public_release/phase3_quarantine_rep.jsonl \
    --variants .work/public_release/phase3_variants_rep.jsonl \
    --summary .work/public_release/phase3_summary_rep.json

run "phase3: byte-identical check" "$REPO" bash -c '
  cmp .work/public_release/phase3_candidate.jsonl .work/public_release/phase3_candidate_rep.jsonl &&
  cmp .work/public_release/phase3_quarantine.jsonl .work/public_release/phase3_quarantine_rep.jsonl &&
  cmp .work/public_release/phase3_parents.jsonl .work/public_release/phase3_parents_rep.jsonl &&
  cmp .work/public_release/phase3_variants.jsonl .work/public_release/phase3_variants_rep.jsonl &&
  echo "candidate, quarantine, parents and variants are byte-identical across runs"'

run "phase3: ruff" "$REPO/backend" \
  "$PY" -m ruff check scripts/ops/rebuild_v10_asr_coordinates.py tests/test_rebuild_v10_asr_coordinates.py

run "phase3: repo layout" "$REPO/backend" \
  "$PY" -m pytest tests/test_repo_layout.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase3: git diff --check" "$REPO" git diff --check

run "phase3: focused first-person suite" "$REPO/backend" \
  "$PY" -m pytest tests/test_rebuild_v10_asr_coordinates.py tests/test_reconcile_v10_ecapa_verdicts.py \
    tests/test_first_person_context_contract.py tests/test_first_person_context_harness.py \
    tests/test_first_person_context_red_team.py tests/test_first_person_context_serving.py \
    tests/test_first_person_context_shadow_route.py tests/test_first_person_context_store.py \
    tests/test_fp_context_builder_from_v9.py tests/test_validate_fp_context_candidate.py \
    tests/test_repo_layout.py -q -p no:cacheprovider --no-header -rf --tb=short

echo "transcript: $TRANSCRIPT"
