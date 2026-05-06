# AskMukthiGuru — Setup Guide

Complete setup guide for local development and production deployment.

## Prerequisites

- **Node.js 18+** / **Bun** (frontend)
- **Python 3.11+** (backend)
- **Docker** (Qdrant vector DB + optional backend containerization)
- **Ollama** (LLM inference, runs on host)

---

## 1. Frontend Setup

### Install Dependencies

```bash
bun install
# or
npm install
```

### Environment Variables

Create a `.env.local` file in the project root for local development overrides:

```env
# Point frontend to local FastAPI backend (default: relative /api/chat for production)
VITE_BACKEND_URL=http://localhost:8000

# These are auto-injected by Lovable Cloud — only needed for standalone local dev:
# VITE_SUPABASE_URL=https://fynkjimvuimakgtidvuq.supabase.co
# VITE_SUPABASE_PUBLISHABLE_KEY=<your-anon-key>
```

### Run Dev Server

```bash
bun run dev    # Starts on http://localhost:8080
```

### Run Tests

```bash
bun test       # or: npx vitest run
```

---

## 2. Backend Setup

### Option A: Docker Compose (Recommended)

```bash
cd backend
cp .env.example .env    # Edit .env with your settings
docker compose up -d --build
```

This starts:
- **Qdrant** on port 6333 (vector database)
- **FastAPI backend** on port 8000

### Option B: Manual Setup

```bash
cd backend
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Start Qdrant separately
docker run -p 6333:6333 -p 6334:6334 \
  -v ${PWD}/qdrant_storage:/qdrant/storage \
  qdrant/qdrant:v1.13.2

# Start the backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ollama (LLM on Host)

Ollama must run on the **host machine**, not in Docker:

```bash
ollama serve

# Install the Sarvam 30B model
cd backend/models
chmod +x setup_sarvam.sh && ./setup_sarvam.sh
```

### Backend Environment (`backend/.env`)

Key settings:

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_MODEL` | `sarvam-30b:latest` | LLM model for inference |
| `QDRANT_URL` | `http://localhost:6333` | Qdrant vector DB URL |
| `WHISPER_MODEL` | `large-v3` | Whisper model for transcription |
| `WHISPER_COMPUTE_TYPE` | `float16` | `float16` for GPU, `int8` for CPU |

---

## 3. Database (Lovable Cloud)

The database is managed by Lovable Cloud (Supabase under the hood). Tables are created via migrations.

### Database Tables

| Table | Purpose |
|-------|---------|
| `profiles` | User display name, avatar, language prefs. Auto-created on signup via trigger. |
| `user_roles` | Admin role management. Manual insert required. |
| `daily_teachings` | Daily teaching images with 24h TTL (`expires_at`). |
| `meditation_sessions` | Per-user meditation tracking (duration, breath cycles, streaks). |
| `conversations` | Chat conversation metadata (user, title, preview). |
| `chat_messages` | Individual chat messages linked to conversations. |

### Auth Flow

1. User signs up at `/auth` (email/password or Google OAuth)
2. Trigger `on_auth_user_created` → `handle_new_user()` → inserts `profiles` row
3. Admin access: must have a row in `user_roles` with `role = 'admin'`

### Making Yourself Admin

After signing up, an admin (or database tool) must insert:

```sql
INSERT INTO user_roles (user_id, role)
VALUES ('<your-user-id>', 'admin');
```

You can find your user ID by querying `auth.users` by email.

---

## 4. Production Deployment

### Frontend
- Lovable auto-deploys when you click **Publish**
- Set `VITE_BACKEND_URL` to your production FastAPI URL (if different from same-origin)

### Backend
- Deploy the FastAPI app from `backend/` to your server (Docker Compose, AWS, GCP, etc.)
- Ensure Qdrant and Ollama are accessible from the backend
- Configure CORS in `backend/app/main.py` if frontend is on a different domain

### Lovable Cloud
- Database, auth, and storage are automatically provisioned
- Edge functions auto-deploy
- No manual Supabase setup needed

---

## 5. Service URLs

| Service | Local URL |
|---------|-----------|
| Frontend | http://localhost:8080 |
| Backend API | http://localhost:8000/docs |
| Ingestion Portal | http://localhost:8000/ingest/ |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Health Check | http://localhost:8000/api/health |

---

## 6. Architecture Quick Reference

### Frontend → Backend Flow
1. User types message in chat UI
2. `aiService.ts` sends POST to `${VITE_BACKEND_URL}/api/chat` (or `/api/chat/stream` for SSE)
3. Backend runs 12-layer RAG pipeline
4. Response streamed back as SSE with status events → ThinkingPills UI
5. Messages saved to localStorage (anonymous) or database (authenticated)

### Backend Pipeline (12 Layers)
1. NeMo Input Rail → safety check
2. Depression Detector → fast-path to meditation
3-11. LangGraph: intent → retrieve → rerank → grade → CRAG loop → generate → Self-RAG → CoVe → format
12. NeMo Output Rail → output moderation

### Key Env Vars Summary

| Variable | Where | Purpose |
|----------|-------|---------|
| `VITE_BACKEND_URL` | `.env.local` | Frontend → Backend URL |
| `VITE_SUPABASE_URL` | Auto-injected | Database URL |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Auto-injected | Database anon key |
| `OLLAMA_MODEL` | `backend/.env` | LLM model |
| `QDRANT_URL` | `backend/.env` | Vector DB URL |
