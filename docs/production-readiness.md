# Production Readiness Scorecard

> **Verdict: RED / NOT READY for unrestricted production release.**

The code gates are healthy, but release readiness is blocked by missing runtime proof. The local `/api/health` contract reports `ready=false` because critical `okf_compiled` is missing; the Qdrant evaluation corpus does not match the golden labels; browser E2E stalled; external integration suites are skipped; and no restore drill or capacity/cost baseline is evidenced.

| Area | Status | Evidence |
|---|---|---|
| Build/static gates | Green | Frontend tests/lint/typecheck/build/bundle, Ruff, Bandit, regex, compile, and canonical loop pass. |
| Backend regressions | Yellow | 2,390 passed, 30 skipped, 1 warning; skipped external services remain material. |
| Retrieval quality | Red | Four cases skip due to unavailable/mismatched labels; strict quality is unproven. |
| Runtime readiness | Red | HTTP 200 payload contains `ready=false`, critical missing `okf_compiled`. |
| Browser/mobile journeys | Red/Yellow | Browser E2E stalled; mobile parity not live-verified. |
| Security/isolation | Yellow | Focused 62-test suite passes; live RLS/provider verification absent. |
| Recovery/DR | Red | No measured restore/RPO/RTO evidence. |
| Scalability/cost | Red | Local probes were 429/readiness limited; no 10x/100x baseline. |

Green requires a matching rights-approved eval corpus, all critical artifacts, complete deterministic browser and mobile journeys, disposable live integrations, a restore drill with RPO/RTO, and a clean capacity/cost experiment.
