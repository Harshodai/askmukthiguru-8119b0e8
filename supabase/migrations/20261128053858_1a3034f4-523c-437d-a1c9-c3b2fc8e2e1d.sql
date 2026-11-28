REVOKE INSERT, UPDATE, DELETE, TRUNCATE, REFERENCES, TRIGGER ON public.whatsapp_account_links FROM PUBLIC, anon, authenticated;
REVOKE ALL ON public.whatsapp_link_challenges FROM PUBLIC, anon, authenticated;
GRANT SELECT ON public.whatsapp_account_links TO authenticated;
GRANT ALL ON public.whatsapp_account_links, public.whatsapp_link_challenges TO service_role;
DROP POLICY IF EXISTS whatsapp_account_links_update ON public.whatsapp_account_links;
DROP POLICY IF EXISTS whatsapp_account_links_delete ON public.whatsapp_account_links;
ALTER TABLE public.whatsapp_account_links DROP CONSTRAINT whatsapp_account_links_status_check;
ALTER TABLE public.whatsapp_account_links ADD CONSTRAINT whatsapp_account_links_status_check CHECK (status IN ('active','revoked','unlinked','opted_out'));
UPDATE public.whatsapp_account_links SET phone_number_encrypted=NULL WHERE phone_number_encrypted IS NOT NULL;
UPDATE public.whatsapp_link_challenges SET phone_number_raw='' WHERE phone_number_raw<>'';
CREATE FUNCTION public.redeem_whatsapp_link(p_token_hash text,p_user_id uuid,p_tenant_id text)
RETURNS SETOF public.whatsapp_account_links LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE c public.whatsapp_link_challenges; owner_id uuid;
BEGIN
 IF p_user_id IS NULL OR p_tenant_id IS NULL OR p_tenant_id<>'oneness' THEN RAISE EXCEPTION 'Invalid account scope'; END IF;
 SELECT * INTO c FROM public.whatsapp_link_challenges WHERE challenge_token_hash=p_token_hash FOR UPDATE;
 IF NOT FOUND OR c.confirmed_whatsapp IS NOT TRUE OR c.consumed_at IS NOT NULL OR c.expires_at IS NULL OR c.expires_at<=now() OR c.expires_at>c.created_at+interval '15 minutes' THEN RAISE EXCEPTION 'Invalid, unconfirmed, expired or used linking code'; END IF;
 PERFORM pg_advisory_xact_lock(hashtextextended(c.phone_number_hash,0));
 SELECT user_id INTO owner_id FROM public.whatsapp_account_links WHERE phone_number_hash=c.phone_number_hash FOR UPDATE;
 IF FOUND AND owner_id<>p_user_id THEN RAISE EXCEPTION 'Number belongs to another account; unlink it there first'; END IF;
 UPDATE public.whatsapp_link_challenges SET consumed_at=now(),confirmed_web_user_id=p_user_id WHERE id=c.id;
 RETURN QUERY INSERT INTO public.whatsapp_account_links AS link (user_id,tenant_id,phone_number_hash,phone_number_masked,status)
 VALUES(p_user_id,p_tenant_id,c.phone_number_hash,c.phone_number_masked,'active')
 ON CONFLICT(phone_number_hash) DO UPDATE SET status='active',linked_at=now(),updated_at=now(),revoked_at=NULL,
 sync_history_consent=CASE WHEN link.status='active' THEN link.sync_history_consent ELSE false END,
 memory_write_consent=CASE WHEN link.status='active' THEN link.memory_write_consent ELSE false END
 RETURNING link.*;
END; $$;
REVOKE ALL ON FUNCTION public.redeem_whatsapp_link(text,uuid,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.redeem_whatsapp_link(text,uuid,text) TO service_role;
CREATE FUNCTION public.sync_whatsapp_turn(p_link_id uuid,p_user_id uuid,p_question text,p_answer text)
RETURNS boolean LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
DECLARE link public.whatsapp_account_links; conversation_id uuid;
BEGIN
 SELECT * INTO link FROM public.whatsapp_account_links WHERE id=p_link_id AND user_id=p_user_id FOR UPDATE;
 IF NOT FOUND OR link.status<>'active' OR link.sync_history_consent IS NOT TRUE THEN RETURN false; END IF;
 SELECT id INTO conversation_id FROM public.conversations WHERE user_id=p_user_id AND title='WhatsApp Companion' ORDER BY created_at DESC LIMIT 1;
 IF conversation_id IS NULL THEN INSERT INTO public.conversations(user_id,title,preview) VALUES(p_user_id,'WhatsApp Companion',left(p_question,120)) RETURNING id INTO conversation_id; END IF;
 INSERT INTO public.chat_messages(conversation_id,role,content) VALUES(conversation_id,'user',p_question),(conversation_id,'guru',p_answer);
 RETURN true;
END; $$;
REVOKE ALL ON FUNCTION public.sync_whatsapp_turn(uuid,uuid,text,text) FROM PUBLIC,anon,authenticated;
GRANT EXECUTE ON FUNCTION public.sync_whatsapp_turn(uuid,uuid,text,text) TO service_role;