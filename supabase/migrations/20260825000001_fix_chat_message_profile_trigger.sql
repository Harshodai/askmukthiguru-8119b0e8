-- The original trigger used a nonexistent row-level owner field, but
-- chat_messages derives ownership
-- through conversations and has no user_id column. Resolve the owner through
-- the parent conversation before updating profile continuity metadata.
CREATE OR REPLACE FUNCTION public.touch_user_last_message()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  owner_id uuid;
BEGIN
  SELECT c.user_id
    INTO owner_id
    FROM public.conversations AS c
   WHERE c.id = NEW.conversation_id;

  UPDATE public.profiles
     SET last_conversation_id = NEW.conversation_id,
         last_message_id = NEW.id,
         last_active_at = now()
   WHERE id = owner_id;

  RETURN NEW;
END
$$;

COMMENT ON FUNCTION public.touch_user_last_message() IS
  'Updates profile continuity metadata using the conversation owner for a new chat message.';
