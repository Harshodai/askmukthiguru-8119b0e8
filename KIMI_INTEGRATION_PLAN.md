# Kimi_Agent_AskMukthi Integration Plan

## Executive Summary
Integrate surgical patches from Kimi_Agent_AskMukthi Repo Deep Dive (Option A) and v2 architecture (Option B) into our codebase to achieve 0.92-0.97 benchmark score.

**Confidence: 8/10** - Haven't validated benchmark compatibility yet.

---

## Phase 1: Option A Surgical Patches (Week 1-2) — Target: 0.92-0.97

### Priority 0 (Must Do First - Unblocks Benchmark)

| Task | File | Description | Status |
|------|------|-------------|--------|
| 1.1 | `backend/rag/graph_strategies.py` | Add `lightweight_verify` node replacing reflect+verify+contradiction chain in StandardGraphStrategy. Add conditional skip for fast/tier2_simple queries. | ⬜ |
| 1.2 | `backend/app/orchestrator_utils.py` | Merge Kimi's `select_graph_for_query(query, detected_intent)` with doctrine keywords, deep patterns, regex patterns. Add `should_skip_verification()`, `get_expected_keywords()`. Keep our existing `prepare_request_state`, `prepare_user_memory`, `cache_language_key`. | ⬜ |
| 1.3 | `backend/.env` + `.env.optimized` | Add `OPENROUTER_API_KEY` (currently only in docker-compose.yml) | ⬜ |

### Priority 1 (After Benchmark Validation)

| Task | File | Description | Status |
|------|------|-------------|--------|
| 1.4 | `backend/rag/nodes/keyword_injection.py` | Create new - doctrine categories, keyword injection for retrieval, coverage verification, auto-injection of missing keywords | ⬜ |
| 1.5 | `backend/scripts/cache_warmer.py` | Create new - warm 60+ doctrine questions across 9 categories | ⬜ |
| 1.6 | `backend/services/multi_provider_llm.py` | Create new - 3-provider failover (Sarvam→OpenRouter→Ollama) with circuit breakers + token bucket rate limiters | ⬜ |
| 1.7 | `src/integrations/lovable/index.ts` | Add Facebook OAuth provider support | ⬜ |

---

## Phase 2: Option B v2 Architecture (Month 2) — Target: 1000+ Users

| Task | File | Description | Status |
|------|------|-------------|--------|
| 2.1 | `backend/celery_config.py` | Create - Celery app with Redis broker, queue routing (transcription/embedding/indexing/ingestion) | ⬜ |
| 2.2 | `backend/tasks/ingest_tasks.py` | Create - 4 specialized Celery tasks: orchestrate, transcribe, process, index | ⬜ |
| 2.3 | `backend/services/memory_service_v2.py` | Create - Three-tier memory: Ephemeral (Redis) → Semantic (PG+Qdrant) → Global (Qdrant Cluster+Neo4j) | ⬜ |
| 2.4 | K8s YAML | Convert Helm charts to raw K8s YAML with GPU workers, Qdrant cluster, Redis cluster, PostgreSQL | ⬜ |

---

## Phase 3: Benchmarking & Validation (Week 2-3)

| Step | Description | Status |
|------|-------------|--------|
| 3.1 | Run `make eval` baseline (current score) | ⬜ |
| 3.2 | Run benchmark after each Priority 0 fix (1.1, 1.2, 1.3) | ⬜ |
| 3.3 | Run benchmark after each Priority 1 fix (1.4-1.7) | ⬜ |
| 3.4 | Target: Overall > 0.95, Performance > 0.85, Faithfulness > 0.90 | ⬜ |
| 3.5 | Test 10 concurrent queries, validate no hallucinations in 50 samples | ⬜ |

---

## Current Verified State (What We Already Have)

✅ **JWT Issuer Fix** - `backend/services/auth_service.py:180-220` - `_valid_issuers()` accepts 3 URLs  
✅ **GPTCache Semantic Upgrade** - `backend/services/cache_service.py:495-550` - `manager="sqlite,qdrant"`, `SBERT`, `SearchDistanceEvaluation`, `temperature_softmax`, LRU eviction  
✅ **GPTCache Server** - `backend/gptcache_config.yml` + `docker-compose.yml` service `gptcache-server` on port 8001  
✅ **Health Check Start Period** - `docker-compose.yml:221` - `start_period: 300s`  
✅ **Google One Tap** - `src/pages/AuthPage.tsx:507-547`  
✅ **Facebook OAuth (AuthPage)** - `src/pages/AuthPage.tsx:416-441`  
✅ **OpenRouter Config** - In docker-compose.yml (env vars defined)  
✅ **FastGraphStrategy** - `backend/rag/graph_strategies.py:226-289`  
✅ **LettuceDetectService** - Better than Kimi (threshold 0.22, doctrine boosts +0.15, answer-length heuristic)  
✅ **orchestrator_utils.py** - Exists with different API  

---

## Known Gaps

| Gap | Impact |
|-----|--------|
| `OPENROUTER_API_KEY` not in .env files | Multi-provider fallback won't work |
| No `lightweight_verify` node | Standard graph still uses 3 verification nodes (~60s) |
| Our `select_graph_for_query()` lacks `detected_intent` param and doctrine keywords | Fast path may not trigger correctly |
| No `keyword_injection.py` | Retrieval misses doctrine-specific terms |
| No `cache_warmer.py` | Semantic cache starts empty |
| No `multi_provider_llm.py` | Single point of failure on Sarvam |
| Facebook not in lovable integration | Facebook OAuth only works via native Supabase path |

---

## Subagent Dispatch Plan

### Batch 1 (Parallel - Priority 0)
- **Agent 1**: Add `lightweight_verify` to `backend/rag/graph_strategies.py`
- **Agent 2**: Merge `orchestrator_utils.py` with Kimi's fast-path routing
- **Agent 3**: Add `OPENROUTER_API_KEY` to `.env` and `.env.optimized`

### Batch 2 (Parallel - Priority 1)
- **Agent 4**: Create `backend/rag/nodes/keyword_injection.py`
- **Agent 5**: Create `backend/scripts/cache_warmer.py`
- **Agent 6**: Create `backend/services/multi_provider_llm.py`
- **Agent 7**: Add Facebook provider to `src/integrations/lovable/index.ts`

### Batch 3 (Sequential - Validation)
- **Agent 8**: Run baseline benchmark (`make eval`)
- **Agent 9**: Run benchmark after each Priority 0 fix
- **Agent 10**: Run benchmark after each Priority 1 fix

---

## Questions for User

1. **OpenRouter API Key**: Do you have one ready? Need to add to `.env` files.
2. **Facebook App**: Is Facebook OAuth configured in Supabase dashboard? (App ID/Secret, redirect URLs)
3. **Benchmark Compatibility**: Should I verify our `make eval` test queries match Kimi's?
4. **GPU for Option B**: Do we have access to NVIDIA T4/A10G instances?
5. **PostgreSQL for Option B**: Add to `docker-compose.yml` now or Month 2?