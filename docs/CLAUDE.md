# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Mukthi Guru** is a privacy-first, zero-hallucination AI spiritual guide grounded in Sri Preethaji & Sri Krishnaji's teachings. It combines a React frontend chat UI with a Python FastAPI backend running a multi-layer RAG pipeline.

**Constraints from SPEC_DEV.md (non-negotiable):**
- $0 budget — only free-tier infrastructure (Colab, Qdrant local, Ollama)
- All processing is local; zero external API calls at inference
- Every dependency must be open source (Apache 2.0, MIT, or Meta Community)
- Target: <1% hallucination rate, <3s response time
- Data source: only Sri Preethaji & Sri Krishnaji's YouTube videos + approved images

## Repository Structure

```
/                          # Root: React frontend (Vite + TypeScript + shadcn/ui)
├── src/                   # React app source
│   ├── lib/aiService.ts   # AI provider abstraction (placeholder/custom/openai modes)
│   ├── lib/chatStorage.ts # Local chat persistence
│   ├── pages/ChatPage.tsx # Main chat UI
│   └── test/              # Vitest tests
├── ingest-ui/             # Standalone HTML/JS ingestion portal (served by backend at /ingest/)
└── backend/               # Python FastAPI backend
    ├── app/
    │   ├── main.py        # FastAPI app, route handlers, lifespan
    │   ├── config.py      # Pydantic Settings (all config from .env)
    │   └── dependencies.py # ServiceContainer (composition root, DI)
    ├── rag/
    │   ├── graph.py       # LangGraph pipeline assembly (layers 2–11)
    │   ├── nodes.py       # All graph node functions
    │   ├── states.py      # GraphState TypedDict (data contract)
    │   └── prompts.py     # LLM prompt templates
    ├── ingest/
    │   ├── pipeline.py    # IngestionPipeline orchestrator
    │   ├── youtube_loader.py # Transcript extraction (3-tier: manual→Whisper→auto-captions)
    │   ├── raptor.py      # RAPTOR hierarchical indexing
    │   ├── cleaner.py     # Text cleaning
    │   ├── auditor.py     # LLM-based content quality check
    │   └── corrector.py   # LLM-based transcript correction
    ├── services/
    │   ├── ollama_service.py    # Ollama LLM client
    │   ├── embedding_service.py # all-MiniLM-L6-v2 embeddings
    │   ├── qdrant_service.py    # Qdrant vector DB client
    │   ├── ocr_service.py       # EasyOCR
    │   └── depression_detector.py # Distress detection
    ├── guardrails/rails.py # Zero-Shot LLM Guardrails
    ├── models/            # Sarvam 30B setup scripts + Modelfile
    ├── colab/             # Google Colab setup & backup scripts
    └── docker-compose.yml # Qdrant, Neo4j, Redis + Backend (Ollama runs on host)
```

## Development Commands

### Frontend (React)
```bash
npm run dev          # Start Vite dev server (http://localhost:8080)
npm run build        # Production build
npm run lint         # ESLint
npm test             # Run Vitest tests (once)
npm run test:watch   # Run Vitest in watch mode
```

Tests are in `src/test/` and match `src/**/*.{test,spec}.{ts,tsx}`. The `@` alias maps to `src/`.

### Backend (Python)
```bash
cd backend

# Setup (first time)
python -m venv venv
venv\Scripts\activate        # Windows
source venv/bin/activate     # Linux/Mac
pip install -r requirements.txt

# Run locally (requires Qdrant, Redis, Neo4j running separately)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run required infrastructure (Docker, from backend/ directory)
docker compose up -d qdrant redis neo4j jaeger
```

### Docker (Recommended)
```bash
cd backend
docker compose up -d --build   # Start Qdrant, Redis, Neo4j, Jaeger + Backend
docker compose logs -f         # Stream logs
docker compose logs -f backend # Backend logs only
docker compose down            # Stop all
```

Ollama must run on the **host** machine (not in Docker) — `ollama serve`.

### Sarvam 30B Model Setup
```bash
cd backend/models
chmod +x setup_sarvam.sh && ./setup_sarvam.sh   # Linux/Colab
.\setup_sarvam.ps1                               # Windows
```

## Service URLs

| Service | URL |
|---------|-----|
| Backend API + Swagger | http://localhost:8000/docs |
| Ingestion Portal | http://localhost:8000/ingest/ |
| Gradio Chat UI | http://localhost:8000/ui |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Prometheus Metrics | http://localhost:8000/metrics |
| Health Check | http://localhost:8000/api/health |
| Jaeger Traces | http://localhost:16686 |
| Neo4j Browser | http://localhost:7474 |

## Configuration

All backend config lives in `backend/.env` (copy from `backend/.env.example`). Key settings:

- `OLLAMA_MODEL` — default `sarvam-30b:latest` (the primary LLM)
- `QDRANT_URL` — default `http://localhost:6333`
- `QDRANT_LOCAL_PATH` — set for local (no-Docker) Qdrant mode
- `WHISPER_MODEL` — `large-v3` (uses `faster-whisper` backend by default)
- `WHISPER_COMPUTE_TYPE` — `float16` for GPU, `int8` or `float32` for CPU

Config is loaded via `app/config.py` (`pydantic-settings`). Import as `from app.config import settings`.

## Architecture: The Multi-Node Anti-Hallucination Pipeline

The chat endpoint (`POST /api/chat`) runs every message through a LangGraph State Machine with ~20 specialized nodes. The original "12-layer" conceptual model has been expanded with additional quality gates and retrieval enhancements.

### Pre-Graph (handled in `main.py`)
1. **Zero-Shot Input Rail** (`guardrails/rails.py`) — blocks harmful/off-topic input
2. **Serene Mind Distress Detector** (`services/depression_detector.py`) — assesses emotional state; does NOT bypass RAG — distress queries run through the full pipeline to retrieve compassionate teachings

### LangGraph Pipeline (`rag/graph.py`)

**Entry:** `intent_router`
- Routes to `handle_distress` / `handle_meditation` / `handle_casual` / `resolve_followup`

**QUERY path (full anti-hallucination chain):**
- `resolve_followup` — resolves pronouns/references from conversation history
- `decompose_query` — splits complex questions into atomic sub-queries
- `navigate_knowledge_tree` (parallel with `generate_hyde`) — PageIndex-inspired cluster selection + HyDE hypothetical answer generation
- `retrieve_documents` — two-phase hybrid retrieval (RAPTOR summaries + leaf chunks + LightRAG graph + Parent-Child resolution + MMR diversity re-ranking)
- `rerank_documents` — Cascaded ColBERT + CrossEncoder re-ranking
- `grade_documents` — CRAG batch relevance grading (single LLM call for all docs)
- `check_context_sufficiency` — iterative sufficiency check; clears cluster filters if insufficient
- Conditional branch: relevant → `enrich_context` | rewrite → `rewrite_query` (max 3x) | fallback → `handle_fallback`
- `enrich_context` — fetches neighbor chunks for broader context
- `context_engineer` — assembles structured prompt layers (persona, knowledge, user state, instructions)
- `generate_answer` — inline hint extraction + context-only generation (merged Stimulus RAG + generation)
- `reflect_on_answer` — Self-Reflection RAG: LLM evaluates answer against retrieved context for hallucinations
- Conditional branch: valid → `verify_answer` | needs_correction → `rewrite_query` (max 3x) | exhausted → `handle_fallback`
- `verify_answer` — combined Self-RAG + CoVe verification in one LLM call (faithfulness + claim verification + confidence score)
- `check_contradiction` — multi-turn contradiction detection against conversation history
- `explain_retrieval` (parallel) — generates 1-sentence reasoning for each top citation
- `format_final_answer` — confidence-based graduated responses, citation formatting, caveats

**Post-Graph (handled in `main.py`)**
- **Zero-Shot Output Rail** — moderates/blocks harmful output
- **Telemetry Logging** — query trace + response trace saved to telemetry DB

The `GraphState` TypedDict in `rag/states.py` is the data contract flowing through all nodes. It includes `request_id` for end-to-end log correlation.

## Architecture: Ingestion Pipeline

`POST /api/ingest` triggers `ingest/pipeline.py:IngestionPipeline.ingest_url()`:

1. Detect URL type (YouTube video / playlist / image)
2. Fetch transcript (3-tier: manual captions → Whisper → auto-captions) or OCR
3. Correct transcript (LLM via `corrector.py`)
4. Audit quality (LLM via `auditor.py`) — rejects low-quality/irrelevant content
5. Clean text (`cleaner.py`)
6. Chunk with `RecursiveCharacterTextSplitter(500 chars, 50 overlap)`
7. Embed with `all-MiniLM-L6-v2` → upsert to Qdrant (level 0: leaf chunks)
8. Build Parent-Child index (`raptor.py`): chunks with metadata → upsert to Qdrant

Playlist ingestion uses concurrent workers (`TRANSCRIPT_CONCURRENT_WORKERS=4`).

## Dependency Injection Pattern

`backend/app/dependencies.py` is the **composition root**. `ServiceContainer` creates all singleton service instances in dependency order and holds them for the lifetime of the application. Import via `get_container()`. Never instantiate services directly in route handlers.

## Frontend ↔ Backend Integration

The React frontend (`src/lib/aiService.ts`) supports three modes:
- `placeholder` — offline mode with canned responses (default)
- `custom` — points to the FastAPI backend at `POST /api/chat`
- `openai` — direct OpenAI API calls

The backend `ChatRequest` expects `{ messages, user_message, meditation_step }`. The frontend sends the full conversation history on each turn.

## Terminology (from SPEC_DEV.md)

| Term | Meaning |
|------|---------|
| **Stimulus RAG** | Extract key hint phrases from retrieved docs before generation |
| **CRAG** | Corrective RAG — grade docs, rewrite query if poor, loop up to 3x |
| **Self-RAG** | LLM checks its own answer for faithfulness to retrieved context |
| **CoVe** | Chain of Verification — generate sub-questions to fact-check the answer |
| **Parent-Child Retrieval** | 400-char child chunks in Qdrant, 1500-char Parent Context injected into the LLM |
| **Beautiful State** | Core teaching concept — state of calm, joy, connection |
| **Serene Mind** | 4-step guided meditation flow triggered by distress detection |

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.
