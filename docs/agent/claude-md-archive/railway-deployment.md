<!-- Archived verbatim from root CLAUDE.md on 2026-10-19 to cut per-session context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on any number. -->

# Archived from CLAUDE.md: railway-deployment

### Railway (Production Deployment & Cost Controls)
- **Project**: `resilient-embrace` | **Service**: `askmukthiguru-8119b0e8` | **Environment**: `production`
- **Current Status (Sep 20, 2026)**: **ALL SERVICES SCALED DOWN / OFFLINE (Compute = $0/hr)**.
  - Backend, Memgraph, and Qdrant deployments removed via `railway down --service <name> --yes` to stop all compute charges.
  - Managed `Redis` is `● Sleeping`.
  - All data volumes (`qdrant-volume`, `memgraph-volume`, `redis-volume`) are preserved intact.
- **Cost Analysis & Memory Utilization**:
  - Railway charges **$10/GB RAM/month** ($0.000231/GB/min) and **$20/vCPU/month**.
  - Total active memory baseline when running is **~3.72 GB RAM** (~$37-$42/month or ~$1.25-$1.40/day):
    - Backend API: **~1.81 GB RAM** ($18.10/mo) — loads ONNX BGE-M3 (560MB), ONNX Reranker (570MB), LettuceDetect ModernBERT (350MB), MiniLM intent (90MB), and LangGraph runtime (250MB).
    - Qdrant: **~1.33 GB RAM** ($13.30/mo) — HNSW index & segment caches for 12,904 chunks + LightRAG collections.
    - Memgraph: **~0.57 GB RAM** (570.6 MiB / 1 GiB limit, $5.70/mo) — in-memory graph index for 6,430 nodes / 4,188 rels.
    - Redis: **~0.01 GB RAM** ($0.10/mo) — hot cache & queues.
  - **Why Serverless wasn't sleeping automatically**: Railway requires **10 minutes of complete inactivity** to trigger sleep. Incoming HTTP traffic hitting `/api/capabilities` and `/api/metrics` every 2-4 seconds continuously reset the inactivity timer.
- **How to Spin Up Services (When Ready)**:
  1. Databases:
     ```bash
     railway redeploy --service qdrant
     railway redeploy --service memgraph
     # Redis wakes up automatically upon receiving connections
     ```
  2. Backend:
     ```bash
     railway up
     # OR: railway redeploy --service askmukthiguru-8119b0e8
     ```
  Or via Railway Dashboard ➡️ Select service ➡️ Deployments ➡️ Redeploy.
- **Deploy method**: Multi-stage Dockerfile (`backend/Dockerfile.railway`) with CPU-only wheels and INT8 ONNX models (~2.2GB image).
- **Health checks & Deployment Probes**:
  - Effective live setting: Deployments configure `healthcheckPath: /api/health` with `healthcheckTimeout: 300` (or `healthcheckPath: /api/healthz` with `healthcheckTimeout: 120`). Target `/api/health` for deployment gating so Railway verifies full subservice readiness rather than relying on `/api/healthz`'s 180s grace masking.
  - `/api/healthz` — liveness probe intercepted by `start_railway.py` wrapper, returns 200 during `_GRACE_SECONDS = 180` boot window, then monitors lifespan heartbeat and default executor starvation canaries.
  - `/api/health` — readiness probe inspecting real per-service health; returns `ready: false` / 503 until `startup_complete=True` (all 18 subservices verified green).
- **Key env vars for backend**: `OPENROUTER_API_KEY`, `SUPABASE_URL`, `SUPABASE_KEY`, `QDRANT_URL=http://qdrant.railway.internal:6333`, `QDRANT_COLLECTION=spiritual_wisdom_contextual`, `REDIS_URL=redis://...:6379`, `NEO4J_URI=bolt://memgraph.railway.internal:7687`, `FORWARDED_ALLOW_IPS=10.0.0.0/8` (mandatory startup security guard), `QUANTIZED_ONLY=true`, `PYTHON_MEMORY_LIMIT_MB=0` (mandatory on Railway: 0 disables RLIMIT_DATA virtual memory limits to prevent thread-allocation and model-loading OOM crashes)
