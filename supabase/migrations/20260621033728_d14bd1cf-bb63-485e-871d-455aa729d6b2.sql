
-- NOTES
CREATE TABLE public.notes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT 'Untitled',
  body TEXT NOT NULL DEFAULT '',
  tags TEXT[] NOT NULL DEFAULT '{}',
  source_message_id TEXT,
  source_conversation_id UUID,
  is_favorite BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.notes TO authenticated;
GRANT ALL ON public.notes TO service_role;
ALTER TABLE public.notes ENABLE ROW LEVEL SECURITY;
CREATE POLICY "notes_own_select" ON public.notes FOR SELECT TO authenticated USING (auth.uid() = user_id);
CREATE POLICY "notes_own_insert" ON public.notes FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);
CREATE POLICY "notes_own_update" ON public.notes FOR UPDATE TO authenticated USING (auth.uid() = user_id) WITH CHECK (auth.uid() = user_id);
CREATE POLICY "notes_own_delete" ON public.notes FOR DELETE TO authenticated USING (auth.uid() = user_id);
CREATE TRIGGER notes_touch_updated_at BEFORE UPDATE ON public.notes FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();
CREATE INDEX notes_user_updated_idx ON public.notes(user_id, updated_at DESC);

-- ASSISTANTS
CREATE TYPE public.assistant_visibility AS ENUM ('public', 'link', 'private');

CREATE TABLE public.assistants (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  avatar_url TEXT,
  system_prompt TEXT NOT NULL DEFAULT '',
  starter_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  knowledge_tags TEXT[] NOT NULL DEFAULT '{}',
  visibility public.assistant_visibility NOT NULL DEFAULT 'public',
  invite_code TEXT UNIQUE,
  created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.assistants TO authenticated, anon;
GRANT INSERT, UPDATE, DELETE ON public.assistants TO authenticated;
GRANT ALL ON public.assistants TO service_role;
ALTER TABLE public.assistants ENABLE ROW LEVEL SECURITY;
CREATE TRIGGER assistants_touch BEFORE UPDATE ON public.assistants FOR EACH ROW EXECUTE FUNCTION public.touch_updated_at();

-- ASSISTANT ACCESS (must exist before assistants policies reference it)
CREATE TABLE public.assistant_access (
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  assistant_id UUID NOT NULL REFERENCES public.assistants(id) ON DELETE CASCADE,
  granted_via TEXT NOT NULL DEFAULT 'invite',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, assistant_id)
);
GRANT SELECT ON public.assistant_access TO authenticated;
GRANT ALL ON public.assistant_access TO service_role;
ALTER TABLE public.assistant_access ENABLE ROW LEVEL SECURITY;
CREATE POLICY "assistant_access_own_select" ON public.assistant_access FOR SELECT TO authenticated USING (user_id = auth.uid());

-- ASSISTANTS policies (now safe to reference assistant_access)
CREATE POLICY "assistants_read_public" ON public.assistants FOR SELECT TO anon, authenticated USING (visibility = 'public');
CREATE POLICY "assistants_read_granted" ON public.assistants FOR SELECT TO authenticated
  USING (visibility <> 'public' AND EXISTS (SELECT 1 FROM public.assistant_access a WHERE a.assistant_id = assistants.id AND a.user_id = auth.uid()));
CREATE POLICY "assistants_read_own" ON public.assistants FOR SELECT TO authenticated USING (created_by = auth.uid());
CREATE POLICY "assistants_insert_own" ON public.assistants FOR INSERT TO authenticated WITH CHECK (created_by = auth.uid());
CREATE POLICY "assistants_update_own" ON public.assistants FOR UPDATE TO authenticated USING (created_by = auth.uid()) WITH CHECK (created_by = auth.uid());
CREATE POLICY "assistants_delete_own" ON public.assistants FOR DELETE TO authenticated USING (created_by = auth.uid());

ALTER TABLE public.conversations ADD COLUMN IF NOT EXISTS assistant_id UUID REFERENCES public.assistants(id) ON DELETE SET NULL;

-- Seed built-in assistants
INSERT INTO public.assistants (slug, name, description, system_prompt, starter_questions, knowledge_tags, visibility)
VALUES
  ('general', 'General Guru', 'Wisdom from Sri Preethaji & Sri Krishnaji for everyday life.',
    'You are AskMukthiGuru, channeling the teachings of Sri Preethaji & Sri Krishnaji. Respond with warmth, clarity, and grounded wisdom.',
    '["What is the Beautiful State?","How do I quiet my mind?","Help me find peace with a difficult relationship.","How do I begin a daily practice?"]'::jsonb,
    ARRAY['general']::text[], 'public'),
  ('relationship', 'Relationship Guidance', 'Compassionate guidance for love, family, and connection.',
    'You are a relationship guide rooted in Sri Preethaji & Sri Krishnaji''s teachings. Focus on connection, forgiveness, and beautiful states in relationships.',
    '["My partner and I keep fighting — what should I do?","How do I forgive a parent who hurt me?","How can I be more present with my children?","I feel lonely in my marriage."]'::jsonb,
    ARRAY['relationship','connection']::text[], 'public'),
  ('sky', 'SKY Teachings (Private)', 'Unreleased private teachings — invite only.',
    'You are a guide drawing from SKY private teachings. Be direct and intimate; speak only from this corpus.',
    '["What is the essence of SKY?","Guide me through today''s SKY practice.","What does SKY say about suffering?","Share a SKY meditation."]'::jsonb,
    ARRAY['sky','private']::text[], 'link')
ON CONFLICT (slug) DO NOTHING;
