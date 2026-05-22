# Mukthi Guru Production Readiness Plan

## Overview
Comprehensive production-readiness audit and fix for Mukthi Guru project covering 100+ issues across security, architecture, wiring, infrastructure, and repo organization.

## Phase-Wise Unit Plan (20 Units)

### Unit 1 — Critical Security Fixes (Backend)
**Files:** `backend/app/telemetry_db.py`, `backend/services/user_profile_service.py`, `backend/scripts/seed_admin.py`, `backend/services/whisper_local_service.py`, `backend/services/sarvam_stt_service.py`, `backend/services/cookie_helper.py`
**Description:** Fix SQL injection in Supabase queries (parameterize all queries), fix subprocess command injection (strict YouTube URL validation regex + use yt-dlp Python API where possible), add CSRF token validation on POST endpoints, sanitize correlation-ID before JSON logging.

### Unit 2 — Critical Security Fixes (Frontend)
**Files:** `src/integrations/supabase/client.ts`, `src/admin/lib/adminAuth.ts`, `src/admin/lib/api.ts`, `src/hooks/useRequireAuth.ts`
**Description:** Remove hardcoded Supabase publishable key fallback, fix deprecated admin auth pattern, prevent mock-data fallback in production, add proper token refresh logic, add CSP configuration.

### Unit 3 — RAG Pipeline Truth: Fix or Document
**Files:** `backend/rag/graph.py`, `backend/rag/nodes.py`, `backend/rag/states.py`, `backend/rag/prompts.py`, `CLAUDE.md`, `ARCHITECTURE.md`
**Description:** Audit actual RAG graph nodes vs documented 12 layers. Either implement missing layers (context engineer, reflect_on_answer, check_contradiction with real logic) OR update all documentation to match the actual ~8-9 node pipeline. Add request_id propagation through GraphState.

### Unit 4 — Guardrails & Safety Hardening
**Files:** `backend/guardrails/rails.py`, `backend/app/main.py` (cache/guardrail interaction), `backend/guardrails/config/`
**Description:** Fix guardrails bypass on cache hits (run output rail before returning cached responses), add guardrails config files for NeMo, fix duplicate regex patterns, add audit logging for blocked requests.

### Unit 5 — Connection Pooling & Service Stability
**Files:** `backend/services/sarvam_service.py`, `backend/services/ollama_service.py`, `backend/services/krutrim_service.py`, `backend/app/dependencies.py`
**Description:** Implement singleton httpx.AsyncClient with configured pool limits for all external API services, add connection reuse, set explicit timeouts from config, fix DI container race condition (replace unsafe double-checked locking with `functools.lru_cache` pattern).

### Unit 6 — Rate Limiting, Body Limits & Streaming Bounds
**Files:** `backend/app/main.py` (endpoints), `backend/app/config.py`
**Description:** Implement per-user rate limiting (use user.id as key), add max request body size limit on FastAPI, add max streaming duration backpressure, fix RequestCoalescer memory leak (background cleanup timer).

### Unit 7 — Multi-Language Full Wiring (Frontend + Backend)
**Files:** `src/components/chat/LanguageSelector.tsx`, `src/lib/aiService.ts`, `src/hooks/useSpeechRecognition.ts`, `backend/app/main.py` (chat endpoint), `backend/services/language_router.py`, `backend/rag/nodes.py`
**Description:** Add backend `/api/languages` endpoint returning supported languages, verify all 23 frontend languages have backend support, fix BCP-47 tag validation in speech recognition, add language parameter propagation through RAG pipeline, add fallback for unsupported browser locales.

### Unit 8 — TypeScript Strictness & Frontend Quality
**Files:** `tsconfig.app.json`, `tsconfig.json`, `vite.config.ts`, `eslint.config.js`, `package.json`, `src/lib/responseCache.ts`
**Description:** Enable `strict: true`, `noImplicitAny: true`, fix all resulting type errors, optimize Vite build (minification, source maps, bundle analysis), fix response cache size bounding, strip console.log in production.

### Unit 9 — Admin Console Integration & Error Handling
**Files:** `src/admin/lib/api.ts`, `src/admin/lib/mockData.ts`, `src/admin/pages/*.tsx`, `src/admin/components/*.tsx`
**Description:** Remove silent mock-data fallback in production, add proper error boundaries for admin routes, fix auth verification to check response types, add loading states and error UIs, ensure all admin API calls handle 401/403 properly.

### Unit 10 — Repository Cleanup: Remove Junk from Git
**Files:** `.gitignore`, `backend/.env`, `/.env.local`, `*.log`, `transcripts/`, `backend/scratch_test*.py`, `mukthi_guru_colab_optimized.py`, `extract_pdf.py`, `parse_dead_code.py`, `test_*.py` (root), `update_task.py`, `chat-ui/`, `ingest-ui/`, `.venv/`, `backend/.venv/`, `.venv_host/`
**Description:** Add comprehensive `.gitignore` rules, remove all committed `.env`/`.env.local` files from git history, delete/move all scratch/test files, remove/move large binaries (PDFs, .txt extracts), delete all tracked log files, move colab script to `scripts/colab/`.

### Unit 11 — Docker & Containerization Production Hardening
**Files:** `backend/Dockerfile`, `frontend.Dockerfile`, `backend/docker-compose.yml`, `docker-compose.prod.yml`, `nginx.conf`, `.dockerignore`
**Description:** Add multi-stage Docker builds, run as non-root user, add security headers in Nginx, add resource limits, fix production compose (real registry URIs, SSL, persistent volumes), add `.dockerignore` to exclude tests/scratch.

### Unit 12 — CI/CD Pipeline Setup
**Files:** `.github/workflows/` (new files), `.pre-commit-config.yaml`, `Makefile`
**Description:** Create `lint-test.yml` (frontend lint + test, backend lint + pytest), `build-deploy.yml` (build Docker images, push to registry), `dependency-check.yml` (Dependabot-style scanning), `security-audit.yml` (expand existing). Integrate pre-commit hooks into CI gate.

### Unit 13 — Monitoring, Observability & Alerting
**Files:** `backend/app/metrics.py`, `backend/app/main.py` (middleware), `backend/app/trace_dashboard.py`, `docker-compose.yml` (Jaeger/Prometheus)
**Description:** Add service-level Prometheus metrics (P99 latency per service, error rates), add request ID propagation to all LLM/retrieval calls, configure Jaeger sampling rate for production, add alerting rules, document observability stack.

### Unit 14 — Database Backup & Recovery
**Files:** `scripts/backup/snapshot_manager.py`, `docker-compose.yml` (volumes), `docs/` (new runbooks)
**Description:** Implement automated Qdrant/Neo4j/Redis backup schedule, add backup verification, document RTO/RPO, add disaster recovery runbook, configure Redis persistence (AOF/RDB).

### Unit 15 — Tests & Coverage Expansion
**Files:** `backend/tests/`, `src/test/`, `tests/integration/` (new), `tests/e2e/` (new)
**Description:** Add RAG node integration tests (CRAG loop, verification, meditation flow), add SSE streaming tests, add error path tests (network failures, timeouts), add frontend language switching tests, set coverage thresholds in CI, add load test script (`scripts/benchmarks/load_test.py`).

### Unit 16 — Ingestion Pipeline Hardening
**Files:** `backend/ingest/pipeline.py`, `backend/ingest/youtube_loader.py`, `backend/ingest/auditor.py`, `backend/ingest/corrector.py`, `scripts/ingestion/`
**Description:** Add global duplicate detection across videos (semantic similarity), fix idempotency guarantees, document error recovery, consolidate scattered ingestion scripts, add timeout on background tasks, fix Whisper language detection (use proper library).

### Unit 17 — Documentation Restructure & API Docs
**Files:** `docs/` (new directory), `README.md`, `DEPLOY.md`, `SPEC_DEV.md`, `ARCHITECTURE.md`, `DEVELOPER_GUIDE.md`, `backend/app/main.py` (OpenAPI tags)
**Description:** Create `docs/index.md` reading guide, move all docs to `docs/`, generate FastAPI OpenAPI/Swagger documentation, add API reference docs, create `docs/adr/` for architecture decisions, create `docs/runbooks/` for ops.

### Unit 18 — Repository Reorganization to SDLC Standards
**Files:** Root directory, `scripts/` (reorganized), `tests/` (reorganized), `backend/`, `src/`, `supabase/`, `.github/`
**Description:** Reorganize repo: move shell scripts to `scripts/bin/`, move deploy files to `scripts/deploy/`, create `tests/integration/` and `tests/e2e/`, ensure consistent naming, add `docs/CONTRIBUTING.md` with branching strategy.

### Unit 19 — Semantic Cache & Qdrant Maintenance
**Files:** `backend/services/cache_service.py`, `backend/services/semantic_cache.py`, `backend/services/qdrant_service.py`
**Description:** Fix cache TTL mismatch (Qdrant vectors accumulate when Redis TTL expires), implement periodic Qdrant cleanup job, add cache invalidation endpoint for admins, add bounded cache size.

### Unit 20 — Security Audit & Hardening Sweep
**Files:** `scripts/security_audit.py`, `.github/workflows/security-audit.yml`, `backend/app/main.py` (CORS, headers), `backend/app/config.py`
**Description:** Expand security audit to check for secrets in code, add SAST scanning (bandit, semgrep), add dependency vulnerability scanning (safety, pip-audit), verify CORS is restrictive, add security headers middleware (HSTS, X-Frame-Options, etc.), add input sanitization helpers.

## E2E Test Recipes

### For Backend Units (1, 3, 4, 5, 6, 13, 16, 19, 20):
```bash
cd backend
# Start infrastructure
docker compose up -d qdrant redis neo4j jaeger
# Run backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
# Verify
curl -s http://localhost:8000/api/health | jq .
curl -s http://localhost:8000/docs  # OpenAPI should load
# Run tests
pytest backend/tests/ -v
```

### For Frontend Units (2, 7, 8, 9):
```bash
# Start dev server
npm run dev  # http://localhost:8080
# Run tests
npm test
# Verify language switching, admin console, chat streaming
```

### For Integration/Full-Stack Units (7, 11, 12):
```bash
cd backend
docker compose up -d --build
# Wait for health checks
curl -s http://localhost:8000/api/health
# Test chat endpoint with language param
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[],"user_message":"hello","language":"hi"}'
```

### For Infrastructure/Repo Units (10, 11, 12, 14, 17, 18):
```bash
# Verify no junk in git
git ls-files | grep -E '\.env$|\.log$|\.venv/' | wc -l  # should be 0
# Verify Docker builds
docker build -f backend/Dockerfile -t mukthi-backend:test backend/
docker build -f frontend.Dockerfile -t mukthi-frontend:test .
# Verify CI workflows pass (act if available)
```