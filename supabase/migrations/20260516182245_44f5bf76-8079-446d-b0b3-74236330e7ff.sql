REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM PUBLIC;
REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM anon;
GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;