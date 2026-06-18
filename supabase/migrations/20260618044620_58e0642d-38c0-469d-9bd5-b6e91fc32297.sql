
-- ============ guru_memories ============
CREATE TABLE IF NOT EXISTS public.guru_memories (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  content TEXT NOT NULL,
  embedding vector(384),
  source TEXT NOT NULL DEFAULT 'explicit' CHECK (source IN ('extracted','explicit')),
  claim TEXT,
  confidence DOUBLE PRECISION,
  decay_score DOUBLE PRECISION DEFAULT 1.0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.guru_memories TO authenticated;
GRANT ALL ON public.guru_memories TO service_role;
ALTER TABLE public.guru_memories ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_guru_memories_select" ON public.guru_memories FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "own_guru_memories_insert" ON public.guru_memories FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_guru_memories_update" ON public.guru_memories FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_guru_memories_delete" ON public.guru_memories FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS guru_memories_user_created_idx ON public.guru_memories (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS guru_memories_embedding_idx ON public.guru_memories USING hnsw (embedding vector_cosine_ops);

-- ============ guru_core_memory ============
CREATE TABLE IF NOT EXISTS public.guru_core_memory (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE REFERENCES auth.users(id) ON DELETE CASCADE,
  content TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.guru_core_memory TO authenticated;
GRANT ALL ON public.guru_core_memory TO service_role;
ALTER TABLE public.guru_core_memory ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_core_memory_select" ON public.guru_core_memory FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "own_core_memory_insert" ON public.guru_core_memory FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_core_memory_update" ON public.guru_core_memory FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_core_memory_delete" ON public.guru_core_memory FOR DELETE TO authenticated USING (auth.uid() = user_id);

-- ============ guru_session_summaries ============
CREATE TABLE IF NOT EXISTS public.guru_session_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  session_id UUID NOT NULL,
  summary TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.guru_session_summaries TO authenticated;
GRANT ALL ON public.guru_session_summaries TO service_role;
ALTER TABLE public.guru_session_summaries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_summaries_select" ON public.guru_session_summaries FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "own_summaries_insert" ON public.guru_session_summaries FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_summaries_update" ON public.guru_session_summaries FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_summaries_delete" ON public.guru_session_summaries FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE INDEX IF NOT EXISTS guru_summaries_user_created_idx ON public.guru_session_summaries (user_id, created_at DESC);

-- ============ chat_sessions ============
CREATE TABLE IF NOT EXISTS public.chat_sessions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_sessions TO authenticated;
GRANT ALL ON public.chat_sessions TO service_role;
ALTER TABLE public.chat_sessions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "own_chat_sessions_select" ON public.chat_sessions FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "own_chat_sessions_insert" ON public.chat_sessions FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "own_chat_sessions_delete" ON public.chat_sessions FOR DELETE TO authenticated USING (auth.uid() = user_id);
ALTER TABLE public.chat_sessions ADD COLUMN IF NOT EXISTS created_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE INDEX IF NOT EXISTS chat_sessions_user_created_idx ON public.chat_sessions (user_id, created_at DESC);

-- Touch trigger for updated_at on guru_memories + guru_core_memory
CREATE OR REPLACE FUNCTION public.touch_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql SET search_path = public AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END;
$$;
DROP TRIGGER IF EXISTS trg_guru_memories_touch ON public.guru_memories;
CREATE TRIGGER trg_guru_memories_touch BEFORE UPDATE ON public.guru_memories FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
DROP TRIGGER IF EXISTS trg_guru_core_touch ON public.guru_core_memory;
CREATE TRIGGER trg_guru_core_touch BEFORE UPDATE ON public.guru_core_memory FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
