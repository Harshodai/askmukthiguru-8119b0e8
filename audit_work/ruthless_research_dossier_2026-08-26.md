# AskMukthiGuru Ruthless Research Dossier

**Date:** 26 August 2026  
**Author:** Manus AI  
**Scope:** Current AskMukthiGuru checkout, attached audit recommendations, provider and serving research, adaptive RAG, observability, safety, open-source projects, competitor patterns, YouTube, Internet Skill Finder, and SimilarWeb.

## Executive conclusion

The attached audit is directionally correct about the central risk: AskMukthiGuru is feature-rich and safety-conscious, but the largest remaining latency and release risks are operational and architectural rather than a missing isolated algorithm. The current checkout has already absorbed several prior fixes and the latest local advanced pass added eventual healing-course side effects plus a privacy-safe pipeline stage ledger. The repository is synchronized at `HEAD == origin/main == 771b507d`; the advanced-pass source and evidence remain local and uncommitted.

The next step should **not** be another collection of language-specific bypasses, query regexes, or fixed magic thresholds. The best advanced direction is a **trace-driven adaptive cascade** over the existing LangGraph and provider gateway. Each optional action—HyDE, decomposition, rewrite, reranking, verification depth, model choice, and provider choice—becomes a route with measured latency, token/cost, evidence gain, quality floor, and failure behavior. A lightweight policy selects a route using current evidence and remaining deadline. It starts in shadow mode, is calibrated on held-out multilingual data, and only then controls production routing.

This approach directly addresses the user’s request to reduce latency through advanced methods rather than hardcoding. It also preserves the repository’s non-negotiable properties: groundedness, citation integrity, abstention, safety order, tenant isolation, privacy, and browser SSE public projections.

## 1. Differences between the attachment and the current checkout

| Attachment finding or recommendation | Current state after subsequent work | Difference / interpretation |
| --- | --- | --- |
| Local branch was at `3d901071`; origin was `708ece6a` | Current `HEAD` and `origin/main` are both `771b507d` | The attachment’s source-integrity snapshot is stale. Current branch synchronization is closed, but the worktree contains local uncommitted advanced changes. |
| Health reports `ready=false` because `okf_compiled` is missing | Still a release blocker; no placeholder artifact was created | This finding remains current and must be fixed in the production image/CI, not bypassed in health code. |
| Browser chat showed an authentication failure in persisted state | One-time anonymous-token refresh/retry was implemented and tested in the prior pass | The defect is partially remediated in source. A clean-storage browser journey and intentionally expired-token journey still need a release proof against `ready=true`. |
| One-sample substantive chat tails were roughly 15–30 seconds | Newer warm/uncached evidence measured English simple around 6.1 seconds, comparison around 24.1 seconds, and Hindi around 30.0 seconds; the prior treatment reduced Hindi to 18.1 seconds | Historical numbers should not be mixed with newer runs. None are p50/p95. The improvement is real only for the matched Hindi experiment and must not be generalized to all traffic. |
| Wisdom Map required manual example fallback | The attachment’s manual-fallback observation remains relevant unless the current frontend has separately added automatic bounded fallback proof | This should be closed with a fetch timeout, transparent “example data” label, retry, and an E2E test. |
| Stage timing was under-instrumented | A reusable relative stage ledger and bounded internal span projection were added locally | This gap is materially improved, but production export/alerting and GenAI semantic field parity remain to be proven. |
| Healing-course assignment was on the first-response path | It was moved to an observed background side effect locally, retaining feature flag, timeout, tenant boundary, and error handling | This is a generic dependency/critical-path optimization, not a query hardcode. It still needs runtime proof under a stable rebuilt backend. |
| Indic HyDE and rewrite behavior was expensive | An explicit configurable Indic policy was added locally: HyDE opt-in for Indic requests and rewrite cap of one, while preserving global settings for other traffic | This is a useful measured treatment, but it remains a policy specialization. The long-term replacement is a learned/trace-driven route utility policy. |
| Recommended external components included Ragas, Langfuse, Promptfoo, OpenLLMetry, Phoenix, Haystack, Presidio, and model routers | Research found selective fit, but no reason to rewrite the current LangGraph/OpenRouter stack | Adopt components only when they close a measured gap: Ragas/Phoenix or Langfuse for offline evaluation and visualization; no parallel orchestrator or duplicate gateway. |
| SimilarWeb and YouTube were proposed as evidence paths | SimilarWeb calls were blocked by insufficient credits; the relevant YouTube page had no captions and video analysis was blocked by insufficient credits | No traffic, ranking, popularity, or detailed video claims are valid evidence in this pass. |

## 2. Measured bottleneck interpretation

The latest evidence points away from ordinary vector retrieval as the first optimization target. English retrieval was approximately 13–221 ms in the recorded samples, while the comparison path spent about 2.25 seconds in reranking, 7.45 seconds in generation, and 5.22 seconds in verification. The Hindi path paid approximately 1.16 seconds for intent routing, 2.04 seconds for decomposition, 4.43 seconds for HyDE, 0.90 seconds for retrieval, 1.12 seconds for reranking, 1.73 seconds for document grading, 4.49 seconds for rewrite, and 4.63 seconds for generation. These are n=1 class samples, not percentile estimates.

The correct optimization objective is therefore not “make every query use the cheapest path.” It is **maximize grounded answer utility subject to a deadline and safety floor**. A route that removes a verification step but promotes unsupported generated text is a regression even if wall time falls. A route that returns deterministic source excerpts with `grounding_state=abstained` can be valid, but it must remain explicitly labeled as non-generated evidence.

## 3. Research findings by method

| Method | Verified evidence | Fit to AskMukthiGuru | Recommendation |
| --- | --- | --- | --- |
| OpenRouter rolling latency/throughput preferences | OpenRouter documents percentile-based provider preferences and global multi-model sorting, while warning that preferences are not guarantees [1] [2] | Directly applicable to the current hosted-provider path if provider, TTFT, output tokens, cost, retries, and residency are logged | **P1 shadow experiment**, then controlled rollout if quality/cost/fallback gates pass |
| Provider prompt caching | OpenRouter documents sticky provider/session routing, byte-identical stable prefixes, dynamic content at the end, and cache read/write metadata [3] | Applicable to stable system/corpus prefixes; helps prefill/TTFT, not long output decode | **P1 experiment** only after prompt token and cache-hit telemetry is complete |
| Adaptive model routing | RouteLLM provides calibrated strong/weak model routing and evaluation, but its results depend on model pair and data distribution; it performed poorly out-of-domain until augmented [4] [5] | Useful design reference; AskMukthiGuru needs its own multilingual spiritual preference/faithfulness labels | **P2 shadow router**, do not import pretrained thresholds blindly |
| LiteLLM adaptive router | Current docs describe quality/cost bandit-style routing with Postgres state and minimum quality tiers, but explicitly list no latency scoring, English-biased regex signals, capped observations, and no decay [6] | Limitations conflict with multilingual, latency-first requirements | **Do not adopt as-is** |
| Trace-driven predicted latency | llm-d describes online sliding-window regressors for TTFT/TPOT using request and server state, with SLO headroom and learned trade-offs instead of fixed weights [7] | Strong conceptual fit for provider/route selection; self-hosted serving is not current deployment | **P1 architecture target**; start with shadow predictions over current provider metadata |
| Self-hosted vLLM/llm-d/SGLang | vLLM documents continuous batching, prefix caching, speculative decoding, and experimental prefill/decode disaggregation; llm-d adds prefix-aware routing, KV management, autoscaling, and flow control; SGLang documents radix prefix reuse [8] [9] [10] | Only applies if AskMukthiGuru later operates compatible models/GPU pools | **P3 infrastructure track**, not a current application fix |
| Adaptive reranking | ICTIR 2026 proposes utility labels over no/light/heavy rerank and reports large latency reductions with quality trade-offs; it also reports limited router generalization and nontrivial training [11] | Directly targets the measured 2.25-second comparison reranker tail | **P1 shadow cascade** using existing reranker choices and held-out nDCG/citation labels |
| Cost-aware retrieval depth | CA-RAG frames routing over a fixed bundle catalog with explicit quality, latency, and token cost; its benchmark is only 28 queries [12] | Transparent catalog design fits; benchmark size means no production claim | **P1 route catalog design**, not paper-number adoption |
| RAG-aware model routing | RAGRouter incorporates retrieved-document representations into model routing and reports efficiency trade-offs [13] | Potentially useful after retrieval, but requires training data and adds model complexity | **P3 research**, after simpler evidence features are exhausted |
| Late-interaction/ColBERT reranking | Qdrant documents dense+sparse retrieval followed by late-interaction reranking over a small candidate set [14] | Could improve retrieval quality or replace current heavy path if corpus and model support are proven | **P2 experiment** only after current reranker profiling and corpus quality labels |
| Prompt compression | LLMLingua offers prompt/KV compression; a 2026 study found up to 18% end-to-end speed-up only in a matched operating window and otherwise compression overhead can erase gains [15] [16] | Risk of removing citation qualifiers, safety instructions, or Indic meaning; current generation tail is not proven prefill-dominated | **Defer** until prompt-token/TTFT ledger proves break-even |
| DSPy/GEPA | Official docs describe metric-feedback optimization of prompts/programs through iterative scoring [17] | Good for non-safety-critical formatting or retrieval-explanation prompts | **P2 offline optimization**, never auto-rewrite safety/provenance rules |
| LangGraph graph-native parallelism | Official docs support conditional edges, private/internal state, graph-wide timeouts/retries, typed streaming, and explicit warning that private values can leak through full-state streams [18] [19] [20] | Current stack already uses LangGraph; patterns fit without adding another orchestrator | **Adopt patterns in place** |
| Ragas | Current repository and docs provide faithfulness, relevance, testset, and feedback-loop evaluation [21] [22] | Strong fit for offline/holdout evaluation, not production inline calls | **P1 evaluation harness** |
| Phoenix/Langfuse/OTel | Phoenix supports OTEL traces, RAG evaluation, datasets, experiments, and OpenRouter/LangGraph integrations; Langfuse supports async traces, scores, datasets, and experiments; OTel GenAI conventions cover model/provider/tokens/cache/TTFT/retrieval/evaluation dimensions [23] [24] [25] | Current internal ledger should become schema-compatible while preserving redaction | **P1 schema alignment; optional platform integration later** |
| Risk-adaptive safety | OWASP recommends structured instruction/data separation, input/output monitoring, remote-content sanitization, least privilege, and model-based defense in depth, while warning guardrails add latency and are not sufficient alone [26] | Fits the existing safety-first graph and supports targeted deeper checks only for risky paths | **Adopt policy architecture; never remove safety to win latency** |

## 4. What “advanced rather than hardcoded” should mean in this repository

A hardcoded optimization says: “if Hindi, skip HyDE,” “if this exact comparison wording, bypass decomposition,” or “if score is below this manually chosen number, use route X.” Those can be useful temporary experiments, but they encode no adaptation, no uncertainty, and no feedback.

An advanced policy should instead use a **versioned route catalog**. Each route declares its capabilities and constraints: expected evidence coverage, latency distribution, token/cost estimate, provider/model, safety checks, failure fallback, and minimum quality tier. Request features are privacy-safe and operational: language family, query length bucket, turn count, retrieval score distribution, evidence coverage, candidate entropy, source freshness, risk class, current queue/route state, and remaining deadline. The policy predicts the marginal utility of each optional stage and selects the cheapest route that satisfies the quality floor and deadline headroom.

The policy should be learned or calibrated from actual AskMukthiGuru traces, not from generic Arena or MMLU alone. Start with shadow decisions and counterfactual replay. Use a conservative safe default whenever the policy is uncertain, missing features, out of distribution, or below a minimum sample count. Use rolling windows or decay so provider and workload changes are learned. Keep exploration bounded and never explore by relaxing safety, tenant, citation, or abstention rules.

## 5. Ranked implementation roadmap

### P0 — release integrity before latency claims

Package the real `okf_compiled` artifact in the exact production image and make the build fail if it is absent. Add a CI assertion for required runtime artifacts. Reconcile source SHA, deployed SHA, image digest, runtime artifact manifest, and health payload in one release record. Until `/api/health` returns `ready=true`, treat live latency numbers as local engineering evidence only.

### P1 — build the adaptive measurement substrate

Extend the current internal stage ledger to emit a stable, redacted schema compatible with current GenAI conventions: workflow, operation, stage, provider, requested/actual model, request and response token counts, cache read/write counts, finish reason, TTFT/first chunk, queue wait, retrieval data source, reranker route, verification route, fallback route, quality scores, and evaluation version. Do not capture prompts, raw answers, memory, private state, or source payloads by default.

Add a held-out multilingual evaluation set covering English and supported Indic languages, simple definitions, comparisons, multi-hop questions, reflective meaning, no-evidence cases, and safety/adversarial cases. Evaluate retrieval recall/precision, citation precision, claim support, faithfulness, abstention correctness, answer relevance, safety decisions, queue abandonment, TTFT, completion latency, token/cost, and error/retry rates.

### P1 — shadow adaptive cascade

Define route bundles using existing components: direct/cheap retrieval, dense retrieval, hybrid retrieval, light rerank, heavy rerank, HyDE, decomposition, one rewrite, deeper verification, and provider alternatives. Run the router in shadow mode first. Log the route it would choose, the actual route, and offline counterfactual quality/latency where replay is possible.

Train a simple calibrated model first—logistic regression, gradient-boosted trees, or isotonic calibration—using measured labels. Labels should encode “best route under quality floor and deadline,” not just “fastest.” Include an abstention/uncertainty option. Compare against the current policy and require non-inferiority on faithfulness, citation support, safety recall, and abstention correctness before enabling control.

### P1 — predicted provider/route latency

For each provider/model/route, maintain rolling estimates of queue wait, TTFT, output tokens per second, error rate, retry cost, and cost. Predict completion time from request shape and current conditions. Select provider/route by SLO headroom, policy constraints, quality floor, and cost. Use OpenRouter’s percentile preferences only as a provider-side experiment, not as a substitute for application telemetry.

### P2 — adaptive reranking and verification

Use post-retrieval evidence signals to decide whether reranking is worth its measured cost. If the initial evidence has high coverage and low ambiguity, a light route may suffice. If evidence is conflicting, low-score, or multi-hop, escalate. Verification depth should depend on risk and evidence uncertainty; the output contract must ensure that rejected generations cannot be promoted as teachings. Compare no/light/heavy routes with claim-level and citation-level labels.

### P2 — prompt/prefix optimization

Reorder prompts so stable system/provenance instructions and immutable corpus framing come first, with dynamic query, memory, and retrieved passages later. Measure provider cache reads/writes and TTFT. Only test LLMLingua-style context compression on a separable retrieved-context block after a measured break-even analysis and source-support reconstruction test. Never compress safety or provenance instructions.

### P3 — self-hosted inference track

If volume, cost, or residency justifies it, benchmark a compatible open model behind vLLM or SGLang. Measure continuous batching, prefix caching, speculative decoding, predicted-latency scheduling, and prefill/decode disaggregation independently. This requires infrastructure, GPU economics, model-quality equivalence, multilingual tests, and rollback capacity; it should not be conflated with application-level RAG changes.

## 6. Safety and privacy boundaries

Latency work must not remove safety stages, lower faithfulness thresholds, route untrusted retrieved text into privileged instructions, expose private graph state through streaming, or use global cache flushes as a policy fix. Risk-adaptive safety means **more** checking where the request or evidence is risky and cheaper deterministic checking for routine traffic—not a universal bypass.

The repository should maintain explicit public output schemas and allowlists. LangGraph documentation warns that private state can still appear in full values streams, so browser SSE must continue to use the project’s own public projection rather than forwarding graph state. Observability platforms should receive redacted attributes and hashed identifiers unless a deliberate data-governance review approves more.

## 7. Research limitations

The Internet Skill Finder was run online for adaptive RAG/LLM latency/observability routing. GitHub JSON extraction failed for all configured repositories and the tool fell back to cache with no actionable result. No external skill was imported.

SimilarWeb calls were attempted for `nithyananda.ai`, `askthegita.ai`, `askgita.ai`, `headspace.com`, and `askmukthiguru.com` for visits, bounce rate, and traffic sources. All calls were stopped before provider execution because the current user has insufficient credits. No traffic or ranking conclusions are valid.

The vLLM Office Hours #32 YouTube page was opened. It showed a 1:01:01 video with captions unavailable. Deeper analysis failed because the analyzer reported insufficient credits. No detailed claims are attributed to that video.

Most academic and vendor numbers in this dossier are source-reported results on other datasets, hardware, models, or traffic. They motivate experiments but are not AskMukthiGuru performance claims. AskMukthiGuru’s latency samples remain small and local until a stable `ready=true` environment supports repeated p50/p95 measurement.

## References

[1]: https://openrouter.ai/docs/guides/best-practices/latency-and-performance "OpenRouter latency and performance"

[2]: https://openrouter.ai/docs/guides/routing/provider-selection "OpenRouter provider selection"

[3]: https://openrouter.ai/docs/guides/best-practices/prompt-caching "OpenRouter prompt caching"

[4]: https://github.com/lm-sys/RouteLLM "RouteLLM repository"

[5]: https://www.lmsys.org/blog/2024-07-01-routellm/ "RouteLLM research article"

[6]: https://docs.litellm.ai/docs/adaptive_router "LiteLLM adaptive router"

[7]: https://llm-d.ai/blog/predicted-latency-based-scheduling-for-llms "llm-d predicted-latency scheduling"

[8]: https://docs.vllm.ai/en/latest/features/disagg_prefill/ "vLLM disaggregated prefilling"

[9]: https://docs.vllm.ai/en/latest/deployment/integrations/llm-d/ "vLLM llm-d integration"

[10]: https://sgl-project-sglang-93.mintlify.app/concepts/radix-attention "SGLang RadixAttention"

[11]: https://arxiv.org/html/2606.25249v1 "Adaptive Re-Ranking, ICTIR 2026"

[12]: https://www.mdpi.com/2673-2688/7/7/250 "Cost-Aware Query Routing in RAG"

[13]: https://arxiv.org/abs/2505.23052 "RAGRouter"

[14]: https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/ "Qdrant hybrid search and reranking"

[15]: https://github.com/microsoft/LLMLingua "Microsoft LLMLingua repository"

[16]: https://arxiv.org/abs/2604.02985 "Prompt Compression in the Wild"

[17]: https://dspy.ai/getting-started/gepa-optimization/ "DSPy GEPA optimization"

[18]: https://docs.langchain.com/oss/python/langgraph/graph-api "LangGraph Graph API"

[19]: https://docs.langchain.com/oss/python/langgraph/fault-tolerance "LangGraph fault tolerance"

[20]: https://docs.langchain.com/oss/python/langgraph/streaming "LangGraph streaming"

[21]: https://github.com/vibrantlabsai/ragas "Ragas repository"

[22]: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ "Ragas faithfulness"

[23]: https://github.com/Arize-ai/phoenix "Phoenix repository"

[24]: https://langfuse.com/docs/observability/overview "Langfuse observability"

[25]: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/ "OpenTelemetry GenAI attributes"

[26]: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html "OWASP LLM prompt-injection prevention"

## Supporting local evidence

- `audit_work/latency_final_report.md`
- `audit_work/advanced_methods_research.md`
- `audit_work/recommendation_reconciliation.md`
- `audit_work/ruthless_web_research_2026-08-26.md`
- `audit_work/final_advanced_methods_snapshot.txt`
- `audit_work/final_validation_snapshot.txt`
