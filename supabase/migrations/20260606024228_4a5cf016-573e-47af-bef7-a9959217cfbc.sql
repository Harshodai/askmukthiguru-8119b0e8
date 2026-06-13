-- 1. Promote kharshaengineer@gmail.com to admin
INSERT INTO public.user_roles (user_id, role)
SELECT id, 'admin'::public.app_role
FROM auth.users
WHERE lower(email) = 'kharshaengineer@gmail.com'
ON CONFLICT (user_id, role) DO NOTHING;

-- 2. [REDACTED] Previously reset the admin password to a hardcoded plaintext value.
--    Removed for security. The exposed password MUST be rotated via the auth dashboard
--    or auth admin API. Never commit credential-setting SQL again.
