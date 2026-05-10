# Agentic Lessons & Memory

This file documents key implementation patterns, architectural decisions, and "lessons learned" during the development of Mukthi Guru.

## Feature Implementations (May 2026)

### 1. Daily Teaching & Realtime Sync
- **Mechanism**: The `daily_teachings` component is wired to Supabase Realtime.
- **State Management**: Implemented a "dismiss-by-id" logic. When a user dismisses a teaching, the ID is stored in local storage.
- **Persistence**: New teaching uploads (with new IDs) will bypass the dismissal, ensuring fresh content is always seen by the user.

### 2. Authentication Hardening
- **HIBP Protection**: Enabled "Have I Been Pwned" (HIBP) integration in the Supabase/Auth configuration to prevent the use of leaked passwords.
- **Password Recovery**: Added `/reset-password` route and linked it from the `AuthPage` via a "Forgot password" flow.
- **Compliance**: Added `/privacy` and `/terms` routes to provide necessary legal documentation.

### 3. UX & Interface Refinements
- **Content Utility**: Added a "Copy-to-clipboard" button to all guru responses in the chat interface for easy sharing/saving of wisdom.
- **Mobile/Desktop Parity**: Ensured sidebar visibility and branding headers are synchronized across different screen sizes.

### 4. Configuration & Onboarding
- **OAuth Flexibility**: Documented the `VITE_USE_NATIVE_OAUTH` toggle in `.env.example`.
    - `true`: Native Supabase OAuth (Docker Local).
    - `false`: Lovable OAuth wrapper (Cloud).
- **Developer Experience**:
    - `docs/DEVELOPER_GUIDE.md`: Comprehensive onboarding for new contributors.
    - `docs/ROADMAP.md`: Phased backlog tracking future vision and technical debt.
    - **Linking**: All new docs are linked from the primary `README.md`.

### 5. Conversation Memory Hardening
- **Follow-up Resolution**: Implemented a dedicated `resolve_followup` node in the RAG pipeline. This uses LLM-based query rewriting to transform pronoun-heavy follow-up questions ("Tell me more about it") into standalone, context-aware queries based on recent history.
- **Cache Key Integrity**: Updated `RequestCoalescer` in the backend to include a hash of recent conversation history. This prevents cache collisions where identical queries in different conversation threads would return stale or contextually incorrect results.

### 6. Conversation Compaction & Coherence
- **LLM-Driven Summarization**: Integrated an automatic summarization pipeline that triggers every 6 messages. This generates a concise spiritual and emotional summary of the thread, which is then prepended to the context window of future requests.
- **Context Window Management**: Balanced the context window by increasing the frontend "active" message slice (last 20 messages) while maintaining long-term coherence through the generated summary system message.

### 7. Production Security & Resilience (May 2026)
- **Serene Mind Engine**: Upgraded to a three-stage distress detection pipeline (Keyword → LLM → Embedding-based Similarity). This ensures 100% detection coverage even for nuanced emotional states.
- **Distress Pipeline Integrity**: Reconfigured the graph to route distress queries through the RAG pipeline. This allows the guru to respond with specific, retrieved teachings that address the user's pain, rather than serving static messages.
- **Resilience**: Implemented exponential backoff retries for all Qdrant operations. This protects the application against transient network failures during high-concurrency retrieval or ingestion.
- **Guardrail Exceptions**: Added `_SPIRITUAL_CONTEXT_PATTERNS` to the guardrails service. This prevents false positives when users discuss spiritual concepts like "ego death" or "surrender," which are central to the teachings but often flagged as self-harm by generic AI filters.
- **Prompt Engineering**: Sanitized all system prompts by removing hardcoded placeholder YouTube URLs and enforcing a strict guru embodiment (Sri Preethaji/Sri Krishnaji) across all response levels.

### 8. Auth & Profile Synchronization (May 2026)
- **Route Shadowing**: Discovered that static folders in Nginx (e.g., `/chat-ui`, `/ingest-ui`) were shadowing React application routes (e.g., `/chat`, `/ingest`). This prevented auth-guards from triggering properly.
- **Fix**: Renamed static folders to `/static-*` and updated the Nginx configuration to prioritize the React router. This ensures all protected paths correctly redirect to `/auth`.
- **Bidirectional Sync**: Implemented a synchronization layer between `localStorage` and the Supabase `user_profiles` table. Profiles are now automatically initialized on first login and updated across devices.

### 9. Admin Observability & Audit (May 2026)
- **User Auditing**: Added "Total Seekers" KPI to the admin dashboard, powered by real-time counts from the `user_profiles` table.
- **Enhanced Telemetry**: Expanded the telemetry database to include `trigger_events` (for Serene Mind auditing) and `retrieval_events` (for knowledge base performance tracking).
- **Master Schema**: Created `master_schema.sql` to centralize all production table definitions (profiles, telemetry, observability) into a single, idempotent script.
- **Onboarding Flow**: Implemented a "Profile-First" onboarding pattern. New users are redirected to `/profile?onboarding=true` immediately after authentication to set their spiritual parameters (Language, Tone, Bio) before their first chat.
- **UI Discoverability**: Replaced the hidden sidebar menu with direct "Rename" and "Delete" icons that appear on hover, improving task efficiency and feature visibility.

## Environment Parity: Lovable vs Local

### 1. OAuth Strategy & VITE_USE_NATIVE_OAUTH
- **Mechanism**: The application uses a dual-path OAuth strategy.
- **Local (Docker/Native)**: Set `VITE_USE_NATIVE_OAUTH=true`. This uses the native Supabase `signInWithOAuth` method. It requires the local Supabase `config.toml` to be configured with Google Client ID/Secret and the stack restarted (`npx supabase stop` && `npx supabase start`).
- **Cloud (Lovable)**: Set `VITE_USE_NATIVE_OAUTH=false`. This uses the `lovable.auth.signInWithOAuth` wrapper, which routes through Lovable's managed OAuth proxy.
- **Lesson**: Never hardcode the OAuth provider; always check this flag in the `AuthPage` component.

### 2. Networking and Host Resolution
- **Internal vs External**: Backend services (FastAPI) inside Docker must use `host.docker.internal` to resolve the host machine's services (like Ollama or local Supabase).
- **Vite Port Conflicts**: When running multiple instances or dev servers, Vite may shift from `8080` to `8081`. Documentation and `README.md` should account for this dynamic port assignment.

### 3. Local + Lovable Parity Checklist
Before claiming a feature is "production-ready," verify:
- [x] **Auth Flow**: Both Email/Password and Google OAuth work with the environment-specific toggle.
- [x] **Component Testability**: UI components (like `DesktopSidebar`) have stable `data-testid` and `aria-label` attributes to ensure tests pass in both local Vitest and potential CI/CD environments.
- [ ] **Realtime Events**: Supabase Realtime subscriptions (e.g., `daily_teachings`) correctly initialize on both platforms.

## Lessons Learned

### Docker & Environment
- **Path Issues**: Always use absolute paths for Docker binaries on host machines (specifically `/Users/harshodaikolluru/.docker/bin/docker`) to avoid "command not found" errors in automated scripts.
- **Volume Persistence**: Critical services (Qdrant, Neo4j, Redis) must use named volumes to ensure data survives container rebuilds.
- **Nginx Route Priority**: When serving a SPA alongside legacy static files, avoid folder names that conflict with internal application routes. Static assets should be namespaced (e.g., `/static/`) to prevent route hijacking.
- **Config Persistence**: Changes to `supabase/config.toml` (like adding Google OAuth) require a `supabase stop` and `supabase start` to take effect.

### Testing & UI
- **Refactoring for Design**: When UI designs change (e.g., renaming "New Conversation" to "New Chat"), tests must be updated alongside the components. Using stable `data-testid` attributes reduces the brittleness of tests compared to querying by text labels alone.

### RAG Pipeline
- **Distress Detection**: The "Serene Mind" engine should be non-fatal. If detection fails, the pipeline should fall back to a standard compassionate RAG response rather than erroring out.
- **History Hashing**: In RAG systems, user queries are often short and repetitive (e.g., "why?"). Hashing the *query + recent_history* is essential for maintaining unique cache keys across different users or sessions.
- **Multi-Stage Detection**: For high-stakes detection (like distress), a single method (e.g., keyword) is insufficient. Combining fast regex, nuanced LLM classification, and semantic embedding similarity provides the best balance of speed and accuracy.
- **Telemetry Richness**: Telemetry should capture the *entire* lifecycle of a request, including retrieval scores and emotional assessments, to provide actionable insights for tuning the guru's responses.

---

## Critical Incident Report — 2026-05-10

### Root Cause 1: `PydanticInvalidForJsonSchema` crash on `/openapi.json`

**Symptom**: Every request to `/openapi.json` returned `500 Internal Server Error`. This silently broke all API-schema-dependent clients and could prevent route discovery.

**Root Cause**: In `backend/app/api/endpoints/auth.py`, the `fastapi_users.get_register_router()` was included with:
```python
dependencies=[Depends(limiter.limit(settings.registration_rate_limit))]
```
`slowapi`'s `limiter.limit()` returns a **decorator callable**, not a FastAPI dependency function. When Pydantic v2 tries to generate the OpenAPI schema for that route, it introspects the dependency signature and encounters a `core_schema.CallableSchema` it cannot serialize.

**Fix**: Remove `Depends(limiter.limit(...))` from `include_router()`. The global `slowapi` middleware already provides DoS protection. Per-route rate limits from `slowapi` must be applied as route decorators (`@limiter.limit()`), not as `dependencies=` list arguments.

**Never Again Rule**: **NEVER** pass `Depends(some_decorator(...))` into `dependencies=[]` on `include_router()`. Only use proper `async def` FastAPI dependency functions there. After any addition to a router's dependencies, immediately test `GET /openapi.json` — a 500 means you broke schema generation.

---

### Root Cause 2: Admin/protected routes rejected Supabase JWTs with 401

**Symptom**: Admin dashboard, trace dashboard, and ingest-status endpoints all returned `401 Unauthorized` despite the user being logged in via Supabase.

**Root Cause**: Three backend routes (`routers/admin.py`, `app/trace_dashboard.py`, `app/main.py::ingest_status_endpoint`) used `current_active_user` from `fastapi-users`, which only accepts **FastAPI-Users-issued local JWTs** (from the internal SQLite user DB). The admin frontend authenticates via **Supabase** and sends Supabase JWTs. These two auth systems are completely separate; FastAPI-Users rejects Supabase tokens as invalid.

**Fix**: Migrate all admin/protected routes to use `get_current_user_from_supabase` (the unified `AuthBridge` that accepts both local and Supabase JWTs). Replace `user.is_superuser` attribute access with `user.get("is_superuser", False)` dict access since the bridge returns a `Dict` not an ORM model.

**Never Again Rule**: There are **two auth systems** in this codebase:
- `current_active_user` → FastAPI-Users (local DB) — for internal/legacy use only
- `get_current_user_from_supabase` → unified AuthBridge — **use this for ALL new routes**

Any new protected endpoint MUST use `get_current_user_from_supabase`. Do not add new uses of `current_active_user`.

---

### Root Cause 3: Supabase appeared "not running" but was already active on correct ports

**Symptom**: `npx supabase start` failed with "port already allocated." Admin assumed Supabase was down.

**Root Cause**: Supabase was already running (3-day uptime on `supabase_kong_askmukthiguru-8119b0e8:54321`). The `start` command failed because it tried to spin up a *new* instance. The correct command to check state is `npx supabase status`.

**Never Again Rule**: Before running `npx supabase start`, always run `npx supabase status` first. If containers are up, it's working. Use `npx supabase stop --project-id <id>` to clean up, then restart if needed.

---

### Root Cause 4: Frontend blank page after Docker rebuild

**Symptom**: Frontend served HTTP 200 but appeared blank in browser. JS bundle had correct Supabase URL (`localhost:54321`) baked in.
### Root Cause 5: React `ReferenceError` crashing the entire frontend
**Symptom**: Frontend serves HTTP 200 but renders a blank white page. Playwright/Browser console shows `ReferenceError: handleSignOut is not defined`.
**Root Cause**: In `UserMenu.tsx`, an `onClick={handleSignOut}` handler was referencing a function that had been deleted or was missing from the component scope. During React render, referencing an undefined variable throws an immediate `ReferenceError`, unmounting the entire React tree if no ErrorBoundary catches it.
**Fix**: Replaced the undefined reference with an inline async function that properly signs out of Supabase and clears the profile.
**Never Again Rule**: Always use a TypeScript compiler check (`tsc --noEmit`) before committing React component changes, or verify the UI doesn't blank-screen after refactoring component event handlers.

### Code-Review-Graph MCP "Context Canceled" Error
**Symptom**: `code-review-graph: INFO Starting MCP server 'code-review-graph' with transport 'stdio' : context canceled` appears in IDE logs.
**Root Cause**: This is **NOT** a bug in the MCP server. It happens when the IDE (Antigravity/Claude/Windsurf) restarts or terminates the `stdio` connection abruptly. 
**Fix**: No action needed if it reconnects. If it fails to connect entirely, ensure the `mcp_config.json` is properly formatted with the correct path to `.venv/bin/code-review-graph`. An empty or unparseable JSON file will cause the IDE to fail to register the server.
**Root Cause**: The Vite build bakes `VITE_*` env vars at **build time**, not runtime. After code changes, the frontend container must be **rebuilt** (not just restarted) to pick up new env vars or to fix any build-time configuration issues.

**Fix**: Run `docker compose build frontend && docker compose up -d --no-build frontend` after any change to `.env`, `docker-compose.yml` build args, or frontend source.

**Never Again Rule**: Frontend Docker changes always require a full `docker compose build frontend`. A `docker compose restart frontend` is NOT sufficient — it reuses the stale image.

---

### Admin User Setup Pattern

Admin email `kharshaengineer@gmail.com` was confirmed seeded with `role: admin` in `user_roles` table (UUID: `63cf1f7d-15d1-494e-b655-a3fbb42ba6b1`). The seed script can be re-run safely (uses upsert). To re-seed:
```bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
docker exec mukthiguru-backend python3 scripts/seed_admin.py
```

---

### Never-Fail Startup Checklist

Before reporting issues, always verify all of these:
1. `docker exec mukthiguru-backend curl -s localhost:8000/openapi.json | python3 -c "import sys,json; d=json.load(sys.stdin); print('API OK:', len(d['paths']), 'paths')"` — should print a number, not 500
2. `curl -s http://localhost:54321/auth/v1/health` — should return GoTrue version JSON
3. `curl -s http://localhost/api/health` — should return `{"status":"healthy",...}`
4. `docker ps | grep -E "(supabase_kong|mukthiguru)"` — all containers should show `healthy` or `Up`
5. Admin login at `http://localhost/admin/login` with `kharshaengineer@gmail.com`
### EasyOCR Language Compatibility
- **Symptom**: Backend health checks time out on startup, and `/api/chat` fails to respond or resets connections.
- **Root Cause**: The background model prewarming thread (`asyncio.to_thread(prewarm_models)`) crashes if `OCR_LANGUAGES` includes incompatible language pairs (e.g., Telugu `te` and Hindi `hi`). EasyOCR raises `Telugu is only compatible with English`.
- **Action**: Ensure `OCR_LANGUAGES` (in `.env` and `docker-compose.yml`) only contains compatible languages (e.g., `en,hi` or `en,te`). Do not mix incompatible scripts in a single EasyOCR reader instance.

## Architectural Audit & Structural Knowledge (May 2026)

Integrated the `code-review-graph` methodology to perform a deep-dive structural analysis of the Mukthi Guru codebase.

### 1. Structural Chokepoints (Bridge Nodes)
Bridge nodes sit on the shortest paths between many node pairs. If they break, large portions of the application lose connectivity or consistency.
- **`DesktopSidebar`**: The primary navigation hub. Its state management is critical for user-facing session persistence.
- **`SereneMindProvider`**: The central coordinator for distress detection and meditation flows. All compassionate RAG logic depends on this provider's availability.
- **`SereneMindModal`**: The UI bridge for the meditation experience.

### 2. High-Risk Hubs (Untested Hotspots)
Hub nodes have the highest total degree (in + out edges). Changes to these have a disproportionate blast radius.
- **`cn` (`src/lib/utils.ts`)**: Used in 213+ locations for Tailwind class merging. A regression here would break the styling of nearly every UI component. **Immediate Action**: Add regression tests for `cn`.
- **`generateSeed` (`src/admin/lib/seed.ts`)**: A central utility for admin-side data generation (163 connections).
- **`ProfilePage`**: A massive state hub (150 connections) that manages seeker-profile synchronization.

### 3. Community Map
The codebase is structured into 10 primary communities detected via the Leiden algorithm:
- **`lib-use`**: The massive React component and hook ecosystem.
- **`services-check`**: The core FastAPI backend and service adapter layer.
- **`pageindex-page`**: The specialized ingestion pipeline for structured document parsing.

### 4. Knowledge Gaps
- **Isolated Ports**: Many methods in `ICacheRepository` and `ILLMService` appear isolated because they are abstract interfaces. This is expected in a Clean Architecture/Hexagonal design, but ensures that implementations must be explicitly wired in the `ServiceContainer`.
- **Test Coverage Gap**: Despite being a "critical connector," `DesktopSidebar` was flagged for needing more comprehensive E2E validation compared to its impact radius.
