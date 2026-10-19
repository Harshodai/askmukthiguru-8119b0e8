<!-- Archived verbatim from root CLAUDE.md on 2026-10-19 to cut per-session context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on any number. -->

# Archived from CLAUDE.md: rag-graph-pipeline

## Architecture: The Multi-Node Anti-Hallucination Pipeline

The chat endpoint (`POST /api/chat`) runs every message through a LangGraph State Machine with ~20 specialized nodes. The original "12-layer" conceptual model has been expanded with additional quality gates and retrieval enhancements.

### Graph Strategy Architecture

`rag/graph.py` is a **thin facade** around `rag/graph_strategies.py`. The actual wiring lives in strategy classes so that new variants can be added without touching the facade:

| Strategy | Class | Purpose |
|----------|-------|---------|
| **Fast** | `FastGraphStrategy` | 5-node pipeline for simple factual queries (~25s) |
| **Standard** | `StandardGraphStrategy` | Full anti-hallucination chain (~133s) |
| **Deep** | `DeepGraphStrategy` | Extended chain for complex multi-part questions |

**Plug-and-play entry routing (2026-10-03).** All strategies share a
registry-driven START router: `backend/rag/pipeline_registry.py` picks the
first enabled+claiming `PipelineModule` per request (`first_person`, then
terminal `general`) and otherwise falls back to `parallel_start`'s Send
fan-out. Topology stays static and compiled once — only routing is dynamic
(LangGraph guidance; never build a subgraph per request). Adding or removing a
serving pipeline = one tuple entry + node/edge wiring; the kill-switch lives in
the module's live `enabled()` predicate, so a flag flip needs no recompile.
Recipe: `docs/DEVELOPER_GUIDE.md` §6; proofs: `backend/tests/test_pipeline_registry.py`.

### Node Architecture (under `rag/nodes/`)

The graph nodes have been modularized into `rag/nodes/`:

| Module | Key Nodes | Purpose |
|--------|-----------|---------|
| `intent.py` | Intent routing, on-device intent classification | Route to distress, meditation, casual, or full pipeline |
| `retrieval.py` | Hybrid retrieval (RAPTOR + leaf + LightRAG + Parent-Child + MMR) | Two-phase hybrid retrieval with keyword injection |
| `reranking.py` | Cascaded ColBERT + CrossEncoder re-ranking | Re-ranking of retrieved documents |
| `generation.py` | Context-only generation, inline hint extraction | Stimulus RAG + generation |
| `verification.py` | Reflect on answer, verify | Self-Reflection RAG, Chain of Verification |
| `keyword_injection.py` | Doctrinal synonym expansion | Improves retrieval coverage for spiritual terms |
| `short_circuit.py` | Fast-path short circuiting | Skips heavy nodes for simple queries |
| `on_device_intent.py` | Local intent classification | On-device intent classification (no LLM call) |
| `utils.py` | Shared node utilities | Context engineering, formatting, fallback handling |

### Pipeline Flow (Standard Path)

**Entry:** `intent_router`
- Routes to `handle_distress` / `handle_meditation` / `handle_casual` / `resolve_followup` (standard/deep) or `retrieve_documents` (fast)

**Fast Path (`FastGraphStrategy`):**
- Skips `resolve_followup`, `navigate_and_hyde` (which since R22 also carries `decompose_query`), `grade_documents`, `context_engineer`, `agentic_graph_traversal`, `cross_teacher_reasoning`
- **Corrected 2026-09-22: `rerank_documents` is no longer skipped.** The fast/tier2_simple candidate set is small (~5-7 docs, see `rag/nodes/retrieval.py` `chunk_limit`) and `rerank_documents` self-protects latency via its own high-confidence bypass (`rerank_bypass_high_confidence_enabled`), so simple queries were reaching generation unranked for no latency benefit. `_map_docs_to_relevant` now reads `reranked_docs` (falling back to raw `documents` on an empty rerank), capped at 5 either way — reranking can reorder the candidate set but never widen how many docs reach `generate_answer`.
- **Corrected 2026-09-05 (production-audit finding F3):** `reflect_on_answer`/`verify_answer`/`extract_citations` are NOT skipped on this path — `rag/graph_strategies.py`'s `FastGraphStrategy.build` wires `generate_answer → reflect_on_answer → verify_answer → extract_citations` unconditionally, and `verify_answer`'s own tier-based bypass (see `verify_answer` below) does not special-case fast/tier2_simple either. This doc previously claimed otherwise.
- Runs: `intent_router` → `resolve_parallel` → `retrieve_documents` → `rerank_documents` → `_map_docs_to_relevant` → `generate_answer` → `reflect_on_answer` → `verify_answer` → `extract_citations` → `format_final_answer` (plus `web_search` for temporal queries and the `handle_casual` / `handle_distress` / `handle_meditation` / `handle_fallback` branches)
- Brings latency from ~133s down to ~25s for simple doctrine queries

**QUERY path (full anti-hallucination chain - `StandardGraphStrategy`/`DeepGraphStrategy`):**
- `resolve_followup` — resolves pronouns/references from conversation history
- `navigate_and_hyde` — **merged parallel triple since 2026-09-12 (R22)**: runs `decompose_query` (atomic sub-query split), `navigate_knowledge_tree` (cluster selection; PageIndex-inspired) and `generate_hyde` concurrently in one `asyncio.gather` (`rag/nodes/retrieval.py`). **`decompose_query` is NOT a separate graph node** — it was one until R22, wired as a serial `decompose_query -> navigate_and_hyde` edge that paid for two independent LLM round trips back-to-back even though neither reads the other's output. Measured p95 165.4s → 113.0s on comparative queries. Do NOT re-split it into its own node, and do NOT convert this into a LangGraph fan-out/join — an earlier fan-out attempt caused an OR-join race, which is why the merge-into-one-node pattern is used. Guarded by `backend/tests/test_graph_strategy_wiring.py` and `benchmarks/validate_graph.py`. HyDE follows `RAG_USE_HYDE`; non-English/Indic requests require the explicit `RAG_INDIC_USE_HYDE=true` override because the extra provider round trip produced a measured latency tail without held-out quality proof
- `retrieve_documents` — two-phase hybrid retrieval (RAPTOR summaries + leaf chunks + LightRAG graph + Parent-Child resolution + MMR diversity re-ranking). Expands queries with doctrinal synonyms and injects doctrine keywords
- `agentic_graph_traversal` — ReAct loop for walking the ontology graph during COMPARATIVE intent or complex queries
- `rerank_documents` — Cascaded ColBERT + CrossEncoder re-ranking
- `grade_documents` — CRAG batch relevance grading (single LLM call for all docs); context-sufficiency scoring is inline here (replaces the former separate `check_context_sufficiency` node)
- Conditional branch: relevant → `enrich_context` | rewrite → `rewrite_query` (global cap `RAG_MAX_REWRITES`; Indic cap `RAG_INDIC_MAX_REWRITES`, default 1) | fallback → `handle_fallback`
- `enrich_context` — fetches neighbor chunks for broader context
- `context_engineer` — assembles structured prompt layers (persona, knowledge, user state, instructions)
- `generate_answer` — inline hint extraction + context-only generation (merged Stimulus RAG + generation)
- `reflect_on_answer` — Self-Reflection RAG: **LettuceDetect only** (embedding/lexical faithfulness). LLM self-consistency check is **disabled** to save ~45s without quality loss on spiritual paraphrasing
- Conditional branch: valid → `verify_answer` | needs_correction → `rewrite_query` (same global/Indic caps) | exhausted → `handle_fallback`
- `verify_answer` — LettuceDetect faithfulness (threshold **0.6** = `faithfulness_floor`; the doctrine-vocabulary boost was **removed 2026-08-10**, audit S3). **CoVe is tier-gated ON, not disabled** (corrected 2026-08-10): it fires for tier3_complex/tier4_deep and compulsorily for any tier scoring below 0.6 (`rag_cove_disabled=False`; `rag/nodes/verification.py`), and a combined-verification gateway runs ahead of it for the two deepest tiers. Only alternative-answer self-consistency stays disabled. **Corrected 2026-09-05 (finding F3): fast/tier2_simple do NOT bypass this node** — `StandardGraphStrategy`'s `_route_after_reflection` routes every state to `verify_answer` unless `needs_correction` is set, with no tier check, and `FastGraphStrategy` wires the same node unconditionally too (see Fast Path above)
- `cross_teacher_reasoning` — when the query names multiple spiritual teachers, queries Neo4j for cross-teacher comparisons (runs after grading)
- `extract_citations` — maps answer sentences to best-matching retrieved documents (post-verification, before formatting)
- `web_search` — real-time web results for temporal queries (feeds back through `resolve_followup` in the standard path)
- `format_final_answer` — confidence-based graduated responses, citation formatting, caveats

**Post-Graph (pipeline stages after `GraphStage`)**
- **Zero-Shot Output Rail** (`OutputGuardrailStage`) — moderates/blocks harmful output
- **Telemetry Logging** — query trace + response trace saved to telemetry DB

The `GraphState` TypedDict in `rag/states.py` is the data contract flowing through all nodes. It includes `request_id` for end-to-end log correlation.

### Pre-Graph (pipeline stages before `GraphStage`)
1. **Zero-Shot Input Rail** (`guardrails/` via `InputGuardrailStage`) — blocks harmful/off-topic input
2. **Serene Mind Distress Detector** (`services/serene_mind_engine.py` via `on_device_intent.py`) — assesses emotional state; does NOT bypass RAG — distress queries run through the full pipeline to retrieve compassionate teachings
