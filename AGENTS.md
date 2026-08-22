# Agentic Lessons & Environment Context

> **Active operating status — reviewed 2026-08-21.** This file contains binding repository invariants alongside dated lessons and handoffs. For a conflict, current source configuration, scoped instructions, and approved runbooks prevail; preserve historical notes as provenance rather than treating their dated measurements as live state.

### Fresh audit invariants — Aug 21, 2026
- The standard graph can terminate at `handle_fallback` after CRAG rewrite exhaustion, bypassing `generate_answer`, `format_final_answer`, and their quality-gated fallback logic. For bounded product cases, inspect `route_after_grading` and terminal nodes; `final_answer` plus reducer-preserved citations and `verification=null` is the diagnostic signature.
- The only terminal comparative exception currently permitted is the narrow meditation-versus-contemplation request. It returns a clearly labelled general distinction with `verification.method=limited_comparison_fallback`, zero citations, and `grounding_state=abstained`; it must not be presented as a corpus teaching.
- Commit `fa41447` is the current deployed head. Backend deployment `a1a1d1c3-77db-456e-b5d7-274c310d5c43` and worker deployment `b7674f10-9e5b-4f20-b4df-ab4130ab3dae` reached `SUCCESS`; worker image commit is `fa41447dcd7426dc23ad9e8277928d46cdd38e06`.
- Final comparative production proof on `fa41447`: `367` response characters, `11.40s` pipeline latency, `14.39s` wall clock, `limited_comparison_fallback`, zero citations, no quarantined source. This closes the bare refusal defect but does not close the latency target.
- Production smoke requests must obtain a signed token from `POST /api/auth/anon-session` and send the token itself in the POST `session_id` field or the route-specific session header. The derived `anon:<id>` identity is server output, never a client credential.
- Pure greeting short-circuits may use deterministic localized phrases for supported Indic locales, but this optimization is limited to `_GREETING_RE` matches. Substantive responses always use the normal safety, retrieval, generation, and translation pipeline.
- Browser-facing SSE metadata is a public projection. Provenance fields must pass through an explicit allowlist; never stream `memory_context`, `attachment_context`, prompts, safety state, raw graph state, or arbitrary future state fields.
- The fresh production baseline remains a known risk: simple English 14.67s pipeline latency, comparative English 31.39s with honest zero-source abstention, and Hindi 19.90s. Do not claim that long-tail latency or refusal quality is solved until a held-out benchmark improves these classes.
- Local validation in the sandbox is dependency-limited: do not install packages. `py_compile`, the regex safety gate, `git diff --check`, and the corpus guard are valid local gates; `pytest` and dependency-complete tests must run in CI or the production/test image.

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
- Public `/knowledge-graph` page: force-directed graph with glow, drag, hover, zoom
- Auth gate removed — loads for all visitors
- Falls back to demo data if backend cold (never shows blank)
- Profile `MemoryManager` graph synced with same visual style

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
- `backend/.env` uses docker hostnames (`qdrant:6333`, `neo4j:7687`, `redis:6379`) — running uvicorn/pytest on the HOST requires overrides (`QDRANT_URL=http://localhost:6333`, `NEO4J_URI=bolt://localhost:7687`, `REDIS_URL=redis://:mukthiguru_redis_pass@localhost:6379/0`, `SUPABASE_URL=http://127.0.0.1:54321`), and Vite needs `VITE_BACKEND_URL=http://localhost:8001` when the backend is not on 8000.
- NEVER `kill -9` a process owned by `com.docker` to free a port (e.g. docker-proxy on 8000) — Docker Desktop restarts the whole engine VM (~5 min, all containers down). Use `docker stop <container>` or run on another port.
- `backend/dotenv/` (untracked test shim) shadows python-dotenv and silently kills `.env` loading — delete it if present.

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

### Security Invariants (as of Aug 1, 2026)
- **nginx `/ui`**: IP-restricted. Only RFC1918 + 127.0.0.1 allowed. Never remove the `deny all` without adding explicit IP allowlist.
- **CSP domains**: Every third-party domain in CSP must have a comment naming what it is and who owns it. Unattributed domains get removed.
- **Bandit**: Must NOT run with `|| true`. Add known FPs to `backend/.bandit` with justification comments.
- **Docker Compose env self-reference**: Never `${VAR}` in an `environment:` block if `VAR` is also defined in the same block. Use literal values or host env.
- **`The_Four_Sacred_Secrets.pdf`**: Removed from git history 2026-08-01. Do not re-add. Embeddings derived from this book may still be in Qdrant — rights basis unconfirmed. See `CONTENT-RIGHTS.md`.
- **git-filter-repo**: Answer `N` to "treat as continuation" prompt for a fresh rewrite. Re-add `origin` remote manually after run.
- **HF model pins**: Every `from_pretrained`/`snapshot_download`/`SentenceTransformer`/`CrossEncoder`/`BGEM3FlagModel` load MUST pass a pinned commit SHA (resolved from the HF API; comment "resolved 2026-08-01; do not bump to a repo head"). Registry: `backend/scripts/download_models.py::_MODEL_REVISIONS`. `BGEM3FlagModel` has no `revision=` kwarg — load from a pinned local `snapshot_download` dir. Any new model added to the repo gets a SHA in `_MODEL_REVISIONS` first. Never add a mutable repo-head load.
- **ONNX model pins (encoder + reranker)**: ONNX snapshot loads (`embedding_service.py::_load_onnx_encoder`, `services/onnx_reranker.py::_load`) MUST pass `snapshot_download(revision=<pinned SHA>)`. `HF_REVISION` (the env override for the ONNX encoder) MUST be a full 40-hex commit SHA (`^[0-9a-f]{40}$`) — reject missing or non-40-hex/mutable values before loading (fail-closed, never a repo head); `_load_onnx_encoder` validates and raises. Code constants `_ONNX_ENCODER_REVISION`/`_ONNX_RERANKER_REVISION` are themselves full SHAs. ONNX artifacts are pre-baked into offline images by `backend/scripts/download_models.py` (temsa reranker pinned in `_MODEL_REVISIONS` at `59d3305e...`; snapshot lands under `HF_HOME/hub/models--<org>--<model>` so the runtime cache lookup hits without network).
 - **Credentialed HTTP clients**: Any urllib/httpx client sending a key must validate scheme (`https`) + expected hostname, and refuse to follow 3xx redirects (`HTTPRedirectHandler` override) — see `backend/scripts/verify_sarvam.py`.
 - **Sarvam gateway keyed traffic** (Aug 11, 2026): `sarvam_http.py::_validate_base_url` sends `api-subscription-key` ONLY to https + `_SARVAM_ALLOWED_HOSTS = {api.sarvam.ai}`; an unallowlisted host (self-hosted E2E 30b endpoint) is accepted only when NO key is set; client uses `follow_redirects=False`. Key rotation takes an excluded-index set and returns None only when ALL keys are exhausted.
 - **Client-supplied assistant config vs shared caches** (Aug 11, 2026): `PipelineContext.assistant_config_present` bypasses shared cache read/write; coalesce key carries a bounded SHA-256 fingerprint (`_assistant_config_fingerprint`, M3 auth gate: system_prompt only for authenticated users); raw prompt text NEVER enters keys.
 - **`FORWARDED_ALLOW_IPS` gate**: `start_railway.py` requires an explicit non-wildcard allowlist (`app.config.settings.forwarded_allow_ips`) and exits at startup when missing or `"*"`. Docker compose runs plain uvicorn (`backend/Dockerfile` CMD) — unaffected. Railway is currently **paused**; set `FORWARDED_ALLOW_IPS` (e.g. `10.0.0.0/8`) before the next Railway deploy.

This file serves as a knowledge base for AI agents interacting with this workspace.


## Plan & Review
### Before starting work
- **CRITICAL: First read `lessons.md`** — search for keywords matching the task scope. Existing lessons contain fixes for repeated regressions (Serene Mind double-wrap, telemetry blocking, Lovable key hard-dependency). Reading first prevents re-debugging known issues.
- Always in plan mode to make a plan.
- After getting the plan, write the plan to `.claude/tasks/TASK_NAME.md`.
- The plan should be a detailed implementation plan with the reasoning behind it, and tasks broken down.
- If the task requires external knowledge or certain packages, research to get the latest knowledge (using appropriate tools).
- Don't over-plan: always think MVP.
- Once you write the plan, ask the user to review it. Do NOT continue until the user approves the plan.
### While implementing
- Update the plan file as you work.
- After completing tasks in the plan, update and append detailed descriptions of the changes you made, so following tasks can be easily handed over to other engineers.

## Docker Execution on Host
- **Docker Path**: The Docker binary is not in the default `/usr/local/bin` or `/opt/homebrew/bin`. It is located at `/Users/harshodaikolluru/.docker/bin/docker`.
- **Command Prefix & Makefile Usage**: Whenever executing `docker` or `docker compose` commands, agents MUST explicitly set the PATH or use the absolute path. Alternatively, and preferably, use the workspace `Makefile` commands which automatically configure the correct PATH.
  - **Preferred (Makefile)**: `make docker-rebuild-web` (to rebuild and restart frontend and backend services without data loss or volume purges).
  - **Other Makefile commands**: `make docker-up` (start full stack), `make docker-down` (stop full stack), `make logs` (view logs).
  - **Raw Command Example**: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH" && docker compose up -d --build backend frontend`
- Failure to do this will result in "unexpected user interaction type: not permission" errors from the agent runner, or `command not found: docker` errors in standard shells.
- **Keychain Credentials Error (-25293) & .docker_clean**: If Docker image pulls/builds fail on macOS with keychain credential errors (e.g., `-25293`), we bypass this by pointing `DOCKER_CONFIG` to a clean folder `.docker_clean/` with a custom `config.json` containing `"credsStore": ""`.
  - **CLI Plugins & Contexts Symlinks**: When overriding `DOCKER_CONFIG`, Docker hides the host's plugins and context directories. To prevent errors like `unknown shorthand flag: 'd' in -d`, you MUST symlink the host's `cli-plugins` and `contexts` into the clean directory:
    ```bash
    ln -s /Users/harshodaikolluru/.docker/cli-plugins .docker_clean/cli-plugins
    ln -s /Users/harshodaikolluru/.docker/contexts .docker_clean/contexts
    ```



## Supabase
- The application stack relies on Supabase for auth and persistence.
- **Local Supabase**: Can be run via `npx supabase start`, but requires the Docker path to be properly mapped if executed programmatically.
- **Google OAuth (Local)**: To test Google Sign-in locally, set `VITE_USE_NATIVE_OAUTH=true` in `.env.local` and ensure `supabase/config.toml` has valid Google credentials. Restart the stack with `npx supabase stop` and `npx supabase start` after changes.
- **Environment Variable Binding**: Missing `SUPABASE_URL` and `SUPABASE_KEY` must be populated in `backend/.env` for Docker builds.
- **Benchmark Auth Backdoor (local only)**: The `X-Test-Key` header is accepted only when ALL THREE conditions are met:
  1. `IS_PRODUCTION=false` (or unset)
  2. `ENABLE_TEST_AUTH=true`
  3. `BENCHMARK_SECRET` is set (non-empty)
  The `X-Test-Key` value must match `BENCHMARK_SECRET`. Without these, `ruthless_benchmark.py` and manual `curl -H X-Test-Key` will receive 401. Never enable this in production.

## Local Benchmarking
- After setting the auth backdoor vars above, run from `backend`:
  ```bash
  JWT_SECRET=$(grep '^JWT_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  BENCHMARK_SECRET=$(grep '^BENCHMARK_SECRET=' .env | cut -d= -f2- | tr -d '\n\r')
  .venv/bin/python -u benchmarks/ruthless_benchmark.py --endpoint http://localhost:8000 --test-key "${BENCHMARK_SECRET:-$JWT_SECRET}" --concurrency 2
  ```
- The current working provider for low-latency local runs is `LLM_PROVIDER=nim`. Sarvam and OpenRouter keys are present as fallbacks.


## Cache Management & Ingestion Isolation
- `REDIS_CACHE_MAX_KEYS` applies only to exact-query keys matching `mukthiguru:cache:*`; never apply it to queues, sessions, quotas, telemetry, rate limits, or Second Brain namespaces.
- Cache telemetry uses fixed namespace labels and bounded SCAN sampling. `REDIS_CACHE_MAX_KEYS=0` is the explicit backward-compatible disable value. Existing keys must remain refreshable when the ceiling is reached.
- Never run global `FLUSHALL` for routine query-cache maintenance. Use the targeted Qdrant/Redis namespace procedure in the production readiness runbook, then verify preserved queue, session, quota, telemetry, and memory namespaces.
- Celery workers accept only the allowlisted queues `ingestion`, `embedding`, `indexing`, `okf`, and `memory`; `CELERY_QUEUES` and `CELERY_CONCURRENCY` are validated at startup. Do not remove `memory` or change concurrency until queue throughput and user-memory SLA are measured.

- **Query-Side Caches (GPTCache & Redis)**: The application uses GPTCache (for semantic caching) and Redis (for response caching) to optimize frontend query latency.
- **In-Memory Cache Flushing**: Caches can be flushed safely at any time using:
  - **Preferred (Makefile)**: `make flush-cache` (executes `python3 scripts/ops/flush_cache.py`, which scans and deletes only query-cache namespaces; it never runs `redis-cli flushall`).
- **Ingestion Pipeline Isolation**: Flushing these query-side caches has **zero** impact on the active or pending ingestion processes. Ingestion is an ETL pipeline that writes exclusively to Qdrant and Neo4j and maintains its own resumption checkpoints in `scripts/ingestion_state.json`. Agents can confidently assure the user that cache flushing is fully isolated and safe to execute.

## Non-Interactive Shell Commands
**ALWAYS use non-interactive flags** with file operations to avoid hanging on confirmation prompts.

Shell commands like `cp`, `mv`, and `rm` may be aliased to include `-i` (interactive) mode on some systems, causing the agent to hang indefinitely waiting for y/n input.

**Use these forms instead:**
```bash
# Force overwrite without prompting
cp -f source dest           # NOT: cp source dest
mv -f source dest           # NOT: mv source dest
rm -f file                  # NOT: rm file

# For recursive operations
rm -rf directory            # NOT: rm -r directory
cp -rf source dest          # NOT: cp -r source dest
```

**Other commands that may prompt:**
- `scp` - use `-o BatchMode=yes` for non-interactive
- `ssh` - use `-o BatchMode=yes` to fail instead of prompting
- `apt-get` - use `-y` flag
- `brew` - use `HOMEBREW_NO_AUTO_UPDATE=1` env var

## Troubleshooting Guidelines for Agents

### React Component Crashing
- **Symptom**: Frontend serves HTTP 200 but renders a blank page, and console shows `ReferenceError: [FunctionName] is not defined`.
- **Action**: When modifying React components, ensure all referenced functions in event handlers (e.g. `onClick={handleSignOut}`) exist in the component scope. If undefined, it will throw a `ReferenceError` during render and unmount the entire app.

### Code-Review-Graph MCP "Context Canceled"
- **Symptom**: `code-review-graph: INFO Starting MCP server 'code-review-graph' with transport 'stdio' : context canceled`
- **Action**: This is normal behavior when the IDE restarts or the agent session ends. Do **NOT** try to "fix" the MCP server code. If it fails to start entirely, verify `mcp_config.json` is valid JSON and points to `.venv/bin/code-review-graph`.

### "Connection issue" chat responses that are actually retrieval failures
- **Symptom**: `/api/health` reports `ready: true`, but chat answers come back as a generic "I'm experiencing a temporary connection issue" instead of doctrine, and Railway logs show `Qdrant dense search failed ... Vector dimension error`.
- **Action**: This is the 2026-07-16 embedding-dimension incident — see root `CLAUDE.md`'s "Embedding dimension contract" section for the full invariant, fix locations, and still-open items (Docker model pre-caching, OpenRouter→NIM failover). Don't re-diagnose from scratch; verify the fix is still in place in `embedding_service.py`/`qdrant/client.py` first.

## Post-Change Documentation Checklist
Agents MUST update the following documentation after completing a fix, feature, or architectural change:
- [ ] **lessons.md**: Document the specific implementation pattern, architectural decision, or "lesson learned".
- [ ] **README.md**: If a new service, route, or environment variable is added, update the README to reflect these changes.
- [ ] **docs/PRODUCT_OPPORTUNITIES.md** (Roadmap section): Mark items as complete or add new technical debt discovered during the change.
- [ ] **docs/DEVELOPER_GUIDE.md**: Update if the onboarding or development workflow has changed.
- [ ] **CLAUDE.md**: Update structural directory map, commands, or URL matrix.
- [ ] **AGENTS.md**: Update agent context, checklist, or guidelines if necessary.

## Session Completion
**When ending a work session**, present the final changes and run validation. Commits and pushing are optional and should only be performed if explicitly approved by the user.

**WORKFLOW:**

1. **File issues for remaining work** - Create issues for anything that needs follow-up
2. **Run quality gates** (if code changed) - Tests, linters, builds
3. **Update Documentation** - Perform updates using the Post-Change Documentation Checklist, requiring applicable documentation updates when markdown files change
4. **Hand off** - Provide context for next session
## Agent Technical Skills
- **Pre-Compiled Technical Skills**: There are 15 pre-compiled agent skills containing structured summaries, patterns, and cheatsheets from technical books. They are located locally under `.agents/skills/<slug>` and mirrored globally at `~/.config/agents/skills/<slug>`.
- **How to Use**: Agents MUST read the `skill.md` file in these directories to load the core frameworks, or query the specific chapter files (e.g. `chapters/ch01-...`) for deep-dive technical context on topics like LangChain, LangGraph, RAG, System Design, or Database Internals.

<!-- code-review-graph MCP tools -->
## MCP Tools: code-review-graph

**IMPORTANT: This project has a knowledge graph. ALWAYS use the
code-review-graph MCP tools BEFORE using Grep/Glob/Read to explore
the codebase.** The graph is faster, cheaper (fewer tokens), and gives
you structural context (callers, dependents, test coverage) that file
scanning cannot.

### When to use graph tools FIRST

- **Exploring code**: `semantic_search_nodes` or `query_graph` instead of Grep
- **Understanding impact**: `get_impact_radius` instead of manually tracing imports
- **Code review**: `detect_changes` + `get_review_context` instead of reading entire files
- **Finding relationships**: `query_graph` with callers_of/callees_of/imports_of/tests_for
- **Architecture questions**: `get_architecture_overview` + `list_communities`

Fall back to Grep/Glob/Read **only** when the graph doesn't cover what you need.

### Key Tools

| Tool | Use when |
| ------ | ---------- |
| `detect_changes` | Reviewing code changes — gives risk-scored analysis |
| `get_review_context` | Need source snippets for review — token-efficient |
| `get_impact_radius` | Understanding blast radius of a change |
| `get_affected_flows` | Finding which execution paths are impacted |
| `query_graph` | Tracing callers, callees, imports, tests, dependencies |
| `semantic_search_nodes` | Finding functions/classes by name or keyword |
| `get_architecture_overview` | Understanding high-level codebase structure |
| `refactor_tool` | Planning renames, finding dead code |

### Workflow

1. The graph auto-updates on file changes (via hooks).
2. Use `detect_changes` for code review.
3. Use `get_affected_flows` to understand impact.
4. Use `query_graph` pattern="tests_for" to check coverage.

## Local Codebase Intelligence & Memory MCP Layer

In addition to `code-review-graph`, this workspace is integrated with four dedicated local/global MCP servers and plugins:
1. **Graphify**: Offline AST codebase graph tool (provides `code-review-graph` MCP tools).
2. **Claude-Mem**: Long-term episodic/semantic memory worker (SQLite + ChromaDB).
3. **CodeGraph**: AST query engine using WASM-compiled tree-sitter grammars.
4. **Understand Anything**: Multi-agent codebase knowledge graph builder and visualizer.

- **Auto-Sync Hook**: A post-commit hook at `.git/hooks/post-commit` automatically runs `node scripts/ops/update-understand-graph.cjs` in the background on every commit to keep the graph (`.understand-anything/knowledge-graph.json`) fresh.
- **Manual Sync**: Run `node scripts/ops/update-understand-graph.cjs` to force sync the graph.

### Strict Environment Constraints
- **Node.js v22 LTS Only**: Do **NOT** upgrade Node.js to Node `25.x` or run CodeGraph commands under Node 25. Node 25 has a critical WASM compiler Zone allocation bug that causes out-of-memory crashes (`Zone allocation constraints`) during tree-sitter compilation. Always keep the shell environment linked to Node 22 LTS (`/opt/homebrew/opt/node@22/bin`).
- **Bun Dependency for Claude-Mem**: Claude-Mem's background worker service runs on Bun for high-performance sqlite bindings. Ensure `bun` is available at `/opt/homebrew/bin/bun`.
- **Git Worktree Cleanup**: In agentic sessions, temporary git worktrees (`.claude/worktrees/agent-*`) can accumulate. This causes severe local git indexing lag. You **MUST** run `git worktree prune` and explicitly delete any temporary worktrees you created (`git worktree remove --force <path>`) before finishing your session.

### Utilizing Local MCP Tools
- **Explore first, grep last**: Use CodeGraph, Graphify, and Understand Anything rather than running heavy recursive glob/grep commands across thousands of files. It saves token costs, prevents host memory thrashing, and respects structural linkages.
- **Memory Recalls**: Leverage `claude-mem` to recall key patterns or historical insights across conversation checkpoints.

## Ponytail & Headroom Guidelines

### The Ladder (hard rule — runs BEFORE writing any code)
Before writing code, the agent stops at the first rung that holds:

1. Does this need to exist?   → no: skip it (YAGNI)
2. Already in this codebase?  → reuse it, don't rewrite
3. Stdlib does it?            → use it
4. Native platform feature?   → use it
5. Installed dependency?      → use it
6. One line?                  → one line
7. Only then: the minimum that works

The ladder runs after it understands the problem, not instead of it: it reads the code the change touches and traces the real flow before picking a rung. Lazy about the solution, never about reading.

Lazy, not negligent: trust-boundary validation, data-loss handling, security, and accessibility are never on the chopping block.

### Ponytail Principle
Keep implementations lightweight, minimal-diff, and simple:
- **Thin wrappers**: Prefer small, focused helper scripts or inline functions over heavy abstractions or new classes.
- **Self-Checks**: Python files should contain a runnable `if __name__ == "__main__":` block at the bottom for quick verification.
- **Optional/Stubbed Features**: Gracefully degrade or skip components if dependencies are not available on the runtime host.
- **LRU Cache Usage**: Use simple caching patterns (e.g. `lru_cache`) instead of custom state tracking classes where possible.

### Headroom Principle
Implement system configurations and runtime operations with safety margins (headroom):
- **Cost Steering**: Automatically steer LLM prompting towards brevity (`COST_STEERED_BREVITY_LIMIT` words) when context/history length is high to optimize token usage.
- **Reversible Context Compression (CCR)**: Allow the LLM to request full text for compressed text using `[RETRIEVE: <source_url>]` pattern; generation stage will intercept and swap the original text.
- **Timeout and Resource Headroom**: Always configure timeouts with safety margins (e.g. 120s timeouts for sequence calls, or 10% GPU/CUDA headroom) to avoid transient service lockups.

Respond terse like smart caveman. All technical substance stay. Only fluff die.

Rules:
- Drop: articles (a/an/the), filler (just/really/basically), pleasantries, hedging
- Fragments OK. Short synonyms. Technical terms exact. Code unchanged.
- Pattern: [thing] [action] [reason]. [next step].
- Not: "Sure! I'd be happy to help you with that."
- Yes: "Bug in auth middleware. Fix:"

Switch level: /caveman lite|full|ultra|wenyan
Stop: "stop caveman" or "normal mode"

Auto-Clarity: drop caveman for security warnings, irreversible actions, user confused. Resume after.

Boundaries: code/commits/PRs written normal.

## Mobile App

- **Capacitor 8** wraps the Vite/React build for Android + iOS. Same codebase, no separate mobile repo.
- **Package id** `com.askmukthiguru.app`, display name `AskMukthiGuru`.
- **Router**: HashRouter on native, BrowserRouter on web — selected in `src/App.tsx` (BrowserRouter breaks in the Capacitor WebView because assets are served from `https://localhost/` with no server fallback).
- **Backend URL**: `src/lib/backendUrl.ts` forces Railway prod on native (`Capacitor.isNativePlatform()` check) because `window.location.hostname` is `localhost` inside the WebView and the prod-host regex would miss it.
- **Push (frontend)**: `src/components/common/PushNotificationsManager.tsx` — registers device token via `@capacitor/push-notifications`, sends to backend. `addListener` returns a Promise → use a `disposed` flag for race-safe cleanup.
- **Push (backend)**: `backend/app/api/push.py` (routes) + `backend/services/push_service.py` (FCM + APNs dispatch). Device tokens stored in `push_devices` table (migration `20260713000000_create_push_devices.sql`).
- **OAuth deep link**: scheme `com.askmukthiguru.app://auth-callback` — captured via `App.addListener('appUrlOpen')` in `src/App.tsx`. Android intent-filter + iOS CFBundleURLTypes wired by Capacitor config. Add this URL to Supabase Auth redirect URLs.
- **Storage**: `@capacitor/preferences` (SharedPreferences / NSUserDefaults) via a `SupportedStorage` adapter for supabase-js — `localStorage` is unreliable in the WebView.
- **Build cmd**: `npm run cap:sync` (vite build + cap sync). Native open: `npm run cap:open:android` / `cap:open:ios`.
- **Re-create native projects**: `rm -rf android ios && npx cap add android && npx cap add ios` — only when package id or Capacitor plugins change drastically. Discards native-side customizations.
- **Icons/splash**: `python3 scripts/ops/generate_mobile_assets.py` (regenerates from `public/icon-512.png`).
- **Store submission**: `docs/MOBILE_RELEASE_RUNBOOK.md` — full Play + App Store guide.
- **Store listing copy**: `docs/STORE_LISTING.md`.
- **Signing + push creds**: `CREDENTIALS_GUIDE.md` → "Mobile App Credentials" (keystore, `google-services.json`, APNs `.p8`, backend env: `FIREBASE_CREDENTIALS_JSON`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY_PATH`, `APNS_KEY_PEM`, `APNS_BUNDLE_ID`).
- **Known TODOs**: ~~Apple Sign-In~~ ✅ implemented (native iOS, `AuthPage.tsx` — requires Supabase Apple provider config before submission). ~~Delete-account flow~~ ✅ implemented (`ProfilePage.tsx` + `delete-my-account` edge function).

## Multimodal Chat Upload Invariants (Aug 19, 2026)
- `POST /api/chat/upload` is ephemeral extraction only. Upload bytes must not enter corpus, Second Brain, Qdrant, or Neo4j without a separate explicit indexing flow and consent boundary.
- Per-file cap is 10 MB; combined cap is 50 MB; chat `attachment_context` is capped at 8,000 characters. Enforce declared-size and bounded-read checks before extractor work.
- MIME declarations are untrusted. Prefer magic-byte sniffing, sanitize filenames with `Path(name).name`, and return truthful metadata-only fallback when OCR/transcription/PDF extraction is unavailable.
- Attachment context is separate from `user_message` and `memory_context`; generation must label it as untrusted evidence and never follow instructions found inside it.
- Any cache or coalescer key for attachment-backed turns must bypass shared reuse or include a bounded content digest. Never include raw attachment text in keys.

# Session Handoff — Jul 11, 2026

## Session Summary
Full 5-phase emergent security audit. 93% pass rate. 30+ fixes across rate limiting, model validation, PII logging, CORS/nginx, access control (IDOR), container security, and CI/CD hardening.

## What Was Done
- **Phase 1 (Critical)**: STT/TTS rate limits (10/min), OpenRouter classify model name fix, audit scripts created (`scripts/security/`), secrets scan, Supabase RLS enabled on 5 tables, PGRST202 schema cache reloaded.
- **Phase 2 (Hardening)**: PII log redaction across 6 files, per-user rate limiting via `TenantContext.get_user_id()`, HSTS+CSP headers in nginx, CORS origin doc fix in docker-compose.
- **Phase 3 (Access Control)**: 2 IDOR fixes on notebook routes, Swagger/docs gated in production, metrics endpoint admin-only, per-user LLM call usage monitor, breath-teaching rate limit added.
- **Phase 4 (Pipeline)**: Non-root users in 3 Dockerfiles, HEALTHCHECK on 2 containers, Trivy + Bandit in CI workflows, `gptcache` image pinned to version.
- **Phase 5 (Report)**: Audit scripts run, report at `scripts/security/report.md`, score 28/30 PASS.
- **Remaining (fixed)**: `.env.example` created at root with `!.env.example` gitignore exception, `password` removed from `check_docker_health.py` `SERVICES` dict.

## Running Services
- Backend: `http://localhost:8000` (healthy)
- Frontend: `http://localhost:80` (Nginx proxy)
- Neo4j: `bolt://localhost:7687` (browser at `http://localhost:7474`)
- Local Supabase: Postgres :54322, API :54321, Studio :54323
- Celery Worker: healthy
- All infra: Qdrant, Redis, Jaeger, Prometheus, Grafana

## Security Audit Scripts
- `scripts/security/audit_log_pii.sh` — scan for PII in log statements
- `scripts/security/audit_secrets.sh` — scan for hardcoded secrets
- `scripts/security/audit_endpoints.sh` — audit API endpoint exposure
- `scripts/security/audit_cors_headers.sh` — check CORS and security headers
- `scripts/security/run_emergent_audit.sh` — run all audits in sequence
- `scripts/security/report.md` — latest audit report (93% pass)
- `scripts/security_audit.py` — programmatic security audit runner

## Critical Context
- Celery worker uses same `backend/Dockerfile` as backend — both must be rebuilt together.
- `docker-rebuild-web` only rebuilds `backend` and `frontend` — run `docker compose up -d --build celery-worker` separately.
- PGRST204 fix: `NOTIFY pgrst, 'reload schema'` after schema changes.
- Swagger docs gated behind `IS_PRODUCTION` check in `main.py`.
- `.env.example` has a `!.env.example` exception in `.gitignore`.
- Security audit report regenerated by running `bash scripts/security/run_emergent_audit.sh`.

## What Was Done
- **MD quality**: Added `resource` field (clean YouTube URL) to all 22 files. Normalized `title` quoting. Added wiki-link cross-references `[[concept-id]]` to 15 files (Karpathy pattern). Created `_scripts/add_wikilinks.py` batch injection tool. See `.claude/tasks/transcript-md-quality.md`.
- **Fixed Neo4j seed Cypher**: `SET t:Teacher:$label_type` → f-string safe interpolation in `backend/app/db/seed_ontology.py`.
- **Fixed celery `/memory` path**: `_BACKEND.parent` → `/app/memory/okf` in `backend/scripts/extract_okf_from_stores.py`.
- **Synced `scripts/` copy**: `backend/scripts/extract_okf_from_stores.py` and `scripts/extract_okf_from_stores.py` byte-identical again.
- **Anonymous user guard**: `memory_service.py` — `_is_anonymous` check returns early for `"anonymous"` user_id to prevent UUID insert errors.
- **PGRST204 retry**: Service retries without `claim`/`confidence`/`decay_score` columns.
- **Celery time limits doubled**: soft 600s→1800s, hard 900s→2400s for LLM retry chains.
- **Guru_memories columns applied**: Added `claim TEXT`, `confidence DOUBLE PRECISION`, `decay_score DOUBLE PRECISION DEFAULT 1.0` to local Supabase + migration file. Reloaded PostgREST schema cache.
- **Migration created**: `supabase/migrations/20260710000000_add_guru_memories_missing_columns.sql`.
- **Reranker JSON error fixed**: Added `json.JSONDecodeError` catch + HF cache clear retry in `_ensure_reranker()` and `_load_fallback()`.
- **Guardrails set to lightweight**: `GUARDRAILS_PROVIDER=lightweight` — skips Llama Guard / Rejection Classifier / NeMo loading (no startup noise).
- **LightRAG timeout default raised**: `lightrag_retrieval_timeout` 3→30s in config.py (matches `.env` value).
- **Knowledge graph query enabled**: `knowledge_graph_query_enabled=True` — LightRAG now queried for RELATIONAL/FACTUAL/QUERY intents (2,200+ relations available).
- **download_models.py fixed**: Rejection classifier model corrected from `meta-llama/Llama-Guard-3-1B` → `protectai/distilroberta-base-rejection-v1`.
- **All containers rebuilt**: backend, celery-worker, frontend — all healthy.
- **Chat pipeline verified**: End-to-end query returns response with context.

## Running Services
- Backend: `http://localhost:8000` (healthy)
- Frontend: `http://localhost:80` (Nginx proxy)
- Neo4j: `bolt://localhost:7687` (browser at `http://localhost:7474`)
- Local Supabase: Postgres :54322, API :54321, Studio :54323
- Celery Worker: healthy, tasks registered (okf_compile, okf_extract, ingestion)
- All infra: Qdrant, Redis, Jaeger, Prometheus, Grafana

## Remaining Issues
- None critical. ColBERTv2 fallback to CrossEncoder is expected (model not cached).
- `test_openrouter_provider_delegation` is a pre-existing test failure unrelated to these changes.

## Demo
1. Open `http://localhost` → Chat with the guru
2. Navigate to `/profile` → Click graph toggle (Network icon in Memory card)
3. See 40 ontology nodes (Teachers, Concepts, Practices) as SVG
4. Drag to pan, scroll to zoom

## Files Changed (This Session)
- `memory/okf/*.md` — 22 files with `resource` field, wiki-links, quoted titles
- `memory/okf/_scripts/add_wikilinks.py` — batch wiki-link injection
- `.claude/tasks/transcript-md-quality.md` — quality plan
- `backend/services/memory_service.py` — anonymous guard + PGRST204 retry
- `backend/celery_config.py` — doubled time limits
- `backend/scripts/extract_okf_from_stores.py` — fixed `/memory` → `/app/memory`
- `scripts/extract_okf_from_stores.py` — synced copy
- `backend/app/db/seed_ontology.py` — fixed Cypher f-string
- `supabase/migrations/20260710000000_add_guru_memories_missing_columns.sql` — new migration
- `backend/services/embedding_service.py` — HF cache clear retry for reranker JSON error
- `backend/services/reranker_service.py` — HF cache clear retry for fallback reranker
- `backend/app/config.py` — `lightrag_retrieval_timeout` 3→30, `knowledge_graph_query_enabled` True
- `backend/.env` — `GUARDRAILS_PROVIDER=lightweight`
- `backend/scripts/download_models.py` — fixed rejection classifier model ID

## Critical Context
- Celery worker uses same `backend/Dockerfile` as backend — both must be rebuilt together.
- `docker-rebuild-web` only rebuilds `backend` and `frontend` — run `docker compose up -d --build celery-worker` separately.
- PGRST204 fix: `NOTIFY pgrst, 'reload schema'` after schema changes.
- Supabase `anond` key is set in `.env` files (local).
- `npx supabase db query "..."` to run SQL against local Postgres.
- `GUARDRAILS_PROVIDER=lightweight` skips all ML guardrails (Llama Guard, Rejection Classifier, NeMo). Lightweight handler covers 13 regex-based topic categories, prompt injection, and emotional wellness redirects.
- `knowledge_graph_query_enabled=True` enables LightRAG graph traversal for RELATIONAL/FACTUAL/QUERY intents with 30s timeout. LightRAG holds 2,365 entities + 2,200 relations.

## Railway Deployment (Production)
- **Project**: `resilient-embrace` | **Service**: `askmukthiguru-8119b0e8` | **Environment**: `production`
- **Status (Aug 11, 2026)**: Railway is **paused** (stopped for a while). Before the next deploy, set `FORWARDED_ALLOW_IPS` (e.g. `10.0.0.0/8`) — `start_railway.py` now exits at startup without an explicit non-wildcard value (fail-closed; see Security Invariants). Until then, dev continues on the docker compose stack, which runs plain uvicorn and needs no such var.
- **Deploy method**: Use `railway up` (tarball upload) — **NOT** `railway redeploy --from-source`
  - `railway up` uploads a tarball and deploys reliably
  - `railway redeploy --from-source` gets stuck at INITIALIZING on this repo
- **Replicas**: Set to **1 replica** in `railway.json` — 2 replicas caused second replica to fail init timeout
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

## ONNX Reranker + ColBERT MaxSim (Jul 27, 2026)

### Phase 1 — ONNX INT8 CrossEncoder (shipped)
- **Reranker backend**: `temsa/mmarco-mMiniLMv2-L12-H384-v1-onnx-cpu-qint8` (23MB ONNX INT8, dynamic quantization of MatMul/Gemm/Attention). Replaces PyTorch `cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` (91MB).
- **Toggle**: `RERANKER_BACKEND=onnx_int8` (default, already in config.py). Rollback: `RERANKER_BACKEND=flagembedding` in `.env` and restart.
- **Tokenizer source**: loaded from the temsa repo (not upstream) to match the ONNX model's own tokenizer files. See lessons.md "Tokenizer source = model repo".
- **Validation**: `backend/scripts/validate_onnx_reranker.py` — P0 env_parse, P1 capability, P2 Spearman >0.90 (passes at 0.976), P3 latency (warm P95 449ms). Run: `cd backend && python3 scripts/validate_onnx_reranker.py`.

### Phase 2 — ONNX-Native ColBERT MaxSim (shipped, disabled by default)
- **What**: Multilingual late-interaction reranking using BGE-M3's colbert_vecs output (ort_out[2], 1024d per token, L2-normalized). Replaces the English-only RAGatouille ColBERTv2 path. 100+ languages.
- **Toggle**: `ENABLE_COLBERT=true` in `.env` (defaults False — Phase 2 ships disabled). When True, `cascaded_rerank()` uses `_colbert_maxsim_rerank()` (ONNX-native, batched); when False, keeps the deprecated RAGatouille fallback.
- **Batched**: `_colbert_maxsim_rerank` encodes query + ALL docs in ONE `encode_with_colbert` call, then scores via `batch_maxsim` (pure NumPy matmul). No per-doc loop.
- **CLS exclusion**: `encode_with_colbert` slices `colbert_vecs[:tokens_num - 1]` per doc, matching FlagEmbedding's `_process_colbert_vecs`. See lessons.md.
- **Validation**: `backend/scripts/validate_colbert_maxsim.py` — P0 env_parse, P1 capability, P2 latency (warm P95 248ms < 2000ms gate), P3 multilingual (en/hi/te/mr all pass), P4 ColBERT-vs-CrossEncoder Spearman 0.89 > 0.85 gate. Run: `cd backend && python3 scripts/validate_colbert_maxsim.py`.
- **RAGatouille**: kept in `requirements.txt` with a TODO comment marking it deprecated. Do NOT remove until the RAGatouille path is confirmed dead in `cascaded_rerank`.

### Pre-existing bug fixed: ONNX encoder re-download
- `_load_onnx_encoder` was not setting `self._encoder`, so `_ensure_encoder()`'s short-circuit (`if self._encoder is not None: return`) never fired on the ONNX path. Every `encode()`/`encode_batch()`/`encode_with_colbert()` call re-downloaded the 570MB ONNX model (~30s per call). Fix: `self._encoder = session` at the end of `_load_onnx_encoder` — a marker that makes the short-circuit fire. 30657ms → 46ms per call (660× improvement). This was a silent production bug since cp1 shipped (Jul 26). See lessons.md.

### Dependency Lock Authority and Clean Release Installs (Aug 13, 2026)

`backend/requirements.txt` is the human-maintained production input and
`backend/requirements.lock` is the committed, fully pinned release artifact.
Docker images and CI install the lock file only. After changing the input, run
from the repository root:

```bash
uv pip compile backend/requirements.txt --output-file backend/requirements.lock
git diff --check backend/requirements.txt backend/requirements.lock
```

The default backend profile deliberately keeps `numpy<2.0` for the tested
PyArrow stack. LettuceDetect is a disabled-by-default optional model profile in
`backend/requirements-optional-ml.txt`; do not enable it in production until its
NumPy 2.x compatibility has passed a separate staging test.

`package-lock.json` is the frontend lock authority; never use `npm install` in
CI or deployment. Clean release evidence must include `npm ci`, `npm test --
--run`, and `npm run build`. Backend clean-install evidence must use a fresh
Python 3.12 environment and `pip install -r backend/requirements.lock` before
running the backend suite. Do not claim a release is reproducible solely because
the existing development virtual environment passes tests.


## Active latency and quality invariants — 2026-08-22

The production latency pass introduced two safe hot-path rules. First, the bounded meditation-versus-contemplation answer may short-circuit only after input and distress guardrails, only for English, and only with explicit limited-support metadata, zero citations, and abstained grounding. Second, translation is a bounded dependency: query, history, and final-answer provider calls use `translation_timeout_s` (default 5 seconds) and fail open with native/original text rather than blocking the full chat pipeline. The English-with-Indic-preference case must not invoke translation at all; native and code-switched Indic input must retain translation and guardrail coverage.

The following changes remain evidence-gated and must not be activated from intuition or an aggregate average: `EMBEDDING_BACKEND=onnx_int8` for query/index migration, RRF/DBSF weights or prefetch multipliers, Neo4j schema mutations, and broad graph parallelization. Activation requires a held-out evaluation with per-query-class NDCG/recall/precision, answer faithfulness, citation correctness, abstention/false-refusal behavior, p95/p99 latency, timeout/error rate, tenant/rights isolation, and a documented rollback. Existing fp32 query/index compatibility, fusion configuration, Neo4j schema, graph caps, and fail-open behavior are the production defaults until those gates pass.

The 2026-08-22 production verification observed the bounded comparison at approximately 7 ms with a 367-character limited-support response and no citations. The active 8655709 runtime returned an English FAQ under Hindi preference in approximately 4.3 seconds and a native Hindi FAQ in approximately 4.0 seconds, while the benchmark matrix also captured a 10.8-second pipeline/13.8-second wall-clock Hindi run, so multilingual latency remains variable. The attempted 940eb55 translation-timeout rollout failed during `Initialization › Snapshot code` after 15 minutes; Build/Deploy never started, and Railway continued to show 8655709 as ACTIVE. Deep health reported `ready=true`, `status=healthy`, embedding dimension 1024, queue size 0, exact-cache keys 0, and healthy Qdrant, Redis, Neo4j, LLM, embedding, fast graph, and LightRAG checks. The translation-timeout code is production-active through the successful `806799d` rollout; continue to treat multilingual tail variance as an open performance risk.

The sandbox has no `pytest` or `pydantic-settings`. Do not install packages for a release check when the task forbids installation, and never represent static compilation or regex safety as a substitute for dependency-complete tests. The focused regression test is committed for execution in CI or the locked production test image.


## Post-rollout latency and memory evidence — 2026-08-22

The current production runtime is `806799d`: Railway backend deployment `8515a2e2-5f40-4901-93be-fd31206526b0` and worker deployment `9061f71f-1f29-46a0-b470-eeb8743e5217` both reached SUCCESS. Public health returned `ready=true`, `status=healthy`, embedding dimension 1024, exact-cache keys 0, queue size 0, and `/api/healthz` returned `{"ok":true,"status":"alive"}`. The Telugu quality regression was corrected in production: the prior 52-character refusal became a 289-character grounded response with one citation and language-aware verification.

Warm repeated Hindi FAQ requests completed in roughly 7 seconds wall-clock with 3.3–3.8 seconds reported pipeline latency, but the final matrix also recorded a 21.2-second Hindi wall-clock outlier during rollout. Multilingual latency therefore remains a tail-observability item, not a solved claim. The current query is now passed into Second Brain recall; preserve this contract for all authenticated memory paths.


## Final latency hardening evidence — Aug 22, 2026

- Runtime `36e6f22` is the latest verified production revision; backend deployment `c1387196-6860-4da9-b7f5-1c74acfce205` and worker deployment `49e64d1d-e979-4459-9f3c-226cf002b8a7` completed successfully. `/api/health` returned `ready=true`, `status=healthy`, Qdrant/Redis/Neo4j/LLM/embedding/graph/LightRAG checks healthy, and chat backpressure clear.
- The translation cache is process-local only, SHA-256 keyed, capped at 512 entries with a 15-minute TTL, and excludes text over 240 characters plus obvious email-like, URL-like, and phone-like input. Never move this cache to shared storage without a privacy review and hit-rate evidence.
- The on-device intent classifier is prewarmed during non-fatal application startup with a native Indic probe. This prevents the first non-keyword Indic request from loading `all-MiniLM-L6-v2` on the user-visible path. Startup prewarm failure must remain non-fatal.
- Query, history, and final-answer translation logs report source/target and duration only; never log raw user text, translated text, or attachment content in latency instrumentation.
- Final production smoke preserved the bounded comparison fast path, grounded Telugu response, abstained unsupported capability response, and distress safety redirect. Hindi improved after prewarm but still has a non-zero long tail; do not claim universal low latency until stable multi-run p95 evidence improves.
- ONNX INT8, RRF/DBSF changes, Neo4j schema mutation, and broad graph parallelization remain disabled until the held-out evaluation contract in `docs/LATENCY_EVIDENCE_GATES.md` passes. Missing local dependencies are an indeterminate result, never a pass.


## Remote Neo4j and benchmark audit — Aug 22, 2026

- Remote Neo4j constraints verified read-only: `UNIQUE_CONCEPT_NAME`, `UNIQUE_PRACTICE_NAME`, and `UNIQUE_TEACHER_NAME`; all owned range indexes were `ONLINE` at 100% population. Concept and teacher lookups used `NodeUniqueIndexSeek`; one-hop concept traversal used indexed seek plus `Expand(All)`.
- The ordinary-index maintenance script declares `entity_type`, `source_id`, `entity_id`, and `tenant_id`. Remote inspection showed `entity_id` range/full-text coverage but did not show ordinary `entity_type`, `source_id`, or `tenant_id` indexes. Do not add them from application startup. Use a separate lock-protected maintenance job with schema snapshot, health check, bounded execution, post-plan verification, and rollback note.
- A single-session remote graph benchmark measured indexed concept, teacher, one-hop expansion, and full-text calls at roughly 1.18–1.34 seconds including cypher-shell overhead. Per-query SSH timing around 8–9 seconds was invalid for database-performance comparison because connection setup dominated.
- The latest production smoke found an open quality regression: `What is the meaning of stillness?` returned a 38-character `refusal_quality_gate` answer with faithfulness `0.0` despite three direct-source provenance items and an `Inner Stillness` entity. Treat retrieved-evidence refusals as P0 quality defects.
- Full question-bank production load tests must not run uncontrolled against user-serving production. Use staging or a dedicated benchmark replica, unbuffered progress, a global budget, and bounded concurrency. The interrupted live run is evidence of tail load, not a complete benchmark pass.

## Cost-effectiveness invariants — Aug 22, 2026

- Current Railway workspace usage is $28.7854, with $27.0931 (94.1%) from memory, $1.3513 (4.7%) from CPU, $0.2645 (0.9%) from volume, and $0.0766 (0.3%) from egress. The $30 hard limit is nearly reached and the current estimate is $53.84. Memory reduction is the first cost target.
- The observed 30-minute memory averages were approximately 8.07 GB backend, 2.45 GB Neo4j, and 154 MB worker. Do not reduce worker concurrency without queue/SLA evidence.
- Graph parallelization overlaps vector and graph calls but does not automatically reduce billable work. Require graph-on/off cost-per-successful-answer, quality, timeout, p95/p99, and resource evidence before broadening it.
- OpenRouter provider-reported cost, known-rate estimates, and unknown costs must remain separate. The configured Gemini generation model is not covered by the fallback-rate table; missing provider cost must never silently aggregate as zero.
