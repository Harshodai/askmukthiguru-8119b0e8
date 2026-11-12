-- ============================================================================
-- Migration: 20261107000001_create_video_serving_decisions.sql
-- PROD-DATA-03 (DATA-18, T3-06): Container State Migration to PostgreSQL
--
-- Moves video serving decisions and human approval state from container-local
-- JSON files (/app/data/fp_video_decisions/*.json) to PostgreSQL, eliminating
-- multi-replica state drift on Railway / Docker clusters.
--
-- REVERT:
-- DROP TABLE IF EXISTS public.video_serving_decisions CASCADE;
-- DROP TABLE IF EXISTS public.video_serving_decision_audit CASCADE;
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.video_serving_decisions (
    video_id TEXT PRIMARY KEY,
    admin_approved BOOLEAN,
    human_speaker_check TEXT,
    grade TEXT,
    notes TEXT,
    updated_by TEXT NOT NULL DEFAULT '',
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_video_serving_decisions_admin_approved
    ON public.video_serving_decisions (admin_approved);

CREATE INDEX IF NOT EXISTS idx_video_serving_decisions_speaker_check
    ON public.video_serving_decisions (human_speaker_check);

ALTER TABLE public.video_serving_decisions ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.video_serving_decisions FROM anon;
GRANT SELECT ON TABLE public.video_serving_decisions TO authenticated;
GRANT ALL ON TABLE public.video_serving_decisions TO service_role;

DROP POLICY IF EXISTS "video_serving_decisions_service_role_all" ON public.video_serving_decisions;
CREATE POLICY "video_serving_decisions_service_role_all" ON public.video_serving_decisions
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

DROP POLICY IF EXISTS "video_serving_decisions_authenticated_read" ON public.video_serving_decisions;
CREATE POLICY "video_serving_decisions_authenticated_read" ON public.video_serving_decisions
    FOR SELECT
    TO authenticated
    USING (true);

-- Append-only audit trail for video serving decisions
CREATE TABLE IF NOT EXISTS public.video_serving_decision_audit (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    video_id TEXT NOT NULL,
    admin_approved BOOLEAN,
    human_speaker_check TEXT,
    grade TEXT,
    notes TEXT,
    actor TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_video_decision_audit_video_id
    ON public.video_serving_decision_audit (video_id);

CREATE INDEX IF NOT EXISTS idx_video_decision_audit_created_at
    ON public.video_serving_decision_audit (created_at DESC);

ALTER TABLE public.video_serving_decision_audit ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.video_serving_decision_audit FROM anon, authenticated;
GRANT ALL ON TABLE public.video_serving_decision_audit TO service_role;

DROP POLICY IF EXISTS "video_serving_decision_audit_service_role_all" ON public.video_serving_decision_audit;
CREATE POLICY "video_serving_decision_audit_service_role_all" ON public.video_serving_decision_audit
    FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);
