# AskMukthiGuru Ruthless Latency Program — Phase 4–6 Evidence

**Date:** 2026-08-26  
**Checkout:** synchronized `main` at `771b507dd106efffcaeee45575cd00c7f7e5d33a` before this work  
**Scope:** attached macOS computer, local Docker Compose stack, dependency-complete host backend environment

## Executive result

The dominant measured Hindi tail was model-backed RAG work rather than queue admission or ordinary English vector retrieval. The implemented change is deliberately narrow: Indic requests reuse the already validated `detected_language` state, skip HyDE unless explicitly enabled, and use an independent CRAG rewrite cap of one. English keeps the configured global HyDE and rewrite policy. Grading, citation verification, grounded-partial envelopes, abstention, distress handling, tenant/cache guards, and browser transport were not weakened.

A controlled same-query experiment under the original global slow settings reduced Hindi backend latency from **30,001 ms to 18,112 ms**, a reduction of **11,889 ms / 39.6%** in the post-change single-case proof. The earlier same-query treatment with `CACHE_MODE=memory` measured **30,001 ms to 16,121 ms (-46.3%)**; that stronger result is directional because provider timing varied between repeated local runs. Both treatment records preserved the same abstained grounded-partial metadata and `citations_verified=true`. These are n=1 samples per class, not p50 or p95 claims.

## What was measured before implementation

The synchronized-main uncached baseline used freshly minted signed anonymous sessions, queued `/api/chat`, 250 ms polling, and the same four query strings. The result was one sample per class.

| Class | Wall ms | Backend ms | Dominant named timings | Quality metadata |
|---|---:|---:|---|---|
| English simple | 6,355 | 6,113 | retrieval 221; generation 1,066 | grounded partial evidence |
| English stillness | 3,154 | 3,019 | retrieval 13; generation 2,941 | abstained reflective-meaning fallback |
| English comparison | 24,186 | 24,146 | rerank 2,252; generation 7,451; verification 5,216 | grounded partial evidence; citations verified |
| Hindi | 30,146 | 30,001 | intent 1,164; decompose 2,038; HyDE 4,426; rewrite 4,494; generation 4,634 | abstained grounded-partial fallback; citations verified |

The node-timing ledger is not a complete backend budget. For the baseline, node sums were 1,288 ms, 2,955 ms, 14,934 ms, and 20,525 ms respectively; the remaining backend budget includes request preparation, graph-internal waits, provider queueing/retry/serialization, stage wrappers, and uninstrumented work. The fresh correlation log showed the full `langgraph` wrapper exceeding the named node sum on the Hindi run, so future work should add provider/queue/translation spans before attributing every tail to retrieval.

## Implemented change

The central settings module now exposes `rag_indic_use_hyde` (default `false`) and `rag_indic_max_rewrites` (default `1`, bounded to 0–3). `backend/rag/nodes/utils.py` provides deterministic state helpers based on `detected_language`; it does not run a second language detector. `generate_hyde` applies the global `rag_use_hyde` switch and then the Indic opt-in gate. `route_after_grading` applies the smaller Indic rewrite budget while preserving the global budget for English.

Docker Compose now wires the settings explicitly, preventing an operator’s Compose override from being silently shadowed by `env_file` precedence. The root `.env.example`, README environment table, CLAUDE pipeline map, lessons ledger, and product-opportunities roadmap describe the policy and its held-out evaluation gate. No secret-bearing `.env` file was modified or committed.

## Before/after treatment evidence

The first controlled treatment used `RAG_USE_HYDE=false`, `RAG_MAX_REWRITES=1`, and `CACHE_MODE=memory` to remove cache contamination. The later post-change runtime proof used the tracked image with the original global settings (`RAG_USE_HYDE=true`, `RAG_MAX_REWRITES=2`) and the new Indic settings (`RAG_INDIC_USE_HYDE=false`, `RAG_INDIC_MAX_REWRITES=1`). The cache was cleared only through the repository’s targeted query-cache procedure; no global Redis flush was used.

| Class | Baseline backend ms | First controlled treatment ms | First delta | Final tracked Hindi proof ms | Final delta vs baseline |
|---|---:|---:|---:|---:|---:|
| English simple | 6,113 | 4,154 | -32.0% | not re-run uncached | — |
| English stillness | 3,019 | 3,299 | +9.3% | not re-run uncached | — |
| English comparison | 24,146 | 21,575 | -10.6% | not re-run uncached | — |
| Hindi | 30,001 | 16,121 | -46.3% | 18,112 | -39.6% |

The treatment’s Hindi node metadata confirms `generate_hyde` fell from multi-second execution to approximately 0–1 ms, while the remaining tail is dominated by decomposition, retrieval, reranking, rewrite, and provider variability. The final tracked proof returned `grounding_state=abstained`, `verification.method=grounded_partial_fallback`, `verification.passed=false`, `citations_verified=true`, `query_tier=tier3_complex`, and `cache_hit=false`. This is the intended fail-closed quality state, not an invented generated teaching.

The English comparison path was not rerouted to a fast graph. Existing regression coverage confirms that a deterministic deep comparison classification is preserved and that the selected deep graph synchronizes its state tier to `tier4_deep`; the implementation did not weaken comparison grading or verification to chase latency.

## Validation matrix

| Validation | Result | Interpretation |
|---|---|---|
| Focused tiered-routing and graph-stage tests | 18 passed in 16.15 s | New Indic policy and existing comparison-tier guard pass together |
| Full backend suite (`backend/tests`) | 2,456 passed, 30 skipped, 1 warning in 249.95 s | No dependency-complete backend regression detected |
| Frontend Vitest | 522 passed, 6 skipped across 90 files | Existing frontend contracts remain green; jsdom navigation warnings were non-fatal test noise |
| Frontend production build and SEO prerender | passed; 28 routes prerendered | Frontend release build remains valid |
| Chromium page-smoke, progressive-anonymous, and accessibility suites | 34 passed in 27.8 s | Anonymous routing, public pages, and serious/critical accessibility checks remain green with service workers blocked |
| Compose config and `git diff --check` | passed | Compose syntax and patch whitespace are clean |
| Final `/api/healthz` | HTTP 200 | Liveness/transport endpoint responds |
| Final `/api/health` | `ready=false`, `status=unhealthy` | Release blocker remains: required `okf_compiled` artifact is absent; do not manufacture it |

Qdrant, Redis, Neo4j, LLM, embedding, graph, queue, backpressure, LightRAG, and OCR checks were otherwise healthy in the captured health JSON. The missing `okf_compiled` artifact remains a release-readiness issue independent of this latency patch.

## Research and limitations

Official provider and infrastructure research supports the decision to prioritize serial model stages. NVIDIA notes that decode is frequently memory-bound; vLLM documents continuous batching, prefix caching, and speculative decoding as serving-layer levers; Qdrant documents recall/latency tuning and payload indexing; and OpenAI and Anthropic document prompt-prefix caching as a prefill/time-to-first-token optimization rather than output-decode elimination. Anthropic’s current documentation is recorded in `audit_work/latency_research.md` at [the official prompt-caching page][1]. The current OpenRouter path still needs a gateway-specific TTFT/output-token measurement before any provider-caching change is attempted.

GitHub gem searches and the Internet Skill Finder were exercised as requested. The attached desktop lacked a usable GitHub CLI for the broad search, sandbox GitHub searches returned empty arrays, and the skill finder’s real-time lookup failed into cached fallback with no relevant match. SimilarWeb returned no traffic or engagement data because of insufficient credits. YouTube pages exposed titles, dates, and player metadata but not usable captions; detailed video claims were therefore not used. These limitations are preserved in the audit ledger rather than treated as product evidence.

## Recommended next sprint

The next highest-value work is not another blind vector-index change. Add a trace ledger for request preparation, provider queue wait, provider attempt/retry, first token, output decode, rerank backend/model load, verification gateway, translation, and cache update. Then run a held-out multilingual benchmark with faithfulness, citation support, abstention correctness, safety controls, and wall/backend latency measured together. The benchmark should decide whether Indic HyDE ever earns an opt-in rollout and whether the remaining rewrite should be retained for all Indic query classes.

For English comparison tails, profile the actual reranker backend and verification path before changing candidate caps or thresholds. Preserve the deep/comparison graph and fail-closed evidence gates. For cold start, treat the absent `okf_compiled` artifact and the roughly 20–30 second local model warm-up as separate release and startup concerns; do not add placeholders or claim production parity.

No commit or push was performed in this continuation because the latest instruction requested pulling and continuing, not a new explicit authorization to publish these new latency changes. The working tree contains the implementation and evidence artifacts for review.

## References

[1]: https://platform.claude.com/docs/en/build-with-claude/prompt-caching "Anthropic Prompt caching documentation"
