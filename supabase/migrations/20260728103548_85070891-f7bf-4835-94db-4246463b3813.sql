-- ============================================================================
-- REVERT: Restore pre-migration state: un-checked brain_touch() and USING-only UPDATE
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- policies. CAUTION: removing the WITH CHECK re-opens the owner-transfer risk
-- this migration closed — revert only deliberately.
-- CREATE OR REPLACE FUNCTION public.brain_touch(p_id text)
-- RETURNS void LANGUAGE sql SECURITY DEFINER SET search_path = public AS $$
--     update public.user_brain_nodes
--        set access_count = access_count + 1,
--            updated_at   = now()
--      where id = p_id;
-- $$;
-- REVOKE ALL ON FUNCTION public.brain_touch(text) FROM authenticated;
-- GRANT EXECUTE ON FUNCTION public.brain_touch(text) TO service_role;
-- DROP POLICY IF EXISTS own_conversations_update ON public.conversations;
-- CREATE POLICY own_conversations_update ON public.conversations
--   FOR UPDATE TO authenticated USING (user_id = auth.uid());
-- DROP POLICY IF EXISTS own_messages_update ON public.chat_messages;
-- CREATE POLICY own_messages_update ON public.chat_messages
--   FOR UPDATE TO authenticated
--   USING (conversation_id IN (SELECT c.id FROM public.conversations c WHERE c.user_id = auth.uid()));
-- DROP POLICY IF EXISTS own_sessions_update ON public.meditation_sessions;
-- CREATE POLICY own_sessions_update ON public.meditation_sessions
--   FOR UPDATE TO authenticated USING (user_id = auth.uid());
-- DROP POLICY IF EXISTS "Users can update their own profiles" ON public.user_profiles;
-- CREATE POLICY "Users can update their own profiles" ON public.user_profiles
--   FOR UPDATE TO authenticated USING (user_id = auth.uid());
-- ============================================================================

-- 1. Harden brain_touch: ownership check + revoke anon execute
CREATE OR REPLACE FUNCTION public.brain_touch(p_id text)
RETURNS void
LANGUAGE sql
SECURITY DEFINER
SET search_path TO 'public'
AS $$
    update public.user_brain_nodes
       set access_count = access_count + 1,
           updated_at   = now()
     where id = p_id
       and user_id = auth.uid()
       and auth.uid() is not null;
$$;

REVOKE ALL ON FUNCTION public.brain_touch(text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.brain_touch(text) TO authenticated, service_role;

-- 2. Add WITH CHECK to UPDATE policies so rows cannot be reassigned to other users
DROP POLICY IF EXISTS own_conversations_update ON public.conversations;
CREATE POLICY own_conversations_update ON public.conversations
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS own_messages_update ON public.chat_messages;
CREATE POLICY own_messages_update ON public.chat_messages
  FOR UPDATE TO authenticated
  USING (conversation_id IN (SELECT c.id FROM public.conversations c WHERE c.user_id = auth.uid()))
  WITH CHECK (conversation_id IN (SELECT c.id FROM public.conversations c WHERE c.user_id = auth.uid()));

DROP POLICY IF EXISTS own_sessions_update ON public.meditation_sessions;
CREATE POLICY own_sessions_update ON public.meditation_sessions
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());

DROP POLICY IF EXISTS "Users can update their own profiles" ON public.user_profiles;
CREATE POLICY "Users can update their own profiles" ON public.user_profiles
  FOR UPDATE TO authenticated
  USING (user_id = auth.uid())
  WITH CHECK (user_id = auth.uid());
