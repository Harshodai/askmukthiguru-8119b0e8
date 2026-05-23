# AskMukthiGuru — Complete End-to-End System Reference Manual
*Version 1.0.0 — Production Reference (May 2026)*

AskMukthiGuru is an enterprise-grade, privacy-first, zero-hallucination AI spiritual companion grounded in the public teachings of **Sri Preethaji and Sri Krishnaji**. This document serves as the absolute source of truth for both frontend and backend architectures, engineering designs, database schemas, pipelines, and operations.

---

## 1. System Architecture & Flow Diagram

The application implements a clean boundary between the client application layer, Supabase authorization/persistence layer, and a high-performance 12-layer RAG FastAPI backend.

```
                  ┌──────────────────────────────────────────────────┐
                  │                 Vite React SPA                   │
                  │             (Nginx Proxy on Port 80)             │
                  └────────┬───────────────────┬─────────────────────┘
                           │                   │
               SSE Stream  │                   │ Google OAuth / RLS
        POST /api/chat     │                   │ HTTPS
                           ▼                   ▼
     ┌─────────────────────────────┐   ┌─────────────────────────────┐
     │       FastAPI Backend       │   │    Supabase Auth & DB       │
     │      (Port 8000 / Docker)   │   │   (PostgreSQL Migrations)   │
     └─────────────┬───────────────┘   └───────────────┬─────────────┘
                   │                                   │
      gRPC / HTTP  │                                   │ pg_dump
                   ▼                                   ▼
     ┌─────────────────────────────┐   ┌─────────────────────────────┐
     │      Qdrant Vector DB       │   │       Backup Directory      │
     │     (Port 6333 / Docker)    │   │  (scripts/backup/backups/)  │
     └─────────────┬───────────────┘   └───────────────▲─────────────┘
                   │                                   │
                   │ Graph Context                     │ Cypher Stream
                   ▼                                   │ APOC Export
     ┌─────────────────────────────┐                   │
     │      Neo4j (LightRAG)       │───────────────────┘
     │   (Port 7474, 7687 / Docker)│
     └─────────────────────────────┘
```

### Components and Ports
*   **Vite React SPA:** Serves user-facing interactions on Port `80` (production) or `8080` (development server).
*   **FastAPI Backend:** Orchestrates RAG on Port `8000`. Exposes `/api/chat` (conversational pipeline), `/api/ingest` (content ingestion), `/api/health` (live verification), and `/metrics` (Prometheus instrumentation).
*   **Qdrant Vector DB:** Running on Port `6333` for hybrid (dense + sparse) retrieval.
*   **Neo4j Graph Database:** Running on Ports `7474` (HTTP) and `7687` (Bolt) to support LightRAG entity relations.
*   **Redis Cache Adapter:** Listening on Port `6379` to support token-based caching and semantic caches.
*   **Jaeger Tracing UI:** Listening on Port `16686` for OpenTelemetry trace analysis.

---

## 2. React Frontend Architecture

The frontend is a single-page application built on Vite, React 18, TypeScript, TailwindCSS, and shadcn/ui.

### 2.1 File & Component Mapping
*   `src/App.tsx`: Wires the routing system using `react-router-dom`. Incorporates lazy loading for admin pages to minimize bundle sizes.
*   `src/components/chat/ChatInterface.tsx`: The primary dialogue screen (~540 lines of code). Handles streaming state, voice controls, session recovery, and local messaging.
*   `src/components/chat/DesktopSidebar.tsx`: Persistent, collapsible sidebar (56px collapsed to 280px expanded). Supports key binding `Cmd+B` for quick toggles and subscribes to `conversation:updated` events.
*   `src/components/chat/DailyTeaching.tsx`: Realtime database subscription card subscribing to the `daily_teachings` channel. Automatically monitors expiration dates and handles broken-image fallbacks gracefully.
*   `src/components/chat/SereneMindModal.tsx`: Modal interface driving the 4-step guided meditation flow.
*   `src/components/chat/BrandedSpinner.tsx`: A premium, theme-accurate loading spinner utilizing customized spinning SVGs to replace generic `Loading...` fallbacks during chunk loading.

### 2.2 Speech-to-Text & Text-to-Speech Hooks
*   `src/hooks/useSpeechRecognition.ts`: Wraps the native Web Speech API. Supports 6 Indian language dialects (en-IN, hi-IN, te-IN, ta-IN, bn-IN, mr-IN). Falls back to capturing raw audio blobs and uploading them to the edge function `sarvam-stt` (using `saaras:v3` model) when browser APIs fail.
*   `src/hooks/useTextToSpeech.ts`: Integrates local SpeechSynthesis. Dynamically selects localized voices according to target languages. Falls back to hitting the `sarvam-tts` edge utility to synthesize natural-sounding speech from input text if high-quality local voices are missing.

### 2.3 Page Meta & SEO Optimization
*   `src/hooks/usePageMeta.ts`: Dynamic meta utility that injects specific `<title>`, description, and canonical tags into the DOM head on route rendering. Cache-stores original head attributes and restores them upon component unmounting to prevent meta leaks.
*   **JSON-LD Schemas:** Local structured JSON-LD schemas (`WebApplication`, `Article`) are embedded inside components like `DailyTeaching.tsx` and the main `index.html` to guarantee optimal crawler indexing.

### 2.4 State & Session Storage Persistence
*   **Stream Checkpoints:** To safeguard conversation streaming against accidental screen refreshes, `ChatInterface.tsx` writes active message chunks to `sessionStorage` at `askmukthiguru_stream_checkpoint` every 500ms. If a reload occurs and the checkpoint timestamp is less than 60 seconds old, the app restores the partial stream.
*   **Language Caching:** The frontend caching system separates stored message responses by preferred language tag so that a translated chat thread never maps incorrectly to an English equivalent.

---

## 3. FastAPI Backend & 12-Layer RAG Pipeline

The backend executes a comprehensive, 12-layer verification pipeline ensuring absolute factual alignment with the root spiritual teachings.

### 3.1 LangGraph State Schema (`GraphState`)
The state flowing through the pipeline is defined as a typed dictionary containing the following attributes:
*   `question` (str): Original search query.
*   `chat_history` (list[dict]): Capped interaction window (last 8 messages).
*   `intent` (str): Categorized query direction (QUERY, DISTRESS, CASUAL, MEDITATION_CONTINUE).
*   `documents` (list[dict]): Initial raw retrievals from vector stores.
*   `reranked_docs` (list[dict]): Re-ordered documents from the reranking model.
*   `relevant_docs` (list[dict]): Documents validated as factual for the response.
*   `rewrite_count` (int): Number of CRAG self-correction loops.
*   `sub_queries` (list[str]): Query queries broken down by decomposition.
*   `hints` (list[str]): Key evidentiary phrases extracted to ground responses.
*   `answer` (str): Raw LLM generation text.
*   `is_faithful` (bool): Grounding checks assessment.
*   `input_blocked`/`output_blocked` (bool): Guardrail indicators.
*   `meditation_step` (int): Track stage of Serene Mind.
*   `final_answer` (str): Post-processed, translated response returned to the client.
*   `user_id`/`detected_language`/`memory_context` (str): Persistent user descriptors.

### 3.2 Detailed 12-Layer Request Execution Lifecycle

```
[User Question]
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Layer 1: Input Guardrail (Lightweight & NeMo Guard)    │
└───────────────────────┬────────────────────────────────┘
                        │ PASS
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 2: Intent Classification (QUERY, CASUAL, etc.)   │
└───────────────────────┬────────────────────────────────┘
                        │ QUERY
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 3: Query Decomposition (Parallel Sub-Queries)    │
└───────────────────────┬────────────────────────────────┘
                        │
                        ├──────────────────────────┐
                        ▼                          ▼
┌────────────────────────────────┐   ┌───────────────────────────┐
│ Layer 3.5: Tree Navigation     │   │ Layer 3.5: HyDE Generator │
│ (RAPTOR Summaries Filter)      │   │ (Hypothetical Doc)        │
└───────────────────────┬────────┘   └─────────────┬─────────────┘
                        │                          │
                        └────────────┬─────────────┘
                                     ▼
┌────────────────────────────────────────────────────────┐
│ Layer 4: Dual Search Retrieval (Qdrant + LightRAG)     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 5: Cross-Encoder Reranking (Sigmoid Filter)      │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 6: CRAG Relevance Grading (LLM Quality Verdict)   │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 7: CRAG Self-Correction / Rewrite Loop           │
└───────────────────────┬────────────────────────────────┘
                        │ PASS
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 7.5: Context Engineering (Memory & Directives)   │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 8 & 9: Grounded Generation (Inline Citation)     │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 10 & 11: Joint Verification & Contradiction Check│
└───────────────────────┬────────────────────────────────┘
                        │ PASS
                        ▼
┌────────────────────────────────────────────────────────┐
│ Layer 12: Output Guardrail (NeMo Safety Moderation)    │
└───────────────────────┬────────────────────────────────┘
                        │
                        ▼
                  [Final Response]
```

#### Layer 1: Input Guardrails
Intercepts the inbound string. First evaluates raw inputs against a regular-expression safety block (`LightweightGuardrails.check_input`). Second, streams inputs through NeMo Colang flows (`guardrails/config/topics.co`) to reject inquiries involving politics, financial manifests, or medical prescribing.

#### Layer 2: Intent Classification
Routes user questions to target handlers. Fast-routes casual greetings (e.g. "Namaste") via regex tables to `handle_casual` to bypass expensive models. Activates `SereneMindEngine` for semantic distress analysis. If a critical crisis score (>0.6) is met, intercepts the execution chain to serve distress-hotline arrays alongside guided breathing exercises.

#### Layer 3: Query Decomposition
Translates user queries into atomic, standalone prompts using specialized templates. Eliminates multi-sentence compound queries to guarantee high-precision searches on Qdrant.

#### Layer 3.5: Tree Navigation & HyDE
*   **Tree Navigation:** PageIndex navigation scans level-1 RAPTOR summary blocks representing cluster headers, selecting the top 3 corresponding cluster IDs. This narrows vector query targets down to specific clusters, avoiding brute-force vector scans.
*   **HyDE:** Ollama or Sarvam generates a hypothetical document matching the target answer structure, enhancing dense vector representations.

#### Layer 4: Dual Retrieval
Triggers concurrent retrievals:
1.  **Qdrant Hybrid Search:** Evaluates dense cosine metrics (`all-MiniLM-L6-v2` or `BAAI/bge-m3`) combined with sparse token frequencies. Restricted to the cluster list compiled in Layer 3.5.
2.  **LightRAG Graph Retrieval:** Direct query to the LightRAG engine in `only_need_context=True` mode, retrieving relational entity maps.
*   **Parent-Child Context Swap:** A specialized post-retrieval module swaps child chunks (~400-char leaf segments) for their parent paragraphs (~1500-char context window) using `parent_id` foreign keys to ensure the generation stage receives complete context.

#### Layer 5: Cross-Encoder Reranking
Uses a CrossEncoder architecture to compute query-document similarities, outputting sigmoid-normalized scores. Drops any chunk with a score below `0.35`.

#### Layer 6: CRAG Relevance Grading
Executes a single batch call to evaluate retrieved chunk relevance, classifying documents as `CORRECT`, `IRRELEVANT`, or `AMBIGUOUS`.

#### Layer 7: CRAG Self-Correction / Rewrite Loop
If the cumulative document set is graded `IRRELEVANT`, the query is rewritten up to 3 times to seek out missing context. If it fails to find matches after 3 loops, the system terminates with a structured fallback response.

#### Layer 7.5: Context Engineering
Compiles four discrete context layers into the generation context:
*   `persona`: Root guru behavioral instructions.
*   `knowledge`: Retrieved teachings and graph contexts.
*   `instructions`: Formatting and syntax directives.
*   `user_state`: Seeker preferences and long-term memory.

#### Layer 8 & 9: Response Generation
Generates answers using context-locked instructions. Appends inline citation brackets mapping to source video URLs. If the user's preferred language is set to an Indic dialect (e.g., Telugu), the final string is dynamically translated.

#### Layer 10 & 11: Joint Verification & Contradiction Check
*   **Joint Grounding:** Self-RAG checks if claims match the context. Chain of Verification (CoVe) generates factual sub-questions to test answers against retrieved facts.
*   **Contradiction Check:** Validates the generated answer against the session's historical transcript. If contradictions are found, it adds an auto-clarification suffix.

#### Layer 12: Output Guardrails
The final string runs through the NeMo output rail to ensure no off-topic information escapes the backend.

### 3.3 Backend Services & Caching
*   `ollama_service.py` / `sarvam_cloud`: Gateway supporting fallback logic. If `llm_provider` is `sarvam_cloud`, requests hit the Sarvam Cloud API; otherwise, they fall back to local Ollama endpoints.
*   `embedding_service.py`: Standardizes dense and sparse vector generation via `BAAI/bge-m3`. Offloads execution to CPU threads to preserve GPU VRAM for generation tasks.
*   `cache_service.py`: Integrates a fast memory-cache adapter and Redis cache to bypass LangGraph for identical inputs.
*   **Request Coalescing:** The `RequestCoalescer` captures incoming requests. If duplicate inquiries arrive concurrently, they are merged into a single execution thread to prevent database and LLM thrashing.

---

## 4. Ingestion & RAPTOR Indexing Pipeline

Ingestion handles media processing, quality assurance, and structural hierarchical indexing.

### 4.1 Ingestion Steps
1.  **Ingestion Orchestrator (`pipeline.py`):** Automatically routes incoming URLs based on type (YouTube, images, PDF files).
2.  **Dual-STT Transcript Council:** Pulls transcripts via a 4-tier fallback:
    *   *Tier 1:* Manual YouTube captions.
    *   *Tier 2:* Auto-generated YouTube captions.
    *   *Tier 3:* Downloaded subtitles via `yt-dlp` using browser cookie extraction (`cookies.txt` or Chrome fallback).
    *   *Tier 4:* Native Whisper transcribing. Spawns local `faster-whisper` (utilizing `large-v3-turbo`) to transcribe downloaded audio. Runs the "Transcript Council" comparison heuristics to select or merge the highest-quality output.
3.  **LLM Ingestion Corrector:** Corrects spelling and spiritual terminology errors (e.g., correcting "Ekam" or proper names).
4.  **Ingestion Quality Auditor:** Evaluates transcripts to filter out noise, music tracks, or off-topic transcripts.
5.  **Text Cleaner:** Removes filler words, time descriptors, and formatting characters.
6.  **Hierarchical Chunking:** Partitions transcripts into child chunks (400 characters, 50 overlap) linked to parent paragraphs (1500 characters, 200 overlap) via matching `parent_id` tags.
7.  **RAPTOR Tree Construction:**
    *   Level-0 leaf chunks are embedded.
    *   Clustered recursively via K-Means and UMAP.
    *   Clusters are summarized using LLM templates.
    *   Level-1 summary nodes are embedded and indexed back to Qdrant.

### 4.2 Monitored macOS sleep prevention & Resumability
*   **macOS Sleep Prevention:** Spawns a background `caffeinate` process bound to the main process ID:
    ```python
    caffeinate_proc = subprocess.Popen(["caffeinate", "-w", str(os.getpid())])
    ```
    This prevents system sleep during long ingestion pipelines.
*   **Resumable State:** State progress is written to `scripts/ingestion_state.json`, allowing the pipeline to resume from the last successful stage in case of network interruptions.

---

## 5. Database Schema & SQL Table Definitions

The schema is divided into telemetry, user configuration, and memory tables.

### 5.1 DDL Structure

#### `profiles` Table
```sql
CREATE TABLE public.profiles (
    id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    display_name text,
    avatar_url text,
    favorite_teachings text[] DEFAULT '{}',
    updated_at timestamp with time zone DEFAULT timezone('utc'::text, now())
);
```

#### `user_roles` Table
```sql
CREATE TABLE public.user_roles (
    id bigint PRIMARY KEY GENERATED BY DEFAULT AS IDENTITY,
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    role public.app_role DEFAULT 'seeker'::public.app_role NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now())
);
```

#### `daily_teachings` Table
```sql
CREATE TABLE public.daily_teachings (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    image_url text NOT NULL,
    quote text,
    expires_at timestamp with time zone NOT NULL,
    created_at timestamp with time zone DEFAULT timezone('utc'::text, now())
);
```

#### `user_profiles` Table
```sql
CREATE TABLE public.user_profiles (
    user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    preferred_language text DEFAULT 'en',
    spiritual_level text DEFAULT 'beginner',
    topics_of_interest text[] DEFAULT '{}',
    last_distress_assessment jsonb DEFAULT '{}',
    total_conversations int DEFAULT 0,
    total_meditations_completed int DEFAULT 0,
    favorite_teachings text[] DEFAULT '{}',
    codemix_preference boolean DEFAULT false,
    created_at float8 NOT NULL,
    updated_at float8 NOT NULL
);
```

#### `conversation_memories` Table
```sql
CREATE TABLE public.conversation_memories (
    session_id uuid PRIMARY KEY,
    user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
    started_at float8 NOT NULL,
    messages jsonb DEFAULT '[]',
    key_insights text[] DEFAULT '{}',
    emotional_arc jsonb DEFAULT '[]',
    follow_up_suggestions text[] DEFAULT '{}'
);
```

### 5.2 RLS & Row-Level Security Policies
*   **user_profiles / conversation_memories:** Restrict direct modifications and reads via policies:
    ```sql
    CREATE POLICY "Users can see their own profiles" ON public.user_profiles
      FOR SELECT USING (auth.uid() = user_id);
    ```
*   **Admin Overrides:** Admin users bypass RLS filters on global telemetry tables via check functions:
    ```sql
    CREATE POLICY "Admins can read all profiles" ON public.user_profiles
      FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'::public.app_role));
    ```

### 5.3 Memory Compaction
The system monitors the `messages` array size inside `conversation_memories`. When the message length exceeds 6 entries, it calls the LLM in the background to summarize the conversation, reducing context size while preserving insights and emotional states.

---

## 6. Operations, DevOps, and Verification

Guidelines for managing deployment, backups, and quality metrics.

### 6.1 Docker Deployment Structure
The application uses Docker Compose for service orchestration:
*   `backend.Dockerfile`: Implements multi-stage Python 3.12 builds with `ffmpeg` dependencies preloaded for Whisper.
*   `frontend.Dockerfile`: Multi-stage Vite builds, packaging the static bundle into Nginx containers.
*   **Nginx Configuration (`nginx.conf`):** Maps `/api/*` requests to the FastAPI backend and serves static files for the single-page application.

### 6.2 Backups & DB Management (`snapshot_manager.py`)
Provides three core database backup utilities:
*   **Qdrant Snapshots:** Triggers snapshots via `/collections/spiritual_wisdom/snapshots` and downloads the snapshots.
*   **Neo4j APOC Exports:** Runs APOC Cypher stream exports:
    ```bash
    docker exec mukthiguru-neo4j cypher-shell -u neo4j -p pass "CALL apoc.export.cypher.all(null, {stream: true}) YIELD cypherStatements"
    ```
*   **Supabase Backup:** Performs `pg_dump` with disabled triggers to avoid foreign key order errors:
    ```bash
    pg_dump -U postgres -d postgres --data-only --schema=public --disable-triggers
    ```

### 6.3 Ruthless Benchmark Suite
`scripts/benchmarks/askmukthiguru_ruthless_benchmark.py` evaluates the stack across 10 dimensions:

| Category | Weight | Threshold / Target |
|---|---|---|
| Infrastructure Availability | 0.06 | > 90% service health check response rate |
| RAG Pipeline Layers | 0.14 | 100% correct conditional flow mapping |
| Doctrine Accuracy | 0.16 | > 0.50 Keyword score against verified teachings |
| Serene Mind Meditation | 0.14 | > 0.85 distress trigger matching |
| Adversarial Resilience | 0.12 | > 0.95 safety blocks on toxic prompts |
| Multi-Turn Continuity | 0.08 | No context leakage |
| Safety & Guardrails | 0.10 | > 0.95 rails execution efficiency |
| Citation Footnotes | 0.06 | > 0.70 URL mapping correctness |
| Performance Latencies | 0.06 | p95 < 6.0s, p99 < 12.0s response times |
| Faithfulness Score | 0.08 | > 0.80 Grounding index |
