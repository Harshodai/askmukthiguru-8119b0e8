-- ============================================================================
-- REVERT: Drop the realtime.messages policy + RLS and the daily_teachings policy
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- NOTE: daily_teachings RLS itself was enabled by 20260506061859; disabling it
-- here would re-expose the table to anon — leave RLS enabled unless rolling back
-- past that migration too.
-- DROP POLICY IF EXISTS "Authenticated users can subscribe" ON realtime.messages;
-- ALTER TABLE realtime.messages DISABLE ROW LEVEL SECURITY;
-- DROP POLICY IF EXISTS "Public can read teachings" ON public.daily_teachings;
-- ============================================================================

-- Security Hardening: Restrict Supabase Realtime Subscriptions
-- This policy ensures that users can only subscribe to channels they are authorized for.

-- 1. Enable RLS on the realtime.messages table (used for Broadcast/Presence),
-- plus the policy scoping it to authenticated users.
--
-- Wrapped in exception handling: `realtime.messages` is owned by Supabase's
-- internal realtime-admin role, not by the role this migration runs as.
-- Hosted Supabase grants that role sufficient privilege — this statement has
-- already applied successfully there, tracked by version in
-- supabase_migrations.schema_migrations, so this edit has no effect on any
-- environment where it already ran. A fresh local `supabase start` does not
-- replicate that grant, so the bare ALTER TABLE failed with "must be owner
-- of table messages" and aborted the entire migration replay before it ever
-- reached later migrations. Catching insufficient_privilege makes local/DR
-- stack rebuilds resilient. See docs/operations/prod-readiness-remediation-2026-08-24.md.
DO $$
BEGIN
    ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;

    CREATE POLICY "Authenticated users can subscribe" ON realtime.messages
    FOR SELECT
    TO authenticated
    USING (true);
EXCEPTION
    WHEN insufficient_privilege THEN
        RAISE NOTICE 'Skipping realtime.messages RLS/policy — insufficient privilege on this environment (expected on a fresh local Supabase CLI stack; already applied on hosted).';
    WHEN duplicate_object THEN
        RAISE NOTICE 'realtime.messages policy already exists — skipping.';
END $$;

-- 3. Ensure daily_teachings RLS is enforced for realtime
ALTER TABLE public.daily_teachings ENABLE ROW LEVEL SECURITY;

-- Allow everyone to read teachings (since they are public wisdom)
-- but they only get realtime updates if they can select from the table.
CREATE POLICY "Public can read teachings" ON public.daily_teachings
FOR SELECT
USING (true);
