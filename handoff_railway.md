# Railway Deployment Handoff — askmukthiguru

**Date:** 2026-07-12  
**Session End:** ~22:30 UTC  
**Status:** Neo4j restore blocked; all other services deployed

---

## 1. Goal

Deploy the full askmukthiguru stack to **Railway Pro** ($20/mo) with:
- Backend (FastAPI) + Celery worker
- Neo4j (graph DB) — with local data restored
- Qdrant (vector DB) — with local data restored
- PostgreSQL (replacing Supabase) — with schema + data
- Redis (cache + Celery broker)
- Frontend on Lovable Pro ($5/mo) pointing to Railway backend

**Target cost:** ~$26/mo  
**Target users:** 50–1,000 initially, low retention

---

## 2. Current State

### ✅ Deployed & Healthy
| Service | Railway Name | Public URL | Status |
|---------|--------------|------------|--------|
| Backend (FastAPI) | `askmukthiguru-8119b0e8` | `https://askmukthiguru-8119b0e8-production.up.railway.app` | ✅ Healthy (`/api/health` 200) |
| Qdrant | `qdrant` | `https://qdrant-production-14ee.up.railway.app` | ✅ 89,053 vectors loaded |
| PostgreSQL | `Postgres` | Internal only | ✅ Running |
| Redis | `Redis` | Internal only | ✅ Running |
| Celery Worker | `celery-worker` | Created, needs config | ⚠️ Created, not configured |

### ⚠️ In Progress / Blocked
| Service | Issue |
|---------|-------|
| **Neo4j** | Browser UI works (`/browser/`), but **cannot upload dump via CLI** (volume read-only in ephemeral containers). Bolt (7687) not publicly exposed. |
| **Data Migration** | Neo4j dump (36 MB) ready locally; Postgres dump (11 MB), Redis RDB (43 KB), Qdrant snapshot (861 MB) ready. Only Qdrant restored. |

### 🗑️ Cleaned Up
- Deleted 4 duplicate Neo4j services, 2 Postgres, 2 Qdrant, 2 Redis
- Orphaned volumes marked for auto-deletion (Jul 14)
- Active volumes now ~2 GB total (was 596+ GB from deleted services)

---

## 3. Files Actively Edited

| File | Purpose |
|------|---------|
| `deploy_all.sh` | Master deployment script (iteratively fixed Railway CLI syntax) |
| `migrate_data.sh` | Data migration helpers |
| `backend/Dockerfile` | Backend image (used by backend + celery) |
| `railway.json` | Not used (Railway uses `Dockerfile` + CLI) |
| `.env` / `backend/.env` | Local env (not synced to Railway) |

### Key Railway CLI Patterns Learned
```bash
# Add database
railway add --database postgres
railway add --database redis

# Add service from template
railway deploy --template neo4j

# Create empty service
railway add --service celery-worker

# Deploy to specific service
railway up --service celery-worker --dockerfile backend/Dockerfile --detach

# Get service variables
railway variables --service <name>

# Create public domain
railway domain --service <name> --port <port>
```

---

## 4. Tried & Failed

### Neo4j Data Restore
| Attempt | Result |
|---------|--------|
| `railway run --service neo4j -- neo4j-admin database load ...` | Volume read-only in ephemeral container |
| `railway files upload ./neo4j.dump /data/neo4j.dump` | `files` subcommand doesn't exist |
| `railway run --service neo4j -- sh -c "mkdir -p /data/dumps && cp ..."` | `/data` read-only in run container |
| Public Bolt domain (`railway domain --port 7687`) | Created HTTPS domain on 7687, but **TLS proxy doesn't upgrade to Bolt WebSocket** |
| Browser UI at `/browser/` | **Works for queries**, but `:system LOAD DATABASE` requires dump file on server filesystem |

### Other
| Attempt | Result |
|---------|--------|
| `railway service create celery-worker --dockerfile backend/Dockerfile --command "celery ..."` | Syntax invalid; must create empty service then `railway up --service` |
| `railway up --service celery-worker --dockerfile backend/Dockerfile --command "..."` | `--command` not supported in `railway up` |

---

## 5. Next Steps

### Immediate (Unblock Neo4j)
**Option A — Browser UI (only working path):**
1. Open `https://gb-neo4j-railway-template-production-2559.up.railway.app/browser/`
2. Login: `neo4j` / **see Railway vault for password**
3. Click ☁️ upload icon → select local `neo4j.dump` (36 MB)
4. Run:
   ```cypher
   :system
   LOAD DATABASE neo4j FROM 'neo4j.dump' OVERWRITE
   ```

**Option B — If UI upload fails:**
- Provision a temporary VM (Hetzner CX22 ~€4/mo), mount Railway Neo4j volume via SSH tunnel, run `neo4j-admin database load` there.

### Parallel Tasks (Run While Neo4j Restores)
```bash
# 1. PostgreSQL restore
railway variables get PGHOST PGPASSWORD PGUSER PGDATABASE PGPORT --service Postgres
psql "postgresql://user:pass@host:port/db" < supabase_dump.sql

# 2. Redis restore
railway variables get REDIS_PASSWORD --service Redis
redis-cli -h redis.railway.internal -p 6379 -a PASS --rdb ./redis_dump.rdb

# 3. Configure Celery Worker (Railway Dashboard)
# Service: celery-worker → Settings
# Dockerfile: backend/Dockerfile
# Start Command: celery -A celery_config worker --loglevel=info --queues=transcription,embedding,indexing,ingestion,okf --concurrency=1
# Deploy

# 4. Lovable frontend
# https://askmukthiguru.lovable.app → Settings → Env Vars
# VITE_BACKEND_URL = https://askmukthiguru-8119b0e8-production.up.railway.app  (NOT VITE_API_URL — code never reads that var)
# Deploy
```

### Verification
```bash
curl https://askmukthiguru-8119b0e8-production.up.railway.app/api/health
# Test chat from Lovable UI
```

---

## 6. Cost Reality Check

| Component | Monthly |
|-----------|---------|
| Railway Pro (base) | $20 |
| Lovable Pro | $5 |
| Domain | ~$1 |
| **Total** | **~$26/mo** |

**Usage so far (partial day):** ~$0.04 — well within $20 credit.

---

## 7. Key Credentials (Store Securely)

| Service | Username | Password |
|---------|----------|----------|
| Neo4j (new) | neo4j | **Retrieve from Railway vault / secret manager** |
| Neo4j (old, deleted) | neo4j | **Rotated — no longer valid** |
| Qdrant | — | (no auth) |
| Postgres | (from `railway variables`) | (from `railway variables`) |
| Redis | — | (from `railway variables`) |

---

## 8. Commands for Next Session

```bash
cd /Users/harshodaikolluru/Public/askmukthiguru-8119b0e8

# Check Neo4j restore status
curl https://gb-neo4j-railway-template-production-2559.up.railway.app/browser/

# Restore Postgres
railway variables get PGHOST PGPASSWORD PGUSER PGDATABASE PGPORT --service Postgres
psql "postgresql://..." < supabase_dump.sql

# Restore Redis
railway variables get REDIS_PASSWORD --service Redis
redis-cli -h redis.railway.internal -p 6379 -a $PASS --rdb ./redis_dump.rdb

# Deploy Celery worker config
# (Do in Railway Dashboard)

# Update Lovable
# VITE_BACKEND_URL = https://askmukthiguru-8119b0e8-production.up.railway.app  (NOT VITE_API_URL — code never reads that var)
```

---

**Status:** 80% deployed. Neo4j is the only blocker. Browser UI is the only proven restore path.