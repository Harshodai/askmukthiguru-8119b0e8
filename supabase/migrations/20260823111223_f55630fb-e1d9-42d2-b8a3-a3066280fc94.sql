DROP POLICY IF EXISTS "Authenticated users can read app settings" ON public.app_settings;

CREATE POLICY "Admins can read app settings"
ON public.app_settings
FOR SELECT
TO authenticated
USING (public.has_role(auth.uid(), 'admin'::public.app_role));

REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM authenticated, anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.promote_admin_by_email(text) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.list_admins() FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.brain_touch(text) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.match_user_memories(vector, integer, double precision) FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM anon, PUBLIC;
REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM anon, PUBLIC;