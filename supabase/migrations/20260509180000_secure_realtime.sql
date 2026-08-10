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

-- 1. Enable RLS on the realtime.messages table (used for Broadcast/Presence)
ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;

-- 2. Allow authenticated users to subscribe to relevant topics
-- For Mukthi Guru, we allow authenticated users to listen to any topic for now,
-- but they MUST be authenticated.
CREATE POLICY "Authenticated users can subscribe" ON realtime.messages
FOR SELECT
TO authenticated
USING (true);

-- 3. Ensure daily_teachings RLS is enforced for realtime
ALTER TABLE public.daily_teachings ENABLE ROW LEVEL SECURITY;

-- Allow everyone to read teachings (since they are public wisdom)
-- but they only get realtime updates if they can select from the table.
CREATE POLICY "Public can read teachings" ON public.daily_teachings
FOR SELECT
USING (true);
