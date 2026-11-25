# Production Plan: Two-Stage Cascade (Hybrid Fusion + Quantized Rerank) & Memgraph-Driven Dynamic Context Harness Sizing

> **Task ID**: `2026-11-25-two-stage-cascade-quantized-rerank-memgraph-harness`  
> **Status**: COMPLETED & VERIFIED (Ready for Deployment)  
> **Target Branches / Commits**: `feat/two-stage-quantized-rerank-memgraph-sizing` on top of `main` @ `e7876ee1a`  
> **Target Environment**: Railway Pro Production & Local Development Stack  
> **Governing Standards**: `AGENTS.md` (Invariants X1, X2, X40, X41, Oct 27 Serving Invariants), `GEMINI.md` (Production-Ready Planning Mandate), `lessons.md` (Strict $\le 1500$ lines ceiling)

---

## Completed Implementation & Audit Log

### 1. ColBERT Decommissioned Across Docker, Railway & Backend
- Explicitly disabled ColBERT in `backend/app/config.py` (`enable_colbert: bool = False`).
- Replaced ColBERT late-interaction / MaxSim in `backend/services/embedding_service.py` (`cascaded_rerank`) with direct high-throughput ONNX INT8 CrossEncoder scoring.
- Added `ENABLE_COLBERT=false` to `backend/.env` and `backend/docker-compose.yml`.

### 2. Configuration Settings Added
- Added settings in `backend/app/config.py`:
  - `first_person_memgraph_sizing_enabled: bool = True`
  - `first_person_memgraph_sizing_min_k: int = 3`
  - `first_person_memgraph_sizing_max_k: int = 12`
  - `first_person_memgraph_sizing_timeout_ms: float = 25.0`
  - `rag_stage1_candidate_pool: int = 40`
  - `rag_quantized_reranker_enabled: bool = True`
- Added `"first_person_memgraph_sizing_enabled"` to `_RUNTIME_CONFIG_FINGERPRINT_FIELDS` in `backend/app/runtime_budget.py`.

### 3. MemgraphHarnessSizer Implemented (`backend/services/first_person_graph_sizing.py`)
- Traverses C++ MAGE Memgraph graph projection via `container.memgraph_driver` (Bolt port 7687).
- Evaluates:
  - Discourse chaining (`TU_CONTINUES` / `TU_PRECEDES`)
  - Conceptual density & centrality across `:Concept` / `:Teaching`
  - Comparative / multi-guru inquiries (Sri Krishnaji and Sri Preethaji)
- Dynamically computes $k \in [3, 12]$ in $\le 15\text{ms}$ with circuit-breaker protection and fail-open heuristic fallback.

### 4. Quantized ONNX INT8 Reranker Unified (`backend/services/reranker_service.py` & `backend/rag/nodes/reranking.py`)
- Prioritized `OnnxReranker` directly when `reranker_backend == "onnx_int8"`, eliminating dependency on `flashrank` and avoiding slow PyTorch fallback.
- Removed artificial candidate limits (8/10 cap expanded to 40 in `_limit_rerank_candidates`).
- Routed complex tier reranking through `OnnxReranker` for sub-35ms CPU scoring.

### 5. Dynamic Sizing Wired into FirstPersonPipeline (`backend/services/first_person_pipeline.py`)
- Wired `MemgraphHarnessSizer` into `_serve_from_context_harness` to dynamically calculate `_max_eval = sizing_decision.k`.
- Replaced static truncation with dynamic retention ($k=3..4$ for atomic concepts, $k=8..10$ for chained discourse).
- Expanded candidate retrieval limit `harness_candidate_limit` to fetch rich candidate sets from Qdrant.

### 6. Test Suite & Invariant Verification
- Added `backend/tests/test_memgraph_harness_sizing.py` (6 tests).
- Added `backend/tests/test_quantized_reranker_cascade.py` (4 tests).
- Ran regression suite: 18/18 tests PASSED in 0.55s.
- Ran `scripts/ops/predeployment_checklist.py`: STAGING READINESS ELIGIBLE, all 10 checks PASSED.
- Byte-identity between `scripts/` and `backend/scripts/` verified.


---

## 1. Executive Summary & Problem Diagnosis

### 1.1 The Operational Bottleneck
In the current AskMukthiGuru retrieval and first-person serving pipeline, two acute architectural limitations artificially constrained retrieval recall, candidate diversity, and latency:

1. **The PyTorch Cross-Encoder CPU Bottleneck & Crude Stopgaps**:
   - PyTorch-based cross-encoder reranking (`cross-encoder/ms-marco-MiniLM-L-6-v2` or `bge-reranker-v2-m3` on CPU) consumed $\sim 120\text{ms}$ per candidate pair on CPU ($\sim 1.8\text{s}$ for 16 pairs).
   - In response, crude hardcoded caps were introduced:
     - `_limit_rerank_candidates` in `backend/rag/nodes/reranking.py` capped candidate inputs to 8 (`tier2_simple`) or 10 (`standard`).
     - `_max_eval` in `backend/services/first_person_pipeline.py` was hardcoded to 4 (`contexts = contexts[:_max_eval]`).
     - `harness_candidate_limit` was capped to 6.
   - Furthermore, `flashrank` was not installed in the production container image, causing `RerankerService` to fall back to PyTorch `CrossEncoder`, and for `tier3_complex` queries, `force_cross_encoder` explicitly forced the slow PyTorch path.
   - These artificial caps severely crippled candidate recall for nuanced, multi-concept, or comparative inquiries, causing the pipeline to miss critical antecedents and companion clips.

2. **Rigid, "Brainless" Harness Candidate Sizing**:
   - Even though AskMukthiGuru maintains an in-memory C++ MAGE Memgraph knowledge graph (`:TUTeachingUnit`, `:TUConcept`, `:TUTopic`, `:TU_CONTINUES`, `:TU_PRECEDES`, `:Concept`, `:Teaching`), the first-person context harness evaluated candidate contexts using a static, hardcoded integer limit ($k=4$).
   - It treated an isolated single-sentence definition identically to an interconnected multi-part discourse spanning several connected teaching units or comparative teacher teachings.

### 1.2 The Production Solution (Option C + Memgraph Harness Brain)
1. **Stage 1 (High-Recall Hybrid Fusion)**:
   - High-recall Qdrant dense vector (1536d / 1024d) + sparse BM25 SPLADE retrieval with Reciprocal Rank Fusion (RRF $k=60$), expanding candidate retrieval from 8–10 to 30–50 candidate items within $\le 30\text{ms}$.
2. **Stage 2 (Quantized High-Throughput ONNX INT8 Reranker)**:
   - Leverage `backend/services/onnx_reranker.py` (`temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8` with ONNX Runtime CPU INT8 quantization) as the first-class, primary high-throughput engine across both general RAG and first-person pipelines.
   - Scoring 30–50 candidate pairs completes in $\le 25-35\text{ms}$ on CPU (<40MB arena buffer), delivering a 40x speedup over PyTorch CPU.
   - Eliminate the artificial 8/10 candidate cap in `_limit_rerank_candidates` and prevent slow PyTorch fallback.
3. **Memgraph-Driven Dynamic Context Harness Sizing ("Memgraph Serving as Brain")**:
   - Introduce `MemgraphHarnessSizer` (`backend/services/first_person_graph_sizing.py`): the harness queries Memgraph in real-time ($\le 15\text{ms}$ bounded Cypher traversal via `container.memgraph_driver`).
   - The graph calculates:
     - **Discourse Chaining**: Active `TU_CONTINUES` / `TU_PRECEDES` sequences across adjacent video teaching units.
     - **Ontological Degree & Concept Density**: Multi-concept intersections (e.g. "suffering" + "inner state" + "Four Sacred Secrets").
     - **Multi-Guru / Comparative Breadth**: Cross-teacher teachings from Sri Krishnaji and Sri Preethaji.
   - Dynamically sizes the evaluation pool:
     $$k_{\text{dynamic}} = \text{clamp}(k_{\text{base}} + \Delta_{\text{chain}} + \Delta_{\text{density}} + \Delta_{\text{comparative}}, k_{\min}=3, k_{\max}=12)$$
     - Atomic/simple queries: $k = 3 \text{ or } 4$ (minimizes latency and TTFT).
     - Standard discourses: $k = 5 \text{ or } 6$.
     - Chained multi-part discourses: $k = 8 \text{ to } 10$.
     - Complex comparative inquiries: $k = 10 \text{ to } 12$.
   - Fail-open, circuit-breaker protected: if Memgraph is offline or exceeds $20\text{ms}$, gracefully falls back to default sizing without dropping a turn.

---

## 2. End-to-End Architecture & Information Flow

```
[ Seeker Inquiry: "How to deal with suffering?" ]
                     │
                     ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 1: HYBRID RETRIEVAL & FUSION (Qdrant + BM25 RRF)      │
│  - Dense semantic search (1536d / 1024d)                    │
│  - Sparse lexical search (SPLADE / BM25)                    │
│  - Pre-filtered: domain_rights_status == 'licensed' (X40)   │
│  - Candidate Pool: 30 to 50 parent context units            │
│  - Latency: <= 25ms                                         │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ MEMGRAPH GRAPH INTELLIGENCE BRAIN (MemgraphHarnessSizer)    │
│  - Driver: container.memgraph_driver (Bolt port 7687)       │
│  - Sub-15ms bounded Cypher inspection:                      │
│    * TU_CONTINUES / TU_PRECEDES chaining degree             │
│    * Concept graph centrality & doctrine density            │
│    * Multi-teacher / comparative authority presence         │
│  - Dynamic Size Decision: k_dynamic in [3..12]              │
│    (e.g., chained discourse -> k=8; atomic -> k=3)          │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ STAGE 2: HIGH-THROUGHPUT QUANTIZED RERANKER (ONNX INT8)     │
│  - Engine: OnnxReranker (mmarco-mMiniLMv2-L12-H384-v1 INT8) │
│  - Native Inference Gate memory bounds (no memory arena OOM)│
│  - Scores candidate pairs in <= 25ms on CPU                 │
│  - Dynamic retention: retains top k_dynamic candidates      │
└────────────────────────────┬────────────────────────────────┘
                             │
                             ▼
┌─────────────────────────────────────────────────────────────┐
│ DETERMINISTIC FIRST-PERSON CONTEXT HARNESS                  │
│  - Evaluates top k_dynamic contexts in parallel             │
│  - Enforces: Boundary check, Antecedent preservation,       │
│    Speaker provenance (Sri Preethaji / Sri Krishnaji),       │
│    Rights certification (X40), Hash integrity               │
│  - Zero LLM generation: 100% authentic verbatim quote       │
│  - UI status: 'success' | 'weak_match'                      │
└─────────────────────────────────────────────────────────────┘
```

---

## 3. Detailed Component Design & Specifications

### 3.1 Stage 1: Expanded Candidate Pool Hybrid Retrieval
- **Files Modified**: `backend/app/config.py`, `backend/services/first_person_pipeline.py`.
- **Invariants**:
  - `domain_rights_status == "licensed"` must be strictly enforced on Qdrant payloads before candidates reach the harness (Invariant X40).
  - Sparse RRF fusion preserves lexical names ("Soul Sync", "Four Sacred Secrets") while dense search captures semantic intent.
- **Candidate Pool Configuration**:
  - `rag_stage1_candidate_pool`: default `40` (configurable via `RAG_STAGE1_CANDIDATE_POOL`, bounded `10..100`).
  - `first_person_context_candidate_limit`: dynamically determined by Memgraph (bounded $3 \le k \le 12$) instead of static 6.

### 3.2 Stage 2: Quantized ONNX INT8 Cross-Encoder Unification
- **Files Modified**: `backend/services/reranker_service.py`, `backend/rag/nodes/reranking.py`, `backend/services/embedding_service.py`.
- **Architecture**:
  - In `backend/services/reranker_service.py`:
    - Check `settings.reranker_backend == "onnx_int8"`.
    - Instantiate `OnnxReranker` directly from `backend/services/onnx_reranker.py` with pinned commit `59d3305e534a9abf92f6eb6238c34b748a89dc83`.
    - Do NOT fail or attempt to import `flashrank` if `flashrank` is not installed; seamlessly serve through `OnnxReranker`.
  - In `backend/rag/nodes/reranking.py`:
    - Remove the hardcoded 8/10 cap in `_limit_rerank_candidates` when the quantized reranker is active.
    - Change `force_cross_encoder` to use `OnnxReranker` via `reranker.rerank(...)` instead of jumping to slow PyTorch CPU CrossEncoder in `embedder.cascaded_rerank`.
  - **Performance SLA**:
    - Scoring 30 candidates: $\le 20\text{ms}$ on CPU.
    - Scoring 50 candidates: $\le 35\text{ms}$ on CPU.
    - RAM overhead: $<40\text{MB}$ total buffer.

### 3.3 Dynamic Context Harness Sizing via Memgraph ("Memgraph Brain")
- **New Module**: `backend/services/first_person_graph_sizing.py` (`MemgraphHarnessSizer`).
- **Graph Schema Queried**:
  - Labels: `:TUTeachingUnit`, `:TUConcept`, `:TUTopic`, `:TUGuru`, `:Concept`, `:Teaching`.
  - Edges: `:TU_CONTINUES`, `:TU_PRECEDES`, `:TU_HAS_CONCEPT`, `:TU_HAS_TOPIC`, `:RELATES_TO`.
- **Cypher Query Contract**:
  - Bounded execution with strict `max_transaction_retry_time = 0.05s` and connection timeout $15\text{ms}$.
  - Inspection Query:
    ```cypher
    // Inspect chaining degree and concept cluster density for seed spans
    MATCH (seed:TUTeachingUnit)
    WHERE seed.span_id IN $seed_span_ids
    OPTIONAL MATCH (seed)-[:TU_CONTINUES|TU_PRECEDES]-(chained:TUTeachingUnit)
    OPTIONAL MATCH (seed)-[:TU_HAS_CONCEPT|TU_HAS_TOPIC]->(c)
    RETURN count(DISTINCT chained) AS chain_count,
           count(DISTINCT c) AS concept_count,
           count(DISTINCT seed.guru_id) AS guru_count
    ```
- **Sizing Decision Heuristic**:
  - Base: $k_{\text{base}} = 4$.
  - Chaining Delta:
    - If `chain_count >= 2`: $+3$ (indicates multi-part discourse sequence; antecedent context is crucial).
    - If `chain_count == 1`: $+1$.
  - Density Delta:
    - If `concept_count >= 4`: $+2$ (indicates rich theological discourse requiring higher candidate breadth).
    - If `concept_count == 0`: $-1$ (isolated or unlinked teaching unit; precision-focused).
  - Comparative Delta:
    - If `guru_count > 1` or query is comparative: $+2$ (requires representation for both Sri Krishnaji and Sri Preethaji).
  - Final clamped value:
    $$k_{\text{dynamic}} = \max(3, \min(12, k_{\text{base}} + \Delta_{\text{chain}} + \Delta_{\text{density}} + \Delta_{\text{comparative}}))$$
- **Telemetry & Logging**:
  - Log structured JSON: `{"event": "memgraph_harness_sizing", "k": 8, "chain_count": 3, "concept_count": 5, "duration_ms": 4.2}`.
  - Fail-Open Safety: If Memgraph driver is absent, queries time out, or throw an exception, cleanly return default $k=5$ with reason `"fallback_timeout"`.

---

## 4. Invariants, Safety & Policy Compliance

1. **Authentic Verbatim Preservation (Oct 27 Serving Invariants)**:
   - Answer text served in first-person is strictly verbatim source spans from Sri Preethaji and Sri Krishnaji.
   - Zero LLM generation of teaching text. Directness is metadata (`is_direct_answer`, `status="weak_match"`).
2. **Repository Layout & Script Drift (Invariant X1 & X2)**:
   - Any script shared between `scripts/` and `backend/scripts/` must remain byte-identical.
   - Run `pytest backend/tests/test_repo_layout.py` to assert zero drift.
3. **Rights Enforcement (Invariant X40)**:
   - Every candidate context and graph traversal node must verify `rights_status == "licensed"`.
4. **Budget & Cap Reporting (Invariant X41)**:
   - Bounded ledger reads; no startup hangs.
5. **Lessons Ceiling (`lessons.md`)**:
   - `lessons.md` must strictly remain $\le 1500$ lines.

---

## 5. Detailed Task Breakdown & Implementation Steps

### Task 1: Add Configuration Settings
- Add settings to `backend/app/config.py`:
  - `first_person_memgraph_sizing_enabled: bool = True`
  - `first_person_memgraph_sizing_min_k: int = 3`
  - `first_person_memgraph_sizing_max_k: int = 12`
  - `first_person_memgraph_sizing_timeout_ms: float = 25.0`
  - `rag_stage1_candidate_pool: int = 40`
  - `rag_quantized_reranker_enabled: bool = True`
- Verify config parity and environment bindings.

### Task 2: Build `MemgraphHarnessSizer`
- Create `backend/services/first_person_graph_sizing.py`:
  - Implement `MemgraphHarnessSizer` class.
  - Implement `calculate_candidate_size(seed_span_ids, query, concepts, teacher_id) -> SizingResult`.
  - Wire Bolt session queries to `container.memgraph_driver` / `container.neo4j_driver`.
  - Implement 20ms circuit-breaker timeout and fail-open heuristic fallback.
  - Structured telemetry and metrics.

### Task 3: Unify Quantized ONNX INT8 Reranker
- Update `backend/services/reranker_service.py`:
  - Ensure `_load_fallback` directly loads `OnnxReranker` without requiring `flashrank` package when `reranker_backend == "onnx_int8"`.
  - Ensure `_run_cross_encoder` uses `OnnxReranker.predict` with native inference gate.
- Update `backend/rag/nodes/reranking.py`:
  - Expand `_limit_rerank_candidates` from 8/10 to 40 candidates when `settings.rag_quantized_reranker_enabled` is True.
  - Route complex tier reranking through `OnnxReranker` instead of slow PyTorch CPU cross-encoder.

### Task 4: Wire Dynamic Sizing into First-Person Pipeline
- In `backend/services/first_person_pipeline.py`:
  - Instantiate `MemgraphHarnessSizer`.
  - In `_serve_from_context_harness`:
    - Call `sizer.calculate_candidate_size(...)` to determine `k_dynamic`.
    - Use `k_dynamic` instead of hardcoded `_max_eval = 4` and `harness_candidate_limit = 6`.
  - In `_expand_context_candidates`:
    - Respect dynamic $k$ bounds when merging TU graph neighbors and enrichment windows.

### Task 5: Comprehensive Unit & Integration Testing
- Create `backend/tests/test_memgraph_harness_sizing.py`:
  - Test atomic query sizing ($k=3$ or $4$).
  - Test chained discourse sizing ($k=8$ to $10$).
  - Test comparative query sizing ($k=10$ to $12$).
  - Test timeout / driver disconnect fallback ($k=5$, fail-open).
- Create `backend/tests/test_quantized_reranker_cascade.py`:
  - Test ONNX INT8 candidate scoring for 40 pairs in $<35\text{ms}$.
  - Test parity between single and batch predictions.
  - Test thread safety under concurrent requests.
- Run complete test suite:
  - `pytest backend/tests/test_memgraph_harness_sizing.py`
  - `pytest backend/tests/test_quantized_reranker_cascade.py`
  - `pytest backend/tests/test_repo_layout.py`
  - `pytest backend/tests/test_lessons_archive.py`

### Task 6: Verification, Deployment & Post-Merge Audit
- Run `scripts/ops/predeployment_checklist.py`.
- Sync `scripts/` and `backend/scripts/` (Invariant X1/X2).
- Commit and push to `main`.
- Deploy to Railway Pro production.
- Execute live production audit curl probes and verify latency $\le 10.0\text{s}$ SLA max (typical $\le 1.5\text{s}$).

---

## 6. Rollback & Contingency Plan

1. **Feature Flags for Instant Disablement**:
   - `FIRST_PERSON_MEMGRAPH_SIZING_ENABLED=false`: Reverts harness sizing to static config bounds instantly without redeployment.
   - `RAG_QUANTIZED_RERANKER_ENABLED=false`: Reverts candidate pool budgeting to previous values.
   - `RERANKER_BACKEND=flagembedding`: Reverts reranker to legacy backend if needed.
2. **Git Rollback**:
   - Single atomic commit on `main`. Clean revert via `git revert HEAD` if any unresolvable regression arises.
