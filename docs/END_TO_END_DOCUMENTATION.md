# AskMukthiGuru — End-to-End Documentation

## 1. Executive Summary & Vision

**AskMukthiGuru** is an AI-powered spiritual guide strictly rooted in the teachings of **Sri Preethaji & Sri Krishnaji**. Built with a focus on delivering grounded, accurate, and safe responses, the system utilizes a multi-layer RAG pipeline, real-time guardrails, and a conversational UI.

### Project Constraints & Philosophy
*   **$0 Budget:** Operates with 100% local processing (no external API calls at inference).
*   **Open-Source Core:** Leverages entirely open-source dependencies.
*   **Groundedness:** Strict adherence to only approved teachings. Hallucination rate strictly targeted below 1%.
*   **Radical Simplicity:** Simplest robust solutions prioritized to avoid over-engineering.

---

## 2. High-Level Architecture

The platform architecture is structured across multiple tiers handling User Interfaces, API interactions, LLM execution, Vector Indexing, and Monitoring.

### Infrastructure Mapping

| Component | Technology | Port | Purpose |
|---|---|---|---|
| **Frontend** | Vite React 18 + TailwindCSS + shadcn/ui | `80` (Nginx) | User interface for chat and landing. |
| **Backend API** | FastAPI | `8000` | RAG orchestration, content ingestion, API endpoints. |
| **LLM Execution** | Ollama | `11434` (Host) | Local LLM hosting (Llama 3.2 8B/Sarvam 30B via GGUF). |
| **Vector DB** | Qdrant | `6333` | Dense vector storage and retrieval. |
| **Knowledge Graph** | Neo4j | `7474` / `7687` | Relationships for LightRAG. |
| **Caching** | Redis | `6379` | Fast response and session caching. |
| **Tracing** | Jaeger | `16686` | OpenTelemetry tracing for RAG pipeline steps. |
| **Auth & Profiles** | Supabase | External | Auth (Google/Email), Profile metadata, Chat history. |

### System Diagram

```mermaid
graph LR
    U[👤 Seeker / Admin] --> FE[React Frontend (Port 80)]
    FE -->|HTTP POST /api/chat| BE[FastAPI Backend (Port 8000)]
    FE -->|HTTP POST /api/ingest| BE
    BE --> OL[Ollama: llama3.2 8B / Sarvam 30B]
    BE --> QD[(Qdrant Vector DB)]
    BE --> NG[NeMo Guardrails]
    BE --> N4J[(Neo4j Knowledge Graph)]
    BE --> WH[Whisper tiny]
    BE --> OCR[EasyOCR]

    style FE fill:#f9f,stroke:#333
    style BE fill:#bbf,stroke:#333
    style OL fill:#fbb,stroke:#333
    style QD fill:#bfb,stroke:#333
    style N4J fill:#fbf,stroke:#333
```

---

## 3. Product Features & Specifications

### 3.1 Core Features
*   **Conversational RAG Chat:** Ask spiritual questions and receive answers cited from video transcripts and texts.
*   **Guided Meditation (Serene Mind):** A 4-step interactive meditation flow automatically triggered when distress is detected.
*   **Daily Teachings:** Real-time push of teachings via Supabase real-time subscriptions.
*   **Multi-language Support:** Web Speech API wrapper for 6 Indian languages, with text-to-speech fallback.
*   **Admin Portals:** Dedicated web interfaces for adding content (`/static-ingest`) and viewing logs (`/admin`).

### 3.2 What AskMukthiGuru is NOT
*   No Fine-Tuning pipeline (Stimulus RAG replaces this).
*   No Whatsapp/Telegram integration (yet).
*   No real-time voice streaming (turn-based text/voice only).

---

## 4. The 12-Layer RAG Pipeline (LangGraph Flow)

The heart of the backend is a complex state machine built with LangGraph to enforce accuracy.

### 4.1 The Pipeline Steps

1.  **Zero-Shot Input Rail:** Instructor-based LLM guardrails block harmful or out-of-scope topics.
2.  **Intent Classification:** (`DISTRESS` | `CASUAL` | `QUERY` | `MEDITATION_CONTINUE`). Fast-paths non-queries.
3.  **Query Decomposition:** Splits complex, multi-part questions into simpler sub-queries.
4.  **Knowledge Tree Navigation:** Uses Parent-Child retrieval (RAPTOR level 1 summary node -> level 0 leaf).
5.  **Hybrid Retrieval:** Dense + BM25 search against Qdrant, augmented with LightRAG (Neo4j).
6.  **Cross-encoder Reranking:** Re-scores top-20 documents to top-3 using `ms-marco-MiniLM-L-6-v2`.
7.  **CRAG Document Grading:** Binary relevance check per document. Irrelevant docs trigger query rewrite (max 3 loops).
8.  **Stimulus RAG (Hint Extraction):** Extracts key evidence phrases from retrieved docs before full generation.
9.  **Context-aware Generation:** Answer generation incorporating memory context.
10. **Self-RAG Faithfulness Check:** LLM checks if its own answer is faithful to the retrieved chunks.
11. **Chain of Verification (CoVe):** Generates sub-questions to fact-check the drafted answer.
12. **Zero-Shot Output Rail:** Instructor-based final check for toxicity and tone.

### 4.2 State Machine (GraphState)

The data contract (`backend/rag/states.py`) carries state through the pipeline:
*   `question`, `chat_history`, `sub_queries`
*   `documents`, `hints`, `generation`, `citations`
*   `intent`, `meditation_step`
*   Verification flags: `relevance_score`, `faithfulness_score`

---

## 5. Ingestion Pipeline

Admins provide YouTube or Image URLs. The system converts these into vector embeddings.

### 5.1 Flow
1.  **Fetch & Transcribe:**
    *   **YouTube:** Tries Manual Captions → Auto Captions → Whisper Tiny fallback → yt-dlp.
    *   **Images:** Download → EasyOCR.
2.  **Correction:** LLM fixes homophones and spiritual proper nouns.
3.  **Auditor Gate:** LLM rejects gibberish.
4.  **Cleaning:** Regex removes `[Music]`, filler, and timestamps.
5.  **Chunking:** `RecursiveCharacterTextSplitter` (500 chars, 50 overlap).
6.  **Embedding & Indexing (Qdrant):** Level-0 (leaf) chunks are stored using `all-MiniLM-L6-v2`.
7.  **RAPTOR Hierarchical Indexing:** K-Means clustering -> LLM summarization -> Level-1 embedding -> Qdrant storage.

---

## 6. Data Storage & Schemas

### 6.1 Supabase Schema (PostgreSQL)
Managed via migrations in `supabase/migrations/`:
*   `profiles`: Display name, avatar, language prefs.
*   `conversations` / `chat_messages`: Long-term chat storage.
*   `conversation_memories`: Compact backend summaries to maintain continuity.
*   `user_roles`: RBAC (Admin designation).
*   `daily_teachings`: Expiration-based teaching cards pushed via Supabase realtime.

### 6.2 Qdrant Collections
Uses dense vectors (384-dim `all-MiniLM-L6-v2`) and sparse vectors for BM25.

### 6.3 Neo4j
LightRAG knowledge graph capturing entities and relationships from transcriptions.

---

## 7. Frontend Details

*   **Stack:** Vite, React 18, Tailwind, shadcn/ui.
*   **Routing:** React Router. `/` (Landing), `/chat` (App), `/auth` (Login), `/admin` (Dashboard).
*   **Auth Flow:**
    *   Supabase provides standard email/password and Google OAuth.
    *   Admin routes (`useAdminGuard`) invoke Postgres Row Level Security (RLS) and RPC `has_role(auth.uid(), 'admin')`.
*   **Chat State:**
    *   Uses a combination of `localStorage` (capped multi-session) and server-sync for persistent conversations.
    *   Streamed responses are checkpointed to `sessionStorage` every 500ms to recover from sudden disconnects.

---

## 8. Backend Service Components

Located in `backend/services/`:
*   `qdrant_service.py`: Qdrant client abstraction for hybrid search.
*   `embedding_service.py`: Handles `all-MiniLM-L6-v2` and `ms-marco` reranker.
*   `ollama_service.py`: Bridge to local LLMs.
*   `ocr_service.py`: EasyOCR wrapper.
*   `lightrag_service.py`: Integration with LightRAG/Neo4j.
*   `depression_detector.py`: Thread-pooled DistilRoBERTa model flagging distress (`score > 0.6`).

---

## 9. Deployment & Infrastructure

### 9.1 Docker Compose (Recommended Local/Prod)
```bash
cd backend
docker compose up -d --build
```
Spins up Nginx(Frontend), FastAPI(Backend), Qdrant, Redis, Neo4j, and Jaeger.
*Note: Ollama runs on the host machine to access the GPU natively.*

### 9.2 Colab Notebook
A single-click deployment option (`AskMukthiGuru.ipynb` / `backend/colab/setup.py`) optimized for free T4 GPUs. It mounts Google Drive for Qdrant storage persistence and uses `pyngrok` to expose the API.

---

## 10. Development, Testing & Observability

### 10.1 Dependency Flow
*   `app.config` defines singleton configuration.
*   `app.dependencies` handles ServiceContainer injection (Singleton DI).

### 10.2 Testing Framework
*   **Frontend:** Vitest for components and `useSpeechRecognition` hooks.
*   **Backend:** `pytest` (e.g., `test_chat.py`, `test_rag.py`).
*   **Evaluation:** `ragas` and `scripts/benchmarks/askmukthiguru_ruthless_benchmark.py` for RAG pipeline testing.

### 10.3 Observability
OpenTelemetry tracks Request Latency and LLM spans, exporting to a local Jaeger instance on port `16686`.

---

## 11. Security, Permissions & Safety Guardrails

### 11.1 Content Permissions
*   **Strict Adherence:** Project requires written copyright clearance before indexing Sri Preethaji & Sri Krishnaji content.
*   **State Tracking:** A `permissions_confirmed` flag exists in configuration; deployment is paused until this is legally confirmed.

### 11.2 Safety Guardrails (NeMo Replacement)
*   The system uses Zero-Shot LLM Input and Output rails (via Instructor) instead of NeMo Guardrails to identify:
    *   Self-harm triggers (immediately surfaces crisis hotlines).
    *   Off-topic (Medical, Crypto, Politics) queries.
*   RBAC in Supabase ensures telemetry and ingestion are admin-only.

---
*Created per project specifications and architectural guidelines.*
## 12. Technical Specifications: APIs and Data Models

### 12.1 Backend API Endpoints (FastAPI)

#### **Chat Endpoints (`app/main.py`)**
*   `POST /api/chat/stream`: The core conversational streaming endpoint.
    *   **Input**: JSON payload containing `messages`, `user_message`, `meditation_step`, and `session_id`.
    *   **Output**: Server-Sent Events (SSE). Streams `event: token`, `event: thinking`, and `event: done` (containing citations and intent).
    *   **Flow**: Validates request → Maps `session_id` → Loads compact user memory context → Passes through NeMo guardrails → Triggers LangGraph state machine → Yields streaming tokens → Saves conversation memory.

*   `POST /api/chat`: Non-streaming legacy chat endpoint.

#### **Ingestion Endpoints (`app/main.py`)**
*   `POST /api/ingest`: Submits content for vectorization.
    *   **Input**: `IngestRequest` (URL, chunk strategy parameters).
    *   **Output**: `IngestResponse` with a tracking status. Kicks off a BackgroundTask for YouTube extraction, transcription, chunking, and embedding.
*   `GET /api/ingest/status`: Retrieves the progress of background ingestion tasks.

#### **User & Profile Endpoints (`app/main.py`)**
*   `GET /api/profile`: Fetches the authenticated user's spiritual profile, language preferences, and meditation level.
*   `PUT /api/profile`: Updates user metadata.

#### **Admin Endpoints (`routers/admin.py`)**
*   `GET /admin/traces`: Fetches recent query and response traces for observability.
*   `GET /admin/kpis`: Retrieves aggregated KPIs (like hallucination rates, distress triggers) over a date range.

#### **Feedback Endpoints (`routers/feedback.py`)**
*   `POST /feedback/`: Submits user feedback (upvote/downvote and optional text) for a generated answer.
*   `GET /feedback/history`: Retrieves recent feedback history for the admin dashboard.

### 12.2 Data Models & Schemas

The system uses Pydantic schemas for data validation (`backend/schemas/`):

*   **`FeedbackCreate` & `FeedbackResponse`**: Models user ratings. Includes `query`, `answer`, `rating` (1/-1), `feedback_text`, and `metadata_json`.
*   **`UserRead`, `UserCreate`, `UserUpdate`**: FastAPI-Users base models defining user structure (UUID, name, email, auth flags).
*   **`ConversationMemory`** (`services/user_profile_service.py`): Compact historical representation of a user session. Includes `session_id`, `messages`, `key_insights`, `emotional_arc`, and `follow_up_suggestions`.

---

## 13. Technical Specifications: LangGraph State Machine

The orchestration layer (`backend/rag/`) enforces the 12-layer pipeline.

### 13.1 GraphState (`rag/states.py`)
A `TypedDict` defining the entire state during pipeline execution:
*   **Input**: `question`, `chat_history`
*   **Routing**: `intent`
*   **Retrieval**: `documents`, `reranked_docs`, `hyde_text`
*   **CRAG**: `relevant_docs`, `grading_reasons`, `rewrite_count`, `rewritten_query`
*   **Stimulus RAG**: `hints`
*   **Verification**: `is_faithful`, `needs_correction`, `reflection_feedback`, `confidence_score`
*   **Generation**: `answer`, `citations`, `final_answer`

### 13.2 Core Nodes (`rag/nodes.py`)
Each graph step is an async Python function mutating `GraphState`:
*   `intent_router()`: Classifies the query (`DISTRESS`, `QUERY`, `CASUAL`). Short-circuits the graph if not a query.
*   `generate_hyde()`: Generates a hypothetical document embedding to improve semantic search matching.
*   `retrieve_documents()`: Executes vector search on Qdrant using the query (or rewritten query).
*   `rerank_documents()`: Re-scores documents using a CrossEncoder.
*   `grade_documents()`: Uses an LLM to evaluate if retrieved chunks are relevant.
*   `check_context_sufficiency()`: Evaluates the total relevant context. Triggers a `rewrite_query()` loop if insufficient.
*   `generate_answer()`: Prompts the LLM with the context, hints, and system persona to formulate an answer.
*   `reflect_on_answer()` & `verify_answer()`: Self-RAG steps where the system verifies if its own generated text hallucinates facts.

---

## 14. Technical Specifications: Frontend Architecture

The frontend is built with React 18 and Vite, located in `src/`.

### 14.1 Key Directories
*   **`src/pages/`**: React Router top-level views.
    *   `ChatPage.tsx`: The primary RAG interface.
    *   `AuthPage.tsx`: Supabase authentication UI.
    *   `ProfilePage.tsx`: User preference management.
    *   `PracticesPage.tsx`: Library of spiritual practices.
*   **`src/components/chat/`**: Complex logic specific to the chat interface.
    *   `ChatInterface.tsx`: Manages the main chat stream, SSE event processing, and local conversational state.
    *   `ChatMessage.tsx`: Renders individual Markdown bubbles and citations.
    *   `DesktopSidebar.tsx`: Session history management.
    *   `SereneMindModal.tsx`: The interactive 4-step guided meditation UI triggered by a `DISTRESS` intent.
    *   `DailyTeaching.tsx`: Real-time Supabase subscription component rendering daily wisdom cards.
*   **`src/hooks/`**: Custom React hooks.
    *   `useSpeechRecognition.ts`: Interface with the browser Web Speech API for multi-lingual dictation.
    *   `useTextToSpeech.ts`: Browser-based speech synthesis.
