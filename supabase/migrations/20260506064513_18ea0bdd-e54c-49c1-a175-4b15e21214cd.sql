-- ============================================================================
-- REVERT: Reverse the REVOKEs (restore execute to anon + public)
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO anon, public;
-- GRANT EXECUTE ON FUNCTION public.handle_new_user() TO anon, public;
-- ============================================================================

-- Revoke anon execute on security definer functions
REVOKE EXECUTE ON FUNCTION public.has_role(uuid, app_role) FROM anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon;

-- Revoke public execute as well (only authenticated and trigger context should call these)
REVOKE EXECUTE ON FUNCTION public.has_role(uuid, app_role) FROM public;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM public;

-- Re-grant to authenticated only for has_role (handle_new_user is trigger-only)
GRANT EXECUTE ON FUNCTION public.has_role(uuid, app_role) TO authenticated;
