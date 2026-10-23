#!/usr/bin/env bash
# Phase 2 verification transcript for the first-person v10 public-release
# remediation (2026-10-22). Every command's real exit code is recorded.
#
# Read-only: no Qdrant write, no alias change, no env change, no deployment.
set -u
cd "$(dirname "$0")/../../.." || exit 99
REPO="$PWD"
PY="$REPO/backend/.venv/bin/python"
TRANSCRIPT="$REPO/audits/evidence/public_release_phase2_verification_2026-10-22.txt"
AUDIO_DIR="/Users/harshodaikolluru/mukthiguru_attribution_data/audio_archive/wavs"
STAMP="2026-10-22T00:00:00+00:00"
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

run "phase2: py_compile" "$REPO" \
  "$PY" -m py_compile backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py

run "phase2: focused tests" "$REPO/backend" \
  "$PY" -m pytest tests/test_regenerate_v10_span_ecapa_verdicts.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase2: --help" "$REPO" \
  "$PY" backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py --help

run "phase2: generation (shipped artifacts, pinned timestamp)" "$REPO" \
  "$PY" backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py \
    --candidate audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl \
    --quarantine audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl \
    --audio-dir "$AUDIO_DIR" \
    --cache .work/public_release/phase2_cache \
    --generated-at-utc "$STAMP" \
    --out-verdicts audits/evidence/public_release_phase2_verdicts_2026-10-22.json \
    --out-verdicts-jsonl audits/evidence/public_release_phase2_verdicts_2026-10-22.jsonl \
    --out-calibration audits/evidence/public_release_phase2_calibration_2026-10-22.json \
    --out-summary audits/evidence/public_release_phase2_summary_2026-10-22.json

run "phase2: determinism repeat (pinned timestamp)" "$REPO" \
  "$PY" backend/scripts/ops/regenerate_v10_span_ecapa_verdicts.py \
    --candidate audits/evidence/public_release_phase3_candidate_2026-10-21.jsonl \
    --quarantine audits/evidence/public_release_phase3_quarantine_2026-10-21.jsonl \
    --audio-dir "$AUDIO_DIR" \
    --cache .work/public_release/phase2_cache \
    --generated-at-utc "$STAMP" \
    --out-verdicts .work/public_release/phase2_repeat_verdicts.json \
    --out-verdicts-jsonl .work/public_release/phase2_repeat_verdicts.jsonl \
    --out-calibration .work/public_release/phase2_repeat_calibration.json \
    --out-summary .work/public_release/phase2_repeat_summary.json

run "phase2: byte-identical check" "$REPO" bash -c '
  cmp audits/evidence/public_release_phase2_verdicts_2026-10-22.json .work/public_release/phase2_repeat_verdicts.json &&
  cmp audits/evidence/public_release_phase2_verdicts_2026-10-22.jsonl .work/public_release/phase2_repeat_verdicts.jsonl &&
  cmp audits/evidence/public_release_phase2_calibration_2026-10-22.json .work/public_release/phase2_repeat_calibration.json &&
  cmp audits/evidence/public_release_phase2_summary_2026-10-22.json .work/public_release/phase2_repeat_summary.json &&
  echo "verdicts, calibration and summary are byte-identical across runs"'

run "phase2: verdict schema validation" "$REPO/backend" \
  "$PY" -m pytest tests/test_regenerate_v10_span_ecapa_verdicts.py -q -p no:cacheprovider --no-header -rf --tb=short \
    -k "shipped or schema or verdict"

run "phase2: ruff" "$REPO/backend" \
  "$PY" -m ruff check scripts/ops/regenerate_v10_span_ecapa_verdicts.py tests/test_regenerate_v10_span_ecapa_verdicts.py

run "phase2: repo layout" "$REPO/backend" \
  "$PY" -m pytest tests/test_repo_layout.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase2: git diff --check" "$REPO" git diff --check

run "phase2: phase3 regression tests" "$REPO/backend" \
  "$PY" -m pytest tests/test_rebuild_v10_asr_coordinates.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase2: reconciliation regression tests" "$REPO/backend" \
  "$PY" -m pytest tests/test_reconcile_v10_ecapa_verdicts.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase2: focused first-person suite" "$REPO/backend" \
  "$PY" -m pytest tests/test_regenerate_v10_span_ecapa_verdicts.py \
    tests/test_rebuild_v10_asr_coordinates.py tests/test_reconcile_v10_ecapa_verdicts.py \
    tests/test_first_person_context_contract.py tests/test_first_person_context_harness.py \
    tests/test_first_person_context_red_team.py tests/test_first_person_context_serving.py \
    tests/test_first_person_context_shadow_route.py tests/test_first_person_context_store.py \
    tests/test_fp_context_builder_from_v9.py tests/test_validate_fp_context_candidate.py \
    tests/test_repo_layout.py -q -p no:cacheprovider --no-header -rf --tb=short

run "phase2: full regression suite" "$REPO/backend" \
  "$PY" -m pytest tests/ -q -p no:cacheprovider --no-header -rf --tb=line

echo "transcript: $TRANSCRIPT"
