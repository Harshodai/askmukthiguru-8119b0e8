-- ============================================================================
-- REVERT: Drop app_settings + policies. NOTE: app_settings is recreated by later
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- migrations (20260715010000, 20260715050512) which also redefine the write
-- policy — review those before reverting this one.
-- DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
-- DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;
-- DROP TABLE IF EXISTS public.app_settings;
-- ============================================================================

-- Migration: Create app_settings table for dynamic configurations
CREATE TABLE IF NOT EXISTS public.app_settings (
  key text PRIMARY KEY,
  value jsonb NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
CREATE POLICY "Allow read access to anyone" ON public.app_settings
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;
CREATE POLICY "Allow write access to authenticated users" ON public.app_settings
  FOR ALL TO authenticated USING (true);

GRANT SELECT ON public.app_settings TO authenticated, anon;
GRANT ALL ON public.app_settings TO service_role;
