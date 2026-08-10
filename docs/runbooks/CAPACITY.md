# Capacity & Load Behavior — /api/chat

Status: **measured locally (mock-LLM sweep), remote staging sweep pending first nightly run** — Aug 2026 (P1-OPS-7).

## Admission control

- `/api/chat` is wrapped in an `asyncio.Semaphore` (`chat.py:_get_chat_semaphore`, `max_concurrent_chat`, default **20**). Try-acquire with 0.01s timeout — an exhausted semaphore returns **503 + `Retry-After: 5`** immediately (fail-fast, no queue buildup).
- `GET /api/health` exposes `chat_backpressure`: `max_concurrent`, `in_flight`, `admission_limited`.
- Downstream LLM circuit breakers and provider failovers protect the pipeline independently.

## Observed behavior (local full-stack, mock LLM)

The mock-LLM sweep (canned 800-token response, no LLM cost) isolates backend
overhead from provider latency:

| Concurrency | In-flight admission | Expected result |
|---|---|---|
| ≤ 20 | semaphore never exhausts | 200s, throughput bound by retrieval+cache path |
| > 20 | requests beyond 20 in flight → immediate 503 | fail-fast backpressure, no queueing |

Gates for the nightly run (`.github/workflows/nightly-load.yml`):

- **p95 < 8s** at concurrency 20 (mock mode).
- **No 5xx** at concurrency 20 and 50.
- **503s must appear** at concurrency 50 (proves backpressure trips at
  `max_concurrent_chat`); a sweep with zero 503s at c50 means the semaphore
  is not the limiting factor.

Remote/staging mode (real LLM) runs concurrency 1→5 only, bounding LLM cost;
the p95 gate is relaxed to 30s because provider latency dominates.

## Degradation behavior

- **Qdrant down** (chaos test `scripts/chaos_qdrant_kill.py`): cached doctrine,
  casual short-circuit, and graceful-degradation paths keep `/api/chat`
  answering 200; recovery after restart is automatic.
- **LLM down**: circuit breaker opens; OpenRouter last-resort fallback or
  graceful-degradation copy is returned (never a hang).

## Breaking point (as established)

- Single replica: admission caps at **20 concurrent chat requests**; beyond
  that, 503 + Retry-After (client sees "Server busy, try again shortly").
  The correct client behavior is to surface this politely and retry after the
  Retry-After window.
- **2-replica scale-out is gated** on the first green remote nightly load run
  (P1-OPS-6 T4/T5): confirm both replicas pass init
  (`overlapSeconds: 120` pre-warm in effect) and that 2 × 20 concurrent is
  comfortably above observed peak.

## Operate

- Nightly: `nightly-load.yml` at 03:00 UTC → reports artifact `nightly-load-reports`.
- Manual: see `backend/benchmarks/locustfile.py` + `backend/scripts/mock_llm_server.py`
  headers for the exact local commands.
- When scaling: run the sweep at the target replica count; expect
  `2 × max_concurrent_chat` headroom; re-record the breaking point here.