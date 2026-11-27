# Scaling and efficiency audit, 2026-11-27

Scope: backend and frontend, for many concurrent users on one Railway container at the lowest cost.
Method: static reading of the code at the cited lines, micro-benchmarks run on a Mac against the
backend venv, and unit tests. **Nothing here was measured against the live stack or on Linux**; the
RSS figures below are macOS `ps` RSS and will differ on Linux. "Measured" means measured in this
worktree; "not measured" means it needs the live stack.

Platform facts this audit relies on (checked 2026-11-27):

- Railway counts any outbound packet as activity, including private-network requests to other
  services, database connections and the replies to inbound requests; a service is inactive after 5
  minutes without packets ([Railway: app sleeping](https://docs.railway.com/reference/app-sleeping)).
- Railway moves traffic to a new deployment as soon as the healthcheck returns 2xx, and runs
  healthchecks only at the start of a deployment, with a default 300 s timeout
  ([Railway: healthchecks](https://docs.railway.com/deployments/healthchecks)).
- Each Uvicorn worker is a separate process with its own copy of every model; on container platforms
  the documented pattern is one process per container
  ([FastAPI: deployment concepts](https://fastapi.tiangolo.com/deployment/concepts/)).
- Uvicorn's `--loop` and `--http` default to `auto`, and `--backlog` to 2048, `--timeout-keep-alive`
  to 5 s ([Uvicorn: settings](https://uvicorn.dev/settings/); the page does not say what `auto`
  picks). The installed uvicorn's `loops/auto.py` and `protocols/http/auto.py` choose uvloop and
  httptools when they import, and both import in the backend venv, so no loop/http setting is needed.

## Ranked findings

Severity: **M** = money, **A** = availability, **L** = latency. "Fixed" = changed in this branch.

| # | Sev | Finding | Evidence | Status |
|---|-----|---------|----------|--------|
| 1 | A, M | `/healthz` answers 200 during a 180 s grace even though the real app is not loaded, so Railway switches traffic to a container that answers every chat with 503 | `backend/start_railway.py:630-642` (`within_grace` -> `healthy = True`); `backend/app/api/chat.py:586-596` (`_reject_if_queue_unattended`, called at `:921` and `:1263`, -> 503 "Service is still starting") | **Proposed** (file owned by another agent), patch below |
| 2 | A, M, L | Public `/api/health`, `/health`, `/api/health/services` run the full deep probe on every call even for anonymous callers: Qdrant ping, Redis connect+ping, Memgraph query, an outbound LLM-provider ping, and an embedding encode on the 2-thread embedding pool. The frontend calls it on every page mount (`src/hooks/useBackendHealth.ts:14`); bots hit it freely | `backend/app/api/health.py` `_build_health_response` (qdrant `:335`, redis `_check_redis`, `_llm.health_check()`, embedding `_probe_async`); no limiter on the route | **Fixed**: one shared probe per `HEALTH_PUBLIC_CACHE_TTL_S` (default 10 s); token callers always get a fresh deep probe |
| 3 | A | `GET /api/kg/subgraph` is public, `async def`, and ran a synchronous Bolt query (`toLower(n.entity_id) CONTAINS $q` full scan) on the event loop. On one worker that stalls every chat | `backend/app/api/kg.py:494-528` (before) | **Fixed**: query runs on its own 2-worker pool (`_KG_EXECUTOR`), not asyncio's default executor, which the `start_railway.py` canary watches |
| 4 | M | Telemetry consumer wakes the whole day: `GET telemetry:stream:last_id` + `XREAD BLOCK 5000` + `sleep(1)` every ~6 s idle = about 20 Redis commands a minute, forever. This alone defeats Railway sleeping | `backend/app/telemetry_sink.py:610-680` (before) | **Fixed**: cursor kept in memory, one blocking read per wait, wait `TELEMETRY_WORKER_BLOCK_MS` (default 8000): about 7.5 commands a minute. See "Can the service ever sleep" |
| 5 | M | Relevance scorer: one Haiku call per evaluated context, k = 3..12 (default sizing 4-7) plus retries, plus distress check. All k are scored even when only the first passing context is used, and the client-side RPM limiter sleeps inside the scorer deadline | see "First-person LLM call count" below | **Report only** (gate semantics) |
| 6 | L | Answerability gate (1 LLM call) runs after HyDE (1 LLM call) and retrieval, not beside them; the prefetch flag exists but is off | `app/config.py:558` (`first_person_answerability_prefetch_enabled = False`); `first_person_bridge.py:1392-1403` | **Recommend** enabling after a graded run |
| 7 | L, M | Signed-in seekers: an admin-role lookup per user every 90 s (Supabase client build + session call + REST query); a "not admin" answer is cached no longer than an "is admin" one | `backend/services/auth_service.py:509-545` | **Fixed** (setting, default unchanged): `ADMIN_ROLE_NEGATIVE_CACHE_TTL_S`, recommend 600 |
| 8 | M | `/api/capabilities` is polled by every page load and 459 times an hour by bots; every call rebuilt the manifest (`shutil.which("ffmpeg")`, OCR probe) and sent no cache headers | `backend/app/api/capabilities.py` (before) | **Fixed**: in-process render, `Cache-Control: public, max-age=60`, `ETag`/304 |
| 9 | M | `ingest/raptor.py` imported scikit-learn (and scipy) at module load, so every serving process paid it though only ingestion clusters | `backend/ingest/raptor.py:31-32` (before); import-time chain measured below | **Fixed**: lazy import |
| 10 | M | Retracted. An earlier draft said the whole `*.railway.app` default domain is allowed and added a setting to drop it. Wrong: Starlette's `TrustedHostMiddleware` treats only a `*.x` pattern as a wildcard, so the `.railway.app` entry in `app/main.py` matches that exact host only; `foo.up.railway.app` already gets 400 and `healthcheck.railway.app` gets 200 (checked with a TestClient, now a test of the current behaviour) | `app/main.py:1141-1146`; `tests/test_scaling_audit_2026_11_27.py::test_trusted_host_dot_prefix_is_not_a_wildcard` | **Already rejected; setting removed.** The default-domain scanner traffic seen on `/api/capabilities` therefore reached an allowed Host: re-check which Host values the live `ALLOWED_HOSTS` permits (read it from the Railway variable, read-only) and do not widen the allowlist. Do not switch to `*.railway.app` |
| 11 | L | `POST /api/search/web-discourse` is public with no request limiter | `backend/app/api/search_routes.py:273` (before) | **Fixed**: same per-IP limiter as its siblings |
| 12 | L | Per-chat Redis client: `_increment_turn_counter` built, connected, authenticated and closed a client on every non-incognito chat, and read `REDIS_URL` from `os.environ` | `backend/app/orchestrator.py:746-768` (before) | **Fixed**: one pooled client from `settings.redis_url` |
| 13 | M | Unbounded in-process state: `TTLRateLimiter._store` (nothing ever called `clear_expired`), `TokenBucketMiddleware._local_buckets`, `AnonQuotaRedisAdapter._degraded_sessions` grow with every distinct client | `app/security_utils.py:268-298`, `app/middleware/rate_limit.py:~110`, `services/anon_quota_redis.py:115-120` | **Fixed**: sweep above 10,000 keys, at most once a minute (limiter), so a flood costs one scan a minute |
| 14 | L | Sync Qdrant calls inside `async def` (second brain vault, canonical memory batch) | AST scan, see below | **Fixed** (`asyncio.to_thread`, millisecond calls; a dedicated pool would be stricter) |
| 15 | L | Enrichment window walks parents one after another, each with a 1.5 s deadline (worst case max_clips x 1.5 s). Flag is off in code, `.env.example` and the IaC, on in `docker-compose.graded.yml` | `backend/services/first_person_pipeline.py:~3030` (before) | **Recommend, not changed**: see below |
| 16 | L | `/api/chat/title` makes one LLM call per new conversation and consumes one anonymous-quota unit (a 5-message anonymous allowance buys fewer conversations) | `backend/app/api/chat.py:681-732` | **Recommend**: derive the title locally for anonymous users |
| 17 | L | Chat payload carries `node_timings`, `retrieval_metadata`, `evaluation_trace`, `kg_concept_nodes`, `daily_practice_card`; none is read by `src/` (grep). Eval tooling does read the first three, so they are not provably unused | `backend/app/schemas/__init__.py:345-` | **Not changed**; size not measured. Add a setting before stripping |
| 18 | M | HyDE cache holds up to 1000 vectors as Python float lists, about 33 KB each, about 33 MB at the cap; embedding cache likewise | `first_person_bridge.py:81-103`; `services/embedding_service.py:196` | Not changed. `array('f')` is 8x smaller; `EMBEDDING_CACHE_SIZE=256` is the cheap knob |
| 19 | M | Memory at import: 387-393 MB vs 457-473 MB before finding 9 (macOS RSS, three runs each) | see below | partly fixed; the rest is needed |
| 20 | A | Frontend is fine: poll backoff exists (`src/lib/chat/transport.ts:219`), capabilities cached 24 h in localStorage, initial load 487 KB gzip over 16 files | measured from `npm run build` | no change |

## Evidence and numbers

### 1. Readiness (proposal)

`/api/healthz` is handled by the wrapper before the real app loads. Inside `_GRACE_SECONDS = 180` it
returns 200 unconditionally (`start_railway.py:630-642`). Railway treats the first 2xx as "deployment
healthy" and routes traffic to it. The real app is imported in a thread and the wrapper forwards
requests to it as soon as `_real_app` is set (`start_railway.py:526-528, 662-668`); until
`startup_complete`, `/api/chat` answers 503 with `Retry-After: 15` and `/api/capabilities` answers 503
`ready:false`. So during every rolling deploy, users are routed to a container that cannot answer, for
roughly the boot time (the wrapper's own comment says about 25 s to import; lifespan budgets are up to
180 s for background init and 120 s for LightRAG).

The comment at `start_railway.py:79-85` argues the grace is needed so Railway does not kill a booting
replica. Per Railway's docs a failing healthcheck during the deploy window only retries until the
timeout (330 s in `.railway/railway.ts`) and then fails the deploy, which leaves the old container
serving. That is the behaviour wanted here.

**Applied 2026-11-27 (default OFF; set `HEALTHZ_REQUIRE_READY=true` to enable).** Five tests in
`backend/tests/test_healthz_grace_masking.py` drive the real ASGI app for both branches. Opt-in so the
default is unchanged until the owner enables it. The same readiness test must apply in **both** branches
of the handler, inside the grace window and after it; gating only the grace branch leaves the
post-grace branch (`start_railway.py:~644`, `healthy = _lifespan_startup_done and not heartbeat_stale
and not executor_stale`) ignoring `startup_complete`, so a boot whose background init timed out would
still report 200 at about 180 s.

```python
# near the other module constants
_READY_GATE = os.environ.get("HEALTHZ_REQUIRE_READY", "").strip().lower() in {"1", "true"}


def _app_ready() -> bool:
    """True once the real app finished startup. Never imports: this runs on the loop while
    _run_real_lifespan imports the app in a thread, so read the module only if already loaded."""
    deps = sys.modules.get("app.dependencies") if _real_app is not None else None
    return _lifespan_startup_done and bool(getattr(deps, "startup_complete", False))


# in the /api/healthz branch
elif within_grace:
    healthy = _app_ready() if _READY_GATE else True
else:
    heartbeat_stale = ...   # unchanged
    executor_stale = ...    # unchanged
    healthy = (
        _lifespan_startup_done
        and not heartbeat_stale
        and not executor_stale
        and (_app_ready() if _READY_GATE else True)
    )
```

`_lifespan_startup_done` alone is not enough: the lifespan yields even when background init timed out
or raised (`app/main.py:1016-1022` sets `startup_error` and carries on), and `startup_complete` is
set only at `app/main.py:785`, at the end of the successful init body.

What happens with the gate on (from the code and Railway's docs, not run):

- Normal boot: 503 until init finishes, then 200; Railway activates the new deployment only then, and
  the old container keeps serving until that moment.
- Boot slower than the 330 s deploy timeout (`.railway/railway.ts`): healthz never turns 200 in time,
  Railway marks the deploy failed and the old container keeps serving. Keep `_GRACE_SECONDS` (180)
  below 330; with the gate it no longer hides anything.
- Background init timeout (180 s budget) or init exception: `startup_complete` stays False, healthz
  stays 503 after the grace window, the deploy fails the same way. There is no restart: Railway
  checks health only at deploy start, and `_stale_exit_watchdog` acts on a stale heartbeat or
  executor canary, not on `startup_complete`. A replica that is already live and somehow never
  completed init therefore stays up answering chat with 503; that case is unchanged by this patch.
- `_lifespan_failed` is still checked first and still returns 503.

Tests to add next to `tests/test_healthz_grace_masking.py`, for gate on: grace window with
`_lifespan_startup_done=True` and `startup_complete=False` -> 503; the same after grace -> 503; both
true -> 200 in both windows; gate off -> behaviour identical to today.

### 2. `/api/health` shared probe

Before: N anonymous callers = N deep probes. After: concurrent callers share one probe, result reused
for `HEALTH_PUBLIC_CACHE_TTL_S` (default 10, `0` disables). The cached body is the already-redacted
`{ready, status}`; the "starting" state is never cached; a caller presenting `METRICS_SCRAPE_TOKEN`
always gets a fresh deep result. `HEALTH_CHECK_TOTAL` now counts probes, not requests, so any rate-based alert on it changes meaning
(request volume is still in `REQUEST_COUNT`). Test: 20 concurrent callers run the probe once
(`tests/test_scaling_audit_2026_11_27.py::test_public_health_concurrent_callers_share_one_probe`).
The embedding probe was also queueing behind chat encodes on the 2-thread pool
(`services/embedding_service.py:82`), so a health storm could delay real chats.

### 4. Telemetry consumer, and can the service ever sleep

Idle command rate: before about 20 per minute (GET + XREAD + 1 s sleep per 6 s cycle); after about 7.5
per minute at the default 8000 ms wait (about 6.7 at the 9000 ms cap). The wait must stay below the
10 s Redis socket timeout of that client, hence the 9000 cap. The cursor is per process. During a deploy overlap two consumers read the same stream, and each now keeps
its own in-memory position, so for the whole overlap both process (and write to Supabase) every event; a
single batch of duplicates is not the bound. Before this change each loop re-read the stored cursor, which
narrowed that overlap. To keep the stored cursor from moving backwards when the two interleave, the write is
now monotonic (`_advance_stream_cursor`: it stores a stream id only if it is ahead of the stored one, and the
consumer continues from the furthest id), which also lets a lagging consumer skip what the other already
handled. GET then SET is two round trips, not atomic, so a race can still lose one advance; that re-delivers
a batch and never skips one. `XREADGROUP` with a consumer group is the real fix (each message to one
consumer). Per message it still does `SET last_id` and `XTRIM`; the Supabase writes per chat are 5-7 sequential sync HTTPS inserts on a
worker thread (`app/telemetry_sink.py:472-590`), unchanged.

Even at 8 s, the loop produces traffic more often than Railway's 5-minute inactivity window, so
**the backend cannot sleep while this consumer runs**, and the JobQueue stale sweep adds a Redis
SCAN every 300 s (`app/services/job_queue.py:308, 413-420`). That matches the owner's observation
that the backend never sleeps. Allowing sleep would need a consumer with no periodic wakeups (a
dedicated connection with `BLOCK 0` and no socket timeout, or moving the consumer into the Celery
on-demand worker) and a sweep interval above 5 minutes. Both are design changes, left to the owner.
With models resident (2.7 GB baseline) sleeping also costs a 60-180 s cold start, so this is a
product choice, not only a cost one.

### 9. Memory at import (macOS RSS, three runs each, `llmlingua` blocked because it is not in
`requirements.lock`)

| import of `app.main` | RSS |
|---|---|
| before (scikit-learn loaded by `ingest.raptor`) | 473, 457, 466 MB |
| after | 388, 387, 393 MB |

About 75 MB less, and `sklearn`/`scipy` are no longer in `sys.modules` (guarded by
`test_raptor_import_does_not_load_sklearn`). Isolated import deltas on the same machine: sklearn 145
MB, pandas 74, qdrant_client 102, neo4j 108, torch 166, transformers 224, FlagEmbedding 449.

What stays and why: `lightrag` (127 MB) is used at serve time (`LightRAGService` is initialised in
the lifespan, `rag_lightrag_context_injection_enabled` is on); `pandas` is pulled by `lightrag.utils`
and by `neo4j._optional_deps`; `openai` (805 modules) backs the provider clients and the guardrail
handler. In the local venv `llmlingua` is also installed and imports torch, transformers, nltk and
scikit-learn through `rag/compressor.py:81`; it is **not** in `requirements.txt`/`requirements.lock`,
so production does not load it, but any developer measurement taken in a venv with it installed is
inflated by about 400 MB. Torch/transformers in production load through the embedding path, which was
left alone as instructed.

### 14. Blocking calls in async code

AST scan of `backend/` (excluding tests, scripts, benchmarks): sync-looking client calls not awaited
inside `async def`: `app/api/kg.py:527`, `services/second_brain/vault_index.py:127,135` (plus its two
delete methods), `services/canonical_memory/vector_index.py:543`,
`services/first_person_graph_expansion.py:277` (already wrapped: the sync branch runs in `_run_sync`)
and `ingest/ontology_writer.py:285` (ingest only). Everything else in the first-person lane runs on
bounded pools: `_FP_IO_EXECUTOR` (32), `_ANS_EXECUTOR` (4), `_EMBED_EXECUTOR` (2), `_HEALTH_EXECUTOR`
(4). The scan matches on receiver names, so it can miss calls on differently named objects.

### First-person LLM call count (item c) and the scorer

Per first-person chat in the production posture (HyDE on, answerability on, harness+terminal on,
Memgraph sizing on, judge and comparative off):

1. Distress: 0-1 (Stage 2 LLM only when patterns leave doubt).
2. HyDE: 1 (cached in-process by query hash for 7 days; lost on every deploy).
3. Answerability gate: 1 (question only, after retrieval because prefetch is off).
4. Relevance scorer: **k calls**, one per evaluated context
   (`first_person_pipeline.py:5786-5800`, `_eval_ctx_worker` passes a single-clip list). `k` comes from
   `MemgraphHarnessSizer`: min 3, max 12, base 4, 5 when the driver is unavailable, up to +3 for
   discourse chains, so 4-7 typical (`services/first_person_graph_sizing.py:102-212`). They run
   concurrently under a semaphore of 4 (`_HARNESS_JUDGE_CONCURRENCY`, `:1855`), so k=7 is two waves.
   A fast transport failure adds one retry (`first_person_relevance_max_attempts = 2`).
5. Translation: 1 for non-English only.

That reproduces the coordinator's count (about 7 scorer calls, 1 distress, 3 small-model calls).

Why the 7 are not removable without changing semantics:

- **Abstentions need all k.** The first context in rank order that passes wins
  (`first_person_pipeline.py:5990`), but an abstain is the outcome when none passes, and `CLAUDE.md` invariant 24
  records coverage of 24-31% of questions (a dated 2026-10-11 measurement at minimum score 3; the
  production minimum is now 2, so today's share is not known). So at most about a quarter to a third of turns could ever
  skip calls. Staging the fan-out by rank would save at most k-4 calls on those turns (3 at k=7, so
  about 1 call per chat on average) and add one scorer round trip to latency when the first wave
  fails. It would also drop the scores that feed `_h_related` (related-clip pointers) and the
  editorial-set path from skipped contexts, so the response is not provably identical. Not done.
- **Batching k single-clip prompts into one multi-clip call changes the judging context** (the model
  sees all clips together and scores relatively). The legacy path did exactly that, which is why this
  lane was split. Not provably the same clip. Not done.
- **Deduplicating identical (question, assembled text) pairs** is the only provably safe cut. I found no
  evidence that identical assembled texts occur (candidates are diversified and containment is not
  equality); the yield is probably near zero, and it needs live traffic to measure. Not done.

What does cut the failure mode without touching a gate:

- The throttle sleeps **inside** the scorer deadline: `OpenRouterService._enforce_rate_limit`
  (`services/openrouter_service.py:385-415`) sleeps up to the retry-after before the request, and the
  scorer wraps the whole `generate()` in `_bounded(_call(), timeout_s)`. A throttled call can burn its
  15 s budget waiting and then abstain as `relevance_indeterminate`. The limiter is a self-imposed
  client cap (`OPENROUTER_RPM_LIMIT`, default 120 per model, `app/config.py:749`); OpenRouter's own
  limit for a paid model is not a requests-per-minute figure: OpenRouter's docs say the 20/min cap
  applies only to `:free` variants, that a paid model "has no platform-level request cap", and that
  spending is governed by credits, a per-key limit and an in-flight spending budget, with upstream
  providers still free to return 429 ([OpenRouter: limits](https://openrouter.ai/docs/api-reference/limits)).
  So the 120/min wall is ours: at 7-8 Haiku calls per chat it is about 15-17 chats a minute. Raising
  `OPENROUTER_RPM_LIMIT` removes the self-throttle but then upstream 429s and the in-flight budget are
  the real ceilings, which were not measured. Owner/ops decision.
- `FIRST_PERSON_ANSWERABILITY_PREFETCH_ENABLED=true` overlaps the gate with HyDE, embedding and
  retrieval. Same call and verdict, only the start time moves, so about one LLM round trip off the
  critical path; the call is wasted when the turn never reaches the gate (exact-cache hit). Needs a
  graded run per `CLAUDE.md` before it is turned on. Not measured.

Enrichment window (the 1.5 s loop), reported and **not changed**: `_widen`
(`services/first_person_pipeline.py`, `_expand_context_candidates`) runs `_call_with_deadline` per
parent in sequence, a new daemon thread per call, worst case max_clips x 1.5 s. Reading the parents
concurrently looks safe but is not: `_call_with_deadline` takes a slot from `_ENRICH_SLOTS`
(`BoundedSemaphore(8)`) without waiting and raises `TimeoutError` when none is free, which the caller
turns into "keep the narrower retrieved spans". A 4-way fan-out would let two concurrent requests use
every slot, so a third request's parents would silently stay un-widened and the harness would gate a
different span set; a timed-out read also holds its slot until the socket gives up. That can change
which context is served under load. If this is revisited, raise `_ENRICH_SLOTS` together with the
fan-out and show that no request is refused at the graded concurrency. The flag is off in
`.env.example` and absent from `.railway/railway.ts`, so production does not pay this today; it is on
in `docker-compose.graded.yml`, which is the frozen comparability harness, so promoting that
posture is where this latency would appear.

### 8. `/api/capabilities`

Micro-benchmark (Mac, 2000 iterations): manifest build 29 us per call, cached endpoint 2 us, 304
path 2 us, body 760 bytes (304 = 0 bytes). The CPU is small; the point is the 459 bot hits an hour
and every page load now being answerable by the browser or an intermediary cache for 60 s and by
`If-None-Match` after that. The body holds booleans and state strings only (no secrets, no
per-caller data), which is what makes `public` caching safe. The 503 not-ready response is
`no-store`. If a CDN is put in front, it will honour `max-age=60`.

### Other checks, no change needed

- Clients: the OpenRouter client is pooled with keep-alive (`services/openrouter_service.py:340-360`,
  20 keep-alive, 30 s expiry). The Qdrant client is one sync client with a 30 s timeout
  (`services/qdrant/client.py:100-119`). Per-call `httpx.AsyncClient` exists only on cold paths
  (speech, OCR, admin role fallback, the off-by-default Jev picker at
  `first_person_pipeline.py:1287`, `first_person_relevance_jev_enabled = False`).
- Exact-cache key (`first_person_pipeline.py:4196-4228`) includes query, teacher, language,
  collection, calibration time, rerank mode, answerability flag and a serving-policy fingerprint, so a
  corpus or policy change cannot replay an old answer. TTL 24 h.
- Metrics: no label takes a user, session, path or query value (grep of `.labels(` sites).
- Anonymous cost vectors: `/api/chat*`, `/api/chat/title` and `/api/first-person/query` run the
  anonymous quota; `/api/auth/anon-session` is per-IP limited (`app/main.py:1398-1500`), so minting
  sessions does not bypass the quota; `/api/speech/*` have Redis-backed limiters. If Redis is down
  the quota degrades to a process-local limit of `min(limit, 3)` and the in-memory counters reset on
  restart (documented behaviour); with one container that is the whole fleet.
- uvicorn: `uvicorn.run("start_railway:app", workers=WEB_CONCURRENCY, proxy_headers=True,
  forwarded_allow_ips=...)` (`start_railway.py:891-898`) uses uvloop and httptools automatically. Not
  set: `limit_concurrency` (it returns 503 at the socket and would bypass the crisis-aware admission
  control in `chat.py`; leave unset), `timeout_keep_alive` (default 5 s is fine behind Railway's
  edge), `access_log` (two INFO lines per request, uvicorn's and `AuditLogMiddleware`'s; a candidate
  to silence if log volume matters, not measured).
- gzip: no `GZipMiddleware`. Responses are small (capabilities 760 B; chat payload not measured), and
  Starlette's gzip middleware sits beside SSE streaming, so it was left out. Revisit with a measured
  chat payload; the frontend 487 KB initial load is already compressed by the static host.

## What changed, and the knobs

| Setting (env) | Default | Effect |
|---|---|---|
| `HEALTH_PUBLIC_CACHE_TTL_S` | 10 | shared public `/api/health` probe; 0 = old behaviour |
| `CAPABILITIES_CACHE_TTL_S` | 60 | `/api/capabilities` render and `max-age`; 0 = no caching |
| `TELEMETRY_WORKER_BLOCK_MS` | 8000 (was 5000 plus a 1 s sleep) | idle wait of the telemetry consumer, 1000-9000 |
| `ADMIN_ROLE_NEGATIVE_CACHE_TTL_S` | 90 (unchanged) | recommend 600; positive result stays 90 s |

Files: `app/api/health.py`, `app/api/capabilities.py`, `app/api/kg.py`, `app/api/search_routes.py`,
`app/telemetry_sink.py`, `app/orchestrator.py`, `app/config.py`,
`app/security_utils.py`, `app/middleware/rate_limit.py`, `services/anon_quota_redis.py`,
`services/auth_service.py`, `services/second_brain/vault_index.py`,
`services/canonical_memory/vector_index.py`, `ingest/raptor.py`; tests in
`tests/test_scaling_audit_2026_11_27.py` and an
autouse reset in `tests/conftest.py` so cached responses never leak between tests.

## Test and guard results

- New: `backend/tests/test_scaling_audit_2026_11_27.py`, 17 tests, all pass (shared health probe, cache
  expiry and token bypass, ETag/304, telemetry cursor, lazy sklearn in a fresh process, pooled client,
  admin negative TTL, limiter pruning and its once-a-minute rate limit, monotonic telemetry cursor, the
  current Host-allowlist behaviour).
- Targeted suites around every touched area (health, capabilities, kg, second brain, canonical memory,
  rate limits, anon quota, auth, telemetry, orchestrator, settings guards, repo layout, ratchets,
  pipeline order, all `test_crisis*` and related safety files): 296 passed in one batch; 491 passed in
  another with one failure (`test_health_hard_bound`, a cached `/api/health` body leaking between tests),
  fixed by the autouse reset in `tests/conftest.py`, after which the health set re-ran 70 passed.
- Full backend suite (`pytest tests`, one run, `test_guru_literal_scan` deselected): 3 failures, none
  caused by this change. `test_first_person_async_lane::test_c20...` is a loop-blocked-for-0.257 s timing
  assertion that failed under load and passes alone; `test_metrics_reachability` reports "checked 0
  files" because it filters out paths under `.claude/` and this work ran in a `.claude/worktrees`
  checkout; `test_supabase_types_lint` names a table (`user_brain_keys_archive_20261119`) with no
  migration, in files this change does not touch. `test_guru_literal_scan::test_baseline_matches_the_tree`
  and `guru_literal_guard.py` fail on two `src/` files whose baseline is stale (untouched here).
- Guards: ruff check and format, `config_lint`, `exception_ratchet` (759, at ceiling),
  `pipeline_order_guard`, `import_layer_lint`, `stale_flags` (0 blocking), `lesson_guards claims` all pass.
- Not run: frontend lint/typecheck/vitest (no frontend file changed), the safety eval script, any live
  stack run.

## Capacity-agent finding folded in

One first-person chat makes about 11 LLM calls (about 7 Haiku relevance scorers, 1 Haiku distress
check, 3 Llama-8B calls), counted at a stub over 3 chats; the 120/min per-model limiter then caps the
box near 15 chats a minute. Section "First-person LLM call count" above accounts for the 7: one scorer
call per evaluated context, k = 3..12 from `MemgraphHarnessSizer`, run four at a time, plus fast-failure
retries. They are all needed for an abstain, batching changes judging context, and early exit would not
provably keep the related-clip list, so none was changed. The levers that do not touch a gate are
`OPENROUTER_RPM_LIMIT` (a self-imposed cap, see the OpenRouter citation) and
`FIRST_PERSON_ANSWERABILITY_PREFETCH_ENABLED` after a graded run. The throttle sleep sitting inside the
scorer deadline is the mechanism by which throttled scorer calls abstain silently as
`relevance_indeterminate`.

## Bot traffic on the default domain (WAF guidance)

Application settings reduce cost per request but a request still reaches the container and is
answered (and Railway counts the reply as activity). To stop scanners before the container:

1. Put the app on a custom domain behind Cloudflare (or any WAF/CDN), let the edge, not the origin, absorb scanners (the origin's Host check
   already rejects other Hosts with 400; see finding 10), and add a
   rate rule per IP on `/api/*`, with a tighter one on `/api/auth/*` and `/api/chat*`.
2. Cache `GET /api/capabilities` at the edge for 60 s (it already sends `Cache-Control`).
3. Keep `/api/healthz` reachable for Railway on the default domain: Railway's check sends
   `Host: healthcheck.railway.app`, which stays allowed, and the wrapper answers it before the app.
4. Make `METRICS_SCRAPE_TOKEN` mandatory for `/api/health` deep output (already the case) and do not
   expose `/internal/metrics` through the CDN.

## Not verified

- Linux RSS, production latency, real Supabase/Redis/Qdrant round-trip counts, chat payload size,
  pass rate by context rank, whether identical assembled texts occur, log volume.
- That Railway sleeps once the consumer and sweep are quiet (the docs say it should; no live test).
- The readiness patch in section 1 (not applied, no test run).
