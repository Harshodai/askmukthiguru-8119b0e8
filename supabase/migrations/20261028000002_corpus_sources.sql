-- ============================================================================
-- REVERT: Drop corpus_sources table and its indexes.
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
--
-- REVERT:
-- DROP TABLE IF EXISTS public.corpus_sources CASCADE;
-- ============================================================================

-- DE-3.1: corpus_sources catalog table for source freshness, status, and release tracking.
CREATE TABLE IF NOT EXISTS public.corpus_sources (
    source_identity TEXT PRIMARY KEY,
    source_url TEXT NOT NULL,
    corpus_id TEXT NOT NULL,
    last_ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_checksum TEXT,
    active_release_id UUID,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_corpus_sources_status_last_ingested_at
    ON public.corpus_sources (status, last_ingested_at);

CREATE INDEX IF NOT EXISTS idx_corpus_sources_corpus_id
    ON public.corpus_sources (corpus_id);

ALTER TABLE public.corpus_sources ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.corpus_sources FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.corpus_sources TO service_role;

DROP POLICY IF EXISTS "corpus_sources_service_role_all" ON public.corpus_sources;
CREATE POLICY "corpus_sources_service_role_all" ON public.corpus_sources
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
