-- ============================================================================
-- Migration: 20261107000000_create_message_citations.sql
-- PROD-DATA-02 (DATA-12, T3-06): Structured Citation Ledger
--
-- Replaces free-form text[] citation strings with a structured, queryable,
-- verified citation ledger linking each served chat message to exact audio-visual
-- coordinates, verbatim text hash, speaker attribution, and rights status.
-- Also establishes immutable audit ledger for cross-store takedowns (PROD-DATA-01).
--
-- REVERT:
-- DROP TABLE IF EXISTS public.message_citations CASCADE;
-- DROP TABLE IF EXISTS public.corpus_takedowns CASCADE;
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.message_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    message_id UUID NOT NULL,
    span_id TEXT,
    video_id TEXT NOT NULL,
    guru_id TEXT NOT NULL,
    start_ms INT NOT NULL DEFAULT 0,
    end_ms INT NOT NULL DEFAULT 0,
    verbatim_text TEXT NOT NULL,
    source_text_hash TEXT NOT NULL,
    rights_status TEXT NOT NULL DEFAULT 'licensed',
    speaker_verified BOOLEAN NOT NULL DEFAULT true,
    withdrawn_by_source BOOLEAN NOT NULL DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_message_citations_message_id
    ON public.message_citations (message_id);

CREATE INDEX IF NOT EXISTS idx_message_citations_video_id
    ON public.message_citations (video_id);

CREATE INDEX IF NOT EXISTS idx_message_citations_span_id
    ON public.message_citations (span_id);

CREATE INDEX IF NOT EXISTS idx_message_citations_rights_status
    ON public.message_citations (rights_status);

ALTER TABLE public.message_citations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.message_citations FROM anon;
GRANT SELECT, INSERT ON TABLE public.message_citations TO authenticated;
GRANT ALL ON TABLE public.message_citations TO service_role;

DROP POLICY IF EXISTS "message_citations_service_role_all" ON public.message_citations;
CREATE POLICY "message_citations_service_role_all" ON public.message_citations
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "message_citations_authenticated_read" ON public.message_citations;
CREATE POLICY "message_citations_authenticated_read" ON public.message_citations
    FOR SELECT
    TO authenticated
    USING (true);

-- Immutable audit ledger for cross-store content revocations (PROD-DATA-01)
CREATE TABLE IF NOT EXISTS public.corpus_takedowns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_identity TEXT NOT NULL,
    reason TEXT NOT NULL,
    dry_run BOOLEAN NOT NULL DEFAULT false,
    qdrant_points_quarantined INT NOT NULL DEFAULT 0,
    redis_keys_flushed INT NOT NULL DEFAULT 0,
    db_records_marked INT NOT NULL DEFAULT 0,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_corpus_takedowns_source_identity
    ON public.corpus_takedowns (source_identity);

CREATE INDEX IF NOT EXISTS idx_corpus_takedowns_created_at
    ON public.corpus_takedowns (created_at DESC);

ALTER TABLE public.corpus_takedowns ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.corpus_takedowns FROM anon, authenticated;
GRANT ALL ON TABLE public.corpus_takedowns TO service_role;

DROP POLICY IF EXISTS "corpus_takedowns_service_role_all" ON public.corpus_takedowns;
CREATE POLICY "corpus_takedowns_service_role_all" ON public.corpus_takedowns
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
