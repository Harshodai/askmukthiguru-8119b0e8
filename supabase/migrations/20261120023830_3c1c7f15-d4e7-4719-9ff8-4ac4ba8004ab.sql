ALTER TABLE public.waitlist_entries ADD COLUMN consent_to_contact boolean NOT NULL DEFAULT false;
GRANT INSERT ON public.waitlist_entries TO anon, authenticated;
CREATE OR REPLACE FUNCTION public.validate_launch_subscription() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path = '' AS $$
BEGIN
 IF NEW.consent_to_contact IS DISTINCT FROM true OR NEW.source NOT IN ('guide_ai_spiritual_companion','guide_serene_mind','guide_spirit_guides','guide_beautiful_state','guide_self_centric','guide_anxiety','guide_suffering') OR NEW.source IS NULL THEN RAISE EXCEPTION 'Valid consent and source required' USING ERRCODE='22023'; END IF;
 NEW.email := lower(btrim(NEW.email));
 IF NEW.email IS NULL OR length(NEW.email) > 254 OR NEW.email !~ '^[A-Za-z0-9.!#$%&''*+/=?^_`{|}~-]+@[A-Za-z0-9]([A-Za-z0-9.-]*[A-Za-z0-9])?\.[A-Za-z]{2,}$' THEN RAISE EXCEPTION 'Valid email required' USING ERRCODE='22023'; END IF;
 NEW.email_key := NEW.email; NEW.name := NULL; NEW.consented_at := now(); NEW.updated_at := now();
 PERFORM pg_catalog.pg_advisory_xact_lock(811901119);
 IF (SELECT count(*) FROM public.waitlist_entries WHERE consented_at > now() - interval '10 minutes') >= 100 THEN RAISE EXCEPTION 'Signup temporarily busy' USING ERRCODE='P0001'; END IF;
 IF EXISTS (SELECT 1 FROM public.waitlist_entries WHERE lower(btrim(email))=NEW.email) THEN RETURN NULL; END IF;
 RETURN NEW;
END;
$$;
REVOKE ALL ON FUNCTION public.validate_launch_subscription() FROM PUBLIC, anon, authenticated;
CREATE TRIGGER validate_launch_subscription BEFORE INSERT ON public.waitlist_entries FOR EACH ROW EXECUTE FUNCTION public.validate_launch_subscription();
CREATE POLICY "Visitors may submit consented launch subscriptions" ON public.waitlist_entries FOR INSERT TO anon, authenticated WITH CHECK (consent_to_contact = true AND source IN ('guide_ai_spiritual_companion','guide_serene_mind','guide_spirit_guides','guide_beautiful_state','guide_self_centric','guide_anxiety','guide_suffering'));
CREATE OR REPLACE FUNCTION public.subscribe_launch_updates(p_email text,p_consent boolean,p_source text) RETURNS text LANGUAGE plpgsql SECURITY INVOKER SET search_path='' AS $$
BEGIN
 IF p_consent IS DISTINCT FROM true THEN RAISE EXCEPTION 'Contact consent required' USING ERRCODE='22023'; END IF;
 INSERT INTO public.waitlist_entries(email,consent_to_contact,source) VALUES(p_email,p_consent,p_source);
 RETURN 'accepted';
END;
$$;