# AskMukthiGuru — OpenWiki Quickstart

> **An AI-powered spiritual guide rooted in the teachings of Sri Preethaji & Sri Krishnaji.**  
> Built with a multi-layer RAG pipeline, real-time guardrails, and a beautiful conversational UI.

---

## 🚀 Quick Start

### Prerequisites
- **Docker Desktop** installed and running
- **Supabase account** for persistent user profiles & telemetry (run `master_schema.sql` in Supabase SQL Editor)

### One-Command Deploy (Recommended)

```bash
cd backend
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"  # macOS Docker PATH fix
docker compose up -d --build
```

This starts **6 services**:
| Service | Port | Description |
|---------|------|-------------|
| Frontend (Nginx + React) | 80 | Main app, chat widget, admin dashboard |
| Backend (FastAPI) | 8000 | RAG pipeline, ingestion, admin API |
| Qdrant | 6333 | Vector database |
| Redis | 6379 | Response caching, ephemeral memory |
| Neo4j | 7474 / 7687 | Knowledge graph (LightRAG) |
| Jaeger | 16686 | OpenTelemetry trace explorer |

### Access Points
| URL | Description |
|-----|-------------|
| http://localhost | Main app (landing, chat, practices, profile) |
| http://localhost/admin | Admin dashboard (login: `admin` / `admin`) |
| http://localhost/admin/rag-flow | RAG Flow Graph — visualizes LangGraph nodes & latency |
| http://localhost/static-chat | Lightweight chat widget (auth-protected) |
| http://localhost/static-ingest | Content ingestion portal (admin only) |
| http://localhost:8000/api/health | Backend health check |
| http://localhost:7474 | Neo4j Browser (use `bolt://localhost:7687`) |
| http://localhost:16686 | Jaeger trace explorer |

---

## 🧭 Repository Structure

```
askmukthiguru/
├── backend/                    # FastAPI backend
│   ├── app/                    # Application core
│   │   ├── api/               # Route groups (chat, ingest, admin, profile, memory, speech)
│   │   ├── config.py          # Pydantic Settings (all env-driven config)
│   │   ├── dependencies.py    # ServiceContainer (DI composition root)
│   │   ├── main.py            # FastAPI app bootstrap
│   │   ├── pipeline/          # Stage-based chat pipeline (cache → graph → memory)
│   │   └── telemetry*         # OpenTelemetry + Supabase sink
│   ├── ingest/                # Content ingestion pipeline
│   │   ├── pipeline.py        # Main orchestrator (YouTube → transcript → chunk → embed → index)
│   │   ├── quality_gate.py    # Staged quality gate (deterministic → LLM → staging queue)
│   │   ├── youtube_loader.py  # 3-tier transcript extraction (captions → Whisper → auto)
│   │   └── raptor.py          # RAPTOR hierarchical indexing (leaf chunks + LLM summaries)
│   ├── rag/                   # RAG pipeline (LangGraph)
│   │   ├── graph.py           # Graph builder facade (strategy pattern)
│   │   ├── graph_strategies.py# Fast/Standard/Deep graph variants
│   │   ├── nodes/             # LangGraph nodes (retrieve, grade, generate, verify, etc.)
│   │   └── states.py          # GraphState definition
│   ├── services/              # 50+ service modules
│   │   ├── memory_service_v2.py   # 3-tier memory (Redis / PG+Qdrant / Neo4j global)
│   │   ├── doctrine_service.py    # Per-guru doctrine synonym injection
│   │   ├── embedding_service.py   # BGE-M3 / multilingual-e5 embeddings
│   │   ├── qdrant_service.py      # Vector search + RAPTOR collections
│   │   ├── sarvam_service.py      # Sarvam 30B LLM (cloud API)
│   │   ├── lightrag_service.py    # LightRAG knowledge graph integration
│   │   └── serene_mind_engine.py  # Distress detection & meditation guide
│   ├── tasks/                 # Celery tasks (ingestion, OKF compilation)
│   └── docker-compose.yml     # Full stack (6 services)
├── frontend/                   # Minimal frontend Dockerfile
├── src/                        # React 18 + Vite + Tailwind + shadcn/ui
│   ├── admin/                 # Admin dashboard (18+ pages)
│   │   ├── pages/             # Ingestion, OKF Manager, RAG Flow, Queries, etc.
│   │   └── lib/api.ts         # Admin API client
│   ├── components/
│   │   ├── chat/              # ChatInterface, ConversationSourcesPanel
│   │   ├── common/            # SereneMindProvider, SessionExpiredHandler
│   │   └── ui/                # shadcn/ui primitives
│   ├── pages/                 # Seeker pages (Chat, Profile, Practices, Notebook)
│   ├── hooks/                 # Custom React hooks
│   └── App.tsx                # Router + providers
├── supabase/
│   └── migrations/            # SQL migrations (ingest_jobs, staging_quality_queue, gurus, etc.)
├── docs/                       # Extensive documentation (see below)
├── lessons.md                  # 300KB+ of hard-won engineering lessons
└── README.md                   # Project root README
```

---

## 📚 Documentation Map

| Section | Description | Key Files |
|---------|-------------|-----------|
| **Architecture** | System design, data flows, component diagrams | `docs/ARCHITECTURE.md`, `docs/architecture/`, `backend/README.md` |
| **Developer Guide** | Local setup, coding standards, testing | `docs/DEVELOPER_GUIDE.md`, `docs/ROADMAP.md` |
| **Ingestion Pipeline** | YouTube → Qdrant + Neo4j + RAPTOR | `backend/ingest/pipeline.py`, `docs/ADAPTIVE_CHUNKING_INTEGRATION.md` |
| **RAG Pipeline** | LangGraph state machine, strategies, nodes | `backend/rag/graph.py`, `backend/rag/graph_strategies.py` |
| **Memory System** | 3-tier memory (Redis / PG+Qdrant / Neo4j global) | `backend/services/memory_service_v2.py` |
| **Admin Dashboard** | 18+ admin pages for observability & control | `src/admin/pages/`, `backend/app/api/admin.py` |
| **Doctrine & OKF** | Per-guru doctrine synonyms, Open Knowledge Format | `backend/services/doctrine_service.py`, `backend/services/memory/okf_store.py` |
| **Quality Gates** | Staged validation (deterministic → LLM → staging queue) | `backend/ingest/quality_gate.py`, `supabase/migrations/*staging_quality_queue.sql` |
| **Operations** | Deployment, monitoring, runbooks | `docs/DEPLOYMENT.md`, `docs/PRODUCTION_READINESS_CHECKLIST.md` |

---

## 🛠 Development Workflow

### Local Dev (Hot Reload)
```bash
# Terminal 1: Infrastructure only
cd backend && docker compose up -d qdrant redis neo4j jaeger

# Terminal 2: Backend
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 3: Frontend
npm install && npm run dev
```

### Key Commands
```bash
# Backend tests
cd backend && pytest -v

# Frontend tests
npm run test

# Lint / typecheck
npm run lint && npx tsc --noEmit
ruff check backend/

# View logs
cd backend && docker compose logs -f backend

# Rebuild after changes
cd backend && docker compose up -d --build
```

### Environment Variables
All config lives in `backend/.env` (or `.env.prod`). Key variables:
- `LLM_PROVIDER`: `sarvam_cloud` (default) | `ollama` | `openrouter`
- `SARVAM_API_KEY`: Sarvam Cloud API key
- `SUPABASE_URL` / `SUPABASE_KEY`: Persistent storage
- `NEO4J_URI` / `NEO4J_PASSWORD`: Knowledge graph
- `REDIS_URL`: Caching & ephemeral memory
- `QDRANT_URL`: Vector database

See `backend/app/config.py` for the complete, typed, validated config schema.

---

## 🎯 Core Concepts

| Concept | Description |
|---------|-------------|
| **Seeker** | End user seeking spiritual guidance |
| **Guru / Assistant** | Configured persona (slug, doctrine synonyms, model config) |
| **Doctrine Synonyms** | Per-guru canonical terms → variants (e.g., "Beautiful State" → ["beautiful state", "peaceful state", ...]) |
| **OKF (Open Knowledge Format)** | Markdown + YAML frontmatter for curated teachings (teaching / practice / glossary) |
| **RAPTOR** | 2-level hierarchical index: leaf chunks (500 chars) + LLM summaries |
| **LightRAG** | Knowledge graph entities + relations in Neo4j, vector index in Qdrant |
| **Serene Mind** | Distress detection engine → routes to meditation guide node |
| **Quality Gate** | 3-tier validation before content hits vector DB |
| **Staging Queue** | Human review UI for content that fails LLM quality gate |

---

## 🔑 Key Entry Points

| Task | File |
|------|------|
| Backend bootstrap | `backend/app/main.py` |
| Config schema | `backend/app/config.py` |
| DI container | `backend/app/dependencies.py` |
| Chat endpoint | `backend/app/api/chat.py` |
| Ingestion endpoint | `backend/app/api/ingest.py` |
| Admin API | `backend/app/api/admin.py` |
| RAG graph builder | `backend/rag/graph.py` |
| Graph strategies | `backend/rag/graph_strategies.py` |
| Ingestion orchestrator | `backend/ingest/pipeline.py` |
| Quality gate | `backend/ingest/quality_gate.py` |
| Memory service v2 | `backend/services/memory_service_v2.py` |
| Doctrine service | `backend/services/doctrine_service.py` |
| Frontend router | `src/App.tsx` |
| Admin shell | `src/admin/layout/AdminShell.tsx` |
| Chat interface | `src/components/chat/ChatInterface.tsx` |

---

## 📖 Further Reading

Start here based on your goal:

| Goal | Read |
|------|------|
| **New contributor onboarding** | `docs/DEVELOPER_GUIDE.md` → `docs/ROADMAP.md` → `lessons.md` |
| **Understand RAG pipeline** | `backend/rag/graph.py` → `backend/rag/graph_strategies.py` → `backend/rag/nodes/` |
| **Understand ingestion** | `backend/ingest/pipeline.py` → `backend/ingest/quality_gate.py` |
| **Admin dashboard deep dive** | `src/admin/pages/IngestionPage.tsx` → `backend/app/api/admin.py` |
| **Memory architecture** | `backend/services/memory_service_v2.py` |
| **Deploy to production** | `docs/DEPLOYMENT.md` → `docs/PRODUCTION_READINESS_CHECKLIST.md` |
| **Debug a failing ingestion** | `backend/tasks/ingest_tasks.py` → `backend/app/api/admin.py` (ingestion health) |
| **Extend with new guru** | `backend/services/doctrine_service.py` → `supabase/migrations/*gurus*.sql` |

---

## 🔗 Related Files

- **Root README**: `/README.md`
- **Backend README**: `/backend/README.md`
- **Lessons Learned**: `/lessons.md` (300KB+ of hard-won knowledge)
- **Architecture Audit**: `/ARCHITECTURE_AUDIT.md`, `/ARCHITECTURE_AUDIT_CORRECTED.md`
- **Production Hosting (India)**: `/docs/PRODUCTION_HOSTING_INDIA.md`

---

> **Tip for agents**: This wiki is the *map*, not the territory. For implementation details, always verify against the source files linked above. The codebase evolves rapidly — `lessons.md` and git history (`git log --oneline -20`) capture the *why* behind major decisions.