-- ============================================================================
-- REVERT: Reverse the REVOKEs and swap the storage read policy back
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO anon;
-- GRANT EXECUTE ON FUNCTION public.handle_new_user() TO anon, authenticated;
-- DROP POLICY IF EXISTS "authenticated_read_teaching_images" ON storage.objects;
-- CREATE POLICY "public_read_teaching_images" ON storage.objects
--   FOR SELECT TO authenticated
--   USING (bucket_id = 'daily-teachings');
-- ============================================================================

-- Revoke anon execute on security definer functions
REVOKE EXECUTE ON FUNCTION public.has_role(UUID, app_role) FROM anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon, authenticated;

-- Restrict storage listing to admins only
DROP POLICY IF EXISTS "public_read_teaching_images" ON storage.objects;
CREATE POLICY "authenticated_read_teaching_images" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'daily-teachings');
