<!-- Archived verbatim from root AGENTS.md on 2026-10-19 to cut context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on it. -->

# Archived from AGENTS.md: agents-md-railway

## Railway Deployment (Production)
- **Project**: `resilient-embrace` | **Service**: `askmukthiguru-8119b0e8` | **Environment**: `production`
- **Status (Aug 11, 2026)**: Railway is **paused** (stopped for a while). Before the next deploy, set `FORWARDED_ALLOW_IPS` (e.g. `10.0.0.0/8`) — `start_railway.py` now exits at startup without an explicit non-wildcard value (fail-closed; see Security Invariants). Until then, dev continues on the docker compose stack, which runs plain uvicorn and needs no such var.
- **Deploy method**: Use `railway up` (tarball upload) — **NOT** `railway redeploy --from-source`
  - `railway up` uploads a tarball and deploys reliably
  - `railway redeploy --from-source` gets stuck at INITIALIZING on this repo
- **Replicas**: **1 replica** (dashboard setting — 2 replicas caused second replica to fail init timeout; `railway.json` was removed Sep 19 in favor of `.railway/railway.ts` IaC + dashboard)
- **Health checks**:
  - `/api/healthz` — intercepted by `start_railway.py` wrapper, returns 200 for 90s grace period
  - `/api/health` — real per-service health, returns `ready: false` until `startup_complete=True`
- **Docker path for CLI**: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && railway <cmd>`
- **Link service**:
  ```bash
  railway link --project resilient-embrace --service askmukthiguru-8119b0e8
  ```
- **View logs**: `railway logs` (shows interleaved from all deployments; use `--deployment <id>` for specific)
- **Environment variables**: Set via `railway variables --json '{"KEY": "value"}'` or dashboard
- **Key env vars for backend**: `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `QDRANT_URL`, `QDRANT_API_KEY`, `REDIS_URL`, `NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD`, `IS_PRODUCTION=true`

### Railway Env Access
To read Railway service env vars locally (useful for Supabase Admin API, debugging):
```bash
railway run --service askmukthiguru-8119b0e8 --environment production -- python3 -c "import os; print(os.environ.get('SUPABASE_URL'))"
```

### Forcing Railway Deploy
`railway up` skips if tarball hash matches. Make a real file change to force build. `railway up --message "..."` alone does NOT force a build.

### Supabase — Create E2E Test User in Production
Supabase project `ozmjeuqbholoxypfxixb` has `mailer_autoconfirm: false`. Use service_role key via `railway run` + Admin API:
1. `railway run --service askmukthiguru-8119b0e8 --environment production -- python3 -c "import os; supabase_key = os.environ.get('SUPABASE_KEY', ''); print('SERVICE_KEY obtained (not printed)', len(supabase_key) > 0)"` to confirm SERVICE_KEY is available (don't print the key)
2. Use the key directly in the Admin API request: `curl -X POST https://ozmjeuqbholoxypfxixb.supabase.co/auth/v1/admin/users -H "apikey: $SUPABASE_KEY" -H "Authorization: Bearer $SUPABASE_KEY" -H "Content-Type: application/json" -d '{"email":"test@example.com","password":"test123","email_confirm":true}'`
3. Sign in with password grant to get `access_token`
4. Delete user after: `DELETE /auth/v1/admin/users/{id}`

### start_railway.py — Blocking Import Fix
`_run_real_lifespan()` must NOT import `app.main` directly on the event loop — PyTorch model loading blocks for 10-30s, freezing health checks. Use `asyncio.to_thread(_import_real_app)`. If Railway health check says "service unavailable" but build succeeds, the event loop is likely blocked by a synchronous import. See `lessons.md` "Jul 17, 2026 — Blocking Import on Event Loop Freezes Health Check".
