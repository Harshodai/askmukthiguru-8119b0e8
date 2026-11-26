# RAG Runtime DAG — reconstructed from source

**Reconstructed:** 2026-11-26 · **Evidence:** static source inspection of `main`; hosted runtime and current production env were not inspected.

This replaces the "12-layer pipeline" narrative in `CLAUDE.md`, which does not
match the code. Where they disagree, the code wins. Nothing here was observed
against a running system — see *What this does not tell you*.

## Entry

`POST /api/chat` -> `app/api/chat.py:423` (streaming variant `:687`) — **not**
`app/main.py`, as previously documented.

Per request: sanitize -> `resolve_anon_identity` -> cost-budget check ->
`authorize_chat_assistant` -> `_enforce_anon_quota` -> `populate_server_side_history`
-> queue (202) or inline orchestrator.

`app/orchestrator.py:82` (sync) and `app/stream_orchestrator.py:113` (SSE) are
thin facades over `PipelineCoordinator.execute()`
(`app/pipeline/pipeline_coordinator.py:191`), wrapped in
`asyncio.wait_for(timeout=pipeline_timeout + 5)`.

## Stage chain — actual order

The source of truth is `backend/app/pipeline/stages/pipeline_builder.py`.
First-person routing is dispatched inside `GraphStage`; it is not a separate
stage in this ordered list.

| # | Stage | Implementation | Runs when | LLM calls |
|---:|---|---|---|---|
| 1 | KillSwitch | `kill_switch_stage.py` | always, before cache | 0 |
| 2 | CacheCheck | `cache_stage.py` | eligible non-incognito cache lookup | 0-1 |
| 3 | RequestState | `glue_stages.py` | always | 0 |
| 4 | InputGuardrail | `guardrail_stage.py` | always | provider-dependent |
| 5 | Distress | `distress_stage.py` | always; graduated assessment | 0-1 |
| 6 | CircuitBreaker | `guardrail_stage.py` | always; short-circuits when open | 0 |
| 7 | DoctrineCache | `doctrine_cache_stage.py` | feature/configuration dependent | 0 |
| 8 | CasualShortCircuit | `glue_stages.py` | exact greeting route | 0 |
| 9 | OffTopic | `off_topic_stage.py` | sets routing metadata; does not independently serve a refusal | 0-1 |
| 10 | BoundedComparisonShortCircuit | `glue_stages.py` | bounded comparison carve-out | 0 |
| 11 | Personalize | `personalize_stage.py` | validated personalization route | 0 |
| 12 | Graph | `graph_stage.py` | general graph; dispatches first-person route when enabled | 1+ |
| 13 | MeditationGen | `meditation_gen_stage.py` | proactive trigger and citation requirements | 1 |
| 14 | Translation | `glue_stages.py` | Indic request/English answer | 0 |
| 15 | ToneAdapter | `tone_adapter_stage.py` | current implementation is a no-op | 0 |
| 16 | OutputGuardrail | `guardrail_stage.py` | always | provider-dependent |
| 17 | Memory | `memory_stage.py` | not incognito and persistable user | 0; post-response work is async |
| 18 | CacheUpdate | `cache_stage.py` | not incognito/blocked/unfaithful | 0 |
| 19 | ResultAssembly | `glue_stages.py` | always; terminal | 0 |

## Strategy selection

`graph_stage.py:248-270` reuses `ctx.detected_query_tier` computed back in
CacheCheck (`cache_stage.py:271`); otherwise `select_graph_for_query`
(`orchestrator_utils.py:171`) applies deterministic heuristics (deep regex ->
token count -> doctrine keywords), then the semantic router, then an LLM
classify call. DISTRESS is forced off the fast lane (`:297`).

## Graph strategies

`rag/graph.py` is a facade; wiring lives in `rag/graph_strategies.py`.

**Fast** (`:377-467`) — confirms the prior correction: **verification is
unconditional on the fast path.**
```
START -> {intent_router, handle_distress_check} -> resolve_parallel
      -> route_after_intent_fast (:61)
      -> retrieve_documents -> _map_docs_to_relevant -> generate_answer
      -> reflect_on_answer -> verify_answer -> extract_citations
      -> format_final_answer -> route_after_formatting (:165)
```

**Standard** (`:212-361`) — **updated 2026-09-12 by R22**, see below
```
resolve_followup -> navigate_and_hyde -> retrieve_documents
  -> _route_after_retrieve (:297)  [COMPARATIVE + agentic enabled -> agentic]
  -> rerank_documents -> grade_documents -> cross_teacher_reasoning
  -> route_after_grading (intent.py:1687)
       {enrich_context | handle_distress | rewrite_query | handle_fallback}
  -> context_engineer -> generate_answer -> reflect_on_answer
  -> _route_after_reflection (:136) -> verify_answer -> extract_citations
  -> format_final_answer
```

**Deep** (`:594-631`) — standard plus `deep_contradiction_gate`, with
`_route_after_verify (:600)` and `_route_deep_gate (:603)`.

Note: `verify_answer` the *node name* is bound to `combined_grade_and_verify`
(`:256`, `:414`), not to the `verify_answer` function; the imported
`verify_answer` symbol at `:52` is unused directly.

## Serialization — independent work awaited in sequence

These are the latency findings. Each is `PROVEN FROM CODE`; none has a measured
cost, because the stack was not running.

1. ~~**`decompose_query -> navigate_and_hyde`** (`graph_strategies.py:292`) — two
   independent LLM calls on a serial edge. `generate_hyde` and
   `navigate_knowledge_tree` both read `question`/`rewritten_query`; **neither
   reads `sub_queries`**, so the dependency the edge implies does not exist.~~
   **FIXED 2026-09-12 (R22).** `decompose_query` is no longer a graph node —
   it runs inside `navigate_and_hyde`'s `asyncio.gather` alongside
   `navigate_knowledge_tree` and `generate_hyde` (`rag/nodes/retrieval.py`),
   and the wiring is now a single `resolve_followup -> navigate_and_hyde ->
   retrieve_documents` edge. A true LangGraph 3-way fan-out/join was NOT used:
   an earlier attempt caused an OR-join race (per the comment R22 replaced), so
   the merge-into-one-node pattern already proven for nav_tree+hyde was reused.
   Measured live: p95 165.4s -> 113.0s on comparative queries. Guarded by
   `tests/test_graph_strategy_wiring.py` (asserts `"decompose_query" not in
   nodes`) and `benchmarks/validate_graph.py`'s static wiring check.
2. **`prepare_user_memory`** (`orchestrator_utils.py:837-877`) — five
   independent I/O awaits in sequence, including `update_profile` (`:857`), a
   **write on the critical path whose result nothing later reads**.
3. **`decompose_query` sub-query expansion** (`retrieval.py:704`) — N
   independent doctrine-service round trips inside a list comprehension.
   Still open after R22: R22 moved *when* `decompose_query` runs (concurrently
   inside `navigate_and_hyde`), not what it does internally.
4. **`retrieve_documents` serial prefix** (`retrieval.py:1116-1117`) — two
   nested DoctrineService round trips for the *same* `assistant_slug`.
5. **`context_engineer`** (`generation.py:742`, `:924`) — Guru-Brain vector
   search then Supabase feedback count; independent, serial, both ahead of
   generation.
6. **Deep-lane KG expansion** (`retrieval.py:1318-1325`) — awaited *after* the
   primary gather; only the relational lane gathers it concurrently.

Previously-documented serial `expand_query_with_ontology` tax: **fixed** — the
coroutine is created un-awaited (`:1161-1173`) and gathered at `:1299`.

## Graph capabilities: exact code paths

The previous version of this section was stale: it said `query_neo4j_subgraph`
had no production callers and that no graph-derived text reached generation.
That is not true of the current source.

| Path | How it is called | What reaches the request | Evidence boundary |
|---|---|---|---|
| Ontology-neighbor expansion | `expand_query_via_kg` from `retrieve_documents`; relational lane gathers it alongside primary Qdrant retrieval, deep lane awaits it after primary retrieval | Neighbor IDs are appended as a bounded additional query and retrieved from Qdrant | Graph topology expands recall; it is not itself teacher speech |
| Neo4j subgraph context | `query_neo4j_subgraph(base_question, scope=scope)` under `rag_graph_context_injection_enabled`, for relational/deep lanes or multi-concept queries | A `knowledge_source=neo4j_subgraph`, `type=graph_context` document is appended to `all_docs` with a low graph score (default 0.35) | Generation receives the relationship context, but quote filtering excludes `neo4j_subgraph` from teacher-quotation evidence |
| LightRAG context | For multi-concept, non-casual queries when `rag_lightrag_context_injection_enabled` is on; calls `lightrag.aquery(..., only_need_context=True)` under a timeout and character cap | A `knowledge_source=lightrag`, `type=graph_context` document is appended to `all_docs` | Supporting graph-linked context only; quote filtering excludes it from teacher-quotation evidence |
| GraphRAG fusion / graph prefetch | Separate opt-in flags | No general GraphRAG fusion unless enabled | Do not equate this with the above graph-context paths |

The ontology expansion budget is currently `max(1, 4 - len(primary_queries))`,
not the old `2 - len(primary_queries)`. The KG-generated query is added after
the planner outputs and shares this bounded expansion budget. It is not
automatically discarded whenever there are two or more primary sub-queries.

Graph context is therefore present in the general RAG generation context, but
must remain categorically separate from verified teacher utterances. The graph
can describe a relationship between concepts; it cannot establish that a
teacher said a sentence, prove a timestamp, or replace a source span. The
first-person route has separate graph/TU/OKF expansion flags and remains
default-off in code until its own measured evaluation and release gates pass.

## Dead or separately disabled paths

| Thing | Why dormant | file:line |
|---|---|---|
| `ToneAdapterStage` | body is `del ctx; return None` | `tone_adapter_stage.py:31` |
| `DoctrineCacheStage` | `DOCTRINE_CACHE_ENABLED=false` in the inspected local env | `doctrine_cache_stage.py` |
| `regenerate_gate` node | `rag_regenerate_before_rewrite=False` | `config.py` |
| `agentic_graph_traversal` | `agentic_graph_traversal_enabled=False` | `config.py` |
| BM25 lane | environment-dependent; do not treat an old `.env` snapshot as current hosted posture | `retrieval.py` |
| `lightrag` argument of `retrieve_for_single_query` | the argument is passed as `None` at the ordinary retrieval call sites; a separate multi-concept LightRAG context path exists | `retrieval.py` |
| GraphRAG fusion / graph prefetch | `graphrag_fusion_enabled=False` by code default | `container.py` |

## What this does not tell you

This DAG is structural. It does **not** establish:

- how long any node takes (nothing was timed);
- whether the serialization findings above matter in practice (no p50/p95);
- whether any expensive stage improves answer quality (no ablation was run —
  and until the `KNOWLEDGE_GRAPH_QUERY_ENABLED` / BM25 confound fix ships, the
  graph ablation could not have produced a clean result anyway);
- whether production env files override the "dead on live config" flags. Only
  `backend/.env` was read.
