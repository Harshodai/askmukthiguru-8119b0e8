# AskMukthiGuru — AI Spiritual Guide

An AI-powered spiritual guide rooted in the teachings of **Sri Preethaji & Sri Krishnaji**. Built with a multi-layer RAG pipeline, real-time guardrails, and beautiful conversational UI.

> **New contributor?** Start with **[docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** for an end-to-end walk-through, then **[docs/ROADMAP.md](docs/ROADMAP.md)** for the prioritized backlog. For architectural insights, check **[lessons.md](lessons.md)**.


## Architecture

| Component | Technology | Port |
|---|---|---|
| **Frontend** (Nginx) | Vite React 18 + TailwindCSS + shadcn/ui | `80` |
| **Backend** (FastAPI) | 12-layer RAG pipeline, Sarvam 30B Cloud API | `8000` |
| **Qdrant** | Vector database | `6333` |
| **Redis** | Response caching | `6379` |
| **Neo4j** | Knowledge graph (LightRAG) | `7474` / `7687` |

## Deploy with Docker (Recommended)

### Prerequisites
- **Docker Desktop** installed and running on your Mac.

### One-Command Deploy (Run this in your terminal)

Since you are on a Mac, you may need to ensure Docker is in your PATH. Open your native macOS Terminal (or your IDE's terminal) and run these exact commands:

```bash
# 1. Navigate to the backend directory
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend

# 2. Add Docker to your PATH (fixes "command not found" errors on Mac)
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"

# 3. Build and start all services in detached mode
docker compose up -d --build
```

This builds and starts **all 6 services**:
- **Frontend** on port **80** — serves the React app, Chat widget, and Ingest UI via Nginx
- **Backend** on port **8000** — FastAPI RAG pipeline
- **Qdrant** on port **6333** — vector database
- **Redis** on port **6379** — response caching
- **Neo4j** on port **7474** — knowledge graph
- **Jaeger** on port **16686** — OpenTelemetry trace UI

### 5. Access the app

 | URL | Description |
 |---|---|
 | http://localhost | Main app (landing, chat, practices, profile) |
 | http://localhost/admin | Admin dashboard (login: `admin` / `admin`) |
 | http://localhost/static-chat | Lightweight chat widget — Auth-protected |
 | http://localhost/static-ingest | Content ingestion portal — Admin-only |
 | http://localhost:8000/api/health | Backend health check |
 | http://localhost:16686 | Jaeger trace explorer |

 ### 6. Database Setup (Supabase)

 For persistent user profiles and admin telemetry, you must run the **[master_schema.sql](master_schema.sql)** in your Supabase SQL Editor. This script creates:
 - **User Profiles**: Persistent spiritual preference storage.
 - **Admin Telemetry**: Auditing for queries, responses, and AI triggers (distress/serene mind).
 - **Role Management**: RBAC for admin access.

### Useful commands (Run these in the backend folder)

```bash
# View live logs for all services
docker compose logs -f

# Rebuild after making code changes
docker compose up -d --build

# Stop all services
docker compose down

# Stop and completely reset the database volumes
docker compose down -v
```

## Local Development (Without Docker)

For development with hot-reload:

```bash
# 1. Start infrastructure only
cd backend && docker compose up -d qdrant redis neo4j jaeger

# 2. Start backend (in one terminal)
cd backend && pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 3. Start frontend (in another terminal)
npm install && npm run dev
```

**Frontend Dev Server**: Defaults to [http://localhost:8080](http://localhost:8080). If port 8080 is busy, it may use `8081` or `8082`. Check the terminal output.

### Local Google Sign-In Setup
To enable Google Sign-In during local development:
1. Ensure `.env.local` has `VITE_USE_NATIVE_OAUTH=true`.
2. Configure `supabase/config.toml` with your Google `client_id` and `secret`.
3. Restart the Supabase stack: `npx supabase stop` followed by `npx supabase start`.

## Environment Variables

Ensure the following variables are configured in `backend/.env` before running the ingestion pipeline or services:

| Variable | Description | Default / Example |
|---|---|---|
| `KEYCHAIN_PASS` | Required for macOS keychain unlocking during YouTube ingestion cookie retrieval. | `142000` |
| `SARVAM_DEBUG` | Set to `true` to enable verbose JSON logging for Sarvam API responses. Helps debug quota/reasoning issues. | `false` |
| `USE_FLASHRANK` | Enable FlashRank ONNX-based high-performance reranking for fast retrieval. | `true` |
| `FLASHRANK_MODEL` | FlashRank model to load. Use `auto` for platform-specific tuning. | `auto` |
| `USE_ADAPTIVE_CHUNKING` | Enable quantitative SC/ICC dynamic chunking strategies (Recursive vs. Semantic). | `true` |
| `ADAPTIVE_CHUNKING_MIN_CHARS` | Minimum text character length before adaptive chunking evaluation is triggered. | `5000` |
| `USE_PROPOSITION_CHUNKING` | Enable LLM-based proposition extraction. Bypasses for short files if set to `auto`. | `auto` |
| `PROPOSITION_CHAR_LIMIT` | Max text character length permitted for proposition extraction to prevent LLM timeouts. | `15000` |

## LLM Configuration

Set `LLM_PROVIDER` in `backend/.env`:

| Provider | Config | Description |
|---|---|---|
| `sarvam_cloud` (default) | Set `SARVAM_API_KEY` and optional `SARVAM_RPM_LIMIT` (e.g. `60`) | Sarvam Cloud API — fast, reliable, rate-limiting control |
| `ollama` | Set `OLLAMA_BASE_URL` | Local Ollama with Qwen/Sarvam models |

## RAG Pipeline (12 Layers)

1. Zero-Shot Input Rail (Guardrails via Instructor)
2. Intent Classification
3. Query Decomposition
4. Knowledge Tree Navigation (Parent-Child Retrieval)
5. Hybrid Retrieval (Qdrant + LightRAG)
6. Cross-encoder Reranking
7. CRAG Document Grading
8. Stimulus RAG (Hint Extraction)
9. Context-aware Generation with bounded conversation memory
10. Self-RAG Faithfulness Check
11. Chain of Verification (CoVe)
12. Zero-Shot Output Rail

Conversation continuity is carried by the active chat `session_id`. The backend
normalizes local browser conversation ids into stable UUIDs for Supabase memory
tables, then injects a compact current-thread and prior-session memory block into
the RAG context.

## Agent Technical Skills

The repository features 15 pre-compiled technical agent skills containing structured summaries, patterns, and cheatsheets, stored locally under `.agents/skills/` and mirrored globally at `~/.config/agents/skills/`:
1. `ai-agents-langchain-mcp` — AI Agents with LangChain, LangGraph, and MCP
2. `ai-agents-in-action` — AI Agents in Action
3. `ai-engineering-chip-huyen` — AI Engineering: Foundation Models (Chip Huyen)
4. `build-llm-app-scratch` — Build an LLM Application (from Scratch)
5. `building-apps-ai-agents` — Building Applications with AI Agents
6. `designing-data-intensive-apps-2e` — Designing Data-Intensive Applications, 2nd Edition
7. `kleppmann-ddia-big-ideas` — Martin Kleppmann: DDIA The Big Ideas
8. `rag-made-simple` — RAG Made Simple: Visual Guide to RAG
9. `system-design-llm-era` — System Design for the LLM Era
10. `ieee-innovative-trends-2019` — IEEE 2019 Innovative Trends in Engineering
11. `database-internals` — Database Internals
12. `designing-distributed-systems` — Designing Distributed Systems
13. `prompt-engineering-llms` — Prompt Engineering for LLMs
14. `building-llms-for-production` — Building LLMs for Production
15. `hands-on-llms` — Hands-On Large Language Models

## Project Structure


```
├── backend/              # FastAPI backend
│   ├── app/              # Main app, config, dependencies
│   ├── rag/              # LangGraph pipeline, prompts, nodes
│   ├── services/         # LLM, embedding, Qdrant, OCR services
│   ├── guardrails/       # NeMo guardrails
│   ├── ingest/           # Content ingestion pipeline
│   ├── Dockerfile        # Backend Docker image
│   └── docker-compose.yml
├── src/                  # React frontend (Vite)
│   ├── components/       # UI components
│   ├── pages/            # Route pages
│   └── admin/            # Admin dashboard
├── chat-ui/              # Static chat widget
├── ingest-ui/            # Static ingestion UI
├── frontend.Dockerfile   # Frontend Docker image (multi-stage Vite build + Nginx)
├── nginx.conf            # Nginx config for frontend proxy
└── index.html            # Frontend entry point
```

## License

Private — All rights reserved.

## Frontend Architecture (May 2026)

### Key UI Components
| Component | Description |
|---|---|
| `DesktopSidebar.tsx` | Collapsible icon-rail sidebar (56px ↔ 280px), `Cmd+B` shortcut, auto-refreshes on `conversation:updated` event |
| `BrandedSpinner.tsx` | Branded loading fallback (replaces all `<Suspense>` bare `Loading...`) |
| `GuidedMeditationFlow.tsx` | Post-session reflection flow: mood → journal → gratitude |
| `DailyTeaching.tsx` | Realtime teaching banner with `expires_at` filter and broken-image fallback |

### Auth Behaviour
- Google OAuth users receive their full name and avatar URL from `user_metadata` immediately on first sign-in.
- `useProfile` always re-reads `localStorage` after server sync to pick up metadata writes.
- `clearProfile()` in `profileStorage.ts` should be called on sign-out.

### Stream Persistence
- Active streaming is checkpointed to `sessionStorage` every 500ms.
- Checkpoint key: `askmukthiguru_stream_checkpoint`. Cleared in `finally` on completion.
- Restored on mount if checkpoint is < 60s old.

### Testing
```bash
# Auth + stream checkpoint unit tests
npx vitest run src/tests/auth.e2e.test.ts

# Native Benchmark Evaluation
python3 backend/tests/eval_ragas_native.py

# Production-grade "Ruthless" benchmark (requires running Docker stack)
python3 scripts/benchmarks/askmukthiguru_ruthless_benchmark.py --url http://localhost:8000
```

---

## 🧭 Developer Q&A and Documentation Directory

Use the directory below to redirect to specific documentation files and sections based on your questions:

*   **Q: How do I set up my local environment and start developing?**
    *   👉 Read the **[DEVELOPER_GUIDE.md Day-1 Setup](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/DEVELOPER_GUIDE.md#4-day-1-setup)**.
*   **Q: Where can I see a detailed map of all the backend 12-layer RAG modules?**
    *   👉 Read **[COMPLETE_SYSTEM_REFERENCE.md Section 3: 12-Layer RAG Pipeline](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/COMPLETE_SYSTEM_REFERENCE.md#3-fastapi-backend--12-layer-rag-pipeline)**.
*   **Q: How does the ingestion pipeline handle Whisper transcribing and YouTube cookie extraction?**
    *   👉 Read **[COMPLETE_SYSTEM_REFERENCE.md Section 4: Ingestion & RAPTOR Pipeline](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/COMPLETE_SYSTEM_REFERENCE.md#4-ingestion--raptor-indexing-pipeline)**.
*   **Q: Where can I inspect the PostgreSQL migration table definitions and RLS policies?**
    *   👉 Read **[COMPLETE_SYSTEM_REFERENCE.md Section 5: Database Schema & SQL Table Definitions](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/COMPLETE_SYSTEM_REFERENCE.md#5-database-schema--sql-table-definitions)**.
*   **Q: What is the configuration schema for the main backend singletons?**
    *   👉 Read the **[app/config.py](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/backend/app/config.py)** configuration file or its summary in the **[COMPLETE_SYSTEM_REFERENCE.md config reference](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/COMPLETE_SYSTEM_REFERENCE.md#33-backend-services--caching)**.
*   **Q: How are database backups and vector collection restores automated?**
    *   👉 Read **[COMPLETE_SYSTEM_REFERENCE.md Section 6.2: Backups & DB Management](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/COMPLETE_SYSTEM_REFERENCE.md#62-backups--db-management-snapshot_managerpy)**.
*   **Q: Where are the system latency and accuracy benchmark scores tracked?**
    *   👉 Read **[COMPLETE_SYSTEM_REFERENCE.md Section 6.3: Ruthless Benchmark Suite](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/COMPLETE_SYSTEM_REFERENCE.md#63-ruthless-benchmark-suite)**.
*   **Q: How do I deploy the entire stack to staging or production using Docker?**
    *   👉 Read **[DEPLOYMENT.md](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/DEPLOYMENT.md)**.
*   **Q: What is the current developmental roadmap and outstanding backlog?**
    *   👉 Read **[ROADMAP.md](file:///c:/Users/khars/PycharmProjects/askmukthiguru-8119b0e8/docs/ROADMAP.md)**.
