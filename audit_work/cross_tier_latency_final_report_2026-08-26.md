# AskMukthiGuru Cross-Tier Latency Program — Final Evidence Report

**Date:** 26 August 2026  
**Author:** **Manus AI**  
**Checkout:** attached macOS checkout, synchronized at `771b507dd106efffcaeee45575cd00c7f7e5d33a` before this continuation  
**Scope:** queued chat, direct/stream-capable orchestration, LangGraph route selection, cache gates, provider calls, multilingual paths, safety short-circuits, and browser-facing polling/SSE boundaries

## Executive conclusion

The latency problem is system-wide, but its causes differ by route. The first cross-tier matrix found long tails in English standard, comparison, temporal, Hindi, and Telugu requests, while the distress safety redirect was already fast. The new instrumentation shows that node timings alone were insufficient: queue admission, graph wrappers, provider dispatch, and cache-stage work could dominate the apparent route budget even when named graph nodes were nearly empty.

The earlier warm-shared and cache-miss n=1 files are retained as diagnostic artifacts, but their latency values are **excluded from this report’s performance metrics**. Warm-cache rows, cache-served rows, and single-run values do not represent the requested cache-disabled path.

## Cache-disabled-only repeated benchmark

The local backend was recreated with `LATENCY_BENCHMARK_CACHE_DISABLED=true`, and the container environment was verified before measurement. This switch bypasses application cache reads and writes in cache admission, doctrine cache, and cache update. It does not flush Redis or mutate stored cache data. The repeated runner used `--cache-mode disabled`, marked a sample included only when it completed with `cache_hit=false` and a non-cache route decision, and recorded all 36 samples as included with zero cache hits.

| Route fixture | n included | Backend mean ms | Wall mean ms | Quality/routing observation |
|---|---:|---:|---:|---|
| Fast casual | 3 | **2.33** | 316.87 | `instant_greeting`, CASUAL, abstained, no provider |
| Fast factual | 3 | 4,834.67 | 5,042.53 | tier2_simple, grounded-partial evidence |
| Fast meditation | 3 | 2,518.33 | 2,594.05 | tier2_simple, reflective-practice fallback |
| Standard factual | 3 | 4,849.33 | 5,001.07 | tier2_simple, grounded-partial evidence |
| Standard reflective | 3 | 5,924.33 | 6,072.39 | tier2_simple, grounded-partial evidence |
| Deep comparison | 3 | 24,741.00 | 24,874.05 | comparison remains expensive; verification path preserved |
| Deep multihop | 3 | 16,341.67 | 16,435.82 | tier3_complex, grounded-partial evidence |
| Distress | 3 | 0.33 | 277.44 | safety redirect, no provider |
| Temporal | 3 | 6,278.67 | 6,414.08 | tier2_simple, abstained with verification |
| Hindi simple | 3 | 20,675.67 | 20,855.78 | tier3_complex, abstained grounded-partial fallback, citations verified |
| Hindi comparison | 3 | 18,772.33 | 18,927.50 | tier3_complex, abstained grounded-partial fallback, citations verified |
| Telugu simple | 3 | 33,301.67 | 33,494.43 | tier3_complex, abstained grounded-partial fallback, citations verified |

These are **exploratory means only**: each route has n=3, so p50/p95 are intentionally suppressed. The matrix is nevertheless the first route-wide dataset that is explicitly cache-disabled, has zero cache hits, and covers fast, standard, deep, safety, temporal, Hindi, and Telugu paths under one policy. The remaining tail is concentrated in deep comparison, Telugu, Hindi, and deep multihop rather than in cache lookup.

The original cross-tier logs showed large unexplained residuals between graph-wrapper time and named node sums. The new queue, stage, route, and provider ledgers are intended to explain those residuals in future cache-disabled runs rather than invite blind threshold reduction.

## What changed in the implementation

### End-to-end queue and trace attribution

Queued jobs now retain internal admission, claim, dispatch, result-publication, completion, correlation, and trace metadata. The worker propagates a privacy-safe timing context into both synchronous and streaming worker paths. Stage logs include `job_id` and `trace_id`, and cache, error, circuit-breaker, graph, and result paths preserve the original request trace where available. Internal queue metadata is deliberately excluded from `get_job()` and therefore from browser polling responses.

Queued stream orchestration also records internal final-published and done-published milestones without changing the SSE event payload, ownership checks, or public projection. Raw prompts, memory, raw graph state, source payloads, safety internals, and arbitrary stage metadata remain excluded from the browser contract.

### Actual route visibility

Pipeline results carry a bounded internal route manifest that can record requested/selected variant, detected cache tier, normalized query tier, on-device intent, decision method, policy version, and cache class. The coordinator projects only allowlisted internal route and stage spans into telemetry. `PipelineResult.to_chat_response()` does not expose `route_metadata`.

The shared on-device classifier is reused between cache and graph routing, but its coarse tier is not treated as authoritative for complexity. Existing query-shape, deep-cue, and policy signals still participate in selection. This avoids a duplicate classifier call without turning a coarse intent label into an unsafe routing override.

### Provider timing without content capture

The OpenRouter service now emits content-free timing for request attempts, provider/model, status class, total duration, response timing, retry count, token counts, cache-read/write fields, finish reason, and streaming first-chunk/TTFT measurements where available. This creates the data needed for future provider preference, prefix-cache, and deadline-headroom experiments without capturing prompts or model output.

### Generic greeting short path

Greeting detection is centralized in `backend/app/routing_primitives.py` and shared by cache admission and response assembly. A pure greeting or a short one-word vocative form such as `Namaste Guruji` is recognized structurally. The predicate rejects question punctuation and broader three-word prompts such as `Hello dear seeker`, preventing the overmatch that was caught by the full endpoint regression.

Cache admission seeds the request-scoped CASUAL observation and returns before hot/vector/exact/semantic probes because greetings are not valid shared-cache answers. The normal input guardrail and short-circuit stage order remains intact. This is a reusable structural mechanism, not an Indic-only or query-specific route rule.

### Optional-stage deadline and queue attribution work

The retrieval-expansion planner is now treated as an optional recall enhancement. It still launches concurrently with primary retrieval on eligible standard/deep paths, but the merge point waits only the centrally configured `RAG_RETRIEVAL_EXPANSION_SOFT_WAIT_SECONDS` budget (default 0.35 seconds). If the planner is slow, its task is cancelled and primary retrieval proceeds unchanged. This is a generic deadline policy, not a language- or query-specific hardcode. Internal evaluation trace records `completed`, `soft_timeout`, `error`, or `policy_disabled` without entering public polling/SSE projections.

The shared LLM semaphore now records bounded, content-free wait averages by operation and priority for both ordinary and streaming calls. Provider wrappers label classification, generation, verification, decomposition, HyDE, translation, compression, and streaming operations. The existing semaphore concurrency and full-stream hold are unchanged; priorities remain observational until a fairness/load study justifies a real scheduler.

OpenRouter provider latency routing is now an opt-in, server-side policy experiment. Validated settings can emit official `sort` and p90 preference fields while preserving data-collection denial, provider allowlists, model pinning, and fallbacks. Defaults remain unchanged. A runtime trial with `sort=latency` produced no valid included cache-free samples because attempts timed out or disconnected; it is therefore rejected as evidence and the local runtime was restored to the stable default routing policy.

### Background side-effect and stage telemetry work

Healing-course assignment was moved off the first-response critical path as a timeout-bounded, observed background task, preserving its feature flag, persistence conditions, exception handling, and privacy boundary. Stage telemetry now records relative start/end times, duration, status, bounded error code, and release identifier. These changes improve attribution and critical-path isolation but are not independently claimed as runtime latency reductions without a stable repeated benchmark.

An observational, versioned cross-tier latency catalog records route-family hypotheses, first-status/TTFT/completion budget hypotheses, and quality/safety gates. It does not control routing. No per-language latency target or hardcoded route threshold was enabled.

## Measured proof and quality preservation

The final cache-disabled benchmark used the queued `/api/chat` fixture. Every route sample had `cache_mode=disabled`, `cache_hit=false`, and a non-cache route decision. The `Namaste Guruji` greeting had three included samples with **2.33 ms backend mean** and **316.87 ms wall mean**; all three used `instant_greeting`, remained `CASUAL` and abstained, and showed no provider call. This is the cache-disabled replacement for the earlier warm-shared single-sample proof.

The 20-sample distress percentile control remains retained separately as warm-shared evidence and is **not used here**, because this report now restricts latency metrics to cache-disabled runs. No cache-disabled route currently has the minimum 20 included samples required for p50/p95 reporting.

Groundedness, citations, abstention, and safety were preserved in the route matrix. Hindi and Telugu misses continued to return grounded-partial or abstained envelopes with `citations_verified=true` where recorded. The fast greeting remained abstained rather than being mislabeled as a grounded teaching answer. The implementation did not make an ungrounded answer appear faithful merely to reduce latency.

## Validation matrix

| Validation | Result | Interpretation |
|---|---|---|
| Focused cache-disabled/cache/pipeline/routing/provider/greeting tests | **32 passed** | Cache bypass, cache exclusion, trace privacy, route reuse, provider instrumentation, and greeting safety regressions pass |
| Complete backend suite after final latency-lane changes | **2,468 passed, 30 skipped, 1 warning in 525.53 s** | Final backend tree is green; warning is the existing test-environment `langchain_text_splitters` stub warning |
| Frontend Vitest from this continuation’s validated baseline | **522 passed, 6 skipped across 90 files** | Backend internal metadata and latency changes did not alter client contracts |
| Frontend production build | **Passed; 28 routes prerendered** | Client release build remains valid |
| Safe Chromium smoke/progressive-anonymous/accessibility suite | **34 passed** | Public pages, anonymous flow, accessibility checks, and browser transport remained green |
| New focused planner/queue/provider-policy tests | **13 passed** | Soft planner cancellation, queue attribution, streaming labels, privacy, and opt-in provider preferences pass |
| Python compilation and diff whitespace | **Passed** | Edited Python modules compile; patch has no whitespace errors |
| Local runtime after final provider-policy revert | Cache-disabled flag restored; provider-sort experiment disabled | The provider experiment produced no valid samples and is not used as performance evidence; runtime readiness must be rechecked before another benchmark |
| Final `/api/health` | Last stable response was HTTP 200 with `ready=false`, `status=unhealthy` | Release blocker remains the absent required `okf_compiled` artifact; it was not fabricated |

The final health payload otherwise reported healthy Qdrant, Redis, Neo4j, LLM, embedding, graph warm-up, queue, backpressure, LightRAG, and OCR checks. The missing curated artifact is independent of the latency changes and must be resolved through the approved corpus/artifact process before release readiness can be claimed.

## Parameter and optimization decisions

The accompanying `cross_tier_parameter_inventory_2026-08-26.md` separates code defaults from Compose/runtime values and records latency impact, quality risk, and measurement requirements. The principal decision was **not** to lower every timeout, top-k, reranker cutoff, rewrite cap, verification gate, or model-output ceiling. Those parameters affect evidence recall, citation support, abstention correctness, safety, or long-answer completeness and require held-out evaluation.

The next optimization seam remains provider and graph attribution: classify time into queue wait, provider dispatch, TTFT, output decode, retries, graph-internal waits, retrieval expansion, reranking backend work, verification, translation, and cache update. The new queue attribution and provider timing fields make that decomposition possible without content capture. Only then should a trace-driven route catalog choose optional RAG work by predicted marginal evidence utility, predicted latency/cost, and remaining deadline headroom. A safe fallback must enforce grounding, citation, abstention, safety, privacy, and tenant-isolation floors. This follows the general evidence pattern in latency-aware provider routing, predicted-latency scheduling, adaptive reranking, and cost-aware RAG research, but none of those external percentages are treated as AskMukthiGuru results [1] [2] [3] [4] [5] [6].

## Research and tooling limitations

OpenRouter’s official documentation supports rolling latency/throughput preferences and explains the distinction between TTFT, provider queueing, prefill, and output decode [1] [2]. Its prompt-caching documentation supports sticky provider/session strategies and stable prefixes, but cache-read/write and TTFT need AskMukthiGuru-specific experiments before adoption [3]. llm-d’s predicted-latency scheduling work supports an online-regressor direction using queue depth, running requests, cache state, and token features, but its reported improvements are not transferable to this stack [4]. Qdrant’s hybrid and late-interaction guidance, ICTIR adaptive reranking, and cost-aware RAG research support conditional escalation only after held-out quality labels [5] [6].

LangGraph’s documentation reinforces explicit private state and public output schemas, particularly because full values streaming can expose private channels [7]. OpenTelemetry’s current GenAI registry supports internal dimensions for operation, provider, model, tokens, cache usage, finish reasons, and first-chunk timing [8]. OWASP’s prompt-injection guidance supports retaining layered input/output checks and treating retrieved content as untrusted data; it also notes that deeper guardrails add latency and should be risk-adaptive rather than removed [9].

The requested external avenues were exercised and recorded honestly. SimilarWeb calls for the relevant competitor domains returned insufficient-credit failures, so no traffic, engagement, ranking, or channel conclusions are drawn. Internet Skill Finder’s live GitHub extraction failed for all configured sources and fell back to cache without importing a skill. The YouTube vLLM Office Hours page was opened, but captions were unavailable and the deeper analyzer call failed for insufficient credits; only primary documentation was used for technical claims. The broad GitHub gem sweep was constrained by the attached environment’s unavailable/insufficient CLI path, so verified web/GitHub pages were used rather than inventing repository evidence.

## Release and repository status

No production deployment, PR, force push, reset, rebase, corpus mutation, global Redis flush, or missing-artifact fabrication was performed. No new commit or push was made in this continuation because explicit authorization to publish these new local changes was not renewed. The working tree contains the implementation, tests, research ledger, benchmark samples, summaries, and this report for review.

## References

[1]: https://openrouter.ai/docs/guides/best-practices/latency-and-performance "OpenRouter latency and performance"

[2]: https://openrouter.ai/docs/guides/routing/provider-selection "OpenRouter provider selection"

[3]: https://openrouter.ai/docs/guides/best-practices/prompt-caching "OpenRouter prompt caching"

[4]: https://llm-d.ai/blog/predicted-latency-based-scheduling-for-llms "Predicted-latency-based scheduling for LLMs"

[5]: https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/ "Qdrant hybrid search and reranking"

[6]: https://arxiv.org/html/2606.25249v1 "Adaptive Re-Ranking with Utility-Based Routing"

[7]: https://docs.langchain.com/oss/python/langgraph/graph-api "LangGraph Graph API"

[8]: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/ "OpenTelemetry GenAI semantic-convention registry"

[9]: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html "OWASP LLM Prompt Injection Prevention Cheat Sheet"


## Question-bank all-tier cache-free benchmark

A reusable manifest builder flattened the repository’s authoritative `backend/benchmarks/question_bank.py` into **420 cases across 35 source categories**, including nested multi-turn scenarios. Manifest source SHA-256: `1adf9d547ffd9ca33c20b63ef57b8291f2938ca138a25028620fd2d06a34f8f6`.

The first single-client wave executed all 420 cases with application caches disabled. It produced 185 valid rows before a near-immediate HTTP-error regime. A retry wave covered the 235 previously failed cases; it recovered most categories and exposed 21 HTTP 429 responses, one HTTP 422, one incomplete job, and one ambiguous cache signal. The merged evidence contains **420 unique cases, 396 included cache-free rows, and 106 quality-valid rows**. The 24 exclusions remain visible and are not converted to latency values.

| Observed public query tier | Included cache-free | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms | Wall mean ms | Wall p50 ms | Wall p95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `fast` | 14 | 11 | 6,469.93 | — | — | 6,792.57 | — | — |
| `tier2_simple` | 282 | 50 | 4,397.33 | 3,134.00 | 13,375.60 | 4,708.94 | 3,609.07 | 13,511.30 |
| `standard` | 21 | 11 | 18,754.57 | 18,658.00 | 33,567.00 | 19,072.71 | 18,969.19 | 33,672.54 |
| `tier3_complex` | 48 | 6 | 22,885.60 | 21,821.00 | 40,836.45 | 23,191.91 | 22,203.69 | 41,114.98 |

The observed-tier table is not an expected-tier table. The source bank lacks complete reviewed expected-route labels; many categories resolve to `tier2_simple`, while complex categories also resolve to `tier3_complex` and `standard`. Route-specific optimization claims require reviewed route labels or a route-discovery benchmark.

| Benchmark stratum | Included cache-free | Quality-valid | Backend mean ms | Backend p50 ms | Backend p95 ms |
|---|---:|---:|---:|---:|---:|
| `in_corpus_doctrine` | 140 | 0 | 4,316.70 | 2,962.00 | 13,000.40 |
| `general_qa` | 80 | 30 | 10,758.70 | 17,499.00 | 34,776.50 |
| `multilingual` | 38 | 1 | 9,784.39 | 5,938.50 | 30,720.05 |
| `safety_distress` | 36 | 30 | 4,047.53 | 3,264.50 | 9,552.25 |
| `safety_governance` | 33 | 12 | 7,712.64 | 1,733.00 | 26,947.80 |
| `conversation_followup` | 16 | 6 | 5,264.12 | — | — |
| `privacy_injection` | 11 | 8 | 13,990.36 | — | — |
| `stress_context` | 10 | 0 | 9,512.40 | — | — |
| `robustness_boundaries` | 13 | 13 | 7,898.69 | — | — |
| `grounding_citation` | 15 | 3 | 2,775.08 | — | — |
| `temporal_out_of_corpus` | 4 | 2 | 5,202.75 | — | — |

The overall merged cache-free mean is **7,129.41 ms backend** and **7,457.22 ms wall**, with overall p50 **3,399.50 ms backend** / **3,645.24 ms wall** and p95 **26,622.75 ms backend** / **26,996.39 ms wall**. These overall percentiles meet the 20-sample rule but represent a mixed workload distribution, not a tier SLO.

Quality and safety are separate gates from latency. The merged included set has a **26.77% quality-valid rate** under required-term, citation, rejected-term, expected-intent, safety, and public-contract checks. Safety-distress rows were 30/36 quality-valid. All scanned included rows had empty `banned_public_keys`; no public-field violation was recorded. Many doctrinal and multilingual rows remained quality-invalid because the local runtime returned grounded partials or abstentions that did not satisfy exact bank terms; this is a quality/evidence finding, not a reason to weaken grounding or abstention.

The detailed all-tier report and chart are `audit_work/question_bank_latency_merged_v1.md` and `audit_work/question_bank_latency_merged_v1.png`. Bounded raw rows are `question_bank_latency_full_v2.jsonl` and `question_bank_latency_retry_v1.jsonl`. Late HTTP errors and 429s are reliability evidence only.
