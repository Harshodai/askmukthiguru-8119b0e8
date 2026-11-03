# Architecture Guide & Documents

AskMukthiGuru is a two-surface application:

- **Seeker experience**: the public site, chat experience, practices, profile, and study notebook
- **Admin experience**: dashboards and control panels for ingestion, quality, retrieval, telemetry, and model/queue operations

The backend is the core orchestration layer combining FastAPI, Celery, LangGraph RAG, and multi-tier persistence.

---

## Architecture Documentation Pages

1. **[System Architecture Overview](overview.md)** — High-level system architecture, component topology, FastAPI gateway, Celery worker pool, multi-tier data plane, and ASCII/Mermaid interaction diagrams.
2. **[12-Layer RAG Pipeline & LangGraph Engine](rag-pipeline.md)** — 12-layer RAG execution breakdown, LangGraph state machine, Fast/Standard/Deep execution strategies, query decomposition, HyDE, hybrid vector retrieval, and quote verification.
3. **[First-Person Context Serving Architecture](first-person-serving.md)** — Verbatim context serving, the zero-hallucination guarantee ("Answer text is evidence, directness is metadata"), serving contract B4 isolation, ECAPA acoustic attribution gates, and quarantine policies.

---

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

## Deep-Dive Guides

- [Corpus Ingestion & Verification Architecture](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/wiki/architecture/ingestion.md)
- [Spiritual Teachings & Ontological Knowledge Framework (OKF)](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/wiki/domain/teachings-and-okf.md)
- [Serene Mind & Clinical Safety Architecture](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/wiki/domain/serene-mind.md)
- [Admin Portal & Operator's Guide](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/wiki/admin/portal-guide.md)
- [Operations, Deployment & CI/CD Pipeline Gates](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/docs/wiki/operations/deployment-and-ci.md)

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
