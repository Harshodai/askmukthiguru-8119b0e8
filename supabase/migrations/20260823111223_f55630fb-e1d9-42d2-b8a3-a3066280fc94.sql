-- ============================================================================
-- REVERT: Restore public execute on admin RPCs and app settings policy
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- DROP POLICY IF EXISTS "Admins can read app settings" ON public.app_settings;
-- CREATE POLICY "Authenticated users can read app settings" ON public.app_settings FOR SELECT TO authenticated USING (true);
-- GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO anon, PUBLIC;
-- ============================================================================

DROP POLICY IF EXISTS "Authenticated users can read app settings" ON public.app_settings;

CREATE POLICY "Admins can read app settings"
ON public.app_settings
FOR SELECT
TO authenticated
USING (public.has_role(auth.uid(), 'admin'::public.app_role));

REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM authenticated, anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.promote_admin_by_email(text) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.list_admins() FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.brain_touch(text) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.match_user_memories(vector, integer, double precision) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM anon, PUBLIC;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated, service_role;