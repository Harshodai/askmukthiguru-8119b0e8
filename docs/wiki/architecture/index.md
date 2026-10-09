# Architecture Overview

AskMukthiGuru is a two-surface application:

- **Seeker experience**: the public site, chat experience, practices, profile, and study notebook
- **Admin experience**: dashboards and control panels for ingestion, quality, retrieval, telemetry, and model/queue operations

The backend is the core orchestration layer. It combines:

- a **FastAPI** application bootstrap in `backend/app/main.py`
- a **service container** in `backend/app/dependencies.py`
- a **LangGraph RAG pipeline** in `backend/rag/`
- an **ingestion pipeline** in `backend/ingest/pipeline.py`
- multiple persistent stores: **Supabase**, **Qdrant**, **Redis**, and **Neo4j**

## System shape

```text
React/Vite frontend -> FastAPI app -> service container -> RAG / ingestion / memory / telemetry
                                 ├─ Supabase for auth, profiles, jobs, review queues, telemetry
                                 ├─ Qdrant for vector retrieval and memory collections
                                 ├─ Redis for caching, Celery broker/backend, ephemeral memory
                                 └─ Neo4j / LightRAG for graph-backed retrieval and conceptual pathways
```

## Major backend flows

### Chat / answer generation
1. `backend/app/api/chat.py` receives a request.
2. The request is normalized, rate-limited, and enriched with user/profile/memory context.
3. `backend/rag/graph.py` builds the active LangGraph strategy.
4. Retrieval, grading, rewrite, verification, and guardrail nodes run inside the graph.
5. The final response is streamed or returned through the chat API.

### Ingestion
1. `backend/app/api/ingest.py` accepts admin requests for supported content URLs.
2. `backend/ingest/pipeline.py` handles loading, cleaning, chunking, redaction, enrichment, and indexing.
3. Content is filtered by the staged quality gate in `backend/ingest/quality_gate.py` before it reaches durable indexes.
4. Celery tasks in `backend/tasks/ingest_tasks.py` handle long-running work off the request path.

### Memory and doctrine
1. `backend/services/memory_service_v2.py` provides the three-tier memory system.
2. `backend/services/doctrine_service.py` loads per-assistant doctrine synonyms and query expansion hints.
3. `backend/services/doctrine_cache.py` supports exact-match doctrine answers for frequent spiritual questions.

## What changed recently

Recent commits show the system moving toward:

- **staged ingestion quality** rather than direct indexing
- **Celery-based orchestration** for background workloads
- **assistant-specific doctrine configuration** rather than hardcoded synonyms
- **multi-guru support** and a more explicit admin review workflow

See `lessons.md` and the recent git history for the rationale behind these changes.

## Where to start when editing architecture

- **App bootstrap and middleware**: `backend/app/main.py`
- **Service wiring**: `backend/app/dependencies.py`
- **RAG graph structure**: `backend/rag/graph.py`, `backend/rag/graph_strategies.py`, `backend/rag/states.py`
- **Ingestion flow**: `backend/ingest/pipeline.py`, `backend/ingest/quality_gate.py`
- **Cross-service configuration**: `backend/app/config.py`

## Source anchors

- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/dependencies.py`
- `backend/rag/graph.py`
- `backend/rag/graph_strategies.py`
- `backend/rag/states.py`
- `backend/ingest/pipeline.py`
- `backend/ingest/quality_gate.py`
- `backend/services/memory_service_v2.py`
- `backend/services/doctrine_service.py`