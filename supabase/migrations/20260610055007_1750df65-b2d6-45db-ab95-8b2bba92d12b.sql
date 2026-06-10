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