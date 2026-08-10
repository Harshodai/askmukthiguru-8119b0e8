-- ============================================================================
-- REVERT: Drop user_scene_blocks + user_skills. DESTRUCTIVE: all scene-block and skill
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- state is lost. NOTE: owner policies were recreated with WITH CHECK by
-- 20260804000001 — drop with the tables.
-- DROP TABLE IF EXISTS public.user_skills;
-- DROP TABLE IF EXISTS public.user_scene_blocks;
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.user_scene_blocks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::UUID,
    session_id UUID,
    scene_type TEXT NOT NULL DEFAULT 'general',
    compressed_blocks TEXT NOT NULL,
    turn_count INT NOT NULL DEFAULT 1,
    turn_range INT4RANGE,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, tenant_id, session_id, id)
);

CREATE INDEX idx_user_scene_blocks_user ON public.user_scene_blocks (user_id, tenant_id);
CREATE INDEX idx_user_scene_blocks_session ON public.user_scene_blocks (session_id);

ALTER TABLE public.user_scene_blocks ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_scene_blocks_owner_policy ON public.user_scene_blocks
    FOR ALL
    USING (user_id = auth.uid());

CREATE TABLE IF NOT EXISTS public.user_skills (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::UUID,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    source_atom_ids UUID[] DEFAULT '{}',
    proficiency DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    practice_count INT NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, tenant_id, name)
);

CREATE INDEX idx_user_skills_user ON public.user_skills (user_id, tenant_id);

ALTER TABLE public.user_skills ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_skills_owner_policy ON public.user_skills
    FOR ALL
    USING (user_id = auth.uid());

NOTIFY pgrst, 'reload schema';
