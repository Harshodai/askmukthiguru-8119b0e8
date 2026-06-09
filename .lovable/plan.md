## Findings

1. **Likely localhost chat auth break**
   - Frontend sends Google session JWT from `src/lib/aiService.ts` to `VITE_BACKEND_URL/api/chat/stream`.
   - Backend verifies JWT issuer/JWKS against `SUPABASE_URL` in `backend/services/auth_service.py`.
   - If frontend uses hosted auth URL but backend env still defaults to local `http://host.docker.internal:54321`, backend rejects token with 401. Result: stream produces no usable answer.

2. **Frontend hides root cause**
   - `ChatInterface.tsx` catches streaming failures silently when no partial text exists.
   - `sendMessage()` falls back to canned/offline guidance on backend/network/auth failure, so real backend failure is easy to miss.

3. **Backend URL not guaranteed in local Docker frontend**
   - `backend/docker-compose.yml` passes Supabase env to frontend build but does not pass `VITE_BACKEND_URL`.
   - Local browser can therefore call relative `/api/chat` or wrong endpoint unless `.env.local` is correct.

4. **Memory frontend only partial**
   - Current UI shows core profile + `guru_memories` via `/api/memory/core` and `/api/memory/list`.
   - It does not show `guru_core_memory` rows directly, `guru_session_summaries`, `conversation_memories`, or matched memories from `match_user_memories`.

## Plan

### 1. Make auth/session reliable before chat calls
- Add shared helper in frontend to get a fresh authenticated session for API calls.
- Use it in `aiService.ts` and `memoryApi.ts` instead of raw `getSession()` only.
- Retry streaming once after token refresh on 401/403, matching existing non-stream retry behavior.

### 2. Surface real chat failures in `/chat`
- In `ChatInterface.tsx`, replace silent stream catch with visible toast containing reason: auth expired, backend unreachable, non-SSE response, or server error.
- If backend returns empty successful response, show clear “backend returned empty answer” error instead of blank guru bubble.
- Keep fallback path, but mark it as offline only when backend truly unavailable.

### 3. Fix local backend targeting
- Update frontend config handling so local dev prefers `VITE_BACKEND_URL=http://localhost:8000` and diagnostics clearly flag missing value.
- Update Docker frontend build args/env to pass `VITE_BACKEND_URL` so containerized localhost uses backend service through nginx/proxy or explicit URL.
- Update docs with required local auth alignment:
  - frontend `VITE_SUPABASE_URL` must match backend `SUPABASE_URL`
  - backend `JWT_SECRET`/JWKS config must match same auth project
  - `VITE_BACKEND_URL=http://localhost:8000`

### 4. Expand memory API client
- Add typed methods in `src/lib/memoryApi.ts` for:
  - core memory rows (`guru_core_memory`)
  - episodic memories (`guru_memories`)
  - session summaries (`guru_session_summaries`)
  - conversation continuity (`conversation_memories`)
  - relevant matched memories for a query, via backend endpoint wrapping `match_user_memories`
- Keep graceful degradation if backend lacks one endpoint.

### 5. Show memory layer in frontend
- Extend `MemoryManager.tsx` with sections/tabs:
  - Core facts
  - Relevant memories
  - Session summaries
  - Conversation continuity
  - Manual add/forget
- Add a small `/chat` memory status panel or header indicator showing when memory layer is connected and recent matched memories are being used.

### 6. Validation
- Add/update tests for:
  - auth token refresh before chat
  - streaming 401 retry
  - backend unreachable/non-SSE error message
  - memory API partial endpoint failure does not break profile page
- Verify local flow manually: Google sign-in → `/chat` → authenticated stream answer → profile Memory tab shows memory data.