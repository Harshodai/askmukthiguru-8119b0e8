# Scaling Beyond 20 Concurrent

Day-one target: **20 pilot users + headroom** (hot-path Redis pools at 32,
`max_concurrent_chat = 8` admission semaphore per replica). This note lists
what else must move before pushing past 20 sustained concurrent, with
concrete next numbers.

## 1. Admission semaphore and workers

- `max_concurrent_chat` (default 8) 503s everything above it per replica —
  raising pools without raising this just moves the ceiling to the
  semaphore. Next: 8 → **24** with 2 uvicorn workers, or hold 8 and run
  **3 replicas** behind the load balancer (preferred: isolates blast radius).
- Rule of thumb: `max_connections ≥ peak in-flight Redis ops per process +
  ~25% headroom`, and `Σ max_connections across processes < redis
  maxclients` (default 10000, but managed tiers are lower — check
  `CONFIG GET maxclients`).
- Uvicorn: 1 worker per core for pure-async; more workers multiply pools.

## 2. BlockingConnectionPool trade-offs

- Default `ConnectionPool` **fails fast** (`MaxConnectionsError`) when
  exhausted — right for background jobs that can retry, wrong for
  user-facing paths where a brief queue beats a burst of 500s.
- `BlockingConnectionPool(max_connections=32, timeout=5)` converts
  exhaustion into bounded queuing (backpressure). Cost: slow commands pin
  the queue, so pair with `socket_connect_timeout=5` + `socket_timeout=5`.
- S1 deliberately kept the default pool + degrade-to-memory fallback
  (fail-open chat beats queued chat for a pilot). Switch to blocking only
  with pool-wait-time metrics and an alert (see §6).

## 3. Qdrant single-node limits

- Single node is fine to ~50–150 QPS for 100K-vector collections over gRPC
  (`prefer_grpc=True`, one shared `AsyncQdrantClient` in lifespan — never
  per-request). Past that: `replication_factor=2` + load balancer in front
  (clients do not spread reads across replicas on their own).
- Separate read vs. write gRPC pools so ingestion upserts never contend
  with query latency. Keep `timeout ≥ 30s` for large payloads.

## 4. Neo4j single-node limits

- Community single instance + persistent volume holds to pilot scale;
  graph traversal is not on the hot path (GraphStage falls back to pure
  Qdrant dense search if Neo4j is unreachable). Past ~50 concurrent graph
  queries: causal cluster (1 core + 2 read replicas) or AuraDB HA, with
  read routing for traversals and writes pinned to the leader.

## 5. Provider quota (the real ceiling)

- Chat latency is dominated by the LLM call, not infra. `max_concurrent_chat=8`
  was sized to a 60 RPM provider limit on the 8-step Standard path.
- Past 20 concurrent: raise provider RPM/TPM tier first, add a fallback
  model + circuit breaker, and cap embedding batch size so re-embeds never
  queue behind live queries. Monitor provider 429 rate as the scale signal.

## 6. SLO tiers and next numbers

| Tier | Sustained concurrent | Redis | API | Qdrant | Neo4j |
| --- | --- | --- | --- | --- | --- |
| Pilot (now) | 20 + headroom | 1 node, pools 32 | 1 replica, semaphore 8 | 1 node, gRPC | 1 instance |
| Growth | 50 | 1 node, pools 64 + wait-time alert | 3 replicas × 8 | 1 node, split read/write pools | 1 instance |
| Production HA | 150 | Primary + replica, Sentinel | autoscaled, semaphore 24/worker | 3-node, rf=2 + LB | 1 core + 2 replicas |

Scale signals in order: provider 429 rate → p95 latency → queue depth →
Redis pool-wait time → Qdrant p99 → Neo4j traversal latency. Change one
tier at a time and re-run the burst gate (`docs/BURST_R4.md`).

## Measured 2026-09-14 — the first real 20-concurrent number

Live run against the host backend, all infra healthy, anon-session token flow
(so the quota shed nothing and the instrument actually reached the admission
semaphore — the round-5 burst and the `run_concurrent_load_test --live` run
both failed this and were unreadable):

```
N=20 simultaneous       wall 40.9s
  admitted 2xx : 8/20
  shed 503     : 12/20   Retry-After=5
  quota 429    : 0/20
  latency        p50 23.9s   p95 40.9s
```

`max_concurrent_chat=8` behaves exactly as specified: 8 in, 12 shed in ~10ms.

**Raising the semaphore alone makes this worse, not better.** p95 is already
40.9s at 8 concurrent against `pipeline_timeout=105`. Admitting 20 on one
worker puts p95 near 100s, converting fast 503s (which a client can retry on
`Retry-After: 5`) into slow 504s. A seeker waiting 100s for a gateway error is
a worse outcome than being told to retry in 5 seconds.

**The lever is workers, and memory is what bounds it.** `workers=1`
(`start_railway.py:322`, `WEB_CONCURRENCY=1` in `Dockerfile.railway:71` — note
line 6 of that file claims "2 uvicorn workers", which is drift, not config).
Measured steady RSS is 2.57GiB of a 6GiB cap. Workers are separate processes
and each lazily loads its own ONNX session, reranker and embedding model, so:

| Workers | Admitted (×8) | Projected RSS | Fits 6GiB? |
| :-- | :-- | :-- | :-- |
| 1 | 8 | 2.57 GiB | yes, current |
| 2 | 16 | ~5.1 GiB | yes, tight |
| 3 | 24 | ~7.7 GiB | **no** |

So 20 simultaneous *requests* is not reachable on one 6GiB container without
either raising the memory cap or moving inference out of the API process
(the round-1 finding: six model families load in-process).

**20 concurrent users is a different number from 20 simultaneous requests.**
People read and type between turns; twenty pilot users plausibly produce 2–5
in-flight POSTs. Nothing here measures think-time, so the honest position for a
pilot is: 8 admitted is likely sufficient for 20 users, and the 503 path is
correct, fast and retryable when it is not. Do not claim 20 simultaneous.

Reproduce: `POST /api/auth/anon-session` for a token per caller, then N parallel
`POST /api/chat` with `X-Session-Id`. `benchmarks/run_concurrent_load_test.py
--live` does NOT do the token exchange and returns 400 on every request, which
reads as a 0% pass rate rather than an auth failure — fix that before trusting it.
