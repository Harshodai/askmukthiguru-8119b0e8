# Offline Launch-Gate Evidence — 13 August 2026

**Scope.** Railway is intentionally offline. This record captures deterministic
repository verification only; it does not represent staging, production, or
external-provider evidence. The code baseline is `be971499` plus the uncommitted
load-harness hardening recorded below.

| Gate | Offline evidence completed | Status | Live evidence still required |
|---|---|---|---|
| Source-release lifecycle | Registry tests cover disabled fallback, unavailable control store, idempotent registration, approval-before-activation, supersession, corpus isolation, and checkpoint version selection | Code verified | Apply the Supabase migration and prove registration → approval → activation → re-activation rollback against an isolated data topology |
| Redis spend guard | Atomic reservation, settlement, refund, and unavailable-store paths are covered by budget tests | Code verified | Stop or isolate Redis in staging while the guard is enabled; verify fail-closed request admission and recovery |
| Scope and crisis safety | Server-resolved assistant scope, corpus containment, Neo4j subgraph scope, and pre-retrieval crisis pre-emption regressions pass | Code verified | Run sentinel-corpus and severe/crisis canaries against the deployed Qdrant, Neo4j, cache, and SSE topology |
| Live logistics | Official-source event handling regression passes | Code verified | Verify official source freshness, event-card transport, and booking links with the deployed web-search configuration |
| Queue and coalescing | Queue lifecycle and identical-request coalescer regressions pass | Code verified | Validate cross-replica Redis streams, reconnection, and provider-call collapse under staging traffic |
| Typed evidence | Answer-evidence and privacy-safe operations snapshot regressions pass | Code verified | Capture deployed traces showing evidence metadata for REST and SSE without seeker-content exposure |
| Readiness matrix | Script syntax, evaluator threshold tests, 25→100→250→500 progression, and a non-staging remote-target rejection path pass | Harness verified | Install benchmark dependencies and run each stage against an approved isolated endpoint; retain raw Locust reports |
| Recovery | Runbook defines database, Qdrant, Neo4j, Redis, and release-config recovery checks | Not executable offline | Execute and time a restore drill; retain RTO/RPO and integrity results |
| Regional TTFT | No physical regional probe is possible with Railway offline | Not executable offline | Measure provider and API TTFT/error rates from India and representative global regions |

## Deterministic Commands and Results

| Command group | Result |
|---|---|
| Source release, checkpoint, budget, crisis, scope, logistics, queue, coalescing | `33 passed, 2 skipped` |
| Typed answer evidence, privacy-safe operations, readiness evaluator | `10 passed` |
| Full backend suite | `1710 passed, 32 skipped` |
| Frontend suite and production build | `361 passed, 6 skipped`; production build and 17-route prerender passed |
| Readiness runner shell syntax and production-target rejection | Passed; remote target without `READINESS_TARGET=staging` exits before Locust runs |
| Load harness prerequisites | `locust` was absent from the canonical development environment; it is now declared in `backend/requirements-dev.txt` and the nightly workflow installs that file |

## Load-Test Invocation After Staging Exists

Set the remote endpoint deliberately; the runner rejects arbitrary remote hosts.

```bash
cd backend
pip install -r requirements-dev.txt
export LOAD_TEST_URL=https://<approved-staging-host>
export READINESS_TARGET=staging
export READINESS_STAGING_HOST=<approved-staging-host>
export BENCHMARK_SECRET=<staging-only-secret>
./benchmarks/run_readiness_matrix.sh
```

Retain the four JSON reports, deployment SHA, active model policy, active corpus
release, environment, dependency topology, region, and the replica count. A
passing local mock-provider run validates control-flow only; it is not evidence
of OpenRouter capacity, physical data-store rollback, or regional latency.
