-- The frontend never reads public.video_serving_decisions (only the backend does,
-- as service_role), yet 20261107000001 let every signed-in user SELECT all rows,
-- including admin grades and notes. Remove that read; service_role keeps full access.
-- REVERT:
-- GRANT SELECT ON TABLE public.video_serving_decisions TO authenticated;
-- CREATE POLICY "video_serving_decisions_authenticated_read" ON public.video_serving_decisions
--     FOR SELECT TO authenticated USING (true);
DROP POLICY IF EXISTS "video_serving_decisions_authenticated_read" ON public.video_serving_decisions;
REVOKE ALL ON TABLE public.video_serving_decisions FROM anon, authenticated;
