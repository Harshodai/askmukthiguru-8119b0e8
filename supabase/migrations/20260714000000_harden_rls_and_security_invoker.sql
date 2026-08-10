-- ============================================================================
-- REVERT: Restore the non-security_invoker view definitions. The okf_review_queue
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- policy was recreated with an identical predicate — nothing to undo there.
-- DROP VIEW IF EXISTS public.v_meditation_heatmap;
-- CREATE VIEW public.v_meditation_heatmap AS
-- SELECT user_id, date_trunc('day', started_at)::date AS day,
--        COUNT(*) AS sessions, COALESCE(SUM(duration_seconds), 0) AS seconds
-- FROM public.meditation_sessions GROUP BY 1, 2;
-- DROP VIEW IF EXISTS public.v_chat_queries_by_assistant;
-- CREATE VIEW public.v_chat_queries_by_assistant AS
-- SELECT assistant_slug, count(*) AS query_count, avg(latency_ms) AS avg_latency_ms,
--        avg(prompt_tokens) AS avg_prompt_tokens, avg(completion_tokens) AS avg_completion_tokens,
--        max(created_at) AS last_query_at
-- FROM public.chat_queries WHERE assistant_slug IS NOT NULL GROUP BY assistant_slug;
-- NOTE: security_invoker=true is a hardening (view inherits caller RLS); dropping
-- it re-exposes the underlying tables' rows per the view owner's rights.
-- ============================================================================

-- Recreate public.v_meditation_heatmap view with security_invoker = true
CREATE OR REPLACE VIEW public.v_meditation_heatmap 
WITH (security_invoker = true) AS
SELECT user_id,
       date_trunc('day', started_at)::date AS day,
       COUNT(*) AS sessions,
       COALESCE(SUM(duration_seconds), 0) AS seconds
FROM public.meditation_sessions
GROUP BY 1, 2;

-- Recreate public.v_chat_queries_by_assistant view with security_invoker = true
create or replace view public.v_chat_queries_by_assistant 
with (security_invoker = true) as
select
    assistant_slug,
    count(*) as query_count,
    avg(latency_ms) as avg_latency_ms,
    avg(prompt_tokens) as avg_prompt_tokens,
    avg(completion_tokens) as avg_completion_tokens,
    max(created_at) as last_query_at
from public.chat_queries
where assistant_slug is not null
group by assistant_slug;

-- Update RLS policy on public.okf_review_queue to use secure has_role check
DROP POLICY IF EXISTS "Admins have full access to okf_review_queue" ON public.okf_review_queue;
CREATE POLICY "Admins have full access to okf_review_queue"
    ON okf_review_queue
    FOR ALL
    TO authenticated
    USING (public.has_role(auth.uid(), 'admin'::public.app_role))
    WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

-- Reload PostgREST schema cache to pick up the new policies and function changes
NOTIFY pgrst, 'reload schema';
