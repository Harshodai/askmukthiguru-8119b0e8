-- Security Hardening & RLS Remediation Migration
-- Date: 2026-07-24

-- ── 1. Realtime Channels Security ──
-- Drop the permissive "Authenticated users can subscribe" policy on realtime.messages
-- which used USING (true) and bypassed topic-scoped restrictions.
DROP POLICY IF EXISTS "Authenticated users can subscribe" ON realtime.messages;

-- ── 2. Staging Quality Queue Hardening ──
-- Restrict SELECT on staging_quality_queue to admins only.
DROP POLICY IF EXISTS "Allow read access to anyone" ON public.staging_quality_queue;
DROP POLICY IF EXISTS "Allow read access to admins only" ON public.staging_quality_queue;
CREATE POLICY "Allow read access to admins only" ON public.staging_quality_queue
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::public.app_role));

REVOKE SELECT ON public.staging_quality_queue FROM anon;
GRANT SELECT ON public.staging_quality_queue TO authenticated;

-- ── 3. Function search_path Normalization (Lint 0011) ──
-- Ensure set_updated_at() trigger function sets search_path = public
CREATE OR REPLACE FUNCTION public.set_updated_at()
RETURNS trigger LANGUAGE plpgsql SET search_path = public AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$;

-- ── 4. SECURITY DEFINER & Trigger Privilege Revocation (Lints 0028 & 0029) ──
-- A. Revoke EXECUTE on trigger functions from PUBLIC, anon, and authenticated
--    (Triggers are executed by the DB engine, not directly via PostgREST RPC)
DO $$
BEGIN
  -- set_updated_at
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.set_updated_at() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- handle_new_user
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.handle_new_user() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- grant_admin_for_designated_emails
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.grant_admin_for_designated_emails() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- touch_updated_at
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.touch_updated_at() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- update_conversation_updated_at
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.update_conversation_updated_at() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- kb_sources_touch_updated_at
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.kb_sources_touch_updated_at() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- touch_user_last_message
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.touch_user_last_message() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- rls_auto_enable
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.rls_auto_enable() FROM PUBLIC, anon, authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;
END $$;

-- B. Revoke EXECUTE on internal / admin RPCs from PUBLIC and anon
--    (Allow execute only for authenticated role or service_role)
DO $$
BEGIN
  -- list_admins
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.list_admins() FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.list_admins() TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- promote_admin_by_email
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.promote_admin_by_email(text) FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.promote_admin_by_email(text) TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- demote_admin_by_id
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- seed_admin_demo
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.seed_admin_demo() TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- ensure_profile_and_role
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.ensure_profile_and_role() FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.ensure_profile_and_role() TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- whoami_diagnostics
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.whoami_diagnostics() FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.whoami_diagnostics() TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- match_user_memories
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.match_user_memories(public.vector, integer, double precision) FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.match_user_memories(public.vector, integer, double precision) TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- has_role
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
    GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;

  -- record_practice
  BEGIN
    REVOKE EXECUTE ON FUNCTION public.record_practice(uuid, date) FROM PUBLIC, anon, authenticated;
    GRANT EXECUTE ON FUNCTION public.record_practice(uuid, date) TO service_role;
  EXCEPTION WHEN undefined_function THEN NULL;
  END;
END $$;

-- ── 5. Reload PostgREST schema cache ──
NOTIFY pgrst, 'reload schema';
