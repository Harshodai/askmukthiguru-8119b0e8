# Handoff — Security / RLS / Metrics / Release Readiness / Guru Voice Epic

Date: Jul 31, 2026 · Branch: merged to `main` · HEAD: `cd5eeded`

## 1. Goal

Product-hardening epic for AskMukthiGuru ahead of production release (Railway backend + Lovable frontend + Supabase). Six workstreams:

1. **AAL2/MFA regression coverage** — Playwright E2E proving unauthenticated/forged sessions never reach protected routes, plus backend enforcement.
2. **RLS verification** — prove cross-user isolation (Alice/Bob) works via SQL policies, scripted verifier, E2E test, nightly CI.
3. **Leaked-password protection** — Supabase Pro setting + verification script.
4. **Metrics parity** — single source of truth between backend pydantic and frontend zod schemas, `GET /api/metrics`, UI hook.
5. **Streak-based healing course assignment** — trigger on distress *streaks/repetition*, never a single signal.
6. **Langhanam unified guru voice** — one voice for both gurus, benchmark-gated (prompt-based vs tone-adapter variants). **Enabled by default** (`langhanam_voice_enabled = True`) after prompt variant scored 4.306/5.0 ≥ 4.0 gate on 2026-07-31.

Success = all 16 plan tasks done, docs updated, merged to main. *(Test suites below are filtered/partial runs — see §2 for caveats.)*

## 2. Current State of Code

**All 16 tasks DONE, merged to `main` and pushed** (`50e40ca5..cd5eeded`, merge `cd5eeded`). 15 epic commits + docs commit `cc3198f9` + dotenv-shim removal `b7c65450`.

- **E2E**: `tests/e2e/security-aal2.spec.ts` (extended, 6 pass) + `tests/e2e/rls-cross-user.spec.ts` (new, 2 pass). Full suite: **251 passed, 22 skipped, 0 failed**.
- **Backend**: `require_aal2` dep + `GET /api/health/mfa` (`backend/services/auth_service.py`, `backend/tests/test_aal2_dependency.py` — 12 tests). `GET /api/metrics` (`backend/app/api/metrics.py`). Healing course service (`backend/services/healing_course_service.py`, 37 tests) + `POST /api/healing-course/assign|progress` (`backend/app/api/healing_course.py`). RLS verifier (`backend/scripts/verify_rls_policies.py`, 12 probes green). Guru voice (`backend/services/guru_voice_langhanam.py`, `backend/rag/nodes/guru_tone_adapter.py`, `backend/benchmarks/guru_voice_benchmark.py`). **Filtered pytest run: 1224 passed** (excludes integration/heavy tests requiring live services; not a full-suite green).
- **Frontend**: `src/hooks/useMetrics.ts` + ProfilePage Journey card (7 tests), `src/components/chat/HealingPathCard.tsx` streak integration (17 tests), `src/lib/metricsSchema.ts`. **Filtered Vitest run: 269 passed** at epic merge; 3 stale duplicate suites deleted 2026-07-31 → 240/240 pass on current code.
- **Schema**: `backend/app/schemas.py` → package `backend/app/schemas/` (rename, all imports updated).
- **Infra**: idempotent migration `supabase/migrations/20260730000000_verify_rls_with_check.sql`; nightly workflow `.github/workflows/nightly-rls.yml`; `docs/RELEASE_READINESS_2026_07_30.md`.
- **Docs**: lessons.md, README.md, ROADMAP.md, CLAUDE.md, AGENTS.md, DEVELOPER_GUIDE.md all updated.

Dev servers currently running (session leftovers): backend uvicorn on `:8001`, Vite on `:8080` with `VITE_BACKEND_URL=http://localhost:8001`.

## 3. Files Actively Edited

Nothing actively in progress — epic complete. If continuing, the hot files are:

- `backend/app/config.py` — additive thresholds; `langhanam_voice_enabled` / `GURU_VOICE_MODE` gates
- `backend/services/healing_course_service.py`, `backend/services/guru_voice_langhanam.py` — new services
- `backend/rag/nodes/generation.py`, `backend/rag/nodes/guru_tone_adapter.py` — voice hook points
- `backend/app/api/metrics.py`, `backend/app/api/healing_course.py`, `backend/app/main.py` — new routers
- `src/components/chat/HealingPathCard.tsx`, `src/hooks/useMetrics.ts`, `src/pages/ProfilePage.tsx`
- `tests/e2e/security-aal2.spec.ts`, `tests/e2e/rls-cross-user.spec.ts`
- `.superpowers/sdd/*` — task briefs/reports/progress ledger (gitignored artifacts)

## 4. Tried and Failed

- **Backend boot on host**: `LLM_PROVIDER` validation error → root cause: untracked `backend/dotenv/` shim shadowed python-dotenv, silently killing `.env` load. **Fixed by deleting the shim** (commit `b7c65450`). Then docker hostnames (`qdrant:6333` etc.) failed DNS → fixed via env overrides.
- **Port 8000 occupied**: other project's Docker stack (tayari-skill-boost) maps host 8000. Ran backend on 8001 + `VITE_BACKEND_URL` override instead.
- **Docker engine died**: `kill -9` on a com.docker proxy (port holder) triggered full engine-VM restart (~5 min, all containers down). Recovered by relaunching Docker Desktop. Lesson recorded: never kill docker-proxy processes.
- **Vitest OOM**: worker crashes (`ERR_WORKER_OUT_OF_MEMORY`) on full suite. Retried with `--pool=forks`, `--maxWorkers=2`, `NODE_OPTIONS=--max-old-space-size=6144`; eventually completes (6GB heap + 3 workers). Pre-existing machine resource issue.
- **3 backend tests still fail** (env, not code): `test_embedding_no_double_prefix`, `test_embedding_service_ragatouille_optional_graceful_fallback`, `test_fail_closed_paths` — all depend on HF model revision `3a90cc8b42f5acec95e57c1e2433ba3b71ba9eef` which 404s on HuggingFace; untracked/pre-existing test files, not epic-touched. Embedding model fails to load at runtime too (degraded but non-critical for E2E).
- **8 vitest failures** confirmed pre-existing (legacy `src/test/*` paths; newer duplicate suites at `src/test/components/*` pass; e.g. jsdom `HTMLMediaElement.pause` not implemented). Not epic-caused.
- **Neo4j container** slow to become healthy after engine restart (`bolt://localhost:7687` unreachable briefly) — non-critical service (GraphRAG only).
- **Guru-voice benchmark degraded**: OpenRouter key returned 403 → rule-based run scored 5.0/5.0 on synthetic corpus but gate forced False; needs live LLM run.

## 5. Next Step

All epic work is merged; remaining items are **user/manual actions + pre-existing debt**, in priority order:

1. **Live-LLM guru-voice benchmark** → flip `langhanam_voice_enabled` if ≥4.0/5.0: `cd backend && .venv/bin/python benchmarks/guru_voice_benchmark.py` (needs working `OPENROUTER_API_KEY`).
2. **Enable leaked-password protection** (manual, Supabase Pro): Auth → Providers → Email → "Prevent the use of leaked passwords", then `backend/scripts/verify_leaked_password_protection.py`.
3. **Set GitHub repo secrets** `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` (prod) for `.github/workflows/nightly-rls.yml`; confirm ephemeral Alice/Bob cleanup on first prod run.
4. **Deploy to Railway** per `docs/RELEASE_READINESS_2026_07_30.md` (`railway up` tarball, 1 replica, `/api/healthz` + `/api/health` checks).
5. **Deferred**: HF revision pin fix for the 3 failing embedding tests; delete stale `src/test/*` duplicate suites; i18n `t()` coverage audit; 768–1024px responsive stress test (pre-release blockers 1–2 in AGENTS.md).
