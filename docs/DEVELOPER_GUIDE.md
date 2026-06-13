# AskMukthiGuru — Developer Guide

> A complete, end-to-end onboarding document for new contributors.
> If you have just cloned this repo, read this top-to-bottom before changing anything.

---

## 1. What this project is

AskMukthiGuru is a privacy-first AI spiritual companion grounded in the public
teachings of Sri Preethaji and Sri Krishnaji. It pairs a React/Vite/TypeScript
frontend (deployed on **Lovable Cloud**) with a Python FastAPI backend that
runs a 12-layer retrieval-augmented-generation (RAG) pipeline against a local
Qdrant vector store and a local Ollama LLM or cloud OpenRouter (supporting free-tier Llama models).

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

OpenTelemetry traces are exported to Jaeger when `OTEL_ENABLED=true`:

```bash
OTEL_SERVICE_NAME=mukthiguru-backend
OTEL_EXPORTER_OTLP_ENDPOINT=http://jaeger:4317
OTEL_PYTHON_FASTAPI_EXCLUDED_URLS='^(?!.*\/api\/chat(?:\/stream)?(?:\?.*)?$).*'
OPENINFERENCE_HIDE_EMBEDDINGS_VECTORS=true
VITE_JAEGER_UI_URL=http://localhost:16686
```

Smoke check: open http://localhost:8000/docs, http://localhost:8080, and http://localhost:16686.

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
   │   body: { messages, user_message, meditation_step, session_id }
   ▼
FastAPI /api/chat/stream  (backend/app/main.py)
   │
   ▼
Normalize session_id ─► Load compact memory context
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
   - response cache keys include the selected language; language changes clear the in-memory frontend cache
   - Regenerate removes the last guru bubble and replays the existing user turn without appending a duplicate query
```

Memory notes:
- `ChatInterface` passes the active conversation id as `session_id` on both
  streaming and non-streaming calls.
- The backend semantic cache prefixes entries with preferred language. This is
  required so Telugu/Hindi/etc. responses never reuse an English cached answer.
- If the user selects an Indic output language but types English text, the
  backend keeps the user query in English and only translates the final answer
  back to the selected language.
- `backend/rag/memory.py` maps local non-UUID ids to deterministic UUIDs with
  `uuid5`, preserving browser continuity while satisfying Supabase UUID tables.
- The generated prompt treats memory as personalization and reference-resolution
  context only; spiritual facts must still come from retrieved teachings.

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
| `conversation_memories` | compact backend continuity summaries | backend service |
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

## 11. Production Benchmarking

The production-readiness harness lives under `backend/benchmarks/`.

```bash
# Full coordinated suite: HTTP ruthless benchmark + native faithfulness eval
python3 backend/benchmarks/run_all.py --endpoint http://localhost:8000

# Fast CLI/import check
python3 backend/benchmarks/run_all.py --help

# HTTP-only benchmark
python3 backend/benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000
```

Reports are written to `backend/benchmarks/reports/`. The HTTP benchmark expects `/api/chat` to expose `faithfulness_score`, `relevancy_score`, `confidence_score`, `verification`, and `hallucination_flag` so the suite can score answer quality, trajectory-adjacent verification, citations, multi-turn retention, and performance without relying only on exact output matching.

Use `.venv/bin/python` or `backend/.venv/bin/python` for local verification. The macOS system Python 3.9 cannot import the backend because the project uses Python 3.10+ type syntax.

---

## 12. Troubleshooting

| Symptom                                           | Likely cause / fix                                                 |
| ------------------------------------------------- | ------------------------------------------------------------------ |
| Chat shows placeholder responses                  | `VITE_BACKEND_URL` empty; set in `.env.local`                       |
| `useLocation()` outside `<Router>`                | Component imports moved outside `BrowserRouter`; keep them inside  |
| OAuth pop-up does nothing                         | `VITE_USE_NATIVE_OAUTH=true` outside Lovable proxy; set to `false` |
| 404 on `/api/chat`                                | Backend not running; `docker compose logs -f backend`              |
| Daily Teaching not refreshing                     | Realtime publication missing; re-run the migration in §7           |
| Admin login succeeds but `/admin` redirects out   | User has no row in `user_roles` with role `admin`                   |

---

## 13. Glossary

- **Stimulus RAG** — extract key hint phrases from retrieved docs before generation.
- **CRAG** — Corrective RAG; grade docs and rewrite query (≤ 3 loops).
- **Self-RAG** — LLM checks its own answer for faithfulness.
- **CoVe** — Chain of Verification; sub-questions to fact-check.
- **RAPTOR** — recursive clustering + summarization of chunks (2-level tree).
- **Beautiful State** — core teaching: state of calm, joy, connection.
- **Serene Mind** — 4-step guided meditation flow triggered by distress detection.

---

## 14. Where to look next

- `docs/ROADMAP.md` — prioritized backlog of pain points and benchmark moves.
- `SETUP.md` — focused environment-variable reference.
- `ARCHITECTURE.md` — deeper architectural rationale.
- `docs/admin/` — admin-console internals.

Welcome aboard. 🌅

---

## 14. Performance & SEO conventions

- **Lazy-load admin chunk.** All `/admin/*` pages are imported via `React.lazy` in
  `src/App.tsx`. End-user bundle never pulls them. Keep this pattern when
  adding new admin pages.
- **Per-route SEO.** Use `usePageMeta({ title, description, canonical })`
  from `src/hooks/usePageMeta.ts` at the top of every public page. The hook
  restores previous meta on unmount so SPA navigation never leaks stale
  titles to crawlers.
- **JSON-LD.** Site-wide `WebApplication` schema lives in `index.html`.
  Per-route schema (e.g. `Article` for teachings) should be added inside the
  page component using `<script type="application/ld+json">`.
- **Sitemap & robots.** `public/sitemap.xml` and `public/robots.txt` are
  static. Update sitemap when you add a new public route.

## 15. Local + Lovable parity checklist

When you ship a feature, verify both surfaces:

## 16. macOS Sleep Prevention & Resumable Ingestion

When running large-scale ingestion pipelines (e.g. transcribing 20+ video playlists sequentially using local Apple Neural Engine accelerated Whisper), execution times can span several hours. macOS automatically suspends idle processes by default, interrupting transcription or database writing.

To prevent this programmatically without requiring manual configuration changes, the ingestion framework incorporates a monitored `caffeinate` subprocess:
```python
import subprocess
import os

# Spawns caffeinate bound to the Python process PID
caffeinate_proc = subprocess.Popen(["caffeinate", "-w", str(os.getpid())])
```
This forces the host system to maintain full CPU, disk, and network activity exactly for the lifespan of the parent ingestion process.

Additionally, the pipeline writes successful step signatures to `scripts/ingestion_state.json`. If execution is manually aborted or interrupted by network dropouts, running the script again will resume exactly where it left off, avoiding redundant compute.

## 17. Asynchronous Supabase Telemetry Sink & Custom Agent Skills

### Asynchronous Telemetry Sink
Observability events (queries, responses, retrieval events, spans, trigger events, and safety evaluations) are logged to Supabase via `SupabaseTelemetrySink` located in [telemetry_sink.py](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/backend/app/telemetry_sink.py).
To ensure database inserts do not impact client response latencies or block the main event loop, all database writes are delegated to a thread pool executor:
```python
loop = asyncio.get_running_loop()
await loop.run_in_executor(None, do_inserts)
```
The sink reads `SUPABASE_SERVICE_ROLE_KEY` from the environment to perform safe, authenticated inserts.

### Technical Agent Skills Compilation
The workspace includes a generation script [generate_all_skills.py](file:///Users/harshodaikolluru/Public/askmukthiguru-8119b0e8/scripts/generate_all_skills.py) that compiles large technical books into structured agent skills. These are installed in two locations:
1. Local skills: `.agents/skills/<slug>/`
2. Global user skills: `~/.config/agents/skills/<slug>/`

Each compiled skill folder contains:
- `skill.md`: Definition schema and entrypoints.
- `chapters/`: Structured chapter-by-chapter summaries.
- `glossary.md`: Key terms with definitions.
- `patterns.md`: Concrete design patterns.
- `cheatsheet.md`: Decision matrices and compare tables.

## 18. Local Codebase Intelligence & Memory MCP Layer

To enable maximum agent productivity and completely offline codebase analysis, three custom Model Context Protocol (MCP) servers reside in the `mcp-servers/` directory.

### Architecture and Components

1. **Graphify (`mcp-servers/graphify`)**:
   - Python-based codebase graph indexing framework using Abstract Syntax Tree (AST) scanning.
   - Outputs a structural graph index in `graphify-out/graph.json`.
   - Exposes robust semantic graph and impact radius tools.
   
2. **Claude-Mem (`mcp-servers/claude-mem`)**:
   - TypeScript/Node memory server running on Bun.
   - Manages episodic and semantic memory context with a background SQLite worker service.
   
3. **CodeGraph (`mcp-servers/codegraph`)**:
   - TypeScript/Node AST query engine leveraging WASM-compiled tree-sitter grammars.
   - Initializes a fast SQLite FTS5 index under `.codegraph/`.

### Strict Developer Constraints

- **Node 22 LTS (Strict Requirement)**: CodeGraph leverages WASM-based tree-sitter bindings. Modern Node `25.x` has a critical JIT Zone allocation bug that will crash during grammar parsing. Ensure your environment links explicitly to Node 22 (e.g. `/opt/homebrew/opt/node@22/bin` on macOS).
- **Bun Installation**: The memory worker uses Bun's fast SQLite/ChromaDB native bindings and requires `bun` to be installed on the host (`/opt/homebrew/bin/bun`).
- **Worktree Accumulation**: Make sure to run `git worktree prune` and delete any locked temporary agent worktrees under `.claude/worktrees/agent-*` regularly to prevent local shell lag.

### Local and Global Integration

These servers are fully registered:
- **Local Codex/Antigravity IDE**: Defined in `.mcp.json` at the project root.
- **Global Claude CLI**: Registered in `~/.claude.json`.
- **Global Hermes Agent CLI**: Registered in `~/.hermes/config.yaml`.

