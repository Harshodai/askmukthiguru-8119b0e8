# AskMukthiGuru Free-to-User Adversarial Audit Checkpoint

**Date:** 26 August 2026  
**Author:** Manus AI  
**Scope:** Read-only product, architecture, runtime, latency, safety, cost, and market checkpoint based on the attached audit brief. No product code, deployment, database, credential, corpus, or external product state was changed by this audit pass. Audit artifacts were added locally.

## Executive conclusion

AskMukthiGuru has a credible free core: anonymous chat is available without a paid-user wall, anonymous quota and concurrency backpressure are real controls, citations and grounded partials are explicitly modeled, distress routing is separated from ordinary doctrine, and attachment evidence is bounded and ephemeral. The product is not yet economically or operationally proven for broad free usage because the main provider spend guard is disabled by default, the local runtime is not equivalent to the current source checkout, the readiness surface is unhealthy in the inspected process, and the long-tail `standard`/`tier3_complex` paths remain expensive and slow.

The right strategy is **free core, bounded expensive edges**. Keep basic chat, safety, citations, and deletion controls free. Enforce provider and modality budgets before expensive work, reserve deeper RAG/translation/voice/memory/attachment/ingestion work for requests whose expected user value justifies it, and make every such decision measurable. Do not optimize by weakening grounding, abstention, safety, privacy, tenant isolation, or public SSE projections.

## Evidence status

| Evidence class | Current evidence |
|---|---|
| VERIFIED IN REPOSITORY | Product routes, backend router mounts, quotas, backpressure, cost tracker, provider gateway, attachment bounds, admin gates, cache namespaces, public SSE projection, model policy, and configuration |
| VERIFIED AT RUNTIME | Local port 8001 liveness and health probes; Qdrant/Redis/Neo4j/LLM reachability; process OpenAPI route set; readiness state |
| MEASURED | Cache-disabled 420-case question-bank benchmark and earlier matched cache-disabled route matrix; current latency report contains the authoritative numerical details |
| WEB RESEARCH | OpenRouter model/pricing/usage documentation, OWASP prompt-injection guidance, RAG/evaluation/observability research |
| COMPETITOR EVIDENCE | Official Ask Nithyananda AI, AskTheGita.AI, and Headspace Ebb/AI pages |
| INFERRED | Cost-to-serve risk of optional modalities, likely value of deterministic admin analytics, need for route-correct held-out labels |
| UNKNOWN | Production billing, user volume, conversion, retention, real cost per workflow, full hosted E2E coverage, current corpus-rights status of derived indexes, and whether every documented capability is live in the current deployment |

## Verified product and architecture strengths

The frontend exposes public chat, guides, practice pages, notebooks, knowledge graph, Second Brain, authentication/MFA, reset-password, profile, admin, and support surfaces. The backend mounts auth, admin, health, capability, cache metrics, chat, assistants, ingestion, speech, profile, memory, teaching, support, waitlist, notebooks, SRS, push, cancellation, compliance, retention, metrics, healing course, knowledge graph, Second Brain, jobs, and tracing routers. Compose includes Qdrant, Neo4j, Redis, backend, frontend, optional ingestion worker, observability, and persistence volumes.

The public chat path performs anonymous quota admission, concurrent-request backpressure, quota claim/release, and asynchronous token-cost recording. The quota defaults to five anonymous turns per 24-hour window and a conservative degraded limit of three. The chat semaphore defaults to 20 in-flight requests per replica; the LLM queue defaults to five concurrent operations and a queue limit of 50. These are meaningful free-user controls, but they are not equivalent to a hard provider-spend limit.

The attachment path caps individual and aggregate bytes, caps extracted context, sniffs MIME types, bounds OOXML/PDF/media processing, deletes temporary files, and fences extracted text as untrusted evidence. Second Brain stores encrypted notes separately from user-scoped vectors. Admin routes use AAL2 and an optional user allowlist. Direct and queued SSE use explicit public projections rather than exposing raw graph, prompt, memory, attachment, or safety state.

## Critical findings

| ID | Finding | Evidence class | Status | Priority |
|---|---|---|---|---|
| F-01 | OpenRouter daily/monthly budgets and per-request ceiling exist, but the shared budget guard is disabled by default; broader monthly operating budget is a soft alert | VERIFIED IN REPOSITORY | Expensive/fragile | P0 |
| F-02 | Provider cost accounting prefers actual usage but fallback rates are static and billable dimensions such as request, web-search, image, reasoning, and cache charges must be reconciled against exact model metadata [1] | VERIFIED IN REPOSITORY + WEB RESEARCH | Cost unknown | P0 |
| F-03 | Local process is alive but unhealthy/not ready: embedding and LightRAG were unavailable in the probe; `/api/healthz` was alive while `/api/health` was not ready | VERIFIED AT RUNTIME | Broken for full capability claims | P0 |
| F-04 | Attached source mounts `/api/capabilities`, but the running port-8001 OpenAPI document exposes zero such paths; the process is not demonstrably the current checkout | VERIFIED IN REPOSITORY + VERIFIED AT RUNTIME | Environment mismatch | P0 |
| F-05 | Cache-free 420-case benchmark produced 396 included rows and 106 quality-valid rows; mixed workload mean was 7.13 s backend, with tier3 complex mean 22.89 s and p95 40.84 s | MEASURED | Slow/quality gap | P0/P1 |
| F-06 | Matched cache-free deep comparison improved 9.94% backend and 9.83% wall at n=3; fast factual was unchanged and standard factual was slightly slower | MEASURED | Exploratory gain only | P1 |
| F-07 | Warm/shared greeting artifacts suggest a large deterministic-path gain, but they are excluded from official cache-free performance claims | MEASURED | Evidence boundary | P1 |
| F-08 | 21 HTTP 429s in the question-bank wave represent provider capacity/reliability pressure, not latency | MEASURED | Reliability/cost risk | P0/P1 |
| F-09 | Repository deletion of rights-sensitive source files does not prove derived vector/graph/cache/backup deletion or rights clearance | VERIFIED IN REPOSITORY + UNKNOWN | Content-rights risk | P0 |
| F-10 | Full hosted authenticated, RLS, OAuth, password-reset, memory, upload, speech, admin, and multimodal E2E proof is not established by this checkpoint | UNKNOWN | Coverage gap | P1 |
| F-11 | Admin analytics includes an LLM-powered question-answering path that spends provider budget for internal reporting | VERIFIED IN REPOSITORY | Low-value cost center | P1 |
| F-12 | Current product positioning can differentiate through provenance and trust rather than another generic chat box; competitors emphasize source framing or documented safety loops [2] [3] [4] | COMPETITOR EVIDENCE | Strategic opportunity | P1/P2 |

## P0 roadmap: protect the free core

### P0.1 — Enforce a server-side provider budget before provider calls

Run a disposable Redis budget drill covering reservation, concurrent requests, daily/monthly rejection, actual-cost refund, unknown-cost conservative retention, and Redis-unavailable fail-closed behavior. After the drill passes, enable the guard in the deployment configuration with an owner-approved envelope. Keep safety, basic grounded chat, and honest degradation available; do not silently convert budget exhaustion into fabricated answers.

### P0.2 — Reconcile model pricing and billable dimensions

Version pricing by exact provider/model ID. Record actual provider cost, estimated cost, prompt/completion/reasoning/cache tokens, request/web-search/image units, finish reason, and pricing snapshot ID. Unknown model or missing usage fields must raise an internal accounting alert rather than become zero-cost usage. OpenRouter’s official documentation explicitly exposes these pricing dimensions and usage fields [1].

### P0.3 — Establish one reproducible runtime target

Stop treating a long-running Uvicorn process or liveness response as proof of current product readiness. Reconcile the port, source revision, image, model files, Qdrant collection, LightRAG state, and capability manifest. The absent `okf_compiled` artifact and unavailable LightRAG/embedding state must remain honest failures until the real artifact or service is supplied; never manufacture placeholders.

### P0.4 — Close content-rights and deletion proof

Create a source-to-derived lineage ledger for corpus items, embeddings, graph nodes, caches, backups, and exports. Mark rights basis, retention, deletion status, and affected release IDs. Do not re-ingest rights-sensitive material or claim its removal from derived stores without read-only verification.

## P1 roadmap: reduce cost and tail latency without weakening quality

### P1.1 — Free-core workflow budgets

Create internal budgets for routine chat, deep comparison/multihop, translation, attachments, memory, graph retrieval, web search, voice, ingestion, admin analytics, and experiments. Admission should choose a safe bounded path before provider work. User-facing behavior must remain truthful and must not reveal sensitive provider policy internals.

### P1.2 — Deterministic-first admin analytics

Answer ordinary KPI, cost, latency, and count questions from structured aggregates. Allow the admin LLM only for synthesis that deterministic queries cannot perform, under an admin-only budget and full cost attribution. This removes internal spend without affecting end-user answers.

### P1.3 — Calibrated adaptive RAG cascade

Run a shadow policy over existing retrieval, planner, reranker, rewrite, and verification stages. Use initial evidence features, queue wait, remaining deadline, token estimate, and provider state to predict marginal grounded-evidence gain. Do not control production behavior until held-out multilingual, comparison, citation, out-of-corpus, and distress evaluations prove no regression. Research supports this quality/latency/cost framing, but reported paper results are not AskMukthiGuru outcomes [5] [6].

### P1.4 — Route-correct cache-free benchmark

Run paired, exact-fixture cache-disabled waves with at least 20 included samples per target route. Separate expected route labels from observed runtime tiers. Track provider 429s and incomplete jobs as reliability exclusions. Keep quality-validity, citation validity, distress handling, and public-contract scans as separate gates.

### P1.5 — Modality and resource metering

Meter CPU seconds, wall time, provider cost, bytes, and failure status for OCR, transcription, reranking, graph work, translation, web search, attachments, and ingestion. Apply modality-specific quotas and concurrency caps. A free product cannot expose unmetered media or ingestion paths merely because the core chat quota is bounded.

## P2 roadmap: improve value per unit cost

Make the first successful answer extremely clear and low-friction, then progressively reveal citations, practices, multilingual support, memory, and deeper research. AskTheGita.AI demonstrates the value of a focused source promise and simple first interaction; Ask Nithyananda AI emphasizes provenance and preservation; Headspace Ebb emphasizes scope, safety, and ongoing evaluation [2] [3] [4]. AskMukthiGuru should use these as positioning references, not as permission to copy claims.

Measure activation, answer completion, citation opening, practice start/completion, return sessions, memory creation/deletion, upload success, distress-safe handling, and abandonment. No CAC, ARPU, retention, churn, conversion, or willingness-to-pay facts were available; do not invent them. Since users do not pay, the relevant near-term economic objective is **cost per safe useful outcome**, not subscription conversion.

## P3 roadmap: optional sustainability and defensibility

Consider grants, institutional sponsorship, donations, or clearly separated advanced workflows only after the free core has proven safety, quality, and unit-cost control. Do not paywall crisis help, basic chat, core citations, or deletion rights. Defensibility should come from rights-cleared corpus provenance, trustworthy source attribution, multilingual quality, safe personalization, transparent abstention, and feedback/evaluation loops—not from a replaceable collection of infrastructure components.

## Audit limitations

This checkpoint does not claim a complete penetration test, production billing reconciliation, production Qdrant quality baseline, authenticated hosted E2E for every route, external analytics coverage, or legal rights opinion. SimilarWeb returned no usable traffic/rank data in the earlier audit; Internet Skill Finder extraction failed across configured sources; those limitations cannot support demand or commercial claims. Local Docker memory is not a provider bill.

## References

[1]: https://openrouter.ai/docs/guides/overview/models "OpenRouter Models API and pricing fields"
[2]: https://nithyananda.ai/ "Ask Nithyananda AI official site"
[3]: https://askthegita.ai/ "AskTheGita.AI official site"
[4]: https://www.headspace.com/ai "Headspace AI principles"
[5]: https://arxiv.org/html/2606.25249v1 "Adaptive Re-Ranking research"
[6]: https://www.mdpi.com/2673-2688/7/7/250 "Cost-Aware Query Routing in RAG"
