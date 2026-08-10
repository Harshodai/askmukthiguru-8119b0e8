-- ============================================================================
-- REVERT: Drop user_episodes. DESTRUCTIVE: all episode logs are lost. NOTE: fails while
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- study_notebook_items.source_episode_id FK exists (added 20260630140000) —
-- drop that FK (or the items table) first:
-- -- ALTER TABLE public.study_notebook_items DROP CONSTRAINT IF EXISTS study_notebook_items_source_episode_id_fkey;
-- DROP TABLE IF EXISTS public.user_episodes;
-- ============================================================================

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