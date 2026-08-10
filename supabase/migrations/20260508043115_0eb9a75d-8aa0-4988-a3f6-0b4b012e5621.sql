-- ============================================================================
-- REVERT: Drop the admin-only policies added here. NOTE: this re-opens INSERT/UPDATE/
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- DELETE on user_roles to any authenticated user (the pre-migration state) —
-- only revert as part of a deliberate rollback.
-- DROP POLICY IF EXISTS "admins_manage_roles_insert" ON public.user_roles;
-- DROP POLICY IF EXISTS "admins_manage_roles_update" ON public.user_roles;
-- DROP POLICY IF EXISTS "admins_manage_roles_delete" ON public.user_roles;
-- DROP POLICY IF EXISTS "Admins can update teaching images" ON storage.objects;
-- DROP POLICY IF EXISTS "Admins can delete teaching images" ON storage.objects;
-- ============================================================================

-- Add explicit admin-only INSERT/UPDATE/DELETE policies on user_roles
CREATE POLICY "admins_manage_roles_insert"
ON public.user_roles
FOR INSERT
TO authenticated
WITH CHECK (has_role(auth.uid(), 'admin'::app_role));

CREATE POLICY "admins_manage_roles_update"
ON public.user_roles
FOR UPDATE
TO authenticated
USING (has_role(auth.uid(), 'admin'::app_role));

CREATE POLICY "admins_manage_roles_delete"
ON public.user_roles
FOR DELETE
TO authenticated
USING (has_role(auth.uid(), 'admin'::app_role));

-- Add UPDATE and DELETE policies on daily-teachings storage bucket for admins
CREATE POLICY "Admins can update teaching images"
ON storage.objects
FOR UPDATE
TO authenticated
USING (bucket_id = 'daily-teachings' AND (SELECT has_role(auth.uid(), 'admin'::app_role)));

CREATE POLICY "Admins can delete teaching images"
ON storage.objects
FOR DELETE
TO authenticated
USING (bucket_id = 'daily-teachings' AND (SELECT has_role(auth.uid(), 'admin'::app_role)));
