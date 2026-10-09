# AskMukthiGuru First-Person Production-Hardening Handoff

**Date:** 2026-09-28  
**Repository:** `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`  
**Scope:** first-person verbatim route from ingestion/index release through serving, evaluation, operations, and multi-guru scale.

## Executive status

**Production verdict remains NO-GO.** The route is materially safer than the original state, but it still lacks the human-gold evidence, corpus coverage, provenance completeness, tenant-isolation proof, alias promotion, restore/load evidence, and signed G1–G6 gates required for a world-class production release.

The first implementation increment is complete: production first-person startup now fails closed when the public route is enabled without retrieval-only mode, rights enforcement, a valid matching calibration profile, or concrete release provenance. No Qdrant collection, alias, graph, or other persistent data was written by this increment.

## Verified in this session

- Reconciled the current first-person handoff, state reconciliation, experiment ledger, production checklist, baseline prompt, non-negotiables, and human-gate definitions.
- Appended deeper findings to the main wide audit and all five lane memos.
- Confirmed v5 cannot support a 99% claim yet: confidence is raw dense cosine while ranking is hybrid RRF; coverage is incomplete; per-clip ASR/model lineage is missing; and the calibration label does not yet certify teacher, boundary, transcript, rights, and timestamp correctness together.
- **VERIFIED:** focused first-person suite: **85 passed in 160.14 seconds** across release, pipeline, store, and route tests.
- **VERIFIED:** touched Python files compile; `git diff --check` passes; audit and plan files exist.
- **VERIFIED PARTIAL:** full backend suite reached **3,232 passed, 3 skipped, 2 deselected**, then failed at `backend/tests/test_metrics_reachability.py::test_declared_collectors_have_callsites` because it was run from the repository root and the test tried to read `app/metrics.py` instead of `backend/app/metrics.py`. This is a test working-directory/path failure, not a first-person failure; rerun from `backend/` to obtain a clean full-suite result.

## Code shipped in this increment

- Added `backend/services/first_person_release.py` with deterministic fail-closed production validation.
- Wired it into `backend/app/main.py` after release-manifest validation and before normal serving readiness.
- Added `backend/tests/test_first_person_release.py` for disabled route, valid contract, unsafe mode, unregistered serving, missing/mismatched profile, and unknown provenance.
- No Qdrant, alias, graph, cache, or corpus write was performed.

## Documents

- Main audit: `audit_work/FIRST_PERSON_V5_WIDE_ARCHITECTURE_AUDIT.md`
- Ingestion lane: `audit_work/wide-review-02.md`
- Serving lane: `audit_work/wide-review-03.md`
- Operations lane: `audit_work/wide-review-04.md`
- Benchmark lane: `audit_work/wide-review-05.md`
- Merged plan: `.claude/tasks/first-person-prod-hardening-2026-09-28.md`
- This handoff.

## Next priorities

1. Rerun the full backend suite from `backend/` and fix only genuine regressions.
2. Add an approved stable `first_person_live` alias promotion/rollback path using the existing atomic alias utility; keep immutable build collections.
3. Add readiness checks for active collection/alias, build manifest, schema, payload completeness, calibration/build match, and rights eligibility.
4. Enforce `guru_id`/`corpus_id`/policy filters and cache namespaces to prove multi-guru isolation.
5. Wire the shared verbatim ingestion pipeline and persist ASR disputes, speaker verification, rights, model/runtime hashes, and immutable build IDs.
6. Extend the nightly data-quality audit to first-person and reconcile the canonical 745-video inventory.
7. Build human-authored, video-disjoint gold data with blind review/adjudication; calibrate on the actual promise, not passage overlap alone.
8. Replace dense-cosine-only confidence with a calibrated feature set including reranker, dense/sparse scores, margin, language, clip length, and integrity evidence.
9. Run load/failure-injection and backup/restore drills, then complete human G1–G6 safety, rights, privacy, cost, pilot, and scale gates.

## Resume commands

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
cd backend && .venv/bin/pytest -q tests --disable-warnings --maxfail=1
cd ..
backend/.venv/bin/pytest -q backend/tests/test_first_person_release.py backend/tests/test_first_person_pipeline.py backend/tests/test_first_person_store.py backend/tests/test_first_person_route.py
git status --short
git diff --check
curl -fsS http://localhost:8000/api/health || true
curl -fsS http://localhost:6333/aliases || true
```

**Boundary:** this handoff does not claim production readiness; it records a safe, tested startup gate and the evidence-backed work remaining for scale and benchmark credibility.
