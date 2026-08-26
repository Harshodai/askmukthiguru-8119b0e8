# Advanced latency methods and audit reconciliation

## Current-vs-attachment reconciliation (2026-08-26)

The attached audit is stale in several places relative to synchronized `main` at `771b507dd106efffcaeee45575cd00c7f7e5d33a`, which equals `origin/main`. Its claimed local head `3d901071...` and origin head `708ece6...` are no longer current. Its latency samples (20.618s English simple, 15.120s stillness, 30.279s Hindi) are historical one-sample observations; the later synchronized-main baseline was 6.113s English simple, 3.019s stillness, 24.146s English comparison, and 30.001s Hindi backend latency. The later tracked Indic policy proof measured Hindi at 18.112s under the original global settings.

The attachment’s claim that the Wisdom Map only falls back manually is stale. `src/components/kg/KGConceptMap.tsx` now automatically falls back to bounded `DEMO_DATA` after a 2.5-second timeout or fetch failure, labels the example state, and exposes `Retry live map`; only a successful zero-node response still presents a manual example action. The attachment’s browser `AUTH_401` finding was a valid observation of persisted browser state, not proof that clean anonymous access fails; token refresh/retry logic and clean anonymous route tests now exist.

The attachment’s P0 missing `okf_compiled` artifact remains open in the current local health payload. The attachment’s recommendation to fix it is valid, but AGENTS.md prohibits manufacturing a placeholder; the artifact must be generated from audited inputs, copied into the exact image, checksum/versioned, and health-gated in CI.

## Existing advanced mechanisms already present

The repository already has Redis/in-memory request coalescing with leader election, follower wait, leader cancellation shielding, takeover, TTL cleanup, and tenant-scoped keys. The OpenRouter gateway already has pooled async HTTP, provider/model policy, budgets, rate limiting, circuit breakers, fallback models, output ceilings, token/cost accounting, and Anthropic-compatible prompt-prefix cache controls. The LangGraph pipeline already separates deterministic safety gates from model-backed steps, has tiered graph strategies, bounded retries/timeouts, queued jobs, replayable SSE for queued requests, and privacy-safe public projections. These are reusable architectural mechanisms, not query-specific hardcodes.

The major gap is instrumentation and adaptive feedback. `StageRunner` already records coarse wrapper timings, but `PipelineCoordinator._stage` is a no-op and `_build_spans` converts only preexisting metrics into spans with `start_ms=0`. The current result metadata does not standardize queue wait, provider attempts/retries, time-to-first-status, time-to-first-token, output decode, translation, or cache-update phases. This prevents evidence-based routing improvements.

## Reusable advanced-method direction

1. Add a privacy-safe stage ledger at the existing coordinator seam. Use OpenTelemetry GenAI semantic names for provider operations and stable application attributes for queue, retrieval, rerank, verification, translation, fallback, and browser completion. Record metadata only by default: model identifier, operation, tier, cache hit, token counts, retry count, duration, status, and error class. Never export prompts, memory context, raw answers, raw graph state, safety internals, or unbounded user content.

2. Use trace-driven adaptive routing instead of language-specific rules. Keep a small policy object that reads rolling stage histograms and request-level remaining budget. Select optional HyDE, decomposition, rerank depth, or a second rewrite only when predicted utility exceeds the measured latency cost and a quality floor remains satisfied. The policy must fail closed to the safer bounded path when telemetry is missing or stale, and every decision must be logged as a versioned policy decision for offline evaluation.

3. Use multi-armed-bandit or contextual-bandit evaluation only behind a shadow/holdout gate. Candidate actions can be `baseline`, `no_hyde`, `one_rewrite`, `rerank_light`, or `rerank_full`; reward must combine groundedness/citation support, abstention correctness, safety outcomes, latency, and cost. Do not let online exploration change safety routing or faithfulness thresholds.

4. Use provider-side prompt caching only for stable prefixes and measure TTFT separately from output decode. OpenRouter already includes Anthropic-compatible cache controls, but the active model path is OpenRouter/Gemini; gateway-specific cache hit and token accounting must be proven before claiming a gain.

5. Add evaluation-driven optimization through existing Ragas-style scripts and prompt/security regression tools rather than adding a second orchestration framework. Held-out multilingual faithfulness, citation support, abstention, safety, and latency gates should decide promotion.

## Verified external findings

OpenTelemetry’s 2026 GenAI observability article recommends recording model identity, input/output token counts, operation durations, finish reasons, and traces for model/tool calls; it states that prompt content capture is opt-in because prompts and completions can be sensitive. The maintained GenAI semantic-conventions repository is separate from the older OpenTelemetry path. Source: https://opentelemetry.io/blog/2026/genai-observability/ and https://github.com/open-telemetry/semantic-conventions-genai.

LangGraph’s official overview describes a low-level runtime that intentionally mixes deterministic and LLM-driven steps, with durable execution, streaming, persistence, and observability. This supports improving the existing graph’s boundaries rather than replacing it. Source: https://docs.langchain.com/oss/python/langgraph/overview.

Ragas defines faithfulness as supported claims divided by total claims and documents an efficient HHEM classifier option. This supports a held-out quality gate and a bounded local verifier experiment, not relaxing production faithfulness rules. Source: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/.

Langfuse’s current repository presents an open-source LLM engineering platform with tracing, prompt management, evaluations, datasets, OpenTelemetry integration, and self-hosting. Its scale/maintenance signals are strong (33.7k stars and a current release/commit were visible during review), but adding the platform is not justified until the existing telemetry seam and export requirements are defined. Source: https://github.com/langfuse/langfuse.

The code-review graph MCP was checked but is not available in the current connector configuration; direct source inspection was used with that limitation recorded here.

## Additional primary-source findings

Langfuse’s current GitHub repository describes tracing for LLM calls, retrieval, embeddings, and agent actions; prompt management with versioning and caching; evaluation/datasets; OpenTelemetry integration; and self-hosting. It is a strong candidate for an observability/evaluation backend, but the current AskMukthiGuru code should first activate its existing telemetry seam and define privacy boundaries before adding a new platform.

The maintained OpenTelemetry GenAI semantic-conventions repository currently has 281 stars, 621 commits, and recent changes visible in the repository. It defines GenAI spans, metrics, and events, including provider/cache/phase usage dimensions. It is an evolving specification rather than a drop-in runtime; use stable metadata and versioned schemas, and keep content capture disabled by default.

GPTCache’s repository has approximately 8.2k stars and 505 commits, but its README explicitly says the project is undergoing rapid development, APIs may change, and new provider/model support is no longer being added broadly. It offers semantic-cache hit ratio, latency, and recall concepts, but the current AskMukthiGuru cache stack already has exact, semantic, vector, tenant, source-release, and faithfulness safeguards. Replacing it wholesale would add risk; prefer measured cache-hit/false-positive evaluation and improve the existing adapter.

## Implemented in this worktree

The response-path healing-course assignment is now eventual rather than blocking. Its existing feature flag, persistable-user gate, shared timeout, and non-fatal error behavior remain intact; the task is scheduled with `asyncio.create_task` and its result is observed. This removes an unrelated persistence side effect from the critical path without changing the graph, safety, grounding, citations, or answer content contract.

The stage ledger now records relative `start_ms`, `end_ms`, and `duration_ms` for every pipeline stage. Result span projection retains legacy node metrics and adds bounded `pipeline.<stage>` entries with status, error code, and release id only. Arbitrary stage metadata is intentionally not projected, preventing prompts, memory, answer content, or raw graph state from reaching the public response. Focused regression coverage passed 112 tests.

This is deliberately a measurement-first step. The next non-hardcoded reduction should use these stage/provider distributions for trace-driven adaptive routing or deadline-aware optional work, promoted only after held-out multilingual faithfulness, citation support, abstention, safety, and latency evaluation. No language-specific hardcoded threshold was added in this step.
