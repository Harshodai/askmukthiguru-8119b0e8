# AskMukthiGuru Cross-Tier Latency Parameter Inventory

**Status:** Measurement and review artifact; no parameter in this document is changed by the catalog or benchmark runner. The inventory distinguishes Python defaults from the attached Docker runtime, because Compose and `.env` overrides can materially change latency and quality behavior.

## Executive summary

The current latency matrix cannot be improved safely by lowering every timeout, top-k, retry count, or verification budget. Those parameters trade latency against grounding, abstention, citation completeness, safety, and recovery from provider failure. The highest-priority measurement gaps are queue admission/claim, graph-wrapper residuals, provider response/TTFT, and route-label mismatch. The local runtime is also not release-ready: `/api/health` reports `ready=false` because the required `okf_compiled` artifact is absent; this artifact must not be fabricated.

| Area | Current evidence | Immediate interpretation |
|---|---|---|
| Queue and browser path | The earlier n=1 matrix included 202 responses and sub-millisecond polling, but lacked a direct job-to-trace join. | Instrumentation must precede tuning; polling is not the main root cause. |
| Graph and stage path | Large residuals remained after node timings, including standard factual, deep comparison, and Telugu. | Graph wrapper, coalescer, preparation, or uninstrumented work is material. |
| Provider path | Generation, rewrite, retrieval, verification, and translation share provider/network tails. | Add provider attempt/response/TTFT telemetry before model or provider policy changes. |
| Quality gates | Grounding, citations, abstention, distress handling, and tenant-scoped caches are binding invariants. | No latency change may disable or weaken these gates without held-out evidence. |
| Runtime readiness | Health currently reports missing `okf_compiled`; backend restart/warm-up has been unstable locally. | No production or release-latency claim is justified from this runtime. |

## Parameter inventory

| Parameter or behavior | Python default / code behavior | Observed Compose runtime or source | Latency leverage | Quality and safety risk | Required measurement before tuning |
|---|---|---|---|---|---|
| `llm_timeout` | 45 seconds in `backend/app/config.py` | Compose default is 60 seconds; runtime must be read from container env | High on provider tails and retries | Too low can convert recoverable provider work into abstention; too high increases tail latency | Provider attempt duration, timeout rate, route, model, retry count, and quality outcome |
| `pipeline_timeout` | 105 seconds | Compose default is 300 seconds | High for worst-case tail and graceful fallback | Too low can truncate grounded recovery; too high hides stuck work | End-to-end deadline milestones and terminal fallback quality |
| `llm_max_retries` | 2 attempts | Compose default is 2 | Medium-to-high for transient failures | Removing retries can lower availability and groundedness; repeated retries amplify queue contention | Retry success rate, incremental latency, status class, and evidence outcome |
| `llm_max_tokens_fast` / `llm_max_tokens_deep` | 800 / 1500 | No direct Compose override observed | Medium for generation and verification tails | Lower ceilings can truncate citations or explanations; deep routes need more budget | Finish reason, visible tokens, reasoning tokens where available, citation completeness |
| `node_timeout_fast` / `node_timeout_main` | 15 / 20 seconds | No direct Compose override observed | Medium for individual stage tails | Timeouts can turn partial evidence into an unsupported refusal if fallback is not safe | Per-node timeout outcomes and bounded fallback metadata |
| `cove_verification_timeout` | 12 seconds | No direct Compose override observed | High for standard/deep verification | Lowering can weaken faithfulness verification; must retain explicit unverified state | Verification pass rate, timeout rate, citation support, held-out faithfulness |
| `faithfulness_verification_timeout` | 8 seconds | No direct Compose override observed | Medium-to-high | A shortened verifier must fail closed as unverified, never as faithful | Timeout/quality confusion matrix by route and language axis |
| `translation_timeout_s` | 5 seconds | No direct Compose override observed | Medium on non-English query/history/answer paths | Preserving native text on timeout is safer than inventing a translation; measure comprehension/grounding | Explicit query/history/answer translation timings and language-stratified quality |
| `semantic_router_confidence_threshold` | 0.55 | No direct Compose override observed | High if many queries fall into expensive standard fallback | Lowering may misroute complex queries to fast and omit needed retrieval/verification | Held-out multilingual route accuracy, evidence support, and tail latency |
| `semantic_router_shadow_mode` | False | No direct Compose override observed | None in control mode; useful for safe experimentation | Shadow work itself can add load if it duplicates provider work | Compare predicted vs actual route without changing returned route |
| `semantic_router_enabled` / `semantic_router_top_k` | True / 3, but comments state these names are not wired to behavior | No direct Compose override observed | Potentially none until wiring is verified | Tuning an unwired parameter creates false confidence | Source-level call graph and runtime log confirmation |
| `openrouter_generation_model` / fallback | Gemini 3.6 Flash / Gemini 2.5 Flash in Python defaults | Runtime observed `google/gemini-3.6-flash`; fallback requires explicit verification | High across all model-backed routes | Faster model/provider can reduce reasoning quality or citation fidelity | OpenRouter response/TTFT, finish reason, provider, cost, and held-out quality |
| `openrouter_classify_model` | Meta Llama 3.1 8B in Python defaults | Runtime observed `google/gemma-3-12b-it` | Medium for classifier and routing tails | Smaller/faster classifier can misclassify distress, temporal, or deep cues | Intent/tier confusion matrix and safety false-negative rate |
| `USE_OPENROUTER_FOR_SIMPLE` | Code/config dependent | Runtime observed `false` | Medium for simple-route provider choice | Switching providers can change behavior and privacy posture | Route-level provider latency and quality comparison |
| `openrouter_rpm_limit` | 20 | Runtime observed 20 | High under concurrency if rate waits occur | Lowering increases graceful degradation; raising may trigger provider throttling | Rate-limit wait, 429s, queue depth, and provider status |
| `openrouter_budget_guard_enabled` | False | Must be confirmed in runtime | Medium when budget reservations contend | Fail-closed budget behavior can produce safe but unexpected abstention | Reservation wait, rejection, cost, and quality by route |
| `queue_concurrency` / `queue_max_size` | 5 / 50 | Queue worker log observed LLM queue max concurrent 5; job queue values need runtime confirmation | High under load | Too much concurrency can cause provider throttling, OOM, or tenant fairness problems | Admission wait, claim wait, provider queue wait, error rate, and cgroup memory |
| `max_concurrent_chat` | 20 | Health previously reported 20 | High for overload behavior | Raising can amplify tail latency and provider failure; lowering increases admission rejection | Load test with p50/p95, rejection rate, and per-tenant fairness |
| `llm_queue_max_concurrent` / `llm_queue_maxsize` | 5 / 50 | Runtime log observed max concurrent 5 | High when multiple graph nodes share the semaphore | Current priority enum is bookkeeping only; changing it without scheduler evidence is speculative | Queue wait distributions by operation and actual concurrency |
| Request queue mode | `use_request_queue=False` by Python default | Runtime log observed `USE_REQUEST_QUEUE=false` | High if enabled, but changes transport topology | New queueing can add claim delay and complicate browser semantics | Compare inline vs queued with same workload and browser milestones |
| `rag_top_k_retrieval` / after-cutoff | 20 / 10 | Runtime observed top retrieval 20 | High for retrieval, context construction, rerank, and generation | Lower k can remove supporting evidence and citations, especially multilingual/deep | Recall, citation support, rerank score distribution, and latency by route |
| `rag_top_k_rerank` | 10 in Python; runtime observed 5 | Runtime override is 5 | Medium-to-high for reranker CPU and candidate cascade | Lower k can hide the correct source and increase abstention or unsupported answers | NDCG/recall, source coverage, rerank time, and citation completeness |
| `rag_use_hyde` | False in Python | Runtime observed false; prior historical environment used true | High for routes that pay HyDE round trips | Disabling can reduce recall on ambiguous queries; the Indic-specific gate remains separate | Held-out recall/faithfulness and provider latency, not only wall time |
| `rag_max_rewrites` | 1 in Python | Runtime observed 2 | High for CRAG retry tails | Lower cap can terminate before recoverable evidence is found; higher cap causes serial tails | Recovery probability and incremental quality per rewrite |
| `rag_indic_use_hyde` / `rag_indic_max_rewrites` | False / 1 | Runtime observed false / 1 | Targeted multilingual leverage | These are policy experiments, not a license to create language-specific quality exceptions | Held-out multilingual evidence/citation/abstention parity |
| FlashRank / cross-encoder backend | FlashRank enabled; backend selection is service-driven | Runtime observed `USE_FLASHRANK=true`; model `BAAI/bge-reranker-v2-m3` | Medium-to-high for comparison and multilingual tails | Replacing rerankers can alter ordering and evidence support | Backend load time, CPU, candidate quality, and route-level NDCG |
| `rerank_min_score` | 0.35 in Python | Compose default 0.15 | Medium for candidate count | Raising can remove useful evidence; lowering can increase noisy context and generation time | Score histograms, evidence recall, citations, and context size |
| Retrieval expansion / follow-up / graph traversal | Feature-controlled but stage behavior is distributed | Runtime flags require explicit env audit | High for standard/deep/multihop residuals | Disabling expansion can lose multi-hop support and force abstention | Substage waits, hop coverage, source support, and route quality |
| Context compression | Disabled by default | Runtime observed disabled | Medium on long contexts | Compression can remove citation-bearing detail or alter source fidelity | Compression latency and before/after evidence support |
| `max_tokens_per_request` and context budgets | 12,000 request-token ceiling; persona budget 2,048 | Runtime must be confirmed | Medium-to-high for long history/assistant routes | Truncating memory or evidence can break tenant/personalization semantics | Input token counts, truncation flags, source/citation retention |
| Distress thresholds and rolling window | Semantic threshold 0.72; history threshold 0.6; 5-turn window; escalation 3 | Runtime must be confirmed | Not a safe latency tuning target | False negatives are unacceptable; distress redirects must remain fast and safe | Safety confusion matrix and first-status/complete latency |
| Multilingual guardrails | Enabled by default | Runtime must be confirmed | Medium for non-English pre-processing | Disabling creates language-dependent injection/crisis gaps | Guardrail latency and multilingual safety recall |
| `WEB_SEARCH_ENABLED` / provider timeout | Search provider is configurable; timeout lesson sets 12 seconds | Runtime log observed web search disabled | High only for temporal/live-logistics paths | Removing live search can make temporal answers stale; timeout must abstain honestly | Provider timeout/status, freshness, and logistics correctness |
| `WEB_CONCURRENCY` | Deployment default 1 | Compose default 1 | Medium; more workers may increase parallel throughput | More workers duplicate model memory and can cause OOM/cache contention | Per-worker memory, queue wait, p95, and restart count |
| Cache thresholds | Per-tier thresholds remain in `CacheCheckStage` (fast 0.82, simple 0.85, standard 0.87, complex/deep 0.92) | Global Compose semantic threshold default is 0.85; runtime cache mode is Qdrant+Redis | High for cache hit rate and pre-route work | Similarity reuse can replay mismatched evidence; personalized/assistant/attachment guards must remain first | Cache hit quality, evidence overlap, source release, and lookup latency |

## Decision order

The current evidence supports the following order: first complete queue-to-trace and provider attribution; next compare graph-wrapper residuals against stage sums; then benchmark provider/model and retrieval candidate alternatives in shadow or offline replay; only afterward consider adaptive route control. Any control policy should use privacy-safe request features, current queue/provider state, remaining deadline, predicted quality floor, and conservative fallback. It must begin in shadow mode and be evaluated on held-out multilingual, temporal, adversarial, distress, citation, and abstention cases.

## Runtime caveats

The attached backend container is bind-mounted to the checkout, but a targeted restart entered a prolonged warm-up/restart state. Health reports `ready=false` because `okf_compiled` is missing, while Qdrant, Redis, Neo4j, LLM, embedding, graphs, and caches report healthy or available. The benchmark result recorded before restart therefore remains a historical n=1 observation and is not a post-change proof. No production deployment, corpus change, artifact fabrication, global cache flush, commit, or push is authorized by this task state.

## References

[1]: ../backend/app/config.py "AskMukthiGuru central configuration"
[2]: ../backend/docker-compose.yml "AskMukthiGuru Compose runtime overrides"
[3]: ../backend/app/pipeline/stages/cache_stage.py "Cache and tier lookup guards"
[4]: ../backend/app/pipeline/stages/graph_stage.py "Graph selection and tier reconciliation"
[5]: ../backend/services/openrouter_service.py "OpenRouter provider gateway"
[6]: ../audit_work/cross_tier_latency_summary.tsv "Cross-tier n=1 benchmark summary"
[7]: ../audit_work/latency_probe_all_routes.jsonl "Cross-tier n=1 route samples"
