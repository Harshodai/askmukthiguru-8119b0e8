-- AskMukthiGuru Master Production Schema
-- This script initializes all tables for User Profiles, Admin Telemetry, and RAG Observability.
-- Run this in your Supabase SQL Editor.

-- ============================================================================
-- 1. ROLES & PERMISSIONS
-- ============================================================================
DO $$ BEGIN
    CREATE TYPE public.app_role AS ENUM ('admin', 'user');
EXCEPTION
    WHEN duplicate_object THEN null;
END $$;

CREATE TABLE IF NOT EXISTS public.user_roles (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE NOT NULL,
  role app_role NOT NULL,
  UNIQUE (user_id, role)
);

ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION public.has_role(_user_id uuid, _role app_role)
RETURNS boolean LANGUAGE sql STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (
    SELECT 1 FROM public.user_roles
    WHERE user_id = _user_id AND role = _role
  )
$$;

DROP POLICY IF EXISTS "Admins can read user_roles" ON public.user_roles;
CREATE POLICY "Admins can read user_roles" ON public.user_roles
  FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- ============================================================================
-- 2. USER PROFILES (Spiritual Persona)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.user_profiles (
    user_id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    preferred_language VARCHAR(20) DEFAULT 'en',
    spiritual_level VARCHAR(30) DEFAULT 'beginner',
    topics_of_interest TEXT[] DEFAULT '{}',
    last_distress_assessment JSONB,
    total_conversations INTEGER DEFAULT 0,
    total_meditations_completed INTEGER DEFAULT 0,
    favorite_teachings TEXT[] DEFAULT '{}',
    codemix_preference BOOLEAN DEFAULT FALSE,
    tts_enabled BOOLEAN DEFAULT FALSE,
    tts_rate NUMERIC DEFAULT 1.0
);

ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can manage their own profile" ON public.user_profiles;
CREATE POLICY "Users can manage their own profile" ON public.user_profiles
    FOR ALL TO authenticated USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Admins can read all profiles" ON public.user_profiles;
CREATE POLICY "Admins can read all profiles" ON public.user_profiles
    FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- ============================================================================
-- 3. CORE TELEMETRY (Sessions & Queries)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.chat_sessions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid REFERENCES auth.users(id) ON DELETE CASCADE,
  anon_user_id text, 
  channel text,
  started_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.prompt_versions (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  name text NOT NULL, 
  version int NOT NULL,
  content text NOT NULL, 
  active boolean DEFAULT false,
  created_at timestamptz DEFAULT now(), 
  created_by uuid,
  UNIQUE (name, version)
);

CREATE TABLE IF NOT EXISTS public.chat_queries (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid REFERENCES chat_sessions(id) ON DELETE CASCADE,
  user_id uuid REFERENCES auth.users(id) ON DELETE SET NULL,
  anon_user_id text,
  query_text text NOT NULL,
  prompt_version_id uuid REFERENCES prompt_versions(id),
  model text, 
  prompt_tokens int, 
  completion_tokens int,
  cost_estimate numeric, 
  latency_ms int, 
  status text,
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.chat_responses (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id uuid REFERENCES chat_queries(id) ON DELETE CASCADE,
  response_text text, 
  citations jsonb,
  faithfulness numeric, 
  answer_relevancy numeric,
  context_precision numeric, 
  context_recall numeric,
  hallucination_flag boolean, 
  judge_reasoning text, 
  confidence numeric,
  created_at timestamptz DEFAULT now()
);

-- ============================================================================
-- 4. RAG OBSERVABILITY (Retrieval & Triggers)
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.retrieval_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id uuid REFERENCES chat_queries(id) ON DELETE CASCADE,
  chunk_ids text[], 
  source_docs text[], 
  scores numeric[],
  top_k int, 
  retrieval_hit boolean
);

CREATE TABLE IF NOT EXISTS public.trigger_events (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id uuid REFERENCES chat_queries(id) ON DELETE CASCADE,
  trigger_name text NOT NULL,
  metadata jsonb, 
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.user_feedback (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id uuid REFERENCES chat_responses(id) ON DELETE CASCADE,
  rating smallint, 
  accuracy smallint, 
  comment text,
  created_at timestamptz DEFAULT now()
);

-- ============================================================================
-- 5. SYSTEM LOGS & CONFIG
-- ============================================================================
CREATE TABLE IF NOT EXISTS public.app_logs (
  id bigserial PRIMARY KEY,
  level text, 
  message text, 
  context jsonb,
  request_id text, 
  created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.model_pricing (
  model text PRIMARY KEY,
  input_per_1k numeric, 
  output_per_1k numeric, 
  currency text DEFAULT 'USD'
);

-- ============================================================================
-- 6. SECURITY & RLS (Admin Only)
-- ============================================================================
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'chat_sessions','prompt_versions','chat_queries','retrieval_events',
    'chat_responses','trigger_events','user_feedback',
    'app_logs','model_pricing'
  ]) LOOP
    EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format(
      'DROP POLICY IF EXISTS "Admins can read %1$s" ON public.%1$I', t);
    EXECUTE format(
      $f$CREATE POLICY "Admins can read %1$s" ON public.%1$I
         FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'))$f$, t);
  END LOOP;
END $$;

-- ============================================================================
-- 7. INDEXES
-- ============================================================================
CREATE INDEX IF NOT EXISTS idx_chat_queries_created_at ON chat_queries (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_chat_responses_hallucination ON chat_responses (hallucination_flag, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trigger_events_name ON trigger_events (trigger_name, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_app_logs_created_at ON app_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_profiles_updated_at ON user_profiles (updated_at DESC);

-- ============================================================================
-- 8. REALTIME (Optional)
-- ============================================================================
DO $$ BEGIN
  ALTER PUBLICATION supabase_realtime ADD TABLE chat_queries;
EXCEPTION WHEN OTHERS THEN NULL;
END $$;
