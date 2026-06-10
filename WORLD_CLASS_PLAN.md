# World-Class Product Plan: Mukthi Guru

> Based on ARCHITECTURE_AUDIT_CORRECTED.md. Goal: Fix critical architectural bottlenecks to hit <3s response, <1% hallucination, and world-class benchmarks.

---

## ⚠️ Spiritual Accuracy Guarantees (Non-Negotiable)

This is a **spiritual guidance system** grounded in the teachings of Sri Preethaji & Sri Krishnaji. Any architectural change must preserve or strengthen the following accuracy guarantees:

1. **Zero-Hallucination Pipeline**: CRAG, Self-RAG, LettuceDetect verification, and contradiction checks must never be weakened by optimization. All refactors must maintain the full anti-hallucination chain.
2. **Guardrails Preserve Spiritual Context**: Input/output guardrails must distinguish between harmful content and valid spiritual distress (e.g., "I feel lost"). The Serene Mind pipeline must remain intact.
3. **No Caching of Unverified Answers**: Exact and semantic caches must only store answers that have passed verification. A cached response without a source citation must be rejected.
4. **Doctrinal Keyword Boost**: The `get_expected_keywords` and `inject_doctrine_keywords` functions must remain active to ensure retrieval covers spiritual terminology.
5. **Verification Thresholds**: The 0.25 LettuceDetect threshold and 0.22 CoVe threshold must not be relaxed. Domain boost for doctrine terms must remain.

**All Phases below are subject to the principle:** *Accuracy before speed. A slower accurate answer is better than a fast wrong answer.*

---

## Phase 1: Foundation (Week 1) — ROI: Massive

### 1.1 Extract `PipelineCoordinator` from Dual Orchestrators

**Problem:** `ChatRequestOrchestrator.orchestrate()` (588 lines) and `ChatStreamRequestOrchestrator.generate_sse()` (630 lines) duplicate ~60% of pipeline logic.

**Solution:** Create a `PipelineCoordinator` that both delegate to. The coordinator returns a `PipelineResult`, and the orchestrators only handle transport (HTTP/HTTPException vs. StreamingResponse/SSE).

**Files to create:**
- `backend/app/pipeline/pipeline_coordinator.py` — Core pipeline logic
- `backend/app/pipeline/stages.py` — Individual stage definitions
- `backend/app/pipeline/result.py` — Unified `PipelineResult` dataclass

**Interface:**
```python
@dataclass(frozen=True)
class PipelineResult:
    final_answer: str
    intent: str
    med_step: int
    citations: list
    latency_ms: int
    query_tier: str
    trace_id: str

class PipelineCoordinator:
    def __init__(self, container: ServiceContainer) -> None: ...

    async def execute(
        self,
        user_msg: str,
        preferred_lang: str,
        chat_history: list[dict],
        meditation_step: int,
        session_id: str | None,
        user: dict,
    ) -> PipelineResult: ...
```

**Steps:**
1. Extract cache check, guardrails, distress detection, graph invocation, translation, and telemetry into `PipelineCoordinator.execute()`
2. Make `ChatRequestOrchestrator` and `ChatStreamRequestOrchestrator` thin wrappers around `PipelineCoordinator`
3. Delete duplicated logic from both orchestrators
4. Refactor to use `Result[T, Error]` for error handling (see 1.4)
5. **Estimated effort:** 1 day

---

### 1.2 Add Per-Stage Tracing + Telemetry

**Problem:** Telemetry is interleaved with business logic (~110 lines in orchestrator, ~120 in stream orc). No per-stage timing is captured.

**Solution:** Extract a `TelemetryPublisher` that subscribes to pipeline events. Each stage emits an event; the publisher logs asynchronously.

**Files to create:**
- `backend/app/telemetry/telemetry_publisher.py` — Event subscriber
- `backend/app/telemetry/events.py` — `PipelineEvent`, `StageCompleted`, `StageFailed`
- `backend/app/telemetry/sinks.py` — Jaeger, Supabase, stdout sinks

**Event Schema:**
```python
@dataclass(frozen=True)
class StageCompleted:
    stage_name: str
    input_hash: str
    output_hash: str
    latency_ms: int
    status: Literal["success", "cached", "error"]
    error_type: str | None = None
```

**Steps:**
1. Define `EventType` enum (STAGE_START, STAGE_END, STAGE_ERROR, CACHE_HIT, GUARDRAIL_TRIGGERED)
2. Wrap each pipeline stage in a decorator that auto-emits telemetry
3. Make `TelemetryPublisher` a singleton that subscribes to events
4. Replace inline telemetry logic in both orchestrators with event emission
5. **Estimated effort:** 2 days

---

### 1.3 Refactor `SarvamCloudService` into Gateway + Domain

**Problem:** 1,624 lines in a single class. HTTP logic, circuit breaker, rate limiting, and ALL prompt assembly are tightly coupled.

**Solution:** Extract:
- `SarvamHTTPGateway` — handles HTTP, auth, circuit breaker, retries
- `LLMGateway` — pure domain: prompt assembly, model selection
- `ClassificationGateway` — intent/complexity/distress classification
- `TranslationGateway` — translation prompts

**Files to create:**
- `backend/services/gateways/sarvam_http.py` — SarvamHTTPGateway
- `backend/services/gateways/llm.py` — LLMGateway
- `backend/services/gateways/classification.py` — ClassificationGateway
- `backend/services/gateways/translation.py` — TranslationGateway

**Interface:**
```python
class LLMGateway:
    def __init__(self, http_gateway: SarvamHTTPGateway) -> None: ...

    async def decompose(self, question: str) -> list[str]: ...
    async def grade_relevance(self, question: str, doc_texts: list[str]) -> list[dict]: ...
    async def generate_hyde(self, question: str) -> str: ...
    async def generate_answer(self, context: str, question: str) -> str: ...
```

**Steps:**
1. Extract all HTTP logic (headers, retries, circuit breaker) into `SarvamHTTPGateway`
2. Extract prompt assembly methods into `LLMGateway` (delegates HTTP to `SarvamHTTPGateway`)
3. Extract classification methods into `ClassificationGateway`
4. Update `ServiceContainer` to wire new gateways
5. **Estimated effort:** 2 days

---

### 1.4 Unify Error Handling with Result Pattern

**Problem:** Three distinct error handling patterns (HTTPException, swallowed warning, fallback response).

**Solution:** Define a `Result[T, Error]` monad and a failure taxonomy.

**Files to create:**
- `backend/app/core/result.py` — `Result`, `Success`, `Failure`
- `backend/app/core/errors.py` — `TransientError`, `PermanentError`, `DegradedError`

**Failure Taxonomy:**
```
Transient → Retry with exponential backoff (e.g., network timeout, rate limit)
Permanent → Fail immediately (e.g., invalid API key, no model loaded)
Degraded → Return partial/fallback response (e.g., cache unavailable, guardrails down)
```

**Usage:**
```python
from app.core.result import Result, Success, Failure

async def check_guardrails(self, text: str) -> Result[dict, GuardrailError]:
    try:
        result = await self.guardrails.check_input(text)
        return Success(result)
    except GuardrailUnavailable:
        return Failure(DegradedError("Guardrails unavailable, proceeding unmoderated"))
```

**Steps:**
1. Define `Result[T, Error]`, `Success`, `Failure` dataclasses
2. Define `TransientError`, `PermanentError`, `DegradedError`
3. Convert orchestrator error handling to use `Result`
4. Add `match`/`fold` helpers for ergonomic error handling
5. **Estimated effort:** 1 day

---

## Phase 2: Optimization (Week 2) — ROI: High

### 2.1 Parallelize Independent Graph Nodes

**Problem:** Many independent LLM calls run sequentially. `navigate_knowledge_tree` and `generate_hyde` are already wired in parallel (verified in `graph_strategies.py`), but other nodes like `decompose_query` followed by `navigate_knowledge_tree` are sequential.

**Solution:** Use LangGraph `Send` API for more parallel branches. Specifically:
- `intent_router` → `decompose_query` + `generate_hyde` can run in parallel
- `enrich_context` + `explain_retrieval` can run in parallel after `context_engineer`
- `reflect_on_answer` + `verify_answer` can be parallelized in the deep graph

**Changes to:**
- `backend/rag/graph_strategies.py` — Add parallel branches
- `backend/rag/states.py` — Ensure state keys don't conflict

**Example:**
```python
# After intent_router, decompose_query and generate_hyde can be parallel
graph.add_node("decompose_query", decompose_query)
graph.add_node("generate_hyde", generate_hyde)
graph.add_edge("intent_router", "decompose_query")
graph.add_edge("intent_router", "generate_hyde")
graph.add_edge("decompose_query", "navigate_knowledge_tree")
graph.add_edge("generate_hyde", "retrieve_documents")
```

**Steps:**
1. Identify all independent node pairs in the graph
2. Add parallel branches in `graph_strategies.py`
3. Ensure `GraphState` has non-overlapping keys for parallel outputs
4. Benchmark before/after
5. **Estimated effort:** 2 days

---

### 2.2 Add Node-Level Benchmarks

**Problem:** `scripts/benchmarks/askmukthiguru_ruthless_benchmark.py` is 2,894 lines and only measures end-to-end latency.

**Solution:** Create `scripts/benchmarks/per_node_benchmark.py` that mocks dependencies and measures each node in isolation.

**Files to create:**
- `scripts/benchmarks/per_node_benchmark.py` — Benchmark runner
- `scripts/benchmarks/fixtures.py` — Mock state fixtures

**Benchmark Target:**
```python
async def benchmark_retrieve_documents():
    state = create_mock_graph_state()
    start = time.monotonic()
    result = await retrieve_documents(state)
    latency = time.monotonic() - start
    return {"node": "retrieve_documents", "latency_ms": latency * 1000}
```

**Steps:**
1. Create mock `GraphState` fixtures for each node
2. Wire mock services (no real Qdrant/Sarvam calls)
3. Run each node 10× and record p50/p95/p99
4. Output JSON + markdown report
5. **Estimated effort:** 1 day

---

### 2.3 Extract Translation as a Stage

**Problem:** Translation logic is duplicated in both orchestrators and scattered across the graph. The graph returns English; the orchestrator translates. This means bilingual users get slower responses.

**Solution:** Move translation into the graph as an optional final stage. The graph already knows `detected_language`. Add a `translate_final_answer` node that is a no-op for English.

**Changes to:**
- `backend/rag/graph_strategies.py` — Add `translate_answer` node before `format_final_answer`
- `backend/rag/states.py` — Add `detected_language` to state
- `backend/app/orchestrator.py` — Remove post-graph translation

**Steps:**
1. Add `translate_answer` node that checks `state["detected_language"]`
2. Gate behind `settings.translation_enabled`
3. Remove translation from orchestrator
4. Verify no latency regression for English queries
5. **Estimated effort:** 1 day

---

### 2.4 Fix OpenRouter Fast Path

**Problem:** `backend/app/orchestrator.py:314-331` has a hardcoded bypass that skips the entire LangGraph for simple queries when `use_openrouter_for_simple` is enabled. No guardrails, no distress detection, no citations.

**Solution:** Remove the bypass entirely. The fast graph already handles simple queries in ~25s (vs. ~133s for standard). The bypass is a premature optimization that breaks the pipeline contract.

**Steps:**
1. Delete the `if graph_variant == "fast" and ...` block
2. Verify fast graph is selected correctly for simple queries
3. **Estimated effort:** 0.5 day

---

## Phase 3: Frontend Decoupling (Week 3)

### 3.1 Introduce ChatStateMachine

**Problem:** `ChatInterface.tsx` (1,531 lines) directly handles streaming, state management, and backend schema.

**Solution:** Create a `ChatStateMachine` that abstracts the backend protocol. The component just renders state.

**Files to create:**
- `src/lib/chatStateMachine.ts` — State machine
- `src/lib/chatStateMachine.types.ts` — Types

**States:**
```
idle → loading → streaming → done
         ↓
    error (retryable / fatal)
```

**Steps:**
1. Define `ChatState` with all possible states
2. Move streaming logic into state machine
3. Make `ChatInterface.tsx` a pure render-component
4. Add tests for state transitions
5. **Estimated effort:** 2-3 days

---

## Phase 4: Cleanup & Verification (Week 3-4)

### 4.1 Use or Delete Contracts

**Problem:** `backend/app/contracts/*.py` (340 lines total) defines 50 isolated nodes that are never formally connected to implementations.

**Decision:** Option 3 — make the DI container inject against abstractions.

**Changes to:**
- `backend/app/dependencies.py` — Import protocols types, assert concrete classes match
- `backend/services/` — Add `typing.Protocol` checks (or Zol.ONes for runtime)

**Steps:**
1. Add runtime assertion: `assert isinstance(qdrant, VectorStore)`
2. Or delete contracts and rely on duck typing
3. **Estimated effort:** 0.5 day

---

### 4.2 Contract Tests for `PipelineCoordinator`

**Problem:** `orchestrate` is in `untested_hotspots`.

**Solution:** After extracting `PipelineCoordinator`, write contract tests.

**Files to create:**
- `backend/tests/test_pipeline_coordinator.py`

**Test Cases:**
1. Cache hit returns immediately
2. Guardrail block returns blocked response
3. Distress detection triggers Serene Mind
4. Graph timeout returns fallback
5. Circuit open returns 503 (benchmark) or fallback (user)

**Steps:**
1. Mock all dependencies
2. Test each stage in isolation
3. Verify telemetry events are emitted
4. **Estimated effort:** 1 day

---

## Tracking: What We Missed (From Corrected Audit)

| # | Issue | Severity | Fix in Phase |
|---|---|---|---|
| 11 | OpenRouter fast path bypass | HIGH | 2.4 |
| 12 | `select_graph_for_query` uses heuristic, not LLM | MEDIUM | 1.1 (make it pluggable) |
| 13 | No per-node timeout in LangGraph | MEDIUM | 2.1 (add timeout in each node) |
| 14 | Memory layer has 200ms hard budget | LOW | Phase 4 (make configurable) |

---

## Go/No-Go Criteria for Each Phase

**Phase 1 is mandatory.** If Phase 1 is not complete, the system is unmaintainable and cannot be optimized.

| Phase | Must Have Before Proceeding |
|---|---|
| 1 → 2 | PipelineCoordinator extracted, tests pass, no regression in end-to-end latency |
| 2 → 3 | Per-node benchmarks show <20% stddev across 3 runs |
| 3 → 4 | ChatStateMachine has 100% state coverage in tests |
| 4 → done | All tests pass, benchmarks show improvement, no new errors in production logs |

---

## Expected Impact

| Metric | Before | After Phase 1 | After Phase 2 |
|---|---|---|---|
| End-to-end latency | 60-180s | 60-180s | 40-120s |
| Orchestrator lines | 588 | ~150 | ~150 |
| Stream orchestrator lines | 630 | ~100 | ~100 |
| Test coverage (orchestrator) | 0% | 80%+ | 80%+ |
| Response time (fast path) | ~25s | ~25s | ~20s |
| Hallucination rate | <1% | <1% | <0.5% |
| Lines in SarvamCloudService | 1,624 | 1,624 | ~600 (gateway) + ~800 (domain) |
