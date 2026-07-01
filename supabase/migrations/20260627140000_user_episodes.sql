-- Phase 2a: Episodic memory — raw query/answer/citation log per user.
-- Separate from guru_memories (which holds LLM-extracted facts with embeddings);
-- this is the verbatim turn log used for recent-episode retrieval and search.

CREATE TABLE IF NOT EXISTS public.user_episodes (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  query text NOT NULL,
  answer text NOT NULL,
  citations jsonb,
  intent text,
  created_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.user_episodes ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "users select own episodes" ON public.user_episodes;
CREATE POLICY "users select own episodes" ON public.user_episodes
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "users insert own episodes" ON public.user_episodes;
CREATE POLICY "users insert own episodes" ON public.user_episodes
  FOR INSERT WITH CHECK (auth.uid() = user_id);

CREATE INDEX IF NOT EXISTS user_episodes_user_created_idx
  ON public.user_episodes (user_id, created_at DESC);