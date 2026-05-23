-- Revoke anon execute on security definer functions
REVOKE EXECUTE ON FUNCTION public.has_role(UUID, app_role) FROM anon;
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM anon, authenticated;

-- Restrict storage listing to admins only
DROP POLICY IF EXISTS "public_read_teaching_images" ON storage.objects;
CREATE POLICY "authenticated_read_teaching_images" ON storage.objects
  FOR SELECT TO authenticated
  USING (bucket_id = 'daily-teachings');
