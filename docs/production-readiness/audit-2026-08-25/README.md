# AskMukthiGuru Productionization Pack — 2026-08-25

This dated pack records the closed-loop productionization exercise for the AskMukthiGuru repository. It is intentionally separate from the pre-existing `docs/production-readiness/` audit artifacts. The work covered source mapping, executable validation, adversarial tests, security-gate correction, benchmark hardening, public-route fixes, local measurement, and a final evidence review.

> **Current verdict: RED / NOT READY for an unrestricted production release.**

The code gates are materially healthier than the release state. The decisive blockers are not a failing unit suite; they are missing proof and observed operational readiness failures: the local service reports `ready=false` because the critical `okf_compiled` runtime artifact is missing, the configured Qdrant evaluation corpus does not match the golden labels so real retrieval quality is unproven, the browser E2E run stalled without output, and provider-backed Redis/Neo4j/Supabase/model integration coverage remains skipped in this environment.

Documents marked **canonical** live at the `docs/` root and are the single source of
truth for their topic. The copies that used to sit in this directory were removed
2026-10-22 as byte-identical duplicates; this pack keeps only the documents that
are unique to the 2026-08-25 exercise.

| Document | Purpose |
|---|---|
| [System map](../../system-map.md) (canonical) | Components, data flows, state boundaries, and dependencies. |
| [Architecture](../../ARCHITECTURE.md) (canonical) | Runtime architecture and trust boundaries. |
| [Production readiness](production-readiness.md) | Release scorecard and explicit blockers. |
| [Scalability](../../scalability.md) (canonical) | Measured local behavior and limits of inference. |
| [Observability](observability.md) | Health, telemetry, alerts, and evidence gaps. |
| [Security](../../security.md) (canonical) | Security controls, scans, and residual risks. |
| [Reliability](../../reliability.md) (canonical) | Failure handling, queue behavior, recovery, and gaps. |
| [Performance](performance.md) | Benchmark methodology, measured values, and interpretation. |
| [Testing strategy](../../testing-strategy.md) (canonical) | Test inventory, executed suites, skips, and E2E status. |
| [Disaster recovery](../../disaster-recovery.md) (canonical) | Backup/restore expectations and unproven paths. |
| [Deployment](../../DEPLOYMENT.md) (canonical) | Read-only deployment assessment and promotion gates. |
| [Runbook](../../runbook.md) (canonical) | Safe operator procedures and bounded triage. |
| [Feature gaps](../../feature-gap-analysis.md) (canonical) | Product and operational capability gaps by priority. |
| [Cost analysis](cost-analysis.md) | Cost drivers and measurement limitations. |
| [Known limitations](../../known-limitations.md) (canonical) | Evidence boundaries that must not be overstated. |
| [Audit findings](audit-findings.md) | Master findings register with status and verification. |
| [Verification results](verification-results.md) | Reproducible commands and observed outcomes. |

No deployment, push, external infrastructure mutation, secret operation, or destructive user-data action was performed. The persistent execution log is maintained outside the checkout at `/home/ubuntu/askmukthiguru_audit_evidence/execution_results.md`.
