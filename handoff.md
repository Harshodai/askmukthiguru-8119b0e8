# Session Handoff — Jul 16, 2026 (Session 3)

## Goal
Debug Railway deployment background init hang, fix per-service health endpoint, verify E2E chat pipeline, and resolve React passive wheel event issue in MemoryManager.

## Current State
- **Backend** deployed on Railway (deployment `32c9c228`), `/api/health` returns `ready: true`, all critical services green.
- **Background init** runs inline with `wait_for(180s)` before lifespan yield — no more `create_task`.
- **Chat E2E** verified: intent classification → retrieval → LLM (OpenRouter llama-3.3-70b-instruct) → guardrails in 5.3s.
- **Frontend MemoryManager** wheel zoom fix already in place (native `addEventListener` with `passive: false` at `src/components/profile/MemoryManager.tsx:410-421`).
- 138 tests pass, 3 skipped, 1 pre-existing failure (`test_health_check_one_failing`).

## Files Actively Being Edited
- `backend/app/main.py` — lifespan + `_background_startup_body`
- `backend/app/api/health.py` — per-service health probes
- `backend/app/dependencies.py` — `startup_complete`, `startup_error` module vars
- `backend/app/container.py` — graph build timeouts
- `backend/start_railway.py` — ASGI wrapper, healthz intercept
- `backend/services/auth_service.py` — TestAuthStrategy blocked in production
- `backend/infrastructure/scheduler.py` — start/shutdown lifecycle
- `backend/lessons.md` — session lessons

## What Was Tried & Failed
1. **`asyncio.create_task` for deferred init** — task never scheduled by event loop under Railway's ASGI wrapper. Even `await asyncio.sleep(0)` after creation didn't help. Three deployments confirmed this.
2. **`railway redeploy --from-source`** — stuck at INITIALIZING. Workaround: `railway up` (tarball upload) works reliably.
3. **`num_replicas: 2` in railway.json** — caused second replica to fail (init timeout). Reduced to **1 replica**.
4. **LightRAG singleton reload on `_background_startup`** — reloading `LazyRAG` instances failed with `AttributeError` because previous instance and new instance share internal state. Workaround: set LR to `None` and recreate from scratch.

## Next Steps
1. **Feed Sri Preethaji / Kriya doctrine into vector store** — chat queried "Who is Sri Preethaji?" returned a connection-issue fallback because no relevant doctrine exists. This is a content ingestion gap, not a pipeline bug.
2. **Wire frontend connection status panel** to display `/api/health/services` results so users see per-service health in the UI.
3. **Add `/_bg_status` debugging endpoint** showing current background startup phase and individual service init progress.
4. **Run `railway up` to deploy the next change** — currently all containers are healthy on `32c9c228`.
