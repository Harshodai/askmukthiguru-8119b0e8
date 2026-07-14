## Scope

Execute Phases 2–4 from prior migration plan, end-to-end, in one build pass. Admin email already granted via trigger in Phase 1 — verify it here. Migration path already decided (Lovable Cloud + hybrid) — this plan is verification + optimization + i18n gap fill, not another migration.

## Phase A — i18n gap audit + batch translate (ruthless)

1. Run `scripts/find_keys_to_translate.py` for all 6 configured locales (en/hi/te/kn/ta/mr) plus add 6 new locales (bn/gu/ml/mr already/or/pa/ur) into `src/i18n.ts` resource map.
2. Grep `src/` for hardcoded English strings in JSX (`>Text<`, `placeholder="..."`, `title="..."`, `aria-label="..."`, `toast.*("...")`, `throw new Error("...")` user-facing) across:
  - `src/pages/**` (all 20+ pages including AuthPage, MFAChallengePage, Reset, Profile, Practices, KnowledgeGraph, SpiritGuides)
  - `src/components/chat/**`, `src/components/landing/**`, `src/components/meditation/**`, `src/components/auth/**`, `src/components/common/**`, `src/components/onboarding/**`
  - `src/admin/**` — flag as English-only-by-design (internal), do NOT translate unless user overrides
3. Extract missing keys → single `unique_english_strings.json` → batch translate via edge function using `google/gemini-2.5-flash` → write into 11 non-English locale JSON files.
4. Add missing locales to `src/i18n.ts` resources import block.
5. Verify `LanguageSelector` shows all 12 with correct native-script sizing (already fixed in prior turn — regression-check only).

## Phase B — Performance audit + fixes

1. `React.lazy` all admin pages (`src/admin/pages/*`) and heavy routes (`KnowledgeGraphPage`, `PracticeDetailPage`, `SpiritGuidesPage`, `MFAChallengePage`) in `src/App.tsx`. Wrap in `<Suspense fallback={<BrandedSpinner/>}>`.
2. Audit `useEffect` fetch chains in `ChatPage`, `ProfilePage`, `Index` (landing) — batch parallel Supabase calls where sequential, memoize expensive selectors.
3. Add `vite-imagetools` for hero/landing images; convert `.jpg` → `.webp` via import query params. Preload LCP image in `index.html`.
4. Run `supabase--slow_queries` → add indexes via migration if any query >100ms mean.
5. Vite bundle: verify `manualChunks` in `vite.config.ts` splits vendor (react, supabase, framer-motion, radix). Add if missing.
6. Remove unused deps flagged by `depcheck`-style ripgrep pass (skip auto-remove, list only).

## Phase C — Session/auth E2E verification via Playwright

Single script at `/tmp/browser/session-audit/`. Uses `LOVABLE_BROWSER_SUPABASE_*` env vars.

Scenarios:

1. Anonymous → `/chat` redirects to `/auth`.
2. Restore session → `/chat` loads user data.
3. Manually expire token in localStorage → next protected nav triggers SessionExpiredHandler toast + redirect.
4. Explicit signout → no toast, redirect to `/auth`.
5. Google OAuth button click → confirms redirect to `accounts.google.com` (stop before consent).
6. `/admin` with admin session → loads; without admin → redirects to `/admin/login`.

Screenshot each step. Report regressions in a `SESSION_AUDIT.md`.

## Phase D — Full-site i18n verification via Playwright

Script iterates through 12 languages. For each:

1. Set `localStorage.askmukthiguru_profile.preferredLanguage = <lang>`.
2. Visit `/`, `/auth`, `/chat`, `/profile`, `/practices`, `/privacy`, `/terms`.
3. Screenshot each. Log any node whose text matches `/^[A-Za-z ,.!?]+$/` and length >8 (likely untranslated English leaking through).
4. Output `I18N_AUDIT.md` with per-language leak count + screenshot links.

## Phase E — Admin access verification

1. Migration in Phase 1 auto-grants `kharshaengineer@gmail.com` admin on Google sign-in.
2. Playwright: sign in as this user → `/admin` → confirm renders (not redirected).
3. `supabase--read_query` on `user_roles` to confirm row exists post-signin (deferred until user actually signs in — document in report).

## Phase F — Migration decision confirmation doc

Write `MIGRATION_DECISION.md`:

- Yes, Lovable Cloud CAN run all 37 tables (schema-only migration already applied in Phase 1).
- Backend writes stay on old `ozmjeuqbholoxypfxixb` until Railway env vars flipped (per `RAILWAY_REWIRE.md`).
- Service-role gap: telemetry/embed must move into edge functions (already scaffolded: `admin-telemetry`, `memory-embed`, `ingest-source`).
- User action: flip Railway env vars when ready, then delete `ozmjeuqbholoxypfxixb` project.

## Files touched

- `src/i18n.ts` — add 6 locale imports.
- `src/locales/{bn,gu,ml,or,pa,ur}.json` — new files, translated.
- `src/locales/{hi,te,kn,ta,mr}.json` — filled gaps.
- `src/App.tsx` — `React.lazy` admin + heavy routes.
- `vite.config.ts` — `manualChunks` if missing, `vite-imagetools`.
- `index.html` — LCP preload.
- New `SESSION_AUDIT.md`, `I18N_AUDIT.md`, `MIGRATION_DECISION.md`, `PERF_AUDIT.md`.
- Possibly one migration for slow-query indexes.

## Out of scope

- Any change to `ozmjeuqbholoxypfxixb` project (user owns).
- Cloudflare DNS (user setting up in parallel).
- Sentry DSN wiring (needs user paste).
- Admin console UI translation (English-only by design).
- Custom Google OAuth credentials (managed OAuth already configured).

## Estimated: ~6-8 credits. Risk: low — verification-heavy, edits scoped to imports + lazy wrappers + locale files.  
  
Give to me in agent ready md files what needs to be done from user end 

Approve to build.