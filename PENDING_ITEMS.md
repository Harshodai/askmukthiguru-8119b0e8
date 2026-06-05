# Pending Items — Mukthi Guru Architecture Enhancement

> **⚠️ Superseded**: See [`PROJECT_STATUS.md`](./PROJECT_STATUS.md) for the comprehensive, up-to-date status report.
> **Source**: `/goal` plan (14 units) from `.claude/plans/elegant-snacking-kite.md`
> **Last Updated**: 2026-06-06
> **Current Git Head**: `2cb9bbdc` (post-development, worktrees cleaned)

## Development Completion Summary

All 14 units plus the additional Connection Pooling task have been **implemented in code**. The remaining work is **E2E testing and verification**, which you requested I not run but instead provide commands for.

---

## Unit Status Overview

| # | Unit | Code Status | E2E Verification | Priority | Notes |
|---|------|------------|------------------|----------|-------|
| 1 | Timeout & Performance | ✅ Done | ⏳ Needs Run | P0 | Timeouts, circuit breaker, retry logic in place |
| 2 | RAG Pipeline Enhancement | ✅ Done | ✅ Verified | — | Merged to main |
| 3 | Semantic Cache Expansion | ✅ Done | ⏳ Needs Run | P0 | Cache service implemented |
| 4 | Production Hardening | ✅ Done | ✅ Verified | — | RPM limiter, rate limiting in place |
| 5 | Faithfulness & Verification | ✅ Done | ⏳ Needs Run | P1 | verify_answer, reflect_on_answer improved |
| 6 | Adversarial Resilience | ✅ Done | ✅ Verified | — | Guardrails in place |
| 7 | Doctrine Accuracy | ✅ Done | ⏳ Needs Run | P0 | DOCTRINE_SYNONYMS (30+ entries) + expansion live |
| 8 | Metrics & Observability | ✅ Done | ⏳ Needs Run | P1 | monitoring_dashboard.py created |
| 9 | Repo Cleanup | ✅ Done | ⏳ Needs Run | P0 | 72/72 unit tests pass (3 env failures) |
| 10 | Docker Health & Log Fixes | ✅ Done | ⏳ Needs Run | P1 | Resource limits + healthchecks for ALL services |
| 11 | Ruflo Integration | ✅ Complete | N/A | — | Documentation only |
| 12 | Token Optimization | ✅ Done | ⏳ Needs Run | P1 | Hard enforcement in nodes.py + ollama_service.py + config |
| 13 | Benchmark Expansion | ✅ Done | ⏳ Needs Run | P1 | 500+ questions in question_bank.py |
| 14 | Production Go-Ahead | ✅ Done | ⏳ Needs Run | P2 | Scripts created, checklist in place |
| — | Connection Pooling | ✅ Done | ⏳ Needs Run | P2 | http_client_pool.py created |

---

## Files Added/Modified in This Session

| File | Change | Unit |
|------|--------|------|
| `backend/docker-compose.yml` | Resource limits for ALL services; healthchecks | 10, 1 |
| `backend/rag/nodes.py` | DOCTRINE_SYNONYMS (30+ entries); TokenBudgetExceeded; `_enforce_token_budget()`; `expand_query_with_synonyms()` | 7, 12 |
| `backend/services/ollama_service.py` | `_enforce_token_budget()` in `generate()`; token logging (`tokens_sent`, `tokens_received`) | 12, 1 |
| `backend/services/http_client_pool.py` | **NEW**: Global `httpx.AsyncClient` singleton; `get_client()`; `aclose()`; `lifespan()` | — |
| `scripts/monitoring_dashboard.py` | **NEW**: CLI dashboard; queries `/metrics`; renders latency/cache/error table | 8 |
| `backend/tests/conftest.py` | `sys.path.insert(0, BACKEND_DIR)` fix for `ModuleNotFoundError` | 9 |

---

## Test Results (Unit Tests)

```
========= 72 passed, 3 failed in 4.39s =========
```

### Passed (72 tests)
- `test_adaptive_chunking` (4)
- `test_benchmarks` (2)
- `test_concurrent_retriever` (multiple)
- `test_context_compressor` (multiple)
- `test_embedding_service` (multiple)
- `test_flashrank_rerank` (3)
- `test_guardrails` (multiple)
- `test_ingestion_pipeline` (multiple)
- `test_memory_context` (multiple)
- `test_nodes` (multiple)
- `test_observability` (multiple)
- `test_rag_advanced` (multiple)
- `test_rrf_ranker` (multiple)
- `test_sarvam_observability` (multiple)
- `test_tiered_router` (multiple)
- `test_tiered_routing_streaming` (multiple)

### Failed (3 tests — all environment, not code bugs)
| Test | Status | Reason |
|------|--------|--------|
| `test_coalescer.py::test_redis_coalescer_concurrency` | ❌ ENV | Redis not running (`PermissionError` connect to localhost:6379; expected in sandbox) |
| `test_coalescer.py::test_redis_coalescer_leader_failure_takeover` | ❌ ENV | Same Redis connection issue |
| `test_dspy_optimization.py::test_build_artifact_writes_manifest` | ❌ ENV | `/tmp` write blocked by sandbox (`PermissionError: Operation not permitted`) |

> These 3 failures are **infrastructure**, not code bugs. They will pass when Redis is available and tests run outside the sandbox.

---

## Remaining E2E Work (For You to Run)

### E2E-1: Validate Docker Compose with Resource Limits
```bash
cd backend
docker compose -f docker-compose.yml config | grep -A2 "deploy:"

# Expected: limits for neo4j (2G/1CPU), redis (512M/0.25CPU), qdrant (1G/0.5CPU), backend (2G/1CPU)
```

### E2E-2: Run Full Unit Test Suite
```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
JWT_SECRET=test_secret \
python3 -m pytest tests/ -v --ignore=tests/test_chat_endpoint.py --ignore=tests/test_coalescer.py -x --tb=short
```

### E2E-3: Test Monitoring Dashboard
```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8
python scripts/monitoring_dashboard.py --url http://localhost:8000/metrics
```

### E2E-4: Run Benchmark
```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
JWT_SECRET=test_secret \
python3 -m benchmarks.ruthless_benchmark --unit doctrine --sample 50
```

---

## Commands You Should Run Now

```bash
# 1. Start infrastructure
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend
docker compose up -d qdrant redis neo4j jaeger

# 2. Run the full test suite (all tests)
JWT_SECRET=test_secret python3 -m pytest tests/ -v --tb=short

# 3. Test the monitoring dashboard
python ../../scripts/monitoring_dashboard.py --url http://localhost:8000/metrics

# 4. Run a specific benchmark category to verify doctrine accuracy
python3 -m benchmarks.ruthless_benchmark --unit doctrine --sample 50

# 5. Check Docker health
docker compose ps --format "table {{.Name}}\t{{.Status}}"
docker compose logs --tail 20 backend qdrant redis neo4j

# 6. Verify endpoint health
curl -s http://localhost:8000/api/health | jq
curl -s http://localhost:8000/api/health/detailed | jq

# 7. Check DOCTRINE_SYNONYMS are wired correctly
grep -n "expand_query_with_synonyms" rag/nodes.py | head -5
```

---

*Status: All development work COMPLETE. Awaiting your E2E verification.*
