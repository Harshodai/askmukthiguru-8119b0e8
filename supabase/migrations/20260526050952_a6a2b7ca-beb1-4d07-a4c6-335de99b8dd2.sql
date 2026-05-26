REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM anon, public;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;

REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM anon, public;
GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO authenticated;

REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM anon, public;
GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;