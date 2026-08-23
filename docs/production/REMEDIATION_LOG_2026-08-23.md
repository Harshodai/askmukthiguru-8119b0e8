# Production Remediation Log — 2026-08-23

This log records direct-to-`main` remediation work from the current production audit. It intentionally does not close an issue merely because source code changed; closure still requires the repository's evidence rule: changed file/configuration, exact validation command/action, result, production evidence where applicable, and independent verification.

## Execution policy

- Changes are committed directly to `main`.
- No pull requests are created by this remediation campaign.
- No corpus, user data, Redis global state, Neo4j schema, or production database state is mutated by repository-only changes.
- Missing curated artifacts are **not** replaced with empty placeholders.
- Local dependency-limited validation is not represented as a successful full test suite.

## Completed repository changes

### CI-001 — Main hard gates

Added `.github/workflows/main-hard-gates.yml` with explicit gates for:

- frontend lint
- TypeScript typecheck
- frontend unit tests
- production build
- high-severity production dependency audit
- Python compilation
- repository diff hygiene
- security audit
- required repository source contracts
- nightly-load evidence-policy verification

### CI-002 — Nightly load evidence must fail closed

Updated `.github/workflows/nightly-load.yml` so an unreachable benchmark endpoint emits `NO_BACKEND_EVIDENCE` and fails unless the workflow is manually dispatched with the diagnostic-only `allow_unreachable_success` override.

Additional hardening:

- load sweeps run only after a proven reachable backend;
- zero-request runs fail;
- concurrency-20 hard failures fail;
- concurrency-50 hard failures fail;
- load report artifacts are required when the load phase runs.

### OPS-ART-001 — Runtime artifact inspection

Added `backend/app/runtime_artifacts.py` and `backend/tests/test_runtime_artifacts.py`.

The verifier reports only safe metadata:

- artifact name
- presence
- size
- required flag
- aggregate missing list

It does not read or expose corpus contents.

The currently known missing curated assets remain intentionally unresolved until the approved artifact-generation/reingestion process produces real, audited assets.

## Still open — not falsely marked complete

- COST-001 — Railway cost/memory ceiling
- QUAL-001 — held-out source-faithfulness and citation benchmark
- MEM-001 — reproducible runtime model/artifact packaging and memory attribution
- DATA-001 — curated OKF/doctrine artifact packaging
- PERF-001 — p95/p99 and first-use latency isolation
- GRAPH-001 — graph-on/off quality/cost A/B
- E2E-001 — broader browser/mobile/authenticated isolation evidence
- OPS-001 — independent rollback and restore drill

## Verification policy

A green repository workflow is not equivalent to production proof. Production-facing issues are closed only after independent runtime evidence is attached to the production issue register.
