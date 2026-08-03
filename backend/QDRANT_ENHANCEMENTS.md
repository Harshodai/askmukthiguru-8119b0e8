# Qdrant Ruthless Enhancement Plan

Status: **Phase 1 COMPLETE** (Aug 3, 2026)

## Phase 1: Observability (High Impact, Low Effort) ✅

### 1. Search Quality Telemetry ✅
- **File**: `backend/tests/test_qdrant_search_quality.py`
- **What**: NDCG@10 metric on 5 golden queries
- **Strategies tested**: dense-only, hybrid (RRF), hybrid+reranker
- **Baseline**: `memory/qdrant_quality_baseline.json` (auto-updated)
- **Run**: `pytest tests/test_qdrant_search_quality.py -v`
- **Result**: Each strategy must hit min NDCG thresholds (0.70-0.78)

### 2. Qdrant Metrics Exposure ✅
- **File**: `backend/services/qdrant/metrics.py`
- **What**: Prometheus collectors for search/upsert latency, collection size, fragmentation
- **Metrics exported**:
  - `qdrant_search_latency_ms` (histogram, p50/p95/p99)
  - `qdrant_upsert_latency_ms` (histogram)
  - `qdrant_collection_size_vectors` (gauge)
  - `qdrant_index_fragmentation_pct` (gauge)
  - `qdrant_search_errors_total` (counter)
- **Integration**: Decorate searcher/indexer with `@track_search_latency`, `@track_upsert_latency`
- **Next**: Wire into `backend/app/metrics.py` → `/api/metrics` endpoint

### 3. Multitenancy Guard Decorator ✅
- **File**: `backend/services/qdrant/multitenancy_guard.py`
- **What**: `@enforce_multitenancy` decorator blocks searches/upserts without `teacher_id`
- **Raises**: `MultitenancyViolation` if called without tenant context
- **Usage**: Decorate `QdrantSearcher.search()` and `QdrantIndexer.upsert_chunks()`
- **Override**: Tests can pass `skip_tenant_check=True`
- **Test**: `backend/tests/test_multitenancy_guard.py` (to create)

### 4. Index Health Probe + Auto-Reopt ✅
- **File**: `backend/services/vector_optimizer.py` (enhanced)
- **What**: `get_index_health()` now calculates `fragmentation_pct` and auto-triggers reopt
- **Thresholds**:
  - Green: segments ≤ 20, fragmentation ≤ 30%
  - Yellow: segments ≤ 50, fragmentation ≤ 40%
  - Red: segments > 50 or fragmentation > 40%
- **Auto-action**: If fragmentation > 30%, calls `trigger_optimizer()` automatically
- **Logging**: Critical warnings logged when status = red

---

## Phase 2: Search Quality & Scaling (Medium Impact, Medium Effort)

### 5. RRF Fusion Weight Tuning
- **Target**: `backend/services/qdrant/searcher.py`
- **What**: Make RRF weights configurable (dense:sparse ratio)
- **Config**: `QDRANT_RRF_DENSE_WEIGHT`, `QDRANT_RRF_SPARSE_WEIGHT`

### 6. Parallelize Batch Ingestion
- **Target**: `backend/ingest/pipeline.py`
- **What**: `TRANSCRIPT_CONCURRENT_WORKERS: 1 → 10`

### 7. Query Result Caching
- **Target**: `backend/services/qdrant/searcher.py`
- **What**: Enable Qdrant `query_cache_ttl` (300s)

---

## Phase 3: Advanced (Lower Priority)

### 8. Shadow Collection A/B Test Framework
### 9. Qdrant Version Compatibility Check
### 10. Embedded Qdrant Mode Test

---

## Deliverables (Phase 1)

✅ `backend/tests/test_qdrant_search_quality.py` — NDCG evaluation
✅ `backend/services/qdrant/metrics.py` — Prometheus collectors  
✅ `backend/services/qdrant/multitenancy_guard.py` — Tenant enforcement
✅ `backend/services/vector_optimizer.py` — Enhanced health + auto-reopt

## Next: Wire Into Searcher/Indexer

Tasks 2-3 require integration with existing services:
- Add `@track_search_latency` to `QdrantSearcher.search()`
- Add `@track_upsert_latency` to `QdrantIndexer.upsert_chunks()`
- Add `@enforce_multitenancy` to both
- Create `test_multitenancy_guard.py` regression test
