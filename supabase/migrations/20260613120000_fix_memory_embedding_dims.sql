-- ============================================================================
-- REVERT: DESTRUCTIVE: this migration TRUNCATEs guru_memories — rows are already lost;
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- restore from backup if data mattered. Best-effort schema revert (back to the
-- 1024-dim shape that pre-dated it):
-- DROP INDEX IF EXISTS public.guru_memories_hnsw_idx;
-- ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS embedding;
-- ALTER TABLE public.guru_memories ADD COLUMN embedding vector(1024);
-- NOTE: match_user_memories was rewritten here to vector(768) and again to
-- vector(1024) by the next migration (20260613180000) — see that file's REVERT.
-- The live contract is 1024-dim; reverting requires a coordinated app rollback.
-- ============================================================================

-- Fix guru_memories embedding dimensions: 1024 → 768
-- Reason: the entire system uses google/gemini-embedding-001 with dimensions=768
-- (text-embedding-004 was shut down 2026-01-14; kb_chunks already uses vector(768))
-- No data migration needed — the write path was never live.

-- 1. Drop HNSW index (cannot alter column type with an index present)
DROP INDEX IF EXISTS public.guru_memories_hnsw_idx;

-- 2. Drop and recreate column (cast is not supported by pgvector)
TRUNCATE TABLE public.guru_memories;
ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS embedding;
ALTER TABLE public.guru_memories ADD COLUMN embedding vector(768) NOT NULL;

-- 3. Recreate HNSW index at correct dimensions
CREATE INDEX guru_memories_hnsw_idx
  ON public.guru_memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 4. Replace match_user_memories RPC with corrected vector dimension
DROP FUNCTION IF EXISTS public.match_user_memories(vector, int, float);
DROP FUNCTION IF EXISTS public.match_user_memories(uuid, vector, int, float);

CREATE OR REPLACE FUNCTION public.match_user_memories(
  p_query_embedding vector(768),
  p_k              int,
  p_min_sim        float
)
RETURNS TABLE (id uuid, content text, similarity float)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  -- Caller must be authenticated; RLS on guru_memories further scopes results.
  IF auth.uid() IS NULL THEN
    RAISE EXCEPTION 'not_authenticated';
  END IF;

  RETURN QUERY
  SELECT
    m.id,
    m.content,
    (1 - (m.embedding <=> p_query_embedding))::float AS similarity
  FROM public.guru_memories m
  WHERE m.user_id = auth.uid()
    AND (1 - (m.embedding <=> p_query_embedding)) >= p_min_sim
  ORDER BY m.embedding <=> p_query_embedding
  LIMIT p_k;
END;
$$;

-- Restrict to authenticated users only
REVOKE EXECUTE ON FUNCTION public.match_user_memories(vector, int, float) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.match_user_memories(vector, int, float) TO authenticated;

-- 5. Add DEFAULT auth.uid() for user_id to avoid NOT NULL and RLS insert failures when client doesn't pass user_id explicitly
ALTER TABLE public.guru_core_memory ALTER COLUMN user_id SET DEFAULT auth.uid();
ALTER TABLE public.guru_memories ALTER COLUMN user_id SET DEFAULT auth.uid();
ALTER TABLE public.guru_session_summaries ALTER COLUMN user_id SET DEFAULT auth.uid();
