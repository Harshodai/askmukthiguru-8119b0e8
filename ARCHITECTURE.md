# Architecture Overview

**Mukthi Guru** is a privacy-first, zero-hallucination AI spiritual guide grounded in Sri Preethaji & Sri Krishnaji's teachings. It uses a React frontend + Python FastAPI backend with a 12-layer RAG pipeline. All processing runs locally with a $0 budget constraint.

## System Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                     FRONTEND (React + Vite)                     │
│  src/pages/ChatPage.tsx → ChatInterface.tsx → aiService.ts      │
│  src/pages/Index.tsx (landing page)                             │
│  Voice: useSpeechRecognition.ts / useTextToSpeech.ts            │
│  Storage: chatStorage.ts, meditationStorage.ts (localStorage)   │
└────────────────────┬────────────────────────────────────────────┘
                     │ POST /api/chat
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI — app/main.py)                 │
│                                                                 │
│  ┌── Layer 1: NeMo Input Rail (guardrails/rails.py) ──────┐    │
│  │   Blocks harmful/off-topic input via phrase matching    │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌── Layer 2: Depression Detector (depression_detector.py) ┐    │
│  │   distilroberta-finetuned-depression → fast-path        │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌── Layers 3–11: LangGraph Pipeline (rag/graph.py) ──────┐    │
│  │   intent_router → decompose → retrieve → rerank →       │    │
│  │   grade (CRAG loop) → extract_hints (Stimulus RAG) →    │    │
│  │   generate → check_faithfulness (Self-RAG) →             │    │
│  │   verify_answer (CoVe) → format_final_answer             │    │
│  └────────────────────────────────────────────────────────┘    │
│  ┌── Layer 12: NeMo Output Rail ──────────────────────────┐    │
│  │   Moderates generated output                            │    │
│  └────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

---

## Key Files and Their Roles

### Backend Core (`backend/app/`)

| File | Role |
|---|---|
| `main.py` | FastAPI entry point. Routes: `/api/chat`, `/api/ingest`, `/api/health`, `/metrics`. Wires the 12-layer pipeline. Mounts Gradio UI and ingest-ui static files. |
| `config.py` | Pydantic Settings singleton. Reads all config from `.env` (Ollama, Qdrant, Whisper, RAG params, RAPTOR, etc). |
| `dependencies.py` | **Composition root.** `ServiceContainer` creates all service singletons in dependency order with thread-safe double-checked locking. |
| `gradio_ui.py` | Optional Gradio chat interface mounted at `/ui`. |
| `metrics.py` | Prometheus metrics (request latency, depression events, meditation sessions). |

### Services (`backend/services/`)

| File | Role |
|---|---|
| `ollama_service.py` | **Single LLM gateway.** Wraps `ChatOllama` with 11 specialized methods: `classify_intent`, `grade_relevance`, `check_faithfulness`, `extract_hints`, `rewrite_query`, `verify_claims`, `summarize`, `decompose_query`, etc. |
| `embedding_service.py` | Dual-model: `all-MiniLM-L6-v2` (384-dim bi-encoder) + `cross-encoder/ms-marco-MiniLM-L-6-v2` (reranker). |
| `qdrant_service.py` | Vector DB abstraction. Supports local (embedded) or Docker mode. Handles upsert batching (100), hybrid search, paginated scroll. |
| `ocr_service.py` | EasyOCR wrapper (en/hi/te). Lazy-loads the model on first use. |
| `depression_detector.py` | `distilroberta-finetuned-depression` classifier. Returns `True` if distress score > 0.6. Runs in a thread pool. |

### RAG Pipeline (`backend/rag/`)

| File | Role |
|---|---|
| `states.py` | `GraphState` TypedDict — the data contract flowing through all pipeline nodes (30+ fields). |
| `prompts.py` | All LLM prompt templates (zero external deps). Includes `GURU_SYSTEM_PROMPT`, `STIMULUS_RAG_PROMPT`, `MEDITATION_STEPS`, etc. |
| `nodes.py` | All 15 async node functions: `intent_router`, `decompose_query`, `retrieve_documents` (with HyDE), `rerank_documents`, `grade_documents`, `rewrite_query`, `extract_hints`, `generate_answer`, `check_faithfulness`, `verify_answer`, `format_final_answer`, plus handlers for casual/distress/meditation/fallback. |
| `graph.py` | Assembles the `StateGraph` — wires nodes with conditional edges (intent routing, CRAG loop, faithfulness gate). Factory: `build_rag_graph()`. |
| `meditation.py` | Serene Mind 4-step guided meditation flow. Pure helper functions for distress/meditation nodes. |

### Ingestion Pipeline (`backend/ingest/`)

| File | Role |
|---|---|
| `pipeline.py` | **Orchestrator.** Routes by URL type (video/playlist/image). Full sequence: fetch -> correct -> audit -> clean -> chunk -> embed -> upsert -> RAPTOR. |
| `youtube_loader.py` | 4-tier transcript extraction: manual captions -> auto captions -> Whisper (faster-whisper/openai-whisper) -> yt-dlp subtitles. Concurrent playlist processing. |
| `raptor.py` | RAPTOR hierarchical indexing. K-Means clustering -> LLM summarization -> level-1 embeddings in Qdrant. Uses UMAP for dimensionality reduction. |
| `corrector.py` | LLM-based transcript correction (fixes homophones, spiritual proper nouns). |
| `auditor.py` | LLM-based quality gate — rejects gibberish/off-topic content before indexing. |
| `cleaner.py` | Regex pipeline: removes `[Music]` tags, timestamps, filler words, normalizes whitespace. |
| `image_loader.py` | Thin facade over `OCRService` for image URL ingestion. |

### Guardrails (`backend/guardrails/`)

| File | Role |
|---|---|
| `rails.py` | NeMo Guardrails integration (fail-open). Phrase-matching for input blocking and output moderation. |
| `config/config.yml` | NeMo config: model, system instructions, flow references. |
| `config/topics.co` | Colang flows: blocks crypto/politics/medical, redirects self-harm to crisis hotlines. |

### Frontend (`src/`)

| File | Role |
|---|---|
| `pages/ChatPage.tsx` | Thin wrapper rendering `ChatInterface`. |
| `components/chat/ChatInterface.tsx` | Core chat UI (~540 lines). Manages conversations, voice I/O, TTS, sidebar, language switching. |
| `lib/aiService.ts` | AI provider abstraction: `placeholder` (canned), `custom` (FastAPI backend), `openai` modes. |
| `lib/chatStorage.ts` | localStorage-based multi-conversation persistence (capped at 10). |
| `lib/meditationStorage.ts` | Meditation session tracking with streak calculation. |
| `hooks/useSpeechRecognition.ts` | Web Speech API wrapper (6 Indian languages). |
| `hooks/useTextToSpeech.ts` | Web Speech Synthesis with language-specific voice selection. |

### Ingestion Portal (`ingest-ui/`)

| File | Role |
|---|---|
| `index.html` + `app.js` | Standalone vanilla JS ingestion UI. URL input, progress polling, health monitoring. |
| `chat.html` + `chat.js` | Simple standalone chat (no React). |
| `style.css` | Shared dark spiritual theme for both pages. |
| `nginx.conf` | Nginx config for standalone Docker deployment (alternative to FastAPI static mount). |

### Deployment & Config

| File | Role |
|---|---|
| `backend/docker-compose.yml` | Qdrant + Backend containers. Ollama runs on host for GPU access. |
| `backend/Dockerfile` | Multi-stage Python 3.12 build with ffmpeg for Whisper. |
| `backend/models/Modelfile.sarvam30b` | Ollama Modelfile for Sarvam 30B (Q4_K_M quantization, LLaMA-3 chat template). |
| `backend/models/setup_sarvam.sh` | Linux/Colab setup: downloads GGUF from HuggingFace, creates Ollama model. |
| `backend/models/setup_sarvam.ps1` | Windows equivalent of setup script. |
| `backend/colab/setup.py` | Colab deployment: installs deps, starts Ollama, launches backend, exposes via ngrok. |
| `backend/colab/transfer.py` | Backup/restore Qdrant data to Google Drive for Colab persistence. |
| `backend/.env.example` | Template for all backend environment variables. |
| `backend/requirements.txt` | Python dependencies (FastAPI, LangChain, LangGraph, qdrant-client, sentence-transformers, etc). |

### Root-Level Scripts

| File | Role |
|---|---|
| `mukthi_guru_colab_optimized.py` | Earlier monolithic version (v5.0) predating the modular backend. Uses Sarvam 2B + unsloth. Historical reference. |
| `test_ocr.py` | One-off Tesseract OCR test script (production uses EasyOCR instead). |

---

## Dependency Flow

```
main.py
  ├── app.config (settings singleton)
  ├── app.dependencies (get_container, startup, shutdown)
  ├── app.metrics (REQUEST_LATENCY, REQUEST_COUNT, metrics_endpoint)
  ├── app.gradio_ui (create_demo)
  ├── rag.graph (create_initial_state)
  └── services.depression_detector (DepressionDetector — global instance)

dependencies.py (ServiceContainer)
  ├── services.qdrant_service (QdrantService)
  ├── services.embedding_service (EmbeddingService)
  ├── services.ollama_service (OllamaService)
  ├── services.ocr_service (OCRService)
  ├── guardrails.rails (GuardrailsService)
  ├── ingest.pipeline (IngestionPipeline)
  └── rag.graph (build_rag_graph)

rag/graph.py
  ├── rag/states.py (GraphState TypedDict)
  └── rag/nodes.py (all node functions)
        ├── rag/prompts.py (prompt templates)
        ├── rag/meditation.py (Serene Mind flow)
        └── services/ (ollama, embedding, qdrant — via init_services())

ingest/pipeline.py
  ├── ingest/youtube_loader.py
  ├── ingest/image_loader.py
  ├── ingest/corrector.py
  ├── ingest/auditor.py
  ├── ingest/cleaner.py
  ├── ingest/raptor.py
  └── services/ (qdrant, embedding, ollama, ocr)

All services import:
  └── app.config (settings) — shared singleton
```

---

## Chat Pipeline Detail (POST /api/chat)

1. **NeMo Input Rail** (`guardrails/rails.py`) — blocks harmful/off-topic input
2. **Depression Detector** (`services/depression_detector.py`) — fast-path to meditation if distress score > 0.6
3. **Intent Router** (`rag/nodes.py`) — classifies as DISTRESS / CASUAL / QUERY / MEDITATION_CONTINUE
4. **Decompose Query** — splits complex questions into 2-3 sub-queries
5. **Retrieve Documents** — embeds query (optionally with HyDE), searches Qdrant (hybrid dense+BM25)
6. **Rerank Documents** — CrossEncoder re-scoring, returns top-3
7. **Grade Documents** (CRAG) — LLM binary relevance check per document
8. **CRAG Loop** — if docs irrelevant, rewrite query and re-retrieve (max 3 iterations)
9. **Extract Hints** (Stimulus RAG) — pulls 3-5 key evidence phrases from docs
10. **Generate Answer** — LLM generates grounded answer using context + hints
11. **Check Faithfulness** (Self-RAG) — LLM verifies answer against context
12. **Verify Answer** (CoVe) — generates sub-questions to fact-check; PASS/FAIL verdict
13. **Format Final Answer** — appends citations, handles unfaithful fallback
14. **NeMo Output Rail** — moderates generated output

## Ingestion Pipeline Detail (POST /api/ingest)

1. Detect URL type (YouTube video / playlist / channel / image)
2. Fetch transcript via 4-tier fallback: manual captions -> auto captions -> Whisper -> yt-dlp subtitles (or OCR for images)
3. Correct transcript (LLM fixes homophones, spiritual proper nouns)
4. Audit quality (LLM rejects gibberish/off-topic; samples 3 random 500-char chunks)
5. Clean text (regex: removes `[Music]` tags, timestamps, filler words)
6. Chunk with `RecursiveCharacterTextSplitter(500 chars, 50 overlap)`
7. Embed with `all-MiniLM-L6-v2` -> upsert to Qdrant (level 0: leaf chunks)
8. Build RAPTOR tree: K-Means cluster -> UMAP reduce -> LLM summarize clusters -> embed summaries -> upsert to Qdrant (level 1: summary nodes)

Playlist ingestion runs transcript extraction concurrently (`TRANSCRIPT_CONCURRENT_WORKERS=4`).

## Frontend Architecture

The React app (Vite + TypeScript + shadcn/ui + Tailwind) has two main pages:

- **Landing page** (`/`) — Hero, Meet the Gurus, How It Works, About Meditation sections
- **Chat page** (`/chat`) — Full-featured chat with:
  - Multi-conversation management (localStorage, capped at 10)
  - Speech-to-text (Web Speech API, 6 Indian languages)
  - Text-to-speech (Web Speech Synthesis, language-aware voice selection)
  - Serene Mind meditation modal with session tracking
  - 3D tilt card effects on landing page

The `aiService.ts` abstraction supports three modes:
- `placeholder` — offline demo with canned spiritual quotes
- `custom` — connects to FastAPI backend at `POST /api/chat`
- `openai` — direct OpenAI API calls

## Terminology

| Term | Meaning |
|------|---------|
| **Stimulus RAG** | Extract key hint phrases from retrieved docs before generation |
| **CRAG** | Corrective RAG — grade docs, rewrite query if poor, loop up to 3x |
| **Self-RAG** | LLM checks its own answer for faithfulness to retrieved context |
| **CoVe** | Chain of Verification — generate sub-questions to fact-check the answer |
| **RAPTOR** | Recursive clustering + summarization of chunks into a 2-level tree |
| **HyDE** | Hypothetical Document Embedding — generate a hypothetical answer to improve retrieval |
| **Beautiful State** | Core teaching concept — state of calm, joy, connection |
| **Serene Mind** | 4-step guided meditation flow triggered by distress detection |
