# AskMukthiGuru — Complete Setup & Code Flow Guide

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Environment Variables](#2-environment-variables)
3. [Frontend Setup](#3-frontend-setup)
4. [Backend Setup](#4-backend-setup)
5. [Database & Auth (Lovable Cloud)](#5-database--auth-lovable-cloud)
6. [Code Flow: How It All Connects](#6-code-flow-how-it-all-connects)
7. [Admin Panel](#7-admin-panel)
8. [Production Deployment](#8-production-deployment)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Quick Start

```bash
# Frontend
cp .env.example .env.local
bun install && bun run dev          # → http://localhost:8080

# Backend (in a second terminal)
cd backend
cp .env.example .env
docker compose up -d --build        # → Qdrant + FastAPI on :8000

# LLM (on host machine)
ollama serve
cd backend/models && ./setup_sarvam.sh
```

---

## 2. Environment Variables

### Frontend (`.env.local`)

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `VITE_BACKEND_URL` | No | `""` (relative) | FastAPI backend URL. Set to `http://localhost:8000` for local dev |
| `VITE_SUPABASE_URL` | Auto | — | Database URL (auto-injected by Lovable Cloud) |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | Auto | — | Database anon key (auto-injected) |

**How backend auto-detection works** (`src/lib/aiService.ts`):
```typescript
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || '';
// Local dev: VITE_BACKEND_URL=http://localhost:8000 → http://localhost:8000/api/chat
// Production: VITE_BACKEND_URL="" → /api/chat (same-origin, reverse-proxied)
```

### Backend (`backend/.env`)

| Variable | Default | Purpose |
|----------|---------|---------|
| `OLLAMA_MODEL` | `sarvam-30b:latest` | LLM model name |
| `QDRANT_URL` | `http://localhost:6333` | Vector DB URL |
| `WHISPER_MODEL` | `large-v3` | Transcription model |
| `WHISPER_COMPUTE_TYPE` | `float16` | GPU: `float16`, CPU: `int8` |

---

## 3. Frontend Setup

### Prerequisites
- Node.js 18+ or Bun

### Install & Run
```bash
bun install
bun run dev          # http://localhost:8080
bun test             # Run all tests
```

### Key Frontend Files

| File | Purpose |
|------|---------|
| `src/lib/aiService.ts` | Backend communication (SSE streaming + fallback) |
| `src/lib/chatStorage.ts` | localStorage chat persistence (anonymous users) |
| `src/lib/chatPersistence.ts` | Database chat persistence (authenticated users) |
| `src/lib/meditationStorage.ts` | Meditation session tracking (localStorage + DB) |
| `src/components/chat/ThinkingPills.tsx` | Pipeline status UI during streaming |
| `src/components/common/SereneMindProvider.tsx` | Meditation context provider |
| `src/components/common/ChatErrorBoundary.tsx` | Error boundary for chat routes |

---

## 4. Backend Setup

### Option A: Docker Compose (Recommended)
```bash
cd backend
cp .env.example .env
docker compose up -d --build
# Qdrant: http://localhost:6333/dashboard
# FastAPI: http://localhost:8000/docs
```

### Option B: Manual
```bash
cd backend
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run Qdrant separately
docker run -p 6333:6333 -v ${PWD}/qdrant_storage:/qdrant/storage qdrant/qdrant:v1.13.2

# Run backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Ollama (Host Machine)
```bash
ollama serve
cd backend/models && chmod +x setup_sarvam.sh && ./setup_sarvam.sh
```

---

## 5. Database & Auth (Lovable Cloud)

### Tables

| Table | Purpose | Auto-created? |
|-------|---------|---------------|
| `profiles` | User display name, avatar, language prefs | Yes (trigger on signup) |
| `user_roles` | Admin/user role assignment | No (manual insert) |
| `daily_teachings` | Teaching images with 24h TTL | Admin creates via panel |
| `meditation_sessions` | Per-user meditation tracking | Auto on completion |
| `conversations` | Chat conversation metadata | Auto for authenticated users |
| `chat_messages` | Individual chat messages | Auto for authenticated users |

### Auth Flow
1. User visits `/auth` → signs up with email/password or Google OAuth
2. Database trigger `on_auth_user_created` → `handle_new_user()` → creates `profiles` row
3. User can now chat with DB-backed message persistence

### Making Yourself Admin
1. Sign up at `/auth` with your email
2. An existing admin (or DB tool) must run:
   ```sql
   INSERT INTO user_roles (user_id, role)
   VALUES ('<your-user-id-from-auth.users>', 'admin');
   ```
3. Navigate to `/admin/login` and sign in with the same email/password

### RLS (Row Level Security)
All tables have RLS enabled:
- Users can only access their own conversations, messages, meditation sessions, and profile
- Admins can insert/delete daily teachings (checked via `has_role()` RPC)
- `user_roles` is read-only for users (no self-promotion)

---

## 6. Code Flow: How It All Connects

### Chat Message Flow

```
User types message
       ↓
ChatInterface.tsx (handleSubmit)
       ↓
aiService.ts → sendMessageStreaming()
       ↓
POST ${VITE_BACKEND_URL}/api/chat/stream
       ↓  (SSE response)
  ┌─ event: status → ThinkingPills UI (Safety check, Understanding, etc.)
  └─ event: message → Token-by-token content → ChatMessage component
       ↓
  On completion:
  ├─ localStorage (chatStorage.ts) — always
  └─ Database (chatPersistence.ts) — if user is authenticated
```

### Backend Pipeline (12 Layers)

```
POST /api/chat → FastAPI (app/main.py)
       ↓
1. NeMo Input Rail → Safety check
2. Depression Detector → Fast-path to meditation if distress
       ↓
3-11. LangGraph State Machine (rag/graph.py):
   intent_router → DISTRESS / CASUAL / QUERY
   ↓ (QUERY path)
   decompose_query → retrieve_documents → rerank → grade_documents
   ↓ (CRAG loop: if docs irrelevant → rewrite → retrieve again, max 3x)
   extract_hints → generate_answer → check_faithfulness → verify_answer → format
       ↓
12. NeMo Output Rail → Output moderation
       ↓
SSE stream back to frontend
```

### SSE Status Event Mapping

| Backend Status | UI Label |
|----------------|----------|
| `Checking message safety...` | Safety check |
| `Understanding your question...` | Understanding |
| `Searching knowledge base...` | Searching wisdom |
| `Composing response...` | Composing |
| `Generating answer...` | Generating |
| `Verifying answer...` | Verifying |

### Data Persistence Strategy

| User State | Chat Storage | Meditation Storage |
|------------|-------------|-------------------|
| Anonymous | localStorage only | localStorage only |
| Authenticated | DB (conversations + chat_messages) + localStorage | DB (meditation_sessions) + localStorage |

### Authentication Architecture

```
Admin login: /admin/login
       ↓
adminAuth.ts → loginAdmin(email, password)
       ↓
supabase.auth.signInWithPassword()
       ↓
supabase.rpc('has_role', { _user_id, _role: 'admin' })
       ↓  (true)
localStorage caches display info (NOT used for auth decisions)
       ↓
useAdminGuard.ts → verifyAdminSession() on each protected page load
       ↓
Re-checks JWT + has_role on every navigation (server-side verification)
```

---

## 7. Admin Panel

### Access
1. Sign up at `/auth` with your email
2. Get admin role assigned (see Section 5)
3. Go to `/admin/login` → enter same credentials
4. Dashboard at `/admin`

### Admin Features
- **Daily Teaching**: Upload teaching images with optional caption (24h TTL)
- **Query Explorer**: View chat queries (requires `chat_queries` table — future)
- **Prompt Management**: Manage prompt versions (requires `prompt_versions` table — future)

### Security
- JWT-verified on every page load via `verifyAdminSession()`
- `has_role()` RPC is SECURITY DEFINER (bypasses RLS safely)
- Anonymous users cannot execute `has_role()` (revoked)

---

## 8. Production Deployment

### Frontend
- Lovable auto-deploys when you click **Publish**
- No `.env.local` needed — Lovable Cloud injects Supabase vars
- Set `VITE_BACKEND_URL` to your production FastAPI URL if not same-origin

### Backend
```bash
cd backend
docker compose -f docker-compose.yml up -d --build
```
- Configure CORS in `backend/app/main.py` for your frontend domain
- Ensure Qdrant and Ollama are accessible

### Reverse Proxy (Production)
If frontend and backend are on the same domain:
```nginx
location /api/ {
    proxy_pass http://backend:8000/api/;
}
```
Then leave `VITE_BACKEND_URL` empty (relative `/api/chat` works).

---

## 9. Troubleshooting

| Issue | Fix |
|-------|-----|
| Chat shows placeholder responses | Set `VITE_BACKEND_URL=http://localhost:8000` in `.env.local` |
| "useSereneMind must be used within SereneMindProvider" | Dev-only warning now — returns safe fallback. Check if route is inside `<UserRoutes>` in App.tsx |
| Admin login says "Not an admin" | Ensure `user_roles` has your user_id with `role = 'admin'` |
| Daily teaching upload fails | Check you're authenticated as admin and `daily-teachings` bucket exists |
| SSE streaming not working | Verify backend is running and `VITE_BACKEND_URL` is correct |
| DB persistence not saving | User must be authenticated (signed in via `/auth`) |

### Service URLs (Local Dev)

| Service | URL |
|---------|-----|
| Frontend | http://localhost:8080 |
| Backend API Docs | http://localhost:8000/docs |
| Ingestion Portal | http://localhost:8000/ingest/ |
| Qdrant Dashboard | http://localhost:6333/dashboard |
| Health Check | http://localhost:8000/api/health |
