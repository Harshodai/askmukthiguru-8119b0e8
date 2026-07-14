# Session Handoff — Jul 15, 2026

## 1. Goal

Production remediation of AskMukthiGuru based on a fresh comprehensive audit. Two workstreams merged into one session:

**Workstream A — Transcription accuracy overhaul (zabt.ai adoption):**
Clone `https://github.com/afeef/zabt-ai`, compare architectures, adopt word-level alignment + speaker diarization + LLM speaker-role fallback into our Whisper pipeline. Shipped on branch `feat/zabt-transcription-adoption` (merged to main as commit `21d640ef`).

**Workstream B — Production audit remediation (P0-P5):**
A fresh re-audit flagged: dead backend, missing security headers, broken SEO, bloated bundle, no analytics. We verified the audit, corrected 3 misdiagnoses, and shipped fixes on branch `fix/prod-remediation-audit` (merged to main as commit `4437da4d`).

**Current goal:** Verify the Railway production deploy is live and healthy with all fixes applied. Deploy is in progress (see §2).

---

## 2. Current State of Code

### Branch
- **Current branch:** `main` (both work branches merged)
- **Latest commit:** `d0299a2e` — chore: add Railway MCP server
- **Work branches (merged):** `feat/zabt-transcription-adoption`, `fix/prod-remediation-audit`

### What shipped (Workstream A — transcription, already merged)
- `backend/app/contracts/transcription.py` — `TranscriptionProvider` Protocol
- `backend/services/whisperx_pipeline.py` (new) — WhisperX align + pyannote diarize + forced re-transcription
- `backend/services/whisper_local_service.py` — `transcribe_with_whisper_enhanced` wrapper + whisperx result cache (`cache_whisperx_result`/`get_cached_whisperx_result`/`clear_cached_whisperx_result`)
- `backend/ingest/pipeline.py` — `_resolve_chunk_speakers_from_cache` (word-overlap mapping) + `_resolve_chunk_speakers_with_llm` (closed-set role fallback: teacher/questioner/translator/narration/unknown — NO junk)
- `backend/requirements-gpu.txt` (new) — whisperx + torch isolated from main requirements
- `backend/app/config.py` — `whisperx_enabled` (default False), `llm_speaker_role_fallback_enabled` (default True), `diarization_min/max_speakers`, `hf_token`

### What shipped (Workstream B — audit remediation, already merged)
- **P0-fix:** `backend/app/core/limiter.py` — `_HEALTH_EXEMPT_PATHS` frozenset; health endpoints get unique exempt key (never 429)
- **P1:** `src/lib/backendUrl.ts:35` — `localhost:8000` gated behind `import.meta.env.DEV` (tree-shaken from prod). `index.html` — removed stale `ozmjeuqbholoxypfxixb.supabase.co` preconnect
- **P2:** `src/App.tsx` — 24 admin lazy imports + `<Route>` block gated behind `ADMIN_ENABLED = import.meta.env.VITE_ADMIN_ENABLED !== 'false'` (default true; set `'false'` to strip admin + chart-vendor from prod bundle)
- **P3:** `scripts/prerender-seo.mjs` (new, 310 lines) — generates 17 route-specific `dist/<path>/index.html` with unique title/meta/canonical/OG/Twitter/JSON-LD. `package.json` `build` = `vite build && node scripts/prerender-seo.mjs`
- **P4:** `src/components/ui/chart.tsx` — documented chart-vendor isolation boundary
- **P5:** `.env.example` — documented `VITE_SENTRY_DSN` + 4 other Vite vars. `src/lib/sentry.ts` — `trackPageview(path)`. `src/App.tsx` — `<RouteTracker />` inside `<AppRouter>`
- **Railway MCP:** `.opencode.json` — added `"railway": { "url": "https://mcp.railway.com" }`

### Audit corrections (important context)
1. **"Railway dead (HTTP 000)"** → FALSE. Backend ALIVE (429 = rate-limited). HTTP 000 was ISP DNS cache per dev.to case study.
2. **"No CSP / X-Frame-Options"** → FALSE for our deployment. `nginx.conf:9-15` already has all 6 security headers. Audit tested Lovable preview domain (`askmukthiguru.lovable.app`), not our nginx-served Railway backend.
3. **"No analytics"** → Partially false. Sentry (`src/lib/sentry.ts`) + Web Vitals (`src/lib/webVitals.ts`) already wired from `src/main.tsx:10-11`. Gap was product analytics (pageviews) — fixed via Sentry breadcrumbs (no new dep).

---

## 3. Files Actively Editing / Key Locations

| File | Role |
|------|------|
| `backend/app/core/limiter.py` | Rate limiter — health exempt set (P0-fix) |
| `src/lib/backendUrl.ts` | Backend URL resolution — localhost gated to DEV |
| `src/App.tsx` | Router — admin gated behind `ADMIN_ENABLED` + `<RouteTracker />` |
| `scripts/prerender-seo.mjs` | NEW — build-time SEO prerender for 17 routes |
| `index.html` | Base SPA template — stale Supabase preconnect removed |
| `.opencode.json` | MCP servers — Railway MCP added (needs session restart to activate) |
| `railway.json` | Railway deploy config — Dockerfile.railway, healthcheck `/api/health` |
| `backend/Dockerfile.railway` | Production image — Python 3.12 slim, 2 uvicorn workers |

### Deployment topology
- **Frontend (canonical):** `https://askmukthiguru.lovable.app` (Lovable-hosted SPA)
- **Backend:** `https://api.askmukthiguru.com` (custom domain, Railway) + `https://askmukthiguru-8119b0e8-production.up.railway.app` (direct Railway URL)
- **Backend URL resolution:** `src/lib/backendUrl.ts` — `VITE_BACKEND_URL` env → prod Railway URL when native/Lovable host → empty (relative `/api`)
- **Railway project:** `resilient-embrace` (ID `7cbd5f8c-2bb1-4ba8-8de9-8bc36a14e137`), env `production`
- **Services:** `askmukthiguru-8119b0e8` (backend), `celery-worker`, `gb-neo4j-railway-template`, `qdrant`, `Redis`

---

## 4. What I Tried and Failed

### Railway MCP activation
- Added `"railway": { "url": "https://mcp.railway.com" }` to `.opencode.json` (commit `d0299a2e`)
- **Problem:** MCP servers load at session start. The new Railway MCP won't be available in THIS session — needs a restart (new session) to activate.
- **Workaround used:** Railway CLI (`/opt/homebrew/bin/railway`, authenticated as `Harshodai`) for all deploy/status checks this session.

### Health endpoint 429 verification
- After merging the `/api/health` rate-limit exemption, I expected the new deploy to return 200 on health.
- **Current state:** `curl https://askmukthiguru-8119b0e8-production.up.railway.app/api/health` still returns **429 "rate limited"**.
- **Root cause hypothesis:** Railway rolling deploy — old replica (without the fix) still serves traffic while new replica initializes. The new deploy (`efc07f50`, status `DEPLOYING`) has not fully replaced the old one.
- **What I tried:** Waited ~9 min total (3 × 3-min sleeps). Still `Initializing (9m)` per `railway status`. Backend has 12Gi memory + model loading → slow init.
- **Did NOT try:** Forcing a redeploy via `railway up` (the auto-deploy from git push was already running; triggering a second could conflict).

### Custom domain `api.askmukthiguru.com`
- `curl https://api.askmukthiguru.com/api/health` returns **000** (connection failure).
- `dig api.askmukthiguru.com +short` returns **empty** (no A record).
- **Hypothesis:** Custom domain DNS not configured or not propagated. The direct Railway URL works (429 = alive). This is a Railway dashboard / DNS config issue, NOT a code issue.

### Build verification of prerender
- Did NOT run a full `npm run build` to verify `scripts/prerender-seo.mjs` generates all 17 files against the real `dist/`. The implementer tested it with a temp `dist/index.html`, but a real production build wasn't executed this session.

---

## 5. Next Steps (In Priority Order)

### Step 1 — Wait for deploy completion + verify health (5-10 min)
```bash
# Check deploy status
railway status | grep "askmukthiguru-8119b0e8:"

# Once status shows "Online" (not "Initializing"), verify health
curl -s -o /dev/null -w "%{http_code}\n" https://askmukthiguru-8119b0e8-production.up.railway.app/api/health
# EXPECTED: 200 (the rate-limit exemption is now in the new replica)
# If still 429 after deploy completes → the exempt paths don't match; check limiter.py
```

### Step 2 — Use Railway MCP (new session required)
Restart opencode to load the Railway MCP server, then use it for:
- Deployment status + logs without CLI
- Service variable management (e.g., set `VITE_ADMIN_ENABLED=false` on the frontend service to strip admin from prod bundle)
- Metrics + health monitoring
- Trigger redeployments cleanly

**In the new session, try:**
```
What Railway tools are available?
Show the latest deployment status for askmukthiguru-8119b0e8
Get the deployment logs for the latest deploy
```

### Step 3 — Fix custom domain `api.askmukthiguru.com`
The direct Railway URL works but the custom domain doesn't resolve.
```bash
dig api.askmukthiguru.com +short   # currently empty
railway domain list                # check if domain is attached to the service
# If not attached: railway domain add api.askmukthiguru.com
# If attached: check DNS provider (CNAME to railway.app or A record), wait for propagation
```

### Step 4 — Set production env vars for the frontend (Lovable)
The frontend is Lovable-hosted. To activate the P2 admin stripping + P3 SEO, the Lovable build needs:
- `VITE_ADMIN_ENABLED=true` (or `false` if admin should be stripped)
- `VITE_SENTRY_DSN` (Sentry DSN from dashboard)
- Confirm `VITE_BACKEND_URL` is set to the Railway URL (or empty for auto-resolve)
- Confirm `VITE_SUPABASE_URL` + `VITE_SUPABASE_PUBLISHABLE_KEY` point to the NEW Supabase project (`fynkjimvuimakgtidvuq`, not the old `ozmjeuqbholoxypfxixb`)

These are set in the **Lovable project settings**, not in our repo. Coordinate with whoever has Lovable access.

### Step 5 — Run a production build to verify prerender
```bash
npm run build
# Verify: ls dist/guides/ai-spiritual-companion/index.html  # should exist
# Verify: grep "AI Spiritual Companion" dist/guides/ai-spiritual-companion/index.html  # unique title
# If broken: debug scripts/prerender-seo.mjs
```

### Step 6 — Verify the SEO prerender is deployed
The frontend is Lovable-hosted — Lovable's build process may not run our `npm run build` script (which now includes the prerender step). If Lovable uses its own build, the prerendered files won't reach production. **Confirm Lovable runs `npm run build` (not just `vite build`).** If not, the prerender needs a different deployment path (e.g., deploy `dist/` to a CDN that respects the per-route HTML files).

### Step 7 — Supabase CORS restriction (P2 follow-up)
The audit flagged Supabase CORS `access-control-allow-origin: *`. This is a Supabase dashboard setting (not code). Log into the new Supabase project (`fynkjimvuimakgtidvuq`), go to Auth → URL Configuration, and restrict allowed origins to:
- `https://askmukthiguru.lovable.app`
- `https://api.askmukthiguru.com`
- (any other canonical prod URLs)

### Step 8 — MFA server-side enforcement (deferred P6)
`/auth/mfa` route exists client-side but no server-side guard. This was deferred. To implement: add MFA challenge endpoint in `backend/app/api/endpoints/auth.py` + verify MFA factor before issuing session JWT.

### Step 9 — Update AGENTS.md / lessons.md (per workspace rules)
Document: Railway MCP setup, the audit correction findings, the prerender build step, the `VITE_ADMIN_ENABLED` flag.

---

## Quick Reference

### Commands
```bash
# Railway CLI (authenticated this session)
railway status                    # service status
railway logs                       # live logs
railway deployment list           # recent deploys
railway up --detach               # trigger deploy

# Local build + SEO prerender
npm run build                     # vite build + prerender-seo.mjs
npm run build:seo                 # alias

# Verify health (after deploy completes)
curl -s -o /dev/null -w "%{http_code}\n" https://askmukthiguru-8119b0e8-production.up.railway.app/api/health

# Test admin stripping (build with flag)
VITE_ADMIN_ENABLED=false npm run build
# Then verify: grep -r "AdminShell" dist/assets/js/  # should return nothing
```

### Key commits on main
- `d0299a2e` — Railway MCP config
- `4437da4d` — Merge remediation (P0-P5)
- `21d640ef` — Merge transcription overhaul (Workstream A)

### Open questions for next session
1. Does Lovable run `npm run build` (with prerender) or just `vite build`? Determines if P3 SEO actually reaches production.
2. Is `api.askmukthiguru.com` custom domain supposed to work, or is the direct Railway URL the canonical backend?
3. Should `VITE_ADMIN_ENABLED` be `false` in the Lovable production build (strip admin from public site)?