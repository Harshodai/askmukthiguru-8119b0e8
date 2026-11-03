-- ============================================================================
-- REVERT: Drop retrieval_feedback_signals table and its indexes.
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
--
-- REVERT:
-- DROP TABLE IF EXISTS public.retrieval_feedback_signals CASCADE;
-- ============================================================================

-- RAG-1: retrieval_feedback_signals table for persisting bounded, TTL'd retrieval feedback signals.
CREATE TABLE IF NOT EXISTS public.retrieval_feedback_signals (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_hash TEXT NOT NULL,
    source_url TEXT NOT NULL,
    point_id TEXT,
    signal TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now(),
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_signals_source_url_expires_at
    ON public.retrieval_feedback_signals (source_url, expires_at);

CREATE INDEX IF NOT EXISTS idx_retrieval_feedback_signals_query_hash
    ON public.retrieval_feedback_signals (query_hash);

ALTER TABLE public.retrieval_feedback_signals ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.retrieval_feedback_signals FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.retrieval_feedback_signals TO service_role;

DROP POLICY IF EXISTS "retrieval_feedback_signals_service_role_all" ON public.retrieval_feedback_signals;
CREATE POLICY "retrieval_feedback_signals_service_role_all" ON public.retrieval_feedback_signals
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
