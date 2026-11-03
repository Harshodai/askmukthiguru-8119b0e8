-- ============================================================================
-- REVERT: Drop corpus_gate_rejections table and its indexes.
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
--
-- REVERT:
-- DROP TABLE IF EXISTS public.corpus_gate_rejections CASCADE;
-- ============================================================================

-- DE-0.5: corpus_gate_rejections table for tracking chunks rejected by quality gates at storage chokepoint.
CREATE TABLE IF NOT EXISTS public.corpus_gate_rejections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url TEXT NOT NULL,
    chunk_index INT,
    gate_layer TEXT NOT NULL,
    reason TEXT NOT NULL,
    matched_span TEXT,
    point_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_corpus_gate_rejections_source_url_created_at
    ON public.corpus_gate_rejections (source_url, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_corpus_gate_rejections_reason
    ON public.corpus_gate_rejections (reason);

ALTER TABLE public.corpus_gate_rejections ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.corpus_gate_rejections FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.corpus_gate_rejections TO service_role;

DROP POLICY IF EXISTS "corpus_gate_rejections_service_role_all" ON public.corpus_gate_rejections;
CREATE POLICY "corpus_gate_rejections_service_role_all" ON public.corpus_gate_rejections
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
