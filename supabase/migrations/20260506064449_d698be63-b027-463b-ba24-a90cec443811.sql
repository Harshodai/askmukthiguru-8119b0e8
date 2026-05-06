-- Create conversations table
CREATE TABLE public.conversations (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL,
  title text,
  preview text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- Create chat_messages table
CREATE TABLE public.chat_messages (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  conversation_id uuid REFERENCES public.conversations(id) ON DELETE CASCADE NOT NULL,
  role text NOT NULL CHECK (role IN ('user', 'guru')),
  content text NOT NULL,
  citations text[],
  confidence_score float,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Enable RLS
ALTER TABLE public.conversations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.chat_messages ENABLE ROW LEVEL SECURITY;

-- Conversations: users can only access their own
CREATE POLICY "own_conversations_select" ON public.conversations
  FOR SELECT TO authenticated USING (user_id = auth.uid());

CREATE POLICY "own_conversations_insert" ON public.conversations
  FOR INSERT TO authenticated WITH CHECK (user_id = auth.uid());

CREATE POLICY "own_conversations_update" ON public.conversations
  FOR UPDATE TO authenticated USING (user_id = auth.uid());

CREATE POLICY "own_conversations_delete" ON public.conversations
  FOR DELETE TO authenticated USING (user_id = auth.uid());

-- Chat messages: users can only access messages in their own conversations
CREATE POLICY "own_messages_select" ON public.chat_messages
  FOR SELECT TO authenticated
  USING (conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid()));

CREATE POLICY "own_messages_insert" ON public.chat_messages
  FOR INSERT TO authenticated
  WITH CHECK (conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid()));

CREATE POLICY "own_messages_update" ON public.chat_messages
  FOR UPDATE TO authenticated
  USING (conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid()));

CREATE POLICY "own_messages_delete" ON public.chat_messages
  FOR DELETE TO authenticated
  USING (conversation_id IN (SELECT id FROM public.conversations WHERE user_id = auth.uid()));

-- Auto-update updated_at on conversations
CREATE OR REPLACE FUNCTION public.update_conversation_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END;
$$ LANGUAGE plpgsql SET search_path = public;

CREATE TRIGGER update_conversations_updated_at
  BEFORE UPDATE ON public.conversations
  FOR EACH ROW
  EXECUTE FUNCTION public.update_conversation_updated_at();

-- Index for faster message lookups
CREATE INDEX idx_chat_messages_conversation ON public.chat_messages(conversation_id);
CREATE INDEX idx_conversations_user ON public.conversations(user_id);