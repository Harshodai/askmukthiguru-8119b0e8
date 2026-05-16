-- Idempotent helper: callers (authenticated users) ensure they have a profile + default role.
CREATE OR REPLACE FUNCTION public.ensure_profile_and_role()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid := auth.uid();
  u record;
  profile_created boolean := false;
  role_created boolean := false;
  resolved_name text;
  resolved_avatar text;
BEGIN
  IF uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_authenticated');
  END IF;

  SELECT id, email, raw_user_meta_data INTO u FROM auth.users WHERE id = uid;
  IF u.id IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'user_not_found');
  END IF;

  resolved_name := COALESCE(
    u.raw_user_meta_data->>'full_name',
    u.raw_user_meta_data->>'name',
    u.raw_user_meta_data->>'display_name',
    split_part(u.email, '@', 1)
  );
  resolved_avatar := COALESCE(
    u.raw_user_meta_data->>'avatar_url',
    u.raw_user_meta_data->>'picture'
  );

  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (uid, resolved_name, resolved_avatar)
  ON CONFLICT (id) DO UPDATE SET
    display_name = COALESCE(public.profiles.display_name, EXCLUDED.display_name),
    avatar_url   = COALESCE(public.profiles.avatar_url,   EXCLUDED.avatar_url)
  RETURNING (xmax = 0) INTO profile_created;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (uid, 'user'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;
  GET DIAGNOSTICS role_created = ROW_COUNT;

  RETURN jsonb_build_object(
    'ok', true,
    'user_id', uid,
    'profile_created', COALESCE(profile_created, false),
    'role_created', role_created > 0
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;

-- One-time backfill for any historical user missing a profile or default role.
INSERT INTO public.profiles (id, display_name, avatar_url)
SELECT
  u.id,
  COALESCE(
    u.raw_user_meta_data->>'full_name',
    u.raw_user_meta_data->>'name',
    split_part(u.email, '@', 1)
  ),
  COALESCE(
    u.raw_user_meta_data->>'avatar_url',
    u.raw_user_meta_data->>'picture'
  )
FROM auth.users u
LEFT JOIN public.profiles p ON p.id = u.id
WHERE p.id IS NULL;

INSERT INTO public.user_roles (user_id, role)
SELECT u.id, 'user'::public.app_role
FROM auth.users u
LEFT JOIN public.user_roles r ON r.user_id = u.id AND r.role = 'user'::public.app_role
WHERE r.user_id IS NULL;