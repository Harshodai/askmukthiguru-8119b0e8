-- ============================================================================
-- Migration: 20261113000000_message_citations_owner_scoped_read.sql
-- Security audit 2026-11-13.
--
-- 1. message_citations_authenticated_read was USING (true), so any signed-in
--    user could read every user's citation rows (verbatim_text, video_id).
--    SELECT is now scoped to the owner of the cited message, via
--    chat_messages.id -> conversations.user_id = auth.uid().
-- 2. `authenticated` was granted INSERT but had no INSERT policy, so with RLS
--    enabled every browser insert (src/lib/chatStorage.ts) was denied and no
--    citation row could ever be stored. INSERT is now allowed for rows that
--    cite the caller's own messages, and for nothing else.
--
-- service_role keeps full access (message_citations_service_role_all).
--
-- REVERT:
-- DROP POLICY IF EXISTS "message_citations_owner_read" ON public.message_citations;
-- DROP POLICY IF EXISTS "message_citations_owner_insert" ON public.message_citations;
-- CREATE POLICY "message_citations_authenticated_read" ON public.message_citations
--     FOR SELECT TO authenticated USING (true);
-- ============================================================================

DROP POLICY IF EXISTS "message_citations_authenticated_read" ON public.message_citations;
DROP POLICY IF EXISTS "message_citations_owner_read" ON public.message_citations;
CREATE POLICY "message_citations_owner_read" ON public.message_citations
    FOR SELECT
    TO authenticated
    USING (
        message_id IN (
            SELECT m.id
            FROM public.chat_messages m
            JOIN public.conversations c ON c.id = m.conversation_id
            WHERE c.user_id = auth.uid()
        )
    );

DROP POLICY IF EXISTS "message_citations_owner_insert" ON public.message_citations;
CREATE POLICY "message_citations_owner_insert" ON public.message_citations
    FOR INSERT
    TO authenticated
    WITH CHECK (
        message_id IN (
            SELECT m.id
            FROM public.chat_messages m
            JOIN public.conversations c ON c.id = m.conversation_id
            WHERE c.user_id = auth.uid()
        )
    );
