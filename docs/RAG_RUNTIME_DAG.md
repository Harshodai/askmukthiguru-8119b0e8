# RAG Runtime DAG — reconstructed from source

**Reconstructed:** 2026-09-11 · **Evidence:** `PROVEN FROM CODE` unless noted.

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

Defined in `app/pipeline/stages/pipeline_builder.py:36-53`. The order documented
in both `CLAUDE.md` files is wrong: `CircuitBreaker` runs **fourth**, not
second, and `BoundedComparisonShortCircuit` is absent from the docs entirely.

| # | Stage | file:line | Runs when | LLM calls |
|---|---|---|---|---|
| 1 | CacheCheck | `cache_stage.py:137` | not benchmark-disabled, not incognito | 0-1 |
| 2 | RequestState | `glue_stages.py:314` | always | 0 |
| 3 | InputGuardrail | `guardrail_stage.py:91` | always | provider-dependent |
| 4 | CircuitBreaker | `guardrail_stage.py:35` | always (short-circuits when open) | 0 |
| 5 | DoctrineCache | `doctrine_cache_stage.py:37` | `doctrine_cache_enabled` — **false in `.env`, dead** | 0 |
| 6 | CasualShortCircuit | `glue_stages.py:334` | deterministic greeting | 0 |
| 7 | Distress | `distress_stage.py:124` | always (assess is regex) | 0-1 |
| 8 | BoundedComparisonShortCircuit | `glue_stages.py:255` | en + bounded meditation comparison | 0 |
| 9 | **Graph** | `graph_stage.py:101` | always | **1-8** |
| 10 | MeditationGen | `meditation_gen_stage.py:59` | proactive triggered + citations | 1 |
| 11 | Translation | `glue_stages.py:392` | indic request, english answer | 0 |
| 12 | ToneAdapter | `tone_adapter_stage.py:31` | **body is `del ctx; return None` — no-op** | 0 |
| 13 | OutputGuardrail | `guardrail_stage.py:202` | always | provider-dependent |
| 14 | Memory | `memory_stage.py:65` | not incognito + persistable user | 0 |
| 15 | CacheUpdate | `cache_stage.py:402` | not incognito/blocked/unfaithful | 0 |
| 16 | ResultAssembly | `glue_stages.py:441` | always (terminal) | 0 |

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

**Standard** (`:212-361`)
```
resolve_followup -> decompose_query -> navigate_and_hyde -> retrieve_documents
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

1. **`decompose_query -> navigate_and_hyde`** (`graph_strategies.py:292`) — two
   independent LLM calls on a serial edge. `generate_hyde` and
   `navigate_knowledge_tree` both read `question`/`rewritten_query`; **neither
   reads `sub_queries`**, so the dependency the edge implies does not exist.
2. **`prepare_user_memory`** (`orchestrator_utils.py:837-877`) — five
   independent I/O awaits in sequence, including `update_profile` (`:857`), a
   **write on the critical path whose result nothing later reads**.
3. **`decompose_query` sub-query expansion** (`retrieval.py:704`) — N
   independent doctrine-service round trips inside a list comprehension.
4. **`retrieve_documents` serial prefix** (`retrieval.py:1116-1117`) — two
   nested DoctrineService round trips for the *same* `assistant_slug`.
5. **`context_engineer`** (`generation.py:742`, `:924`) — Guru-Brain vector
   search then Supabase feedback count; independent, serial, both ahead of
   generation.
6. **Deep-lane KG expansion** (`retrieval.py:1318-1325`) — awaited *after* the
   primary gather; only the relational lane gathers it concurrently.

Previously-documented serial `expand_query_with_ontology` tax: **fixed** — the
coroutine is created un-awaited (`:1161-1173`) and gathered at `:1299`.

## Dead on live config

| Thing | Why dead | file:line |
|---|---|---|
| `ToneAdapterStage` | body is `del ctx; return None` | `tone_adapter_stage.py:31` |
| `DoctrineCacheStage` | `DOCTRINE_CACHE_ENABLED=false` | `.env` |
| `regenerate_gate` node | `rag_regenerate_before_rewrite=False` | `config.py:680` |
| `agentic_graph_traversal` | `agentic_graph_traversal_enabled=False` | `config.py:1210` |
| BM25 lane | `BM25_RETRIEVAL_ENABLED=false` | `.env` |
| `lightrag` param of `retrieve_for_single_query` | declared, **never referenced in the body**; both call sites pass `None` | `retrieval.py:794`, `:1276`, `:1421` |
| `query_neo4j_subgraph` | **zero production callers** (tests only) | `retrieval.py:245` |
| GraphRAG fusion, graph prefetch | `graphrag_fusion_enabled=False` | `container.py:406` |

## Where the knowledge graph actually goes

```
expand_query_via_kg (rag/kg_expansion.py:167)   <- the ONLY live Neo4j call per request
  gated: retrieval.py:1138-1143
  concurrent with the dense fan-out (:1299, relational lane)
      -> kg_neighbors
  -> augment_query(...)          retrieval.py:1395
  -> appended LAST to expansion_queries (:1397)
  -> [...][:remaining_budget]    remaining_budget = 2 - len(primary_queries)
        == 0 whenever there are 2+ sub-queries  ->  DISCARDED
        == 1 and planner empty                  ->  one extra retrieval, no provenance
```

The prompt's "RELATIONSHIPS & DOCTRINE ONTOLOGY (sacred graph)" block is built
from multi-chunk bookkeeping (`generation.py:1032-1043`), not graph edges.

**Conclusion: no Neo4j-derived text reaches the LLM prompt.** The graph's only
possible live influence is extra query *terms*, in a narrow case.

## What this does not tell you

This DAG is structural. It does **not** establish:

- how long any node takes (nothing was timed);
- whether the serialization findings above matter in practice (no p50/p95);
- whether any expensive stage improves answer quality (no ablation was run —
  and until the `KNOWLEDGE_GRAPH_QUERY_ENABLED` / BM25 confound fix ships, the
  graph ablation could not have produced a clean result anyway);
- whether production env files override the "dead on live config" flags. Only
  `backend/.env` was read.
