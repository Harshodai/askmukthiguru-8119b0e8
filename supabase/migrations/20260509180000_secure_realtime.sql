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
