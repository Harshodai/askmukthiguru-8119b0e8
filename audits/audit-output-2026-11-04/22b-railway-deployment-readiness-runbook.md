# 22b — Railway deployment-readiness runbook (deferred validation)

Owner: S1. Target: `origin/main@46b808fb`. Conventions: `CONVENTIONS.md`.
Companion: 22 (Qdrant and graph deferred validation, S2). Related: 05, 14, 15.

Railway was not contacted. Every step here is a procedure for the owner or the coding agent to run later. Statements about the repository are [V-STATIC]; statements about Railway state are [DOC-CLAIM] or [LIVE-R].

## 1. What the repository declares

| Item | Evidence | Label |
|---|---|---|
| IaC | `.railway/railway.ts`: one service `askmukthiguru-8119b0e8`, `start: python start_railway.py`, `healthcheck: /api/healthz`, `healthcheckTimeout: 330`, project `resilient-embrace`. `dockerfilePath`, `builder`, `watchPatterns` are **comments**, "must be kept in sync with Railway service settings UI". | [V-STATIC] |
| Ignore file | `.railwayignore` hides frontend files including the pattern `*.ts`, which also matches `.railway/railway.ts` | [V-STATIC]; effect on IaC upload unknown [LIVE-R] |
| Image | `backend/Dockerfile.railway` (144 lines): two-stage, Python 3.12-slim, CPU torch, `uv pip install -r requirements.lock`, models baked at build (`scripts/download_models.py`, `QUANTIZED_ONLY=true`), non-root `appuser`, `COPY memory/`, `COPY config/helplines.yaml` | [V-STATIC] |
| Entrypoint | `backend/start_railway.py` (661 lines): ASGI shim that answers `/api/healthz` immediately, 180 s unconditional grace, then real readiness; heartbeat, executor canary, memory trimmer, stale-exit watchdog; `SERVICE_TYPE=celery` / `celery-beat` switch | [V-STATIC] |
| Deploy script | `scripts/deploy/deploy_railway.sh` (362 lines): sets `CORS_ORIGINS`, `EMBEDDING_*`, `FORWARDED_ALLOW_IPS`, `GUARDRAILS_PROVIDER`, `JWT_SECRET`, `LIGHTRAG_GRAPH_STORAGE`, `LLM_PROVIDER=openrouter`, `MEMGRAPH_URI`, `NEO4J_*`, `PG*`, `PYTHON_MEMORY_LIMIT_MB`, `QDRANT_COLLECTION`, `QDRANT_URL`, `REDIS_URL`, `RERANKER_*`, `SARVAM_CLOUD_MODEL`, `WEB_CONCURRENCY=1`; checks `OPENROUTER_API_KEY SUPABASE_URL SUPABASE_KEY ANON_SESSION_HMAC_SECRET BRAIN_KEK`; optional `--with-worker` | [V-STATIC] |
| Other services | Qdrant, Memgraph and managed Redis exist as manually created Railway services, scaled down; volumes intact | [DOC-CLAIM] `docs/operations/railway-production-status-2026-09-20.md` |
| State | backend "Failed" since 2026-08-23; public URL 404; `api.askmukthiguru.com` does not resolve (checked 2026-10-11) | [DOC-CLAIM] task list §1 cause 4 |

## 2. Readiness gaps (fix before the first deploy)

| ID | Gap | Evidence | Fix |
|---|---|---|---|
| R-1 | Spend cap not set | SYS-004: guard default off; not in Dockerfile or script | Set `OPENROUTER_BUDGET_GUARD_ENABLED=true`, `OPENROUTER_BUDGET_FAIL_CLOSED=true`, daily/monthly caps; better, flip code defaults |
| R-2 | Unauthenticated LLM-spending route | SEC-001 | Fix code or set `FIRST_PERSON_ROUTE_ENABLED=false` on Railway until fixed |
| R-3 | Only the backend is declared in IaC | §1 | Declare Qdrant (pinned `qdrant/qdrant:v1.18.0`), Redis, worker, beat; decide whether Memgraph is needed (doc 08/17) |
| R-4 | Dockerfile path and builder live only in the UI | `railway.ts` comments | Move into IaC or a `railway.json`; record in the runbook |
| R-5 | FP collection and contract files | `FIRST_PERSON_ACTIVE_COLLECTION` default `first_person_v10` (`config.py:209`); v10-only mode needs `FIRST_PERSON_CONTEXT_HARNESS_ENABLED=true` and `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED=true` (CLAUDE.md inv. 25); startup validates the serving contract (`app/main.py:833-841`) | Set explicitly; confirm the collection exists in the Railway Qdrant (doc 22) |
| R-6 | Relevance scorer model | `FIRST_PERSON_RELEVANCE_MODEL` empty by default; local uses `anthropic/claude-haiku-5.5` allowed via `OPENROUTER_EXTRA_ALLOWED_MODELS` (CLAUDE.md inv. 24) | Set both explicitly |
| R-7 | Supabase migrations are not applied by any deploy step | no migration step in `deploy_railway.sh`; faculty-labels migration not applied [DOC-CLAIM task list N5] | Add `supabase db push` (or equivalent) to the release procedure with a dry-run diff |
| R-8 | No staging | SYS-007 | Create a staging environment first; production only after staging passes §5 |
| R-9 | Backups | SYS-012 | Configure off-host backups before real users |
| R-10 | Frontend points at the dead Railway URL | `.env.production:VITE_BACKEND_URL` [DOC-CLAIM task list N6] | Update after the backend URL is stable |

## 3. Required environment variables (names only)

Derived from `Settings` production validators (`app/config.py:2340-2620`), the deploy script, the Railway image and compose. Values never go into the repository.

| Group | Variables | Required? |
|---|---|---|
| Runtime | `ENV`, `IS_PRODUCTION`, `ENVIRONMENT`, `PORT` (Railway), `WEB_CONCURRENCY`, `FORWARDED_ALLOW_IPS`, `PYTHON_MEMORY_LIMIT_MB`, `CORS_ORIGINS` | yes |
| Secrets | `JWT_SECRET`, `ANON_SESSION_HMAC_SECRET`, `BRAIN_KEK`, `FACULTY_ACCESS_CODE` (unless `FACULTY_GATE_DISABLED`), `METRICS_SCRAPE_TOKEN` | yes (validators) |
| LLM | `LLM_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, `OPENROUTER_GENERATION_MODEL`, `OPENROUTER_GENERATION_MODEL_FALLBACK`, `OPENROUTER_CLASSIFY_MODEL`, `OPENROUTER_FAST_MODEL`, `OPENROUTER_EXTRA_ALLOWED_MODELS`, `FIRST_PERSON_RELEVANCE_MODEL` | yes |
| Spend | `OPENROUTER_BUDGET_GUARD_ENABLED`, `OPENROUTER_BUDGET_FAIL_CLOSED`, `OPENROUTER_DAILY_BUDGET_USD`, `OPENROUTER_MONTHLY_BUDGET_USD` | yes (R-1) |
| Stores | `QDRANT_URL`, `QDRANT_API_KEY` (if enabled), `QDRANT_COLLECTION`, `REDIS_URL`, `RATE_LIMIT_STORAGE_URI` (else limiter uses REDIS per `app/core/limiter.py:55-90`), `MEMGRAPH_URI`/`NEO4J_URI`, `NEO4J_USER`, `NEO4J_PASSWORD` | yes (graph only if the general graph stays) |
| Supabase | `SUPABASE_URL`, `SUPABASE_KEY` / service role, `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` | yes |
| First person | `FIRST_PERSON_ACTIVE_COLLECTION`, `FIRST_PERSON_CONTEXT_COLLECTION`, `FIRST_PERSON_CONTEXT_HARNESS_ENABLED`, `FIRST_PERSON_CONTEXT_TERMINAL_ENABLED`, `FIRST_PERSON_CHAT_BRIDGE_ENABLED`, `FIRST_PERSON_LLM_FALLBACK_ENABLED`, `FIRST_PERSON_SERVE_WEAK_MATCH`, `FIRST_PERSON_ROUTE_ENABLED` | yes, explicit |
| Models | `EMBEDDING_BACKEND`, `EMBEDDING_MODEL`, `EMBEDDING_DIMENSION`, `RERANKER_BACKEND`, `RERANKER_MODEL` | set in image |
| Workers | `SERVICE_TYPE` (`celery`, `celery-beat`), Celery queue/concurrency vars parsed in `start_railway.py:106-125` | per service |

Note: `extra="ignore"` (`config.py:52-55`) means a misspelled variable is silently ignored (CQ-010). Check the startup log for the effective values.

## 4. Deployment procedure

1. Freeze a release commit on `main`. Record the SHA.
2. Run the repo gates locally or in CI: `lint-test.yml`, `main-hard-gates.yml`, `production-readiness.yml`, `security-audit.yml`. Each must pass before you deploy.
3. Apply Supabase migrations to **staging** with a dry-run diff first. Record the migration head.
4. Confirm the Qdrant collections and counts on staging with the read-only checks in doc 22.
5. Deploy backend to staging with the variables in §3. Build the Railway Dockerfile; expect a long build (models baked) [INF].
6. Watch logs for: lifespan complete; serving-contract validation report; effective FP collection; budget caps; no `anon_session_hmac_secret is required` error.
7. Deploy `celery-worker` and `celery-beat` (`SERVICE_TYPE`).
8. Run the smoke suite (§5). Stop on any failure.
9. Run the load test (§6).
10. Promote the same image to production; repeat §5 on production.

## 5. Smoke tests (staging, then production)

| # | Check | Pass condition |
|---|---|---|
| S-1 | `GET /api/healthz` | 200 after grace; 503 during a forced Qdrant outage |
| S-2 | `GET /api/ready` | 200; circuit closed |
| S-3 | `POST /api/auth/anon-session` | token returned |
| S-4 | Greeting "namaste" via `/api/chat` | canned greeting, `model_used=None`, < 1 s |
| S-5 | Crisis probe (from the existing crisis probe set; never call real helplines) | helpline response, no clip, < 2 s |
| S-6 | 10 on-topic FP questions from the frozen bank | each ends in a clip or a static abstain; `route_decision` ∈ {`first_person_bridge`, `first_person_abstain`}; served clips pass the integrity gate |
| S-7 | 5 out-of-corpus questions | 5/5 abstain or boundary; 0 clips |
| S-8 | 6th anonymous message in 24 h | 429 `quota_exceeded` |
| S-9 | `POST /api/first-person/query` without a token | 401 (after SEC-001 fix) or 404 (route disabled) |
| S-10 | Admin route without AAL2 | 401/403 |
| S-11 | `/internal/metrics` with token | 200; without token 401 |
| S-12 | Account deletion on a seeded test account | edge function returns success; erasure check finds 0 rows (SEC-004) |
| S-13 | Budget guard | log shows caps; a forced low cap returns the controlled budget error, not a 500 |

## 6. Load test

- Tool: `backend/scripts/ops/gate1_load_test.py` (1,521 lines) with `--mode first-person` [V-STATIC exists].
- Profile: real models, budget guard on with a test cap, concurrency 1 → 5 → 10 → 20, 10 minutes each.
- Record: p50/p95/p99 by route, 503 rate, executor-canary staleness, RSS, provider-reported cost.
- Pass: no 5xx; executor canary never stale; p95 within the provisional SLO (doc 15 §8); 503s only above `max_concurrent_chat`.

## 7. Rollback

| Change type | Rollback |
|---|---|
| Backend image | Railway redeploy of the previous deployment (record its id before each release) |
| FP collection switch | Set `FIRST_PERSON_ACTIVE_COLLECTION` to the previous collection and redeploy; env changes need a redeploy/recreate, not a restart (CLAUDE.md inv. 23 lesson) |
| Flags | Revert the variable; the FP bridge flag is read live per request (`pipeline_registry.py:67-80`) |
| Migration | Manual, reviewed `REVERT` blocks in each migration (`docs/runbooks/MIGRATION_ROLLBACK.md`); never automatic |
| Data | Restore from snapshot (doc 22; `docs/runbooks/restore-snapshot.md`) |

## 8. Monitoring and recovery

- Scrape `/internal/metrics` with `METRICS_SCRAPE_TOKEN`; deploy `alerting-rules.yml` (14 rules) to a hosted Prometheus or Grafana Cloud; route Alertmanager to one on-call channel.
- Add the outcome metrics from doc 15 §7 before inviting users.
- Recovery drills before launch: Qdrant snapshot restore, Supabase restore, Redis loss (quota/rate-limit degrade), LLM provider outage (circuit opens; FP abstains statically).

## 9. Exit criteria for "Railway ready"

1. R-1 … R-10 closed with evidence.
2. Staging passes §5 and §6; results stored under `audits/evidence/` with the commit SHA.
3. Backups configured and one restore drill per store passed.
4. Owner sign-off [HUMAN].

## 10. Statically verified vs needs Railway

| Statement | Status |
|---|---|
| IaC declares one service; Dockerfile path not in IaC | [V-STATIC] |
| Budget guard absent from image and script | [V-STATIC] |
| Health grace 180 s < timeout 330 s | [V-STATIC] |
| Which services and volumes exist now, their sizes, and current env values | [LIVE-R] |
| Whether `.railwayignore` affects IaC | [LIVE-R] |
| Build time, image size (~2.5 GB claimed), cold-start time | [DOC-CLAIM] / [LIVE-R] |
