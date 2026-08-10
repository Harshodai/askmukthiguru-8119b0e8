-- ============================================================================
-- REVERT: Drop the admin-only write policies. NOTE: the pre-migration permissive
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- policy ("Allow write access to authenticated users") was already dropped here;
-- restore it from 20260701140000 only for a deliberate rollback.
-- DROP POLICY IF EXISTS "Admins can insert app settings" ON public.app_settings;
-- DROP POLICY IF EXISTS "Admins can update app settings" ON public.app_settings;
-- DROP POLICY IF EXISTS "Admins can delete app settings" ON public.app_settings;
-- ============================================================================


DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;

CREATE POLICY "Admins can insert app settings"
ON public.app_settings FOR INSERT
TO authenticated
WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

CREATE POLICY "Admins can update app settings"
ON public.app_settings FOR UPDATE
TO authenticated
USING (public.has_role(auth.uid(), 'admin'::public.app_role))
WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

CREATE POLICY "Admins can delete app settings"
ON public.app_settings FOR DELETE
TO authenticated
USING (public.has_role(auth.uid(), 'admin'::public.app_role));
