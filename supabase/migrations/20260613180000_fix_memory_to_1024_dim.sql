-- Fix guru_memories embedding dimensions: 768 → 1024
-- Reason: the system uses BAAI/bge-m3 (dense dim=1024) for ALL embeddings.
-- The previous migration to 768 was incorrect (google/gemini-embedding-001 was never
-- actually integrated into the backend embedding service).
-- Aligning memory layer to 1024-dim to match:
--   - Qdrant spiritual_wisdom collection (ingested with bge-m3, 1024-dim)
--   - embedding_service default: BAAI/bge-m3

-- 1. Drop HNSW index
DROP INDEX IF EXISTS public.guru_memories_hnsw_idx;

-- 2. Drop and recreate column
TRUNCATE TABLE public.guru_memories;
ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS embedding;
ALTER TABLE public.guru_memories ADD COLUMN embedding vector(1024) NOT NULL;

-- 3. Recreate HNSW index at correct dimensions
CREATE INDEX guru_memories_hnsw_idx
  ON public.guru_memories
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

-- 4. Replace match_user_memories RPC with correct 1024-dim signature
DROP FUNCTION IF EXISTS public.match_user_memories(vector, int, float);
DROP FUNCTION IF EXISTS public.match_user_memories(uuid, vector, int, float);

CREATE OR REPLACE FUNCTION public.match_user_memories(
  p_query_embedding vector(1024),
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

REVOKE EXECUTE ON FUNCTION public.match_user_memories(vector, int, float) FROM PUBLIC, anon;
GRANT  EXECUTE ON FUNCTION public.match_user_memories(vector, int, float) TO authenticated;
