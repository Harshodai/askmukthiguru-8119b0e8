-- ============================================================================
-- REVERT: Drop the owner-scoped policies and restore anon kb grants. NOTE: the
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- kb_chunks_read_all / kb_sources_read_all policies dropped here (from
-- 20260605023720) and the benchmark-admin DELETEs are not restored — re-seed
-- from 20260516191000 only if the benchmark user must come back.
-- DROP POLICY IF EXISTS "users read own chat_queries" ON public.chat_queries;
-- DROP POLICY IF EXISTS "users read own feedback" ON public.feedback_events;
-- GRANT SELECT ON public.kb_chunks TO anon;
-- GRANT SELECT ON public.kb_sources TO anon;
-- ============================================================================

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