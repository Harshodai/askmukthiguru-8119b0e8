# Product Hardening Backlog

**Status:** Active release-control record.
**Owner:** Founder / engineering lead.
**Review cadence:** Every implementation batch and before any environment promotion.

> A passing frontend build or isolated unit test is not release approval. Every item below requires the specified proof in a non-production environment before the affected capability is exposed.

## Batch 1 — containment and reproducible test bootstrap

| Item | Status | Evidence required before release | Release effect |
|---|---|---|---|
| Browser worker caches only immutable public static assets; it no longer intercepts API, personalised, crisis, practice or live-information requests and never returns a simulated offline spiritual answer. | Implemented, verification pending in browser integration. | Service-worker integration test proves authenticated/API responses are absent from Cache Storage; sign-out purge and offline UX review. | PWA promotion blocked until proof exists. |
| Backend test bootstrap can select explicit `memory://` rate-limit storage without changing application Redis configuration. | Implemented. | Clean virtual-environment collection and focused unit test results recorded in CI. | Backend release blocked until clean CI uses the declared environment. |
| Makefile prefers `backend/.venv` for backend commands. | Implemented. | `make test-backend` succeeds in a clean checkout/CI. | Local root virtual environment is not release evidence. |
| Redis requirements and backend project metadata use one supported range. | Implemented. | Locked dependency artifact, clean install and `pip check`/equivalent are clean. | Dependency reproducibility remains blocked. |
| Edge Function config exposes only `healthz` without a JWT; all other functions retain platform JWT enforcement unless a reviewed source-controlled exception is added. | Implemented. | Staging deploy verifies the auth matrix and scheduled jobs do not depend on dashboard-only settings. | Cron/Edge-function features remain blocked until tested. |

## Active P0 release blockers

| ID | Blocking capability | Required proof | Owner | Due |
|---|---|---|---|---|
| P0-1 | Corpus, teacher and tenant scope containment | Cross-scope vector, graph, cache, memory and citation isolation suite. | RAG/data lead | Before invited alpha |
| P0-2 | Single consented memory plane | Durable outbox, lease/idempotency, deletion receipts and cross-store erase proof. | Privacy/backend lead | Before invited alpha |
| P0-3 | Replica-safe chat work | Two-replica crash/retry/disconnect test with one provider execution per idempotency key. | Platform lead | Before private beta |
| P0-4 | Capability truth and calibrated support labels | Dependency-outage matrix visibly changes answer support state and UI. | Backend/product lead | Before invited alpha |
| P0-5 | Public support and attachment handling | Text-only default or quarantine/scan/safe-view/retention pipeline. | Security/operations lead | Before public support |
| P0-6 | PWA runtime boundaries | Browser integration proof for static-only cache and non-advisory offline state. | Frontend/security lead | Before PWA promotion |
| P0-7 | Dependency lock and CI evidence | One lock authority; clean build/test; non-skippable integration jobs. | Build/QA lead | Before invited alpha |
| P0-8 | Edge-function control plane | Versioned auth/schedule/provider inventory and staging auth tests. | Supabase/platform lead | Before edge/cron promotion |

## Conditional capability freezes

| Capability | Default | Re-enable only when |
|---|---|---|
| WhatsApp broker | Disabled | Identity, consent, replay/idempotency, deletion, redaction, budget and production-runtime tests pass. |
| Automatic Supabase memory extraction/drainer | Disabled | It is replaced by the approved single-memory-plane design. |
| Redis Streams request queue | Disabled | Claim/ack/nack/recovery/cancellation semantics pass two-replica chaos tests. |
| Public support attachments | Disabled | Quarantine/scan/safe-preview and operator access controls pass. |
| Offline spiritual chat responses | Disabled | The worker remains static-only; do not emulate live guidance offline. |
| Multi-teacher/licensed corpus expansion | Disabled | Scope/provenance and rights-release proofs pass. |

## Known environment exceptions

| Exception | Impact | Resolution |
|---|---|---|
| The root `.venv` is stale and lacks Celery; the backend-managed `.venv` is the current backend test environment. | Running root-venv pytest fails before tests execute. | Remove/rebuild the root Python environment or add a single documented environment bootstrap; CI must use the backend project environment. |
| Current project-environment `pip check` reports pre-existing incompatible installed package versions unrelated to the Redis alignment. | The local environment is not a clean dependency-lock proof. | Generate and validate one locked install in a clean CI/staging environment before release. |

## Batch 2 — stable identity and scope provenance

| Item | Status | Evidence required before release | Release effect |
|---|---|---|---|
| Reciprocal-rank fusion and local retrieval deduplication use a canonical SHA-256 document key instead of process-local Python object IDs or hashes. | Implemented and unit-tested. | Retrieval regression suite shows equivalent documents from separate channels fuse once while distinct chunks survive. | Required before quality/latency benchmarking. |
| Global-memory points use deterministic UUIDv5 identities derived from tenant, user and normalised content; Qdrant payloads contain `tenant_id`. | Implemented and unit-tested for new writes. | Non-production payload backfill plus cross-tenant query test against real Qdrant. | Existing global-memory reads must not be promoted until legacy payload scope is verified. |
| Global-memory search fails closed without a user and filters on both tenant and user. Neo4j `User` matches include tenant identity. | Implemented and unit-tested with mocks. | Real Qdrant and Neo4j cross-tenant isolation evidence. | Personal-memory capability remains alpha-only. |
| New ontology relationships are merged with `corpus_id` and carry `teacher_id`; targeted subgraph traversal binds a corpus ID. | Implemented and unit-tested. | Run `scripts/ops/backfill_neo4j_relationship_scope.py` against non-production, review count, apply, then capture scoped retrieval evidence. | Multi-teacher corpus launch remains blocked. |

> **Migration warning:** current-default corpus reads allow legacy Neo4j relationships without `corpus_id` only during migration. Non-default corpora never receive those legacy edges. Do not introduce a second corpus until the backfill evidence is attached to the release record.

## Batch 3 — consent-gated memory and bounded durable work

| Item | Status | Evidence required before release | Release effect |
|---|---|---|---|
| Backend memory persistence is disabled by default through `feature_memory_write=False`. The memory stage exits before second-brain, profile, semantic, layered, and episodic persistence paths. | Implemented and regression-tested. | Capture an explicit user-consent record and a successful enable/disable/delete proof for the approved single memory plane. | Automatic memory persistence remains off until consent and deletion evidence are accepted. |
| The legacy frontend Supabase memory-extraction enqueue is disabled unless `VITE_MEMORY_EXTRACTION_ENABLED=true`. | Implemented and production build verified. | Staging test confirms the disabled client cannot enqueue a pending extraction and the enabled path has authenticated, scoped RLS controls. | The legacy edge extraction path remains disabled. |
| Consent-enabled memory background tasks now have a configurable `memory_background_task_timeout_seconds` bound (30 seconds by default). | Implemented. | Load-test timeout and cancellation behaviour against the real LLM, Supabase, and memory dependencies. | Background memory enrichment is best-effort and cannot be relied on for a durable user promise. |
| Redis-backed legacy job processing now acquires a per-job `SET NX EX` lease, verifies terminal state after claim, releases only its own lease, and returns interrupted work to `queued` for recovery. | Implemented and unit-tested for concurrent claims. | Two-replica crash/retry test with real Redis and provider-side idempotency-key evidence. | The legacy queue is safer for a single-process deployment; Redis Streams remains disabled. |
| SSE streaming now checks for a client disconnect and cancels the active pipeline in generator cleanup. | Implemented and regression-tested with a blocking pipeline. | Staging disconnect test confirms provider cancellation propagation and no leaked tasks under concurrent streams. | Client disconnects stop active request work; detached consent-enabled enrichment remains timeout-bounded. |

> **Deployment default:** retain `FEATURE_MEMORY_WRITE=false`, omit `VITE_MEMORY_EXTRACTION_ENABLED`, and retain `USE_REQUEST_QUEUE=false` for the first release. These controls must not be enabled merely because unit tests pass; each needs its listed non-production evidence.

## Batch 4 — capability truth, multilingual response support, and official live sources

| Item | Status | Evidence required before release | Release effect |
|---|---|---|---|
| Generation abstentions with no retrieved teaching or memory context emit the calibrated low internal support value of `2.0`, rather than a misleading `8.0`. The chat UI now presents **Teaching-supported**, **Partially supported**, or **Limited support** labels instead of a raw 1–10 score. | Implemented; backend regression and frontend production build verified. | Fixture evaluation across cited, partially cited, abstained, cache, and dependency-failure cases. | The support label is explanatory, not a guarantee of truth or pastoral authority. |
| Roman-script Hinglish and Tanglish routing counts individual vernacular token matches instead of regex-list entries, which made the old threshold unreachable. | Implemented and unit-tested. | Test corpus including transliteration variants, ordinary English with Sanskrit terms, and mixed-script inputs. | User language is better preserved without treating a single spiritual term as code-mixing. |
| Assistant messages retain the configured response language. Translation now uses that answer language as the source and the user preference as the target; when both match, it offers English as the alternate target. | Implemented, component-tested, and production build verified. | Browser validation across Hindi, Tamil, Telugu, Kannada, Hinglish, and English responses. | Existing historic messages without language metadata safely default to English. |
| Live web results are tagged as official-domain evidence. Database configuration can narrow the source-controlled official allowlist but cannot widen it unless the explicit `WEB_SEARCH_ALLOW_DB_DOMAIN_OVERRIDE=true` break-glass flag is set. | Implemented and unit-tested. | Staging test for next-event and booking queries using accessible official event and booking pages; validate freshness and citation display. | `WEB_SEARCH_ENABLED` remains off by default. Do not claim live dates or booking availability while it is off or official evidence is unavailable. |
| Teacher voice review confirms the Langhanam prompt allows first-person wording only when it is present in retrieved context and requires explicit attribution; it forbids synthesising or impersonating living teachers. | Existing control reviewed; no behavioural change required. | Attribution benchmark against quoted, paraphrased, multilingual, and sparse-context examples before adding a new teacher. | Multi-teacher expansion remains blocked on rights, provenance, and tenant-scope proof. |

## Batch 5 — deployment and integration boundaries

| Item | Status | Evidence required before release | Release effect |
|---|---|---|---|
| The active backend Docker entrypoint now starts as root solely to repair mounted cache/data permissions, then drops to `appuser` before the server or worker executes. | Implemented; shell syntax verified. | Build and start the Railway image with representative mounted volumes; confirm the application process UID is `appuser` and writable paths are limited to the intended data/cache directories. | Prevents non-root startup failures caused by root-owned mounts without serving the application as root. |
| Railway deployment config explicitly probes `/api/healthz` with a 60-second timeout, matching the Railway wrapper’s readiness and heartbeat semantics. | Implemented; JSON validated. | Staging rolling deploy showing readiness success, graceful drain, and recovery on a forced dependency-health failure. | Deployment health is now explicit; it is not a substitute for end-to-end dependency monitoring. |
| The standalone legacy WhatsApp broker is fail-closed: every route returns 404 and direct startup exits unless `WHATSAPP_WEBHOOK_ENABLED=true`. No active backend compose or Railway configuration starts the broker. | Implemented and regression-tested. | A separate production design must pass identity, consent, replay/idempotency, durable state, deletion, redaction, budget, and provider-webhook verification before the flag is set. | WhatsApp remains frozen for the initial release. |

> **Operational rule:** Do not set `WHATSAPP_WEBHOOK_ENABLED=true`, `WEB_SEARCH_ENABLED=true`, `USE_REQUEST_QUEUE=true`, or `FEATURE_MEMORY_WRITE=true` in production until the corresponding release evidence in this backlog has been attached and approved.

## Batch 6 — reconciliation safeguards

| Item | Status | Evidence required before release | Release effect |
|---|---|---|---|
| Playlist checkpoints use the same source URL for the pre-ingestion lookup and final save. The content hash is retained as metadata. Ontology write failures now raise explicitly; playlist ingestion rolls back its indexed source and leaves it uncheckpointed. | Implemented and regression-tested. | Controlled re-ingestion of a changed and unchanged playlist source with Qdrant, LightRAG, Neo4j, and checkpoint stores. | Prevents a known duplicate-work loop and false successful playlist checkpoint when required graph materialization fails. |
| Public support is text-only. The profile UI no longer offers files and the API rejects every attachment before it is stored or emailed. | Implemented and regression-tested. | Separate approved design and tests for quarantine, scanner, MIME/size validation, safe preview, retention/deletion, and operator access before adding any file route. | Public attachment upload remains unavailable. |
| `GET /api/capabilities` emits a non-secret manifest that separates policy-disabled, available, and unavailable feature states. | Implemented and unit-tested. | Staging dependency-outage tests and UI consumption that change answer support state for the affected capability. | Capability reporting exists but does not yet replace per-answer degradation evidence. |
