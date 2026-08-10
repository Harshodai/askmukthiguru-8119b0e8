-- ============================================================================
-- REVERT: Drop whoami_diagnostics() and restore handle_new_user() to the profiles-only
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- body. NOTE: the user_roles backfill INSERT is data-altering — backfilled
-- 'user' role rows for pre-existing accounts remain after this revert.
-- DROP FUNCTION IF EXISTS public.whoami_diagnostics();
-- CREATE OR REPLACE FUNCTION public.handle_new_user()
-- RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER AS $$
-- BEGIN
--   INSERT INTO public.profiles (id, display_name, avatar_url)
--   VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url');
--   RETURN NEW;
-- END;
-- $$;
-- ============================================================================

-- 1) Extend handle_new_user to also seed a 'user' role row.
CREATE OR REPLACE FUNCTION public.handle_new_user()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path TO 'public'
AS $function$
BEGIN
  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url')
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'user'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN NEW;
END;
$function$;

-- 2) Make sure the trigger exists (idempotent).
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
  AFTER INSERT ON auth.users
  FOR EACH ROW EXECUTE FUNCTION public.handle_new_user();

-- 3) Backfill existing users that have no role row.
INSERT INTO public.user_roles (user_id, role)
SELECT u.id, 'user'::public.app_role
FROM auth.users u
LEFT JOIN public.user_roles r ON r.user_id = u.id AND r.role = 'user'
WHERE r.id IS NULL;

-- 4) Diagnostic RPC — only ever returns the caller's own state.
CREATE OR REPLACE FUNCTION public.whoami_diagnostics()
RETURNS jsonb
LANGUAGE plpgsql
STABLE SECURITY DEFINER
SET search_path TO 'public'
AS $$
DECLARE
  uid uuid := auth.uid();
  profile_row public.profiles%ROWTYPE;
  role_list text[];
  is_admin boolean;
BEGIN
  IF uid IS NULL THEN
    RETURN jsonb_build_object('authenticated', false);
  END IF;

  SELECT * INTO profile_row FROM public.profiles WHERE id = uid;
  SELECT array_agg(role::text) INTO role_list FROM public.user_roles WHERE user_id = uid;
  SELECT public.has_role(uid, 'admin'::public.app_role) INTO is_admin;

  RETURN jsonb_build_object(
    'authenticated', true,
    'user_id', uid,
    'profile_present', profile_row.id IS NOT NULL,
    'display_name', profile_row.display_name,
    'roles', COALESCE(role_list, ARRAY[]::text[]),
    'is_admin', COALESCE(is_admin, false)
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO authenticated;
