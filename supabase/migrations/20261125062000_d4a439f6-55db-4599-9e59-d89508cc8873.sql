CREATE TABLE public.launch_email_deliveries (
 subscriber_id uuid PRIMARY KEY REFERENCES public.waitlist_entries(id) ON DELETE CASCADE,
 state text NOT NULL DEFAULT 'queued', attempts integer NOT NULL DEFAULT 0,
 next_attempt_at timestamptz NOT NULL DEFAULT now(), locked_at timestamptz,
 provider_message_id text, last_error text,
 created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now()
);
GRANT ALL ON public.launch_email_deliveries TO service_role;
REVOKE ALL ON public.launch_email_deliveries FROM PUBLIC, anon, authenticated;
ALTER TABLE public.launch_email_deliveries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Trusted service manages confirmation delivery" ON public.launch_email_deliveries FOR ALL TO service_role USING (true) WITH CHECK (true);
CREATE TRIGGER launch_delivery_updated BEFORE UPDATE ON public.launch_email_deliveries FOR EACH ROW EXECUTE FUNCTION public.set_updated_at();
CREATE FUNCTION public.enqueue_launch_confirmation() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 IF NEW.consent_to_contact IS TRUE THEN INSERT INTO public.launch_email_deliveries(subscriber_id) VALUES (NEW.id) ON CONFLICT DO NOTHING; END IF;
 RETURN NEW;
END; $$;
REVOKE ALL ON FUNCTION public.enqueue_launch_confirmation() FROM PUBLIC,anon,authenticated;
CREATE TRIGGER enqueue_launch_confirmation AFTER INSERT ON public.waitlist_entries FOR EACH ROW EXECUTE FUNCTION public.enqueue_launch_confirmation();
CREATE FUNCTION public.claim_launch_confirmations(p_email text DEFAULT NULL,p_limit integer DEFAULT 5)
RETURNS TABLE(subscriber_id uuid,email text,unsubscribe_token uuid,attempts integer)
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN
 RETURN QUERY WITH candidates AS (
 SELECT d.subscriber_id FROM public.launch_email_deliveries d JOIN public.waitlist_entries w ON w.id=d.subscriber_id
 WHERE w.consent_to_contact IS TRUE AND w.consented_at > now()-interval '12 months'
 AND (p_email IS NULL OR w.email_key=lower(btrim(p_email)))
 AND d.attempts<3 AND d.next_attempt_at<=now()
 AND (d.state IN ('queued','failed') OR (d.state='sending' AND d.locked_at<now()-interval '5 minutes'))
 ORDER BY d.created_at LIMIT greatest(1,least(p_limit,10)) FOR UPDATE OF d SKIP LOCKED
 ), claimed AS (
 UPDATE public.launch_email_deliveries d SET state='sending',attempts=d.attempts+1,locked_at=now()
 FROM candidates c WHERE d.subscriber_id=c.subscriber_id RETURNING d.subscriber_id,d.attempts
 ) SELECT c.subscriber_id,w.email,w.unsubscribe_token,c.attempts FROM claimed c JOIN public.waitlist_entries w ON w.id=c.subscriber_id;
END; $$;
REVOKE ALL ON FUNCTION public.claim_launch_confirmations(text,integer) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.claim_launch_confirmations(text,integer) TO service_role;
-- Add only the launch source to the existing validation body, retaining every validation and throttle.
DO $$ DECLARE definition text; BEGIN
 SELECT pg_get_functiondef('public.validate_launch_subscription()'::regprocedure) INTO definition;
 IF position('''launch_page''' IN definition)=0 THEN
 definition:=replace(definition,'''guide_suffering'')','''guide_suffering'',''launch_page'')');
 IF position('''launch_page''' IN definition)=0 THEN RAISE EXCEPTION 'Launch source validation pattern changed'; END IF;
 EXECUTE definition;
 END IF;
END; $$;
ALTER POLICY "Visitors may submit consented launch subscriptions" ON public.waitlist_entries WITH CHECK (consent_to_contact=true AND source IN ('guide_ai_spiritual_companion','guide_serene_mind','guide_spirit_guides','guide_beautiful_state','guide_self_centric','guide_anxiety','guide_suffering','launch_page'));
-- Restricted, explicitly invoked backfill for a single consented address; not a public resend API.
CREATE FUNCTION public.queue_existing_launch_confirmation(p_email text) RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN INSERT INTO public.launch_email_deliveries(subscriber_id)
 SELECT w.id FROM public.waitlist_entries w WHERE w.email_key=lower(btrim(p_email)) AND w.consent_to_contact IS TRUE AND w.consented_at>now()-interval '12 months'
 ON CONFLICT DO NOTHING; END; $$;
REVOKE ALL ON FUNCTION public.queue_existing_launch_confirmation(text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.queue_existing_launch_confirmation(text) TO service_role;