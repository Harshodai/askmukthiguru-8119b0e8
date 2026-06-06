
-- 1. Promote kharshaengineer@gmail.com to admin
INSERT INTO public.user_roles (user_id, role)
SELECT id, 'admin'::public.app_role
FROM auth.users
WHERE lower(email) = 'kharshaengineer@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;

-- 2. Reset password to a known value (bcrypt via pgcrypto)
UPDATE auth.users
SET encrypted_password = crypt('Mukthi@2026!', gen_salt('bf')),
    updated_at = now()
WHERE lower(email) = 'kharshaengineer@gmail.com';
