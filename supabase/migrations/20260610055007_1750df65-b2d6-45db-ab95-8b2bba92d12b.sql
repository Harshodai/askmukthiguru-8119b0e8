-- ============================================================================
-- REVERT: Data-only migration. Remove the admin role row. The profile row may be
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- legitimately present from signup (handle_new_user) — delete only if this
-- migration's insert was the sole origin.
-- DELETE FROM public.user_roles
-- WHERE role = 'admin'
--   AND user_id IN (SELECT id FROM auth.users WHERE lower(email) = 'kharshaengineer@gmail.com');
-- ============================================================================

-- Grant admin role to kharshaengineer@gmail.com if the user exists.
-- Idempotent: ON CONFLICT NO-OP. Safe to re-run.
INSERT INTO public.user_roles (user_id, role)
SELECT id, 'admin'::public.app_role
FROM auth.users
WHERE lower(email) = 'kharshaengineer@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;

-- Also ensure a profile row exists for the admin user.
INSERT INTO public.profiles (id, display_name)
SELECT id, COALESCE(raw_user_meta_data->>'full_name', split_part(email,'@',1))
FROM auth.users
WHERE lower(email) = 'kharshaengineer@gmail.com'
ON CONFLICT (id) DO NOTHING;