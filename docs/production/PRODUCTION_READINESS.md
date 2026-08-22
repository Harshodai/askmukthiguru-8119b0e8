# AskMukthiGuru Production Readiness Matrix

**Assessment date:** 2026-08-22  
**Current repository head:** `8c9662d`  
**Current backend/worker deployment:** `3980b6ec-2080-4a78-94f8-776cca43d379` / `fd44c8ff-6363-42a7-8bac-3a5c32642ecb`

## Verdict

# NOT READY FOR PRODUCTION

This verdict follows the attached Master Mission’s strict rule: unresolved P0 quality and cost risks cannot be hidden by a high aggregate score. The application is serving controlled traffic and has healthy dependencies, but broad public scaling is not justified while the Railway hard limit is nearly exhausted, the stillness grounded-answer gap remains open, long-tail concurrent latency is unexplained, and complete browser/recovery evidence is incomplete.

## Matrix

| Category | Requirement | Status | Evidence | Test / verification | Owner | Remaining risk |
|---|---|---|---|---|---|---|
| Core chat | Grounded answers for representative queries | PARTIAL | Hindi/Telugu smoke grounded at faithfulness `0.80`; stillness now renders a bounded non-doctrinal fallback in backend, while the Lovable browser capture remains limited-support/0 sources | Live smoke plus browser capture and prior benchmark artifacts | Backend + QA | Core topic still lacks a proven authoritative grounded answer |
| Safety | Distress requests receive safe redirect | VERIFIED FOR SMOKE | Post-deploy distress smoke returned `blocked=true`, `grounding_state=safety_redirect` | Signed anonymous-session production smoke | Security + QA | Full multilingual/adversarial matrix remains open |
| Cost | Current and forecast spend remain within controlled envelope | FAIL | Railway `$29.3763` current usage vs `$30` hard limit; forecast `$54.7602`; memory `94.2%` | Railway usage and service metrics | FinOps + Performance | Broad traffic can exhaust limit |
| Provider accounting | Actual, estimated, and unknown AI costs are separated | VERIFIED | Commit `34c98a5` adds model-aware fallback and bounded Prometheus counters | Static compilation; deployed health/smoke | FinOps + Backend | Authenticated metrics aggregation still needs live proof |
| Memory | Backend resident memory is attributed and optimized | NOT VERIFIED | Backend average `6,767.6 MB`, maximum `13,634.7 MB` in latest 30-minute window | Railway metrics only; no phase-by-phase attribution | Performance + DevOps | Root cause and safe savings unknown |
| Retrieval | Ranking and citation correctness hold across protected classes | PARTIAL | Neo4j plans and health verified; full held-out graph/RRF/ONNX A/B incomplete | Read-only Neo4j audit; partial live smoke | Database + QA | Retrieval drift or false refusals possible |
| Graph | Parallel graph work improves useful cost/latency | NOT VERIFIED | Source topology bounded; no valid graph-on/off held-out comparison | Static/source inspection only | Architecture + Performance | More work may be billed without throughput gain |
| Database | Constraints/indexes and mutations are safe | VERIFIED / MUTATION BLOCKED | Three remote uniqueness constraints ONLINE and populated; mutation script lacks lock/snapshot/rollback | Remote read-only SHOW and EXPLAIN evidence | Database | Future mutation remains unsafe until runbook exists |
| Browser UX | Critical journeys pass in real browser at required breakpoints | PARTIAL | Lovable homepage/chat routes load; harmless chat submission completes with visible actions, but the captured stillness turn rendered limited support/0 sources before the new SSE final-event fix; authenticated, tablet, mobile, and custom-domain evidence remain incomplete | Real-browser public route/chat capture plus direct production SSE contract smoke; full browser/E2E run and Lovable republish verification still required | UX + QA | The repository now emits and consumes an authoritative final answer, but the Lovable-hosted bundle has not been independently proven to contain the new parser |
| Authentication | Auth, authorization, AAL2, and tenant isolation are independently verified live | PARTIAL | Repository tests and prior RLS evidence exist; fresh independent live red-team pass incomplete | CI/test-image plus live user A/B probes required | Security + Privacy | BOLA/IDOR regression not freshly re-proven |
| Uploads | Bounded multimodal extraction is safe and understandable | PARTIAL | Size/semaphore/SSRF code exists; complete browser and failure matrix incomplete | Upload E2E and malicious-file tests required | Backend + Red Team | Expensive or malformed uploads may stress service |
| Observability | Failures, cost spikes, and token anomalies are diagnosable | PARTIAL | Health, Prometheus metrics, logs, new provider counters, and direct SSE trace evidence exist; `/api/metrics` remains protected and was not authenticated in this pass | Static, health, startup-log, and direct SSE evidence; authenticated counter visibility open | SRE + Observability | Dashboards/alerts may not be operationally proven |
| SLOs | Latency, availability, queue, and useful-answer SLOs have error budgets | PARTIAL | Policies and runbooks exist; stable held-out p95/p99 and useful-answer SLO not closed | Multi-run load and route-level telemetry required | SRE + Performance | Tail latency remains unexplained |
| Backups | Important data can be restored | PARTIAL | Backup and restore runbook exists | Non-destructive restore proof remains open | DevOps + Data | Recovery may fail under incident pressure |
| Deployment | Reproducible and rollback-aware release | VERIFIED FOR DEPLOYMENT | Clean archive deployed to backend/worker; both target deployments reached `SUCCESS`; correct Railway service domain returned `/api/healthz=200` and `/api/health` healthy | Railway deployment IDs and live health checks | DevOps | Rollback drill not fully executed |
| Data integrity | Corpus and user memory boundaries are preserved | PARTIAL | No corpus files changed; memory privacy invariants documented | Static corpus guard and prior vault evidence | Data + Privacy | Full second audit and restore proof open |

## Scoring rule

No numerical score overrides the verdict. A future score must report the numerator, denominator, source, window, and evidence class for every category. Any unresolved P0, uncontrolled cost risk, critical user-journey failure, data-loss risk, or severe security issue automatically produces **NOT READY FOR PRODUCTION**.

## Closure requirements

The final verdict may change only after the shared issue register is updated with independent verification for `COST-001`, `QUAL-001`, `PERF-001`, `MEM-001`, `DATA-001`, `E2E-001`, and `OPS-001`. The required proof includes a staging/blue-green memory experiment, a held-out graph/retrieval matrix, real-browser critical journeys, adversarial authorization and cost-abuse testing, authenticated telemetry validation, and a non-destructive backup/restore drill.
