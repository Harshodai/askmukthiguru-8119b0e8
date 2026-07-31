# Task 13 Report: Verify RLS migration completeness

## Brief summary
Create an idempotent migration that guarantees four UPDATE row-level security policies on `conversations`, `chat_messages`, `meditation_sessions`, and `user_profiles` include both `USING` and `WITH CHECK` ownership clauses. The migration must be a no-op if migration `20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql` already applied them correctly.

## Environment
- Working directory: `/Users/harshodaikolluru/Public/askmukthiguru-8119b0e8`
- Branch: `security-rls-metrics-release-readiness-2026-07-30`
- PostgreSQL syntax validation: `supabase/postgres:15.1.1.76` Docker image

## Commands run

### 1. Read referenced migration
```bash
cat supabase/migrations/20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql
```
Confirmed it already defines the four UPDATE policies with `USING` and `WITH CHECK`.

### 2. SQL syntax validation
```bash
export PATH="/Users/harshodaikolluru/.docker/bin:$PATH"
docker run --rm -v ... supabase/postgres:15.1.1.76 sh -c "initdb ...; pg_ctl ... start; psql -U postgres -d postgres -f /tmp/verify.sql"
```
Output:
```
DO
```

## Code changes made
- Created `supabase/migrations/20260730000000_verify_rls_with_check.sql`
  - Anonymous `DO` block inspects `pg_policy.polqual` and `pg_policy.polwithcheck` for the four named policies.
  - Skips any policy that already has both `USING` and `WITH CHECK` set.
  - Otherwise `DROP POLICY IF EXISTS ...` then `CREATE POLICY ...` with the correct ownership expressions.
  - `chat_messages` uses the conversation-ownership subquery; all others use `user_id = auth.uid()`.

## Self-review
- [x] Migration filename matches brief exactly
- [x] Idempotent: skips matching policies, recreates only if `USING` or `WITH CHECK` is missing
- [x] No-op when `20260728103548_85070891-f7bf-4835-94db-4246463b3813.sql` is already applied
- [x] SQL syntax validated against Supabase Postgres 15 image
- [x] Only the required migration file was created; no unrelated files modified
- [x] Migration not applied locally per strict scope

## Status
DONE

## One-line summary
Created idempotent `20260730000000_verify_rls_with_check.sql` that ensures the four UPDATE RLS policies include both `USING` and `WITH CHECK`, with syntax validation passing on Supabase Postgres 15.
