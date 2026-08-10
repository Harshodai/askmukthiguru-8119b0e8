-- ============================================================================
-- REVERT: Reverse the REVOKEs
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO PUBLIC, anon;
-- ============================================================================

REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM anon;
GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;
