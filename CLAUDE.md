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
    ├── guardrails/rails.py # NeMo Guardrails input/output rails
    ├── models/            # Sarvam 30B setup scripts + Modelfile
    ├── colab/             # Google Colab setup & backup scripts
    └── docker-compose.yml # Qdrant + Backend (Ollama runs on host)
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

# Run locally (requires Qdrant running separately)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run Qdrant (Docker, from backend/ directory)
docker run -p 6333:6333 -p 6334:6334 -v ${PWD}/qdrant_storage:/qdrant/storage qdrant/qdrant:v1.13.2
```

### Docker (Recommended)
```bash
cd backend
docker compose up -d --build   # Start Qdrant + Backend
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

## Configuration

All backend config lives in `backend/.env` (copy from `backend/.env.example`). Key settings:

- `OLLAMA_MODEL` — default `sarvam-30b:latest` (the primary LLM)
- `QDRANT_URL` — default `http://localhost:6333`
- `QDRANT_LOCAL_PATH` — set for local (no-Docker) Qdrant mode
- `WHISPER_MODEL` — `large-v3` (uses `faster-whisper` backend by default)
- `WHISPER_COMPUTE_TYPE` — `float16` for GPU, `int8` or `float32` for CPU

Config is loaded via `app/config.py` (`pydantic-settings`). Import as `from app.config import settings`.

## Architecture: The 12-Layer Pipeline

The chat endpoint (`POST /api/chat`) runs every message through:

1. **NeMo Input Rail** (`guardrails/rails.py`) — blocks harmful/off-topic input
2. **Depression Detector** (`services/depression_detector.py`) — fast-path to meditation
3–11. **LangGraph State Machine** (`rag/graph.py`) — assembled from nodes in `rag/nodes.py`:
   - `intent_router` → DISTRESS / CASUAL / QUERY
   - QUERY path: `decompose_query` → `retrieve_documents` → `rerank_documents` → `grade_documents`
   - CRAG loop: if docs irrelevant → `rewrite_query` → retrieve again (max 3x)
   - `extract_hints` (Stimulus RAG) → `generate_answer` → `check_faithfulness` (Self-RAG) → `verify_answer` (CoVe) → `format_final_answer`
12. **NeMo Output Rail** — moderates/blocks harmful output

The `GraphState` TypedDict in `rag/states.py` is the data contract flowing through all nodes.

## Architecture: Ingestion Pipeline

`POST /api/ingest` triggers `ingest/pipeline.py:IngestionPipeline.ingest_url()`:

1. Detect URL type (YouTube video / playlist / image)
2. Fetch transcript (3-tier: manual captions → Whisper → auto-captions) or OCR
3. Correct transcript (LLM via `corrector.py`)
4. Audit quality (LLM via `auditor.py`) — rejects low-quality/irrelevant content
5. Clean text (`cleaner.py`)
6. Chunk with `RecursiveCharacterTextSplitter(500 chars, 50 overlap)`
7. Embed with `all-MiniLM-L6-v2` → upsert to Qdrant (level 0: leaf chunks)
8. Build RAPTOR tree (`raptor.py`): cluster chunks → summarize → embed summaries → upsert to Qdrant (level 1: summary nodes)

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
| **RAPTOR** | Recursive clustering + summarization of chunks into a 2-level tree |
| **Beautiful State** | Core teaching concept — state of calm, joy, connection |
| **Serene Mind** | 4-step guided meditation flow triggered by distress detection |
