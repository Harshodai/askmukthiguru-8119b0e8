# Docker idle-cost audit — AskMukthiGuru

**Assessment date:** 2026-08-23

## Conclusion

The available Docker evidence does not establish a Railway invoice amount. It does establish that the connected desktop is running two separate Compose projects continuously: the AskMukthiGuru stack and an unrelated `tayari-skill-boost` project containing Supabase-style services. Docker resource usage on the desktop cannot be converted directly into Railway dollars. The two projects must therefore be attributed separately before any cost conclusion is made.

The local AskMukthiGuru stack was running six containers under `restart: unless-stopped`: backend, Celery worker, Qdrant, Neo4j, Redis, and frontend. During a bounded six-sample window from `14:43:21Z` through `14:44:21Z`, the measured AskMukthiGuru memory was approximately **2,287.8 MiB** when summing the displayed container values. The backend accounted for approximately **1.378 GiB**, Neo4j approximately **691 MiB**, Qdrant approximately **150 MiB**, the worker approximately **49 MiB**, Redis approximately **6–7 MiB**, and the frontend approximately **12 MiB**.

The same Docker host also had 17 visible containers from the unrelated `tayari-skill-boost` project, including Supabase-style services. Their displayed memory values summed to approximately **2,655.7 MiB** in the point-in-time inventory. This is not evidence that AskMukthiGuru caused that usage, and no action was taken against that project.

## Measured baseline

| Scope | Observed state | Interpretation |
|---|---:|---|
| AskMukthiGuru containers | 6 running | All had `restart: unless-stopped`; they remain online without active users unless manually stopped |
| AskMukthiGuru displayed memory | ~2,287.8 MiB | Backend model/runtime memory dominates the local stack |
| AskMukthiGuru backend | ~1.378 GiB, mostly 0.2–0.6% CPU in the sample | High idle resident memory; not proof of a billable Railway memory value |
| AskMukthiGuru Neo4j | ~691 MiB, roughly 0.7–1.0% CPU | Largest non-backend resident service in the local stack |
| AskMukthiGuru worker | ~49 MiB, mostly below 0.2% CPU, with one 23.6% sample | Worker is not the main idle memory driver, but it is unnecessary when no ingestion is running |
| AskMukthiGuru Qdrant | ~150 MiB, below 0.7% CPU | Persistent vector service remains online for local serving |
| AskMukthiGuru Redis | ~6–7 MiB, below 1% CPU | Not an idle cost driver in this snapshot |
| AskMukthiGuru frontend | ~12 MiB, 0% CPU | Not an idle cost driver in this snapshot |
| Unrelated `tayari-skill-boost` project | 17 visible containers; ~2,655.7 MiB displayed memory | Separate local workload; left untouched |
| Docker images | 28 total, 23 active, 61.49 GB total; 11.79 GB reclaimable | Disk/build footprint, not the same as runtime memory billing |
| Docker build cache | 158 records, 38.61 GB; 21.36 GB reclaimable | Large local disk footprint; safe cleanup requires explicit confirmation because it can slow future builds |
| Docker volumes | 13 total, 11 active, 2.605 GB | Persistent data; no volumes were deleted |

The backend log sample contained **176 `/api/health` requests in the last 30 minutes**, all of the observed backend request paths in that interval. This is consistent with an active health-check or monitoring loop and is not evidence of end-user traffic. The worker log sample contained no matched task/heartbeat/error lines in the inspected 30-minute tail. After the worker was manually stopped, Docker reported exit code `137` with `OOMKilled=false`; this audit does not classify that stop as an OOM event.

## Changes applied

The local Compose file now places `celery-worker` behind an explicit `ingestion` profile. The default serving command starts Neo4j, Redis, Qdrant, backend, and frontend without the worker; ingestion is enabled explicitly with `COMPOSE_PROFILES=ingestion docker compose up -d`. This is reversible and does not remove worker functionality.

The Neo4j, Redis, Qdrant, and backend health-check intervals were changed from 10 seconds to 30 seconds. This reduces local probe frequency while retaining health checks. It does not change Railway billing and is not presented as a measured dollar saving.

No action was taken against the unrelated Compose project. No user data, Redis data, Qdrant data, Neo4j data, model cache, or volumes were deleted. No global cache flush was performed.

## What remains unproven

The Docker snapshot does not prove the cause of the Railway billing spike. Railway billing must be reconciled with Railway’s service-level resource metrics and billing period, not inferred from local Docker Desktop values. It also does not prove that the backend’s model memory can be reduced safely; that requires a controlled model-loading experiment with response quality and latency checks. A sustained memory/CPU observation window, worker queue depth, scheduled task inventory, and service-by-service Railway metrics are still required before claiming savings.

The Docker stack’s `restart: unless-stopped` policy means a developer can leave the stack consuming local resources while no users are present. The safe operating rule is to stop the serving stack when idle and explicitly enable ingestion only when needed. The unrelated `tayari-skill-boost` project should be stopped only by its owner; it was not changed in this audit.
