# Ruthless web research ledger — 2026-08-26

## Measured AskMukthiGuru questions

The latest local evidence shows ordinary English retrieval is not the first target: English simple backend latency was about 6.1s with retrieval about 221ms; English comparison was about 24.1s with rerank about 2.25s, generation about 7.45s, and verification about 5.22s; Hindi was about 30.0s with model-backed intent/decomposition/HyDE/rewrite/generation tails. The research questions are therefore: how to lower provider queue/TTFT and decode tails; how to route optional RAG work using observed utility and cost; how to reduce reranker/verification tail without weakening groundedness; how to reuse stable prefixes safely; and how to prove improvements with held-out multilingual and safety evaluation.

## OpenRouter latency and routing

OpenRouter’s official latency guide separates total latency into TTFT (network, provider queue, prompt prefill) plus output tokens divided by generation throughput. It documents rolling five-minute percentile preferences such as `preferred_max_latency` and `preferred_min_throughput`, and explains that these preferences reorder preferred providers rather than guaranteeing a threshold. It also documents a multi-model `partition: none` strategy that globally sorts endpoints by throughput or latency instead of exhausting the primary model group first. Source: https://openrouter.ai/docs/guides/best-practices/latency-and-performance.

OpenRouter’s provider-selection documentation says default routing considers recent outages and price, while explicit sorting by latency/throughput disables normal load balancing. It documents `preferred_min_throughput`, `preferred_max_latency`, percentile cutoffs, and the warning that thresholds are preferences rather than hard guarantees. Source: https://openrouter.ai/docs/guides/routing/provider-selection.

Applicability: AskMukthiGuru currently sends provider preferences through `openrouter_service.py` but should not blindly set explicit ordering or throughput thresholds. First add per-call TTFT, output token count, retry, provider, and finish-reason telemetry; then test provider preference policies against quality, cost, and fallback reliability. OpenRouter’s percentile routing is a strong non-hardcoded candidate because it uses rolling provider measurements, but the app must preserve data residency/provider policy constraints.

## OpenRouter prompt caching

OpenRouter’s current prompt-caching documentation states that provider sticky routing can preserve a cache-warm provider for subsequent requests, that a consistent `session_id` can be used as the sticky key, and that stable prompt prefixes should be kept byte-identical while dynamic content is placed later. It reports cache reads and writes in usage details such as `cached_tokens` and `cache_write_tokens`. Gemini 2.5+ supports implicit caching subject to model-specific minimum prompt sizes; explicit cache breakpoints are recommended for large RAG content. Source: https://openrouter.ai/docs/guides/best-practices/prompt-caching.

Applicability: AskMukthiGuru already tracks cached tokens and sends Anthropic-style cache controls for Anthropic models. The active Gemini path needs a gateway-specific experiment with stable system/corpus prefix placement, `session_id` propagation where policy permits, cache-read/write telemetry, TTFT, and output-decode separation. Prompt caching should not be described as a fix for long decode tails.

## vLLM serving architecture

The official vLLM anatomy article describes paged attention, continuous batching, chunked prefill, prefix caching, guided decoding, speculative decoding, disaggregated prefill/decode, and trace-driven latency/throughput benchmarking. It explains that prefill is often compute-bound while decode is memory-bandwidth-bound, and that continuous batching mixes new prefills with existing decodes. Prefix caching avoids recomputing shared prompt prefixes and helps prefill, but not output decode. Chunked prefill prevents a long prompt from monopolizing an engine step. Source: https://vllm.ai/blog/2025-09-05-anatomy-of-vllm.

Applicability: vLLM is a later serving-layer experiment only if AskMukthiGuru self-hosts a compatible model on suitable GPU infrastructure. It is not an immediate fix for the current OpenRouter/Gemini path. The reusable immediate lesson is to benchmark TTFT, inter-token latency, queue wait, and throughput separately, and to avoid mixing serving-engine changes with RAG quality changes.

## Adaptive RAG and reranking research leads

Search results surfaced an empirical Adaptive Re-Ranking paper, a cost-aware query-routing study, Qdrant’s official hybrid-search/late-interaction reranking tutorial, and recent adaptive-RAG papers. The useful recurring pattern is conditional escalation: start with a cheap retrieval path, inspect evidence confidence/coverage, and spend more compute only when expected evidence gain justifies it. This must be measured against held-out faithfulness/citation/abstention, not assumed.

Search results also surfaced `Ragas` for faithfulness/relevance evaluation, Qdrant late-interaction reranking, and cost-aware routing literature. These are research candidates until primary pages and current repository maintenance are checked; snippets alone are not evidence.

## Primary RAG sources verified

Qdrant’s official hybrid-search tutorial recommends broad dense+sparse retrieval followed by late-interaction reranking on a small candidate set. It presents dense embeddings for semantic recall, BM25-style sparse retrieval for keyword precision, and ColBERT-style multi-vector late interaction for nuanced reranking. The tutorial disables HNSW for the late-interaction multivector because it is used for reranking rather than ANN retrieval. Source: https://qdrant.tech/documentation/tutorials-basics/reranking-hybrid-search/.

The 2026 ICTIR Adaptive Re-Ranking paper proposes utility-based per-query routing among no reranker, light reranker, and heavy reranker. Its abstract reports large potential latency reductions but also shows that learned routing is non-trivial and can trade nDCG against speed. The paper reports that approximately 40% of queries in its training analysis saw no reranking benefit and only 11% benefited from the heavy reranker over lighter choices, but these are the paper’s datasets and must not be generalized to AskMukthiGuru without evaluation. It recommends utility labels that combine effectiveness and measured latency and emphasizes held-out test data. Source: https://arxiv.org/html/2606.25249v1; code link in paper: https://github.com/emirkaan5/adaptive-reranker.

The 2026 MDPI Cost-Aware Query Routing in RAG paper frames retrieval-depth choice as a transparent utility optimization over expected answer quality, latency, and token cost. Its study uses 28 queries and reports 26% fewer billed tokens versus always-heavy retrieval and 34% lower response time versus always-direct answering while maintaining reported quality parity; the small benchmark means this is a design reference, not a production guarantee. Source: https://www.mdpi.com/2673-2688/7/7/250.

Ragas’ current faithfulness documentation defines faithfulness as supported claims divided by total answer claims, ranging from 0 to 1, and provides a collections-based API plus an efficient HHEM-2.1-Open classifier option. This directly fits AskMukthiGuru’s fail-closed groundedness and abstention gates, but LLM-judge/classifier scores must be calibrated against expert labels and cannot replace safety policy. Source: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/.

## Adoption conclusion

The best immediate advanced candidate is not replacing Qdrant or adding a large RAG framework. It is a constrained adaptive cascade over existing components: cheap retrieval and deterministic evidence signals first; reranking/HyDE/rewrite/verification escalation only when predicted marginal evidence gain exceeds predicted latency/cost under the remaining deadline. The router must run in shadow mode first, use held-out multilingual data, and record per-query decisions and counterfactual route outcomes. Qdrant late interaction is a later candidate only if current reranker profiling shows the current cross-encoder/ONNX path is the dominant cost and quality labels prove a multivector path improves the relevant corpus.

## Observability, evaluation, and security sources verified

OpenTelemetry’s current GenAI registry says the GenAI semantic conventions have moved to the dedicated `semantic-conventions-genai` repository. The registry includes attributes for operation, provider, request/response model, request max tokens, stream, response finish reasons, time-to-first-chunk, retrieval data source, evaluation scores, workflow, input/output token usage, cache-read tokens, and cache-creation tokens. The registry also marks older attributes as moved/deprecated, so AskMukthiGuru should track the current repository rather than copying legacy names. Source: https://opentelemetry.io/docs/specs/semconv/registry/attributes/gen-ai/.

Langfuse’s current observability docs describe traces covering model calls, retrieval, tools, timings, token usage, costs, and evaluation scores, with asynchronous background batching intended not to affect application response time. Its RAG evaluation guide recommends evaluating retrieval components independently from the complete answer path, then running end-to-end correctness, faithfulness, groundedness, and relevance experiments on a consistent dataset. Sources: https://langfuse.com/docs/observability/overview and https://langfuse.com/blog/2025-10-28-rag-observability-and-evals.

OWASP’s current prompt-injection prevention cheat sheet separates direct injection, indirect/remote content injection, encoding/obfuscation, persistent multi-turn attacks, RAG poisoning, output leakage, and agent/tool manipulation. It recommends structured separation of instructions and data, input and output monitoring, remote-content sanitization, least privilege, comprehensive monitoring, and model-based guardrails as defense in depth. It also warns that guardrail models are themselves attackable and add latency, so higher-cost checks should be reserved for higher-risk paths. Source: https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html.

## Adoption conclusion

The observability work should use the existing `trace_spans` sink and add current GenAI-compatible dimensions as internal attributes: workflow, operation, provider, model, request/response token counts, cache read/write counts, finish reason, TTFT/first chunk, retrieval data source, and evaluation score. Raw input/output message capture should remain disabled by default because AskMukthiGuru’s privacy boundary excludes prompts, memory, raw answers, and arbitrary graph state from browser/public projections. Langfuse is a viable self-hosted or OTLP-compatible visualization/evaluation option, but it should be adopted only after the internal schema and redaction contract are stable.

For security, do not optimize by removing guardrails. Use risk-adaptive defense: deterministic cheap checks on routine input, deeper indirect-injection and output checks for retrieved/web content or tool/action paths, and strict permission validation independent of model output.

## Open-source candidate sweep

The current search surfaced `lm-sys/RouteLLM` for serving/evaluating model routers, LiteLLM’s beta adaptive router for request-type/model performance routing, Langfuse/Ragas integration for traced evaluations, and existing GPTCache/semantic-cache references. These are candidates, not automatic dependencies. The main fit risk is framework duplication: AskMukthiGuru already has an OpenRouter gateway, routing, coalescing, cache tiers, OTEL bootstrap, and evaluation metadata. Any adoption must be component-level and justified by a measured missing capability.

## Maintained open-source projects verified

`lm-sys/RouteLLM` is an Apache-2.0 repository with 5,399 stars and 175 commits on the retrieved page. It provides an OpenAI-compatible router/server, trained routers, threshold calibration, and benchmark evaluation. Its README claims up to 85% cost reduction while maintaining 95% GPT-4 performance on specified public benchmarks; these claims are not AskMukthiGuru evidence. It is primarily model-quality/cost routing, not retrieval-depth routing. Source: https://github.com/lm-sys/RouteLLM.

`vibrantlabsai/ragas` is Apache-2.0 with 15,468 stars, 1,147 commits, and current documentation for objective metrics, dataset/testset generation, integrations, and feedback loops. It is a strong candidate for offline evaluation infrastructure, not for inserting evaluator calls into the production critical path. Source: https://github.com/vibrantlabsai/ragas.

`Arize-ai/phoenix` is open-source with 11,193 stars and 9,742 commits on the retrieved page. Its README describes OpenTelemetry-based tracing, RAG/LLM evaluation, datasets, experiments, prompt management, and integrations for LangGraph, OpenRouter, LiteLLM, and OpenInference. It offers lightweight OTEL and evaluation client packages as well as a self-hosted platform. Source: https://github.com/Arize-ai/phoenix.

LiteLLM’s adaptive router documentation is explicitly marked beta. It stores quality estimates in Postgres, tracks request-type/model outcomes, balances quality and cost through weights, supports minimum quality tiers, and exposes router state. Its known limitations are important: latency is not scored, classification is regex-based and English-biased, observations are capped per cell without decay, and session stickiness can limit learning. Source: https://docs.litellm.ai/docs/adaptive_router.

## Adoption conclusion

RouteLLM is useful as a design reference for calibrated model routing but should not be inserted behind the existing OpenRouter gateway without proving model compatibility, quality labels, multilingual coverage, and added hop latency. LiteLLM adaptive routing is not a drop-in answer because its own documented limitations overlap AskMukthiGuru’s requirements. Ragas and Phoenix are the strongest selective candidates: Ragas for held-out evaluation and Phoenix/OpenInference for an optional OTLP visualization layer after privacy/redaction contracts are finalized. Existing internal telemetry should remain the source of truth until such integration is justified.

## Internet Skill Finder result

The online Internet Skill Finder was invoked for `adaptive RAG LLM latency observability routing`. The GitHub Connector path reported JSON extraction errors for all seven configured repositories and fell back to cache; the result contained no matching skill. This is a tooling limitation, not evidence that no relevant skills exist. No external skill was imported.

## Competitor source: Ask Nithyananda AI

The official page positions the product as a spiritual AI focused on preserving and decoding civilizational/scriptural knowledge. It exposes a direct web prompt, a “Try Ask Nithyananda” action, app download, and an “Other platforms” option. The page emphasizes source provenance and preservation rather than a generic wellness chatbot. Source: https://nithyananda.ai/.

Competitive implication for AskMukthiGuru: provenance and trust are product-level differentiators, not merely retrieval implementation details. AskMukthiGuru should make source-backed guidance, clear teaching attribution, citation quality, and fail-closed abstention visible in the experience while keeping the adaptive latency layer invisible and policy-constrained.

## Competitor source: AskTheGita.AI

The official page presents a focused, single-purpose experience: a Bhagavad Gita quote, a calm reflection framing, and a text field inviting the user to share a concern. Its promise is everyday guidance through dialogue, with the Gita as the stated source. Source: https://askthegita.ai/.

Competitive implication: a low-friction first-value flow and one clear source promise may be more important than exposing a complex feature menu. AskMukthiGuru can differentiate with a similarly simple entry while progressively revealing practices, source citations, multilingual support, and deeper personalization after the first useful response.

## Competitor source: Headspace Ebb

Headspace’s official Ebb page describes an empathetic AI companion for in-the-moment support, self-reflection, and personalized meditation/activity recommendations. It explicitly states that Ebb is not a therapist or clinical service, and describes privacy, security, and safety boundaries. Source: https://www.headspace.com/ai-mental-health-companion.

Headspace’s AI principles page describes a multi-model orchestration with safety-by-design guardrails, real-time risk identification, pre-release evaluation, red teaming, post-release tracking, and clinician review of deidentified high-acuity cases and random quality samples. It states that messages are classified across risk categories and that high-risk conversations are directed to crisis resources. Source: https://www.headspace.com/ai.

Competitive implication: the differentiator is not “an AI chat box”; it is a documented trust loop: clear scope, specialized safety detection, human/clinical review where appropriate, continuous evaluation, and personalized content recommendations. AskMukthiGuru can adapt the architecture pattern without copying clinical claims: classify spiritual/safety risk, preserve fail-closed routing, log privacy-safe evaluation outcomes, and recommend a practice only after a grounded answer or explicit safe fallback.

## Prompt optimization and cascades research leads

Search results surfaced DSPy/GEPA for metric-driven prompt optimization, FrugalGPT and RouteLLM for model cascades, and newer work on dynamic model routing/cascading. The relevant principle is to optimize a declarative pipeline against a measurable objective and route between known components under a quality/cost/latency constraint. This can replace months of manual prompt tuning, but optimizer outputs must be versioned, held out, red-teamed, and reviewed; they must not be applied directly to safety-critical prompts or source attribution without regression gates.

## Prompt optimization and model-cascade sources verified

DSPy’s official GEPA guide describes metric-driven prompt/program optimization: run a program on training examples, score outputs, send examples and feedback to a reflection model, propose instruction candidates, and keep the best-scoring candidates within a budget. It explicitly replaces manual prompt hand-tuning with an optimization loop. Source: https://dspy.ai/getting-started/gepa-optimization/.

Applicability: GEPA could optimize non-safety-critical response-format or retrieval-explanation prompts using held-out faithfulness/citation metrics. It must not directly rewrite safety policies, source-attribution rules, or abstention boundaries without human review and regression gates. Prompt versions should be immutable and released like code.

The RouteLLM primary article describes routing between stronger and weaker models using preference data, with routers including matrix-factorization, similarity-weighted ranking, BERT, and causal-LLM approaches. It reports strong results on MT Bench for its model pair, but also states that Arena-trained routers performed poorly on out-of-distribution MMLU until augmented with task-specific data. Source: https://www.lmsys.org/blog/2024-07-01-routellm/.

Applicability: this is strong evidence for calibration and distribution-shift testing, not permission to import a pretrained router. AskMukthiGuru’s multilingual spiritual corpus and fail-closed grounding objective differ from Arena preference data. A local router should be trained or calibrated on AskMukthiGuru traces and held-out multilingual labels, with minimum-quality floors and a safe default.

## Prompt compression and semantic routing leads

Search results surfaced Microsoft LLMLingua prompt compression, vLLM Semantic Router, Aurelio Semantic Router, research on “when to reason,” and newer adaptive compression work. These methods could reduce prompt prefill or route reasoning depth, but compression can remove citation qualifiers or safety instructions and must therefore be applied only to explicitly separable context blocks with reconstruction/support tests. Semantic routers are attractive for low-latency routing, but their embedding/classifier overhead and language/domain shift must be measured against the current heuristic/embedding router.

## Semantic routing and compression sources verified

`vllm-project/semantic-router` is an Apache-2.0 repository with 5,294 stars and 1,888 commits on the retrieved page. Its README positions it as a programmable mixture-of-models routing layer that selects or composes model paths based on request signals, user preferences, and application policies. The page lists current 2026 releases and supports heterogeneous compute, privacy, safety, and latency objectives. Source: https://github.com/vllm-project/semantic-router.

The associated “When to Reason: Semantic Router for vLLM” paper reports a semantic router that selectively enables reasoning for hard prompts and reports 47.1% lower latency and 48.5% fewer tokens with a 10.2-point accuracy improvement on its MMLU-Pro/vLLM setup. Its implementation relies on a ModernBERT classifier and Rust/Candle core with vLLM/Envoy integration. These are results on an open-model GPU stack, not evidence for AskMukthiGuru’s OpenRouter/Gemini path. Source: https://arxiv.org/html/2510.08731v1.

`microsoft/LLMLingua` is an MIT repository with 6,606 stars and 85 commits on the retrieved page. It offers LLMLingua, LongLLMLingua, LLMLingua-2, and SecurityLingua; the README claims up to 20x prompt compression and describes RAG examples, but it requires a compressor model and adds preprocessing. Source: https://github.com/microsoft/LLMLingua.

The 2026 “Prompt Compression in the Wild” study evaluates thousands of runs and 30,000 queries across open-source models and GPUs. It reports up to 18% end-to-end speed-up only when prompt length, compression ratio, and hardware match; outside that window, compression overhead can erase gains. Source: https://arxiv.org/abs/2604.02985.

## Adoption conclusion

Semantic routing is a credible direction for a future policy service, but AskMukthiGuru already has a semantic router and a no-LLM heuristic-first router. The next step is not to add another router; it is to evaluate current router accuracy/latency by language and query class and use a versioned policy interface. Prompt compression should be deferred until the ledger proves prompt prefill is a material share of end-to-end time and until citation/support retention is measured. Compression must never apply to safety instructions, source-attribution constraints, or untrusted content without explicit structured boundaries and reconstruction tests.

## Serving, scheduling, and cache research verified

vLLM’s current developer-preview documentation describes disaggregated prefilling as experimental. Separating prefill and decode across vLLM instances can tune TTFT and inter-token latency independently and control tail ITL; it does not improve throughput by itself. The mechanism requires KV-cache connectors and additional serving infrastructure. Source: https://docs.vllm.ai/en/latest/features/disagg_prefill/.

The vLLM/llm-d integration docs describe a Kubernetes-native fleet layer with prefix-aware routing, distributed/tiered KV-cache management, prefill/decode disaggregation, autoscaling, and flow control. They report representative benchmark results such as faster TTFT and higher throughput, but these depend on specific hardware, model, traffic, and cluster setups. Source: https://docs.vllm.ai/en/latest/deployment/integrations/llm-d/.

llm-d’s predicted-latency scheduling article is especially relevant to the “rather than hardcodings” requirement. It trains lightweight online regressors for TTFT and TPOT from request features and server state, including input length, queue depth, running requests, KV-cache usage, prefix-cache match, and tokens in flight. It uses a sliding, stratified window and chooses endpoints by predicted latency/SLO headroom rather than fixed heuristic weights. The article reports up to 43% P50 E2E improvement and 70% TTFT improvement in its representative MaaS workload, plus production reductions, but those numbers are not transferable to AskMukthiGuru. Source: https://llm-d.ai/blog/predicted-latency-based-scheduling-for-llms.

SGLang’s RadixAttention documentation describes automatic prefix reuse through a radix tree, with reference counting, configurable eviction policies, page alignment, and speculative decoding integration. It is most effective for long shared system prompts, few-shot examples, document QA, and multi-turn conversations, and requires exact token-prefix matches. Source: https://sgl-project-sglang-93.mintlify.app/concepts/radix-attention.

## Adoption conclusion

Self-hosted vLLM/llm-d/SGLang is a later infrastructure track, not an immediate code-level fix while AskMukthiGuru uses OpenRouter-hosted generation. The reusable near-term concept is an online latency predictor and deadline-aware scheduler at the provider/route boundary, using the existing stage ledger and provider metadata. It can start as shadow prediction over OpenRouter alternatives and later control routing if a multi-provider or self-hosted pool is available. A learned policy should include exploration, decay/sliding windows, SLO headroom, and safe fallbacks; fixed thresholds should be learned or calibrated from traces rather than hardcoded per language.

## YouTube research limitation

The vLLM Office Hours #32 video page was opened: “[vLLM Office Hours #32] Intelligent Inference Scheduling with vLLM and llm-d,” Red Hat, dated September 11, 2025, duration 1:01:01. The player reported that subtitles/closed captions were unavailable. A deeper video-analysis attempt failed with `resource_exhausted: insufficient credits`; therefore no detailed claims are attributed to the video beyond its visible title/date/duration. The primary vLLM/llm-d documentation was used instead.
Source: https://www.youtube.com/watch?v=gaoNMdsfOPg.

## SimilarWeb research limitation

A bounded SimilarWeb API comparison was attempted for `nithyananda.ai`, `askthegita.ai`, `askgita.ai`, `headspace.com`, and `askmukthiguru.com`, covering visits, bounce rate, and desktop traffic sources for recent monthly windows. Every call was stopped before the provider request because the current user has insufficient Manus credits (`failed_precondition`). No traffic, ranking, engagement, or channel figures are available; no competitor popularity conclusion is drawn from SimilarWeb.

## Graph orchestration sources verified

LangGraph’s current Graph API documents state schemas, private channels, conditional edges, super-step parallelism, and explicit input/output schemas. It warns that private state channels are not automatically private during values streaming; output keys or an explicit public projection are required. Its current fault-tolerance docs support graph-wide node defaults for retries, timeouts, and error handlers, with run/idle timeout policies and resume-safe failure provenance. Sources: https://docs.langchain.com/oss/python/langgraph/graph-api and https://docs.langchain.com/oss/python/langgraph/fault-tolerance.

LangGraph’s streaming docs recommend typed event streaming (`version="v2"`) and provide separate updates, values, messages, custom, checkpoints, tasks, and debug projections. It supports filtering streamed tokens by node/tag and explicitly documents that full values streaming can expose all state channels. Source: https://docs.langchain.com/oss/python/langgraph/streaming.

Haystack’s current pipeline docs describe directed multigraphs with concurrent branches, conditional routers, loops, async execution, streaming, concurrency limits, and cancellation/draining of sibling tasks. They caution that sync components offloaded to worker threads cannot be interrupted and their side effects may still complete. Source: https://docs.haystack.deepset.ai/docs/pipelines.

## Adoption conclusion

AskMukthiGuru already uses LangGraph, so adding Haystack or another orchestrator would add framework sprawl. The reusable methods are graph-native: explicit private/internal state, explicit public output schema, conditional edges based on measured evidence, graph-wide timeout/retry defaults, cancellation-safe parallel branches, and typed public stream projections. The current stage ledger should evolve toward these contracts, but no private state should be streamed by default.

## Adaptive RAG primary papers verified

The ICTIR 2026 Adaptive Re-Ranking paper proposes utility-based labels that combine retrieval effectiveness and measured per-query latency, then routes each query among no-rerank, light-rerank, and heavy-rerank strategies. It reports 1.15–53x lower median latency than a heavy BGE reranker across its datasets with nDCG changes ranging from -17.5% to +4.0%. Its router adds about 3.6 ms in the reported setup, but the authors note that simple post-retrieval score signals were insufficiently generalizable and that the learned router’s test accuracy was about 65%. These limitations reinforce the need for AskMukthiGuru-specific held-out labels. Source: https://arxiv.org/html/2606.25249v1.

The Cost-Aware Query Routing in RAG paper defines a fixed catalog of retrieval bundles and selects per query using expected quality, latency, and token cost. It reports results on only 28 queries; the paper itself frames the benchmark as small and controlled. Its useful contribution is transparency: bundle choices, weights, and per-query logs can be inspected, but the small evaluation cannot establish production quality. Source: https://www.mdpi.com/2673-2688/7/7/250.

RAGRouter models how retrieved documents affect which RAG-capable LLM should answer, using document embeddings and capability embeddings with contrastive learning, and adds a score-threshold mechanism for low-latency routing. It is conceptually relevant to choosing provider/model routes after retrieval, but it requires training data and is not validated on AskMukthiGuru’s corpus or languages. Source: https://arxiv.org/abs/2505.23052.

SmartChunk Retrieval proposes a planner that selects query-adaptive chunk abstraction levels and a lightweight compression module, with a reinforcement-learning component called STITCH. The ICLR 2026 abstract reports improved QA and lower cost across several benchmarks, but no direct AskMukthiGuru result. It is a long-term ingestion/retrieval experiment, not a safe drop-in production optimization. Source: https://proceedings.iclr.cc/paper_files/paper/2026/hash/5c1ff00b27ba052039bb41531236baac-Abstract-Conference.html.

## Adoption conclusion

The strongest general method is an explicit route catalog plus learned utility: every route has a measured latency distribution, cost, quality floor, and failure behavior; a lightweight policy selects among routes using current evidence and remaining deadline. Start with shadow mode and counterfactual replay. Use learned routing only after enough AskMukthiGuru-specific multilingual labels exist; otherwise use calibrated deterministic signals, not query-specific string rules.


## Additional latency research — follow-up sweep

The current local runtime snapshot is `LLM_PROVIDER=openrouter`, generation model `google/gemini-3.6-flash`, fast/classify model `google/gemma-3-12b-it`, `LLM_TIMEOUT=60`, `PIPELINE_TIMEOUT=300`, `LLM_MAX_RETRIES=2`, `RAG_TOP_K_RETRIEVAL=20`, `RAG_TOP_K_RERANK=5`, `RERANK_MIN_SCORE=0.10`, `USE_FLASHRANK=true`, `RAG_USE_HYDE=false`, `RAG_MAX_REWRITES=2`, `RAG_INDIC_USE_HYDE=false`, `RAG_INDIC_MAX_REWRITES=1`, and `LATENCY_BENCHMARK_CACHE_DISABLED=true`. Several other names queried from the container environment were unset because the application uses central Pydantic defaults or differently named settings; this is a configuration-visibility gap, not evidence that the controls are inactive.

SAGE: SLO-Aware Adaptive Retrieval for Production RAG Systems is a 2026 IEEE conference publication. Its abstract describes a lightweight, no-LLM-call policy that selects passage count from initial retrieval score distributions, rank gaps, and lexical signals, trained offline from an oracle latency-quality tradeoff. It reports improved SLO compliance and lower P95/cost on its datasets, but those figures are not AskMukthiGuru evidence. Source: https://ieeexplore.ieee.org/abstract/document/11631166/.

AiFlow: Token-Native Reactive Orchestration with Bounded Backpressure for Streaming LLM Applications is arXiv:2608.00558, submitted 1 August 2026. Its abstract proposes typed token/context events, per-node queue bounds, worker concurrency, ordering, overflow, cancellation, and retry discipline. It reports lower application time-to-first-progress than aggregation baselines while not changing provider-side TTFT, based on controlled and captured traces. Its public implementation is linked as ModelEngine-Group/fit-framework. These are research results, not AskMukthiGuru measurements. Sources: https://arxiv.org/abs/2608.00558 and https://github.com/ModelEngine-Group/fit-framework.

HeraSys: Collaborative Serving of Multiple LLM Workflows via Fine-Grained End-to-End Optimization is arXiv:2607.22578, submitted 7 June 2026. Its abstract proposes structural node merging/reuse across workflows, load-aware joint scheduling, resource skewing, adaptive batching, and pipeline decomposition to reduce tail latency under multi-tenant concurrency. It is relevant to future shared-workflow deduplication, but is not a drop-in change for the current single-request LangGraph flow. Source: https://arxiv.org/abs/2607.22578.

The official vLLM anatomy article explains that prefill is generally compute-bound and decode is memory-bandwidth-bound, and describes continuous batching, chunked prefill, prefix caching, guided decoding, speculative decoding, and disaggregated prefill/decode. These mechanisms require a self-hosted compatible inference engine and are not immediate changes to the current OpenRouter/Gemini route. Source: https://vllm.ai/blog/2025-09-05-anatomy-of-vllm.

The official OpenRouter latency guide separates total latency into TTFT (network, provider queue, prompt prefill) plus output tokens divided by generation throughput. It documents rolling percentile provider preferences, throughput preferences, stable session IDs, static prompt prefixes, and cross-model endpoint flattening with `partition: none`. The app should measure provider/attempt/TTFT/output timing before enabling these preferences. Source: https://openrouter.ai/docs/guides/best-practices/latency-and-performance.

Red Hat’s llm-d article describes KV-cache-aware routing over vLLM pods using prefix-aware scoring, session affinity, and an in-memory cache index. It requires Kubernetes/GPU serving infrastructure and therefore belongs to a later self-hosted serving track, not the current OpenRouter path. Source: https://developers.redhat.com/articles/2025/10/07/master-kv-cache-aware-routing-llm-d-efficient-ai-inference.

GitHub CLI inspection found the following current repository metadata: `vllm-project/vllm` was inspected but its output was truncated in the terminal capture; `llm-d/llm-d` reported Apache-2.0, 4,155 stars, and a 26 August 2026 push; `vibrantlabsai/ragas` reported Apache-2.0, 15,472 stars, and a 24 February 2026 push; `Arize-ai/phoenix` reported 11,198 stars and a 26 August 2026 push; `ModelEngine-Group/fit-framework` reported MIT, 2,117 stars, and a 13 March 2026 push; `vllm-project/semantic-router` reported Apache-2.0, 5,303 stars, and a 26 August 2026 push. A generic `gh search repos` query returned no matches, so the known-project metadata was used only as a candidate screen, not as proof of fit.

The Internet Skill Finder live lookup again failed JSON extraction for all seven configured GitHub skill sources and fell back to cached data with zero matches. The failure is tooling evidence, not evidence that no relevant skills exist. The SimilarWeb and YouTube limitations recorded above remain applicable.
