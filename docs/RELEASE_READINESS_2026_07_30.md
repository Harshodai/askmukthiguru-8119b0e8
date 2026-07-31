# Release Readiness — AskMukthiGuru (2026-07-30)

**Product:** AskMukthiGuru — Lovable-generated React frontend, FastAPI backend (Railway), Supabase auth, Qdrant, Neo4j, Redis.
**Stack in one line:** `Vite/React` → `FastAPI (Railway, 1 replica)` → `Supabase (auth + Postgres)` · `Qdrant (vectors)` · `Neo4j (graph)` · `Redis (cache)`.

## Status summary

| Area | Status | Evidence |
|---|---|---|
| Railway deployment pipeline | ✅ Ready | Verified `railway up` tarball flow; health endpoints live (see checklist) |
| Backend env var coverage | ✅ Ready | Full list below; set on `askmukthiguru-8119b0e8` + `celery-worker` |
| Supabase leaked-password protection | 🟡 Conditional | Requires Pro plan + dashboard toggle; verifier script ready |
| RLS hardening | ✅ Ready | RLS on all tables; idempotent WITH CHECK migration applied; cross-user E2E + verifier |
| Lovable Cloud sync decision | ✅ Decided | Do NOT migrate backend (see section) |
| i18n `t()` coverage audit | ❌ Not ready | 8 of 14 languages fall back to English; hardcoded strings remain |
| Responsive stress test 768–1024px | ❌ Not ready | Weakest breakpoint band, not stress-tested |
| Google login E2E | ❌ Not ready | Spec exists, needs CI-injected OAuth test identities |
| Forgot-password E2E | ❌ Not ready | Partial (button/route/form); needs real-Supabase-email link test |
| Audio E2E (prod) | ❌ Not ready | Needs CDN-accessible asset, not `:8080` |

**Verdict:** infrastructure and security hardening are release-ready; frontend quality gates (i18n, responsive, auth E2E) are the remaining blockers.

---

## 1. Deployment checklist (Railway)

Project: `resilient-embrace` · Service: `askmukthiguru-8119b0e8` · Environment: `production`.

### 1.1 Pre-flight

- [ ] Backend builds locally with `backend/Dockerfile.railway` (builder `DOCKERFILE` in `railway.json`; start command `python start_railway.py`; restart policy `ON_FAILURE` max 5; draining 30s, overlap 10s; CPU 4000 / 16Gi limits).
- [ ] Docker CLI path exported for local commands: `export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"`.
- [ ] Railway CLI linked: `railway link --project resilient-embrace --service askmukthiguru-8119b0e8`.

### 1.2 Backend environment variables

Set on **both** `askmukthiguru-8119b0e8` and `celery-worker` (same Dockerfile). Values live in the Railway dashboard / `railway variables`; never in git.

| Variable | Required | Notes |
|---|---|---|
| `SUPABASE_URL` | ✅ | Must match frontend `VITE_SUPABASE_URL` (same project ref — split-brain guard) |
| `SUPABASE_KEY` | ✅ | service_role key, backend-only |
| `SUPABASE_ANON_KEY` | ✅ | anon key (used by verification scripts) |
| `QDRANT_URL` / `QDRANT_API_KEY` | ✅ | vector store |
| `REDIS_URL` | ✅ | cache + ephemeral memory TTL |
| `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD` | ✅ | knowledge graph (private network `*.railway.internal`) |
| `LLM_PROVIDER` | ✅ | `openrouter` (or `nim`) with matching `*_API_KEY`, `*_GENERATION_MODEL`, `*_CLASSIFY_MODEL` |
| `IS_PRODUCTION` | ✅ | `true` — also gates Swagger docs and test-auth backdoor |
| `JWT_SECRET` | ✅ | Supabase JWT secret |
| `CORS_ORIGINS` | ✅ | prod frontend origin(s) |
| `WEBSHARE_PROXY_URL` | 🟡 Optional | YouTube fetching (free tier) |
| `YOUTUBE_COOKIES_B64` / `YOUTUBE_COOKIES_FILE` | 🟡 Optional | logged-in YouTube cookies |
| `SUPADATA_API_KEY` | 🟡 Optional | transcript fallback |
| `FIREBASE_CREDENTIALS_JSON`, `APNS_KEY_ID`, `APNS_TEAM_ID`, `APNS_KEY_PATH`/`APNS_KEY_PEM`, `APNS_BUNDLE_ID` | 🟡 Optional | push notifications |

**Never set in production:** `ENABLE_TEST_AUTH=true`, `BENCHMARK_SECRET` (test-auth backdoor must stay disabled), `IS_PRODUCTION=false`.

### 1.3 Replicas

- [ ] **Replicas = 1** (Railway dashboard → scale, or `railway scale`). Do NOT run 2 — the second replica fails its init timeout on this service (see AGENTS.md Railway notes).

### 1.4 Deploy (tarball method)

```bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
railway link --project resilient-embrace --service askmukthiguru-8119b0e8
railway up
```

- Use `railway up` (tarball upload). **NOT** `railway redeploy --from-source` — it gets stuck at INITIALIZING on this repo.
- `railway up` skips when the tarball hash matches — make a real file change to force a build.
- Celery worker shares the same Dockerfile; deploy together (`SERVICE_TYPE=celery` variant).
- Do not run migrations through Railway; apply Supabase migrations via `npx supabase migration up` (or the dashboard SQL editor) before/after code deploy per release notes.

### 1.5 Health checks & verification

| Endpoint | Meaning |
|---|---|
| `/api/healthz` | Liveness — intercepted by `start_railway.py` wrapper; returns 200 during the 90s startup grace period |
| `/api/health` | Real readiness — `ready: false` until `startup_complete=True`; reflects Qdrant/Redis/Neo4j/Supabase health |

```bash
curl -s https://api.askmukthiguru.com/api/healthz      # {"status":"healthy",...}
curl -s https://api.askmukthiguru.com/api/health       # ready:true once startup completes
```

- [ ] `/api/healthz` returns 200 immediately after deploy.
- [ ] `/api/health` flips to `ready: true` (models/reranker loaded — allow warm-up; synchronous model imports must never run on the event loop, see `start_railway.py` `asyncio.to_thread` fix).
- [ ] Smoke: send one chat message and confirm a doctrine-grounded answer with citations.
- [ ] `railway logs` shows no `Vector dimension error` (embedding-dimension contract intact) and no crash-loop.

---

## 2. Lovable Cloud Sync Decision

**Decision:** Do not migrate the production backend to Lovable Cloud.
**Reason:** Lovable Cloud is a managed Supabase-compatible backend auto-generated by Lovable. AskMukthiGuru has a custom FastAPI backend, vector store (Qdrant), and graph database (Neo4j). Two-way sync between FastAPI and Lovable Cloud is not automatic; it requires manual REST/Realtime/edge-function plumbing. The risk of data drift and operational complexity outweighs the benefit.
**If Lovable is used:** Host only the frontend prototype on Lovable Cloud and point it at the existing Supabase Auth + FastAPI backend.

### Verified facts (Lovable docs, 2026-07)

- Lovable Cloud is a built-in backend (database, auth, storage, realtime, edge functions) for Lovable-hosted apps — https://docs.lovable.dev/features/cloud.
- **"At the moment, migration from Supabase to Cloud is not supported"** (Cloud FAQ). The Supabase integration docs say the same: *"There is no automatic migration in either direction"* — https://docs.lovable.dev/integrations/supabase.
- Edge functions are Deno/TypeScript request/response handlers (https://supabase.com/docs/guides/functions), **not a sync layer** — mirroring FastAPI service logic as edge functions is strictly more work and less capable (no service_role direct Postgres, no Qdrant/Neo4j sidecars on a private network, no Celery workers).
- This project is already wired to external Supabase project `ozmjeuqbholoxypfxixb`; Lovable Cloud is mutually exclusive with an external Supabase connection. Full tradeoff table: `docs/LOVABLE_CLOUD_AND_SUPABASE.md`.

### Guardrail

- [ ] One Supabase project remains the single source of truth: frontend uses anon key + RLS; backend uses service_role server-side only. Verify both point at the same project ref:
  ```bash
  grep -r "VITE_SUPABASE_URL" .env.production          # frontend target
  railway variables --service askmukthiguru-8119b0e8 | grep SUPABASE_URL   # backend target
  ```

---

## 3. Supabase leaked-password protection

> This feature requires the project to be on the **Pro plan or above**.

HIBP-based: Supabase checks new passwords against the HaveIBeenPwned k-anonymity API; no password ever leaves Supabase (verified in design spec §3.3).

### Dashboard steps

1. Open `https://supabase.com/dashboard/project/ozmjeuqbholoxypfxixb/auth/providers` (Authentication → Providers → Email).
2. Ensure the project is on **Pro plan or above**.
3. Toggle **Prevent the use of leaked passwords** to **ON**.
4. Verify manually: attempt to sign up with the password `password123`; expect rejection with `reasons: ["leaked_password"]`.

### Verification script

Run **only after** enabling the dashboard toggle:

```bash
cd backend
python3 scripts/verify_leaked_password_protection.py
```

Expected output: `{"ok": true}`. If the toggle is off, it prints `{"ok": false}` with the server response.

> **Release checklist item:** add "Supabase leaked-password protection enabled + script `ok:true`" as a gated checkbox in the release checklist (Section 7). This cannot be set from code — it is dashboard configuration.

---

## 4. RLS & security hardening (recently shipped)

- **RLS on all tables** — `supabase/migrations/20260711000000_enable_rls_on_all_tables.sql` (service_role bypasses RLS; anon/authenticated limited to policies).
- **Idempotent WITH CHECK verification** — `supabase/migrations/20260730000000_verify_rls_with_check.sql` re-creates the four UPDATE policies (`conversations`, `chat_messages`, `meditation_sessions`, `user_profiles`) with both `USING` and `WITH CHECK` ownership predicates; no-op if already correct.
- **Cross-user isolation verified** — `backend/scripts/verify_rls_policies.py` (Alice/Bob probes, 12 assertions) + `tests/e2e/rls-cross-user.spec.ts`.
- **AAL2/MFA** — `require_aal2` dependency + probe route; extended `tests/e2e/security-aal2.spec.ts`.
- **Security audit** — 93% pass; report at `scripts/security/report.md`.

**Status: ✅ Ready** for release. Nightly RLS CI (`nightly-rls.yml`) is scheduled to keep it that way.

---

## 5. Remaining pre-release items (from root AGENTS.md)

| # | Item | Current state | Blocker for GA? |
|---|---|---|---|
| 1 | **i18n `t()` coverage audit** — audit `t()` usage vs translation keys; add missing keys to the 6 real locales (`en, hi, te, kn, ta, mr`); 8 languages (`bn, gu, ml, ur, or, pa, as, sa`) fall back to English; hardcoded English strings still exist | In progress — `tests/e2e/i18n-coverage.spec.ts` exists | ✅ Yes (release blocker for multi-language promise) |
| 2 | **Responsive stress test 768–1024px** — full stress-test at every breakpoint; tablet band is the weakest, untested | Not done | ✅ Yes (mobile-first audience) |
| 3 | **Google login E2E** — dedicated OAuth test identities or isolated provider test app with CI-injected secrets; verify single redirect | Spec exists (`tests/e2e/google-auth-flow.spec.ts`); needs CI secrets | ✅ Yes (primary auth path) |
| 4 | **Forgot-password E2E** — real Supabase email: verify email sent + link works (expired-link path covered) | Partial — button/route/form render tested only | ✅ Yes |
| 5 | **Audio E2E on production** — STT/TTS against CDN-accessible asset, not `:8080` | Not done | 🟡 Should fix (audio is core feature) |

---

## 6. Rollback plan

### 6.1 Code rollback (primary — no code changes on our side)

Railway keeps every successful deployment; rollback restores **both the Docker image and custom variables** of the previously successful deployment (https://docs.railway.com/deployments/deployment-actions).

1. Railway dashboard → `askmukthiguru-8119b0e8` → **Deployments** → ⋯ on the last known-good deployment → **Rollback** (confirm).
2. Deployments older than the plan's retention policy cannot be rolled back (option hidden) — if so, redeploy from source: `railway up` after `git checkout <previous-stable-tag>` (or `railway redeploy` to re-run the latest code, https://docs.railway.com/cli/redeploy).
3. Verify: `/api/healthz` 200, `/api/health` `ready:true`, smoke chat, `railway logs` clean.
4. If the rollback was env-only (variables), no code rollback needed — `railway variables` + redeploy.

Full incident playbook: `docs/ROLLBACK_PLAN.md`.

### 6.2 RLS migration revert notes

RLS migrations are **additive and idempotent**; rolling back the *code* does not require reverting them, and reverting them is only for emergency data-plane remediation:

- `20260730000000_verify_rls_with_check.sql` — a `DO` block; re-running is a no-op when policies already have `USING` + `WITH CHECK`. To revert to looser policies, `DROP POLICY` and recreate the pre-existing definitions (captured in the migration file header for `20260728103548_*`).
- `20260711000000_enable_rls_on_all_tables.sql` — revert = `DROP POLICY <name>` for each added policy + `ALTER TABLE ... DISABLE ROW LEVEL SECURITY`. **Not recommended:** leaves tables exposed to anon/authenticated via the REST API. Only do this in a data-exposure emergency, and re-enable immediately after.
- **Never** roll back a Supabase migration that shipped data written under it (e.g., `user_course_progress`, second-brain vault) — schema-rollback plus retained rows causes constraint drift. Prefer forward-fix migrations.
- Local Supabase: `npx supabase migration up` / `down` manage the local DB only; production is the dashboard SQL editor or `supabase db push`.
- After any policy change in production, run `NOTIFY pgrst, 'reload schema';` (PGRST cache) and re-run `backend/scripts/verify_rls_policies.py`.

---

## 7. Go / no-go checklist (final gate)

- [ ] Deploy via `railway up`; replicas = 1
- [ ] `/api/healthz` + `/api/health` both green
- [ ] Supabase leaked-password protection ON + `verify_leaked_password_protection.py` → `{"ok": true}`
- [ ] RLS verifier passes against production-adjacent env (never with real user data)
- [ ] i18n `t()` audit complete — all 6 real locales covered
- [ ] Responsive stress test passes at 375 / 768 / 1024 / desktop
- [ ] Google login E2E green with CI secrets
- [ ] Forgot-password E2E green with real Supabase email
- [ ] Audio E2E green against CDN asset
- [ ] Rollback path identified (last-known-good deployment marked)

**Go when:** all above boxes ticked. **No-go until:** items 5.1–5.5 resolved.
