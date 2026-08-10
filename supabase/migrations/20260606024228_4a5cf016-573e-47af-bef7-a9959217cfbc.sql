-- ============================================================================
-- REVERT: Data-only migration. Remove the admin role row granted here. NOTE: this row
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- may have been re-created by later migrations (20260610055007, 20260714064138)
-- — a full rollback of admin grants requires reviewing those as well.
-- DELETE FROM public.user_roles
-- WHERE role = 'admin'
--   AND user_id IN (SELECT id FROM auth.users WHERE lower(email) = 'kharshaengineer@gmail.com');
-- ============================================================================

-- 1. Promote kharshaengineer@gmail.com to admin
INSERT INTO public.user_roles (user_id, role)
SELECT id, 'admin'::public.app_role
FROM auth.users
WHERE lower(email) = 'kharshaengineer@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;

-- 2. [REDACTED] Previously reset the admin password to a hardcoded plaintext value.
--    Removed for security. The exposed password MUST be rotated via the auth dashboard
--    or auth admin API. Never commit credential-setting SQL again.
