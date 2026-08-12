# Production Deployment Runbook

This runbook applies to the current production-hardening release. Automated checks are necessary but do not replace the non-production evidence required by the [release evidence pack](./release-evidence-pack.md) and [hardening backlog](./product-hardening-backlog.md).

## Pre-deployment configuration

Set all credentials only in the hosting platform. Do not store them in Git, build logs, screenshots, or support tickets. Railway requires the existing application secrets plus an explicit non-wildcard `FORWARDED_ALLOW_IPS` value appropriate for the proxy boundary.

| Control | Initial production value | Enable only after |
|---|---|---|
| `FEATURE_MEMORY_WRITE` | `false` | Consent, idempotency, deletion, and cross-store erasure evidence. |
| `VITE_MEMORY_EXTRACTION_ENABLED` | Omit or `false` | A reviewed single-memory-plane design and scoped RLS evidence. |
| `USE_REQUEST_QUEUE` | `false` | Two-replica claim, acknowledgement, recovery, cancellation, and provider-idempotency evidence. |
| `WEB_SEARCH_ENABLED` | `false` | Staging verification of official event and booking sources, freshness, and citations. |
| `WEB_SEARCH_ALLOW_DB_DOMAIN_OVERRIDE` | `false` | A reviewed break-glass change with an approved official-domain list. |
| `WHATSAPP_WEBHOOK_ENABLED` | `false` | Completion of the dedicated WhatsApp release gate. |

Deploy one web worker per Railway replica initially. The local embedding and reranking assets are process-resident; scale horizontally only after staging load evidence verifies memory, Redis, Qdrant, Neo4j, and LLM-provider headroom. Railway uses `python start_railway.py` and probes `/api/healthz` with a 60-second timeout.

## Deployment procedure

| Step | Action | Expected result |
|---|---|---|
| 1 | Confirm the release commit is clean and target-platform variables retain the safe defaults above. | No credentials are in Git and frozen features remain disabled. |
| 2 | Deploy the backend through the Railway Docker configuration. | `/api/healthz` is successful after the start grace period. |
| 3 | Deploy the frontend through Vercel with the established backend URL and authentication origin settings. | API, authentication, and chat traffic are not intercepted by the service worker. |
| 4 | Run authorised non-production smoke tests using a disposable user. Include supported teaching, sparse evidence, Hindi or Tamil or Hinglish, and client-disconnect scenarios. | Citations and support labels are truthful, sparse evidence is limited support, and streaming stops cleanly. |
| 5 | Record release metadata and exceptions. | The release owner can reproduce sign-off. |

## Post-deployment checks

Recheck `/api/healthz` after the grace period. Test an authenticated chat turn and a signed-out route. Confirm that no-evidence responses are not labelled teaching-supported, that a Hindi answer can translate to English, and that an English answer can translate to the configured Indian language. Unless separately approved, a WhatsApp broker health request must return 404.

Monitor health, memory, latency, time to first token, errors, rate limits, and limited-support volume.

## Rollback

If readiness fails, errors rise, attribution is wrong, or a safety gate is unexpectedly enabled, stop rollout and restore the last verified deployments. Preserve redacted logs, reset the relevant flag to its safe default, record the exception in the hardening backlog, and deploy the prior verified Git commit rather than editing production files.

## Durable Memory Outbox Rollout

Apply `20260805000001_memory_outbox.sql` before enabling `FEATURE_MEMORY_WRITE`.
Keep this flag `false` until the user-facing consent control calls
`PUT /api/memory/consent` with `{"granted": true}`. A successful chat then writes
one scoped outbox row before asynchronous memory work is dispatched; no receipt
means that no new memory is persisted.

Run Celery Beat and a `celery-worker` that consumes the `memory` queue in addition
to the existing ingestion queues. The task `tasks.memory_outbox_tasks.drain_memory_outbox`
is dispatched immediately and is also scheduled every minute to recover rows from
process crashes or disconnects. The PostgreSQL claim function uses `SKIP LOCKED`;
multiple worker replicas therefore do not process the same claimed row.

| Verification | Expected evidence |
|---|---|
| Consent | A `memory_consent_receipts` row for the authenticated user and tenant with `granted=true` and no `revoked_at`. |
| Durability | A `memory_outbox` row is recorded before the worker begins; it transitions from `pending` to `processing` to `done`. |
| Recovery | Stop a worker after enqueueing a test row, restart it, and confirm the scheduled task completes the row within two minutes. |
| Erasure | `DELETE /api/memory/all` returns `completed` and a `memory_deletion_receipts` record listing all store counts. A `partial_failure` response must be retried. |

To roll back new memory writes, set `FEATURE_MEMORY_WRITE=false`. Existing outbox
rows remain visible for controlled replay or account-wide deletion; do not drop the
outbox tables as a rollback shortcut.
