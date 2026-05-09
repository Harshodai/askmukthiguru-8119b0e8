# AskMukthiGuru — Developer Guide

> A complete, end-to-end onboarding document for new contributors.
> If you have just cloned this repo, read this top-to-bottom before changing anything.

---

## 1. What this project is

AskMukthiGuru is a privacy-first AI spiritual companion grounded in the public
teachings of Sri Preethaji and Sri Krishnaji. It pairs a React/Vite/TypeScript
frontend (deployed on **Lovable Cloud**) with a Python FastAPI backend that
runs a 12-layer retrieval-augmented-generation (RAG) pipeline against a local
Qdrant vector store and a local Ollama LLM (default model: `sarvam-30b`).

Non-negotiable constraints (see `SPEC_DEV.md`):

- $0 budget — only free-tier infra (Colab, Qdrant local, Ollama).
- 100 % local processing at inference; zero external API calls.
- All dependencies open source (Apache 2.0, MIT, or Meta Community).
- Target: < 1 % hallucination, < 3 s response time.

---

## 2. Architecture at a glance

```
┌──────────────┐    HTTPS     ┌────────────────┐    SQL/RLS    ┌────────────────┐
│  React UI    │◄────────────►│  Lovable Cloud │◄─────────────►│   Postgres     │
│ (Vite, TS)   │   auth +     │  (Supabase)    │               │ + RLS policies │
└──────┬───────┘   realtime   └────────────────┘               └────────────────┘
       │
       │ SSE  POST /api/chat/stream
       ▼
┌──────────────┐   gRPC/HTTP  ┌────────────────┐    REST       ┌────────────────┐
│  FastAPI     │◄────────────►│    Qdrant      │               │   Ollama       │
│  (12-layer   │   vector     │  (vector DB)   │               │  (sarvam-30b)  │
│   RAG)       │   search     └────────────────┘               └────────┬───────┘
└──────┬───────┘                                                        │
       └────────────────────────── LLM completions ─────────────────────┘
```

Three deployable surfaces:

| Surface           | Hosted on            | Entry file                    |
| ----------------- | -------------------- | ----------------------------- |
| End-user web app  | Lovable Cloud / Vite | `src/main.tsx` → `src/App.tsx`|
| Admin console     | Same bundle, `/admin`| `src/admin/layout/AdminShell` |
| FastAPI backend   | Docker / VM          | `backend/app/main.py`         |

---

## 3. Repository tour

```
.
├── src/                          ← React app
│   ├── pages/                    ← Routed pages (Index, Auth, Chat, Profile, …)
│   ├── components/
│   │   ├── chat/                 ← ChatInterface, ChatMessage, DailyTeaching, …
│   │   ├── meditation/           ← Serene Mind 4-step flow
│   │   ├── landing/              ← Hero, Footer, FloatingParticles
│   │   ├── common/               ← Providers (Theme, SereneMind, Reminder, …)
│   │   └── ui/                   ← shadcn/ui primitives
│   ├── admin/                    ← Self-contained admin console (lazy candidate)
│   ├── hooks/                    ← useProfile, useRequireAuth, speech, TTS, …
│   ├── lib/                      ← aiService, chatStorage, persistence, utils
│   ├── integrations/
│   │   ├── supabase/             ← Auto-generated Supabase client + types
│   │   └── lovable/              ← Lovable-managed OAuth wrapper
│   └── test/                     ← Vitest specs
├── backend/                      ← Python FastAPI
│   ├── app/                      ← FastAPI app, config, DI, dashboards
│   ├── rag/                      ← LangGraph pipeline (graph, nodes, prompts)
│   ├── ingest/                   ← YouTube + image ingestion + RAPTOR indexing
│   ├── services/                 ← Ollama, Qdrant, embeddings, OCR, cache
│   ├── guardrails/               ← NeMo input/output rails
│   ├── routers/                  ← admin + feedback HTTP routers
│   └── tests/                    ← pytest suite
├── supabase/migrations/          ← All schema changes (timestamped SQL)
├── docs/                         ← This guide, ROADMAP, admin docs, etc.
├── chat-ui/  ingest-ui/          ← Standalone HTML utilities served by FastAPI
├── public/                       ← Static assets (favicon, robots.txt, sitemap)
├── README.md  SETUP.md  AGENTS.md  CLAUDE.md
└── package.json  vite.config.ts  tailwind.config.ts  tsconfig.json
```

---

## 4. Day-1 setup

### 4a. Frontend only (Lovable preview)

```bash
npm install
npm run dev          # http://localhost:8080
```

Lovable Cloud auto-injects `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY`.
Chat will fall back to placeholder responses unless `VITE_BACKEND_URL` points
at a running FastAPI backend.

### 4b. Full stack locally

```bash
# 1. Backend (in another terminal)
cd backend
cp .env.example .env                 # fill secrets if needed
docker compose up -d --build         # starts Qdrant + FastAPI
ollama serve                         # on host, NOT in Docker
ollama pull sarvam-30b               # one-time

# 2. Frontend
cp .env.example .env.local
# .env.local:
#   VITE_BACKEND_URL=http://localhost:8000
#   VITE_USE_NATIVE_OAUTH=true       # only if running outside Lovable proxy
npm install
npm run dev
```

Smoke check: open http://localhost:8000/docs and http://localhost:8080.

---

## 5. Authentication flow

```
User → /auth ──signup/signin──► Supabase Auth ──onAuthStateChange──► /chat
                  │
                  └──Google──► lovable.auth.signInWithOAuth('google')
                                  │
                                  └─ Lovable proxy → Google → callback → session
```

- **Email/password**: standard Supabase. Email confirmation **required** by
  default; users get a verification link.
- **Google**: managed by Lovable Cloud; no client-ID setup needed.
- **Password reset**: `/reset-password` page handles the recovery hash and
  calls `supabase.auth.updateUser`.
- **Auth gate**: `useRequireAuth` hook wraps `ChatPage`; unauthenticated users
  are redirected to `/auth`.
- **Admin role**: stored in `public.user_roles` (never on `profiles`).
  `useAdminGuard` calls `has_role(auth.uid(), 'admin')` (SECURITY DEFINER RPC).

---

## 6. Chat request lifecycle

```
ChatInterface.handleSend()
   │
   ▼
sendMessageStreaming()  in src/lib/aiService.ts
   │
   │   POST  ${VITE_BACKEND_URL}/api/chat/stream
   │   body: { messages, user_message, meditation_step }
   ▼
FastAPI /api/chat/stream  (backend/app/main.py)
   │
   ▼
NeMo Input Rail ─► Depression Detector ─► LangGraph
                                              │
                                              ▼
   intent_router → decompose → retrieve → rerank → grade
                                              │ (CRAG loop ≤3×)
                                              ▼
                                         extract_hints → generate
                                              │
                                              ▼
                                  check_faithfulness → CoVe verify
                                              │
                                              ▼
                                       format_final_answer
                                              │
                                              ▼
                                    NeMo Output Rail
   │
   │  SSE events:
   │     event: token            { text }
   │     event: thinking         { step, status }
   │     event: done             { intent, citations, meditation_step }
   ▼
Frontend yields StreamChunks → ChatInterface updates message
   - tokens append to current guru bubble (markdown-rendered)
   - "done" event sets citations and triggers Serene Mind if intent==='DISTRESS'
```

---

## 7. Daily Teaching lifecycle

```
Admin /admin/daily-teaching
   │  upload image (storage bucket: daily-teachings)
   │  insert row in public.daily_teachings (expires_at = now+24h)
   ▼
Postgres realtime publication: supabase_realtime
   │  INSERT broadcast to subscribed clients
   ▼
src/components/chat/DailyTeaching.tsx
   .channel('daily-teachings-feed').on('postgres_changes', INSERT, …)
   refetch latest active row, render banner
   dismiss state keyed by teaching id, so a fresh upload re-shows
```

RLS: anyone authenticated can `SELECT` rows where `expires_at > now()`; only
admins can `INSERT`/`DELETE`.

---

## 8. Database

Tables (all under `public`):

| Table                | Purpose                              | Owner        |
| -------------------- | ------------------------------------ | ------------ |
| `profiles`           | display name, avatar, language       | self         |
| `conversations`      | one per chat                         | self         |
| `chat_messages`      | turns (role, content, citations)     | self via FK  |
| `meditation_sessions`| Serene Mind tracking                 | self         |
| `daily_teachings`    | admin-uploaded card                  | admins       |
| `user_roles`         | role assignments (admin, …)          | admins       |

Schema changes go through `supabase/migrations/*.sql`. Never edit
`src/integrations/supabase/types.ts` — it is auto-generated.

---

## 9. Testing

```bash
npm test                       # Vitest unit tests
npm run lint                   # ESLint
cd backend && pytest -q        # backend unit tests
```

Add a test next to the file you change. Match `src/**/*.{test,spec}.{ts,tsx}`.

---

## 10. Deployment

- **Lovable Cloud**: click *Publish*. `VITE_*` are injected automatically.
- **Self-hosted Docker**:
  ```bash
  docker compose -f docker-compose.prod.yml up -d --build
  ```
  Reverse-proxy `/api/*` to FastAPI and serve the Vite build at root.

---

## 11. Troubleshooting

| Symptom                                           | Likely cause / fix                                                 |
| ------------------------------------------------- | ------------------------------------------------------------------ |
| Chat shows placeholder responses                  | `VITE_BACKEND_URL` empty; set in `.env.local`                       |
| `useLocation()` outside `<Router>`                | Component imports moved outside `BrowserRouter`; keep them inside  |
| OAuth pop-up does nothing                         | `VITE_USE_NATIVE_OAUTH=true` outside Lovable proxy; set to `false` |
| 404 on `/api/chat`                                | Backend not running; `docker compose logs -f backend`              |
| Daily Teaching not refreshing                     | Realtime publication missing; re-run the migration in §7           |
| Admin login succeeds but `/admin` redirects out   | User has no row in `user_roles` with role `admin`                   |

---

## 12. Glossary

- **Stimulus RAG** — extract key hint phrases from retrieved docs before generation.
- **CRAG** — Corrective RAG; grade docs and rewrite query (≤ 3 loops).
- **Self-RAG** — LLM checks its own answer for faithfulness.
- **CoVe** — Chain of Verification; sub-questions to fact-check.
- **RAPTOR** — recursive clustering + summarization of chunks (2-level tree).
- **Beautiful State** — core teaching: state of calm, joy, connection.
- **Serene Mind** — 4-step guided meditation flow triggered by distress detection.

---

## 13. Where to look next

- `docs/ROADMAP.md` — prioritized backlog of pain points and benchmark moves.
- `SETUP.md` — focused environment-variable reference.
- `ARCHITECTURE.md` — deeper architectural rationale.
- `docs/admin/` — admin-console internals.

Welcome aboard. 🌅
