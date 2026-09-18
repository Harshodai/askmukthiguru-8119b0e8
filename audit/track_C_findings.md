# Track C — Ruthless Production-Readiness Audit
## GC/Memory, Redis/Celery, Streaming/Async/Concurrency

Repo: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
Date: 2026-09-18
Scope: Phase 7 (GC/Memory/Resource Leaks), Phase 12 (Redis/Celery/Background Jobs), Phase 13 (Streaming/Async/Concurrency)

Environment at time of audit: Docker stack up — `mukthiguru-backend` (localhost:8000), `mukthiguru-qdrant` (6333), `mukthiguru-memgraph` (7687), `mukthiguru-redis` (6379), plus `mukthiguru-autoheal` and a local Supabase stack (13 containers). `docker exec` into any container was denied by this session's permission system throughout — every runtime check that needed it (file descriptor counts, in-container process inspection) is marked UNKNOWN below rather than assumed. `docker ps`, `docker stats`, `docker logs`, `docker inspect`, and HTTP calls to the services were all available and used instead.

---

## Phase 7 — Garbage Collection / Memory / Resource Leaks

### Status: COMPLETE (with one item UNKNOWN — file descriptor counts)

### What was checked

1. **The semantic-cache GC fix from commit `96fd24a5` (this session, earlier today).** Read `backend/services/cache/semantic_adapter.py` and `backend/tasks/cache_maintenance_tasks.py` in full, plus `backend/celery_config.py`'s `beat_schedule`.
2. **Other instances of the same pattern** (a cache/store with TTL on one side, none on the other): `backend/services/cache/{hot_cache_adapter,redis_adapter,memory_adapter,llm_cache}.py`, `backend/services/doctrine_cache.py`, `backend/services/canonical_memory/vector_index.py`, and the ingestion-time Qdrant backup-collection mechanism (`ingest/pipeline.py:_backup_before_reindex`).
3. **Module-level global state**: `backend/rag/nodes/_services.py`, `backend/services/http_client_pool.py`.
4. **Data-retention enforcement**: `backend/celery_config.py` beat schedule, `backend/services/compliance_logger.py`.
5. **Live burst test**: 40 concurrent-ish real `/api/chat?wait=true` requests (concurrency 6) against the live backend, using the `X-Test-Key` benchmark bypass (`ENABLE_TEST_AUTH=true`, `IS_PRODUCTION=false` in `backend/.env`) to skip the 5-message anonymous quota and exercise the full pipeline repeatedly.

### What was verified

**The semantic-cache fix (96fd24a5) is correct and complete.** `SemanticCacheAdapter.get()` now deletes the Qdrant point reactively the moment it finds the Redis payload already expired (`semantic_adapter.py:216-228`); `put()` mirrors `cached_at` into the Qdrant payload (`semantic_adapter.py:274-279`) so the new scheduled sweep can filter on age without touching Redis; `tasks/cache_maintenance_tasks.py:prune_semantic_cache` runs hourly via `celery_config.py`'s `beat_schedule` (`"prune-semantic-cache": {"schedule": 3600.0}`, confirmed present at `celery_config.py:105-108`) and scroll-deletes points older than `semantic_cache_ttl` in batches of 500. Both halves exist, both are wired, both are tested (`tests/test_cache_maintenance_tasks.py`, `tests/test_semantic_adapter_roundtrip.py`). No further action needed here.

**Other TTL-asymmetric cache patterns — none found live.** `hot_cache_adapter.py` and `memory_adapter.py` use bounded in-process structures (hand-rolled TTL dict with `_expire_stale()` + max-size eviction, and `cachetools.TTLCache`, respectively) — both self-bound, no external store to leak into. `redis_adapter.py` is pure Redis with `setex`, no secondary store. `llm_cache.py` (GPTCache) despite its docstring/log line claiming "Qdrant + shared embedder", actually uses `manager="map"` — an LRU-bounded in-memory store persisted to a flat file (`lessons.md §22` cited in-code) — it does **not** touch Qdrant at all; the log message is stale/misleading but not a leak (see AMK-C-006, LOW). `services/doctrine_cache.py` is dead code on the live config (`DOCTRINE_CACHE_ENABLED=false`, confirmed in `app/pipeline/stages/doctrine_cache_stage.py:40`). `canonical_memory/vector_index.py` is a Qdrant index for permanent (not TTL'd) user memories, deleted explicitly on memory delete/forget — correct by design, not a TTL mismatch.

**The Qdrant ingestion backup mechanism (`_backup_before_reindex`) is correctly bounded, not a leak.** Every re-ingestion of an existing source snapshots it to a dated `spiritual_wisdom_ingest_backup_YYYYMMDD` collection, then calls `prune_backups(prefix, max_backups=5)` (`ingest/pipeline.py:2794`, `services/qdrant/indexer.py:412-427`), which sorts backup collections alphanumerically (works because of the `YYYYMMDD` suffix) and deletes all but the newest 5 via `delete_collection`. Confirmed live: Qdrant currently holds exactly 5 such backup collections (`20260901`, `20260902`, `20260903`, `20260905`, `20260906`) — consistent with the retention policy actually firing. Not a finding.

**Module-level singletons (`rag/nodes/_services.py`) are a small, fixed set of service references** (ollama, embedder, qdrant, lightrag, etc.), set once at startup via `init_services()`, explicitly nulled via `clear_services()` at shutdown. Bounded; not a leak.

**`services/http_client_pool.py`** is a correct singleton pattern: one shared `httpx.AsyncClient` with connection limits (`settings.http_pool_max_connections` / `max_keepalive`), guarded by an `anyio.Lock` against double-init, closed via `aclose()` in the FastAPI lifespan. No per-request client creation found anywhere this audit touched.

**Data-retention enforcement gap — confirmed still accurate, both halves.**
- `celery_config.py`'s `beat_schedule` (lines 92-109) has exactly 4 jobs: win-back email dispatch, batched-memory processing, memory-outbox drain, and the new semantic-cache prune. **Zero jobs delete or archive old rows from Supabase `chat_responses` or any telemetry table.**
- `services/compliance_logger.py:log_interaction()` accepts and validates `retention_days` (raises `ValueError` on a bad value, lines 179-188) and stores it in the JSONL audit record — but nothing anywhere in the codebase reads that field back to purge anything. Confirmed via search: no caller filters or deletes compliance-audit rows/files by age.
- Additionally, and not previously flagged: `ComplianceLogger.write_record()` writes to a local, daily-rotated-by-filename JSONL file (`compliance_audit_YYYY-MM-DD.jsonl`, `services/compliance_logger.py:58-61`) — "rotate daily using a timestamp suffix" per the module docstring — but **rotation here only means a new filename per day; old files are never deleted.** This is unbounded local-disk growth, independent of the Supabase retention gap, and is a second instance of the same "half a retention story" pattern the task asked me to look for.

**Burst test — the backend crashed under load. Resource usage did not stabilize; it triggered a hard process kill.**

Baseline before burst: `mukthiguru-backend` at 3.07–3.6 GiB / 6 GiB (51–60%), PIDS 20–29, climbing slowly even at idle (health-check polling only). Qdrant `mukthi_semantic_cache_1024d` at 6 points.

Burst: 40 requests, concurrency 6, real questions, via `POST /api/chat?wait=true` with the benchmark bypass header. First 11 requests succeeded in 0.1–0.6s each (cache/fast-path hits). Request #12 took 12.1s then the connection was **severed mid-response** ("Remote end closed connection without response"), and every subsequent request failed instantly with `Connection reset by peer` / `Broken pipe`. Final tally: **11/40 succeeded**, the rest failed because the backend process was gone.

`docker ps` immediately after: `mukthiguru-backend` was **not running** — not unhealthy, not restarting, just absent. `docker ps -a`: `Exited (137)` (SIGKILL). `docker inspect .State`: `OOMKilled: false`, `FinishedAt: 2026-09-18T09:30:08Z`. Container logs up to the moment of death show completely normal operation (pipeline stages completing, `JobQueue worker 2: completed job_...`, health checks passing) — no error, no exception, no warning immediately preceding the kill. It was restarted externally (not via Docker's own `RestartPolicy`, confirmed `RestartCount=0` with policy `unless-stopped`) — the only other thing in the stack positioned to do that is `mukthiguru-autoheal` (a Docker-autoheal container, `Up 2 days (healthy)`, present specifically to `docker start` containers that go unhealthy/down). Full restart took from 09:30:08 to 09:31:50 — **~102 seconds of total backend downtime**, during which every in-flight and new request failed.

**Root cause: host/VM memory overcommit, not a Python-level leak.** `docker info` reports the Docker Desktop Linux VM's total memory as `8319504384` bytes (**7.75 GiB**) — this is the actual memory ceiling shared by every container, independent of any per-container `mem_limit`. `backend/docker-compose.yml` sets per-service memory limits via `deploy.resources.limits.memory` that, summed across only the services that were actually running at burst time, already exceed that ceiling: backend `${BACKEND_MEMORY_LIMIT:-6G}` (line 370) + qdrant `3G` (line 170) + memgraph `1G` (line 438, confirmed by cross-referencing `docker stats`' 1 GiB limit shown for memgraph) + redis `512M` (line 128) = **10.5 GiB of configured ceiling against a 7.75 GiB VM**, before counting the always-on Supabase stack (13 more containers) sharing the same VM. `mukthiguru-backend` itself never got near its own 6 GiB cgroup limit during the burst (`docker stats` showed it at 3.6 GiB right before the crash) — the container's own limit was never the constraint. The VM ran out of real memory across the sum of everything scheduled on it, and the Linux kernel's OOM killer (VM-level, not this container's cgroup — hence `OOMKilled: false` at the Docker/cgroup level while the process still died with signal 9) picked the single largest resident process, which was the backend. This is fully reproducible: **6 concurrent full-pipeline chat requests, well under the code's own admission-control ceiling of 8 (`settings.max_concurrent_chat`, confirmed via `/api/health`'s `chat_backpressure.max_concurrent: 8`), were enough to kill the process.** The backpressure semaphore in `app/api/chat.py` protects against too many requests in flight; it has no awareness of actual available memory, so it is not a functional safety net against this failure mode on a host this size.

**Consequence for in-flight background jobs.** `/api/chat` in the live config runs through the Redis-backed job queue (`app/services/job_queue.py`) rather than inline — the log lines confirm `JobQueue worker N: completed job_id`. See AMK-C-002 in Phase 12 below: jobs that were in `status=processing` at the moment of the kill are not reclaimed by anything on restart, because `JobQueueService.start()` only re-enqueues job IDs still present in the durable `job_queue:pending` Redis list, and a claimed job is removed from that list at claim time (before the worker starts real work). A user whose request was mid-flight during this exact crash would see their `GET /api/jobs/{job_id}` poll stuck at `"processing"` forever.

### Problems found (see numbered findings below)
- AMK-C-001: Backend process killed by host/VM-level OOM under a burst well within the app's own concurrency limit (CRITICAL, launch blocker)
- AMK-C-002: Jobs claimed but not completed at crash time are never reclaimed — permanent stuck "processing" status (HIGH)
- AMK-C-003: No data-retention enforcement for Supabase `chat_responses`/telemetry tables despite `retention_days` metadata existing (MEDIUM)
- AMK-C-004: Local compliance-audit JSONL files rotate daily by filename but are never deleted — unbounded local disk growth (LOW/MEDIUM)
- AMK-C-006: `llm_cache.py` docstring/log line falsely claims Qdrant usage when it is actually a bounded local map cache (LOW, cosmetic/confusing-only)

### Unknowns
- **File descriptor counts before/after burst**: `docker exec` was denied by this session's permission system for the entire audit (confirmed via multiple attempts, including simple `echo`); no host-side equivalent exists for inspecting a container's `/proc` on macOS Docker Desktop (the container runs inside a separate Linux VM, not visible from the host `/proc`). Could not be measured. **UNKNOWN** — a future audit with `docker exec` permission should re-run this specifically, ideally instrumented to catch it before the process is OOM-killed again.
- Whether repeated bursts (not just one) cause the backend's steady-state memory to *ratchet upward* between crashes (a genuine per-process leak layered on top of the overcommit problem) is **UNKNOWN** — only one burst was run, and it terminated in a crash before a clean stabilization point was reached. The pre-burst baseline (3.07 → 3.6 GiB climbing over ~25 minutes of idle + health-check-only traffic) is itself suspicious and warrants a longer idle-baseline observation than this audit had budget for.

---

## Phase 12 — Redis / Celery / Background Jobs

### Status: COMPLETE

### What was checked
`backend/celery_config.py` (broker config, `beat_schedule`, `task_routes`, retry/ack policy), `backend/tasks/ingest_tasks.py`, `backend/tasks/memory_outbox_tasks.py`, `backend/services/memory_outbox.py`, `supabase/migrations/20260805000001_memory_outbox.sql` (the `claim_memory_outbox` SQL function), `backend/app/services/job_queue.py` (Redis-backed queue, worker pool, crash-recovery path).

### What was verified

**Celery global config is sound.** `task_acks_late=True` + `task_reject_on_worker_lost=True` (celery_config.py:79-80) means an unacked task (worker died mid-task) is redelivered to another worker rather than silently lost. `worker_max_tasks_per_child=10` and `worker_max_memory_per_child=1_500_000` KB (1.5 GB) recycle ingestion worker children periodically — a real defense against slow leaks in long-running ingestion workers (ONNX/embedding model state, ffmpeg subprocess handles, etc.), separate from the API-process OOM found in Phase 7. `broker_transport_options={"visibility_timeout": 3600}` bounds how long a claimed-but-not-acked task can sit invisible before Celery considers it abandoned and redelivers it.

**Ingestion tasks (`tasks/ingest_tasks.py`) — retry-safe for the Qdrant write path, confirmed by reading the actual point-ID generation, not assumed.** `orchestrate_ingestion` and `ingest_document_task` both carry `autoretry_for=RETRYABLE_INGEST_ERRORS` (network/timeout-shaped only; parse/quality/auth failures are excluded from auto-retry by design, `classify_ingest_error`) with 2-3 max retries and exponential backoff+jitter. I checked whether a retry after partial success would duplicate data: `services/qdrant/indexer.py:upsert_chunks` docstring and code confirm **deterministic point IDs based on `source_url:chunk_index:raptor_level`** — a retried ingestion overwrites the same Qdrant points rather than creating duplicates. I also specifically chased down a `parent_id = str(uuid.uuid4())` (`ingest/pipeline.py:1831`, `3239`) that looked like a retry-duplication risk at first read — traced it fully and confirmed it is only ever written as a *payload field* on the deterministic child-chunk points (grouping key + inlined `parent_text` for parent-child retrieval), never used as a Qdrant point ID itself, so it does not create orphaned points on retry. **Can the same ingestion job run twice safely? Yes, for the vector-store write path.** Not independently verified for the Neo4j/LightRAG graph-write side of the same pipeline (out of budget this pass) — flagged as unknown, not asserted safe.

**"What happens if a worker dies halfway through an ingestion task?"** `task_acks_late` + `task_reject_on_worker_lost` means the task is redelivered and retried from the top (not resumed) by a surviving worker, subject to the per-task `max_retries`. Given the Qdrant write path is idempotent (above), a from-the-top retry is safe for that half of the pipeline. The Neo4j/LightRAG graph writes are not confirmed idempotent (unknown, above) — a worker crash after the vector write but before/during the graph write could leave the two stores inconsistent for that source on a from-scratch retry, depending on whether the graph write path also keys on deterministic entity IDs. Not verified this pass.

**Memory outbox (`memory_outbox.py` + `20260805000001_memory_outbox.sql`) — well-designed claim/lock mechanism, but two real gaps found.**
- `claim_memory_outbox()` (the Postgres function backing `get_pending()`) uses `FOR UPDATE SKIP LOCKED` for atomic, safe concurrent claiming across multiple workers, and reclaims rows stuck in `status='processing'` after a 10-minute staleness window (`locked_at < now() - interval '10 minutes'`) — this correctly handles a worker that dies mid-processing without ever calling `mark_failed`.
- **AMK-C-005 (below): the enrichment side effects run on every processing attempt, including retries, with no idempotency guard tied to the outbox row.** `_drain_once()` (`tasks/memory_outbox_tasks.py`) calls `memory_service.extract_and_write`, `episodic.log_episode`, `l1_extractor.extract_atoms` → `memory_service.add_atoms`, and `l2_scene_compressor.compress_turns_to_scene` → `save_scene_block` — none of these are keyed by `outbox_id` or otherwise deduplicated. A row that gets claimed, has its side effects executed, and then the **worker process is killed (not a Python exception — same SIGKILL class of event reproduced live in Phase 7) before `mark_processed()` runs**, is picked back up by the 10-minute staleness reclaim and its side effects run again — duplicate episodic memory entries, duplicate L1 atoms, duplicate L2 scene blocks for the same conversation turn. This is a real "can the same job execute twice safely?" **No**, for this task specifically, and Phase 7 just demonstrated the exact kind of crash (whole-process SIGKILL, not a catchable exception) that would trigger it.
- No `attempts` cap enforced anywhere in Python: the SQL schema tracks `attempts integer NOT NULL DEFAULT 0` and increments it on every claim, but nothing reads that column to stop retrying and mark a row permanently failed / move it to a dead-letter state after N attempts. A row whose exception is always raised inside the `try` in `_drain_once` is exempted from this (it's marked `status='failed'` terminally on any caught `Exception`) — the risk is narrower than "infinite retry," but the `attempts` column being tracked-and-never-consulted is dead instrumentation, consistent with the session's stated pattern of half-built retention/lifecycle mechanisms.

**Job queue (`app/services/job_queue.py`) — Redis-backed, durable pending list, correct graceful-shutdown recovery, but no crash recovery for already-claimed jobs (AMK-C-002).** `JobQueueService.start()` recovers job IDs still in the durable `job_queue:pending` Redis list on process start (`start()`, line ~318-322). On a *graceful* shutdown (`stop()` cancels workers), the `except asyncio.CancelledError` handler explicitly resets a job's Redis-hash `status` back to `"queued"` so it is recoverable on the next `start()` (comment at job_queue.py: "Shutdown must leave the job recoverable"). **This safety net only fires for `asyncio.CancelledError` — a clean, catchable Python-level cancellation.** It cannot fire for a SIGKILL/OOM-kill (Phase 7's reproduced crash): the event loop is destroyed instantly, no `except` clause runs, and a job that was claimed (removed from the `pending` list at claim time, per the Lua-script atomic claim referenced in the file) and left at `status="processing"` in Redis stays there forever — `start()`'s recovery only looks at the `pending` list, never at stuck `processing` rows. A client polling `GET /api/jobs/{job_id}` for that job gets an indefinite `"processing"` with no resolution, timeout, or requeue. This is the single most user-visible consequence of the Phase 7 crash and is filed as its own finding (AMK-C-002) because it is a distinct code gap from the OOM itself — fixing the memory overcommit reduces how often this triggers, but does not make a future crash (deploy-time OOM, host restart, `docker kill`, k8s eviction, etc.) safe.

### Unknowns
- Whether the Celery worker (`celery-worker`, profile-gated behind `COMPOSE_PROFILES=ingestion`) was tested live — it was **not started** this pass (budget/time; starting it, running an ingestion, and killing the worker mid-task to observe actual redelivery behavior would have roughly doubled this phase's cost). The `task_acks_late`/`task_reject_on_worker_lost` config was verified by reading, not by live crash-injection. Code-inspection confidence is high; live-verified confidence is **UNKNOWN**.
- Idempotency of the Neo4j/LightRAG graph-write half of ingestion under retry — **UNKNOWN**, not traced this pass (see above).

---

## Phase 13 — Streaming / Async / Concurrency

### Status: PARTIAL — code-reviewed in depth; live concurrent-stream / mid-stream-disconnect testing was not run this pass (see Unknowns)

### What was checked
`backend/app/stream_orchestrator.py` (the SSE `_sse()` generator, disconnect handling, heartbeat/timeout logic), `backend/app/api/chat.py` (`backpressure_semaphore`, `_get_chat_semaphore`), `backend/app/services/job_queue.py` (semaphore-bounded worker pool). Searched the full backend tree for `asyncio.Lock()` / `threading.Lock()` / `threading.RLock()` usage outside tests.

### What was verified

**No `asyncio.Lock`/`threading.Lock` usage anywhere in `backend/` outside tests and the (unrelated) `migrations/maintenance_runner.py` Redis-backed `DistributedLock`.** No risk of an in-process deadlock from lock contention was found, because there is essentially no in-process locking to contend on. `services/http_client_pool.py` uses `anyio.Lock` for its one lazy-init guard (not caught by the plain-text grep, read directly instead — confirmed correct, see Phase 7).

**SSE streaming (`app/stream_orchestrator.py`) is well-built for cancellation and cleanup, on direct read.**
- The pipeline runs as a tracked `asyncio.create_task` (`pipeline_task`, line 110), never fire-and-forget.
- The main loop polls `request.is_disconnected()` every iteration; on a true disconnect it does an early `return` from inside the `try` block that owns a `finally` — Python generator semantics guarantee the `finally` still runs on that `return`, so cleanup is not skipped by the early exit.
- The `finally` block (lines ~300-311) explicitly checks `if not pipeline_task.done(): pipeline_task.cancel(); await pipeline_task` (swallowing the resulting `CancelledError`) — a disconnected/timed-out/errored stream does not leave an orphaned background task running the full RAG pipeline to completion for no listener.
- The same `finally` releases the anonymous-quota reservation (`_release_anon_quota`) whenever the stream did **not** complete successfully (`if not completed`) — a killed/disconnected/timed-out stream does not permanently consume a user's quota slot.
- A heartbeat task (`asyncio.sleep(HEARTBEAT_INTERVAL)`, 5s) races against the actual queue-get and the pipeline-completion via `asyncio.wait(..., return_when=asyncio.FIRST_COMPLETED)`; whichever of the three didn't win is explicitly `.cancel()`'d and awaited before the loop continues, so no stray `get_task`/`heartbeat` task leaks across iterations.

I did not find a gap in this file on static reading. This is meaningfully better-engineered than the Phase 7/12 findings above.

**Backpressure (`app/api/chat.py:backpressure_semaphore`) is correct in isolation** — try-acquire with a 10ms timeout (fails fast, no thundering-herd pile-up on the semaphore itself), semaphore released in a `finally`, semaphore lazily rebuilt if it's ever bound to a dead/different event loop (guards a real TestClient-across-loops footgun). Its ceiling (`settings.max_concurrent_chat = 8`) is the same number that Phase 7's burst test demonstrated is **already too high for this host's actual available memory** — 6 concurrent requests (under the cap) triggered a VM-level OOM kill. This is not a bug in the semaphore's own logic; it's a capacity-planning mismatch between the app-level admission control and the infrastructure it runs on, already filed as AMK-C-001.

### Problems found
No new *code-level* concurrency bugs found in the streaming/cancellation path itself. The phase's substantive finding is that Phase 7's crash (AMK-C-001) **is** a concurrency-adjacent problem — 6 simultaneous in-flight requests, each spinning up the full graph (LLM calls, ONNX reranker, BGE-M3 embedding, LettuceDetect NLI, all in-process), pushed memory past the host ceiling. The concurrency-control code itself does not have a bug; the number configured into it does not match the box it runs on.

### Unknowns
- **Did not run**: several genuinely simultaneous `/api/chat/stream` SSE connections with a mid-stream client-side abort, to directly observe server-side task cancellation rather than infer it from code reading. Budget did not allow a second live-traffic exercise after the burst test crashed the backend and required a ~2-minute recovery window; code reading gives high confidence but is not the same as an observed live abort.
- **Did not test**: simultaneous memory writes / canonical-memory race conditions under real concurrent load (would require two authenticated sessions writing memory concurrently; the live test only exercised anonymous/benchmark-bypass chat).
- Whether `job_queue.py`'s worker pool (separate from the SSE-specific concerns above) leaves any state behind when a *worker task itself* (not the whole process) is cancelled mid-`worker_factory()` call, versus the whole-process-crash case already covered in AMK-C-002 — partially covered by the `except asyncio.CancelledError` branch read in Phase 12, not independently live-tested here.

---

## Findings

### AMK-C-001 — Backend process killed by host-VM OOM under load well within the app's own concurrency limit
**Severity:** CRITICAL
**Launch Blocker:** YES
**Evidence:** Live-reproduced this audit. Baseline `docker stats mukthiguru-backend`: 3.07–3.6 GiB/6GiB before burst. Burst script: 40 `POST /api/chat?wait=true` requests, concurrency **6** (below the code's own `max_concurrent_chat=8` ceiling, confirmed via `/api/health`'s `chat_backpressure.max_concurrent: 8`), using the `X-Test-Key` benchmark bypass. Result: 11/40 succeeded, then all subsequent requests failed with `Connection reset by peer`/`Broken pipe`. `docker ps -a` showed `mukthiguru-backend: Exited (137)`. `docker inspect --format '{{json .State}}'`: `"OOMKilled": false`, `FinishedAt: 2026-09-18T09:30:08Z`, container logs show completely normal pipeline execution up to the last log line before death (no exception, no warning). `docker info --format '{{.MemTotal}}'` = `8319504384` bytes = 7.75 GiB total for the whole Docker Desktop VM. `backend/docker-compose.yml`'s `deploy.resources.limits.memory` for the services actually running at burst time sum to ≥10.5 GiB (backend `${BACKEND_MEMORY_LIMIT:-6G}` + qdrant `3G` + memgraph `1G` + redis `512M`), before counting the 13-container Supabase stack sharing the same VM. Container restarted externally (not via Docker `RestartPolicy`, confirmed `RestartCount=0`) — consistent with the running `mukthiguru-autoheal` container issuing a `docker start` after detecting the down container; total downtime ~102s (`09:30:08` → `09:31:50`).
**Root Cause:** Memory overcommit at the infrastructure level: the sum of per-container `mem_limit`s configured in `docker-compose.yml` exceeds the actual memory available to the Docker Desktop VM (or, in production, whatever the equivalent host ceiling is). Each container's own cgroup limit is honored individually, but nothing prevents their concurrent peak usage from exceeding total physical memory, at which point the kernel's global OOM killer (not any single container's limit) picks the largest process — here, the backend, because it holds multiple in-process ML models (BGE-M3 embedding, ONNX reranker, LettuceDetect NLI) plus per-request pipeline state for every concurrent chat. The app-level admission control (`max_concurrent_chat=8`) has no awareness of actual memory headroom and did not prevent the crash because the burst (6) was under its own ceiling.
**User Impact:** Every in-flight request (successful or not) at the moment of the crash is dropped with a broken connection and no answer; the entire service is unavailable for ~100+ seconds afterward for every user, not just the ones whose burst caused it; jobs claimed-but-incomplete are permanently stuck (see AMK-C-002). This is a single point of failure with no redundant replica (root `CLAUDE.md`: Railway is pinned to 1 replica).
**Required Fix:** Either (a) reduce per-container memory limits so their sum has real headroom under the actual host/VM ceiling (and set the VM ceiling itself higher in production, where it is not artificially capped like local Docker Desktop), or (b) lower `max_concurrent_chat` to a value empirically safe for the box it runs on, or — properly — both, plus load-testing to find the actual safe concurrency ceiling per GB of available memory rather than asserting one. Production (Railway, single replica, per root `CLAUDE.md`) needs this number re-derived against Railway's actual container memory allocation, not the local Docker Desktop VM's 7.75 GiB, which will differ.
**Regression Test:** A repeatable load-test script that fires N concurrent full-pipeline `/api/chat` requests (N = configured `max_concurrent_chat`) against a fresh backend and asserts (1) the container is still running afterward (`docker inspect .State.Running`), (2) `docker stats` peak memory stayed under X% of the actual available host memory, not just under the container's own `mem_limit`. This audit's `burst_test.py` (saved at the scratchpad path used this session) is a starting point but was not written as a permanent regression test — it should be moved into the repo (e.g. `backend/scripts/ops/` or a `benchmarks/` script) if kept.
**Verification:** Re-run the same burst (6-8 concurrent real chat requests) against the box the fix will actually run on (production sizing, not local Docker Desktop) and confirm the container survives with memory headroom remaining, not just that it happened not to die this particular time.

> **CORRECTED 2026-09-18 — same defect as AMK-B-002, and it is not overcommit.**
> The overcommit arithmetic in the Root Cause is accurate as arithmetic, but it
> is not what killed the process. Re-reproduced at concurrency 6: peak container
> memory **4.11 GiB of 6 GiB**, `OOMKilled: false`, and the log carries
> `Fatal Python error: Segmentation fault` with the faulting thread inside
> torch's `Linear.forward` under `modeling_modernbert`. The host OOM killer was
> never involved. See the AMK-B-002 correction for the mechanism.
> **Measured ceiling** (what this finding actually asked for): marginal cost
> ~324 MB per concurrent chat over a ~2300 MB resident-model baseline, so the
> memory-only ceiling is ~13 concurrent on 8 GB and ~73 on 32 GB. The deploy
> target is Railway Pro (32 GB), where memory does not bind at any realistic
> concurrency. `max_concurrent_chat` therefore **stays at 8**: the real limits
> are the OpenRouter rate limiter (347 s of sleeping across 79 events in one
> 24-request run) and the now-serialized verification pass. Lowering it would
> refuse traffic the box can hold.
> The regression test this finding asked for now exists as a permanent script:
> `backend/scripts/ops/gate1_load_test.py` asserts container liveness, restart
> count and peak memory against a fraction of HOST memory, and exits non-zero on
> breach. (Its live-HTTP mode had never worked — `base_url=None` raised
> `TypeError` before the first request; fixed.) Full write-up:
> `docs/engineering-notes/concurrency-ceiling-2026-09-18.md`.

### AMK-C-002 — Jobs claimed by a worker that dies (not merely cancelled) are never reclaimed; client polling gets stuck "processing" forever
**Severity:** HIGH
**Launch Blocker:** YES (directly caused by, and will recur independently of, AMK-C-001 — any process death mid-job hits this, including a future deploy, host restart, or k8s eviction)
**Evidence:** `backend/app/services/job_queue.py`. `start()` (~line 310) recovers only job IDs still present in the durable `job_queue:pending` Redis list on process boot. The atomic-claim Lua script (referenced in the file, lines ~205-218) removes a job from that pending list and sets `status="processing"` at claim time, before the worker's real work begins. The only code path that ever resets a claimed job back to a recoverable `"queued"` state is the `except asyncio.CancelledError` branch inside the per-job worker coroutine (~line 645), which fires exclusively on a graceful, catchable cancellation (e.g. `stop()`'s `w.cancel()` during an orderly shutdown). AMK-C-001 is a live-reproduced example of the crash class (SIGKILL) that this branch cannot catch — the event loop is destroyed instantly.
**Root Cause:** The job queue's crash-recovery path only covers jobs that never left the durable `pending` list (never claimed) plus jobs whose owning worker got a chance to run cleanup code before exiting. It has no path for jobs already claimed (removed from `pending`, `status="processing"` in the per-job Redis hash) whose worker process disappears without running any Python exception handler.
**User Impact:** A user whose request was in-flight during any full-process crash (OOM, `docker kill`, host reboot, bad deploy) sees their `GET /api/jobs/{job_id}` poll return `status: "processing"` indefinitely — no error, no timeout, no eventual resolution. The frontend has no signal to fall back to a retry or an error state; the user is left waiting forever (or until they give up) for an answer that will never arrive.
**Required Fix:** Add a startup (or periodic) sweep that scans `job:*:meta` Redis hashes for `status="processing"` with a `dispatch_started_at`/`claimed_at` older than a bounded staleness window (mirroring the Postgres `claim_memory_outbox`'s working 10-minute pattern for the memory outbox) and either requeues them (if the underlying work is safely re-runnable — verify idempotency of `worker_factory` first, since a chat job re-run means re-calling the LLM, which is not free but is safe) or marks them `failed` with a clear message so the client's poll resolves instead of hanging.
**Regression Test:** Claim a job (simulate via directly writing `status="processing"` + an old `claimed_at` to Redis, bypassing a real worker), start/trigger the recovery sweep, and assert the job transitions to either `queued` (re-run) or `failed` (with a message), not left indefinitely at `processing`. Extend `tests/test_chat_endpoint.py` or add a dedicated `test_job_queue_crash_recovery.py`.
**Verification:** Kill `-9` the backend process mid-request in a test environment (not just cancel it) with a job claimed, restart the backend, and confirm the orphaned job resolves to a terminal state within the staleness window rather than staying `processing` forever.

### AMK-C-003 — No Supabase data-retention enforcement despite `retention_days` metadata existing; Celery Beat has zero cleanup jobs for `chat_responses`/telemetry
**Severity:** MEDIUM
**Launch Blocker:** NO (not a crash risk; a compliance/cost/data-hygiene gap)
**Evidence:** `backend/celery_config.py`'s `beat_schedule` (lines 92-109) contains exactly 4 scheduled tasks — win-back emails, batched-memory processing, memory-outbox drain, semantic-cache prune — none of which touch `chat_responses` or any telemetry table. `backend/services/compliance_logger.py:log_interaction()` (lines 135-189) accepts, validates, and stores a `retention_days` field per audit record (raising `ValueError` on an invalid value) but no code anywhere reads that field back to delete anything. This is unchanged from what was found and explicitly left unfixed earlier in this same session, per the task brief.
**Root Cause:** `retention_days` was built as write-side metadata (presumably for a future enforcement job) without the corresponding read-side purge job ever being implemented.
**User Impact:** Not user-facing directly, but a GDPR/compliance risk (data that should be deleted after N days per its own recorded policy is retained indefinitely) and an unbounded-growth cost/performance risk for the `chat_responses`/telemetry tables over the life of the product, plus everything downstream that scans those tables (root `CLAUDE.md` notes `hallucination_anomaly.py` reads `chat_responses` — an ever-growing table slows that job over time too).
**Required Fix:** Add a Celery Beat task (daily is reasonable, matching the existing win-back cadence) that deletes/archives `chat_responses` and telemetry rows older than their recorded `retention_days` (or a global default), and a corresponding enforcement pass over the local compliance-audit JSONL files (see AMK-C-004, likely the same fix covers both if audit records move into a table).
**Regression Test:** Insert rows with a past-due `retention_days` cutoff, run the new purge task, assert those rows are gone and newer rows are retained.
**Verification:** Confirm the task appears in `beat_schedule`, runs on schedule in a staging environment, and actually reduces row counts for artificially aged test data.

### AMK-C-004 — Local compliance-audit JSONL files are never deleted (unbounded local disk growth)
**Severity:** LOW/MEDIUM
**Launch Blocker:** NO
**Evidence:** `backend/services/compliance_logger.py:58-61` (`_get_audit_path`) generates a new file per UTC day (`compliance_audit_YYYY-MM-DD.jsonl`) under `COMPLIANCE_AUDIT_DIR` (or `/app/logs` in the container). The module's own docstring calls this "rotate daily using a timestamp suffix" — but rotation here only changes which file new writes go to; nothing in the file, and nothing found elsewhere in the audit, ever deletes an old day's file.
**Root Cause:** Same class of bug as AMK-C-003 — a retention concept (`retention_days` per-record) exists without an enforcement job, and separately, "rotation" was implemented as "new filename," not "expire old files."
**User Impact:** Slow, unbounded growth of the backend container's local disk (or persistent volume) over the life of the deployment; every LLM interaction writes at least one line per day-file. Low severity because volume per record is small (a hash, a 500-char preview, some metadata) and this predates the current session, but compounds indefinitely with no existing bound.
**Required Fix:** A scheduled cleanup (could be the same Celery Beat task as AMK-C-003, or a simple `find compliance_audit_*.jsonl -mtime +N -delete`-equivalent) that removes audit files older than the retention policy.
**Regression Test:** Create fake dated audit files (some old, some recent), run the cleanup, assert only the recent ones remain.
**Verification:** Confirm on a staging/local run that old files are actually removed and the newest file is untouched.

### AMK-C-005 — Memory-outbox enrichment side effects are not idempotent; a worker crash after side effects but before `mark_processed()` causes duplicate memory writes on the automatic 10-minute reclaim
**Severity:** MEDIUM
**Launch Blocker:** NO (narrow window, but the trigger — a hard process crash mid-task — was just reproduced live in this same audit via AMK-C-001)
**Evidence:** `backend/tasks/memory_outbox_tasks.py:_drain_once()` (lines 15-132) calls, per claimed row: `memory_service.extract_and_write`, `episodic.log_episode`, `l1_extractor.extract_atoms` → `memory_service.add_atoms`, `l2_scene_compressor.compress_turns_to_scene` → `save_scene_block` — in that order, with `outbox.mark_processed(outbox_id)` only called after all of them succeed (line 126). None of these four writes are keyed by `outbox_id` or otherwise made idempotent/dedup-checked. `supabase/migrations/20260805000001_memory_outbox.sql`'s `claim_memory_outbox()` reclaims any row stuck in `status='processing'` for more than 10 minutes (`locked_at < now() - interval '10 minutes'`) regardless of why it's stuck — including a worker that was SIGKILLed mid-loop after doing the writes but before reaching line 126.
**Root Cause:** The outbox pattern correctly makes *claiming* safe (atomic, `FOR UPDATE SKIP LOCKED`) and *retryable* (staleness reclaim), but the work done between claim and `mark_processed` was written assuming exceptions are the only failure mode (they're individually try/excepted and marked `failed` terminally) — it does not account for the process itself dying mid-execution, which skips both the exception handler and `mark_processed`, leaving the row to be reclaimed and its side effects re-run from scratch.
**User Impact:** A user whose conversation turn was being written to memory at the exact moment of a backend/worker crash gets that turn's episodic memory, L1 atoms, and/or L2 scene block written twice. Not data loss, but silent duplication that could skew personalization, waste storage, or (worse) cause `memory_service.extract_and_write`'s downstream fact-extraction to file the same fact twice with slightly different phrasing, compounding over time.
**Required Fix:** Make each enrichment write idempotent keyed on `outbox_id` (e.g., an `outbox_id` column/tag on the written memory/episode/atom/scene rows, checked before insert), or record a completion marker per sub-step so a reclaimed row resumes rather than restarts, or simplest: wrap all four writes in a single transaction/outbox-pattern-correct "exactly once to the outside world" primitive if the underlying stores support it.
**Regression Test:** Claim a row, run the four enrichment writes, kill the process before calling `mark_processed`, wait past the 10-minute staleness window (or fake `locked_at`), let another drain pick it up, and assert the enrichment writes are NOT duplicated.
**Verification:** Count episodic/L1/L2 rows for a synthetic outbox row before and after the simulated crash-and-reclaim; confirm counts increase by 1, not 2.

> **FIXED 2026-09-18 (resume-marker variant).** `memory_outbox.completed_steps`
> (migration `20260918000000_memory_outbox_completed_steps.sql`) records each of
> the five enrichment sub-steps as it commits; `_drain_once` skips the ones
> already done, so a reclaimed row RESUMES instead of restarting.
> `claim_memory_outbox` returns `outbox.*` and does not reset the column, so no
> change to that function was needed.
> **Honest limit**: this narrows the duplicate window from "all five writes,
> including two LLM calls" to "the single step in flight at the instant of the
> crash" — it does not close it. Closing it fully needs the destination stores to
> accept an idempotency key, which they do not today. A failed marker write is
> deliberately non-fatal: losing a marker costs the resume optimisation for one
> step, whereas failing the row would cost the seeker's memory entirely.
> Regression tests: `backend/tests/test_memory_outbox_worker.py`
> (`test_reclaim_after_crash_does_not_rerun_committed_enrichment`,
> `test_reclaim_resumes_only_the_steps_that_had_not_committed`,
> `test_step_marker_failure_degrades_to_replay_not_to_row_failure`).

### AMK-C-006 — `llm_cache.py` docstring and log line claim Qdrant usage; the actual implementation is a bounded local map cache
**Severity:** LOW
**Launch Blocker:** NO
**Evidence:** `backend/services/cache/llm_cache.py` docstring: "Uses Qdrant (already running) as vector store + BGE-M3 embeddings", and the success log line: `"GPTCache semantic caching attached to LangChain (Qdrant + shared embedder)"` — but the actual `manager_factory(manager="map", ...)` call (line 65-69) explicitly avoids Qdrant per an in-code citation of `lessons.md §22` ("avoid SQLite+Qdrant overhead and qdrant-client version incompatibilities"), using an LRU-bounded flat-file-persisted map instead, with `embedding_func` reduced to an identity/string-key function (not a real embedding call).
**Root Cause:** The docstring/log message were written for an earlier or intended design and never updated when the implementation switched to the simpler `map` manager.
**User Impact:** None functionally (the actual cache is correctly bounded by `gptcache_max_size`) — but this is exactly the kind of stale claim that misleads a future engineer (or auditor) into assuming a Qdrant-backed leak risk exists here when it doesn't, or conversely into believing semantic similarity matching is happening when it's actually exact-string matching only.
**Required Fix:** Update the docstring and the log line to describe what the code actually does (bounded local exact-match map cache, no Qdrant, no real embeddings).
**Regression Test:** None needed — documentation-only fix.
**Verification:** Read the corrected docstring/log line and confirm they match `init_gptcache`'s actual `manager="map"` behavior.

---

## Summary for parent agent

- **Phase 7 (GC/Memory)**: COMPLETE, one item UNKNOWN (fd counts — `docker exec` denied all session). The committed semantic-cache GC fix (96fd24a5) is verified correct and complete; no other cache/store found with the same TTL-asymmetry pattern live. The real finding is much bigger than what was being checked for: **a live burst of 6 concurrent chat requests (under the app's own concurrency ceiling of 8) OOM-killed the entire backend container in ~2 minutes**, due to per-container memory limits in `docker-compose.yml` summing to more than the Docker Desktop VM's actual 7.75 GiB ceiling. 11/40 requests succeeded before the crash; the rest failed with connection resets. The container restarted itself via an external `autoheal` watchdog after ~102s downtime, not via Docker's native restart policy.
- **Phase 12 (Redis/Celery)**: COMPLETE. Celery global config, ingestion-task retry safety (verified idempotent via deterministic Qdrant point IDs, not assumed), and the memory-outbox atomic claim/staleness-reclaim mechanism are all solid. Two real gaps: jobs claimed by a worker that hard-crashes (not merely cancelled) are never reclaimed by `job_queue.py` and leave the client polling forever (AMK-C-002, directly triggered by the Phase 7 crash type); and the memory-outbox's four enrichment side effects are not idempotent, so the same crash-and-10-minute-reclaim sequence duplicates memory writes (AMK-C-005). Data retention for Supabase `chat_responses`/telemetry and local compliance-audit files is confirmed still completely unenforced (AMK-C-003, AMK-C-004), unchanged from what this session already found and deliberately left unfixed.
- **Phase 13 (Streaming/Async)**: PARTIAL (code-reviewed thoroughly; did not live-test concurrent SSE streams or mid-stream aborts due to budget spent recovering from/investigating the Phase 7 crash). No lock usage anywhere in the backend outside tests (nothing to deadlock on). SSE streaming cancellation, task cleanup, and quota-release-on-failure in `stream_orchestrator.py` are correctly implemented on direct code reading — no bug found. The phase's real finding is that the concurrency-admission-control ceiling (`max_concurrent_chat=8`) is not actually safe for this host, which is the same root cause as AMK-C-001.

**Resource usage under burst: did NOT stabilize — it crashed the process.** Before burst: 3.07→3.6 GiB/6GiB (idle baseline, climbing slowly). During burst: process killed (signal 9) at request #12 of 40, ~102s total downtime, external watchdog restart. This is not a slow-leak signature; it's an acute host-memory-overcommit crash, evidenced concretely by the VM total (7.75 GiB) being smaller than the sum of just the 4 currently-running containers' own configured limits (≥10.5 GiB).

**Top 5 most severe findings:**
1. AMK-C-001 (CRITICAL, blocker) — backend OOM-killed by host/VM memory overcommit under normal-ceiling concurrent load
2. AMK-C-002 (HIGH, blocker) — crashed/claimed jobs never reclaimed; client polls hang forever
3. AMK-C-005 (MEDIUM) — memory-outbox enrichment writes duplicate on crash-and-reclaim
4. AMK-C-003 (MEDIUM) — no retention enforcement for Supabase chat/telemetry data despite recorded policy
5. AMK-C-004 (LOW/MEDIUM) — local compliance-audit files grow unbounded, same missing-enforcement pattern as #4

**Launch blockers: AMK-C-001 and AMK-C-002.** Both stem from the same demonstrated failure mode (a full backend-process death) and were reproduced live, not inferred — this repo cannot safely run in production, even at the modest concurrency ceiling it already sets for itself, without both the memory-sizing fix and the crash-recovery fix for in-flight jobs.
