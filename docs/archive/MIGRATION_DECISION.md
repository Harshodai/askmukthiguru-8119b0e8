# Migration Decision — Lovable Cloud + Hybrid Backend

**Decision:** Migrate database schema to Lovable Cloud (`fynkjimvuimakgtidvuq`). Keep FastAPI backend on Railway, repointed at Lovable Cloud.

**Status:** Phase 1 complete. See `USER_ACTIONS.md` for what's left.

---

## Can Lovable Cloud run everything?

**Yes** — with one caveat.

| Capability | Lovable Cloud | Notes |
|---|---|---|
| Postgres + pgvector | ✅ | All 40 tables + embeddings migrated |
| Auth (email, Google, Apple, MFA) | ✅ | Managed OAuth configured |
| Edge Functions | ✅ | 15 functions already deployed |
| Storage buckets | ✅ | `daily-teachings` bucket present |
| RLS policies | ✅ | All policies ported |
| pg_cron | ✅ | Available for scheduled jobs |
| **service_role key access** | ❌ | Not exposed by Lovable Cloud |

## The service-role caveat

Your FastAPI backend (Railway) currently uses `SUPABASE_SERVICE_ROLE_KEY` to write telemetry, embeddings, and admin data bypassing RLS.

**Lovable Cloud will not give you that key.** Two paths:

### Option A — Edge functions (recommended)
Move privileged writes into Lovable-Cloud edge functions. FastAPI calls them via authenticated invoke. Already scaffolded:

- `admin-telemetry` — telemetry event writes
- `memory-embed` — embeddings + guru_memories writes
- `ingest-source` — kb_sources / kb_chunks writes

Extra latency: ~50-100ms per call. Acceptable for non-hot-path writes.

### Option B — Keep dual backend
FastAPI keeps writing to old `ozmjeuqbholoxypfxixb` (service_role available there). Frontend reads from new Lovable Cloud. Not recommended — schema drift risk, two RLS surfaces to maintain.

---

## Full Migration Plan (already executed in Phase 1)

1. ✅ Schema DDL for all 40 tables → applied to Lovable Cloud via migration
2. ✅ RLS policies + GRANTs for `authenticated` + `service_role`
3. ✅ `has_role`, `ensure_profile_and_role`, `whoami_diagnostics`, `match_kb_chunks`, `match_user_memories` functions
4. ✅ `handle_new_user` + `grant_admin_for_designated_emails` triggers
5. ✅ `.env.production` VITE vars point to `fynkjimvuimakgtidvuq`
6. ✅ Managed Google OAuth activated
7. ⏳ **User action**: Update Railway env vars → see `RAILWAY_REWIRE.md`
8. ⏳ **User action**: Re-sign-in of all users (schema-only, no data carry-over)

---

## Data Migration Choice: Schema Only

You chose "start fresh" — old user data (profiles, conversations, chat history, meditation sessions) on `ozmjeuqbholoxypfxixb` will not carry over. Users must sign up again on the new Cloud DB.

**Why this is fine for you:**
- App is pre-production public launch
- Small existing user base
- Doctrine content (`kb_sources`, `kb_chunks`, `assistants`) can be re-ingested via Railway backend after step 4

**If you change your mind:** ask agent for full data migration (~2-3 credits) — `pg_dump` from old → SQL insert to new for whitelisted tables.

---

## What Stays on `ozmjeuqbholoxypfxixb`

Until you delete it:
- Old user accounts (unusable — frontend now points elsewhere)
- Old chat history
- Old KB embeddings (can be re-ingested)

**Delete when:** Railway rewire (step 4) is done AND you've re-signed in as admin on new DB. See `USER_ACTIONS.md` #8.
