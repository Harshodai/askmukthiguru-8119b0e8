# Feature Upgrade Research and Evidence Boundaries

This document translates the requested external research into engineering criteria. It does not treat competitor marketing as proof of product quality, and it does not claim live SimilarWeb traffic where the analytics service did not return data. YouTube discovery identified relevant first-hand talks on RAG evaluation and LLM observability, but video analysis was unavailable in the current execution environment; therefore no video-derived quote or factual claim is used here.

## Research findings

### RAG and AI answer quality

Production RAG must separate retrieval quality from generation quality. Retrieval needs ground-truth source identifiers and ranking metrics such as precision@k, recall@k, hit rate, MRR, and NDCG; generation needs independent measures for correctness, faithfulness, groundedness, relevance, completeness, and refusal behavior. A domain-specific benchmark is more useful than a generic public benchmark, and synthetic examples should be reviewed by people with domain knowledge. [1] [2]

For AskMukthiGuru, this validates the existing decision not to interpret the mismatched Qdrant corpus as a quality score. The next upgrade is a versioned evaluation contract keyed to stable source IDs, corpus version, tenant, rights status, language, query intent, expected evidence spans, and expected safe behavior. Online monitoring should sample retrieved context and generated claims without storing raw sensitive prompts by default. A low retrieval score should route to retrieval/index diagnosis; an unfaithful answer should be blocked or converted to an honest abstention.

### E2E and UX quality

Playwright recommends testing user-visible behavior with isolated tests, user-facing locators, web-first assertions, controlled database state, traces on retry, and explicit avoidance of third-party dependency testing. It recommends cross-browser/device projects and CI sharding as suites grow. [3] Accessibility automation with axe can catch common issues such as missing labels, duplicate IDs, and contrast problems, but the official guidance says automated scans must be supplemented with manual and inclusive user testing. [4]

For AskMukthiGuru, the current E2E stall should be treated as a harness reliability defect until diagnosed. The upgrade path is a deterministic startup fixture, explicit health/readiness wait with diagnostics, isolated storage state per journey, trace-on-first-retry, public/authenticated projects, and route contracts for guides, support, chat, memory, practices, and error recovery. The next accessibility increment should use role/label contracts plus axe scans on the highest-value routes, followed by keyboard and screen-reader review.

### Observability and GenAI operations

OpenTelemetry’s current GenAI guidance emphasizes recording model identity, input/output token counts, durations, finish reasons, tool calls, and nested spans while treating prompt and completion content as sensitive opt-in data. [5] Its observability primer defines SLIs from user-visible behavior and explains that traces correlate logs and spans across a distributed request. [6]

For AskMukthiGuru, GenAI telemetry should make a chat request diagnosable across admission, retrieval, graph, model, guardrail, persistence, and response stages. The safe default is metadata-only capture, with redaction and bounded sampling; prompt content must not enter traces by accident. The practical dashboard should show request latency, time to first token, queue age, provider/model, token usage, retrieval hit/recall indicators, safety outcome, cache result, and error class with low-cardinality dimensions.

### Wellness-product expectations

Public product pages show that mature wellness products combine guided content with personalization, progress tracking, expert-led programs, sleep or focus pathways, and persistent habits. Headspace presents guided meditations, AI guidance, sleep resources, expert-led programs, personalized recommendations, and progress tracking. [7] Calm Sleep presents personalized plans, daily tasks, readiness progress, check-ins, insights, and wearable integration. [8] Insight Timer emphasizes a large content library, meditation, sleep, breathwork, yoga, contemplation, and personalization. [9]

These are competitive expectations, not mandates to copy. The highest-value AskMukthiGuru upgrades are a coherent “next practice” journey, explainable progress and reflection, better content discovery, resilient audio, and personalized recommendations that respect consent and privacy. The product should avoid adding social or wearable complexity until the core practice, memory, and safety journeys have stronger evidence.

## Open-source candidates

| Candidate | Use | Decision |
|---|---|---|
| [Vectara open-rag-eval](https://github.com/vectara/open-rag-eval) | Reference-free RAG evaluation without requiring golden answers; Apache-2.0; 400 stars in the captured search. | Inspect and adapt concepts only after license, dependency, and corpus fit review. |
| [Qdrant qdrant-rag-eval](https://github.com/qdrant/qdrant-rag-eval) | Qdrant-oriented evaluation examples and reference material; 89 stars in the captured search. | Useful for corpus-aligned retrieval experiments; not a drop-in production dependency. |
| [bharatrag](https://github.com/pradnyagundu/bharatrag) | Indian-language RAG evaluation library; active in the captured search. | Candidate for Hindi/Marathi evaluation ideas; validate maintenance and language coverage before adoption. |
| [axe-core-npm](https://github.com/dequelabs/axe-core-npm) | Browser accessibility engine; MPL-2.0; 719 stars in the captured search. | Prefer the official Playwright integration if dependency policy permits; add scans to E2E, not as sole accessibility proof. |
| [Evidently](https://github.com/evidentlyai/evidently) | Open-source evaluation/monitoring library referenced by its RAG guide. | Evaluate as a reporting layer only after the repository’s privacy and dependency constraints are reviewed. |

The GitHub search returned no strong results for the broad API-contract and fault-injection queries, so no low-signal repository is being adopted merely to satisfy a checklist. Existing pytest, Playwright, health, load, and operational scripts remain the baseline.

## SimilarWeb evidence boundary

Read-only SimilarWeb probes were attempted for `askmukthiguru.lovable.app` and public comparator domains. The service returned no usable traffic data in the current environment, so this document makes no traffic, ranking, engagement, or market-share claim. Product prioritization should use first-party analytics, activation/retention, practice completion, chat success, safe-abstention, and support outcomes once those are instrumented.

## References

[1]: [Evidently, “A complete guide to RAG evaluation”](https://www.evidentlyai.com/llm-guide/rag-evaluation)
[2]: [Anyscale Docs, “RAG evaluation”](https://docs.anyscale.com/rag/evaluation)
[3]: [Playwright, “Best Practices”](https://playwright.dev/docs/best-practices)
[4]: [Playwright, “Accessibility testing”](https://playwright.dev/docs/accessibility-testing)
[5]: [OpenTelemetry, “Inside the LLM Call: GenAI Observability”](https://opentelemetry.io/blog/2026/genai-observability/)
[6]: [OpenTelemetry, “Observability primer”](https://opentelemetry.io/docs/concepts/observability-primer/)
[7]: [Headspace, “Mental Wellness App”](https://www.headspace.com/app)
[8]: [Calm, “Take the stress out of sleep with Calm Sleep”](https://www.calm.com/blog/calm-sleep)
[9]: [Insight Timer](https://insighttimer.com/)
