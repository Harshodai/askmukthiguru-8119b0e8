
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
