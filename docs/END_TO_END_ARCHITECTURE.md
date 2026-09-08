# AskMukthiGuru — Current End-to-End HLD & LLD

> **Status:** Current-source architecture reference
> **Reviewed:** 2026-09-07
> **Repository:** `Harshodai/askmukthiguru-8119b0e8`
>
> This document describes the implementation represented by the current `main` source. Older architecture/setup documents may describe historical designs; when they conflict with source, current source wins.

## 1. Executive summary

AskMukthiGuru is a full-stack multilingual spiritual companion built from:

- React 18 + TypeScript + Vite frontend, with Capacitor packaging.
- FastAPI/Python backend.
- Supabase Auth/Postgres/RLS for identity and durable application state.
- LangGraph for multi-strategy RAG orchestration.
- Qdrant for dense+sparse hybrid retrieval.
- Neo4j for bounded graph/entity/relationship retrieval; LightRAG for ingestion, administrative and operational graph work (not the live chat hot path).
- Redis for shared coordination, caching, quota reservations, coalescing and queues.
- Cloud LLM routing through provider adapters/gateway, with optional local Ollama.
- Layered safety, grounding, verification and provenance controls.
- OpenTelemetry/Prometheus/Sentry/Supabase telemetry for operations and quality.

The product is therefore **not simply an LLM wrapper**. It is a stateful retrieval and reasoning platform with a seeker-facing product, an operational/admin control plane, an ingestion pipeline, and several durable/personal knowledge planes.

## 2. Source-of-truth hierarchy

1. Current source code on `main`.
2. Current `AGENTS.md`, `CLAUDE.md` and operational guidance.
3. Dated production-readiness reports, interpreted as historical evidence.
4. Older architecture/setup specifications, interpreted as history/intent.

Known documentation drift includes old local-Ollama/no-auth descriptions and old embedding dimensions. Current code has Supabase auth/RLS, tenant context, anonymous signed-session quotas, cloud-provider routing and BGE-M3-oriented 1024-dimensional dense retrieval.

## 3. HLD topology

```text
                         Internet / Mobile
                                |
                                v
                  +----------------------------+
                  | React / Vite / Capacitor    |
                  | Chat + Profile + Practices |
                  | Admin + Study + SecondBrain |
                  +-------------+--------------+
                                |
                         HTTPS / SSE
                                |
                                v
                  +----------------------------+
                  | FastAPI application          |
                  | auth / tenant / quota / QoS |
                  | validation / API routers     |
                  +-------------+--------------+
                                |
                                v
                  +----------------------------+
                  | LangGraph AI orchestration   |
                  | Fast / Standard / Deep       |
                  +------+-------------+---------+
                         |             |
               +---------+             +-----------+
               |                                     |
               v                                     v
      +-------------------+                  +-------------------+
      | Retrieval plane  |                  | Provider plane   |
      | Qdrant           |                  | LLM Gateway      |
      | Neo4j / LightRAG |                  | Sarvam/OpenRouter|
      | reranker/RAPTOR  |                  | NIM/Ollama paths |
      +---------+---------+                  +---------+---------+
                |                                      |
                +------------------+-------------------+
                                   |
                                   v
                       +------------------------+
                       | Durable data plane     |
                       | Supabase/Postgres/RLS  |
                       | memory/telemetry       |
                       +------------------------+

                 Redis sits across the runtime as
          shared cache / queue / coalescing / quota state.
```

Production self-hosted compose currently contains frontend, backend, Qdrant and Redis. Neo4j is external/managed in that compose design. Railway is the documented hosted backend path and Vercel the hosted frontend path.

## 4. Frontend architecture

`src/App.tsx` is the client composition root. It establishes TanStack Query, Serene Mind context, routing, error boundaries, push/retention behavior, telemetry and lazy-loaded pages.

The router uses `HashRouter` for native Capacitor platforms and `BrowserRouter` for web.

### Major surfaces

- Landing/home.
- Chat.
- Authentication, MFA and password reset.
- Profile.
- Practices and practice detail.
- Teaching/guide pages.
- Study Notebook.
- Knowledge Graph.
- Second Brain.
- Daily Teaching.
- Admin control plane.

Admin code is conditionally imported through `VITE_ADMIN_ENABLED`; when disabled at build time, the admin imports/routes can be tree-shaken from the production bundle.

### Chat client

`src/lib/chat/` is the current transport abstraction. `src/lib/aiService.ts` is a compatibility facade.

Important public operations include:

```text
sendMessage
sendMessageStreaming
translateText
uploadChatAttachment
checkConnection
checkBackendHealth
generateSummary
generateConversationTitle
submitFeedbackToBackend
queueMemoryExtraction
```

Streaming uses a terminal `done` contract and can handle queued `202 + job_id` responses. The client distinguishes status/stage/token/final/done/error events and treats premature stream termination as failure rather than silently displaying a partial answer as successful.

## 5. Backend composition root

`backend/app/main.py` owns process bootstrap, middleware, router registration, lifecycle, telemetry and shutdown. Business services are composed through the dependency/container layer.

`ServiceContainer` is intentionally created through `ContainerBuilder` and is effectively the application dependency graph.

### Container stages

1. Infrastructure: Supabase, Qdrant, LightRAG, Neo4j accessor, OCR, language routing, ingestion and quota services.
2. Retrieval: embedding, semantic model routing, Guru Brain/KG vector services and cache integrations.
3. AI/resilience: LLM providers, translation, OpenRouter, failover, circuit breakers.
4. Operations: compliance, A/B routing, prompt store and cost tracking.
5. Guardrails/coordination: safety rails, exact/semantic cache, doctrine service, queues, coalescer, gateway, Second Brain and optional graph fusion.

## 6. Chat admission boundary

Before expensive RAG/model execution, chat requests pass through several controls:

```text
HTTP request
  -> authentication / anonymous session
  -> tenant context
  -> rate limit
  -> anonymous quota reservation
  -> bounded chat concurrency
  -> server-side history ownership check
  -> sanitization / attachment evidence boundary
  -> LangGraph
```

Anonymous quota uses reservation/claim/release semantics so concurrent requests cannot trivially oversubscribe the same quota window.

Chat backpressure is fail-fast: a saturated replica returns 503/Retry-After rather than creating an unbounded in-process queue.

Authenticated conversation history is reloaded server-side and ownership checked instead of trusting arbitrary browser history.

## 7. Attachment boundary

`POST /api/chat/upload` is an ephemeral evidence-extraction API, not a general artifact store.

The current contract bounds file count/size and extraction concurrency and can process text, PDF, OOXML, images, audio and video through dedicated extraction paths. The resulting `attachment_context` is bounded before entering the RAG graph.

Attachment evidence is explicitly untrusted. It is not automatically promoted to corpus knowledge, durable memory, Qdrant or Neo4j. Attachment-backed requests bypass ordinary response-cache reuse.

The MVP should not be described as providing page-level PDF citations, frame-level video citations, resumable uploads or malware scanning unless a separate artifact lifecycle is implemented.

## 8. LangGraph architecture

`backend/rag/states.py` defines the canonical `GraphState`. It contains user input, routing, retrieval, correction, generation, verification, safety, memory, web-search, operational and provenance fields.

Reducers are important because graph branches can update shared channels concurrently. Current reducers include latest-value semantics, dictionary merges, fan-in of sub-results and monotonic maximums.

### Fast strategy

Designed for low-complexity/high-confidence questions:

```text
START
 -> intent/distress
 -> parallel resolution
 -> route
 -> retrieval
 -> relevant-doc mapping
 -> generation
 -> reflection
 -> verification
 -> citations
 -> formatting
```

### Standard strategy

General-purpose path:

```text
START
 -> intent + distress
 -> parallel resolution
 -> follow-up resolution
 -> decomposition
 -> navigation/HyDE
 -> Qdrant + graph retrieval
 -> reranking
 -> CRAG grading
 -> rewrite/retrieve loop when necessary
 -> context engineering
 -> generation
 -> reflection
 -> verify
 -> citations
 -> format
```

### Deep strategy

Quality-first path for complex queries, adding heavier decomposition, graph-oriented reasoning and verification. It should not be treated as a free/default route because it increases latency and model-call cost.

## 9. Retrieval architecture

### Qdrant

The Qdrant service is decomposed into client, filters, indexer, MMR, neighbor, RAPTOR, searcher and utility modules.

The current retrieval design supports:

- named dense vectors;
- sparse lexical vectors;
- hybrid retrieval/RRF;
- metadata filters;
- RAPTOR hierarchy nodes;
- parent/neighbor expansion;
- reranking;
- MMR;
- deterministic document IDs;
- circuit breaking and operational health.

The primary BGE-M3 dense path uses 1024 dimensions. Model/pooling/dimension changes must be treated as index migrations, not casual configuration edits.

### Embedding service

Embedding execution is lazy/warmable and supports device selection, async CPU offload, caching, circuit breaking and explicit dimension validation. Model revisions are pinned in sensitive loading paths.

### Neo4j + LightRAG

LightRAG is wrapped as a singleton service and uses Neo4j for graph-oriented knowledge. The graph ontology is constrained around entities such as `Teacher`, `Concept`, `Practice`, `Event`, `Organization`, `Location` and `Other`.

The standard live chat retrieval calls `retrieve_for_single_query(..., lightrag=None)` and therefore does **not** invoke LightRAG. It can use separately bounded Neo4j/context-graph enrichment where configured; LightRAG remains active for ingestion, administration and operational graph work. Qdrant is the primary hot-path retrieval system, and each optional graph capability must degrade safely when unavailable.

## 10. LLM gateway

`services/llm_gateway.py` is the provider reliability boundary.

```text
selected provider
   -> timeout/retry policy
   -> circuit breaker
   -> same-provider/model fallback where configured
   -> optional cross-provider fallback
```

Cross-provider fallback is deliberately not a default because silently sending a user's content to another vendor has privacy and policy implications.

The gateway enforces hard output-token ceilings and keeps streaming fallback safe; it does not attempt unsafe mid-stream provider swaps.

## 11. Generation and verification

The response quality pipeline is layered:

```text
retrieved evidence
 -> context engineering
 -> generation
 -> reflection
 -> regenerate/rewrite/fallback when needed
 -> verification
 -> citation extraction
 -> final formatting
 -> output safety
```

Provenance/evidence metadata is carried through the graph rather than generated only after the answer has already been produced.

Personalization is intended to affect style, user context and reference resolution. It must not be treated as an authoritative source of spiritual facts.

## 12. Memory architecture

Memory is separated conceptually into:

```text
profile/preferences
conversation/session summaries
explicit memories
persona/personalization
Second Brain / Mukthi Vault
```

Memory APIs are authenticated and user scoped. The purge path is designed to address multiple storage planes rather than assuming a single database contains all memory.

Second Brain is an encrypted per-user knowledge surface with its own persistence/indexing behavior and can degrade independently from core chat.

## 13. Content ingestion

The ingestion path is conceptually:

```text
source
 -> transcript/document extraction
 -> cleaning/normalization
 -> doctrine correction
 -> safety/artifact validation
 -> chunking/contextualization
 -> embedding
 -> RAPTOR hierarchy
 -> Qdrant
 -> Neo4j/LightRAG graph extraction
 -> checkpoint/manifest
 -> validation/publication
```

A critical invariant is that generated ingestion artifacts must be validated before entering Qdrant. Checkpoints should be cross-checked against actual target-store state so stale checkpoint state cannot falsely report success.

## 14. Database and RLS

Supabase/Postgres is the durable application data plane for identity-linked state, conversations, messages, profiles, memory, content, notebooks, telemetry and administrative data.

The authorization model is layered:

```text
Supabase identity
 -> backend user resolution
 -> tenant/user ownership checks
 -> Postgres RLS
```

Admin access adds server-side privilege checks and optional explicit admin-user allowlisting.

Schema evolution belongs in `supabase/migrations/*.sql`; generated DB types should not be hand-edited.

## 15. Admin/control plane

The admin backend is not merely CRUD. Current routes expose operational evidence including:

- traces and trace detail;
- operations snapshots;
- prompt versions;
- feedback;
- doctrine terms;
- RAG flow graphs;
- evaluation runs;
- retrieval quality;
- ingestion health;
- model/routing distributions;
- safety events;
- alerts/triggers;
- cache/queue/monitoring data.

Admin routes require AAL2 and server-side superuser checks; optional `ADMIN_USER_IDS` adds defense in depth.

## 16. Observability

The system contains:

- Prometheus-style application metrics.
- OpenTelemetry traces.
- Jaeger-compatible tracing in supported deployments.
- Sentry frontend/error instrumentation.
- Supabase-backed telemetry for admin dashboards.
- Correlation IDs and per-node timings.
- PII scrubbing at structured logging/filter boundaries.
- Token/cost accounting.

Observability failures should not become user-traffic blockers.

## 17. Reliability controls

Important controls include:

- request rate limits;
- anonymous quota reservation;
- chat backpressure;
- LLM circuit breakers;
- embedding circuit breakers;
- request coalescing/single-flight;
- exact and semantic caching;
- bounded queues;
- provider/model fallback;
- graph/retrieval degradation;
- health/readiness separation;
- model fingerprint checks;
- graceful request draining.

## 18. Health semantics

`/api/healthz` is liveness and should remain cheap.

`/api/health` is deep dependency health.

`/api/ready` is readiness-oriented and should be interpreted in the context of critical dependency requirements rather than treating every optional service as a hard blocker.

## 19. Deployment

### Backend image

Python 3.12 multi-stage Docker build, lockfile installation, model cache preparation, corpus/OKF artifact inclusion, healthcheck and non-root application execution.

### Frontend image

Node 20 build stage followed by Nginx 1.27 static serving.

### Production compose

Current production compose contains:

```text
frontend
backend
qdrant
redis
```

Neo4j is external/managed there. Backend configuration also expects Supabase and external model-provider credentials.

### Railway

The repository has a dedicated Railway startup path with explicit forwarded-proxy trust configuration. Wildcard forwarded-IP trust should not be used in production.

## 20. Testing

The repository contains a substantial test and verification surface:

- frontend unit/component tests;
- TypeScript checks;
- ESLint;
- Vite production builds;
- Playwright browser/E2E tests;
- accessibility checks;
- backend pytest;
- RAG/evaluation harnesses;
- Bandit/security scans;
- dependency audits;
- RLS verification;
- authentication/AAL2 tests;
- production-readiness sweeps.

Historical release reports contain successful test counts, but dated release reports must not be treated as proof that live provider, restore, rollback or production smoke verification remains green today.

## 21. Ruthless architecture assessment

### What is genuinely strong

1. **Explicit orchestration state.** LangGraph state/reducers make the RAG flow inspectable and testable.
2. **Retrieval diversity.** Qdrant handles semantic/lexical retrieval while Neo4j/LightRAG contributes relationship context.
3. **Provider boundary.** The gateway centralizes timeout, circuit and fallback behavior.
4. **Admission controls.** Quotas, backpressure and coalescing address common AI-product failure modes.
5. **Security depth.** Auth + ownership + RLS + AAL2/admin checks is materially stronger than UI-only authorization.
6. **Operational visibility.** The admin telemetry surface is unusually broad for a product of this type.
7. **Evidence/provenance awareness.** Retrieval evidence and verification are first-class graph state rather than a post-hoc UI decoration.

### What is dangerous

1. **Architecture complexity.** There are many independent libraries and runtime planes. Complexity itself is now a reliability risk.
2. **Dependency surface.** The locked backend stack is very large. Security upgrades can create compatibility regressions, especially in the ML/RAG stack.
3. **Index drift.** Qdrant dimensions/model revisions/pooling/RAPTOR metadata are coupled. A technically successful deployment can still serve poor retrieval if indexes are stale.
4. **Graph drift.** Neo4j/LightRAG has its own schema, workspace and indexing lifecycle. It can become silently stale even while Qdrant remains healthy.
5. **Worker/runtime assumptions.** Multiple workers plus large embedding models can multiply memory consumption. Scaling workers blindly is unsafe.
6. **Too many fallback layers.** Fallbacks improve availability but can hide quality regressions if provider/model switches are not visible in metrics and evaluations.
7. **Documentation drift.** Historical documents can lead engineers to configure the wrong provider, package manager, vector dimensions or auth assumptions.
8. **Live-system evidence gap.** Unit tests cannot prove that Railway + Supabase + Redis + Qdrant + Neo4j + provider credentials + workers behave correctly together.

## 22. Specific Neo4j/LightRAG verdict

**They are genuinely wired into the architecture, but their live roles differ.** Current source has a LightRAG service, Neo4j driver access, graph retrieval nodes, graph state and admin RAG-flow visibility. The standard chat hot path deliberately passes `lightrag=None` for latency and circuit-breaker safety; bounded Neo4j/context-graph enrichment may still be used separately. LightRAG is therefore an active ingestion/administrative/operational component, not a standard-chat retrieval dependency.

However, **I would not describe the current implementation as ruthlessly exploiting graph retrieval yet.** The architecture is graph-assisted, not graph-dominant.

The practical shape is:

```text
                    Query
                      |
             +--------+--------+
             |                 |
          Qdrant          bounded Neo4j context
       dense+sparse       entities/relations
             |                 |
             +--------+--------+
                      |
                 rerank/grade
                      |
                 generation
```

The graph layer is valuable for relational questions such as:

- how concepts relate;
- teacher/concept relationships;
- practice/concept relationships;
- multi-hop entity questions;
- connecting semantically distant evidence.

But it should not be invoked expensively for every simple semantic lookup. The right goal is **query-adaptive graph traversal**, not maximum graph usage.

### What I would improve

1. Route relational/multi-hop intents aggressively toward graph retrieval.
2. Keep graph traversal bounded by hop count, node budget and latency budget.
3. Measure graph contribution separately: answer quality with/without graph evidence.
4. Record graph hit rate, useful-edge rate, unique evidence contribution and graph-induced latency.
5. Add graph-aware evaluation sets, not just generic RAG benchmarks.
6. Detect stale/empty graph workspaces as a data-quality failure rather than silently degrading forever.
7. Make graph provenance visible at answer/evidence level.
8. Avoid duplicating identical facts in Qdrant and Neo4j without measuring marginal value.
9. Treat LightRAG workspace/collection naming as a migration-sensitive contract, and prove an explicit live-chat integration before describing it as a chat dependency.

## 23. Things I consider potentially worst if left unchecked

### A. Silent retrieval degradation

This is the biggest architectural risk. The application can remain green while the knowledge index becomes stale, dimension-incompatible, partially ingested or semantically degraded.

**Priority:** P0/P1 depending on production state.

### B. Dependency/security debt

The backend has an unusually broad ML/RAG dependency tree. Vulnerabilities or incompatible upgrades can block deployment and create security exposure.

**Priority:** P0 if current audit is still red.

### C. Complexity-induced operational blindness

Qdrant + Neo4j + LightRAG + Redis + Supabase + queues + multiple model providers + multiple graph strategies means there are many ways for one subsystem to be degraded while the top-level API still returns 200.

**Priority:** P1.

### D. Memory scaling

Large embedding models combined with multiple backend workers can multiply resident memory. This is a capacity risk, not merely an optimization issue.

**Priority:** P1.

### E. Fallback masking

Provider fallback can make availability look excellent while silently reducing answer quality or changing model behavior. Routing/fallback events must be first-class evaluation dimensions.

**Priority:** P1.

### F. Documentation divergence

If old docs are followed, engineers can easily configure the wrong architecture. The repository needs one clearly authoritative current architecture document and explicit historical labels.

**Priority:** P1.

## 24. Production-readiness interpretation

The system has many production-grade controls, but I would **not** certify it solely from repository inspection.

The final production gate should prove, in a disposable release-like environment:

```text
frontend
 + auth
 + FastAPI
 + Redis
 + Qdrant
 + Neo4j/LightRAG
 + real provider
 + worker topology
 + migrations/RLS
 + backup/restore
 + observability
 + browser E2E
 + retrieval evaluation corpus
 + failure injection
```

The highest-value release tests are real end-to-end round trips, RLS cross-user probes, graph/vector consistency checks, provider failure/fallback tests, worker restart/recovery tests, backup/restore, migration rollback, and retrieval-quality regression evaluation.

## 25. Developer rule of thumb

When modifying AskMukthiGuru, always ask:

1. Does this change identity or tenant boundaries?
2. Does it change the GraphState contract?
3. Does it alter retrieval/index semantics?
4. Does it change model/provider routing?
5. Does it change cache/coalescing behavior?
6. Does it change memory persistence or deletion semantics?
7. Does it change a production readiness assumption?
8. Does the current documentation still describe the actual source?

If the answer to any of these is yes, update the relevant architecture/operational documentation and add the corresponding regression test.
