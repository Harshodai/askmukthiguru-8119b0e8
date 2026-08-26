# AskMukthiGuru: Attachment Reconciliation and Advanced Latency Plan

**Date:** 26 August 2026  
**Scope:** Compare `pasted_content_2.txt` with synchronized `main`, inspect the current backend/frontend implementation, and identify safer advanced methods than query- or language-specific hardcoding.

## Executive conclusion

The attachment is useful as a prioritization memo, but it is not a current-state report. Several observations are stale because the repository has moved to `771b507dd106efffcaeee45575cd00c7f7e5d33a`, equal to `origin/main`, and later remediation work has already changed browser authentication recovery, Wisdom Map fallback behavior, graph routing, and latency controls. The two recommendations that remain highest priority are the missing `okf_compiled` artifact and the absence of held-out multilingual release gates. The most important architectural gap is not another shortcut: it is a reliable, privacy-safe measurement and decision layer that can learn which optional RAG stages are worth their latency.

The previous Indic-specific HyDE/rewrite controls were a conservative, validated experiment, not a general optimization architecture. To avoid hardcoding, this work adds two reusable foundations: **eventual execution for non-response-critical course assignment** and **relative, privacy-safe pipeline stage spans**. The next reduction should be trace-driven adaptive routing, promoted from shadow evaluation only when groundedness, citation support, abstention, safety, latency, and cost all meet their gates.

## Difference matrix

| Attachment recommendation or finding | Current repository/runtime | Difference | Status and action |
| --- | --- | --- | --- |
| Backend is not release-ready because `okf_compiled` is missing | Current health still reports the required artifact missing; other major dependencies were observed as available in the prior local snapshot | This finding remains accurate, not stale | **P0 open.** Generate the audited artifact from approved inputs, package it into the exact image, checksum/version it, and make CI fail if it is absent. Do not create a placeholder. |
| Release evidence is split across heads and deployments | Current `HEAD` equals `origin/main` at `771b507d`; the new worktree changes are local and uncommitted | The attachment’s historical SHA references are stale; the general release-manifest concern remains valid | **P0/P1 open.** Keep source SHA, deployed SHA, image digest, artifact manifest, and health result in one signed handoff. |
| Browser chat still reaches `AUTH_401` in persisted state | Anonymous-token refresh/retry handling and clean anonymous route coverage were added in prior remediation; a persisted authenticated browser can still be a distinct test state | A contaminated persisted-session observation must not be generalized to clean anonymous failure | **P1 partially closed.** Retain clean-storage and expired-token tests; do not treat one persisted-browser failure as proof of a transport regression. |
| Nontrivial chat latency is 15–30 seconds | Later synchronized-main local samples were approximately 6.1s English simple, 3.0s stillness, 24.1s English comparison, and 30.0s Hindi backend latency; the tracked Indic treatment later measured 18.1s Hindi | The attachment’s numbers are historical one-sample values, not current p50/p95; the tail problem remains | **P1 open.** Collect repeated per-class p50/p95 with queue wait, first status, TTFT, complete, node, and unexplained overhead. |
| Wisdom Map needs manual fallback after fetch failure | `KGConceptMap.tsx` now falls back automatically to bounded example data after a 2.5s timeout or fetch failure, labels it, and offers retry; only a successful zero-node response retains a manual example action | The broad finding is stale and narrower than the current behavior | **Closed for fetch failure.** Keep zero-node and retry coverage; measure live success and example-map impressions separately. |
| Groundedness and abstention lack held-out release gates | Current code has faithfulness/citation/abstention metadata and focused tests, but no sufficiently broad held-out multilingual release gate | The safety machinery exists; evaluation breadth is still missing | **P1 open.** Add held-out language/query-class suites for faithfulness, citation precision/recall, abstention correctness, safety, latency, and cost. |
| Browser-facing telemetry needs standardized GenAI dimensions | OTEL dependencies and manual RAG tracing already exist; OpenRouter records model, token, cache, cost, and retry-related data; however `PipelineCoordinator._stage` was a no-op and response spans previously had no stage boundaries | The attachment correctly identified a measurement gap, but not an absence of all telemetry | **Partially addressed in this worktree.** StageRunner now records relative start/end/duration and result projection adds bounded `pipeline.<stage>` entries without arbitrary metadata. Provider-level OTEL/GenAI dimensions remain a follow-up. |
| Anonymous first value needs a public practice-to-chat loop | Existing public chat and practice/product surfaces exist, but the attached memo’s complete completion/save/return loop is not proven by the current evidence | Still open, independent of latency | **P2 open.** Add a safe product experiment with first-party activation and retention metrics. |
| Tablet responsiveness is weakest at 768–1024px | Existing responsive work covers common breakpoints, but the attachment correctly says the full keyboard/visual stress matrix is not closed | Still open | **P2 open.** Run 768, 820, 912, and 1024px visual and keyboard journeys. |
| Audio, Google login, password reset, production NDCG, nightly RLS remain incomplete | These remain release-readiness work items in AGENTS.md; they are not solved by latency changes | Still open | **P2/P0 depending on release path.** Close with CI or production-safe evidence rather than claims. |
| Marketing authority/scale claims are unverified | No new primary evidence was found in this pass | Still open | **P2 open.** Qualify, prove, or remove public claims. |

## What is already advanced rather than hardcoded

The current architecture already contains several mechanisms that should be preserved. Redis-backed request coalescing elects a leader, shares serialized results with followers, handles leader cancellation, takes over after leader death, and scopes keys by tenant. The provider gateway uses pooled async HTTP, model policy enforcement, budget reservation, rate limiting, circuit breaking, fallback models, output ceilings, token/cost accounting, and provider-specific prompt-cache controls. LangGraph combines deterministic guardrails with model-backed nodes and bounded routing. Queued streaming has authorization and replay rules. These are structural optimizations, not query-specific exceptions.

The main missing layer was the feedback loop. `StageRunner` had coarse timings, but the coordinator callback was a no-op and `_build_spans` only converted node metrics with `start_ms=0`. The new stage ledger closes part of that gap. It is deliberately metadata-only: stage name, relative boundaries, duration, status, bounded error code, and release identifier are allowed; arbitrary metadata is not projected. This follows the privacy posture recommended by current OpenTelemetry GenAI guidance, which treats prompt and completion content as sensitive and opt-in rather than default telemetry [1].

The request-state path also contained a noncritical persistence side effect: healing-course assignment was awaited for up to the shared node timeout even though no current graph or result consumer used `recommended_course`. It is now scheduled as an observed background task while preserving its feature flag, persistable-user gate, timeout, and non-fatal failure semantics. This is a general async critical-path improvement, not a Hindi or query-pattern shortcut.

## Advanced methods to use next

### 1. Trace-driven adaptive RAG policy

Replace language-specific optional-stage rules with a policy object that chooses among optional actions such as baseline retrieval, HyDE, one rewrite, deeper reranking, or full verification. The policy should use request signals already present in state—query tier, retrieval confidence, evidence count, remaining request budget, model/provider health, and recent stage histograms—not a list of phrases or a language exception.

The policy should be conservative when telemetry is cold or stale: choose the bounded baseline path, preserve safety and citation checks, and emit a versioned decision record. Once enough data exists, predicted marginal groundedness/citation benefit can be compared with predicted latency and cost. This is a suitable place for a contextual bandit or constrained optimizer, but only in shadow or holdout mode initially. Safety routing and faithfulness thresholds must never be explored online.

### 2. Deadline-aware optional work

Every request should carry an internal remaining-budget value derived from the actual request deadline. Optional work should receive a child deadline and be cancelled when its predicted or observed cost would violate the remaining budget. The controller should use the same timeout settings and provider health signals already used by the system, rather than embedding a fixed Hindi/English branch. This improves reliability as well as latency because slow providers stop consuming the entire pipeline budget.

### 3. Standard GenAI and application spans

Keep the existing OTEL bootstrap, but map provider calls to current GenAI conventions: operation, model, provider, input/output token counts, finish reason, cache-read/write tokens, retry count, and duration. Add application spans for queue admission, queue wait, request preparation, retrieval, rerank, grading, generation, verification, translation, fallback, cache update, and final delivery. Capture no raw prompts, memory, answer text, source payloads, or safety internals by default. Langfuse or another OTLP-compatible backend is a possible downstream viewer, but adding it before the local ledger and schema are stable would be framework sprawl [1] [2].

### 4. Evaluation-driven optimization

Use the current graph as the system under test and add selective Ragas-style faithfulness and citation evaluation, Promptfoo-style adversarial prompt-injection cases, and a deterministic safety suite. Ragas defines faithfulness as the fraction of answer claims supported by retrieved context, which is directly aligned with the current citation and abstention contract [3]. Keep evaluation data held out from routing development. Promotion should require no regression on safety recall, abstention correctness, citation support, or tenant isolation, in addition to a latency/cost improvement.

### 5. Cache improvement with false-positive gates

The current stack already has exact, semantic, vector, tenant, source-release, and faithfulness safeguards. GPTCache is useful as a reference for hit ratio, latency, and recall, but its own README warns that APIs may change and broad new provider support is not being added [4]. Do not replace the current cache wholesale. Instead, measure cache hit rate, false-positive rate, source-version invalidation, and answer-support quality by query class. Only promote semantic reuse when the answer remains supported under the same authority and release scope.

### 6. Provider and serving-layer optimization

OpenRouter already pools connections, tracks token usage, and sends Anthropic-compatible cache controls. Provider prompt caching should be measured as TTFT/prefill improvement, not assumed to reduce output decode time. For later higher-QPS work, test provider/model routing, prefix stability, speculative decoding, continuous batching, or a dedicated inference server independently from RAG changes. These methods are serving-layer experiments and should not be mixed into a retrieval-quality release.

## Implementation delivered in this worktree

The following changes are local and uncommitted:

| Change | Why it is non-hardcoded | Safety boundary |
| --- | --- | --- |
| Healing-course assignment is scheduled as observed background work | Applies to any persistable request and is controlled by the existing feature flag and node timeout | Does not alter answer, safety, grounding, citation, or tenant gates; failures are non-fatal and observed |
| StageRunner records relative stage start/end/duration | Generic for every pipeline stage; no language/query exception | Only bounded timing/status fields are projected; arbitrary stage metadata is excluded |
| Result span projection retains node metrics and adds `pipeline.<stage>` entries | Reuses existing span/result contract and supports future dashboards | No prompts, memory, raw answers, graph state, or raw source payloads are added |
| Focused tests cover timing fields, privacy exclusion, and prior routing/healing behavior | Regression-driven, not magic-number-driven | 112 focused tests passed |

## Recommended sequence

First, close the `okf_compiled` artifact gate with audited inputs and image-level CI verification. Second, run the new stage ledger in a controlled environment and collect enough repeated traces to estimate per-class distributions. Third, add a shadow-only adaptive policy whose decisions do not affect user responses; compare baseline, no-HyDE, one-rewrite, rerank-light, and full-rerank actions against held-out quality and safety data. Fourth, promote only a constrained policy that demonstrates a statistically credible tail reduction without worsening groundedness, citation support, abstention, safety, or tenant isolation. Only after that should a new telemetry backend, semantic-cache replacement, or serving-layer experiment be considered.

## Research limitations

The code-review graph MCP was unavailable in the current connector configuration, so direct source inspection was used. SimilarWeb traffic data remains unavailable because of the prior credit limitation. Internet Skill Finder did not return an actionable verified skill during the prior pass. YouTube captions and frame-level analysis were unavailable, so no detailed claims are made from the video. These limitations affect competitive and traffic conclusions, not the repository source comparison above.

## References

[1]: https://opentelemetry.io/blog/2026/genai-observability/ "OpenTelemetry: Inside the LLM Call: GenAI Observability"
[2]: https://github.com/open-telemetry/semantic-conventions-genai "OpenTelemetry GenAI Semantic Conventions"
[3]: https://docs.ragas.io/en/stable/concepts/metrics/available_metrics/faithfulness/ "Ragas Faithfulness"
[4]: https://github.com/zilliztech/GPTCache "GPTCache repository and README"

## Validation evidence for this worktree

The focused backend suite passed **112 tests** after the implementation. The complete dependency-complete backend suite passed **2,456 tests with 30 skips** in 501.88 seconds. The frontend suite passed **522 tests with 6 skips** across 90 test files, and the production build completed successfully with **28 prerendered routes**. `py_compile` and `git diff --check` passed.

A rebuilt Docker backend was started on the attached computer, but its local healthcheck remained in the warm-up state while downloading/loading model artifacts and it experienced repeated lifecycle restarts, including a healthcheck attempt with exit code 137 while the container itself reported `OOMKilled=false`. The host endpoint was not serving during the bounded observation window. Therefore, this worktree’s new background-task and stage-ledger changes are validated by source-level and dependency-complete tests, but no new live before/after latency claim is made for them. The earlier Hindi improvement numbers remain historical evidence for the prior Indic-scoped experiment and are not attributed to this new stage-ledger change.

No commit or push was performed. The branch remains synchronized with `origin/main`; all listed source/docs/evidence changes are local working-tree changes.
