-- ============================================================================
-- REVERT: Reverse the REVOKEs (restore execute to anon + public)
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO anon, public;
-- GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO anon, public;
-- GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO anon, public;
-- ============================================================================

REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM anon, public;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;

REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM anon, public;
GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO authenticated;

REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM anon, public;
GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;