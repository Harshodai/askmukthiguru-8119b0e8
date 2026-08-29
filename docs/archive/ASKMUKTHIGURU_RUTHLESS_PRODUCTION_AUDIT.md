
---

## Approved execution addendum: 24 clusters and final task #75

The connected-computer working tree now carries the authoritative `handoff.md` runbook. It divides the hardening pass into 24 scope-locked clusters covering secrets, builds, config, auth, abuse controls, pipeline contracts, fast/standard/deep routes, LLM resilience, coalescing, streaming, TTFT, Qdrant fusion, reranking, confidence calibration, citations, source ingestion, media adapters, quality gates, release publication, graph provenance, evaluation, and deployment operations.

The runbook deliberately reserves **task #75 as the final CRITICAL circuit-breaker cluster**. Its scope is restricted to `backend/services/circuit_breaker.py`, `backend/app/constants.py`, `backend/app/container.py`, `backend/app/metrics.py`, the actual health/operator route owner, and the smallest required test/integration surface. It will be accepted only after fake-clock, half-open concurrency, flapping/recovery, provider failover, metric, authentication, and healthy-route isolation tests pass. This sequencing prevents a circuit breaker from masking unresolved timeout, retry, queue, or observability defects.

The existing handoff’s pre-production warnings remain active. In particular, the OpenRouter key rotation, contaminated Neo4j/LightRAG rebuild, unverified staging alert, multilingual/auth/audio E2E gaps, and teacher-domain read-side enforcement must not be reported as complete without production evidence.

## Execution evidence and final disposition

The connected-computer implementation pass preserved the existing wave-11 changes, removed two tracked credential-bearing artifacts, made quality-gate and ingestion retry behavior fail-closed/typed, fixed a production-host allowlist defect, hardened task #75 circuit-breaker transitions and operator control, and added regression coverage. The final non-integration backend suite passed **1,760 tests**; the frontend suite passed **369 tests** with 6 skips; the frontend build and Docker Compose configuration both passed.

The result is **GO for internal review, conditional for controlled alpha, and NO-GO for unrestricted public production** until cloud-specific cold-start/load/memory, secret rotation/history, graph rebuild, staging alert, OAuth/audio E2E, and backup/restore evidence is complete. The full cluster contract and exact acceptance criteria remain in `handoff.md`.

## TODO backlog for completing this audit

The following backlog must be completed in addition to the 24-cluster runbook. It is duplicated in full in `handoff.md` so the audit report remains useful when read independently.

| Priority | TODO IDs | Completion gate |
|---|---|---|
| P0 | TODO-001 through TODO-006 | No exposed/active secrets, clean tenant/admin isolation, Python 3.12 release contract, teacher-domain read enforcement, and atomic release publication are proven. |
| P1 | TODO-007 through TODO-020 | Railway two-replica load/cold-start, memory/SLO, alerts, backup/restore, confidence calibration, source-held-out evaluation, full clean re-ingestion, multilingual/auth/audio E2E, distributed reset cooldown, chaos, and real TTFT are evidenced. |
| P2 | TODO-021 through TODO-026 | Open-source adoption decisions, future-tradition ontology, progressive-disclosure product features, waitlist/retention experiments, Expo decision, and clean release packaging are complete or explicitly deferred. |

The detailed owner, exact scope, acceptance criteria, and evidence requirements for every ID are in the root `handoff.md`. No finding should be reclassified as “done” based only on a local unit test when its acceptance criterion requires staging or production evidence.
