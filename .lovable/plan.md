# Production Readiness Plan — Migration, Perf, i18n, Session, Admin

## Scope
Six deliverables in one pass. Each has a concrete artifact and an automated verification step.

---

## 1. Supabase Schema Migration Plan (with dry-run)

**Artifact:** `MIGRATION_PLAN.md` + `scripts/migration/dry_run.sql` + `scripts/migration/verify.ts`

Contents:
- Table inventory (37 tables from old `ozmjeuqbholoxypfxixb` → Lovable Cloud `fynkjimvuimakgtidvuq`).
- Dependency order (auth-referenced tables last: `profiles`, `user_roles`, `conversations`, `chat_messages`, ...).
- Per-table checklist: columns, FKs, indexes, RLS policies, GRANTs.
- **Dry-run SQL**: `BEGIN; ... ROLLBACK;` block that recreates schema on Lovable Cloud in a savepoint, verifies constraints via `information_schema`, then rolls back.
- **Verifier** (`verify.ts`): connects to both projects, diffs `pg_catalog` for tables/columns/policies/grants, prints a pass/fail table.
- Env-var switch checklist: `.env.production`, Railway (`SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_PUBLISHABLE_KEY`), and confirmation that `service_role` gap is covered by existing edge functions.
- Decision gate: run `verify.ts` → 100% pass → flip Railway env → smoke test → decommission old project.

## 2. Prod-Readiness Assessment for Railway Backend

**Artifact:** `PROD_READINESS_FINAL.md`

Covers the user's target stack:
- **Backend (FastAPI) on Railway**: env vars, healthcheck, autoscale settings, cold-start budget.
- **Redis / Neo4j / Qdrant on Railway**: managed vs self-hosted trade-offs, persistent volume sizing, backup cadence.
- **AI models via API (no local Ollama)**: provider matrix (OpenRouter / Sarvam / Lovable AI Gateway), fallback chain, per-request timeout budget targeting <3s p95.
- **Frontend on Lovable**: CDN cache headers, lazy routes, prefetch strategy.
- Verdict: **GO / NO-GO** per component with blockers listed.

## 3. Frontend Performance Instrumentation

**Artifact:** `src/lib/webVitals.ts` + wired into `src/main.tsx` + Sentry integration.

- Install `web-vitals` package.
- Report LCP, INP, CLS, FCP, TTFB to Sentry via `Sentry.captureMessage` with `level: 'info'` + custom tags (`route`, `connection.effectiveType`, `deviceMemory`).
- Add navigation-timing breakdown (DNS, TCP, TTFB, DOM, load) as Sentry breadcrumbs.
- Route-change marks via React Router listener.
- **Latency fixes shipped this pass**:
  - `React.lazy` every admin page + heavy landing sections (already partially done — extend to `SpiritGuidesPage`, `PracticesPage`, `PracticeDetailPage`).
  - `vite.config.ts`: `manualChunks` (react, supabase, radix, framer-motion, i18n).
  - Preload LCP image (`<link rel="preload" as="image">`) in `index.html`.
  - Debounce `useProfile` refetch; consolidate N+1 `useEffect` fetches in `ChatPage`.

## 4. Admin Permission Self-Check

**Artifact:** `src/pages/AdminSelfCheck.tsx` (route `/admin/self-check`) + edge function `admin-self-check`.

- Page calls `whoami_diagnostics()` RPC (already exists) and renders a checklist: authenticated ✓, profile present ✓, roles [], is_admin ✓/✗.
- Verifies `kharshaengineer@gmail.com` grant works end-to-end (checks trigger fired, both `admin` and `user` rows present, RLS test query against `admin`-gated table).
- Automated Playwright test asserts the checklist all-green after Google sign-in.

## 5. Playwright E2E — i18n Coverage (all 14 locales × all routes)

**Artifact:** `e2e/i18n.spec.ts` + `e2e/fixtures/routes.ts`

- Enumerate every route (`/`, `/auth`, `/chat`, `/profile`, `/practices`, `/practices/:id`, `/spirit-guides`, `/privacy`, `/terms`, `/admin/*`, `/auth/callback`).
- For each of 14 languages (`en, hi, te, kn, ta, mr, bn, gu, ml, ur, or, pa, as, sa`):
  1. Set locale via `LanguageSelector`.
  2. Visit each route (authenticated where required, via seeded session).
  3. Assert no visible node matches `/^[A-Za-z][A-Za-z ,.!?'"-]{8,}$/` for non-English locales (untranslated leak).
  4. Screenshot each route → `test-results/i18n/<lang>/<route>.png`.
- Report: `test-results/i18n-report.html` with pass/fail per (lang, route) cell.
- **Also fills missing translation keys** in `src/locales/*.json` via Lovable AI (`google/gemini-2.5-flash`) batch translate before running the suite.

## 6. Playwright E2E — Session/Auth Regression Suite

**Artifact:** `e2e/session.spec.ts`

- **Login**: Google OAuth via `lovable.auth.signInWithOAuth` (mocked provider on CI, real in staging).
- **Refresh**: Reload page, assert session persists via `@capacitor/preferences`-backed storage.
- **Logout**: `supabase.auth.signOut()` → assert redirect to `/auth`, no stale tokens in storage.
- **Token expiry**: Force-expire access token, hit protected route, assert silent refresh via refresh_token OR redirect to `/auth` if refresh_token invalid.
- **Protected routes**: Anonymous → `/profile`, `/chat` (auth-required), `/admin/*` → assert redirect with `redirectTo` param preserved.
- Runs in CI on every PR; blocking.

---

## Execution Order

```text
Step 1  Install deps (web-vitals, @playwright/test if missing)
Step 2  Write MIGRATION_PLAN.md + dry_run.sql + verify.ts   [artifact only]
Step 3  Write PROD_READINESS_FINAL.md                        [artifact only]
Step 4  Ship webVitals.ts + wire Sentry + code splits + preload
Step 5  Ship AdminSelfCheck page + route
Step 6  Fill missing i18n keys (batch translate 13 locales)
Step 7  Write e2e/i18n.spec.ts + e2e/session.spec.ts
Step 8  Run Playwright locally against http://localhost:8080, fix leaks
Step 9  Commit + report pass/fail matrix
```

## Out of Scope (explicit)
- Cloudflare DNS setup for `askmukthiguru.com` — user action, documented only.
- Railway env var flip — user action, documented only.
- Migrating actual user data — schema-only per prior decision.
- Admin console UI translation — English-only by design (prior decision).

## Estimated Cost
~8–10 credits (heaviest: Playwright runs across 14 langs × ~12 routes = 168 screenshots, plus batch translation of ~100 keys × 13 locales).

## Risk
Medium. Playwright suite may reveal 50+ i18n leaks that need manual key extraction. Mitigation: cap first pass at top 20 leaks per language, file rest as follow-ups.
