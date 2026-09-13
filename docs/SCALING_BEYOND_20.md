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
