# AskMukthiGuru — Developer Guide

> A complete, end-to-end onboarding document for new contributors.
> If you have just cloned this repo, read this top-to-bottom before changing anything.

---

## 1. What this project is

AskMukthiGuru is an AI spiritual companion grounded in the public teachings of
Sri Preethaji and Sri Krishnaji. It pairs a React/Vite/TypeScript frontend
(deployed on **Lovable Cloud** + **Railway**) with a Python FastAPI backend
that runs a **12-layer** retrieval-augmented-generation (RAG) pipeline.

Current runtime defaults (updated 2026-08-01; see `AGENTS.md` for invariants):

- **LLM provider**: Sarvam Cloud 30B (Indian multilingual), OpenRouter (Llama
  free tier), or NIM (low latency) — set via `LLM_PROVIDER` env var.
- **Safety guardrails**: `GUARDRAILS_PROVIDER=lightweight` — 13 regex-based topic
  categories + prompt injection detection + emotional wellness redirects.
  NeMo Guardrails is available in `backend/guardrails/` but not the runtime default.
- **Hosting**: Railway.app (backend, via `backend/Dockerfile.railway`); Lovable Cloud
  (frontend build + Supabase auth). `docker-compose.prod.yml` is for self-hosted.
- **Target**: < 3 s TTFT, < 1 % hallucination rate (measured by eval harness).

> ⚠️ `docs/SPEC_DEV.md` describes the original v1 zero-budget / local-Ollama
> architecture. It is **historical only** — not the current production constraints.

---

## 2. Architecture at a glance

```
┌──────────────┐   HTTPS    ┌───────────────────┐   SQL/RLS  ┌────────────────┐
│  React UI    │◄──────────►│ Lovable Cloud /   │◄──────────►│   Supabase     │
│ (Vite, TS)   │  auth +    │ Supabase Auth     │            │ Postgres + RLS │
└──────┬───────┘  realtime  └───────────────────┘            └────────────────┘
       │
       │ SSE  POST /api/chat/stream
       ▼
┌──────────────┐  HTTP/gRPC ┌────────────────┐   Bolt     ┌─────────────────┐
│  FastAPI     │◄──────────►│    Qdrant      │            │    Neo4j 5.17   │
│  (12-layer   │  vector    │ (89k+ vectors) │            │ (LightRAG KG)   │
│   RAG)       │  search    └────────────────┘            └─────────────────┘
└──────┬───────┘
       │  LLM completions (cloud)
       ▼
┌─────────────────────────────────────────────────────────┐
│  LLM Provider (one of):                                 │
│    Sarvam Cloud 30B  |  OpenRouter Llama  |  NIM API   │
└─────────────────────────────────────────────────────────┘
```

Three deployable surfaces:

| Surface           | Hosted on                   | Entry file                     |
| ----------------- | --------------------------- | ------------------------------ |
| End-user web app  | Lovable Cloud + Railway     | `src/main.tsx` → `src/App.tsx` |
| Admin console     | Same bundle, `/admin`       | `src/admin/layout/AdminShell`  |
| FastAPI backend   | Railway (`backend/Dockerfile.railway`) | `backend/app/main.py` |

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
cp .env.example .env                 # fill secrets: LLM_PROVIDER, SARVAM_API_KEY, etc.

# Start infrastructure containers (Qdrant, Neo4j, Redis)
bash ../scripts/docker-safe.sh docker compose up -d qdrant neo4j redis

# Run FastAPI on host (override docker hostnames for local)
export QDRANT_URL=http://localhost:6333 NEO4J_URI=bolt://localhost:7687 \
       REDIS_URL=redis://:mukthiguru_redis_pass@localhost:6379/0
.venv/bin/uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Frontend
cp .env.example .env.local
# .env.local:
#   VITE_BACKEND_URL=http://localhost:8000
#   VITE_USE_NATIVE_OAUTH=true       # only if running outside Lovable proxy
npm install
npm run dev
```

> **Note**: Ollama is available as a fallback LLM provider (`LLM_PROVIDER=ollama`)
> for fully offline dev, but is not used in production. Cloud providers
> (Sarvam, OpenRouter, NIM) are the defaults.

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
Input Rail (GUARDRAILS_PROVIDER=lightweight by default)
   │  13 regex topic categories + prompt injection + emotional wellness redirects.
   │  NeMo/LlamaGuard available in backend/guardrails/ but not the active default.
   │
   ▼
Depression Detector ─► 12-layer RAG pipeline
                              │
                              ▼
   intent_router → decompose → retrieve (Qdrant + Neo4j)
                              │
                              ▼
                    rerank (cross-encoder) → grade (CRAG ≤3×)
                              │
                              ▼
                    extract_hints → 3-Pass Generation:
                              │   Pass 1: inline citation verification
                              │   Pass 2: factually grounded draft
                              │   Pass 3: Guru voice tone adapter
                              ▼
                    CoVe verify → faithfulness gate
                              │
                              ▼
                       format_final_answer
                              │
                              ▼
                    Output Rail (lightweight regex)
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
| Neo4j UI connection fails (`WebSocket failure`)    | Browser blocks unencrypted `bolt://` when Neo4j UI is served via HTTPS (Mixed Content). Connect using `bolt+s://` or `neo4j+s://` with SSL config, or access UI via plain HTTP (`http://`). Note that connecting to `localhost` inside the browser will connect to the client machine, not the docker host; use the actual server IP/hostname instead. |

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


## Local Dev Without Docker (Jul 31, 2026)

`backend/.env` ships docker-network hostnames. To run backend/tests on the host, export overrides first:

```bash
export QDRANT_URL=http://localhost:6333 NEO4J_URI=bolt://localhost:7687 \
  REDIS_URL=redis://:mukthiguru_redis_pass@localhost:6379/0 SUPABASE_URL=http://127.0.0.1:54321
# backend on a non-default port (8000 may be taken by another Docker stack):
cd backend && .venv/bin/python -m uvicorn app.main:app --port 8001
# frontend, pointing at it:
VITE_BACKEND_URL=http://localhost:8001 npm run dev   # Playwright reuses this server
```

Infra: `make dev-up` starts qdrant+redis (`mukthiguru-*` containers); local Supabase via `npx supabase start`. Playwright auto-starts Vite but NOT the backend.

Gotchas: delete `backend/dotenv/` if present (shadows python-dotenv → `.env` silently ignored); never kill docker-proxy processes to free a port (engine restarts).
