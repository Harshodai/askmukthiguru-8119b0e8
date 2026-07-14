# Plan: Full Production Migration + Audit

## Trade-offs: Lovable Cloud Supabase vs. your `ozmjeuqbholoxypfxixb` project

You asked "can Lovable Supabase handle everything?" — short answer: **yes for the frontend, with two caveats you need to accept.**

### What Lovable Cloud CAN do (equivalent to standalone Supabase)

- Postgres + pgvector (already enabled — `guru_memories`, `kb_chunks` use it)
- Auth: email/password, Google OAuth (managed, no client setup), Apple, Magic Link, MFA
- Edge Functions (Deno) — all 15 of yours port over 1:1
- Storage buckets (`daily-teachings` already exists)
- Row Level Security, roles, RPCs, triggers, cron via pg_cron
- Transactional + auth emails via Lovable Email (custom domain `askmukthiguru.com` when Cloudflare DNS is done)

### What's DIFFERENT (the caveats)

1. **No Supabase dashboard.** You manage via Lovable Cloud UI + me (migrations, secrets, logs). If you need raw SQL editor / advanced project settings not exposed in the Cloud UI, they don't exist here. For your use case (chat app, RAG, admin console) — fine.
2. **Service role key + DB password are not exposed.** Your Railway FastAPI backend currently uses `SUPABASE_SERVICE_ROLE_KEY` to write telemetry/embeddings. On Lovable Cloud, service-role work must happen inside **edge functions** (which have implicit service-role access), not from Railway. This is the biggest architectural implication:
  - **Option A**: Move telemetry/embed writes into edge functions your FastAPI calls (adds one HTTP hop, ~50ms).
  - **Option B**: Keep FastAPI on its own Supabase (`ozmjeuqbholoxypfxixb`) for backend writes only, and use Lovable Cloud purely for the frontend auth + user-facing tables. Two DBs, harder to keep in sync.
  - **Recommended: Option A** — cleaner, one source of truth.

### My recommendation

**Migrate everything to Lovable Cloud (schema-only, per your answer).** Rewire Railway to call new edge functions for admin/telemetry writes. You lose zero features, gain: managed Google OAuth, managed email, no `.env` juggling, faster prod deploys, unified admin.

Even I agree on Option A, since having a single source of truth is best.

---

## Execution scope (this session — "everything in one go")

### Phase 1 — Backend migration (Lovable Cloud Supabase = `fynkjimvuimakgtidvuq`)

1. **Port 40 tables** from `ozmjeuqbholoxypfxixb` → Lovable Cloud via one big migration file:
  - `profiles`, `user_roles`, `user_profiles`
  - `conversations`, `chat_messages`, `chat_queries`, `chat_responses`, `chat_sessions`
  - `assistants`, `assistant_access`, `assistant_configurations`, `assistant_doctrines`, `gurus`
  - `kb_sources`, `kb_chunks` (with pgvector)
  - `guru_memories`, `guru_core_memory`, `guru_session_summaries`, `conversation_memories`
  - `meditation_sessions`, `daily_teachings`, `notes`, `push_subscriptions`
  - `telemetry_events`, `trace_spans`, `retrieval_events`, `feedback_events`, `user_feedback`
  - `ingestion_runs`, `ingest_jobs`, `ingestion_checkpoints`, `token_usage`
  - `alert_rules`, `alert_events`, `annotations`, `app_logs`, `eval_runs`, `eval_results`, `golden_questions`, `model_pricing`, `pending_extractions`, `prompt_versions`, `query_clusters`, `safety_events`, `trigger_events`
  - Enum `app_role`, functions (`has_role`, `ensure_profile_and_role`, `match_kb_chunks`, `match_user_memories`, `promote_admin_by_email`, etc.)
  - All RLS policies + GRANTs in a single migration
2. **Grant admin to `kharshaengineer@gmail.com**` via `user_roles` (post-signup trigger handles user-record creation on first login).-> also add how can we add other admins as well with thorough 2 factor authentication and alo if possible any RSA Key.
3. **Update `.env` / `client.ts**` — Lovable auto-generates these; verify `VITE_SUPABASE_URL` points to `fynkjimvuimakgtidvuq.supabase.co`. and also see how we can do this to railway as well
4. **Enable Google OAuth** via managed Lovable Cloud provider (no Google Cloud Console step needed initially — your custom OAuth creds can be added later in Cloud → Auth Settings).
5. **Port edge functions** — verify all 15 in `supabase/functions/` still deploy on Lovable Cloud (they should — same Deno runtime).
6. **Document Railway rewiring** — I'll produce a `RAILWAY_REWIRE.md` with exact env var changes + new edge-function endpoints for backend writes. You update Railway when ready.

### Phase 2 — UX / i18n audit (Playwright end-to-end)

1. **Language selection propagation** — verify Hindi/Telugu/Tamil/Malayalam/Kannada/Bengali/Gujarati/Odia/Punjabi/Urdu/Assamese/Sanskrit render in native script at readable size across:
  - Landing page, Auth page, Chat page (header, input, messages, sidebar, thinking pills)
  - Profile, Practices, Meditation flow, Admin console
  - Toast messages, error banners, empty states
2. **Missing translation keys** — audit `src/i18n.ts` + `scripts/keys_to_translate_*.json`; fill gaps via Lovable AI Gateway (Gemini Flash) for the 12 non-English locales in one batch.
3. **Admin console i18n** — currently English-only; scope it to English (admin is internal, not seeker-facing) and document this decision.
4. **Chat UX regressions** — scroll behavior, message ordering, streaming cursor, session-expired handler, MFA challenge flow, Google One Tap.
5. **Landing page scroll fix verification** — confirm bottom sections reachable on 869×772 viewport (your current preview size).

### Phase 3 — Performance audit

1. **Bundle analysis** — run `vite build` and inspect chunks; lazy-load admin routes, meditation flow, knowledge graph.
2. **Route-level code splitting** — verify `React.lazy` on all admin pages (many aren't).
3. **Image optimization** — check `public/` for unoptimized PNGs, convert to WebP.
4. **Query batching** — audit `useAssistants`, `useProfile`, `useStudyNotebooks` for N+1 patterns.
5. **First-paint metrics** — Playwright + `performance.timing` on production build.
6. **Report** to `PERFORMANCE_AUDIT.md` with prioritized fixes; apply top 5 quick wins.

### Phase 4 — Prod-readiness checklist

- Sentry DSN placeholder → require you to paste it (`add_secret` for `VITE_SENTRY_DSN`).
- `robots.txt` + `sitemap.xml` sanity check.
- SEO meta on Auth / Practice / Profile pages.
- Email domain: I'll scaffold auth email templates but full DNS activation requires your Cloudflare setup for `askmukthiguru.com`.
- Publish button reminder at end.

---

## Deliverables

1. One large migration SQL (schema + RLS + grants + admin seed for `kharshaengineer@gmail.com`).
2. `RAILWAY_REWIRE.md` — env var + edge function endpoint changes for backend.
3. `PERFORMANCE_AUDIT.md` — findings + applied fixes.
4. `I18N_AUDIT.md` — coverage report + newly-translated keys.
5. Applied code changes: lazy loading, i18n key fills, UX regressions, admin route i18n scoping.
6. Playwright verification screenshots (landing scroll, language switch, admin login, chat streaming).

## Risks / your action items

- **After migration**: users on `ozmjeuqbholoxypfxixb` cannot log in until they re-signup (schema-only migration = fresh data).
- **Railway env vars**: you must update them per `RAILWAY_REWIRE.md` or backend telemetry breaks. I cannot touch Railway.
- **Cloudflare DNS for `askmukthiguru.com**`: parallel to this work; email templates activate once DNS is verified.
- **Custom Google OAuth**: managed OAuth works immediately for `*.lovable.app`. For your custom domain, you'll add authorized redirect URLs once Cloudflare + custom domain in Lovable are hooked up.

## Estimated credits: ~12-15

- Migration + edge fn port: 3
- i18n audit + fills: 3
- Perf audit + fixes: 3
- Playwright E2E verification: 2
- Admin seed + auth verification: 1
- Docs (RAILWAY_REWIRE, I18N, PERF): 2

Approve to proceed with all phases