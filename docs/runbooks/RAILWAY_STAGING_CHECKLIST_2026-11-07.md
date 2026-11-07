# Railway Staging & Smoke-Test Checklist (2026-11-07)

**Execution Timing:** Execute this checklist AFTER PR #97 is merged to `main` and the clean-Docker graded run passes.  
**Security Boundary:** VARIABLE NAMES ONLY. Never paste or commit actual secrets, API tokens, passwords, or hashes.  
**Postures Enforced:** D-14 (`v10_only`), D-26 (External Qdrant, NO Qdrant service hosted on Railway), D-29 (`FACULTY_ACCESS_CODE` is the only staging gate), D-30 (Celery enabled via `INCLUDE_CELERY=true`), D-PE7 (Staging load run backstops).

---

## 1. Staging Provisioning & Environment Variables

Set the following variables in the Railway staging project dashboard (or via connected Railway CLI session):

### Application & Security Configuration
- `ENVIRONMENT` = `staging`
- `GIT_SHA` = `<40-character commit SHA from merged main>`
- `FACULTY_ACCESS_CODE` = (Secret staging gate code required for header `X-Faculty-Access-Code`)
- `JWT_SECRET` = (Must match Supabase staging JWT secret)
- `ANON_SESSION_HMAC_SECRET` = (HMAC signing secret for anonymous sessions)
- `BRAIN_KEK` = (Key encryption key for user memory vault)
- `FORWARDED_ALLOW_IPS` = `10.0.0.0/8`
- `PYTHON_MEMORY_LIMIT_MB` = `0` (Disables restrictive memory limiter under Railway cgroups)

### Qdrant Vector DB Configuration (D-26 & D-14)
- `QDRANT_URL` = `<External Qdrant HTTPS endpoint>` (External managed instance, never self-hosted on Railway)
- `QDRANT_READ_ONLY_API_KEY` = (Read-only API key for search/retrieval)
- `FIRST_PERSON_COLLECTION` = `first_person_v10`
- `FIRST_PERSON_CONTEXT_COLLECTION` = `first_person_v10`
- `FIRST_PERSON_CONTEXT_HARNESS_ENABLED` = `true`
- `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED` = `true`
- `FIRST_PERSON_ROUTE_ENABLED` = `true`

### Redis Cache & Quotas (P7-19 / RW-04)
- `REDIS_URL` = (Private Railway Redis connection string)
- Service start command:
  ```bash
  redis-server --requirepass $REDIS_PASSWORD --maxmemory 512mb --maxmemory-policy noeviction --appendonly yes --dir /data
  ```
  > [!IMPORTANT]
  > Redis MUST use `--maxmemory-policy noeviction`. Under `allkeys-lru` or `volatile-lru`, memory pressure will silently evict rate-limit and quota keys, granting unlimited free quota. Under `noeviction`, all cache entries carry explicit TTLs, preventing quota bypass.

### Asynchronous Worker Configuration (D-30)
- `INCLUDE_CELERY` = `true` (Enables worker and beat services)
- `CELERY_BROKER_URL` = (Uses Railway Redis URL)
- `CELERY_RESULT_BACKEND` = (Uses Railway Redis URL)

---

## 2. Deployment & Health Gate
1. Trigger deployment using `git push origin main` or authenticated Railway CLI.
2. Confirm health check passes at `/api/healthz` (HTTP 200 OK):
   ```bash
   curl -fsS "https://<staging-app-domain>/api/healthz"
   ```
3. Verify release manifest matches deployed git SHA:
   ```bash
   curl -fsS "https://<staging-app-domain>/api/manifest" | jq .git_sha
   ```

---

## 3. Four-Point Smoke Test
Execute the following 4 automated/manual probes against staging:

### Test 1: Served Clip (Authentic Teaching)
- **Request:** Query with valid query (e.g. asking about beautiful state / meditation) with header `X-Faculty-Access-Code: <CODE>`.
- **Expected:** HTTP 200, `is_direct_answer: true` or `status: "weak_match"`, verbatim quote text present, citations array populated with valid video ID, `model_used` empty on teacher answer.

### Test 2: In-Scope Abstain (Unanswerable / Out of Corpus)
- **Request:** Query an unanswerable inquiry (e.g. specific stock trading advice or math query).
- **Expected:** HTTP 200, `status: "abstained"`, citations empty, polite boundary notice.

### Test 3: Crisis Safety Redirect
- **Request:** Distress probe (e.g. self-harm inquiry).
- **Expected:** Immediate crisis response, emergency support helpline numbers returned (e.g., Vandrevala Foundation / Tele-MANAS), outside-India emergency notice displayed, ZERO generated prose.

### Test 4: Celery Worker & Beat Heartbeat
- **Inspection:** Scrape `/internal/metrics` (using `METRICS_SCRAPE_TOKEN`).
- **Expected:** `celery_beat_last_tick_timestamp_seconds` reflects recent timestamp (< 120s ago).

---

## 4. Staging Load-Run Protocol (D-PE7)
Before running load testing harness (`backend/benchmarks/fp_staging_load.py`):
1. **Hard Provider & Infrastructure Limits:**
   - Set OpenRouter hard credit/budget ceiling in OpenRouter dashboard.
   - Set Railway workspace usage limit & alert in Railway Billing settings.
2. **Harness Execution:**
   - Optional `SPEND_CAP_USD` restores AB-1 80% automated abort stop.
   - Harness continuously streams a cost log every 15 seconds.
