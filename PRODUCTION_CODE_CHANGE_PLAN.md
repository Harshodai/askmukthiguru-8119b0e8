
---

## Scope-locked 24-cluster execution contract

Implementation now follows the 24-cluster runbook in the repository-root `handoff.md`. Each cluster is restricted to the exact files listed there, requires acceptance tests and saved evidence, and may not introduce opportunistic changes outside scope. The order is security/configuration → request/retrieval/TTFT → ingestion/release/graph → evaluation/deployment.

### Final CRITICAL task #75 — circuit breaker

Task #75 is intentionally last. Scope is restricted to `backend/services/circuit_breaker.py`, `backend/app/constants.py`, `backend/app/container.py`, `backend/app/metrics.py`, the actual health/operator route owner, the circuit-breaker tests, and the minimum necessary integration/load test. The implementation must test monotonic clocks, state transitions, concurrent half-open admission, failure classification, timeout semantics, provider-specific policy, metrics, multi-worker behavior, authenticated reset, and healthy-route isolation. It is not complete if it merely opens after a threshold; it must prove recovery without flapping and safe degradation under provider failure.

### Documentation acceptance

The audit report, this code-change plan, and `handoff.md` must agree on the cluster names, file allow-lists, acceptance criteria, task #75 ordering, and no-go conditions. Existing pre-production warnings in `handoff.md` remain authoritative until verified in the real deployment environment.

## Actual implementation evidence

The connected-computer pass implemented the scoped quality-gate fail-closed behavior, typed ingestion retries, frontend production-host fail-closed correction, task #75 circuit-breaker hardening, and task #75 tests. The full backend non-integration suite is green at **1,760 passed**, the frontend suite is green at **369 passed / 6 skipped**, the frontend build is green, and the compose manifest renders successfully. Remaining work is explicitly operational: production secret rotation/history review, Railway staging load and cold-start, memory/SLO alerting, graph rebuild, OAuth/audio verification, global multi-replica operator-reset rate limiting, and backup/restore drills.

## TODO backlog and completion contract

The implementation plan is not complete until the following unresolved items are closed. The full TODO registry is in `handoff.md`; this file keeps the priority and engineering closure contract visible beside the code plan.

| Priority | TODO IDs | Engineering requirement |
|---|---|---|
| P0 | TODO-001–TODO-006 | Close secret rotation/history, graph contamination, teacher-domain read enforcement, atomic candidate release, Python 3.12 reproducibility, and real RLS/admin isolation before public traffic. |
| P1 | TODO-007–TODO-020 | Prove cloud cold-start/load/RSS/SLO/alerts/restore, calibrate confidence, expand source-held-out evaluation, complete clean corpus rebuild, remove dead config, finish E2E, distributed reset locking, chaos, and real TTFT. |
| P2 | TODO-021–TODO-026 | Benchmark open-source additions, formalize future-tradition ontology, ship progressive-disclosure/retention features, decide Expo, and perform a clean release review. |

Every TODO must produce a code diff or an explicit decision record, a regression or staging test where applicable, an evidence file, and a rollback note. `handoff.md` is the status authority; this plan is the engineering execution authority.
