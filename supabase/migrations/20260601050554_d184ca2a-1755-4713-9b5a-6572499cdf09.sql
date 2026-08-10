-- ============================================================================
-- REVERT: Drop the anon daily_teachings policy + grants and the realtime topic policies
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- NOTE: realtime.messages RLS stays enabled (20260509180000) — disable only when
-- rolling back past that migration too.
-- DROP POLICY IF EXISTS "anon_reads_active_daily_teachings" ON public.daily_teachings;
-- REVOKE SELECT ON public.daily_teachings FROM anon;
-- DROP POLICY IF EXISTS "realtime_daily_teachings_public" ON realtime.messages;
-- DROP POLICY IF EXISTS "realtime_admin_topics" ON realtime.messages;
-- DROP POLICY IF EXISTS "realtime_user_own_topics" ON realtime.messages;
-- ============================================================================


-- 1. Allow anon to read active daily teachings (landing page carousel)
CREATE POLICY "anon_reads_active_daily_teachings"
ON public.daily_teachings
FOR SELECT
TO anon
USING (expires_at > now());

GRANT SELECT ON public.daily_teachings TO anon;

-- 2. Lock down Realtime channel subscriptions
ALTER TABLE realtime.messages ENABLE ROW LEVEL SECURITY;

-- Allow everyone (anon + authenticated) to subscribe to the public daily-teachings topic
CREATE POLICY "realtime_daily_teachings_public"
ON realtime.messages
FOR SELECT
TO anon, authenticated
USING (
  (realtime.topic() = 'daily_teachings')
);

-- Admins can subscribe to admin-scoped topics (prefix 'admin:')
CREATE POLICY "realtime_admin_topics"
ON realtime.messages
FOR SELECT
TO authenticated
USING (
  realtime.topic() LIKE 'admin:%'
  AND public.has_role(auth.uid(), 'admin'::public.app_role)
);

-- Authenticated users can subscribe to their own user-scoped topics ('user:<uid>:...')
CREATE POLICY "realtime_user_own_topics"
ON realtime.messages
FOR SELECT
TO authenticated
USING (
  realtime.topic() LIKE ('user:' || auth.uid()::text || ':%')
);
