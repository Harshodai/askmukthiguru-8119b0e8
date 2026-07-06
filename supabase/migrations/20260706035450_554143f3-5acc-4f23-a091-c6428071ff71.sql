
DROP POLICY IF EXISTS "public_read_teaching_images" ON storage.objects;
DROP POLICY IF EXISTS "Public read access to daily-teachings" ON storage.objects;
DROP POLICY IF EXISTS "authenticated_read_teaching_images" ON storage.objects;
CREATE POLICY "authenticated_read_teaching_images"
  ON storage.objects FOR SELECT
  TO authenticated
  USING (bucket_id = 'daily-teachings');

REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.promote_admin_by_email(text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.list_admins() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.seed_admin_demo() TO service_role;
GRANT EXECUTE ON FUNCTION public.promote_admin_by_email(text) TO service_role;
GRANT EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.list_admins() TO service_role;
GRANT EXECUTE ON FUNCTION public.handle_new_user() TO service_role;
