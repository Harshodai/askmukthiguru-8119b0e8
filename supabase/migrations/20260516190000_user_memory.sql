-- Migration to create user_profiles and conversation_memories tables
-- Supporting Seeker Continuity and Multi-Session Memory

CREATE TABLE IF NOT EXISTS public.user_profiles (
  user_id uuid PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
  preferred_language text DEFAULT 'en',
  spiritual_level text DEFAULT 'beginner',
  topics_of_interest text[] DEFAULT '{}',
  last_distress_assessment jsonb DEFAULT '{}',
  total_conversations int DEFAULT 0,
  total_meditations_completed int DEFAULT 0,
  favorite_teachings text[] DEFAULT '{}',
  codemix_preference boolean DEFAULT false,
  created_at float8 NOT NULL,
  updated_at float8 NOT NULL
);

CREATE TABLE IF NOT EXISTS public.conversation_memories (
  session_id uuid PRIMARY KEY,
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  started_at float8 NOT NULL,
  messages jsonb DEFAULT '[]',
  key_insights text[] DEFAULT '{}',
  emotional_arc jsonb DEFAULT '[]',
  follow_up_suggestions text[] DEFAULT '{}'
);

-- Enable RLS
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.conversation_memories ENABLE ROW LEVEL SECURITY;

-- Policies for user_profiles
DROP POLICY IF EXISTS "Users can see their own profiles" ON public.user_profiles;
CREATE POLICY "Users can see their own profiles" ON public.user_profiles
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update their own profiles" ON public.user_profiles;
CREATE POLICY "Users can update their own profiles" ON public.user_profiles
  FOR ALL USING (auth.uid() = user_id);

-- Policies for conversation_memories
DROP POLICY IF EXISTS "Users can see their own memories" ON public.conversation_memories;
CREATE POLICY "Users can see their own memories" ON public.conversation_memories
  FOR SELECT USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can insert their own memories" ON public.conversation_memories;
CREATE POLICY "Users can insert their own memories" ON public.conversation_memories
  FOR ALL USING (auth.uid() = user_id);

-- Admin overrides
DROP POLICY IF EXISTS "Admins can read all profiles" ON public.user_profiles;
CREATE POLICY "Admins can read all profiles" ON public.user_profiles
  FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'::public.app_role));

DROP POLICY IF EXISTS "Admins can read all memories" ON public.conversation_memories;
CREATE POLICY "Admins can read all memories" ON public.conversation_memories
  FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'::public.app_role));
