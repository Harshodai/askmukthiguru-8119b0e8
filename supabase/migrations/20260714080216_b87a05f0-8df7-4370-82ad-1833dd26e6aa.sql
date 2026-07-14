
-- 1. kb_sources / kb_chunks: drop the "authenticated can read everything" policy.
--    Retrieval keeps working through public.match_kb_chunks (SECURITY DEFINER),
--    which returns only the fields the app needs.
DROP POLICY IF EXISTS kb_sources_select_authenticated ON public.kb_sources;
DROP POLICY IF EXISTS kb_chunks_select_authenticated ON public.kb_chunks;

CREATE POLICY kb_sources_admin_select
  ON public.kb_sources
  FOR SELECT
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role));

CREATE POLICY kb_chunks_admin_select
  ON public.kb_chunks
  FOR SELECT
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role));

-- 2. Daily-teachings storage: replace LIKE '%name' with strict equality on the
--    stored object path. Supports both bare object name and full "bucket/name" form.
DROP POLICY IF EXISTS public_read_active_teaching_images ON storage.objects;

CREATE POLICY public_read_active_teaching_images
  ON storage.objects
  FOR SELECT
  USING (
    bucket_id = 'daily-teachings'
    AND EXISTS (
      SELECT 1
      FROM public.daily_teachings d
      WHERE d.expires_at > now()
        AND (
          d.image_url = storage.objects.name
          OR d.image_url = 'daily-teachings/' || storage.objects.name
          OR split_part(d.image_url, 'daily-teachings/', 2) = storage.objects.name
        )
    )
  );

-- 3. Revoke EXECUTE on trigger-only SECURITY DEFINER functions.
--    These fire from database triggers and must never be RPC-callable.
REVOKE EXECUTE ON FUNCTION public.handle_new_user()                    FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.grant_admin_for_designated_emails()  FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.update_conversation_updated_at()     FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.kb_sources_touch_updated_at()        FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.touch_updated_at()                   FROM PUBLIC, anon, authenticated;
