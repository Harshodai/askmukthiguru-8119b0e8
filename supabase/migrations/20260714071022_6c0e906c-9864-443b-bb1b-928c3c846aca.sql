-- 1) Drop RPCs flagged as insecure (idempotent — no-ops if absent)
DROP FUNCTION IF EXISTS public.match_user_memories_by_user(uuid, vector, integer, double precision) CASCADE;
DROP FUNCTION IF EXISTS public.match_user_memories_by_user(uuid, vector, integer, float) CASCADE;
DROP FUNCTION IF EXISTS public.meditation_streak(uuid) CASCADE;

-- 2) Drop any anon-read policy on ingest_jobs (if the table exists)
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='ingest_jobs') THEN
    EXECUTE 'DROP POLICY IF EXISTS "Anon read-only on ingest_jobs" ON public.ingest_jobs';
    EXECUTE 'REVOKE SELECT ON public.ingest_jobs FROM anon';
  END IF;
END$$;

-- 3) Revoke EXECUTE on internal-only SECURITY DEFINER functions from anon/PUBLIC.
-- These are only meant to be reachable by authenticated users (with in-function role checks)
-- or by triggers/service_role. This addresses the SUPA linter findings.
REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.grant_admin_for_designated_emails() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.promote_admin_by_email(text) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.list_admins() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.match_user_memories(vector, integer, double precision) FROM PUBLIC, anon;
REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;

-- 4) Enforce email-domain allow-list server-side inside handle_new_user.
-- Since this trigger runs AFTER INSERT on auth.users, a RAISE EXCEPTION here rolls back
-- the entire signup transaction, so the check cannot be bypassed by calling Auth REST directly.
CREATE OR REPLACE FUNCTION public.handle_new_user()
 RETURNS trigger
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO 'public'
AS $function$
DECLARE
  allowed_domains text[] := ARRAY['gmail.com','googlemail.com','hotmail.com','outlook.com','live.com','msn.com'];
  email_domain text;
BEGIN
  IF NEW.email IS NOT NULL THEN
    email_domain := lower(split_part(NEW.email, '@', 2));
    IF NOT (email_domain = ANY(allowed_domains)) THEN
      RAISE EXCEPTION 'email_domain_not_allowed: %', email_domain
        USING HINT = 'Only gmail, hotmail, or outlook addresses are accepted.';
    END IF;
  END IF;

  INSERT INTO public.profiles (id, display_name, avatar_url)
  VALUES (NEW.id, NEW.raw_user_meta_data->>'full_name', NEW.raw_user_meta_data->>'avatar_url')
  ON CONFLICT (id) DO NOTHING;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (NEW.id, 'user'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN NEW;
END;
$function$;

-- 5) Tighten storage policy for daily-teachings bucket: only allow reads of objects
-- referenced by a non-expired daily_teachings row. Applies to anon and authenticated.
DROP POLICY IF EXISTS "authenticated_read_teaching_images" ON storage.objects;
DROP POLICY IF EXISTS "public_read_active_teaching_images" ON storage.objects;
CREATE POLICY "public_read_active_teaching_images"
ON storage.objects
FOR SELECT
TO anon, authenticated
USING (
  bucket_id = 'daily-teachings'
  AND EXISTS (
    SELECT 1 FROM public.daily_teachings d
    WHERE d.expires_at > now()
      AND d.image_url LIKE '%' || storage.objects.name
  )
);

-- 6) Ensure UPDATE/DELETE on daily_teachings are admin-only (they already are for DELETE;
-- add explicit admin UPDATE policy so realtime UPDATE events cannot originate from non-admins).
DROP POLICY IF EXISTS "admin_update" ON public.daily_teachings;
CREATE POLICY "admin_update"
ON public.daily_teachings
FOR UPDATE
TO authenticated
USING (has_role(auth.uid(), 'admin'::app_role))
WITH CHECK (has_role(auth.uid(), 'admin'::app_role));