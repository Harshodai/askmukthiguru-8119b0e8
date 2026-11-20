-- DPDP controls for the launch-updates list (public.waitlist_entries).
-- Builds on 20261120023738 / 20261120023830 (already applied). Idempotent; does not loosen RLS.
--   1. Erase path: anon-callable erase RPCs (by email, interim; by email + token, for the
--      future confirmation email) and an admin+AAL2 DELETE policy.
--   2. Retention: purge_expired_launch_subscribers() (default 12 months from first consent),
--      callable by service_role only; optional pg_cron schedule when that extension exists.
--   3. Throttle: the global 100/10min ceiling is kept; adds a per-source bucket and a
--      per-client bucket keyed on a day-salted hash of x-forwarded-for from
--      current_setting('request.headers', true) (Supabase "Securing your API" docs).
--      No header (direct SQL, or a proxy that strips it) means the client bucket is skipped.
-- Retention clock is consented_at, which a duplicate re-subscribe does not refresh.

ALTER TABLE public.waitlist_entries
  ADD COLUMN IF NOT EXISTS unsubscribe_token uuid NOT NULL DEFAULT pg_catalog.gen_random_uuid();
CREATE UNIQUE INDEX IF NOT EXISTS waitlist_entries_unsubscribe_token_key
  ON public.waitlist_entries (unsubscribe_token);
CREATE INDEX IF NOT EXISTS waitlist_entries_consented_at_idx
  ON public.waitlist_entries (consented_at);

-- Short-lived throttle counters. Holds bucket names and hashed client keys only, never an email.
CREATE TABLE IF NOT EXISTS public.launch_signup_throttle (
  id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  bucket text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS launch_signup_throttle_bucket_idx
  ON public.launch_signup_throttle (bucket, created_at);
ALTER TABLE public.launch_signup_throttle ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON public.launch_signup_throttle FROM PUBLIC, anon, authenticated;
GRANT ALL ON public.launch_signup_throttle TO service_role;

-- Day-salted hash of the first x-forwarded-for hop, or NULL when no header is visible.
CREATE OR REPLACE FUNCTION public.launch_client_key() RETURNS text
LANGUAGE plpgsql STABLE SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_ip text;
BEGIN
  BEGIN
    v_ip := pg_catalog.btrim(pg_catalog.split_part(
      (pg_catalog.current_setting('request.headers', true)::json)->>'x-forwarded-for', ',', 1));
  EXCEPTION WHEN others THEN
    v_ip := NULL;
  END;
  IF v_ip IS NULL OR v_ip = '' OR pg_catalog.length(v_ip) > 64 THEN RETURN NULL; END IF;
  RETURN pg_catalog.encode(pg_catalog.sha256(
    pg_catalog.convert_to(v_ip || ':' || current_date::text, 'UTF8')), 'hex');
END;
$$;
REVOKE ALL ON FUNCTION public.launch_client_key() FROM PUBLIC, anon, authenticated;

-- Count one hit on a bucket over the last 10 minutes; refuse once the limit is reached.
-- Callers hold advisory lock 811901119, so the check and the insert cannot race.
CREATE OR REPLACE FUNCTION public.launch_throttle_hit(p_bucket text, p_limit integer) RETURNS void
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
  IF (SELECT count(*) FROM public.launch_signup_throttle
       WHERE bucket = p_bucket AND created_at > now() - interval '10 minutes') >= p_limit THEN
    RAISE EXCEPTION 'Signup temporarily busy' USING ERRCODE = 'P0001';
  END IF;
  INSERT INTO public.launch_signup_throttle(bucket) VALUES (p_bucket);
END;
$$;
REVOKE ALL ON FUNCTION public.launch_throttle_hit(text, integer) FROM PUBLIC, anon, authenticated;

-- Signup validation: every protection from 20261120023830 is kept, plus the two new buckets
-- and a server-generated unsubscribe token.
CREATE OR REPLACE FUNCTION public.validate_launch_subscription() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_client text;
BEGIN
 IF NEW.consent_to_contact IS DISTINCT FROM true OR NEW.source NOT IN ('guide_ai_spiritual_companion','guide_serene_mind','guide_spirit_guides','guide_beautiful_state','guide_self_centric','guide_anxiety','guide_suffering') OR NEW.source IS NULL THEN RAISE EXCEPTION 'Valid consent and source required' USING ERRCODE='22023'; END IF;
 NEW.email := lower(btrim(NEW.email));
 IF NEW.email IS NULL OR length(NEW.email) > 254 OR NEW.email !~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$' THEN RAISE EXCEPTION 'Valid email required' USING ERRCODE='22023'; END IF;
 NEW.email_key := NEW.email; NEW.name := NULL; NEW.consented_at := now(); NEW.updated_at := now();
 NEW.unsubscribe_token := pg_catalog.gen_random_uuid();
 PERFORM pg_catalog.pg_advisory_xact_lock(811901119);
 IF (SELECT count(*) FROM public.waitlist_entries WHERE consented_at > now() - interval '10 minutes') >= 100 THEN RAISE EXCEPTION 'Signup temporarily busy' USING ERRCODE='P0001'; END IF;
 PERFORM public.launch_throttle_hit('signup-src:' || NEW.source, 40);
 v_client := public.launch_client_key();
 IF v_client IS NOT NULL THEN PERFORM public.launch_throttle_hit('signup-client:' || v_client, 10); END IF;
 IF EXISTS (SELECT 1 FROM public.waitlist_entries WHERE lower(btrim(email))=NEW.email) THEN RETURN NULL; END IF;
 RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.validate_launch_subscription() FROM PUBLIC, anon, authenticated;
DROP TRIGGER IF EXISTS validate_launch_subscription ON public.waitlist_entries;
CREATE TRIGGER validate_launch_subscription BEFORE INSERT ON public.waitlist_entries
  FOR EACH ROW EXECUTE FUNCTION public.validate_launch_subscription();

-- Interim erase by email. No email channel exists yet to confirm ownership, so this is
-- throttled (global, and per client when visible) and always answers 'accepted', never
-- revealing whether the address was on the list. Confirmation step: PENDING; once a channel
-- exists, retire this function and use the token variant below.
CREATE OR REPLACE FUNCTION public.erase_launch_subscription(p_email text) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_email text := lower(btrim(p_email)); v_client text;
BEGIN
  IF v_email IS NULL OR length(v_email) > 254 OR v_email !~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$' THEN RAISE EXCEPTION 'Valid email required' USING ERRCODE='22023'; END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(811901119);
  PERFORM public.launch_throttle_hit('erase-all', 60);
  v_client := public.launch_client_key();
  IF v_client IS NOT NULL THEN PERFORM public.launch_throttle_hit('erase-client:' || v_client, 10); END IF;
  DELETE FROM public.waitlist_entries WHERE email_key = v_email;
  RETURN 'accepted';
END;
$$;
REVOKE ALL ON FUNCTION public.erase_launch_subscription(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.erase_launch_subscription(text) TO anon, authenticated;

-- Token variant for a future confirmation email link: needs the unguessable per-row token,
-- which anon can never read (SELECT is admin+AAL2 only).
CREATE OR REPLACE FUNCTION public.erase_launch_subscription_with_token(p_email text, p_token uuid) RETURNS text
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_email text := lower(btrim(p_email)); v_client text;
BEGIN
  IF v_email IS NULL OR p_token IS NULL OR length(v_email) > 254 THEN RAISE EXCEPTION 'Valid email and token required' USING ERRCODE='22023'; END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(811901119);
  PERFORM public.launch_throttle_hit('erase-all', 60);
  v_client := public.launch_client_key();
  IF v_client IS NOT NULL THEN PERFORM public.launch_throttle_hit('erase-client:' || v_client, 10); END IF;
  DELETE FROM public.waitlist_entries WHERE email_key = v_email AND unsubscribe_token = p_token;
  RETURN 'accepted';
END;
$$;
REVOKE ALL ON FUNCTION public.erase_launch_subscription_with_token(text, uuid) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.erase_launch_subscription_with_token(text, uuid) TO anon, authenticated;

-- Admin erase: same predicate as the SELECT policy (admin role at AAL2). No other DELETE policy exists.
GRANT DELETE ON public.waitlist_entries TO authenticated;
DROP POLICY IF EXISTS "Launch subscriber erase requires admin MFA" ON public.waitlist_entries;
CREATE POLICY "Launch subscriber erase requires admin MFA" ON public.waitlist_entries FOR DELETE TO authenticated USING ((SELECT auth.jwt()->>'aal') = 'aal2' AND public.has_role((SELECT auth.uid()), 'admin'));

-- Retention: documented period is 12 months from consent. service_role only.
CREATE OR REPLACE FUNCTION public.purge_expired_launch_subscribers(p_months integer DEFAULT 12) RETURNS integer
LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE v_deleted integer;
BEGIN
  IF p_months IS NULL OR p_months < 1 THEN RAISE EXCEPTION 'Retention must be at least 1 month' USING ERRCODE='22023'; END IF;
  PERFORM pg_catalog.pg_advisory_xact_lock(811901119);
  DELETE FROM public.waitlist_entries WHERE consented_at < now() - pg_catalog.make_interval(months => p_months);
  GET DIAGNOSTICS v_deleted = ROW_COUNT;
  DELETE FROM public.launch_signup_throttle WHERE created_at < now() - interval '1 day';
  RETURN v_deleted;
END;
$$;
REVOKE ALL ON FUNCTION public.purge_expired_launch_subscribers(integer) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.purge_expired_launch_subscribers(integer) TO service_role;

-- Schedule in-database only if pg_cron is installed. Otherwise the Celery task
-- tasks.retention_tasks.cleanup_retention_data calls the same function daily.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'pg_cron') THEN
    PERFORM cron.schedule('purge-launch-subscribers', '17 3 * * *', 'SELECT public.purge_expired_launch_subscribers(12)');
  END IF;
END
$$;
