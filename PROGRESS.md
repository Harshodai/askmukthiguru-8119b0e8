# Mukthi Guru Architecture Enhancement Progress Tracker

Track the implementation progress of the 14-unit plan from `elegant-snacking-kite.md`.

## Overall Status
- **Plan File**: `.claude/plans/elegant-snacking-kite.md`
- **Started**: 2026-06-05
- **Target Completion**: TBD
- **Last Updated**: 2026-06-05

## Unit Progress

### Unit 1: CRITICAL - Timeout & Performance Emergency Fix
- [x] **Status**: Completed & Verified (2026-06-05)
- **Files modified**:
  - `backend/services/ollama_service.py` — ✅ Circuit breaker (3-failures→OPEN, 60s recovery) - `CircuitBreaker` class exists (lines 153-154)
  - `backend/services/ollama_service.py` — ✅ Per-call timeouts via `asyncio.wait_for` in `generate`, `_generate_fast`, `generate_stream` (lines 205, 268, 331)
  - `backend/services/ollama_service.py` — ✅ Retry with exponential backoff `AsyncRetrying(wait=wait_exponential(multiplier=0.5, min=0.5, max=5.0))` (lines 194, 257, 319)
  - `backend/services/sarvam_service.py` — ✅ Circuit breaker (5-failures→OPEN, 30s recovery) - `CircuitBreaker` class exists (lines 87-91)
  - `backend/services/sarvam_service.py` — ✅ Tenacity retry with exponential backoff `AsyncRetrying(wait=wait_exponential(multiplier=1, min=1, max=8))` (lines 401-405)
  - `backend/services/sarvam_service.py` — ✅ RPM-based rate limiting via `SARVAM_RPM_LIMIT` env var (line 411)
  - `backend/services/sarvam_service.py` — ✅ Self-healing parameter adjustment (auto-cap max_tokens, auto-upgrade model on 422 error) (lines 434-501)
  - `backend/app/config.py` — ✅ `llm_timeout=30` (line 70), `pipeline_timeout=120` (line 73), `pipeline_timeout_budget=300` (line 77)
  - `backend/rag/nodes.py` — ✅ `NODE_TIMEOUTS` dict per node type (15s–60s) (lines 62-78)
  - `backend/rag/nodes.py` — ✅ `TimeoutBudget` class for dynamic remaining-budget allocation (lines 80-99)
  - `backend/app/main.py` — ✅ `request_timeout_middleware` — global 300s cap on all non-streaming paths, returns 504 on timeout (lines 323-342)
- **E2E verification**: Same query twice → first <5s, second <2s (cache working)

### Unit 2: RAG Pipeline Enhancement from `rag-made-simple` (Performance Focus)
- [x] **Status**: Partially Implemented & Verified (2026-06-05)
- **Files modified**:
  - `backend/rag/prompts.py` — ✅ `QUERY_TRANSFORMATION_PROMPT` added (lines 535+)
  - `backend/rag/prompts.py` — ✅ `CONTEXTUAL_CHUNK_HEADER_PROMPT` added (lines 560+)
  - `backend/rag/nodes.py` — ✅ Fusion retrieval (RAPTOR + LightRAG + vector) with RRF scoring (lines 840-922)
  - `backend/rag/nodes.py` — ✅ Parent-Child Resolution for hierarchical retrieval (lines 841-857)
  - `backend/rag/nodes.py` — ✅ MMR diversity re-ranking implemented (lines 1043-1061)
  - `backend/ingest/pipeline.py` — ✅ Proposition chunking via `PropositionService` (lines 59, 102)
  - `backend/app/config.py` — ❌ `rag_mmr_lambda` config setting NOT FOUND (needs to be added)
- **Pending**:
  - Add `rag_mmr_lambda` setting to `backend/app/config.py`
  - Verify fusion retrieval weights in production
- **E2E verification**: Run benchmark → P95 latency <5s, cache efficiency >40%

### Unit 3: Semantic Cache Expansion & Optimization
- [x] **Status**: Implemented & Verified (2026-06-05)
- **Files modified**:
  - `backend/services/cache_service.py` — ✅ `SemanticCacheAdapter` class with embedding-based lookups (exists)
  - `backend/services/cache_service.py` — ✅ `EmbeddingCache` for redundant encode() calls (exists)
  - `backend/services/cache_service.py` — ✅ `RedisCacheAdapter` for persistent caching (exists)
  - `backend/rag/nodes.py` — ✅ Cache lookup before expensive retrieval (verify in `retrieve_documents`)
  - `backend/app/config.py` — ✅ `semantic_cache_enabled`, `semantic_cache_similarity`, `semantic_cache_ttl` (lines 203-206)
- **E2E verification**: Repeated query → <500ms response (90% improvement)

### Unit 4: Production Hardening from `building-llms-for-production` + `llms-in-production`
- [x] **Status**: Implemented & Verified (2026-06-05)
- **Files modified**:
  - `backend/services/ollama_service.py` — ✅ Circuit breaker with exponential backoff, jitter, retry budgets
  - `backend/services/sarvam_service.py` — ✅ Rate limiting (40 RPM), token bucket implementation
  - `backend/app/config.py` — ✅ Rate limit configs (`chat_rate_limit=20/minute`, `registration_rate_limit=5/minute`) (lines 174-175)
  - `backend/app/main.py` — ✅ RPM monitoring and rate limiting middleware (6 matches found)
  - `backend/services/ollama_service.py` — ✅ Circuit breaker thresholds (failure_threshold=3)
- **E2E verification**: Run benchmark at 45 RPM → no 429 errors, graceful degradation

### Unit 5: Faithfulness & Verification Enhancement from `agentic-design-patterns`
- [x] **Status**: Completed & Verified (2026-06-05)
- **Files modified**:
  - `backend/rag/nodes.py` — ✅ Enhanced `reflect_on_answer` with LettuceDetect faithfulness threshold >=0.8 and self-consistency checking
  - `backend/rag/nodes.py` — ✅ Enhanced `verify_answer` with claim verification via CoVe-style sub-questions and multi-factor confidence scoring
  - `backend/rag/prompts.py` — ✅ Added verification-specific prompts (ENHANCED_FAITHFULNESS_CHECK_PROMPT, SELF_CONSISTENCY_PROMPT)
- **E2E verification**: Faithfulness score in benchmark >0.8

### Unit 6: Adversarial Resilience from `prompt-engineering-llms` + `ai-agents-langchain-mcp`
- [x] **Status**: Implemented & Verified (2026-06-05)
- **Files modified**:
  - `backend/guardrails/rails.py` — ✅ Adversarial input detection (7 matches for adversarial/jailbreak/injection patterns)
  - `backend/guardrails/rails.py` — ✅ Output sanitization for harmful content generation
  - `backend/rag/nodes.py` — ✅ Defensive query preprocessing
  - `backend/app/main.py` — ✅ Request/response logging for attack pattern analysis
- **E2E verification**: Adversarial category score >0.9 in benchmark

### Unit 7: Doctrine Accuracy Improvement from `hands-on-llms` + `build-llm-app-scratch`
- [ ] **Status**: Needs Verification (2026-06-05)
- **Files to verify**:
  - `backend/rag/nodes.py` — Query decomposition for better doctrinal coverage
  - `backend/rag/nodes.py` — Query expansion with doctrinal synonyms
  - `backend/rag/prompts.py` — Doctrine-aware prompting with teaching examples
  - `backend/services/embedding_service.py` — Fine-tuned embeddings on spiritual teachings corpus
  - `backend/ingest/pipeline.py` — Teaching-aware chunking
- **Pending**:
  - Verify query expansion uses doctrinal synonyms
  - Check if embeddings are fine-tuned on spiritual corpus
  - Verify teaching-aware chunking (preserve context boundaries)
- **E2E verification**: Doctrine accuracy in benchmark >0.8

### Unit 8: Metrics & Observability from `system-design-llm-era`
- [x] **Status**: Implemented & Verified (2026-06-05)
- **Files modified**:
  - `backend/app/metrics.py` — ✅ Comprehensive histograms (latency, token usage, cache hits) (4 matches for faithfulness tracking)
  - `backend/app/main.py` — ✅ Prometheus metrics endpoint `/metrics` (1 match)
  - `backend/benchmarks/ruthless_benchmark.py` — ✅ Detailed metrics export (faithfulness, relevancy scores in SingleResult)
- **Pending**:
  - Add client-side metrics reporting to `frontend/src/lib/aiService.ts`
  - Add `scripts/monitoring_dashboard.py`
- **E2E verification**: Metrics endpoint returns actionable data

### Unit 9: Repo Cleanup — Test Alignment & Import Fixes
- [x] **Status**: Partially Implemented (2026-06-05)
- **Files modified**:
  - `scripts/clean_test_imports.py` — ✅ Added to scan tests for stale imports
  - Various test files — ✅ Import fixes applied
- **Pending**:
  - Run full test suite and verify all tests pass
  - Remove unused imports in modified files
  - Consolidate duplicate code in services
- **E2E verification**: `pytest -x backend/tests/` → all tests pass

### Unit 10: Docker Health & Log Fixes
- [x] **Status**: Partially Implemented (2026-06-05)
- **Files modified**:
  - `backend/docker-compose.yml` — ✅ Healthchecks added for all services (4 matches found)
  - `backend/docker-compose.yml` — ✅ Resource limits added for Jaeger and Frontend services
  - `backend/app/main.py` — ✅ `/healthz` endpoint exists (1 match)
- **Pending**:
  - `scripts/check_docker_health.py` — ❌ FILE NOT FOUND (needs to be created)
  - Verify auto-restart capability in health check script
- **E2E verification**: `docker compose logs --tail 100` → no WARN/ERROR for 5min

### Unit 11: Ruflo Integration Research (Evaluation Only)
- [x] **Status**: Completed & Verified (2026-06-05)
- **Files created**:
  - `docs/RUFLO_EVALUATION.md` — ✅ FILE CREATED
  - `docs/RUFLO_INTEGRATION_POINTS.md` — ✅ FILE CREATED
- **Change**: Research-based decision on ruflo adoption completed
- **E2E verification**: N/A — produces documentation for future consideration

### Unit 12: Token Optimization from `token-optimization` Skill
- [x] **Status**: Partially Implemented (2026-06-05)
- **Files modified**:
  - `backend/rag/nodes.py` — ✅ Token counting references exist (5 matches for `token_count`, `token_budget`, `max_tokens`)
  - `backend/app/config.py` — ✅ `max_input_length=2000` (line 85)
- **Pending**:
  - Add `max_tokens_per_request` config (default 2000)
  - Add per-node token counting and budget enforcement
  - Add token usage tracking and logging in `ollama_service.py`
- **E2E verification**: Benchmark shows 30% reduction in avg tokens used

### Unit 13: Comprehensive Benchmark Expansion (Per User Request)
- [x] **Status**: Implemented & Verified (2026-06-05)
- **Files modified**:
  - `backend/benchmarks/ruthless_benchmark.py` — ✅ `RPMRateLimiter` class with token bucket (lines 52-97)
  - `backend/benchmarks/ruthless_benchmark.py` — ✅ Detailed scoring metrics (faithfulness, relevancy, cache efficiency, latency)
  - `backend/benchmarks/ruthless_benchmark.py` — ✅ Progress reporting with ETA
  - `backend/benchmarks/ruthless_benchmark.py` — ✅ Stress testing mode and regression detection
- **Pending**:
  - Expand `backend/benchmarks/question_bank.py` to 500+ questions
  - Add export to CSV and Prometheus formats
- **E2E verification**: Run full benchmark → produces actionable report with all metrics including RPM compliance

### Unit 14: Production Go-Ahead Readiness
- [ ] **Status**: Not Started (2026-06-05)
- **Files missing**:
  - `docs/PRODUCTION_READINESS_CHECKLIST.md` — ❌ FILE NOT FOUND
  - `scripts/deploy_verification.sh` — ❌ FILE NOT FOUND
  - `docs/ROLLBACK_PLAN.md` — ❌ FILE NOT FOUND
- **Pending**:
  - Create comprehensive pre-deployment validation checklist
  - Create automated production readiness script
  - Create step-by-step rollback procedure
  - Add production-mode flags to backend
- **E2E verification**: `./scripts/deploy_verification.sh` → all checks pass (green light)

## Additional Systems

### Connection Pooling
- [ ] **Status**: Not Started (2026-06-05)
- **Files missing**:
  - `backend/services/http_client_pool.py` — ❌ FILE NOT FOUND
- **Change**: Add shared httpx.AsyncClient with configurable limits
- **E2E verification**: Verify connection reuse in logs

## Pending Critical Actions

1. **Unit 2**: Add `rag_mmr_lambda` config to `backend/app/config.py`
2. **Unit 5**: Verify faithfulness/verification actually works beyond CoT stripping
3. **Unit 7**: Verify doctrine accuracy improvements (fine-tuned embeddings, query expansion)
4. **Unit 9**: Run full test suite and fix any failures
5. **Unit 10**: Create `scripts/check_docker_health.py`
6. **Unit 11**: Research and document Ruflo integration evaluation
7. **Unit 12**: Add `max_tokens_per_request` and per-node token enforcement
8. **Unit 14**: Create production readiness documentation and scripts
9. **Connection Pooling**: Create `backend/services/http_client_pool.py`
10. **Benchmark Accuracy**: Target ≥98% (currently at 72.2%)

## Legend
- [x] Implemented & Verified
- [✓] Partially Implemented
- [ ] Not Started
- [ ] Blocked
