-- Recreate public.v_meditation_heatmap view with security_invoker = true
-- ── 1. Restrict App Settings & Quality Queue Write Access ──
-- Only admins should be able to write/manage app_settings
DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.app_settings;
CREATE POLICY "Allow write access to admins only" ON public.app_settings
  FOR ALL TO authenticated 
  USING (public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

-- Only admins should be able to write/manage staging_quality_queue
DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.staging_quality_queue;
CREATE POLICY "Allow write access to admins only" ON public.staging_quality_queue
  FOR ALL TO authenticated 
  USING (public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

-- ── 2. Restrict Telemetry Router Decisions Write/Read Access ──
-- Only admins should be able to SELECT/INSERT/UPDATE router decisions (backend uses service_role which bypasses RLS)
DROP POLICY IF EXISTS "Allow select for all users" ON public.router_decisions;
CREATE POLICY "Allow select for admins only" ON public.router_decisions
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role));

DROP POLICY IF EXISTS "Allow insert for all users" ON public.router_decisions;
CREATE POLICY "Allow insert for admins only" ON public.router_decisions
  FOR INSERT TO authenticated
  WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));

-- ── 3. Secure Storage Buckets (Disable listing for non-admins) ──
-- Drop broad SELECT policies on storage.objects for daily-teachings
DROP POLICY IF EXISTS "Public read access for daily teachings" ON storage.objects;
DROP POLICY IF EXISTS "Public read access to daily-teachings" ON storage.objects;
DROP POLICY IF EXISTS "authenticated_read_teaching_images" ON storage.objects;

-- Create policy allowing admins full management (including listing)
DROP POLICY IF EXISTS "Admins manage daily-teachings bucket" ON storage.objects;
CREATE POLICY "Admins manage daily-teachings bucket" ON storage.objects
  FOR ALL TO authenticated
  USING (bucket_id = 'daily-teachings' AND public.has_role(auth.uid(), 'admin'::public.app_role))
  WITH CHECK (bucket_id = 'daily-teachings' AND public.has_role(auth.uid(), 'admin'::public.app_role));

-- ── 4. Revoke public/anon execute on SECURITY DEFINER functions ──
-- For security definer functions, execution privilege must be revoked from public/anon
-- and granted only to authenticated role or kept fully restricted (internal functions)

-- Internal trigger functions (no public/client execution needed)
DO $$
BEGIN
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;
END $$;
REVOKE EXECUTE ON FUNCTION public.touch_user_last_message() FROM PUBLIC, anon, authenticated;

-- Client-accessible RPC functions (restrict to authenticated role only)
DO $$
BEGIN
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.meditation_streak(uuid) FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.meditation_streak(uuid) TO authenticated;
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;
END $$;

REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;

REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;


REVOKE EXECUTE ON FUNCTION public.match_user_memories(public.vector, integer, double precision) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.match_user_memories(public.vector, integer, double precision) TO authenticated;

DO $$
BEGIN
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, public.vector, integer, double precision) FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.match_user_memories_by_user(uuid, public.vector, integer, double precision) TO authenticated;
  EXCEPTION WHEN undefined_function THEN
    NULL;
  END;
END $$;

REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO authenticated;

-- Reload PostgREST schema cache to apply permissions immediately
NOTIFY pgrst, 'reload schema';
