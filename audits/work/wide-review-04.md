# Production Operations, Reliability, Security, and Scalability Review

## Executive finding

The project contains substantial operational work: Docker health checks, Redis persistence, Qdrant persistence, Prometheus/Grafana/Jaeger, queues, watchdog/autoheal, resource limits, and Kubernetes/Railway manifests. The problem is configuration and deployment drift. The live local stack is healthy, but the deployment system does not yet present one reproducible, immutable, multi-guru production control plane.

## Evidence

- `backend/docker-compose.yml` defines backend, Redis, Qdrant, Memgraph, observability, health checks, logging caps, thread controls, and resource limits.
- `backend/Dockerfile` and `backend/Dockerfile.railway` build different runtime shapes. The Railway image copies `backend/`, selected scripts, memory, and helplines, but not the root production compose manifest.
- `backend/infrastr- `backend/infrastr- `backend/infrastr- `backend/infrastr- `backe multiple Redis/Qdrant replicas, Celery workers, and stateful storage. It is a design manifest, not evidence of a tested deployment.
- `backend/app/health.py`, `backend/app/api/health.py`, `backend/app/metrics.py`, `backend/app/unified_observability.py`, and telemetry modules provide health and metrics.
- `backend/app/queue/redis_stream_queue.py`, `backend/app/queue/in_process_queue.py`, Celery tasks, and Redis locks provide asynchronous work paths.
- `backend/tests/test_prod_compose_invariants.py`, `test_docker_compose_healthcheck.py`, `test_railway_startup_hygiene.py`, and `test_railway_cleanup.py` provide meaningful static checks.

## Direct runtime evidence

- Docker Desktop daemon available.
- Backend container healthy, restart count 0 at probe.
- `/api/health` returned `ready:true` and healthy dependency signals.
- Qdrant, Redis, Memgraph, Prometheus, Grafana, Jaeger, frontend, and Supabase local services were running.
- `docker compose -f backend/docker-compose.yml config --quiet` passed.
- Container first-person tests passed 85/85.
- Host production/infrastructure tests passed 47/47.
- Container production-invariant test failed because `/docker-compose.prod.yml` is absent from the image; the host version passes.

## P0 blockers

1. **Unsafe first-person runtime configuration:** local container has `IS_PRODUCTION=false` and `FIRST_PERSON_SERVE_UNREGISTERED=true`. Production startup must fail closed on these states.
2. **No atomic promotion/rollback:** Qdrant aliases are empty. Collection selection is a mutable configuration value.
3. **Image/config parity failure:** production-invariant tests need a file absent from the image. CI must validate the exact image 3. **Image/config parity faundle.
4. **Mutable deployment references:** Kubernetes uses `latest` images. Use image digests and immutable release manifests.
5. **No proven tenant policy enforcement:** guru isolation is not a mandatory control-plane policy injected into every request/cache/query.
6. **Backup/restore not proven:** persistence volumes exist, but restore drills and recovery-point/recovery-time objectives are not demonstrated.

## Reliability concerns

- `WEB_CONCURRENCY=1` in Railway limits horizontal CPU process scale; increasing it can multiply model memory/thread usage.
- Compose includes extensive dependencies and local Supabase services; production should separate online serving from ingestion and development-only services.
- Redis has max memory and LRU policy. This is appropriate for caches but dangerous for durable job/state keys unless namespaces and persistence semantics are explicit.
- Jaeger all-in-one memory is capped and in-memory; it is not a durable trace store.
- Health checks verify reachability/readiness but not calibration validity, rights policy, alias correctness, retrieval quality, or cross-tenant isolation.
- External LLM, translation, ASR, embedding, and reranking providers require explicit circuit breakers, quotas, cost budgets, retries, and provider/version accounting.

## Security concerns

- `backend/app/config.py` has security settings and metrics protections, but production must fail on missing secrets and unsafe auth/test flags.
- Default/example credentials in Compose are acceptable for local development only and must be structurally rejected in production.
- `/metrics`, admin routes, ingestion routes, and debug surfaces need separate auth and network policy.
- Logs must exclude seeker text, secrets, raw embeddings, and sensitive crisis content while retaining enough trace metadata for incident response.
- Rights/revocation events need immutable audit records and cache/index invalidation.

## Target operational architecture

- Control plane: guru registry, rights policy, build registry, evaluation gates, alias controller, audit log.
- Serving plane: stateless API replicas, mandatory policy middleware, exact cache, vector search, rerank/calibration, response integrity validator.
- Ingestion plane: separately scaled ASR/diarization/alignment/index workers with durable queue, idempotency key, checkpoint, dead-letter queue, and run registry.
- Storage plane: immutable object store for raw/audio/transcript artifacts; Qdrant for versioned vectors; relational metadata store for manifests/policies; Redis only for bounded cache/coordination.
- Observability plane: Prometheus SLOs, traces with build/guru IDs, quality telemetry, leakage probes, cost/provider metrics, alerts and runbooks.
- Release plane: immutable image digests, build manifest, candidate collection, offline gates, canary, atomic alias swap, rollback.

## Concrete remediation

- Add production startup assertions and a configuration contract test that runs inside the final image.
- Replace `latest` with digest-pinned images and generate SBOMs.
- Separate `compose.dev`, `compose.test`, and a production deployment bundle with one release manifest.
- Add Qdrant snapshot and restore automation; test it regularly.
- Define RPO/RTO for Qdrant, metadata, object storage, Redis queues, and audit logs.
- Add chaos tests for Qdrant/Redis/LLM/embedding outages, retry storms, stale locks, and partial indexing.
- Add per-guru quotas, rate limits, cache namespaces, worker pools, noisy-neighbor protection, and shard promotion.

## Production gate addendum

The runtime health endpoint proves dependency readiness but does not prove first-person readiness. It must additionally validate: the active collection or alias exists; its manifest matches the release manifest; every served point meets rights/eligibility/schema gates; a calibration profile matches the encoder/build; and `FIRST_PERSON_SERVE_UNREGISTERED` is false in production.

The existing `QdrantAliasManager` in `backend/services/qdrant/aliases.py` and its tests demonstrate the correct atomic-swap primitive. The serving configuration should use a stable alias (for example `first_person_live`) and retain immutable build collections for rollback instead of editing `FIRST_PERSON_COLLECTION` and recreating the container.
