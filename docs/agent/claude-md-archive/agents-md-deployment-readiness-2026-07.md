<!-- Archived verbatim from root AGENTS.md on 2026-10-19 to cut context cost. Not auto-loaded. Text is dated: verify against code and lessons.md before relying on it. -->

# Archived from AGENTS.md: agents-md-deployment-readiness-2026-07

## Deployment Readiness Checklist (Jul 19, 2026)

### Language Selection
- 14 language codes registered, **6 with real translations**: en, hi, te, kn, ta, mr
- 8 languages fall back to English (bn, gu, ml, ur, or, pa, as, sa)
- `ml` (Malayalam) now visible in dropdown (added to filter)
- Hardcoded English strings still exist — need `t()` coverage audit
- Chat backend translates responses if `preferredLanguage` is set

### Google Login — Single Redirect ✅
- `redirectTo` set to `/auth` (not origin root)
- Duplicate OAuth guard via `sessionStorage.lastOAuthRedirect` (5s cooldown)
- Intended path stored/restored after OAuth

### Forgot Password
- Flow exists: `AuthPage` → `resetPasswordForEmail` → `/reset-password` route → `ResetPasswordPage`
- Error handling improved: `AuthApiError` catch with user-friendly messages (expired link detection)
- E2E test verifies button exists + route mounts + form renders

### Knowledge Graph — Obsidian Style
- Public and Profile Memory use one React Flow map; public outage data is labelled, personal data is never fabricated.

### LightRAG & Knowledge Base Status (Jul 24, 2026) ✅
- **Qdrant `spiritual_wisdom`**: 89,053 points (full corpus: books, 450+ YouTube discourses, meditations, lectures)
- **Neo4j Knowledge Graph**: 8,750+ nodes active over private network (`bolt://gb-neo4j-railway-template.railway.internal:7687`)
- **LightRAG Direct Ingestion**: Active background ingestion worker (`scripts/ingest_lightrag_data.py`, `CONCURRENCY_WORKERS=8`) reading directly from `spiritual_wisdom` with OpenRouter inference (`meta-llama/llama-3.1-8b-instruct`) and BAAI BGE-M3 1024d embeddings to build dual-level graph vectors.

### User Personalization & Second Brain Vault Status (Jul 22, 2026) ✅

**Aug 21 rotation invariants:** Second Brain persistence timestamps use PostgreSQL-compatible timezone-aware ISO-8601 values at the write boundary and normalize both ISO and legacy numeric forms on reads. BRAIN_KEK rotation is a staged transaction: take a read-only backup/snapshot, dry-run and CAS-verify every Mode-A row, apply only after explicit authorization, set the replacement on backend and worker, clear BRAIN_KEK_NEXT in service and shared scopes, explicitly redeploy both processes, and verify an authenticated vault unlock. Key material must never be printed, committed, or left in shell history; padded and unpadded base64url inputs are accepted but operational generation should use padded output.
- **Second Brain Vault (`second_brain_vault`)**: Shared multi-tenant collection in Qdrant indexed with `user_id` keyword filter. Payload NEVER holds plaintext; user notes live encrypted in Postgres (`user_brain_nodes`), vectors in Qdrant (`services/second_brain/vault_index.py`).
- **User Familiarity Classification**: `classify_user_familiarity` dynamically adapts prompt tone across `Seeker` (simple explanations of Sanskrit terms), `Practitioner` (balanced meditation guidance), and `Advanced Meditator` (deep philosophical & neurobiological terms).
- **3-Tiered Memory Retention & Automated TTL Cleanup**:
  1. *Tier 1 (Ephemeral Session)*: Redis 15-minute sliding TTL (`EPHEMERAL_TTL = 900`).
  2. *Tier 2 (Transient Chat Logs)*: 90-day retention TTL for chat logs and transient query telemetry.
  3. *Tier 3 (User Core Memories & Vault)*: Protected while user is active. Accounts inactive $>365\text{ days}$ auto-purged via `scripts/ops/cleanup_inactive_user_data.py`.
- **User Privacy Controls (GDPR / Right to Forget)**: `DELETE /api/memory/reflections` and `POST /api/memory/forget` endpoints allow users to wipe memories or forget individual entries at any time.


### Design Sync — Sacred Minimal
- Chat components: unified `rounded-2xl`, `shadow-sm`, consistent spacing/colors
- Auth pages: gradient backgrounds, `shadow-xl`, `rounded-xl` buttons
- `design-tokens.css` imported as canonical source (dedup started)

### Responsiveness
- Tested at 375px (mobile), 768px (tablet), 1024px (desktop)
- Chat composer: `max-h-[120px]`, compact buttons, `px-2 sm:px-4`
- Sidebar: `hidden md:flex` (correct 768px breakpoint)
- KG: responsive viewBox via ResizeObserver
- Weakest area: tablet (768–1024) — not fully stress-tested

### Mic/STT
- Web Speech API with per-language BCP47 mapping (`hi-IN`, `te-IN`, etc.)
- Firefox: explicitly unsupported (returns `{ unsupported: true }`)
- Native app: uses Capacitor speech plugin
- Language read from `i18n.language`, forwarded to backend in FormData

### Completed (Jul 31, 2026) — Security/RLS/Metrics/Release epic
- AAL2/MFA: backend `require_aal2` + `/api/health/mfa`; E2E extended (`serviceWorkers: 'block'` — SW bypasses `page.route()`).
- RLS: idempotent WITH CHECK migration; `backend/scripts/verify_rls_policies.py` (12 probes, ephemeral Alice/Bob via Admin API); nightly `.github/workflows/nightly-rls.yml` (set repo secrets before enabling); E2E `tests/e2e/rls-cross-user.spec.ts`.
- Leaked passwords: enabled manually (Pro) Auth → Providers → Email → "Prevent the use of leaked passwords"; verified with `backend/scripts/verify_leaked_password_protection.py`.
- Metrics parity: `backend/app/schemas/metrics.py` ↔ `src/lib/metricsSchema.ts`; `GET /api/metrics`; `src/hooks/useMetrics.ts`.
- Healing courses: streak-based (≥2 consecutive, 3-of-5, escalation, 24h repeat) via `backend/services/healing_course_service.py`; `POST /api/healing-course/{assign,progress}`; `HealingPathCard.tsx`.
- Guru voice: `langhanam_voice_enabled=false` default; `GURU_VOICE_MODE=prompt|adapter`; benchmark-gated flip (needs live LLM run).
- `docs/RELEASE_READINESS_2026_07_30.md` (Railway + Lovable decision + rollback).

### Remaining Before Prod Deploy
1. Language coverage: audit `t()` usage vs translation keys, add missing keys to 6 real locales
2. Full responsive stress-test at every breakpoint (especially 768–1024)
3. Google login E2E test using dedicated OAuth test identities or an isolated provider test app with CI-injected secrets (verify single redirect in staging or with tight production safeguards)
4. Forgot password E2E test with real Supabase email (verify email sent + link works)
5. Audio E2E on production (CDN-accessible Lovable asset, not `:8080`)
6. Live-LLM guru-voice benchmark → flip `langhanam_voice_enabled` at ≥4.0/5.0
7. Set nightly-RLS repo secrets and confirm ephemeral-user cleanup before first prod run
8. **[NEW - Aug 10]** Run NDCG integration test against production Qdrant to capture real baseline. The test reads `settings.qdrant_url`/`settings.qdrant_api_key`/`settings.qdrant_collection` from env, so a host run without loading production env will hit Docker hostnames (`qdrant:6333` from `backend/.env`) or localhost defaults (`app/config.py`) — NOT production. Required before running: load production env (`set -a; source <(railway run --service askmukthiguru-8119b0e8 --environment production -- printenv); set +a` — or export explicitly), confirm `QDRANT_URL` points at production Qdrant, `QDRANT_COLLECTION` = `spiritual_wisdom` (prod collection; config default is `spiritual_wisdom_contextual`), and use read-only `QDRANT_API_KEY`. Then: `cd backend && python -m pytest tests/test_qdrant_search_quality.py -v -m integration`
9. **[BLOCKER - Sep 8]** Set `FORWARDED_ALLOW_IPS` env var in Railway before next deploy. `start_railway.py` exits at startup without it (fail-closed). Set to `10.0.0.0/8` or similar RFC1918 range. Railway is currently paused — must be set before `railway up`.
10. **[BLOCKER - Sep 8]** Run full backend test suite in CI/test image. Local Docker stalls at ~41% (dependency-limited sandbox). Requires `pip install -r requirements.lock` + `pytest` in the production test image or CI pipeline.
11. **[Sep 8]** NDCG integration test requires production Qdrant access. Cannot run locally without loading production env via `railway run`. Blocked on Railway unpause.
12. **[Sep 8]** Google login E2E and Forgot-password E2E require real Supabase email delivery. Cannot run in sandbox — needs Supabase project with `mailer_autoconfirm: false` and working email provider.
13. **[Sep 8]** Guru-voice benchmark requires live LLM run with `langhanam_voice_enabled=true`. Blocked on production deployment + benchmark infrastructure.

### Completed (Aug 10, 2026) — Staff+ Engineering Audit Remediation Sprint
12 evidence-backed fixes applied across 3 audit passes; all sprint-touched files syntax-verified except the pre-existing EOL string-literal error in `scripts/monitoring_dashboard.py` recorded below.

**Security (P0):**
- **Deleted `The_Four_Sacred_Secrets.pdf`** (2.7 MB copyright risk from repo root)
- **Deleted `backend/app/sarvam_debug.json`** (33 MB raw API debug data with PII)
- **Deleted `cookies.txt`** (294 KB credential exposure risk)
- **`.dockerignore` hardened**: added named guards + `*.pdf` catch-all to prevent re-introduction

**Measurement (P0-NDCG):**
- **Fixed NDCG=0.0 baseline bug** (`backend/tests/test_qdrant_search_quality.py:24` — `_extract_source_filename()`): `r.get("source_url")` silently returned `""` — fixed to multi-key fallback (`source_url` → `source` → `url`) across both top-level and nested `payload` fields. Also corrected DCG formula from `2^(rank+1)` to standard `log2(rank+2)`.

**Safety (P1-Crisis):**
- **Extended crisis keyword coverage** (`distress_stage.py`): Added Kannada (`ಆತ್ಮಹತ್ಯೆ`), Malayalam (`ആത്മഹത്യ`), and Marathi-specific idioms (`जीव देणे`). 6 scripts now covered (was 4).

**Observability (P1-Telemetry):**
- **Fixed output guardrail status** (`guardrail_stage.py`): `"error"` → `"moderated"` — safety interventions no longer inflate error rate metrics.

**Reliability (P1-Infra):**
- **Qdrant maintenance lock TTL** (`main.py`): 120s → 300s to prevent premature expiry on cold Railway instances.
- **Redis-backed auth/admin rate limiting** (`security_utils.py` + `main.py`): `RedisBackedRateLimiter` class added with ZADD sliding window + exponential backoff tracking. Falls back to `TTLRateLimiter` if Redis unavailable. Wired into `_AUTH_RATE_LIMITER` and `_ADMIN_RATE_LIMITER`.
- **LightRAG `TTLCache` thread safety** (`lightrag_service.py`): Added `_cache_lock = threading.RLock()` protecting all 4 `_query_cache` access sites.
- **LightRAG OpenRouter tenacity retry** (`lightrag_service.py`): 3 attempts, `wait_exponential(min=2, max=30)` before falling back to Sarvam/Ollama. Prevents silent ghost-node writes on 429 storms.
- **Embedding warm-up canary** (`main.py`): Fires ONNX encoder before `startup_complete=True`. Validates dimension contract (logs ERROR if dim != `settings.embedding_dimension`).

**New Scripts:**
- **`scripts/ops/qdrant_backup.py`**: Standalone Qdrant snapshot backup (REST API, S3 upload, local prune). Run as Railway cron `0 2 * * *`.
- **`scripts/eval/run_ragas_eval.py`**: Standalone RAGAS evaluation runner (faithfulness, answer_relevancy, context_precision). CI-gate mode with `--ci --threshold 0.6`.

**Pre-existing issue (not from audit):** `scripts/monitoring_dashboard.py` line 68 has an EOL string literal syntax error — pre-dates this sprint, not introduced by any Aug 10 change.

### Completed (Aug 10, 2026) — K3 Ultra Audit Remediation (10 items)
All 10 verified findings from the K3 Ultra Audit corrected edition addressed. 17/17 tests pass.

**Security (P0):**
- **SEC-4 FIXED** (`auth_service.py:TestAuthStrategy`): `test_key == benchmark_secret` → delegates to `security_utils.is_benchmark_request(request)` which uses `hmac.compare_digest`. Timing attack closed.
- **SEC-1 FIXED** (`tests/test_no_jwt_secret_backdoor.py`): Added `# gitleaks:allow` + 4-line explanatory comment block on `JWT_SECRET` and `BENCHMARK_SECRET` synthetic fixture constants.
- **SEC-2 FIXED** (`tests/e2e/rls-cross-user.spec.ts`, `scripts/ui-explore.mjs`, `scripts/prelaunch.sh`): Hardcoded passwords replaced with `process.env.* ?? 'fallback'` pattern + `# gitleaks:allow`. CI can override via env vars.
- **SEC-2 FIXED** (`tests/e2e/chat-scrolling-and-tts.spec.ts`): 3 raw mock JWTs annotated with `MOCK_ACCESS_TOKEN` named constant + `# gitleaks:allow` + comments explaining signature is literal 'signature' — unverifiable against any JWKS.
- **SEC-3 FIXED** (`docs/archive/RAILWAY_REWIRE.md`): `SUPABASE_ANON_KEY` JWT redacted → `<redacted — retrieve from Lovable Cloud dashboard>`.
- **SEC-5 FIXED** (`.env.example`): `VITE_ADMIN_ENABLED=true` → `VITE_ADMIN_ENABLED=false` with expanded comment explaining Vite bundle behavior (code stays in bundle; flag only hides routes at runtime).
- **SEC-6 DOCUMENTED** (`auth_service.py`): Stale `== benchmark_secret` comment updated to accurately reflect `hmac.compare_digest` + full risk/mitigation table in comment block.

**Performance (P0/P1):**
- **PERF-1 FIXED** (`app/chat_engine.py`): Coalescer moved from per-request `build_coalescer()` call to singleton `_get_coalescer()` lazy-init on `ChatEngine`. Added `close()` for graceful connection pool teardown.
- **PERF-2 DOCUMENTED** (`app/api/chat.py`): `asyncio.to_thread()` wrapping of sync Supabase client is the correct pattern. Added `# PERF-2 TODO: migrate to async Postgres client` to track technical debt.

**Code Quality (P1/P2):**
- **CODE-1 FIXED** (`app/coalescer.py`): Two `except Exception: pass` silent blocks replaced with `except Exception as e: logger.debug(...)`. No more invisible Redis errors.
- **CODE-2 PARTIAL** (`app/api/admin.py`): Moved `datetime/timedelta/UTC` to module-level imports; removed redundant inline `from app.telemetry_db import get_kpis, get_node_latencies` (already at module top). Added comment explaining remaining intentional lazy-loads (circular import avoidance for celery tasks, cost tracker, prompt store).
- **`time.sleep` DOCUMENTED** (`services/embedding_service.py`): Added clarifying comment at all 3 instances explaining they run in `asyncio.to_thread()` worker threads — event loop is NOT blocked.

**New Invariants (added to lessons.md):**
- L-K3-1: Secret comparisons → `hmac.compare_digest`, never `==`
- L-K3-2: Connection-pool objects are singletons, never per-request
- L-K3-3: `time.sleep()` in sync methods called via `to_thread()` is NOT a bug
- L-K3-4: `except Exception: pass` is forbidden — always log at DEBUG+
- L-K3-5: Test fixture secrets need `# gitleaks:allow` + explanatory comment



### Local Dev Caveats (Jul 31, 2026)
- `backend/.env` uses docker hostnames (`qdrant:6333`, `neo4j:7687`, `redis:6379`) — running uvicorn/pytest on the HOST requires overrides (`QDRANT_URL=http://localhost:6333`, `NEO4J_URI=bolt://localhost:7687`, `REDIS_URL=redis://:${REDIS_PASSWORD}@localhost:6379/0`, `SUPABASE_URL=http://127.0.0.1:54321`), and Vite needs `VITE_BACKEND_URL=http://localhost:8001` when the backend is not on 8000.
- NEVER `kill -9` a process owned by `com.docker` to free a port (e.g. docker-proxy on 8000) — Docker Desktop restarts the whole engine VM (~5 min, all containers down). Use `docker stop <container>` or run on another port.
- `backend/dotenv/` (untracked test shim) shadows python-dotenv and silently kills `.env` loading — delete it if present.
- **System `python3` cannot run backend code** — the backend requires Python 3.12-only stdlib (e.g. `datetime.UTC`); system/default `python3` is often 3.9 and fails with a cryptic `ImportError: cannot import name 'UTC' from 'datetime'` deep inside an unrelated import chain. Root `.python-version` pins `3.12` for pyenv/asdf-aware tooling, but that's not enough if no version manager is active on PATH — always invoke `backend/.venv/bin/python` (or `backend/.venv/bin/pytest`) explicitly, or use `make test-backend` (already resolves the venv correctly; see `Makefile`'s `PYTHON`/`PYTEST` vars). `evals/run_safety_scenarios.py` now fails fast with this same guidance instead of the raw `ImportError` if run under the wrong interpreter. CI (`.github/workflows/lint-test.yml`) already pins `actions/setup-python@v5` to `3.12` — this trap is local-dev-only, not a CI risk.
- **Container bind-mount topology (2026-10-03)** — `docker exec mukthiguru-backend` sees fresh bind-mounted code with NO restart, but ONLY the bind set: `app`, `evaluation`, `services`, `rag`, `ingest`, `tests`, … plus **repo-root `scripts/` → `/app/scripts`**. **`backend/scripts/` is NOT mounted** — a tool written there is invisible in the container (`No module named ...`); container-runnable ops scripts must live in repo-root `scripts/ops/` and run as `docker exec mukthiguru-backend python -m scripts.ops.<tool>`. Conversely, tests importing `backend/scripts/*` can only run host-side (`backend/.venv/bin/pytest`). Verify mounts with `docker inspect --format '{{json .Mounts}}' mukthiguru-backend`. See lessons.md `L-OPS-MOUNT-1`.

### Completed (Aug 1, 2026) — Ruthless audit remediation
- **Git history scrub**: `The_Four_Sacred_Secrets.pdf` fully removed from ALL commits via `git-filter-repo`. Confirmed 0 commits remain. `CONTENT-RIGHTS.md` updated with scrub date.
- **nginx security hardening**: `/ui` Gradio location now has `allow/deny` IP restriction (RFC1918 + loopback only — blocks public). CSP cleaned: removed unidentified `gs-extension-embeds-final.vercel.app` from `style-src`; removed all `localhost`/`127.0.0.1` entries from `connect-src`. HSTS/TLS mismatch documented with comment.
- **Docker Compose bug fixed**: `LMCACHE_REMOTE_URL=${REDIS_URL}` → explicit `redis://:${REDIS_PASSWORD}@redis:6379/0` (Docker Compose cannot self-reference env block vars).
- **Bandit CI hardened**: removed `|| true`; added `backend/.bandit` config file with documented justified skips. Scanner now blocks CI.
- **DEVELOPER_GUIDE.md rewritten**: removed `$0/local-only/Ollama` v1 constraints. Architecture diagram, §1, §4b, §6 pipeline updated to current reality (cloud LLMs, Railway, lightweight guardrails, 12-layer pipeline). Old SPEC_DEV.md explicitly marked as historical.
- **README attribution fixed**: removed false "Google DeepMind" claim; replaced with accurate solo-dev + AI assistant attribution. Removed duplicate env section.
- **ROADMAP.md**: removed duplicate "In Progress" section.
- **PRE_LAUNCH_CHECKLIST_PLAN.md**: marked 4 items as Done with evidence (RLS, .env nginx deny, HSTS, rate limiting).
- **docs/GUARDRAILS_DECISION.md** [NEW]: ADR documenting `lightweight` mode as explicit architectural decision with risk table and path-to-ML-rails criteria.
- **docs/INCIDENT_RESPONSE.md** [NEW]: Runbook covering 5 scenarios (credential exposure, cross-tenant data leak, LLM hallucination, DoS/OOM, data loss).
- **SECURITY_CHECKLIST.md**: item #25 (IR runbook) marked DONE.
- **lessons.md**: 5 new Aug 1 lessons prepended (Docker Compose self-ref, filter-repo N prompt, Bandit || true, CSP localhost pollution, third-party CSP domains).
