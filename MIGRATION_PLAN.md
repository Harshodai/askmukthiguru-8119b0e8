# Supabase Schema Migration Plan — Old → Lovable Cloud

**From:** `ozmjeuqbholoxypfxixb` (legacy, was on user Supabase)
**To:**   `fynkjimvuimakgtidvuq` (Lovable Cloud, managed)
**Strategy:** Schema-only, no user data. Start fresh. Old project retained read-only for 30 days as rollback safety.

---

## Table Inventory (37 tables)

Live on target already (verified via `supabase--read_query`):

```
alert_events           chat_queries          eval_runs             kb_sources
alert_rules            chat_responses        feedback_events       meditation_sessions
annotations            chat_sessions         golden_questions      model_pricing
app_logs               conversations         guru_core_memory      notes
assistant_access       daily_teachings       guru_memories         pending_extractions
assistants             eval_results          guru_session_summaries profiles
chat_messages          ingestion_runs        kb_chunks             prompt_versions
push_subscriptions     query_clusters        retrieval_events      safety_events
telemetry_events       trace_spans           trigger_events        user_profiles
user_roles
```

All 37 tables have RLS enabled and GRANTs applied (previous migration verified).

---

## Dependency Order (create in this order in an empty project)

```
1. Extensions:  pgcrypto, vector, pg_stat_statements
2. Enums:       app_role
3. Auth-independent: model_pricing, kb_sources, kb_chunks, prompt_versions,
                     golden_questions, query_clusters, alert_rules
4. Auth-referenced (FK to auth.users):
                profiles → user_roles → conversations → chat_messages
                notes, meditation_sessions, guru_memories, guru_core_memory,
                guru_session_summaries, chat_sessions, push_subscriptions,
                user_profiles, assistants, assistant_access
5. Telemetry (references auth.uid() in RLS only):
                chat_queries, chat_responses, retrieval_events, trace_spans,
                trigger_events, eval_runs, eval_results, feedback_events,
                annotations, safety_events, app_logs, telemetry_events,
                ingestion_runs, alert_events, pending_extractions,
                daily_teachings
6. Functions:   has_role, handle_new_user, ensure_profile_and_role,
                whoami_diagnostics, match_kb_chunks, match_user_memories,
                grant_admin_for_designated_emails, promote_admin_by_email,
                demote_admin_by_id, list_admins, touch_updated_at,
                kb_sources_touch_updated_at, update_conversation_updated_at
7. Triggers:    on_auth_user_created (handle_new_user + grant_admin_for_designated_emails)
                on_auth_user_confirmed (grant_admin_for_designated_emails)
                per-table BEFORE UPDATE for updated_at
```

---

## Dry-Run Procedure

The target project already has the schema. Verification, not creation, is the risk.

```bash
# Step 1 — Snapshot both schemas
node scripts/migration/verify.ts --emit-snapshot > /tmp/target.json

# Step 2 — Diff against reference snapshot committed in repo
diff -u scripts/migration/reference_schema.json /tmp/target.json

# Step 3 — Run the assert-only SQL block (safe, read-only)
psql "$SUPABASE_DB_URL" -f scripts/migration/dry_run.sql
```

Exit code 0 = safe to flip. Non-zero = do NOT proceed; investigate diff first.

---

## Environment Variable Switch Checklist

### Frontend (`.env.production`, already flipped)
| Variable | Value |
|---|---|
| `VITE_SUPABASE_URL` | `https://fynkjimvuimakgtidvuq.supabase.co` |
| `VITE_SUPABASE_PROJECT_ID` | `fynkjimvuimakgtidvuq` |
| `VITE_SUPABASE_PUBLISHABLE_KEY` | (Lovable Cloud anon key) |
| `VITE_BACKEND_URL` | Railway prod URL |
| `VITE_ALLOW_MOCK` | `false` |

### Railway backend (USER ACTION)
```
SUPABASE_URL=https://fynkjimvuimakgtidvuq.supabase.co
SUPABASE_ANON_KEY=<Lovable Cloud anon key>
SUPABASE_PUBLISHABLE_KEY=<same>
# SUPABASE_SERVICE_ROLE_KEY — NOT AVAILABLE on Lovable Cloud.
# All service-role writes MUST route through edge functions
# (admin-telemetry, memory-embed, ingest-source — already scaffolded).
```

### Post-flip smoke test
1. Sign in with `kharshaengineer@gmail.com` → visit `/admin/self-check` → all rows PASS.
2. Send one anonymous chat → verify no writes to `conversations` (anon path).
3. Sign in, send chat → verify row appears in `chat_messages`.
4. Hit backend `/api/chat` from Railway → verify JWT is accepted.

### Rollback
Flip Railway env back to old project; frontend `.env.production` still points to Lovable Cloud, so a fresh deploy is required to fully roll back. Old project remains untouched for 30 days.

---

## Service-Role Gap — Non-Negotiable

Lovable Cloud does NOT expose `SUPABASE_SERVICE_ROLE_KEY`. Any code path that bypassed RLS on the old project must move to an edge function that validates JWT + uses `SECURITY DEFINER` functions or per-request auth context.

**Already migrated:** `admin-telemetry`, `memory-embed`, `ingest-source`.
**To audit on Railway:** any FastAPI code doing `supabase.table(...)` with service-role key — those calls MUST become HTTP calls to edge functions or use anon key + RLS.

---

## Decision Gate

Proceed only when ALL are true:
- `verify.ts` reports 0 diffs vs reference snapshot.
- `dry_run.sql` exits 0.
- `/admin/self-check` shows all PASS for the admin email.
- Playwright session suite (`e2e/session.spec.ts`) passes on staging.
- Playwright i18n suite (`e2e/i18n.spec.ts`) passes for at least `en, hi, te` (top 3 locales).
