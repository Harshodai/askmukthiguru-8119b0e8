-- ============================================================================
-- REVERT: Same shape as 20260715010000 — drop app_settings + reverse prompt_versions
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- CAUTION: version cast fails on non-numeric values; description/author shared
-- with other migrations.
-- DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
-- DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;
-- DROP TABLE IF EXISTS public.app_settings;
-- ALTER TABLE public.prompt_versions ALTER COLUMN version TYPE integer USING version::integer;
-- ALTER TABLE public.prompt_versions DROP COLUMN IF EXISTS description;
-- ALTER TABLE public.prompt_versions DROP COLUMN IF EXISTS author;
-- ============================================================================

ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS description TEXT DEFAULT '';
ALTER TABLE public.prompt_versions ADD COLUMN IF NOT EXISTS author TEXT DEFAULT 'system';
ALTER TABLE public.prompt_versions ALTER COLUMN version TYPE TEXT USING version::TEXT;

CREATE TABLE IF NOT EXISTS public.app_settings (
  key TEXT PRIMARY KEY,
  value JSONB NOT NULL,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

GRANT SELECT ON public.app_settings TO anon, authenticated;
GRANT ALL ON public.app_settings TO service_role;
GRANT INSERT, UPDATE, DELETE ON public.app_settings TO authenticated;

ALTER TABLE public.app_settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow read access to anyone" ON public.app_settings;
CREATE POLICY "Allow read access to anyone" ON public.app_settings
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;
CREATE POLICY "Allow write access to authenticated users" ON public.app_settings
  FOR ALL TO authenticated USING (true) WITH CHECK (true);

NOTIFY pgrst, 'reload schema';