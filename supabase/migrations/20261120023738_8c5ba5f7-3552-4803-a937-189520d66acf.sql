GRANT ALL ON public.waitlist_entries TO service_role;
GRANT SELECT ON public.waitlist_entries TO authenticated;
ALTER TABLE public.waitlist_entries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Launch subscriber read requires admin MFA" ON public.waitlist_entries FOR SELECT TO authenticated USING ((SELECT auth.jwt()->>'aal') = 'aal2' AND public.has_role((SELECT auth.uid()), 'admin'));

CREATE OR REPLACE FUNCTION public.subscribe_launch_updates(p_email text, p_consent boolean, p_source text)
RETURNS text LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
DECLARE normalized_email text := lower(btrim(p_email));
BEGIN
  IF p_consent IS DISTINCT FROM true THEN RAISE EXCEPTION 'Contact consent required' USING ERRCODE = '22023'; END IF;
  IF normalized_email IS NULL OR length(normalized_email) > 254 OR normalized_email !~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$' THEN RAISE EXCEPTION 'Valid email required' USING ERRCODE = '22023'; END IF;
  IF p_source IS NULL OR p_source NOT IN ('guide_ai_spiritual_companion','guide_serene_mind','guide_spirit_guides','guide_beautiful_state','guide_self_centric','guide_anxiety','guide_suffering') THEN RAISE EXCEPTION 'Invalid signup source' USING ERRCODE = '22023'; END IF;
  -- Serialize the bounded aggregate intake check and duplicate writes.
  PERFORM pg_catalog.pg_advisory_xact_lock(811901119);
  IF (SELECT count(*) FROM public.waitlist_entries WHERE consented_at > now() - interval '10 minutes') >= 100 THEN RAISE EXCEPTION 'Signup temporarily busy' USING ERRCODE = 'P0001'; END IF;
  IF NOT EXISTS (SELECT 1 FROM public.waitlist_entries WHERE lower(btrim(email)) = normalized_email) THEN
    INSERT INTO public.waitlist_entries(email,email_key,source,consented_at,updated_at)
    VALUES(normalized_email,normalized_email,p_source,now(),now()) ON CONFLICT (email_key) DO NOTHING;
  END IF;
  RETURN 'accepted';
END;
$$;
REVOKE ALL ON FUNCTION public.subscribe_launch_updates(text,boolean,text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.subscribe_launch_updates(text,boolean,text) TO anon, authenticated;
