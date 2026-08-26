
# Refreshed baseline after latest origin/main

The attached repository was refreshed to `771b507dd106efffcaeee45575cd00c7f7e5d33a` (`origin/main` matched). Health remained `ready=false`, `status=unhealthy` because `runtime_artifacts.missing_required=["okf_compiled"]`; Qdrant, Redis, Neo4j, LLM, embedding, fast/standard graph, queue, and backpressure checks were otherwise reported OK.

End-to-end local probe used freshly minted signed anonymous sessions, queued `/api/chat`, 250ms job polling, and structured result metadata. One sample per class:

- English simple: wall 6,355ms; result latency 6,113ms; `retrieve_documents` 221.4ms; `generate_answer` 1,066.4ms; grounded partial evidence.
- English stillness: wall 3,154ms; result latency 3,019ms; retrieval 13.4ms; generation 2,941.4ms; reflective-meaning fallback; abstained.
- English comparison: wall 24,186ms; result latency 24,146ms; retrieval 14.1ms; rerank 2,251.6ms; generation 7,450.6ms; verification 5,216.1ms; grounded partial evidence with verified citations.
- Hindi: wall 30,146ms; result latency 30,001ms; intent router 1,164.2ms; decompose 2,038.4ms; HyDE 4,426.1ms; retrieval 899.0ms; rerank 1,120.0ms; grade 1,731.2ms; rewrite 4,494.3ms; generation 4,634.0ms; abstained grounded-partial fallback.

Dominant bottlenecks are not queue admission or vector retrieval in these samples. They are serial LLM-like stages, especially Hindi intent/decompose/HyDE/rewrite/generation, comparison reranking plus generation plus verification, and a stillness generation tail despite fast retrieval. The one-sample nature means this is directional evidence, not a production p50/p95 claim.

## Independent retrieval and observability cross-check

Source: https://unstructured.io/insights/retrieval-latency-optimization-for-production-rag-systems

The production-RAG guidance recommends caching retrieval results/assembled context where query distribution is stable, batching and parallelizing independent vector/keyword/metadata work, routing by complexity, and applying explicit backpressure/timeouts/fallbacks. This agrees with the refreshed measurements: retrieval is cheap in the English samples, so the first optimization target is serial LLM work, not blindly changing Qdrant.

Source: https://github.com/open-telemetry/semantic-conventions/tree/main/docs/gen-ai

The old semantic-conventions path reports that GenAI conventions moved to a dedicated repository, so this GitHub page is provenance for the transition rather than the maintained standard itself. AskMukthiGuru should verify its OTel dependency/version and migrate to the maintained GenAI semantic-conventions repository before treating attribute names as stable. Regardless of schema version, the needed spans remain queue admission/wait, request preparation, retrieval, rerank, generation, verification, translation, fallback, and browser completion.

## Anthropic provider caching (official documentation, retrieved 2026-08-26)

Anthropic documents automatic and explicit prompt-prefix caching with 5-minute and 1-hour TTL options. The documentation says cached prefixes reduce repeated prompt processing and generally improve time-to-first-token for long documents, while the cache covers the stable prefix through a cache breakpoint. This is a provider/gateway-specific prefill optimization; it does not remove output decoding time and therefore is not a substitute for reducing serial RAG calls or generation budgets in the current OpenRouter path.

Source: https://platform.claude.com/docs/en/build-with-claude/prompt-caching
