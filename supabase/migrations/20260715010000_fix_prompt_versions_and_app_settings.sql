-- ============================================================================
-- REVERT: Drop the app_settings table created here and reverse the prompt_versions
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- changes. CAUTION: version TEXT→INTEGER cast fails on non-numeric values.
-- description/author are shared with 20260618110000 etc. — drop only if all are
-- reverted.
-- DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
-- DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;
-- DROP TABLE IF EXISTS public.app_settings;
-- ALTER TABLE public.prompt_versions ALTER COLUMN version TYPE integer USING version::integer;
-- ALTER TABLE public.prompt_versions DROP COLUMN IF EXISTS description;
-- ALTER TABLE public.prompt_versions DROP COLUMN IF EXISTS author;
-- ============================================================================

-- Migration: Fix prompt_versions missing columns + ensure app_settings table exists
-- Fixes:
--   PGRST204: "Could not find the 'author' column of 'prompt_versions' in the schema cache"
--   PGRST205: "Could not find the table 'public.app_settings' in the schema cache"

-- 1. Add missing columns to prompt_versions (author, description)
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS author TEXT DEFAULT 'system';

-- 2. Ensure prompt_versions.version is TEXT (not integer)
ALTER TABLE public.prompt_versions ALTER COLUMN version TYPE TEXT USING version::TEXT;

-- 3. Create app_settings table if it was never applied to production
CREATE TABLE IF NOT EXISTS public.app_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
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

-- 4. Notify PostgREST to reload schema cache (clears PGRST204/205)
NOTIFY pgrst, 'reload schema';
