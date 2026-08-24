# System Map

## Scope

AskMukthiGuru is a React/Vite/TypeScript client with Capacitor packaging and a FastAPI/Python backend. The user-facing product combines chat, spiritual practices, profile and memory surfaces, guides, notebooks, knowledge graph views, and administrative operations. The backend coordinates retrieval, generation, safety, personalization, telemetry, and asynchronous work.

## Runtime components

| Layer | Verified components | Primary responsibility |
|---|---|---|
| Web client | React 18, React Router, TanStack Query, Tailwind/shadcn, Vite | Public pages, authenticated app shell, chat UX, memory/profile UX, route-level lazy loading. |
| Native shell | Capacitor, Android, iOS projects | Mobile packaging and native integration. Mobile production parity was not live-verified in this run. |
| API | FastAPI routers and service container | Authenticated/anonymous API contracts, chat admission, jobs, profile/memory, uploads, health, admin controls. |
| Chat orchestration | Synchronous and streaming orchestrators, guardrails, intent and language routing | Request validation, retrieval/generation pipeline, moderation, streaming, quotas, and response shaping. |
| Retrieval | Qdrant dense/sparse search, tenant/corpus filters, reranking paths | Grounded candidate retrieval. Real quality remains unproven because the configured live collection does not match the golden evaluation labels. |
| Knowledge graph | Neo4j/LightRAG and graph-tier services | Graph context and relationship-aware retrieval. Local Neo4j integration tests were skipped because Neo4j was unreachable. |
| Persistence | Supabase tables, encrypted Second Brain vault APIs, local/browser chat storage | User profile/memory, sessions, summaries, encrypted reflections, and client retention. |
| Cache and queues | Redis query/cache namespaces, job queue, Celery/worker paths | Rate limiting, cache, queue admission, async execution, and operational state. Routine cache maintenance must remain scoped. |
| Providers | LLM gateways, embeddings, OCR, optional speech/vision providers | Generation, embeddings, file understanding, and optional multimodal capabilities. Provider-backed coverage is not fully live in this environment. |
| Observability | Structured logs, Sentry hooks, OpenTelemetry/Jaeger, health/readiness | Diagnostics, traces, user-visible error telemetry, and operational readiness. End-to-end collector behavior was not production-verified. |
| Operations | CI workflow, `scripts/ops`, benchmarks, backup utilities, loop validation | Build/test/security gates, maintenance, backup, load probes, and audit evidence. |

## Request and state flows

1. A client request enters a FastAPI route, is assigned a tenant/request context, and passes auth, quota, rate-limit, validation, and backpressure checks.
2. Chat requests either execute through the synchronous/streaming orchestrator or are admitted to the job queue. A queued request returns HTTP 202 with a job identifier and owner-scoped polling/streaming URL.
3. The orchestrator invokes intent/language routing, cache lookup, retrieval and graph enrichment, safety/grounding controls, provider generation, post-generation verification, and response/telemetry publication.
4. Successful or blocked interactions update quota and selected persistence paths. Memory writes and summaries are separate from the encrypted Second Brain vault.
5. The frontend renders route-local state. Profile Memory reads Supabase-native memory tables through `memoryApi`; Second Brain reads the backend vault through `secondBrainApi`. This separation is now explained in the vault error state.

## Critical trust boundaries

The principal boundaries are anonymous versus signed-in identity, tenant/corpus filters at retrieval, owner-scoped job polling and deletion, Supabase row-level authorization, backend vault authorization, admin routes, upload parsing, provider gateways, and browser-visible SSE metadata. The repository contains targeted regression coverage for many of these boundaries, but live disposable Supabase/Neo4j/Redis/provider verification is still required before Green status.

## Evidence links

The route table is in [`src/App.tsx`](../../../src/App.tsx). Chat queue behavior is in [`backend/app/api/chat.py`](../../../backend/app/api/chat.py), job ownership is in [`backend/app/api/job_routes.py`](../../../backend/app/api/job_routes.py), Qdrant search is under [`backend/services/qdrant`](../../../backend/services/qdrant), Profile Memory is represented by [`src/lib/memoryApi.ts`](../../../src/lib/memoryApi.ts), and the encrypted vault by [`src/lib/secondBrainApi.ts`](../../../src/lib/secondBrainApi.ts).
