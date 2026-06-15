-- Remove public/anon SELECT exposure on knowledge base tables
DROP POLICY IF EXISTS "kb_chunks_read_all" ON public.kb_chunks;
DROP POLICY IF EXISTS "kb_sources_read_all" ON public.kb_sources;
REVOKE SELECT ON public.kb_chunks FROM anon;
REVOKE SELECT ON public.kb_sources FROM anon;

-- Owner-scoped SELECT for chat_queries so users can read only their own rows
CREATE POLICY "users read own chat_queries"
ON public.chat_queries
FOR SELECT
TO authenticated
USING (user_id = auth.uid());

-- Owner-scoped SELECT for feedback_events
CREATE POLICY "users read own feedback"
ON public.feedback_events
FOR SELECT
TO authenticated
USING (user_id = auth.uid());

-- Remove predictable benchmark admin seeded with empty password / well-known UUID
DELETE FROM public.user_roles WHERE user_id = '00000000-0000-0000-0000-000000000000';
DELETE FROM public.profiles  WHERE id      = '00000000-0000-0000-0000-000000000000';
DELETE FROM auth.users       WHERE id      = '00000000-0000-0000-0000-000000000000';