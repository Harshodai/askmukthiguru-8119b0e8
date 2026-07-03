# OpenWiki Documentation Plan

## Repository Overview
**AskMukthiGuru** - AI Spiritual Guide built with React + FastAPI + 12-layer RAG pipeline + Celery + Supabase + Qdrant + Neo4j + Redis + LightRAG

## Target Documentation Structure

### openwiki/quickstart.md (Entry Point)
- High-level project overview
- Quick start (Docker, local dev)
- Architecture summary with links to sections
- Key URLs and access points

### openwiki/architecture/ (Backend Architecture)
- **overview.md** - System diagram, component overview, data flow
- **rag-pipeline.md** - 12-layer RAG pipeline, LangGraph nodes, graph strategies
- **ingestion.md** - Ingestion pipeline, quality gate, Celery tasks, RAPTOR
- **services.md** - Core services (Qdrant, Embedding, LLM, SereneMind, Memory, etc.)
- **observability.md** - Telemetry, metrics, tracing, cost tracking, A/B testing

### openwiki/workflows/ (Key Workflows)
- **ingestion.md** - URL → transcript → quality gate → chunk → embed → index → RAPTOR
- **chat.md** - User query → RAG pipeline → response → memory write → telemetry
- **admin.md** - Admin dashboard workflows (ingestion queue, quality review, OKF manager, RAG flow viz)

### openwiki/domain/ (Domain Concepts)
- **teachings.md** - Sri Preethaji & Sri Krishnaji teachings, doctrine terms, OKF
- **serene-mind.md** - Distress detection, guided meditation, emotional intelligence
- **knowledge-graph.md** - LightRAG, Neo4j entities, entity consolidation
- **multi-guru.md** - Multi-guru configurations, guru-specific collections

### openwiki/data/ (Data & Storage)
- **qdrant.md** - Collections, named vectors, HNSW, RAPTOR levels, payload schema
- **supabase.md** - Tables, migrations, RLS, auth, telemetry, memory, OKF review queue
- **neo4j.md** - Graph schema, LightRAG integration, entity consolidation
- **redis.md** - Caching, Celery, job queues, ephemeral memory

### openwiki/api/ (API Surface)
- **chat.md** - `/api/chat`, streaming, session management
- **ingest.md** - `/api/ingest`, job tracking, staging queue
- **admin.md** - Admin endpoints (overview, queries, quality, telemetry, settings)
- **memory.md** - Memory endpoints, episodic, semantic, notebooks

### openwiki/operations/ (Operations)
- **deployment.md** - Docker, Docker Compose, Railway, Kubernetes
- **local-dev.md** - Local dev setup, hot reload, Supabase local
- **benchmarks.md** - Benchmark suite, ruthless benchmark, native eval
- **backup-restore.md** - Qdrant snapshots, Supabase backups, Neo4j dump/restore

### openwiki/testing/ (Testing)
- **unit.md** - Unit tests, vitest, pytest
- **e2e.md** - Playwright, auth tests
- **benchmarks.md** - Benchmark scripts, CI integration

### openwiki/integrations/ (External Integrations)
- **llm-providers.md** - Sarvam Cloud, Ollama, OpenRouter, NIM, Anthropic Gateway
- **supabase.md** - Auth, database, realtime, storage
- **external-apis.md** - YouTube, Apify, Sarvam STT/TTS, Whisper

---

## Source Evidence Map

| Documentation Section | Key Source Files |
|----------------------|------------------|
| Quickstart | `/README.md`, `/backend/README.md`, `/docker-compose.yml`, `/backend/docker-compose.yml` |
| Architecture Overview | `/docs/ARCHITECTURE.md`, `/backend/app/main.py`, `/backend/app/dependencies.py` |
| RAG Pipeline | `/backend/rag/graph.py`, `/backend/rag/graph_strategies.py`, `/backend/rag/nodes/`, `/backend/rag/states.py` |
| Ingestion Pipeline | `/backend/ingest/pipeline.py`, `/backend/ingest/quality_gate.py`, `/backend/tasks/ingest_tasks.py`, `/backend/celery_config.py` |
| Services | `/backend/services/*.py`, `/backend/app/dependencies.py` |
| Qdrant | `/backend/services/qdrant_service.py`, `/backend/services/qdrant/` |
| Supabase | `/supabase/migrations/*.sql`, `/backend/app/telemetry_db.py`, `/backend/services/memory_service_v2.py` |
| Neo4j | `/backend/services/lightrag_service.py`, `/backend/ingest/pipeline.py` |
| Redis | `/backend/app/dependencies.py`, `/backend/celery_config.py`, `/backend/services/cache/` |
| Frontend | `/src/App.tsx`, `/src/components/chat/ChatInterface.tsx`, `/src/admin/pages/` |
| LLM Providers | `/backend/services/llm/`, `/backend/services/sarvam_service.py`, `/backend/services/ollama_service.py` |
| Deployment | `/docker-compose.yml`, `/backend/docker-compose.yml`, `/docs/DEPLOYMENT.md` |
| Benchmarks | `/backend/benchmarks/*.py`, `/docs/RUTHLESS_AUDIT_REPORT.md` |

---

## Remaining Questions (to resolve during doc writing)

1. **Multi-guru configuration** - How are multiple gurus configured? Check `supabase/migrations/20260703170000_gurus_and_configurations.sql` and `backend/services/doctrine_service.py`
2. **OKF Review Queue** - What is the OKF (Orthogonal Knowledge Framework) review queue workflow? Check `scripts/extract_okf_from_stores.py`, `backend/services/okf_quality_filter.py`
3. **Doctrine Service** - How does the doctrine cache/service work? Check `backend/services/doctrine_cache.py`, `backend/services/doctrine_service.py`, `backend/app/pipeline/stages/doctrine_cache_stage.py`
4. **Multi-tenant architecture** - How does tenant isolation work? Check `backend/services/tenant_context.py`, `supabase/migrations/20260627130000_tenant_rls.sql`
5. **Serene Mind Engine** - Distress detection details? Check `backend/services/serene_mind_engine.py`, `backend/rag/meditation.py`
6. **Telemetry/Observability stack** - Jaeger, OpenTelemetry details? Check `backend/app/telemetry*.py`, `backend/app/observability.py`
7. **Admin dashboard flows** - Ingestion queue, quality review, OKF manager workflows? Check `/src/admin/pages/`

---

## Documentation Priority

1. **Must have** (Phase 1):
   - quickstart.md
   - architecture/overview.md
   - architecture/rag-pipeline.md
   - workflows/ingestion.md
   - workflows/chat.md
   - data/qdrant.md
   - data/supabase.md

2. **Should have** (Phase 2):
   - architecture/ingestion.md
   - architecture/services.md
   - domain/teachings.md
   - domain/serene-mind.md
   - api/chat.md
   - api/ingest.md
   - operations/deployment.md
   - operations/local-dev.md

3. **Nice to have** (Phase 3):
   - architecture/observability.md
   - domain/knowledge-graph.md
   - domain/multi-guru.md
   - data/neo4j.md
   - data/redis.md
   - api/admin.md
   - api/memory.md
   - operations/benchmarks.md
   - operations/backup-restore.md
   - testing/unit.md
   - testing/e2e.md
   - integrations/llm-providers.md
   - integrations/supabase.md
   - integrations/external-apis.md