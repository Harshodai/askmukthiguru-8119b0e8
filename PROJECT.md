# Project: Graded-8 Answer Failure Remediation & Graded-9 Execution

## Architecture
- **Evaluation Judge**: Dual-grader LLM assessment (`anthropic/claude-sonnet-5.5` + `google/gemini-3.6-flash`) in `backend/scripts/ops/grade_served_answers.py` and `scripts/ops/grade_served_answers.py`.
- **Content Quality & Event Gate**: Deterministic regex filter `EVENT_MARKER_RE` in `backend/services/first_person_content_assessment.py`, enforced across `first_person_evidence_policy.py`, `first_person_pipeline.py`, `first_person_context_harness.py`, and `first_person_safety_policy.py`.
- **Evaluation Runner & Replay**: `backend/scripts/ops/graded_capture.py`, `backend/scripts/ops/grade_served_answers.py`, `backend/scripts/ops/graded_registered_report.py`, `scripts/ops/collection_fingerprint.py`, and new `scripts/ops/run_offline_replay.py`.
- **Ingestion Pipeline**: Video transcript segmentation, chunking grammar (`boundary_v1`, `boundary_v2:rhetorical`), and dry-run validation in `scripts/ops/dry_run_resegmentation.py`.

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Stricter Judge Rubric (R1) | Enforce specific question directness and complete closure of thoughts/analogies/lists | M1 | Survey (explorer_survey_2) |
| 2 | Deterministic Promotional & Event Filter (R2) | Extend `EVENT_MARKER_RE` to deterministically reject upcoming-program and promotional phrases | M1 | Survey (explorer_survey_2) |
| 3 | Resilient Grader Parsing (R3) | Add retry logic on unparseable grader output with increased token allowance | M1 | Survey (explorer_survey_2) |
| 4 | Offline Replay Validation (R4) | Deterministic re-scoring (no LLM) of 40 served + 116 negative controls with patterns written from the graded-8 failures; 9 rows rejected, 31 kept. Not a judge-rubric measurement | M2 | Survey (explorer_survey_1) |
| 5 | Ingestion Re-segmentation Strategy & Dry-Run (R6) | Design + dry-run rhetorical re-segmentation. Hand-selected windows; measured 2026-11-15: 1 of 3 windows closes. Grammar unimplemented, nothing re-ingested | M3 | Survey (explorer_survey_3) |
| 6 | Registered Graded-9 Execution (R5) | Pre-flight check, spend check, capture, fingerprinting, grading, and registered report | M4 | Survey (explorer_survey_1) |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| M1 | Gate & Harness Enhancements | Implement R1 rubric, R2 event filter, R3 parser retry, pass unit & regression tests | None | DONE |
| M2 | Offline Replay Validation | Build & execute `run_offline_replay.py` on 40 served + 116 controls; verify elimination of 9 flawed rows & Bar 8 resolution | M1 | DONE (deterministic patterns, not an LLM judge run; PASS is by construction — see lessons L-RUBRIC-RECITED-IS-NOT-MEASURED-1) |
| M3 | Ingestion Re-segmentation Exploration | Build & execute `dry_run_resegmentation.py` on failure videos; verify complete discourse closure | M1 | DONE — measured 1/3 windows close (q010); q019/q074 still truncate (L-WINDOW-DEFAULTED-CLOSURE-1) |
| M4 | Registered Graded-9 Execution | Preflight 7/7 PASS, capture 202 rows, fingerprint stamped, report generated, spend logged | M2, M3 | DONE |

## Interface Contracts
### Gate & Harness ↔ Replay & Runner
- `RUBRIC` in `backend/scripts/ops/grade_served_answers.py` and `scripts/ops/grade_served_answers.py` must stay byte-identical.
- `EVENT_MARKER_RE` in `backend/services/first_person_content_assessment.py` must be imported and callable via `assess_content(body)`.
- `ask_and_parse_with_retry` must return `dict[str, Any]` matching the `Grade` schema (`{"verdict": str, "harmful": bool, "reason": str}`).
- `run_offline_replay.py` must accept rows from `20261114-graded-8/rows.jsonl` and `negative_controls.jsonl` and output clean summary tables and exit 0 only when all 9 flawed rows are rejected, ~28-30 valid rows pass, and negative controls achieve >= 95% abstention.

## Code Layout
- `backend/scripts/ops/grade_served_answers.py` (and repo-root duplicate `scripts/ops/grade_served_answers.py`): Judge rubric and retry logic.
- `backend/services/first_person_content_assessment.py`: Canonical `EVENT_MARKER_RE` regex.
- `scripts/ops/run_offline_replay.py`: Offline replay harness.
- `scripts/ops/dry_run_resegmentation.py`: Ingestion re-segmentation dry-run harness.
- `docs/runbooks/GRADED_9_PRE_REGISTERED_CRITERIA.md`: the only graded-9 pre-registration page (no `GRADED_9_RUNBOOK.md` exists; an earlier line here named one).
