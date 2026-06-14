# Mukthi Guru - Codebase Map

> One-stop navigation guide for new and returning contributors.

## Entry Points

| Task | Start Here | Also See |
|------|------------|----------|
| Run the full stack | `backend/docker-compose.yml` | [CLAUDE.md#development-commands](/CLAUDE.md) |
| Chat API (backend) | `backend/app/main.py` → `POST /api/chat` | `backend/app/stream_orchestrator.py` |
| Chat UI (frontend) | `src/pages/ChatPage.tsx` | `src/lib/aiService.ts` |
| Admin dashboard | `src/admin/pages/OverviewPage.tsx` | `src/admin/lib/adminAuth.ts` |
| Add a RAG node | `backend/rag/nodes/` | `backend/rag/graph_strategies.py` |
| Run ingestion | `scripts/ingestion/` | `backend/ingest/pipeline.py` |
| Run benchmarks | `backend/benchmarks/` | `backend/benchmarks/run_all.py` |
| Add a service | `backend/services/` | `backend/app/dependencies.py` |

## Architecture Quick-Reference

```
Frontend (React + Vite)
├── src/lib/aiService.ts          # API client (custom / openai / placeholder)
├── src/pages/ChatPage.tsx        # Main chat UI
├── src/admin/                    # Admin dashboard sub-app
└── src/components/               # Reusable UI components

Backend (FastAPI)
├── app/main.py                   # FastAPI entry + routes
├── app/dependencies.py           # ServiceContainer (DI composition root)
├── app/stream_orchestrator.py    # Streaming orchestrator
├── app/observability.py          # OpenTelemetry + tracing
├── rag/
│   ├── graph.py                   # Graph builder facade
│   ├── graph_strategies.py        # Fast/Standard/Deep strategies
│   ├── nodes/                     # Modular node implementations
│   │   ├── intent.py
│   │   ├── retrieval.py
│   │   ├── reranking.py
│   │   ├── generation.py
│   │   ├── verification.py
│   │   ├── keyword_injection.py
│   │   ├── on_device_intent.py
│   │   ├── short_circuit.py
│   │   └── utils.py
│   └── states.py                  # TypedDict data contract
├── ingest/
│   └── pipeline.py               # Ingestion orchestrator
├── services/
│   ├── ollama_service.py         # Ollama LLM
│   ├── openrouter_service.py       # OpenRouter multi-model
│   ├── sarvam_service.py          # Sarvam 30B local
│   ├── embedding_service.py       # all-MiniLM-L6-v2
│   ├── qdrant_service.py          # Vector DB
│   ├── lightrag_service.py        # Graph RAG
│   ├── serene_mind_engine.py     # Distress detection + meditation
│   ├── reranker_service.py        # Re-ranking
│   └── ... (see CLAUDE.md Service Matrix)
├── guardrails/
│   ├── chain.py                   # Guardrail chain orchestration
│   ├── lightweight_handler.py     # Zero-shot LLM guardrails
│   └── nemo_handler.py          # NeMo Guardrails
├── benchmarks/
│   └── run_all.py                 # Run all benchmarks
└── tests/
    └── conftest.py                # Pytest fixtures
```

## Directory Index

### Frontend (`src/`)
- **`admin/`** — Admin dashboard (overview, queries, retrieval, quality, feedback, alerts, triggers, telemetry, evals, prompts, admins, ingestion, logs, settings)
- **`components/`** — UI components (auth, chat, common, landing, layout, meditation, profile)
- **`hooks/`** — Custom React hooks (auth, chat, meditation, theme, TTS, speech recognition, etc.)
- **`lib/`** — Core libraries (aiService, chatStorage, auth, profile, memory, favorites, export, responseCache)
- **`pages/`** — Route pages (Index, Auth, Chat, Profile, Practices, PracticeDetail, Privacy, Terms, ResetPassword, TTSVerification, AuthDiagnostics, AuthLatency, SpiritGuides, NotFound)
- **`test/`** — Vitest unit and integration tests
- **`integrations/`** — Supabase, Lovable integrations

### Backend
- **`app/`** — FastAPI app, route handlers, config, DI, streaming, telemetry, tracing
- **`benchmarks/`** — Benchmark suite (smoke, focused, comprehensive, ruthless, ragas, sdlc, chunk-size)
- **`ingest/`** — Ingestion pipeline (pipeline, youtube_loader, raptor, cleaner, auditor, corrector, image_loader)
- **`rag/nodes/`** — Modular LangGraph nodes (intent, retrieval, reranking, generation, verification, keyword_injection, on_device_intent, short_circuit, utils)
- **`services/`** — 53 services (LLM, retrieval, memory, streaming, guardrails, auth, etc.)
- **`tests/`** — Pytest test suite
- **`scripts/`** — One-off utilities (ingestion, ops, security, etc.)

### Root Level
- **`scripts/`** — Project-wide scripts (ingestion, ops, benchmarks, security, monitoring, whatsapp)
- **`k8s/`** — Kubernetes Helm chart + Skaffold config
- **`.github/workflows/`** — CI/CD pipelines (build, lint, test, security audit)
- **`ingest-ui/`** — Standalone ingestion portal

## Key Files by Concern

| Concern | Primary File | Supporting Files |
|---------|-------------|------------------|
| Pipeline graph wiring | `rag/graph_strategies.py` | `rag/graph.py`, `rag/nodes/*.py` |
| Pipeline state contract | `rag/states.py` | — |
| Pipeline prompt templates | `rag/prompts.py` | — |
| LLM provider factory | `services/llm_factory.py` | `services/ollama_service.py`, `services/openrouter_service.py` |
| Vector retrieval | `services/qdrant_service.py` | `services/lightrag_service.py`, `services/reranker_service.py` |
| Distress detection | `services/serene_mind_engine.py` | `rag/nodes/on_device_intent.py` |
| Ingestion entry | `ingest/pipeline.py` | `scripts/ingestion/*.py` |
| Benchmark entry | `benchmarks/run_all.py` | Individual `benchmarks/*.py` |
| Config loading | `app/config.py` | `.env`, `.env.optimized` |
| DI container | `app/dependencies.py` | `services/container_builder.py` |
| Streaming entry | `app/stream_orchestrator.py` | `services/streaming_generator.py` |
| Guardrails chain | `guardrails/chain.py` | `guardrails/lightweight_handler.py`, `guardrails/nemo_handler.py` |
| Admin route wiring | `backend/routers/admin.py` | `src/admin/pages/*.tsx` |
| Feedback routes | `backend/routers/feedback.py` | `src/lib/memoryApi.ts` |
| Auth service | `services/auth_service.py` | `src/lib/authTelemetry.ts` |
| Memory (backend) | `services/memory_service_v2.py` | `services/memory_service.py` |
| Memory (frontend) | `src/lib/memoryApi.ts` | `src/hooks/useProfile.ts` |

## Adding New Components

### Add a RAG Node
1. Create `backend/rag/nodes/my_node.py`
2. Import in `backend/rag/graph_strategies.py` (add to the relevant strategy)
3. Add node to the graph wiring in the strategy class
4. Add tests in `backend/tests/test_nodes.py`

### Add a Service
1. Create `backend/services/my_service.py`
2. Register in `backend/app/dependencies.py` (ServiceContainer)
3. Update `backend/app/config.py` if new config needed
4. Add tests in `backend/tests/`

### Add a Frontend Component
1. Create component in `src/components/<domain>/MyComponent.tsx`
2. Export from `src/components/<domain>/index.ts` if applicable
3. Use in relevant pages or components
4. Add tests in `src/test/` or `src/tests/`

### Add an Admin Page
1. Create page in `src/admin/pages/MyPage.tsx`
2. Add route in `src/App.tsx` or admin router
3. Add to admin navigation in `src/admin/layout/AdminShell.tsx`
4. Add mocks/data in `src/admin/lib/mockData.ts`

## External Systems

| System | Role | Local URL | Docker Service |
|--------|------|-----------|----------------|
| Qdrant | Vector DB | http://localhost:6333 | `qdrant` |
| Redis | Cache / Queue | — | `redis` |
| Neo4j | Graph DB | http://localhost:7474 | `neo4j` |
| Jaeger | Tracing | http://localhost:16686 | `jaeger` |
| Ollama | LLM host | — | Runs on **host** (not Docker) |
| Prometheus | Metrics (via FastAPI) | http://localhost:8000/metrics | — |
| Supabase | Auth / DB | Configured via env | External (cloud) |
