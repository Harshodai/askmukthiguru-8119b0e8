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

## LLM Configuration

Set `LLM_PROVIDER` in `backend/.env`:

| Provider | Config | Description |
|---|---|---|
| `sarvam_cloud` (default) | Set `SARVAM_API_KEY` | Sarvam Cloud API — fast, reliable |
| `ollama` | Set `OLLAMA_BASE_URL` | Local Ollama with Qwen/Sarvam models |

## RAG Pipeline (12 Layers)

1. NeMo Input Rail (guardrails)
2. Intent Classification
3. Query Decomposition
4. Knowledge Tree Navigation (RAPTOR)
5. Hybrid Retrieval (Qdrant + LightRAG)
6. Cross-encoder Reranking
7. CRAG Document Grading
8. Stimulus RAG (Hint Extraction)
9. Context-aware Generation with bounded conversation memory
10. Self-RAG Faithfulness Check
11. Chain of Verification (CoVe)
12. NeMo Output Rail

Conversation continuity is carried by the active chat `session_id`. The backend
normalizes local browser conversation ids into stable UUIDs for Supabase memory
tables, then injects a compact current-thread and prior-session memory block into
the RAG context.

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

# RAG quality benchmark (requires running Docker stack)
python scripts/benchmark_rag_responses.py --base-url http://localhost:8000
```
