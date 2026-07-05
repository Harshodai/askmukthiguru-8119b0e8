-- Fix: match_user_memories_by_user — service-role safe variant
-- The existing match_user_memories uses auth.uid() which requires a user JWT.
-- The backend uses the service role key and cannot set auth.uid().
-- This new function accepts p_user_id explicitly, safe for service-role calls.

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
  SELECT m.id, m.content,
    (1 - (m.embedding <=> p_query_embedding))::float AS similarity
  FROM public.guru_memories m
  WHERE m.user_id = p_user_id
    AND (1 - (m.embedding <=> p_query_embedding)) >= p_min_sim
  ORDER BY m.embedding <=> p_query_embedding
  LIMIT p_k;
END;
$$;

-- Grant to service_role (backend calls) and authenticated (direct client calls)
REVOKE EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, vector, int, float) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, vector, int, float) TO service_role;
GRANT EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, vector, int, float) TO authenticated;
