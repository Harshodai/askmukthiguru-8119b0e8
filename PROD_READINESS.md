# Production Readiness Notes

## Frontend (this repo)

### Sentry
- `src/lib/sentry.ts` initialized in `main.tsx`. Guarded to only enable on `*.lovable.app` hosts.
- **TODO** (manual): Set `VITE_SENTRY_DSN` in Lovable → Project Settings → Environment Variables. This is a frontend Vite env var, must be set in Lovable UI (not Railway).
- `captureFeatureError(err, feature, extra?)` tags errors by feature area. Current features: `chat`, `translation`, `language`, `meditation`, `auth`.
- `ignoreErrors` filters out ResizeObserver, fetch failures, and AbortError.

### Language selector font size
- Non-English pill label: `text-base leading-none` + `h-9` pill.
- Dropdown rows: native-script label `text-lg` (Latin `text-base`).
- Fixes readability for Devanagari, Telugu, Tamil, Malayalam, Kannada, Bengali, Gujarati, Odia, Punjabi, Urdu, Assamese, Sanskrit.

## Backend (Railway FastAPI)

### CORS — ✅ Done
- `CORS_ORIGINS` set on Railway: `https://askmukthiguru.lovable.app,https://*.lovable.app,http://localhost:5173`
- Middleware already wired in `backend/app/main.py:410-417` with wildcard-to-regex conversion.

## Supabase — ✅ Verified

**Project**: `ozmjeuqbholoxypfxixb.supabase.co`

### Env vars on Railway — ✅ All Set
| Variable | Status |
|---|---|
| `SUPABASE_URL` | ✅ `https://ozmjeuqbholoxypfxixb.supabase.co` |
| `SUPABASE_KEY` (service role) | ✅ JWT with `role: service_role` |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ Set (same as SUPABASE_KEY) |
| `SUPABASE_ANON_KEY` | ✅ Present |

### Env vars on frontend — ✅ Match
- `.env.production` has `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` pointing to `ozmjeuqbholoxypfxixb`.

### Tables verified (~40 tables) — ✅ All Present
`profiles`, `user_profiles`, `user_roles`, `conversations`, `conversation_memories`, `chat_messages`, `chat_queries`, `chat_responses`, `chat_sessions`, `gurus`, `assistants`, `assistant_configurations`, `assistant_doctrines`, `assistant_access`, `kb_sources`, `kb_chunks`, `meditation_sessions`, `ingest_jobs`, `ingestion_runs`, `ingestion_checkpoints`, `token_usage`, `telemetry_events`, `user_feedback`, `feedback_events`, `trace_spans`, `notes`, and more.

### RLS policies — ⚠️ Not checked (requires Supabase dashboard access)
- Verify in Supabase dashboard: Authentication → Policies for each table.
