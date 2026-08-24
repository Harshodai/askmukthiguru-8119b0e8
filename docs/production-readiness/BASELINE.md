# AskMukthiGuru Productionization Baseline

**Captured:** 2026-08-21. **Scope:** read-only inspection and existing repository quality gates; no application code changed before this report.

## Executive baseline

The checkout is clean on `main` at commit `35e28195`, with origin aligned and no pre-existing working-tree changes. Frontend build and unit tests pass. Frontend lint exits successfully but reports 39 warnings. The frontend bundle budget fails because core JavaScript is 3.01 MB against a strict `< 3.00 MB` budget. Backend tests run in the repository’s Python 3.12 virtual environment and report **4 failures, 2,332 passed, and 30 skipped**. A host-level Python 3.11 compile scan is not authoritative because the project requires Python 3.12 and uses PEP 695 syntax; it also traversed an incompatible vendored Python 3.9 site-packages tree.

The representative Playwright prelaunch run fails all four selected suites. The visible root cause in the captured browser output is frontend-to-backend CORS failure from `http://localhost:4173` to the configured Railway backend URL, with no `Access-Control-Allow-Origin` header. This prevents declaring browser journeys healthy. The run also generated screenshots, videos, traces, and error contexts under Playwright’s existing `test-results/` directory.

## Evidence matrix

| Area | Status | Evidence |
|---|---|---|
| Git state | **VERIFIED** | `docs/production-readiness/baseline-git.txt`; clean `main` at `35e28195`. |
| Frontend build | **VERIFIED PASS** | `npm run build` exit 0; 28 routes prerendered. |
| Frontend unit tests | **VERIFIED PASS** | `87 passed, 1 skipped` test files; `506 passed, 6 skipped` tests. Existing jsdom navigation and React lifecycle diagnostics appear in output but did not fail the suite. |
| Frontend lint | **VERIFIED PASS WITH WARNINGS** | Exit 0; 39 warnings, primarily React Fast Refresh export and hook dependency warnings. |
| Bundle budget | **VERIFIED FAIL** | Core JS `3.01 MB`; budget `< 3.00 MB`. Total JS `4.47 MB`; max chunk budget remained within reported limits. |
| Backend syntax | **VERIFIED FAIL / ENVIRONMENT-SCOPED** | Host Python 3.11 compile scan fails on project PEP 695 syntax and an incompatible `backend/venv` Python 3.9 package tree. Project declares Python `>=3.12`; use the project virtualenv for authoritative checks. |
| Backend tests | **VERIFIED FAIL** | Project Python 3.12 virtualenv: 4 failed, 2,332 passed, 30 skipped, 70 warnings in 329.52s. Failures: `test_citation_marker_remap.py::test_diversity_reorder_does_not_desync_citation_numbering`; `test_health.py::test_health_check`; `test_regex_safety_scanner.py::test_current_runtime_tree_has_no_known_evil_literals`; `test_task3.py::test_retrieval_bm25_uses_native_sparse_vector`. Jaeger export also reported unavailable. |
| Browser page smoke | **VERIFIED FAIL** | Selected prelaunch run failed; inspect preserved browser log and `test-results/`. |
| Browser accessibility | **VERIFIED FAIL / ROOT CAUSE SHARED** | Selected prelaunch run failed against configured remote backend CORS path; no clean accessibility conclusion until backend transport is isolated or corrected. |
| Auth/session browser flows | **VERIFIED FAIL / ROOT CAUSE SHARED** | Same prelaunch run failed while app attempted capability calls to Railway from localhost. |
| Safe-control sweep | **VERIFIED FAIL** | 10 route cases failed with fatal CORS console errors from `/api/capabilities`. |
| Production integrations | **NOT VERIFIED** | No destructive or credentialed production mutation performed. Google OAuth, real reset email, production audio/CDN, nightly RLS secrets, live guru-voice benchmark, and production Qdrant NDCG remain environment-dependent per repository guidance. |
| Load/performance | **NOT VERIFIED** | No safe load run yet; bundle budget is the only measured performance gate in baseline. |

## Baseline product and architecture inventory

The product is a React/Vite/Capacitor client with web `BrowserRouter` and native `HashRouter`, Supabase authentication and persistence, and a FastAPI backend. Backend composition includes Qdrant, Neo4j, Redis, Celery/background queues, LightRAG/RAG retrieval, embeddings/reranking, LLM provider gateways, safety guardrails, encrypted Second Brain storage, anonymous quota, cache layers, ingestion, telemetry, health checks, and admin APIs.

Primary P0/P1 user journeys are anonymous chat, authenticated chat, streaming chat, attachment upload and evidence handling, sign-in/OAuth/password reset, session expiry, profile and memory operations, Second Brain encryption/recovery, knowledge graph browsing, practices and Serene Mind consent, healing-course progress, and privileged admin/evaluation operations. Highest-risk trust boundaries are chat-to-provider/RAG flow, uploaded evidence, anonymous identity/quota, shared caches/coalescing, user memory and RLS, admin authorization, external credentialed clients, ingestion-to-index writes, and production configuration.

## Prioritized baseline findings

| Priority | Finding | Risk | Proposed verification |
|---|---|---|---|
| P0 | Four backend regression failures in citation remapping, health serialization, regex safety scanning, and native sparse retrieval. | Release confidence and correctness. | Run each failing test in isolation; inspect recent commits and implementation contracts; add minimal regressions. |
| P0 | Browser suites fail because local preview calls Railway backend without accepted CORS origin. | Critical user journeys and CI prelaunch gate cannot pass. | Reproduce with network capture; verify intended local backend URL/configuration and production CORS allowlist without weakening production security. |
| P0 | Core frontend bundle is 0.01 MB over strict budget. | CI/release gate failure; potentially unnecessary load cost. | Run bundle analyzer and identify largest shared chunks before changing dependencies or route splits. |
| P1 | 39 lint warnings, including hook dependency warnings. | Potential stale state/race behavior and maintainability risk. | Classify warnings by runtime impact; fix correctness-relevant warnings first, defer purely stylistic Fast Refresh splits. |
| P1 | Health test and Jaeger export failures may indicate observability contract or local dependency mismatch. | Readiness/diagnosis ambiguity. | Reproduce health failure in isolation with exact traceback; separate optional exporter outage from health response correctness. |
| P1 | Database migrations contain historical destructive statements and duplicate reconciliation patterns, even where comments or guards may make them safe. | Migration rollout/data integrity. | Review migration history and current schema; run local dry-run/validation only, no production mutation. |
| P1 | Placeholder provider path exists in frontend transport and diagnostics. | Trust risk if reachable outside development. | Trace provider selection and production defaults; ensure placeholder is explicit development-only and never silently masks backend outage in production. |
| P1 | Production readiness checklist still names unverified OAuth, reset email, audio, RLS secrets, live voice benchmark, and production NDCG tasks. | Cannot honestly mark release ready without evidence or waiver. | Verify safe staging paths or keep as explicit blockers. |
| P2 | Frontend lint warnings and broad chat component complexity. | Regression and developer velocity risk. | Use targeted ownership audit around chat state, effects, optimistic updates, and mobile sheets. |

## Baseline constraints

The project’s authoritative Python runtime is 3.12. The root host Python 3.11 must not be used to judge backend syntax. Local browser tests default to a preview server but the app’s configured backend URL points at Railway, so local E2E requires an intentional safe backend mode or a correctly configured CORS allowlist. Production Qdrant/Neo4j/Supabase/Railway state must not be inferred from Docker defaults.

## Immediate execution order

1. Reproduce and isolate the four backend failures in parallel, then fix P0 correctness issues with tests.
2. Resolve the local E2E transport/configuration problem without weakening production CORS or auth, then rerun page, accessibility, session, and safe-control suites.
3. Reduce core JS below the existing budget using measured bundle evidence.
4. Run focused security/RLS/privacy, AI/RAG, UX/mobile, and SRE/CI audits with separate file ownership.
5. Integrate changes in security/data-integrity-first order and rerun the complete release gate.

## Truth labels

**VERIFIED:** repository state, frontend build/unit/lint exit status, bundle-budget failure, backend test result, and browser CORS failure were observed from commands and captured logs. **NOT VERIFIED:** production integrations, real user email/OAuth, production retrieval quality, load capacity, backup restore rehearsal, and production deployment. **ESTIMATED:** none in this baseline report; no capacity or cost figures are asserted without measurements.
