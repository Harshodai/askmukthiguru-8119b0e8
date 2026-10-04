# Scale / Load Readiness Audit — 2026-10-04

**Question:** can this serve lots of users? **Owner ceiling:** infra < $35/mo (Railway $10/GB-mo; Railway currently paused; local docker stack is the measurement target).
**Method:** fresh-eyes audit from code + configs + light live probes only. No code changed, no deploys, no ingest-driver contact.
**Load caveat (read first):** host was severely loaded during all probes — mass-ingest driver + ASR workers, `load avg 50.75 / 22.59 / 15.95` at probe time. Every latency below is an **upper bound**, not a clean-room number.

## 1. Serving topology (from evidence, not memory)

| Layer | Evidence | Setting |
|---|---|---|
| Edge / replicas | `railway.json` (root + `backend/` identical, unattributed) | **1 replica**, 6 Gi limit, `overlapSeconds 45` (dual-run burst on deploy) |
| ASGI server (Railway) | `backend/start_railway.py:502-510` | `uvicorn.run(workers=1)`, proxy-headers on, `FORWARDED_ALLOW_IPS` fail-closed |
| ASGI server (local/prod compose) | `backend/docker-entrypoint.sh:27-101` | `WEB_CONCURRENCY` unset → auto `min(nproc,2)`; `>1` = gunicorn+UvicornWorker, `=1` = bare uvicorn. Local compose default `WEB_CONCURRENCY=1` (live: `printenv` → `1`) |
| Chat admission | `backend/app/api/chat.py:183-230` | **global `asyncio.Semaphore(8)`** (`max_concurrent_chat=8`, `app/config.py:712`); exhausted → immediate **503 + Retry-After: 5**, no queue |
| Per-IP rate limits (slowapi, key = client IP via proxy headers, `app/core/limiter.py:24-49`) | `app/config.py:855-857`, `app/api/chat.py:475,575` | `/api/chat` **20/min**, `/api/chat/title` 20/min, upload 10/min, **first-person 120/min**, health endpoints **exempt** (`limiter.py:13-21`) |
| Abuse/cost guards | `app/config.py:872-874`, compose env | anon quota **5 msgs / 24 h** (degraded 3); OpenRouter budget guard **$0.03/req fail-closed**, $10/day, $100/mo; RPM limits OpenRouter 20 / NIM 30 / Sarvam 60 |
| LLM concurrency | `app/config.py:759`, `:732` | `llm_queue_max_concurrent=5`, `native_inference_max_concurrent=6` |
| Redis | compose `redis` svc | local 450 MB `allkeys-lru`; prod compose 512 MB **`noeviction`** (quota-counter protection); exact-cache cap `redis_cache_max_keys=10k` (`config.py:693`) |
| Redis per-user footprint | `services/memory_service_v2.py:37`, cache adapters, `config.py:1221` | ephemeral session keys **15-min TTL (~900 s, few KB)**; rate-limit ZADD windows; anon-quota counters; exact cache TTL **1 h** (`services/cache/constants.py:4`); semantic cache TTL **7 d**; retrieval cache 300 s |
| Qdrant | live `GET /collections` | local `spiritual_wisdom_contextual`: **14,033 pts**, 29,077 indexed vecs, 1024d, `scalar int8`, `on_disk:true`, HNSW m=32; container 250 MB / 3 GB. Prod corpus ≈ 89 k pts (per repo notes) |
| Graph | compose + `config.py:529-536` | Memgraph primary (512 MB `--memory-limit`, 1 G cgroup), driver pool **8**, `kg_query_timeout 5 s`, fail-open |
| Postgres/Supabase | `app/api/chat.py` PERF-2 comment, compose | **sync supabase-py via `asyncio.to_thread`** — no client-side pool; each call = new TLS handshake to PostgREST/Kong (Supavisor pools server-side). Local full Supabase stack also running (10+ containers, 4 d uptime) |
| Job queue | `app/services/job_queue.py:262` | Redis-backed, `max_connections=32` |
| Celery | `start_railway.py:400-424`, compose `celery-worker` (opt-in `ingestion` profile) | queues `ingestion,embedding,indexing,okf,memory`, concurrency 1–2; Railway worker paused for budget |
| Push | `services/push_service.py` | FCM via firebase-admin (lazy init) + APNs via httpx; no batching; off-request path |
| Per-request LLM shape | `config.py:115-120,958`; `openrouter_service.py:94-104` | classify 8b ($0.02/$0.04 per M) + generation **deepseek-chat ($0.14 in / $0.28 out per M)** + ≤2 rewrites + HyDE (non-Indic) + translation (Indic); output ceilings 800 (fast) / 1500 (deep); input budget ≤12 k tokens |
| Live RSS (probe time) | `docker stats` | backend **3.42 GiB / 6 GiB** (57 %); memgraph 490 MB; qdrant 250 MB; redis 6.5 MB of 450 MB. Railway idle noted in-repo at **~4.3 GiB** |

## 2. Live probes (light only)

| Probe | Result |
|---|---|
| 1× `GET /api/health` (comprehensive) | 200 in **1.97 s** |
| 20 parallel `GET /api/health` | **20/20 × 200, 6.8–9.3 s each** (upper bound; load avg ~50) |
| 1× then 2× `GET /api/healthz` (trivial always-200, `health.py:109-117`) | **timeout (30 s, then 60 s)** — event loop could not schedule a no-op coroutine |
| Post-probe state (read-only) | `docker ps` backend "Up 6 h (healthy)" vs `docker inspect` Health: **starting**, `RestartCount: 1`, `OOMKilled: false`; logs show parallel-session first-person pipeline still progressing |

**Interpretation (honest):** the 20× burst on the *expensive* comprehensive endpoint saturated the single worker; afterwards even the cheap liveness probe starved. Pre-probe `RestartCount` was not recorded, so I cannot prove the burst caused a restart vs. merely saturating a 6-hour-old container — both readings are reported as observed. Either way, **~20 concurrent expensive requests is enough to make the serving path unresponsive**, and `/api/health` is **rate-limit-exempt** (`limiter.py:13-21`), so anyone can repeat this accidentally (monitoring scrape pile-up) or deliberately. No authenticated chat probe was attempted after this — sending a full LLM-backed chat into a saturated worker would add spend and load for no new information; per-request cost is derived from code ( §4 ).

## 3. Bottleneck ranking (first-breaks-first)

**P0-1 — Global 8-slot chat semaphore + 1 worker + 1 replica = ~1 chat/s.**
`max_concurrent_chat=8` with ~4–14 s pipeline latency (repo baselines: EN 14.7 s cold, HI 19.9 s, warm paths ~4 s; take ~8 s typical) → **≈ 1 req/s sustained, 9th concurrent chat gets 503**. ~50 simultaneous users after a discourse = visible 503s. Single replica = zero HA; any restart = full outage; deploy overlap runs 4.3 GiB × 2.
*Fix (owner applies):* `backend/app/config.py` `max_concurrent_chat` 8 → 12–16 **and** `start_railway.py:506` `workers=1` → 2 (Redis-backed OpenRouter RPM limiter already cross-process, `openrouter_service.py:122-138`, so the old "pinned at 1" reason is stale — verify with mock-LLM locust first). Cost: +~1.4 GiB/worker (entrypoint comment: each worker loads embedding model). Expected gain: ~2× burst headroom.

**P0-2 — Idle infra already exceeds the $35/mo ceiling at zero users.**
4.3 GiB idle × $10 = **~$43/mo memory alone**, + vCPU (~0.5–1 avg → $10–20) + Pro seat $20 w/ $20 credit → **≈ $53–63/mo before one chat**. Local RSS 3.42 GiB confirms the shape. Biggest chunk: ~2.9 GiB documented ONNX embedding/reranker loads.
*Fix:* no config tweak fits 4.3 GiB in $35 on metered RAM. Options: (a) raise ceiling to ~$65; (b) move serving to flat-rate host (keeps Qdrant/Supabase/LLM where they are); (c) cut RSS — lazy-load reranker, drop LightRAG graph stack from serving path, shrink `BACKEND_MEMORY_LIMIT`. Expected gain: (b) ≈ flat $10–20/mo; (c) ≈ −1–1.5 GiB (~−$10–15/mo) with quality-regression risk — needs held-out eval per repo's evidence-gated rule.

**P0-3 — Provider RPM 20/min caps throughput at the same place as the semaphore.**
OpenRouter `openrouter_rpm_limit=20` ÷ ~3 provider calls/chat (classify + generate + spare) ≈ **6–7 chats/min**; excess waits ≤10 s (`_MAX_GATEWAY_THROTTLE_WAIT_S`) then degrades. Raising the semaphore without raising this just moves the queue.
*Fix:* `backend/docker-compose.yml:256` / Railway env `OPENROUTER_RPM_LIMIT` 20 → 60 (Sarvam path already allows 60; confirm OpenRouter tier quota first). Expected gain: removes the sub-semaphore ceiling; pair with P0-1.

**P1-1 — `/api/health` (comprehensive, up to 12 s hard bound) is rate-limit-exempt and unguarded.**
Proven above: 20× parallel = backend unresponsive. Scrapers + humans + deploys can pile up.
*Fix:* `backend/app/core/limiter.py` — remove `/api/health` from `_HEALTH_EXEMPT_PATHS` (keep `/api/healthz` exempt) **or** add a dedicated `TTLRateLimiter(ttl=60, max_requests=30)` on the comprehensive endpoint; point all liveness probes at `/api/healthz`. Expected gain: eliminates the cheapest accidental-DoS vector found in this audit.

**P1-2 — first-person route at 120/min on a heavier pipeline.**
`first_person.py:188` allows 6× the chat rate on a path with integrity gates + answerability LLM calls; anon-quota coverage for this route not verified in this audit.
*Fix:* parity with chat (`120/minute` → `20–30/minute`) or confirm anon-quota enforcement on the route. Expected gain: closes a 6× spend-amplification asymmetry.

**P2 — Everything else is not the first break:** Redis (MBs used of 450 MB; 10 k-user session state ≈ tens of MB); Qdrant (89 k prod pts ≈ <0.5 GB int8 — headroom to ~1 M vectors before RAM matters, ~1.4 GB int8 + HNSW); Memgraph pool 8 + 5 s timeout + fail-open; Supabase sync-client TLS churn (~50–100 ms/call — migrate to shared `httpx.AsyncClient` when p95 demands it); Celery 1–2 workers (ingestion-isolated, correct); push (off-request, unbatched — batch only when notification bursts exist).

## 4. Cost math (per-MAU, LLM + infra)

Per-turn LLM (typical, from §1 shape): classify ~500 tok 8b ≈ $0.00001 + generation ~4 k in × $0.14/M ≈ $0.00056 + ~600 out × $0.28/M ≈ $0.00017 + rewrites/translation amortized ≈ **~$0.001/turn typical, ~$0.003–0.005 worst-case** (deep route + 2 rewrites + translation). Guards: $0.03/req fail-closed, $10/day, $100/mo.
Assume 10 turns/MAU/mo (light spiritual-app use):

| MAU | LLM/mo | Infra/mo (Railway, idle-dominated) | Total vs $35 |
|---|---|---|---|
| 100 | ~$1 | ~$53–63 | **over before 1 user** |
| **1,000** | **~$10** | ~$53–63 | **~$63–73, ≈ 2× ceiling** |
| 10,000 | ~$100 (hits $100/mo budget guard → fail-closed starts biting) | ~$53–63 + first scale-out (2nd replica doubles RAM $) | ~$150+ |

LLM scales linearly and is cheap per user; **infra idle cost is the binding constraint from user zero**. Rate-table sources: in-repo `openrouter_service.py:94-104` ($0.14/$0.28 deepseek-chat) corroborated by DeepSeek docs/OpenRouter trackers (2026: V4-Flash $0.14/$0.28 — Cowoker AI blog; OpenRouter pricing page).

## 5. Best-practice anchors (2025–2026, 5 sources)

1. Uvicorn/Gunicorn sizing `(2×cores)+1`, workers × connections = capacity; every worker duplicates RSS — https://sentry.io/answers/number-of-uvicorn-workers-needed-in-production
2. FastAPI official: single-process dev vs. multi-worker deployment; replication via workers/replicas — https://fastapi.tiangolo.com/deployment/server-workers
3. Supabase/Supavisor: transaction mode (6543) for API traffic, pooled-client limits per compute size (Micro: 200 clients) — https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits ; https://supabase.com/blog/supavisor-postgres-connection-pooler
4. Qdrant capacity: `vectors × dim × 4 B × 1.5`; scalar-int8 ≈ 4× smaller (1 M × 1024d ≈ 5.7 GB fp32 → ~1.4 GB int8 + HNSW) — https://qdrant.tech/documentation/capacity-planning
5. Railway 2026 metered rates $10/GB-mo RAM, $20/vCPU-mo, Pro $20 w/ $20 credit, ≤42 replicas — https://railway.com/pricing ; https://livemy.app/blog/railway-pricing

## 6. Verdict

**Can it serve lots of users today? No.** Two independent ceilings, cost first: (1) **idle infra (~$53–63/mo) already exceeds the $35 ceiling with zero users** — no traffic level fixes this, only hosting or budget changes; (2) technically, **~7 concurrent chats** (≈ 1 req/s) is the hard ceiling — global 8-slot semaphore, 1 worker, 1 replica, provider RPM 20/min all converge there, and a 20-parallel hit on the exempt comprehensive health endpoint rendered the worker unresponsive in this audit. First user-visible break under real growth: **503 "Server busy" bursts**, then cost-guard fail-closeds at ~10 k MAU. Redis/Qdrant/graph/push all have headroom and are correctly not the target.
