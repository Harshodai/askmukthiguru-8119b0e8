# System Design for the LLM Era — AskMukthiGuru Master Doc (Phase 7)

Binding architecture reference for the chat/RAG serving path. Section numbers
are stable — tests in `tests/test_llm_system_design_invariants.py` pin the
invariants by name. Dated measurements are provenance, not live SLO claims.

## 1. Topology

```
Client (Lovable/web, Capacitor native) ──HTTPS/SSE──▶ Nginx (/api)
  ▶ FastAPI app (backend/app/main.py; plain uvicorn in Docker, start_railway.py on Railway)
    ▶ POST /api/chat → anon-quota → orchestrator → PipelineCoordinator.execute()
      → StageRunner chain (pipeline_builder.py):
        CacheCheck → RequestState → InputGuardrail → CircuitBreaker → DoctrineCache
        → CasualShortCircuit → Distress → BoundedComparisonShortCircuit → Graph
        → MeditationGen → Translation → ToneAdapter → OutputGuardrail → Memory
        → CacheUpdate → ResultAssembly
      → GraphStage → LangGraph (graph_strategies.py Fast/Standard/Deep; nodes in rag/nodes/)
    ▶ POST /api/chat/stream → stream_orchestrator (queued SSE + direct SSE)
  ▶ Qdrant (spiritual_wisdom dense/sparse), Neo4j (GraphRAG), Redis (cache/quota), Postgres/Supabase (auth/memory)
```

Node data contract: `GraphState` TypedDict in `rag/states.py` (carries
`request_id`). Composition root: `app/dependencies.py` (`ServiceContainer`).
Config only via `app.config.settings`. LLM backends: separate non-inheriting
provider classes (`openrouter_service.py` / `sarvam_service.py` /
`ollama_service.py`) behind `services/llm_gateway.py` (`LLMGateway`).

## 2. Latency budget (P90 < 2s warm, P99 < 5s)

- PipelineCoordinator reports per-stage timings; `node_timings` surfaces
  LangGraph node latency on `ChatResponse`.
- Hot path rules: bounded meditation-vs-contemplation short-circuit only after
  input/distress guardrails, English only, with explicit limited-support
  metadata, zero citations, abstained grounding.
- Translation is a bounded dependency (`translation_timeout_s`, default 5s):
  fail open with native/original text; English-with-Indic-preference never
  invokes translation.
- Cold costs that must NOT sit on the user path: BGE-M3/ONNX encoder load,
  all-MiniLM intent prewarm (non-fatal startup prewarm), reranker fetch.
- Long-tail risks (open): multilingual tail variance, concurrent wall-clock
  vs internal route timings (capacity/queueing), first-request model load.

## 3. Five-tier cache

| Tier | Store | Key scope | TTL |
|------|-------|-----------|-----|
| 1 Exact query | Redis `mukthiguru:cache:*` | normalized query + assistant fingerprint | bounded, refreshable |
| 2 Semantic | GPTCache / Redis semantic | embedding similarity | similarity threshold-gated |
| 3 Hot doctrine | in-process + Redis | flagship teaching IDs | short, explicit |
| 4 Translation | process-local SHA-256, max 512 entries | source/target/text ≤240 chars | 15 min; never shared storage |
| 5 Ephemeral session | Redis sliding | session turns | 900s |

Invariants: `REDIS_CACHE_MAX_KEYS` applies ONLY to exact-query keys; never
flush globally (`flush_cache.py` scans query-cache namespaces only);
client-supplied assistant config bypasses shared reuse (fingerprint in
coalesce key, raw prompt never in keys); attachment-backed turns bypass
shared reuse or carry a bounded content digest.

## 4. LITM canonicalization (normalize → index → expand)

Lightweight Intent-Topic Mapping keeps retrieval language-agnostic:

1. **Normalize** — lowercase/strip, Indic→Latin alias map, doctrine synonym
   table (e.g. "serene mind" ↔ "samatvam").
2. **Index** — canonical topic IDs as Qdrant payload filters + Neo4j concept
   node seeks (`UNIQUE_CONCEPT_NAME`, indexed `NodeUniqueIndexSeek`).
3. **Expand** — one-hop concept traversal (`Expand(All)` off the indexed
   seek), LightRAG relations for RELATIONAL/FACTUAL/QUERY intents.
Edges: `MENTIONS_TOPIC`, `GROUNDED_IN`, `CITED_BY`. Tests pin edge names and
the normalize→seek→expand order.

## 5. ReAct safeguards (loop detection, step caps, breaker unmasking)

- Agentic graph traversal is step-capped; loop detection aborts repeated
  state revisits (test: cyclic path terminates, visited-set grows).
- Circuit breakers fail CLOSED-safe: `CircuitBreaker` stage runs AFTER
  `InputGuardrail` so safety decisions are never bypassed by an open circuit;
  provider classifier ERROR/TIMEOUT maps to public `system_error`, never
  silent abstain or safety_redirect.
- Breaker state is unmasked in deep health (per-provider open/closed +
  rejection counters), never hidden behind a generic degraded flag.

## 6. Safety, SSE, and PII

- Deterministic acute self-harm/distress blocks run in `InputGuardrailStage`
  (6 scripts: en/hi/te/kn/ml/mr + Marathi idioms). Crisis → blocked
  `DISTRESS`, no citations, no final answer. Domestic-violence and
  prompt-injection blocks are deterministic and terminal.
- Browser SSE metadata is a public projection: allowlisted fields only —
  never `memory_context`, `attachment_context`, prompts, safety state, raw
  graph state. Queued SSE emits `final` (authoritative post-normalization
  answer) then `done`; frontend MUST persist the `final` event. Consumer
  returns immediately on `done` (no extra XREAD wait); non-stream fallback
  polls immediately then backs off 250ms→1s.
- PII: log redaction across services; translation/latency logs carry
  source/target/duration only, never raw or translated user text; `<think>`
  blocks are stripped before SSE emission.

## 7. Eval: faithfulness, TTFT/TPOT, abstention

- Golden set: `scripts/eval/golden_questions.json` (50 items; factual,
  practices, synthesis, multilingual, adversarial; 10 abstain).
- Metrics: faithfulness floor (reject-rate delta via `ragas_eval.py`),
  abstention precision (should_abstain ↔ abstain), citation validity
  (inline `[n]` verified against retrieved sources; orphans stripped),
  TTFT (first SSE token) / TPOT (per-token) from stream probes.
- RAGAS runner: `scripts/eval/run_ragas_eval.py` (faithfulness,
  answer_relevancy, context_precision; CI-gate `--ci --threshold 0.6`).
- NDCG integration (`tests/test_qdrant_search_quality.py`) requires
  production Qdrant env — never run against localhost defaults and claim a
  baseline.

## 8. DSPy self-improvement (MIPROv2)

- Signature: `MukthiGuruSignature` (context/question/tone → answer);
  module: `MukthiGuruModule` (ChainOfThought).
- Provider priority in `setup_dspy_lm()`: openrouter (live default,
  `dspy.LM(model=f"openrouter/{model}")`) → nim → ollama local-only.
- Harness: `scripts/eval/self_improving_harness.py` — MIPROv2 over
  35-train/15-dev stratified split; composite metric (faithfulness ≥ 0.85,
  abstention precision, citation validity, zero-tolerance distress veto).
- Approved programs only are saved to
  `rag/compiled/dspy_optimized_program.json`; `load_compiled_module()`
  overlays it at `make_module()` time. Harness never writes corpus/Qdrant.

## 9. Garani 33-point matrix (condensed)

Correctness (1–6): faithfulness floor, citation verification, orphan-strip,
abstention precision, multilingual parity, comparison honesty.
Safety (7–12): distress block, DV block, injection block, PII redaction,
untrusted-attachment labelling, no corpus writes from uploads.
Latency (13–18): P90/P99 budgets, TTFT/TPOT probes, prewarm, bounded
translation, immediate-done SSE, backoff polling.
Cost (19–23): per-provider cost split (reported/estimated/unknown),
budget guards, no silent vendor reroute, memory-first optimization,
benchmark moratorium near hard limit.
Reliability (24–28): breaker ordering, fail-open translation, graceful
Redis/Neo4j/Qdrant degradation, honest abstention over fabrication,
idempotent checkpoints cross-validated against stores.
Evolvability (29–33): Pydantic forbid-gates, model_validate_json paths,
DSPy compiled-artifact versioning, OKF review gate, lessons.md updates.

## 10. 28-point production checklist

1. `FORWARDED_ALLOW_IPS` set (non-wildcard) before any Railway deploy.
2. Full backend suite green in CI/test image (never claim from py_compile).
3. NDCG integration vs production Qdrant baseline captured.
4. RAGAS CI gate ≥ 0.6.
5. Faithfulness floor holds on held-out set.
6. Abstention precision measured; retrieved-evidence refusals = P0.
7. Distress/DV/injection blocks verified per locale.
8. PII redaction scan clean; no raw text in latency logs.
9. SSE `final`-event parser published in hosted bundle.
10. Translation timeout + fail-open verified.
11. Cache tiers isolated; no global flush path.
12. Quota/rate-limit Redis adapters with memory fallback verified.
13. Breaker order (guardrail before breaker) regression green.
14. ONNX/RRF/DBSF/graph-parallel changes evidence-gated only.
15. Embedding dimension contract (1024) validated at startup canary.
16. OKF `compiled.json` + doctrine lexicon present (never placeholders).
17. Ingestion `find_artifact()` gate on every LLM→Qdrant path.
18. Checkpoints cross-validated after any store wipe.
19. Upload path ephemeral (10MB/file, 50MB total, 8k context cap).
20. RLS probes + nightly workflow secrets set.
21. Leaked-password protection enabled.
22. Secrets scan clean (no JWT/backdoor, gitleaks allowlists annotated).
23. Bandit gate without `|| true`.
24. pip-audit rerun after upgrades.
25. Mobile push/OAuth/storage paths smoke-tested.
26. Custom-domain + breakpoint coverage closed.
27. Cost/memory snapshot within hard limit.
28. lessons.md + runbook updated for every change in this doc.
