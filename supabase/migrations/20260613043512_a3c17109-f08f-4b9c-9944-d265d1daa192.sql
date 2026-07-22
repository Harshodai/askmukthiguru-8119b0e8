
-- 1. Fix match_user_memories: drop p_user_id, scope to auth.uid()
DROP FUNCTION IF EXISTS public.match_user_memories(uuid, vector, int, float);

CREATE OR REPLACE FUNCTION public.match_user_memories(
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
  IF auth.uid() IS NULL THEN
    RAISE EXCEPTION 'not_authenticated';
  END IF;
  RETURN QUERY
  SELECT m.id, m.content,
    (1 - (m.embedding <=> p_query_embedding))::float AS similarity
  FROM public.guru_memories m
  WHERE m.user_id = auth.uid()
    AND (1 - (m.embedding <=> p_query_embedding)) >= p_min_sim
  ORDER BY m.embedding <=> p_query_embedding
  LIMIT p_k;
END;
$$;

REVOKE EXECUTE ON FUNCTION public.match_user_memories(vector, int, float) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_user_memories(vector, int, float) TO authenticated;

-- 2. Restrict kb_chunks and kb_sources reads to authenticated users
DROP POLICY IF EXISTS "kb_chunks_select" ON public.kb_chunks;
DROP POLICY IF EXISTS "Anyone can read kb_chunks" ON public.kb_chunks;
DROP POLICY IF EXISTS "Public can read kb_chunks" ON public.kb_chunks;
CREATE POLICY "kb_chunks_select_authenticated" ON public.kb_chunks
  FOR SELECT TO authenticated USING (true);

DROP POLICY IF EXISTS "kb_sources_select" ON public.kb_sources;
DROP POLICY IF EXISTS "Anyone can read kb_sources" ON public.kb_sources;
DROP POLICY IF EXISTS "Public can read kb_sources" ON public.kb_sources;
CREATE POLICY "kb_sources_select_authenticated" ON public.kb_sources
  FOR SELECT TO authenticated USING (true);

REVOKE SELECT ON public.kb_chunks FROM anon;
REVOKE SELECT ON public.kb_sources FROM anon;

-- 3. Revoke EXECUTE on internal SECURITY DEFINER helpers from anon/public
REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;

REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO authenticated;

REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;

REVOKE EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) TO authenticated;

REVOKE EXECUTE ON FUNCTION public.promote_admin_by_email(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.promote_admin_by_email(text) TO authenticated;

REVOKE EXECUTE ON FUNCTION public.list_admins() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.list_admins() TO authenticated;

REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.seed_admin_demo() TO authenticated;

DROP FUNCTION IF EXISTS public.match_kb_chunks(vector, integer, double precision) CASCADE;
