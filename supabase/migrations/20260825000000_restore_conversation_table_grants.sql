-- Restore the table privileges required by the authenticated client sync path
-- and backend service-role reads/writes. RLS remains the row-level boundary.
GRANT SELECT, INSERT, UPDATE, DELETE ON public.conversations TO authenticated;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.chat_messages TO authenticated;
GRANT ALL ON public.conversations TO service_role;
GRANT ALL ON public.chat_messages TO service_role;

COMMENT ON TABLE public.conversations IS
  'User-owned conversations. Access is controlled by own_conversations_* RLS policies.';
COMMENT ON TABLE public.chat_messages IS
  'Conversation messages. Access is controlled by own_messages_* RLS policies.';

DO $$
BEGIN
  IF NOT has_table_privilege('authenticated', 'public.conversations', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'authenticated conversation table grants were not applied';
  END IF;
  IF NOT has_table_privilege('service_role', 'public.conversations', 'SELECT,INSERT,UPDATE,DELETE') THEN
    RAISE EXCEPTION 'service_role conversation table grants were not applied';
  END IF;
END
$$;
