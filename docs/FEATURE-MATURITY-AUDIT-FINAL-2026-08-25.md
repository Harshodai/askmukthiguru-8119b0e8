# AskMukthiGuru Feature Maturity and Productionization Audit

**Audit date:** 2026-08-25
**Repository:** `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
**Author:** Manus AI
**Final verdict:** **RED — NOT PRODUCTION READY**

## Executive conclusion

AskMukthiGuru has a broad and increasingly coherent feature surface: anonymous and authenticated chat, streaming, citations, practices, meditation, profile preferences, memory, Second Brain, notebooks, knowledge graph, SRS/healing, speech, support, admin, queues, and operational health. The audit expanded the evidence materially and fixed several genuine defects. The best-tested user journeys now reach **L3: repeatable journey maturity**, while dependency-blocked or operationally unproven features remain at L1–L2. This is meaningful progress, but it is not a production-readiness pass.

The release remains Red because readiness is correctly false when the required `okf_compiled` runtime artifact is absent; retrieval quality has no approved matching golden corpus; live provider/worker fault behavior is incomplete; restore/RPO/RTO has not been demonstrated; clean chat capacity is not measurable while every local load attempt is quota-admitted as HTTP 429; and cost-per-completed-answer evidence is absent. A passing code/test loop cannot override those gates.

> **Principle applied:** capability presence is not operational maturity. A route, mock, or unit test is evidence of implementation, not evidence of safe scale, recovery, privacy, cost, or production correctness.

## What was executed

The audit followed a source inventory, feature/dependency map, user-journey execution, backend and store contracts, red-team suites, local disposable Supabase isolation proof, performance probes, research synthesis, targeted fixes, cross-review, and a final canonical loop. External research is summarized in [`FEATURE-UPGRADE-RESEARCH-2026-08-25.md`](FEATURE-UPGRADE-RESEARCH-2026-08-25.md), while the detailed scorecard is in [`FEATURE-MATURITY-SCORECARD-2026-08-25.md`](FEATURE-MATURITY-SCORECARD-2026-08-25.md).

| Evidence scope | Result | Meaning |
|---|---:|---|
| Canonical validation loop | `LOOP_RESULT=PASS`; **2,392 passed, 30 skipped, 1 warning** | Frontend tests/lint/typecheck/build/budget, focused backend, Ruff, Bandit, regex safety, compile, and full backend suite pass. Evidence: `/tmp/askmukthi_audit/loop-feature-maturity-final2`. |
| Focused chat/TTS browser journey | **2 passed** | Tour dismissal, `/chat` route, streaming auto-scroll, diagnostic page, and native fallback harness pass. |
| Seeker journey | **2 passed** | Current landing-to-anonymous-chat flow and STT → Telugu language switch → streamed response → native TTS fallback pass. |
| Accessibility smoke | **8 passed** | Covered route-level axe checks pass; manual inclusive testing remains open. |
| Prelaunch sweep | **10 passed** | Covered route, mount, and asset contracts pass. |
| Admin journey/drilldown | **1 passed; 2 passed, 9 skipped** | Unauthenticated and covered contracts pass; privileged/live paths remain unverified. |
| Internationalization | **84 passed** | Covered locale/route matrix passes. |
| Chromium/mobile Chrome/Firefox/WebKit route smoke | Passed in prior expansion | Cross-browser route mounting and known third-party noise isolation pass. |
| Notebook/graph backend contracts | **70 passed, 1 known warning** | Deterministic graph/notebook boundaries pass; live Neo4j and scale evidence remain open. |
| SRS/healing/speech/support/waitlist backend contracts | **65 passed, 1 known warning** | Deterministic feature contracts pass; live integrations remain open. |
| Frontend feature contracts | **174 passed across 17 files** | Chat, speech, transport, storage, waitlist, memory, and admin resiliency contracts pass. |
| Red-team backend suites | **163 passed, 1 warning** | Authorization, AAL2, injection, guardrails, cache scope, migration, and request safety checks pass. |
| Privacy/integrity/lifecycle suites | **115 passed, 1 skipped, 1 warning** | Retention, deletion, cache isolation, uploads, crypto, PII redaction, and corpus integrity contracts pass. |
| AI-safety/prompt suites | **59 passed, 1 warning** | Distress, prompt semantics, verifier, streaming, and SRS injection boundaries pass. |
| Operability/concurrency backend suite | **52 passed, 1 warning** | Queue, streaming, routing, health, metrics, scheduler, worker, cache, and graph boundary contracts pass. |
| Disposable local two-user RLS | **2 passed** | Alice/Bob UI and REST negative isolation checks pass on local Supabase only. |
| Meditation fallback tests | **10 passed across 3 files** | Missing audio can fall back to browser TTS; canonical MP3 publication remains unverified. |

The detailed execution register is [`verification-results.md`](verification-results.md). Counts above are intentionally not added into one grand total because suites overlap.

## Material fixes completed

The audit did not merely report test failures. It removed evidence-backed defects and added regressions around them.

| Surface | Fix | Verification |
|---|---|---|
| Static asset serving | Vite preview now returns 404 for missing `/assets/...` files instead of allowing a missing script to fall through to the SPA shell. Production Nginx static locations now use `try_files $uri =404`. | Prelaunch and route suites pass; canonical loop passes. |
| E2E diagnostics | Explicit `VITE_ENABLE_E2E_DIAGNOSTICS=true` enables diagnostic routes only in the Playwright production-like build; ordinary production remains tree-shaken. | TTS diagnostic journey passes. |
| Accessibility timing | Landing axe capture waits for the animated navbar to settle; a duplicate valid demo trigger is selected intentionally. | Accessibility suite passes. |
| Cross-browser smoke | Supabase realtime is isolated in generic mount smoke and only the verified Firefox third-party cookie warning is filtered. App errors remain observable. | Chromium, Mobile Chrome, Firefox, and WebKit route smoke pass. |
| Chat E2E harness | Test now uses an allowlisted synthetic Gmail identity, asserts `/chat`, dismisses the real guided tour through its Skip control, and finds the composer by accessible role/name. | Chat/TTS and seeker journeys pass. |
| Seeker E2E drift | Stale “Beautiful State” and auth-first CTA assertions were updated to the current “Find your next steady step” and anonymous-first `/chat` behavior. | Seeker journey passes. |
| Conversation/message grants | New migration restores authenticated CRUD and service-role access for `conversations` and `chat_messages`, with defensive privilege checks. | Source contract and disposable local RLS proof pass. |
| Chat profile trigger | New migration resolves message ownership through the parent conversation instead of nonexistent `chat_messages.user_id`. | Source contract and disposable local RLS proof pass. |
| Benchmark safety | Prior audit fixes remain validated: scoped cache clearing replaces global Redis flush and shell execution; URL validation is HTTP(S)-only; queued HTTP 202 is not confused with completion. | Canonical loop and red-team suites pass. |

The two conversation migrations are **not claimed as deployed**. They were reproduced and fixed on a disposable local schema. The linked production migration history was neither inspected through privileged production access nor mutated.

## Feature maturity outcome

The scorecard uses six operational dimensions implicitly: user journey completeness, identity/data safety, failure behavior, observability, scale/cost, and recovery. Its levels are defined as follows: L0 absent or unknown; L1 implemented surface; L2 isolated contract; L3 repeatable journey; L4 production-like integration with SLOs, idempotency, alerting and fault evidence; L5 scaled and recoverable; and L6 continuously governed with drift detection and safe automated response.

| Current maturity band | Feature groups |
|---|---|
| **L3** | Landing/public routes, auth/AAL2 contracts, anonymous/authenticated chat journeys, SSE/streaming boundaries, practices/guides, profile preferences, Profile Memory contracts, notebooks/graph contracts, SRS/healing contracts, STT, TTS fallback, support/waitlist, queues/jobs, health/readiness, admin denial/resiliency, retention/lifecycle contracts. |
| **L2** | Uploads/multimodal input, Second Brain vault, retrieval/corpus ingestion, authenticated telemetry export, some live provider-dependent behavior. |
| **L1** | Push notifications, native mobile packaging, disaster recovery/restore execution, cost governance, canonical meditation asset delivery. |
| **L4–L6 not awarded** | No feature has complete real-dependency, completion-aware SLO, fault-injection, recovery, cost, and scale evidence sufficient for L4 or higher. |

The complete per-feature rationale and next gates are in [`FEATURE-MATURITY-SCORECARD-2026-08-25.md`](FEATURE-MATURITY-SCORECARD-2026-08-25.md). The feature inventory and dependency map remain in [`FEATURE-CATALOG-MATURITY-2026-08-25.md`](FEATURE-CATALOG-MATURITY-2026-08-25.md) and [`dependency-map.md`](dependency-map.md).

## Ruthless blocker register

| Priority | Blocker | Evidence | Required closure |
|---:|---|---|---|
| **P1** | Required `okf_compiled` artifact missing | `/api/health` returned HTTP 200 but `ready=false`, `status=unhealthy`, and `runtime_artifacts.missing_required=["okf_compiled"]`. | Supply the approved artifact, verify checksum/version/rights, and require readiness success in the deployment gate. Do not manufacture the artifact. |
| **P1** | Retrieval quality unproven | Existing labels do not match the configured contextual corpus. Strict evaluation was intentionally not declared valid. | Provision an approved rights-aligned corpus with stable source IDs, then run retrieval metrics separately from grounded-generation and safety metrics. |
| **P1** | Migration deployment state unknown | Fresh disposable local schema exposed missing grants and an invalid trigger, both fixed in new migrations. | Verify migration history in controlled staging and run synthetic authenticated CRUD/RLS tests before closure. |
| **P1** | Recovery unproven | No restore drill, measured RPO/RTO, or cross-store integrity verification. | Drill Supabase, Qdrant, Neo4j, Redis, object storage, indexes, and deletion guarantees together. |
| **P1** | Chat capacity unmeasured | A bounded local probe made 40 requests at concurrency 4 for five seconds; **40/40 were HTTP 429**. | Obtain an authorized clean staging quota/provider path, run completion-aware 1x/10x/100x tests, and measure p50/p95/p99, queue age, saturation, retries, and completion rate. |
| **P1** | Cost unmeasured | No trustworthy completed-answer token/cost sample was produced; provider billing was not accessed. | Measure cost per completed answer, cache hit/miss, retry/fallback, embedding batch, audio/OCR operation, storage unit, and telemetry volume. |
| **P1/P2** | Live provider/worker fault matrix incomplete | Deterministic contracts pass, but live Sarvam/LLM/embedding/Redis/Celery/Neo4j failure and duplicate-delivery behavior are not fully demonstrated. | Add controlled staging fault injection, retry/lease/DLQ proof, and user-visible recovery evidence. |
| **P2** | Canonical meditation audio unavailable locally | Manifest URL for the canonical MP3 returned HTTP 404 in local preview; browser TTS fallback works. | Verify rights-approved publication, CDN route, content type, integrity, and device playback in staging. Do not substitute fabricated media. |
| **P2** | Mobile/push readiness incomplete | Mobile Chrome route evidence exists; native device audio, push, offline, crash, and release telemetry do not. | Run iOS/Android device or emulator release smoke with permission-denial and offline cases. |
| **P2** | Authenticated telemetry continuity unverified | Unauthenticated `/metrics` and `/api/metrics` correctly return 401; security headers and PII redaction contracts pass. | Verify authorized metrics access, trace continuity, low-cardinality dimensions, sensitive-content opt-in, and alert drills. |
| **P2** | Known test warning | Repository `langchain_text_splitters` stub warning remains. | Remove or explicitly isolate the stub with an ownership and dependency decision. |

## Performance and observability evidence

The local readiness endpoint was sampled ten times sequentially with all requests returning HTTP 200, **p50 50.5 ms** and **maximum 70.3 ms**. A separate 20-request, 10-way concurrent health probe returned **20/20 HTTP 200**, **p50 115.5 ms**, **p95 267.7 ms**, and **maximum 493.9 ms**. These are local responsiveness observations, not production SLOs, and do not change the false readiness result.

The production-like frontend build passed in **5.25 seconds real time** (`vite` reported 4.88 seconds), emitted **188 files**, and occupied approximately **9.2 MB** in `dist`. The largest observed uncompressed JavaScript assets were `index` 474.7 kB, `ChatPage` 400.4 kB, `generateCategoricalChart` 358.9 kB, and `radix-vendor` 292.3 kB. Bundle budgets pass, but route-level code splitting and chart loading remain worthwhile mobile optimizations.

The `/api/metrics` and `/metrics` endpoints correctly reject unauthenticated access with HTTP 401. Responses included `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `frame-ancestors 'none'`, a restrictive permissions policy, and correlation IDs. Authenticated export, trace continuity, and cost/cardinality controls remain unverified.

## Research and requested research tools

The research pack applied official RAG evaluation guidance, Playwright best practices, axe accessibility guidance, OpenTelemetry GenAI observability guidance, and public wellness-product pages. It recommends stable rights-approved source IDs, separate retrieval and generation metrics, user-facing locators, isolated state, trace-on-retry, metadata-only GenAI telemetry by default, explicit privacy controls, resilient audio, explainable progress, and consent-respecting personalization. Sources and candidate open-source repositories are linked in [`FEATURE-UPGRADE-RESEARCH-2026-08-25.md`](FEATURE-UPGRADE-RESEARCH-2026-08-25.md).

GitHub Gem Seeker research identified `vectara/open-rag-eval`, `qdrant/qdrant-rag-eval`, `bharatrag`, `axe-core-npm`, and Evidently as candidates for inspection or concepts. No package was installed or adopted merely to satisfy the checklist. Broad API-contract and fault-injection searches returned no strong candidate.

Internet Skill Finder was attempted for RAG evaluation, Playwright accessibility, security red teaming, and observability/SLO work, but the online connector response was malformed and the fallback cache returned no usable results. YouTube discovery found relevant RAG-evaluation and LLM-observability talks, but video analysis was unavailable because the environment reported insufficient credits; therefore no video-derived claim is made. SimilarWeb read-only probes for AskMukthiGuru and public comparator domains returned insufficient-credit failures; no traffic, rank, engagement, or market-share claim is made. First-party activation, retention, practice completion, safe-abstention, chat completion, and support outcomes should be instrumented instead.

## Safety and change controls

No PR was created. Nothing was pushed or deployed. No linked production project, provider billing account, real user account, production corpus, Neo4j database, or user-owned data was mutated. The local Supabase stack was started, reset only as a disposable test environment, used with synthetic users for RLS proof, and stopped at the end. The Qdrant quality baseline was copied before the final loop and compared byte-for-byte afterward; its preexisting timestamp/content remained unchanged.

The repository contains a mixture of current-session audit changes and preexisting user audit artifacts. Those artifacts were preserved. The final implementation changes and evidence are visible in the working tree for review; no claim is made that they are deployed.

## Recommended release sequence

First, make readiness truthful and green by supplying the approved runtime artifact and verifying the exact deployment artifact set. Second, reconcile the retrieval corpus and run strict retrieval plus grounded-generation evaluation with rights, language, intent, and safe-abstention labels. Third, verify the conversation migrations in staging. Fourth, run real-provider and worker fault matrices with completion-aware semantics, idempotency, leases, retries, DLQ, and queue SLOs. Fifth, execute restore/RPO/RTO drills across every durable store. Sixth, measure capacity and cost using an authorized clean staging budget. Seventh, complete device-level mobile audio, push, offline, accessibility, and auth coverage. Only after these gates pass should the scorecard be reconsidered for L4.

## References

[1]: [`FEATURE-MATURITY-SCORECARD-2026-08-25.md`](FEATURE-MATURITY-SCORECARD-2026-08-25.md) — feature-by-feature 0–6 maturity evidence.
[2]: [`FEATURE-UPGRADE-RESEARCH-2026-08-25.md`](FEATURE-UPGRADE-RESEARCH-2026-08-25.md) — external research, open-source candidates, and tool limits.
[3]: [`verification-results.md`](verification-results.md) — targeted and canonical execution results.
[4]: [`audit-findings.md`](audit-findings.md) — master finding register.
[5]: [`performance.md`](performance.md) — performance measurements and limits.
[6]: [`observability.md`](observability.md) — health, metrics, telemetry, and SLO evidence.
[7]: [`cost-analysis.md`](cost-analysis.md) — cost measurement boundary and required gate.
[8]: [Evidently, “A complete guide to RAG evaluation”](https://www.evidentlyai.com/llm-guide/rag-evaluation)
[9]: [Playwright, “Best Practices”](https://playwright.dev/docs/best-practices)
[10]: [OpenTelemetry, “Inside the LLM Call: GenAI Observability”](https://opentelemetry.io/blog/2026/genai-observability/)
