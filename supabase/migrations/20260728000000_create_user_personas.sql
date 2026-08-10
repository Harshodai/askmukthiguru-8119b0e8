-- ============================================================================
-- REVERT: Drop user_personas. DESTRUCTIVE: all persona data is lost. NOTE: the owner
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- policy was recreated with WITH CHECK by 20260804000001 — drops with the table.
-- DROP TABLE IF EXISTS public.user_personas;
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.user_personas (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL DEFAULT '00000000-0000-0000-0000-000000000000'::UUID,
    content TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE(user_id, tenant_id)
);

ALTER TABLE public.user_personas ENABLE ROW LEVEL SECURITY;

CREATE POLICY user_personas_owner_policy ON public.user_personas
    FOR ALL
    USING (user_id = auth.uid());

-- Notify PostgREST to reload schema cache after column additions
NOTIFY pgrst, 'reload schema';
