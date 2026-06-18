-- ============================================================================
-- DB Consolidation: consolidate cost_tracking + prompt_store into Supabase
-- ============================================================================

-- 1. token_usage table (replaces SQLite cost_tracking.db)
CREATE TABLE IF NOT EXISTS public.token_usage (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id TEXT NOT NULL DEFAULT 'default',
  user_id TEXT NOT NULL DEFAULT '',
  session_id TEXT NOT NULL DEFAULT '',
  model TEXT NOT NULL DEFAULT '',
  provider TEXT NOT NULL DEFAULT 'ollama',
  tokens_in INTEGER NOT NULL DEFAULT 0,
  tokens_out INTEGER NOT NULL DEFAULT 0,
  cost_usd NUMERIC NOT NULL DEFAULT 0.0,
  endpoint TEXT DEFAULT '/api/chat',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT ON public.token_usage TO authenticated;
GRANT ALL ON public.token_usage TO service_role;

ALTER TABLE public.token_usage ENABLE ROW LEVEL SECURITY;

CREATE POLICY "admins read token_usage"
  ON public.token_usage FOR SELECT
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "service_role manage token_usage"
  ON public.token_usage FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

CREATE INDEX IF NOT EXISTS idx_token_usage_tenant_created
  ON public.token_usage(tenant_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_token_usage_user_created
  ON public.token_usage(user_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_token_usage_created_at
  ON public.token_usage(created_at DESC);

-- 2. Add missing columns to prompt_versions (description, author)
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS author TEXT DEFAULT 'system';

-- Convert version from INTEGER to TEXT for semver support ("1.0.0")
ALTER TABLE public.prompt_versions ALTER COLUMN version TYPE TEXT
  USING version::TEXT;

-- 3. Fix RLS on conversation_memories – allow service_role full access
ALTER TABLE public.conversation_memories ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "service_role manage conversation_memories" ON public.conversation_memories;
CREATE POLICY "service_role manage conversation_memories"
  ON public.conversation_memories FOR ALL
  TO service_role
  USING (true) WITH CHECK (true);

-- Allow authenticated users to read their own memories
DROP POLICY IF EXISTS "users read own conversation_memories" ON public.conversation_memories;
CREATE POLICY "users read own conversation_memories"
  ON public.conversation_memories FOR SELECT
  TO authenticated
  USING (auth.uid() = user_id);

-- Allow authenticated users to insert their own memories
DROP POLICY IF EXISTS "users insert own conversation_memories" ON public.conversation_memories;
CREATE POLICY "users insert own conversation_memories"
  ON public.conversation_memories FOR INSERT
  TO authenticated
  WITH CHECK (auth.uid() = user_id);

-- 4. Fix FK violation: guru_session_summaries should allow NULL user_id for anonymous
ALTER TABLE public.guru_session_summaries
  ALTER COLUMN user_id DROP NOT NULL;

-- 5. Add missing columns to feedback_events for full feedback storage
ALTER TABLE public.feedback_events ADD COLUMN IF NOT EXISTS query_text TEXT DEFAULT '';
ALTER TABLE public.feedback_events ADD COLUMN IF NOT EXISTS answer_text TEXT DEFAULT '';
ALTER TABLE public.feedback_events ADD COLUMN IF NOT EXISTS feedback_text TEXT DEFAULT '';
ALTER TABLE public.feedback_events ADD COLUMN IF NOT EXISTS metadata_json JSONB DEFAULT '{}'::jsonb;

GRANT ALL ON public.feedback_events TO service_role;

-- Force reload of PostgREST schema cache
NOTIFY pgrst, 'reload schema';
