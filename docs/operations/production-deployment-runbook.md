# Production Deployment Runbook

> **Release baseline:** `40e8923f` or the final release commit that supersedes it. This runbook governs the initial Vercel frontend and Railway backend release. Passing automated tests is necessary but does not replace the non-production evidence required in the [release evidence pack](./release-evidence-pack.md) and [hardening backlog](./product-hardening-backlog.md).

## 1. Pre-deployment configuration

Configure secrets through the hosting platform only. Do not add credentials to repository files, build logs, screenshots, or support tickets. The backend must have the standard authentication, LLM, Redis, Qdrant, Neo4j, and Supabase variables required by its existing deployment configuration, together with an explicit, non-wildcard `FORWARDED_ALLOW_IPS` value appropriate for the deployed proxy boundary.

| Control | Initial production value | Re-enable only after |
|---|---|---|
| `FEATURE_MEMORY_WRITE` | `false` | Explicit consent, outbox/idempotency, deletion, and cross-store erase evidence. |
| `VITE_MEMORY_EXTRACTION_ENABLED` | **Omit** or set `false` | The approved single-memory-plane design and scoped RLS proof. |
| `USE_REQUEST_QUEUE` | `false` | Two-replica claim/ack/recovery/cancellation chaos test and provider idempotency proof. |
| `WEB_SEARCH_ENABLED` | `false` | Staging verification for official event/booking sources, freshness, and citations. |
| `WEB_SEARCH_ALLOW_DB_DOMAIN_OVERRIDE` | `false` | A reviewed break-glass change with a documented official-domain list. |
| `WHATSAPP_WEBHOOK_ENABLED` | `false` | The WhatsApp release gate in the hardening backlog is fully satisfied. |

The Railway process must start through `python start_railway.py`; it refuses startup if forwarded-header trust is missing or set to a wildcard. Railway is configured to probe `/api/healthz` with a 60-second health-check timeout. Keep the Railway deployment at **one web worker per replica** initially because the local embedding and reranking assets are process-resident. Scale with horizontal replicas only after staging load evidence confirms Redis, Qdrant, Neo4j, and provider quotas.

## 2. Deployment procedure

| Step | Action | Expecte| Step | Action | Expecte| Step | Action | Expecte| Step | Action | Expecte| Step | Action | Expecte| Step | Action | arget platforms. | No secrets appear in Git; safety gates retain the initial values above. |
| 2 | Deploy the backend from the Railway Docker configuration. | The service reaches `GET /api/healthz` successfully after its start grace period. |
| 3 | Deploy the frontend to Vercel with the backend base URL and authenticated-origin settings already used by the application. | The static frontend loads without using the service worker for API, auth, or chat responses. |
| 4 | Run a small authorised smoke test with a disposable non-production user first: one supported teaching query, one sparse-evidence query, one Hindi/Tamil/Hinglish query, and one disconnect. | Citations/support labels are truthful; sparse evidence is labelled limited; the stream cancels cleanly. |
| 5 | Capture the release evidence required by the evidence pack, including the commit SHA, UTC time, environment name, redacted request identifiers, observed health result, and rollback decision. | The release owner can reproduce and approve the deployment. |

## 3. Post-deployment checks

Confirm that `/api/healthz` remains successful after the grace window, then check a normal authenticated chat turn and a signed-out route. Confirm that a no-evidence response is not presented as teaching-supported, a message rendered in Hindi translates from `hi-IN` to English when requested, and an English answer translates to the configured Indian language. Confirm that the WhatsApp health endpoint returns 404 unless an apprConfirm that `/api/healthz` remains successful after the grace window, then check a normal authenticated chat turn and a signed-out route. Confirm that a no-evidence response is not presented as teaching-supported, a message rendered in Hindi translates from `hi-IN` to English when requested, and aed errors or make a demo appear more complete.

## 4. Rollback

If `/api/healthz` fails after the start grace period, error rates rise, response attribution is incorrect, or a safety gate is found enabled unexpectedly, stop rollout and return the Railway and Vercel services to their last verified deployment. Preserve redacted logs and request identifiers, set the affected feature flag to its safe default, and record the exception in the hardening backlog before retrying. For a code rollback, deploy the previous verified Git commit rather than editing production files in place.
