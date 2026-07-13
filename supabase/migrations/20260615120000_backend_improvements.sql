-- Backend Improvements Migration: multi-device, bhakti analytics, push subs, pending extractions, daily teachings
-- 2026-06-15

-- ── 1. Multi-device session continuity ──
ALTER TABLE public.profiles
  ADD COLUMN IF NOT EXISTS last_conversation_id uuid REFERENCES public.conversations(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS last_message_id uuid REFERENCES public.chat_messages(id) ON DELETE SET NULL,
  ADD COLUMN IF NOT EXISTS last_active_at timestamptz;

CREATE OR REPLACE FUNCTION public.touch_user_last_message()
RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  UPDATE public.profiles
     SET last_conversation_id = NEW.conversation_id,
         last_message_id = NEW.id,
         last_active_at = now()
   WHERE id = NEW.user_id;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_touch_last_message ON public.chat_messages;
CREATE TRIGGER trg_touch_last_message
AFTER INSERT ON public.chat_messages
FOR EACH ROW EXECUTE FUNCTION public.touch_user_last_message();

CREATE OR REPLACE VIEW public.v_meditation_heatmap 
WITH (security_invoker = true) AS
SELECT user_id,
       date_trunc('day', started_at)::date AS day,
       COUNT(*) AS sessions,
       COALESCE(SUM(duration_seconds), 0) AS seconds
FROM public.meditation_sessions
GROUP BY 1, 2;

CREATE OR REPLACE FUNCTION public.meditation_streak(p_user uuid)
RETURNS int LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  WITH days AS (
    SELECT DISTINCT date_trunc('day', started_at)::date d
    FROM public.meditation_sessions WHERE user_id = p_user
  ), s AS (
    SELECT d, d - (row_number() OVER (ORDER BY d))::int AS grp FROM days
  )
  SELECT COALESCE(MAX(cnt), 0) FROM (SELECT COUNT(*) cnt FROM s GROUP BY grp) z;
$$;

-- ── 3. Web Push subscriptions ──
CREATE TABLE IF NOT EXISTS public.push_subscriptions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  endpoint text NOT NULL UNIQUE,
  p256dh text NOT NULL,
  auth text NOT NULL,
  created_at timestamptz DEFAULT now()
);
GRANT SELECT, INSERT, DELETE ON public.push_subscriptions TO authenticated;
GRANT ALL ON public.push_subscriptions TO service_role;
ALTER TABLE public.push_subscriptions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "self" ON public.push_subscriptions;
CREATE POLICY "self" ON public.push_subscriptions FOR ALL
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- ── 4. Daily teachings for push ──
CREATE TABLE IF NOT EXISTS public.daily_teachings (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  caption text NOT NULL,
  image_url text,
  publish_date date NOT NULL DEFAULT CURRENT_DATE,
  created_at timestamptz DEFAULT now()
);
GRANT SELECT ON public.daily_teachings TO authenticated;
GRANT ALL ON public.daily_teachings TO service_role;
ALTER TABLE public.daily_teachings ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "daily_teachings_public" ON public.daily_teachings;
CREATE POLICY "daily_teachings_public" ON public.daily_teachings FOR SELECT USING (true);

-- ── 5. Memory-extract background job ──
CREATE TABLE IF NOT EXISTS public.pending_extractions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  conversation_id uuid,
  message_id uuid,
  payload jsonb NOT NULL DEFAULT '{}',
  status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','processing','done','failed')),
  attempts int NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz DEFAULT now(),
  processed_at timestamptz
);
CREATE INDEX IF NOT EXISTS idx_pending_extractions_status_created
  ON public.pending_extractions (status, created_at);
GRANT SELECT, INSERT, UPDATE ON public.pending_extractions TO service_role;
ALTER TABLE public.pending_extractions ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "pending_extractions_self" ON public.pending_extractions;
CREATE POLICY "pending_extractions_self" ON public.pending_extractions FOR ALL
  USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid());

-- ── 6. Cron schedules (run manually via Supabase SQL Editor after deploy) ──
-- See docs/IMPROVEMENTS_BACKEND.md for the exact SELECT cron.schedule(...) blocks
