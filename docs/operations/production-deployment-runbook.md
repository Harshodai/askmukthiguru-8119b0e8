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

## Queued Chat Reconnection and Redis Streams Gate

Queued chat streams now emit Redis Stream entry IDs as SSE `id` fields and accept
the standard `Last-Event-ID` header. A reconnect replays only entries after that
cursor; malformed cursors are ignored and restart from `0`. Event streams retain
for at least `QUEUE_JOB_TTL`, and responses disable intermediary buffering.

`USE_REQUEST_QUEUE=false` remains the production-safe default. Although the
repository contains a Redis Streams queue abstraction, the chat producer and a
dedicated cross-replica request consumer have not yet been switched to it. The
capability manifest therefore reports it as unavailable even if the flag is set.
Do not enable the flag until a staging deployment demonstrates producer routing,
consumer-group recovery (`XAUTOCLAIM`), cancellation semantics, and ownership
checks under a process restart. The existing Redis-backed `JobQueueService` with
its NX lease remains the active queued-chat path.

## Trusted Live Logistics Rollout

`LIVE_LOGISTICS` is disabled by default. It is the only intent allowed to call the
live search node. It covers event, Manifest, Guru Darshan, schedule, venue, and
booking questions only when an event/program noun and logistics cue are both
present. General temporal questions continue through the teaching corpus without
live search.

Enable `WEB_SEARCH_ENABLED=true` and `LIVE_LOGISTICS_ENABLED=true` only after
checking that `WEB_SEARCH_ALLOWED_DOMAINS` contains exclusively the approved
official domains. Every returned event card includes `official_source_url`,
`booking_url`, `verified_at`, and `expires_at`; the expiry is controlled by
`LIVE_LOGISTICS_TTL_SECONDS` (default 900 seconds). The UI must show the source
link and verification time rather than treating the generated prose as the
booking authority. If the feature or live service is unavailable, the response
contains no event card and directs the seeker to `ekam.org` instead of guessing.

## Reproducible Dependency Release Gate

The committed lock artifacts are deployment inputs: `backend/requirements.lock`
for Python and `package-lock.json` for the frontend. CI and all Dockerfiles
install the Python lock, while the frontend uses `npm ci`. A dependency change is
not ready for deployment until a clean Python 3.12 environment can install the
backend lock and a clean Node install can complete `npm ci`, tests, and the
production build. Regenerate the backend lock with `uv pip compile
backend/requirements.txt --output-file backend/requirements.lock` whenever its
source manifest changes; review both files together in the same pull request.

## Waitlist Activation and Privacy Gate

The public waitlist is deliberately closed by default. Apply
`supabase/migrations/20260805000002_waitlist_entries.sql` before setting
`WAITLIST_ENABLED=true` on the backend. The table enables RLS and accepts writes
only through the service-role client; it stores a normalised `email_key`, the
contact-consent timestamp, and an optional acquisition source. Never expose the
Supabase service key or direct table access to the browser.

The landing-page form remains hidden unless the separately deployed frontend
variable `VITE_WAITLIST_ENABLED=true` is set. Set both frontend and backend flags
only in the same approved release. The browser submits only an email, source, and
an affirmative `consent_to_contact=true` value to `POST /api/waitlist/`; the API
returns the same acceptance response for a new or already-known email. The
endpoint applies `REGISTRATION_RATE_LIMIT` and returns no account-existence or
email-delivery signal.

| Release check | Required evidence | Rollback |
|---|---|---|
| Database | Migration is applied and `waitlist_entries` has RLS enabled | Keep the table; do not delete consent records as a feature rollback |
| Backend | `/api/capabilities` reports `waitlist: available` only with the feature enabled and service client present | Set `WAITLIST_ENABLED=false` |
| Frontend | The form is visible only in the approved production build and links to `/privacy` | Remove `VITE_WAITLIST_ENABLED` or set it to `false` and redeploy |
| Privacy | A representative record has a consent timestamp and no browser-accessible secret is present | Stop collection; retain and handle records under the published privacy policy |

## Assistant Corpus Registry and Retrieval Containment

Assistant slugs are presentation identifiers, never retrieval authority. Configure
`ASSISTANT_CORPUS_REGISTRY` as a JSON mapping of an allowlisted assistant slug to
its permitted `corpus_id` and optional `teacher_id`; keep
`ALLOWED_ASSISTANT_SLUGS` aligned with that mapping and retain an explicit
`DEFAULT_CORPUS_ID`. The server resolves this scope once in `GraphStage` and
passes it to graph, vector, cache, and ontology boundaries. An unrecognised or
unmapped slug must fail closed to the default corpus, not inherit a client tag.

Before enabling a new teacher, run a canary with sentinel documents in each corpus
and confirm that cross-corpus retrieval, graph traversal, cache reuse, and
ontology projection do not expose the sentinel. The corpus ID and source-release
version are part of ingestion checkpoint identity; a source update must use a new
release version and must not silently reuse a completed checkpoint from another
corpus.

## Crisis Pre-emption Verification

Severe distress and crisis classifications are now handled before graph execution,
model invocation, cache, memory, and proactive-practice stages. The deterministic
reply must present the immediate helpline-first path and record the
`crisis_preempted` route decision. This is safety behaviour, not a configurable
marketing feature; do not gate it with an environment flag.

Run a staging trace with both severe-distress and crisis fixtures before every
safety-sensitive release. The trace must prove that no retrieval span, generation
span, memory write, cache write, or live-search span occurs after the classification.
A failure requires rollback or a release hold, not an exception list.

## Evidence-Support Labels and Official Live Information

The UI renders support as one of `Teaching-supported`, `Partially supported`, or
`Limited support` through `src/lib/chat/evidenceSupport.ts`; do not add local
numeric-threshold copies in message components. The label describes support from
backend metadata and is not a personal diagnosis, truth guarantee, or fabricated
confidence percentage.

For live logistics, enable `WEB_SEARCH_ENABLED` and `LIVE_LOGISTICS_ENABLED` only
after the allowlist and freshness checks in the existing live-logistics section
pass. The transport must retain `live_logistics_events` for both REST and SSE
responses. The chat UI displays a typed official-event card only for HTTPS
official URLs, with a verification time and distinct official-details and booking
links. It must not infer dates or booking availability from generated prose.

## Governed Source-Release Lifecycle

`CORPUS_RELEASE_REGISTRY_ENABLED=false` is the default. Enable it only after the
Supabase migration is applied and the approval/rollback drill below succeeds in
staging. The registry records source references, identities, immutable versions,
checksums, approval audit fields, and activation state. It does not store source
bodies, seeker messages, prompts, or generated answers.

| Step | Required operator action | Required check |
|---|---|---|
| Register | Create a checksum-addressed candidate release through the protected admin API | The release is `pending`; a duplicate checksum returns the same release |
| Review | Validate source authority, attribution, quality, and checksum against the candidate corpus work | Record an AAL2 admin approval; only `pending` may become `approved` |
| Activate | Activate an approved release through the protected admin API | The database atomically supersedes the earlier active release for that corpus/source |
| Verify | Run retrieval and citation canaries using the active corpus/version | The response evidence envelope reports only structured corpus/release/model-policy facts |
| Roll back | Re-approve and re-activate the prior audited release when rollback is required | Record the reason, then re-run scope and citation canaries before traffic increases |

The present ingestion integration namespaces checkpoints and stored chunk metadata
by the active release version when the registry is enabled. It does **not** claim
physical Qdrant/Neo4j/LightRAG blue-green collection aliasing: current ingestion
can still overwrite the shared physical source index. Keep the registry disabled
for public traffic until a staging drill proves the approval, activation,
supersession, and rollback workflow with the actual data topology. A future
physical-alias design remains a separate implementation gate.

The typed `answer_evidence` response field contains only the resolved corpus,
observed release version when retrieval provides one, model-policy ID, calibrated
support label, source count, top structured source score, and citation-verification
state. It must not be populated from generated answer text or presented as a
numerical spiritual-truth score.

## Staged Deployment Control Sheet

Do not call a deployment production-ready merely because unit tests pass. The
release owner must retain the evidence below for the deployed build and record the
commit SHA, environment, and timestamp with the release.

| Gate | Evidence that must pass | Decision if it fails |
|---|---|---|
| Scope containment | Corpus-sentinel canary shows no cross-tenant or cross-teacher retrieval, graph, cache, or ontology leakage | Hold the release and disable the new assistant mapping |
| Safety routing | Severe and crisis traces end at `crisis_preempted` before retrieval or generation | Hold the release |
| Privacy and erasure | Memory deletion drill and waitlist consent path complete as designed | Keep write flags disabled |
| Live logistics | Official-domain, freshness, and event-card source checks pass | Keep `LIVE_LOGISTICS_ENABLED=false` |
| Recovery | Restore drill verifies database, Qdrant, Neo4j, and release configuration recovery | Do not increase traffic |
| Capacity | Staging load test records p95 TTFT, error rate, queue depth, and provider-limit behaviour at the intended launch concurrency | Cap traffic to the observed safe level and investigate |


Source-release registration, approval, atomic metadata activation, and the typed
answer-evidence contract are implemented in this repository. They remain launch
gates until their required staging evidence is retained. Physical corpus alias
activation, the source-release rollback drill, and live data-topology verification
are still separate gates and must not be inferred from the metadata registry.

## OpenRouter Model Policy and Spend-Guard Activation

The active OpenRouter deployment must use pinned model IDs and the server-side policy rather than browser-selected models. Set `OPENROUTER_POLICY_ID`, `OPENROUTER_ENFORCE_MODEL_POLICY=true`, `OPENROUTER_REQUIRE_NO_TRAINING=true`, and the primary, fast, classification, and optional fallback model IDs in Railway. Leave `OPENROUTER_ALLOWED_PROVIDERS` empty unless a verified provider allowlist is required; the policy still requests no-training routing and records the policy ID in the privacy-safe operations view.

The values in `.env.example` reserve a conservative early-stage envelope: `$0.25` per day, `$6.00` per month, and `$0.03` maximum per admitted request. They are deployment defaults, not a claim about a provider’s final price. Recalculate them from the selected OpenRouter model card and the actual monthly budget before enabling traffic.

| Control | Initial state | Required activation proof | Immediate rollback |
|---|---|---|---|
| Model policy | Enabled | Pinned primary/fast/classification/fallback IDs pass startup validation | Restore last known pinned configuration; never use a `:latest` alias |
| Actual-cost ledger | Enabled | A staging request records non-zero OpenRouter `usage.cost` when returned | Retain token accounting; investigate missing provider usage before interpreting spend totals |
| Redis spend guard | **Disabled** | Shared-Redis health loss returns a controlled failure, rejected reservation does not call the provider, and a known lower actual cost refunds only the unused reserve | Set `OPENROUTER_BUDGET_GUARD_ENABLED=false` only while the incident is mitigated, then cap public admission and restore the guard |

When the Redis guard is enabled, an unavailable shared ledger fails closed by default. Do not set `OPENROUTER_BUDGET_FAIL_CLOSED=false` in a public launch without an explicit, time-bounded incident decision; doing so trades a cost ceiling for availability.

## Staged 500-Session Readiness Gate

Run the readiness matrix only against local mock infrastructure or a non-production staging environment using test authentication. It must not point to the public Lovable frontend or the production Railway service. The test progresses through 25, 100, 250, and 500 active users, uses the identical-question workload already represented in the Locust file, and saves a JSON report for every stage.

```bash
cd backend
export LOAD_TEST_URL=https://staging-api.example.com
export BENCHMARK_SECRET='staging-only-secret'
export READINESS_DURATION=180s
./benchmarks/run_readiness_matrix.sh
```

The runner rejects a stage with fewer completed requests than declared active users, p95 above the configured default of 8 seconds, or a failure rate above 1 percent. Record the report directory, deployment SHA, model-policy ID, corpus release, region, Redis/Qdrant/Neo4j topology, and current Railway replica count with each run. A passing mock-provider run proves application backpressure and race handling; it does **not** prove external OpenRouter capacity or global user latency.

Before advancing public admission, run a separate staging trace for crisis pre-emption, corpus containment, live-logistics source freshness, memory erasure, Redis guard failure, queued-SSE reconnection, and a restore drill. Failure of any gate freezes cohort expansion and returns the system to the previously observed safe cohort.
