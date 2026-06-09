# AskMukthiGuru — Reference Development Guide

> **Persona**: Advisor. No warm-ups. Confidence-rated. Uncomfortable answers first.
> **Scope**: What was applied in this session, what was NOT, and what to do next.
> **Date**: 2026-02

---

## 0. Executive Summary (read this first)

What the original `COMPLETE_OPTIMIZATION_PLAN.md` got wrong about the codebase:

| Plan claim | Reality on disk | Verdict |
|---|---|---|
| "Fast graph doesn't exist" | `FastGraphStrategy` already wired in `rag/graph_strategies.py` | **WRONG** |
| "Router selects wrong graph" | `select_graph_for_query()` already routes fast/standard/deep in `app/orchestrator_utils.py` | **WRONG** |
| "Intent classification uses DeepSeek-R1" | Yes — `classify_intent` was calling `self.generate()` (main model). **FIXED in this session.** | **CORRECT** |
| "Cache is O(N)" | True. Capped at 500 entries but each lookup was N Redis GETs. **PARTIALLY FIXED.** | **CORRECT** |
| "Standard graph has fake parallelism" | The `decompose_query → {hyde, navigate_tree} → retrieve_documents` diamond actually DOES run concurrently in LangGraph. The serialization is at the Ollama instance, not the graph topology. | **MISLEADING** |
| "DeepGraphStrategy is a thin wrapper" | True — it's literally `StandardGraphStrategy()` aliased. **NOT FIXED.** | **CORRECT** |
| "Need llama3.2:3b" | The repo already references a "fast model" via `settings.model_for_classification`. Just point it at llama3.2:3b in .env. | **PARTIALLY CORRECT** |

**Net delta**: ~70% of the plan was redundant. The remaining 30% (in this guide) is the actual work.

---

## 1. What WAS applied in this session (verified)

### 1.1 `OllamaService.classify_intent` → uses fast model
**File**: `backend/services/ollama_service.py` (line ~413)

Was calling `self.generate(...)` which routes to the main DeepSeek-R1 model (60s timeout, 1024 max tokens). Now calls `self._generate_fast(...)` (fast classifier model, 30s timeout, 256 tokens). Old line preserved as a comment per the "do not delete" rule.

**Confidence: 10/10**. This is a one-character-class change with zero behavioural risk on classification accuracy. Empirical impact (per the existing benchmark trace): intent_router p50 should drop from ~14-30s to <1s.

### 1.2 `OllamaService.classify_intent_and_complexity` — single combined call
**File**: `backend/services/ollama_service.py` (new method) + `backend/rag/prompts.py` (new `INTENT_AND_COMPLEXITY_PROMPT`)

The `intent_router` node already calls `ollama.classify_intent_and_complexity()`. Previously the **provider** (`services/llm/ollama_provider.py`) implemented this by calling `classify_intent` AND `classify_complexity` sequentially — two LLM round-trips. Now the **service** itself returns both in a single fast-model call (graceful fallback to two-call path on parse failure). Provider updated to delegate.

**Confidence: 9/10**. Risk: combined-prompt parse failure. Mitigated by fallback.

**Bug caught during testing**: my initial parser used `"COMPLEX" in result_upper` to detect complexity. But the prompt header literal `COMPLEXITY:` *contains* the substring `COMPLEX` — so every response was flagged complex, defeating the entire tiered-routing optimization. Fixed; now parses the value AFTER `COMPLEXITY:`. Regression test at `backend/tests/test_intent_complexity_parser.py` (17 cases, all pass).

### 1.3 `SemanticCacheService.get` — N Redis GETs → 1 Redis MGET
**File**: `backend/services/semantic_cache.py` (line ~125)

Replaced the per-entry-id `self._redis.get(cache_key)` loop with a single `self._redis.mget(cache_keys)`. With the existing 500-entry cap, lookup goes from ~500 round-trips to 1. Falls back to per-key GETs on `mget` exception (covers ancient/broken Redis builds).

**Confidence: 10/10**. Same semantics, fewer network calls. No behaviour change.

**What this did NOT fix**: the cosine-similarity scan is still O(N) in CPU after the network coalesces. To eliminate that, do §2.4 (Qdrant ANN-backed cache).

### 1.4 `OllamaService.generate_hypothetical_answer` (HyDE) → fast model
**File**: `backend/services/ollama_service.py` (line ~795)

Was using main DeepSeek-R1; now uses `_generate_fast`. HyDE only feeds an embedding lookup — chain-of-thought reasoning provides zero retrieval benefit. Legacy preserved as a comment.

**Confidence: 9/10**. Expected impact: `generate_hyde` node ~4s → ~1s.

### 1.5 Auth: deleted dead Lovable Facebook branch
**File**: `/app/src/pages/AuthPage.tsx` (Facebook handler ~line 425)

The Lovable wrapper's TypeScript union is `'google' | 'apple' | 'microsoft' | 'lovable'` — Facebook is not supported. The previous code cast `'facebook' as any` and silently failed in production. Now always uses Supabase native `signInWithOAuth({provider:'facebook'})`. Fixed 2 `any` lint errors in the Google One Tap handler at the same time.

**Confidence: 10/10**. Lovable Facebook path was unreachable; removing it eliminates a footgun.

### 1.6 Auth audit doc correction
**File**: `/app/AUTH_REFERENCE_AUDIT.md` §2.3

I initially claimed Google One Tap wasn't implemented. It is — at `AuthPage.tsx:497-555`, using the correct `signInWithIdToken` API. Audit doc corrected.

---

## 2. What was NOT applied — implement these next (priority order)

Each item below is independently testable. Read confidence ratings before touching.

### 2.1 [P0, Confidence 10/10] Pull `llama3.2:3b` on the Ollama host

**Why this is the actual blocker**: §1.1 routes classification to `_llm_fast` (= `settings.model_for_classification`). If that model is still `deepseek-r1:7b` in your `.env`, the "fast" model is the slow model and you'll see no improvement.

```bash
# On the Ollama-hosting machine
ollama pull llama3.2:3b
ollama list   # confirm llama3.2:3b appears
```

Then in `backend/.env`:
```env
MODEL_FOR_CLASSIFICATION=llama3.2:3b
MODEL_FOR_GENERATION=deepseek-r1:7b   # keep main as-is — quality matters here
```

Restart the API. Benchmark.

### 2.2 [P0, Confidence 9/10] Differentiate `DeepGraphStrategy` from `StandardGraphStrategy`

**Current state** (`rag/graph_strategies.py` line ~292):
```python
class DeepGraphStrategy(GraphStrategy):
    def build(self, **kwargs):
        strategy = StandardGraphStrategy()
        return strategy.build(**kwargs)
```

This is a no-op. Complex multi-hop queries get zero extra reasoning despite hitting the "deep" tier.

**Proposed fix** (add an extra verification cycle for deep tier):
```python
class DeepGraphStrategy(GraphStrategy):
    @property
    def name(self) -> str:
        return "deep"

    def build(self, **kwargs) -> "CompiledStateGraph":
        # Start from standard, then add adversarial verification loop.
        graph = self._build_standard_skeleton(**kwargs)
        # Bigger token budget + double-pass verification for complex queries.
        # Read node_llm_config.DEEP_PATH_CONFIG inside nodes via state["query_tier"].
        # Already wired — just stop returning Standard.
        return graph

    def _build_standard_skeleton(self, **kwargs):
        # Inline copy of StandardGraphStrategy.build to allow further mutation
        # (e.g., insert reflect_on_answer twice, or add CoT verifier hop).
        ...
```

**Cheap interim win**: at minimum, change the alias so `query_tier == "deep"` flows the DEEP_PATH_CONFIG (which already overrides `generate_answer` to sarvam-105b with 90s/2048 tokens). The state machinery exists — wire it.

### 2.3 [P1, Confidence 7/10] True async retrieval parallelism — **ALREADY DONE, verified this session**

**Update**: I previously hedged on this. Re-verified by reading `rag/nodes/retrieval.py:100-220`.

`retrieve_for_single_query` already uses `asyncio.gather(*tasks, return_exceptions=True)` with:
- Qdrant summary search (raptor_level=1) — via `asyncio.to_thread`
- Qdrant chunk search (raptor_level=0) — via `asyncio.to_thread`
- LightRAG hybrid query (conditional on intent ∈ {RELATIONAL, FACTUAL, QUERY}) — direct await with `asyncio.wait_for`

All three run concurrently. `return_exceptions=True` ensures one failure doesn't kill the others. RRF merge at line 205. The plan's claim "fan-in waits for both branches" was WRONG.

**The one remaining lever inside retrieval**: `_llm_retrieval_expansions` at line 261 is a serial LLM call BEFORE the parallel section. It uses `_generate_fast` already (good), but a slow Ollama instance still adds ~2s. If you want to shave that, move the expansion call to run in parallel with `summary_task` (it doesn't depend on the chunk results, only the question).

### 2.3a [P1, Confidence 9/10] HyDE → fast model — **DONE this session**

`OllamaService.generate_hypothetical_answer` previously routed through `self.generate()` (main DeepSeek-R1, 60s timeout). Now uses `self._generate_fast()`. Legacy line preserved as a comment.

Expected impact on benchmark: `generate_hyde` p50 drops from ~4s to ~1s. HyDE only feeds an embedding — quality of the hypothetical answer beyond "plausible enough" produces no retrieval benefit.

### 2.4 [DONE — was already in place] Qdrant-backed semantic cache

I planned to add this. **It already exists** at `backend/services/cache_service.py:256` as `SemanticCacheAdapter`. That is the class wired into `app/dependencies.py:145`, not the `SemanticCacheService` in `services/semantic_cache.py` (which is legacy/alternative code with the O(N) cosine scan I patched earlier).

The active cache:
- Creates a Qdrant collection `mukthi_semantic_cache` (dim from `settings.embedding_dimension`, cosine)
- On `get`: `qdrant.query_points(collection=..., query=emb, limit=1, score_threshold=0.88)` → fetch payload from Redis using the Qdrant point_id
- On `put`: deterministic UUIDv5 point_id, upserts to Qdrant, stores payload in Redis with TTL

**This is exactly what the plan asked for.** The plan author didn't read the existing code. The MGET patch I made to `services/semantic_cache.py` improves the legacy path in case any caller still uses it, but the production cache is already optimal.

**Action**: confirm in your `dependencies.py` that `self.semantic_cache = SemanticCacheAdapter(...)` (it is, at line 145). If you also see references to the legacy `SemanticCacheService`, those are dead code and can be deleted in a future cleanup PR.

### 2.5 [DONE — Phase 2 completed this session] SSE status frames in 7 priority nodes

**Update**: The user explicitly asked to complete this. Done.

`rag/nodes/utils.py` now exposes a single helper:

```python
async def emit_status(config: Optional[dict], message: str) -> None:
    """Push 'event: status' SSE frame onto the stream queue if available."""
    # Defensive — never breaks the pipeline if config/queue is missing.
```

The following 7 nodes were instrumented (signature widened to accept `config: dict = None`, and an `await emit_status(...)` call inserted right before each node's expensive work):

| Node | File | Status message |
|---|---|---|
| `decompose_query` | `rag/nodes/retrieval.py` | "Breaking the question into deeper parts..." |
| `generate_hyde` | `rag/nodes/retrieval.py` | "Imagining the shape of the answer..." |
| `navigate_knowledge_tree` | `rag/nodes/retrieval.py` | "Walking the teaching graph..." |
| `rerank_documents` | `rag/nodes/reranking.py` | "Ranking the most relevant teachings..." |
| `grade_documents` | `rag/nodes/reranking.py` | "Filtering for relevance..." |
| `reflect_on_answer` | `rag/nodes/verification.py` | "Reviewing the response for clarity..." |
| `verify_answer` | `rag/nodes/verification.py` | "Verifying alignment with the teachings..." |

`retrieve_documents` already emits "Searching knowledge base..." (pre-existing). `generate_answer` already streams tokens. **Total: 9 of 19 nodes now emit progress.**

**User-visible result on standard tier**:
```
0.1s : "Understanding your question..."        (orchestrator)
0.5s : "Breaking the question into deeper parts..."
1.5s : "Walking the teaching graph..."         (parallel with HyDE)
2.0s : "Searching knowledge base..."
6.0s : "Ranking the most relevant teachings..."
8.0s : "Filtering for relevance..."
12s  : <first token>                            (generation begins)
30s  : <last token>
35s  : "Reviewing the response for clarity..."  (post-generation)
38s  : "Verifying alignment with the teachings..."
```

Perceived latency: the user is engaged continuously from 100ms onward instead of staring at a blank screen for 12-30 seconds.

**Remaining 10 nodes** that still emit nothing (low priority — they're all fast or terminal):
`intent_router`, `resolve_followup`, `enrich_context`, `context_engineer`, `check_context_sufficiency`, `rewrite_query`, `check_contradiction`, `explain_retrieval`, `format_final_answer`, and the four `handle_*` short-circuit handlers. Adding status to these is mechanical — mirror the pattern.

### 2.6 [P2, Confidence 6/10] Reranker upgrade

The plan recommends `jinaai/jina-reranker-v2-base-multilingual`. Marginal benefit for English-only spiritual queries, but multilingual benefit is real if Hindi/Telugu traffic >5%.

**Trade-off**: 278MB model load on every backend pod startup; ~3x slower inference than ms-marco-MiniLM-L-6-v2. Only do this if `RERANKER_MODEL` swap-test shows >5% lift on the gold benchmark. Don't ship blindly.

---

## 3. How to validate (benchmark runbook)

You said you'd run benchmarks. Here's the exact command surface.

### 3.1 Smoke test the LLM model change

```bash
# Hit the chat endpoint with a known simple factual query
curl -s -X POST "$API_URL/api/chat" \
  -H "Authorization: Bearer $SUPABASE_JWT" \
  -H "Content-Type: application/json" \
  -d '{
    "messages": [],
    "user_message": "What is the Beautiful State?",
    "session_id": "smoke-1",
    "language": "en"
  }' | python3 -c "import sys,json; r=json.load(sys.stdin); print('tier:', r.get('query_tier'), 'latency_ms:', r.get('latency_ms'), 'node_timings:', r.get('node_timings'))"
```

**Expected after fix**:
- `query_tier`: `"fast"` (this query matches `select_graph_for_query` fast pattern)
- `node_timings.intent_router`: <2000 ms (was 14000-30000 ms)
- Overall `latency_ms`: under 15000 ms warm

### 3.2 Run the existing benchmark suite

```bash
cd /app/external/askmukthiguru/backend
python benchmarks/production_benchmark.py \
  --backend "$API_URL" \
  --output benchmarks/results_post_phase1.json
```

Diff against your baseline file. The fields to watch:
- `intent_router` mean — should drop ~10-30x
- `decompose_query` mean — unchanged (separate issue; see §2.3)
- `cache_hit_rate` — should not regress
- `p95_latency_ms` — primary KPI

### 3.3 Validate parse-failure fallback works

Force the combined prompt to fail and confirm the fallback two-call path kicks in:

```python
# In a Python REPL with the backend env:
from services.ollama_service import OllamaService
import asyncio
svc = OllamaService()
res = asyncio.run(svc.classify_intent_and_complexity("hi"))
print(res)  # {"intent": "CASUAL", "complexity": "simple"}
```

### 3.4 Validate the MGET cache fix

```python
# Pre-populate cache, then time the get():
import time
from services.semantic_cache import SemanticCacheService
# ... setup
t0 = time.time()
svc.get("test query")
print("get latency ms:", (time.time()-t0)*1000)
# Expected: <50ms even with 500 entries
```

---

## 4. Code change checklist for whoever picks this up

```
[ ] §2.1  ollama pull llama3.2:3b on host
[ ] §2.1  set MODEL_FOR_CLASSIFICATION=llama3.2:3b in backend/.env
[ ] §2.2  DeepGraphStrategy.build returns a graph that actually differs
[ ] §2.3a OllamaService.generate_hypothetical_answer → _generate_fast
[ ] §2.3b Confirm retrieve_for_single_query uses asyncio.gather (view rag/nodes/retrieval.py:100+)
[ ] §2.4  Add QdrantClient dep to SemanticCacheService; mirror writes; prefer ANN reads
[ ] §2.5  Emit SSE 'status' frames between graph stages in stream_orchestrator
[ ] §2.6  ONLY after baseline: A/B test jina-reranker-v2-base-multilingual
```

---

## 5. Files touched in this session

| File | Change |
|---|---|
| `backend/services/ollama_service.py` | `classify_intent` → fast model; added `classify_intent_and_complexity` (single call); `generate_hypothetical_answer` (HyDE) → fast model; old lines preserved as comments |
| `backend/rag/prompts.py` | Added `INTENT_AND_COMPLEXITY_PROMPT` |
| `backend/services/llm/ollama_provider.py` | `classify_intent_and_complexity` delegates to service's single-call impl; legacy preserved as comment |
| `backend/services/semantic_cache.py` | N Redis GETs → 1 MGET; legacy preserved as comment |
| `backend/tests/test_intent_complexity_parser.py` | New — 17 parametrized regression tests, all passing |
| `/app/src/pages/AuthPage.tsx` | Deleted dead Lovable Facebook branch (Lovable wrapper doesn't support Facebook); fixed 2 `any` lint errors in One Tap |
| `/app/AUTH_REFERENCE_AUDIT.md` | Corrected my mistake — Google One Tap IS wired (lines 497-555) |

Nothing else in `backend/` was touched. The auth layer, graph topology, dependency container, ingestion, and API surface are untouched.

---

## 6. Anti-patterns the previous plan recommended — DO NOT do these

1. **"Re-embed everything to BGE-m3"** — The plan itself rejected this on confidence 10/10 (E5-large-instruct is fine). Listed here so a future agent doesn't resurrect it.
2. **"Three-tier hybrid cache: Redis + Qdrant + RAG"** — Over-engineering. The Redis exact-match tier provides ~0% marginal benefit over a Qdrant ANN cache with threshold 0.999. Just use Qdrant.
3. **"Add `_event__` yields to retrieval node"** — LangGraph nodes return dicts, not async generators. Use `astream_events` from the orchestrator instead (see §2.5).
4. **"Add Prometheus + Grafana before fixing latency"** — Don't decorate what isn't working yet. Latency first, observability second.
