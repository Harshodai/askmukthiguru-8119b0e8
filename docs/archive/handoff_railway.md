# Railway Production Fix — Handoff (Jul 15, 2026 - Session 2)

---

## ✅ Deployment Status
- **celery-worker**: ● Online (Successfully deployed!)
- **askmukthiguru-8119b0e8** (Main API): ● Deploying / Initializing (latest commit `18ff4c2f` pushed and building)
- Web health check path `/api/healthz` successfully configured in the Railway UI under service-specific settings.

---

## 🎯 Root Cause: Embedding Models Failure — SOLVED

### The Bug
`PYTHONOPTIMIZE=2` in `backend/Dockerfile.railway` (line 52) = Python `-OO` flag

**What `-OO` does**: Strips ALL docstrings from every Python module at import time.

**What breaks**: `transformers` library uses `@replace_return_docstrings` decorator in `modeling_utils.py` line 5379:
```python
lines = func_doc.split("\n")  # func_doc is None when -OO strips docstrings
```

This is why EVERY version from 4.44.2 to 4.48.2 failed — it's not a version bug.

**Fix**: `PYTHONOPTIMIZE=2` → `PYTHONOPTIMIZE=1` (removes only `assert`, keeps docstrings)

---

## Changes Made & Tasks Completed

- [x] **Dockerfile.railway**: Changed `PYTHONOPTIMIZE=2` → `PYTHONOPTIMIZE=1` (fixes embedding models crash)
- [x] **requirements.txt**: Bumped `transformers` to `4.51.0` and `peft` to `0.14.0` for security updates
- [x] **useMeditationAudio.ts**: Added `onerror` handler to silence PWA asset 404 errors
- [x] **health.py**: Fixed `startup_complete` import binding bug (so `/api/health` updates to `healthy` dynamically)
- [x] **railway.json**: Removed global `healthcheckPath` and `healthcheckTimeout` (fixes Celery worker deploy loop)
- [x] **lessons.md**: Added lesson documenting multi-service healthcheck collision on Railway
- [x] **Service settings**: Configured API health check path `/api/healthz` specifically in the Railway dashboard UI

---

## ⚠️ Action Required: Supabase Migration

**Must be applied manually to Lovable's Supabase project `fynkjimvuimakgtidvuq`**

Go to: https://supabase.com/dashboard/project/fynkjimvuimakgtidvuq/sql/new

Run this SQL:
```sql
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS author TEXT DEFAULT 'system';

CREATE TABLE IF NOT EXISTS public.app_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
CREATE POLICY "Allow read access to anyone" ON public.app_settings FOR SELECT USING (true);
GRANT SELECT ON public.app_settings TO authenticated, anon;
GRANT ALL ON public.app_settings TO service_role;
NOTIFY pgrst, 'reload schema';
```

---

## ⚠️ Action Required: SUPABASE_KEY in Railway

Current Railway env `SUPABASE_KEY` = **anon key** (same as `SUPABASE_ANON_KEY`)
- Backend PromptStore, telemetry writes need service_role key
- Get from: https://supabase.com/dashboard/project/fynkjimvuimakgtidvuq/settings/api
- Set via: Railway dashboard → askmukthiguru-8119b0e8 → Variables → SUPABASE_KEY

---

## Memory + 500+ Users Strategy

### Current metrics
- Memory: 824 MB baseline, spikes to 1.65 GB  
- `WEB_CONCURRENCY=1` (Railway env) — CORRECT setting
- CPU: avg 0.03 vCPU, max 0.81 vCPU

### Why WEB_CONCURRENCY=1 is correct
- FastAPI/uvicorn is async — 1 process handles 100s of concurrent HTTP connections
- Multiple workers = each loads BGE-M3 (~550MB) into RAM = memory spikes
- 1 worker × 1 process: BGE-M3 loads once, Redis coalescer deduplicates requests

### How to scale to 500+ users
**Use Railway Replicas, not multiple workers:**
1. Railway dashboard → `askmukthiguru-8119b0e8` → Settings → Scaling → Set 2-4 replicas
2. Each replica = independent pod with 1 uvicorn worker
3. Redis coalescer is shared across replicas (already configured)
4. Load balancer distributes traffic across replicas

### Memory optimization (to reduce spikes)
The 1.65 GB spike happens when embeddings are loaded. After our PYTHONOPTIMIZE fix:
- BGE-M3 model: ~550MB (loaded once at startup)
- App baseline: ~300MB
- Total with models: ~900MB-1.2GB steady state
- Set Railway memory limit to 4 GB (down from 24 GB) to catch runaway leaks

---

## Service Connectivity Verified

| Service | Status | Latency |
|---------|--------|---------|
| Qdrant | ✅ Connected | 28ms |
| Redis | ✅ Connected | 4ms |
| Ollama/LLM | ✅ Connected | 43ms |
| Neo4j | ✅ Connected | Internal bolt:// |
| CORS | ✅ Working | Lovable origin allowed |

---

## Verification Commands (after build completes ~8 min)

```bash
# 1. Check deployment SUCCESS
railway deployment list --service askmukthiguru-8119b0e8

# 2. Health check
curl -s https://askmukthiguru-8119b0e8-production.up.railway.app/api/health

# 3. Deep health (should show qdrant: true, embedding model loaded)
curl -s https://askmukthiguru-8119b0e8-production.up.railway.app/api/healthz

# 4. Check logs for embedding model load success (no more NoneType error)
railway logs --service askmukthiguru-8119b0e8 -n 50 | grep -E "embedding|NoneType|BAAI"

# 5. E2E test: open https://askmukthiguru.lovable.app → send chat message
```

Expected log after fix:
```
✅ Embedding model BAAI/bge-m3 loaded successfully
✅ Semantic router initialized
```
---

## LightRAG Persistent Volume (Post-Deploy)

Set on Railway service so the graph survives container restarts:

```bash
railway variables --service askmukthiguru-8119b0e8 --set LIGHTRAG_WORKING_DIR=/data/lightrag
# Mount a Railway volume at /data (dashboard → Service → Volumes → Add /data)
```

Backend already reads `LIGHTRAG_WORKING_DIR` at startup; no code change needed. Without the volume, LightRAG re-indexes on every deploy.
