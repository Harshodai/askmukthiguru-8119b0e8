-- Deterministic memory conflict resolution.
-- New values for the same fact_key close the prior active row by valid_to;
-- cosine similarity remains a retrieval signal, never a contradiction signal.

ALTER TABLE public.guru_memories
  ADD COLUMN IF NOT EXISTS fact_key text,
  ADD COLUMN IF NOT EXISTS valid_from timestamptz,
  ADD COLUMN IF NOT EXISTS valid_to timestamptz;

UPDATE public.guru_memories
SET valid_from = COALESCE(valid_from, created_at)
WHERE valid_from IS NULL;

CREATE INDEX IF NOT EXISTS guru_memories_active_fact_key_idx
  ON public.guru_memories (user_id, fact_key)
  WHERE valid_to IS NULL AND fact_key IS NOT NULL;

DROP FUNCTION IF EXISTS public.match_user_memories_by_user(uuid, vector, integer, double precision);

CREATE OR REPLACE FUNCTION public.match_user_memories_by_user(
  p_user_id uuid,
  p_query_embedding vector(1024),
  p_k int,
  p_min_sim float
)
RETURNS TABLE (id uuid, content text, similarity float)
LANGUAGE plpgsql
STABLE
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF p_user_id IS NULL THEN
    RAISE EXCEPTION 'user_id_required';
  END IF;

  RETURN QUERY
  SELECT
    m.id,
    m.content,
    (1 - (m.embedding <=> p_query_embedding))::float AS similarity
  FROM public.guru_memories m
  WHERE m.user_id = p_user_id
    AND m.valid_to IS NULL
    AND (1 - (m.embedding <=> p_query_embedding)) >= p_min_sim
  ORDER BY m.embedding <=> p_query_embedding
  LIMIT p_k;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, vector, integer, double precision) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, vector, integer, double precision) TO service_role, authenticated;

NOTIFY pgrst, 'reload schema';
