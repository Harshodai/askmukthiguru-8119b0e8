# AskMukthiGuru Production Evidence Pack

This directory is the stable entry point for the Master Mission productionization program. It links to existing detailed engineering documents rather than creating duplicate prose. Every status is evidence-scoped and must distinguish verified, partially verified, blocked, not verified, estimated, and target states.

| Area | Current artifact | Evidence source | Current state |
|---|---|---|---|
| Shared issues | [`../../PRODUCTION_ISSUES.md`](../../PRODUCTION_ISSUES.md) | Current issue register | Active; blockers and owners recorded |
| Architecture | [`../architecture/README.md`](../architecture/README.md), [`../engineering-notes/subsystem-inventory.md`](../engineering-notes/subsystem-inventory.md) | Repository architecture docs | Partially verified against current runtime |
| Product and journeys | [`../../PRE_LAUNCH_CHECKLIST_PLAN.md`](../../PRE_LAUNCH_CHECKLIST_PLAN.md), [`../operations/product-hardening-backlog.md`](../operations/product-hardening-backlog.md) | Existing checklist and backlog | Mixed historical/current; revalidation required |
| Security and privacy | [`../INCIDENT_RESPONSE.md`](../INCIDENT_RESPONSE.md), [`../runbooks/PRIVACY.md`](../runbooks/PRIVACY.md), [`../SECURITY_CHECKLIST.md`](../SECURITY_CHECKLIST.md) | Security and privacy runbooks | Partially verified; live authenticated red-team evidence remains incomplete |
| Performance | [`../LATENCY_EVIDENCE_GATES.md`](../LATENCY_EVIDENCE_GATES.md), [`../runbooks/CAPACITY.md`](../runbooks/CAPACITY.md), [`railway_postflush_latency_evidence_2026-08-22.md`](railway_postflush_latency_evidence_2026-08-22.md), [`railway_hindi_repeat_timing_2026-08-22.md`](railway_hindi_repeat_timing_2026-08-22.md) | Held-out benchmark policy, Railway probes, and stage logs | Warm samples improved; long-tail latency remains open |
| Observability and SLOs | [`../operations/runtime-observability.md`](../operations/runtime-observability.md), [`../runbooks/ALERTING.md`](../runbooks/ALERTING.md) | Metrics and alerting docs | Metrics exist; live cost counters require authenticated metrics access |
| Cost and FinOps | [`../COST_EFFECTIVENESS_AUDIT_2026-08-22.md`](../COST_EFFECTIVENESS_AUDIT_2026-08-22.md) | Railway usage, resource metrics, provider accounting | Memory-dominated and near hard limit |
| Deployment and rollback | [`../operations/production-deployment-runbook.md`](../operations/production-deployment-runbook.md), [`../runbooks/MIGRATION_ROLLBACK.md`](../runbooks/MIGRATION_ROLLBACK.md), [`railway_stage_timing_health_browser_2026-08-22.md`](railway_stage_timing_health_browser_2026-08-22.md) | Clean archive deployment, rollback deployment, and browser/SSH health checks | Rollback verified; edge propagation observations remain |
| Backup and recovery | [`../runbooks/BACKUP_RESTORE_DRILL.md`](../runbooks/BACKUP_RESTORE_DRILL.md) | Backup/restore runbook | Restore proof remains open |
| Current readiness | [`PRODUCTION_READINESS.md`](PRODUCTION_READINESS.md) | This release matrix | **NOT READY FOR PRODUCTION** under the attached mission’s strict gate |
| Cache maintenance | [`railway_postflush_latency_evidence_2026-08-22.md`](railway_postflush_latency_evidence_2026-08-22.md) | Targeted Railway flusher and protected-namespace verifier | Completed without global Redis flush or user-memory mutation |
| Failed experiment and recovery | [`../../PRODUCTION_ISSUES.md`](../../PRODUCTION_ISSUES.md) | Reranker-prefetch build/runtime failure and rollback | Experiment reverted; reranker packaging remains gated |

## Operating rule

No document in this directory may convert a source inspection, a theoretical optimization, or a healthy dependency probe into a production-readiness claim. Current live evidence takes precedence over dated reports, and a P0, uncontrolled cost risk, critical journey failure, data-loss risk, or unresolved security breach keeps the final verdict at **NOT READY FOR PRODUCTION**.
