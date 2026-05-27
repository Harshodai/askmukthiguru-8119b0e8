
-- ============================================================================
-- Admin telemetry schema
-- ============================================================================

-- chat_queries
CREATE TABLE IF NOT EXISTS public.chat_queries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID,
  query_text TEXT NOT NULL,
  model TEXT,
  status TEXT NOT NULL DEFAULT 'ok',
  latency_ms INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cost_estimate NUMERIC,
  prompt_version_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.chat_queries TO authenticated;
GRANT ALL ON public.chat_queries TO service_role;
ALTER TABLE public.chat_queries ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read chat_queries" ON public.chat_queries FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- chat_responses
CREATE TABLE IF NOT EXISTS public.chat_responses (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID NOT NULL,
  response_text TEXT,
  citations JSONB DEFAULT '[]'::jsonb,
  faithfulness NUMERIC,
  answer_relevancy NUMERIC,
  context_precision NUMERIC,
  context_recall NUMERIC,
  hallucination_flag BOOLEAN DEFAULT false,
  confidence NUMERIC,
  judge_reasoning TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.chat_responses TO authenticated;
GRANT ALL ON public.chat_responses TO service_role;
ALTER TABLE public.chat_responses ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read chat_responses" ON public.chat_responses FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- retrieval_events
CREATE TABLE IF NOT EXISTS public.retrieval_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID NOT NULL,
  source_docs TEXT[] DEFAULT '{}',
  scores NUMERIC[] DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.retrieval_events TO authenticated;
GRANT ALL ON public.retrieval_events TO service_role;
ALTER TABLE public.retrieval_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read retrieval_events" ON public.retrieval_events FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- trace_spans
CREATE TABLE IF NOT EXISTS public.trace_spans (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID NOT NULL,
  span_name TEXT NOT NULL,
  start_ms INTEGER NOT NULL DEFAULT 0,
  duration_ms INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.trace_spans TO authenticated;
GRANT ALL ON public.trace_spans TO service_role;
ALTER TABLE public.trace_spans ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read trace_spans" ON public.trace_spans FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- trigger_events
CREATE TABLE IF NOT EXISTS public.trigger_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID,
  trigger_type TEXT NOT NULL,
  trigger_name TEXT,
  payload JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.trigger_events TO authenticated;
GRANT ALL ON public.trigger_events TO service_role;
ALTER TABLE public.trigger_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read trigger_events" ON public.trigger_events FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- safety_events
CREATE TABLE IF NOT EXISTS public.safety_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID,
  rule TEXT NOT NULL,
  severity TEXT,
  action TEXT,
  details JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.safety_events TO authenticated;
GRANT ALL ON public.safety_events TO service_role;
ALTER TABLE public.safety_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read safety_events" ON public.safety_events FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- prompt_versions
CREATE TABLE IF NOT EXISTS public.prompt_versions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  body TEXT,
  active BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.prompt_versions TO authenticated;
GRANT ALL ON public.prompt_versions TO service_role;
ALTER TABLE public.prompt_versions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read prompt_versions" ON public.prompt_versions FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins write prompt_versions" ON public.prompt_versions FOR ALL TO authenticated USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- alert_rules
CREATE TABLE IF NOT EXISTS public.alert_rules (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  metric TEXT NOT NULL,
  threshold NUMERIC,
  comparator TEXT,
  enabled BOOLEAN NOT NULL DEFAULT true,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.alert_rules TO authenticated;
GRANT ALL ON public.alert_rules TO service_role;
ALTER TABLE public.alert_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read alert_rules" ON public.alert_rules FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins write alert_rules" ON public.alert_rules FOR ALL TO authenticated USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- alert_events
CREATE TABLE IF NOT EXISTS public.alert_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_id UUID,
  fired_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  value NUMERIC,
  message TEXT
);
GRANT SELECT ON public.alert_events TO authenticated;
GRANT ALL ON public.alert_events TO service_role;
ALTER TABLE public.alert_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read alert_events" ON public.alert_events FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- annotations
CREATE TABLE IF NOT EXISTS public.annotations (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID,
  author_id UUID,
  body TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.annotations TO authenticated;
GRANT ALL ON public.annotations TO service_role;
ALTER TABLE public.annotations ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read annotations" ON public.annotations FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins write annotations" ON public.annotations FOR ALL TO authenticated USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- app_logs
CREATE TABLE IF NOT EXISTS public.app_logs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  level TEXT NOT NULL DEFAULT 'info',
  message TEXT NOT NULL,
  context JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.app_logs TO authenticated;
GRANT ALL ON public.app_logs TO service_role;
ALTER TABLE public.app_logs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read app_logs" ON public.app_logs FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- eval_runs
CREATE TABLE IF NOT EXISTS public.eval_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at TIMESTAMPTZ,
  summary JSONB DEFAULT '{}'::jsonb
);
GRANT SELECT ON public.eval_runs TO authenticated;
GRANT ALL ON public.eval_runs TO service_role;
ALTER TABLE public.eval_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read eval_runs" ON public.eval_runs FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- eval_results
CREATE TABLE IF NOT EXISTS public.eval_results (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id UUID,
  question TEXT,
  answer TEXT,
  score NUMERIC,
  metrics JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.eval_results TO authenticated;
GRANT ALL ON public.eval_results TO service_role;
ALTER TABLE public.eval_results ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read eval_results" ON public.eval_results FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- golden_questions
CREATE TABLE IF NOT EXISTS public.golden_questions (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question TEXT NOT NULL,
  expected_answer TEXT,
  tags TEXT[] DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.golden_questions TO authenticated;
GRANT ALL ON public.golden_questions TO service_role;
ALTER TABLE public.golden_questions ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read golden_questions" ON public.golden_questions FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins write golden_questions" ON public.golden_questions FOR ALL TO authenticated USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- ingestion_runs
CREATE TABLE IF NOT EXISTS public.ingestion_runs (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending',
  chunks_added INTEGER DEFAULT 0,
  details JSONB DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.ingestion_runs TO authenticated;
GRANT ALL ON public.ingestion_runs TO service_role;
ALTER TABLE public.ingestion_runs ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read ingestion_runs" ON public.ingestion_runs FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- model_pricing
CREATE TABLE IF NOT EXISTS public.model_pricing (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  model TEXT NOT NULL UNIQUE,
  input_per_1k NUMERIC NOT NULL DEFAULT 0,
  output_per_1k NUMERIC NOT NULL DEFAULT 0,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.model_pricing TO authenticated;
GRANT ALL ON public.model_pricing TO service_role;
ALTER TABLE public.model_pricing ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read model_pricing" ON public.model_pricing FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins write model_pricing" ON public.model_pricing FOR ALL TO authenticated USING (public.has_role(auth.uid(), 'admin')) WITH CHECK (public.has_role(auth.uid(), 'admin'));

-- query_clusters
CREATE TABLE IF NOT EXISTS public.query_clusters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  label TEXT NOT NULL,
  size INTEGER NOT NULL DEFAULT 0,
  centroid JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.query_clusters TO authenticated;
GRANT ALL ON public.query_clusters TO service_role;
ALTER TABLE public.query_clusters ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read query_clusters" ON public.query_clusters FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- user_profiles (admin telemetry view of seekers — separate from public.profiles)
CREATE TABLE IF NOT EXISTS public.user_profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL UNIQUE,
  first_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen TIMESTAMPTZ NOT NULL DEFAULT now(),
  total_queries INTEGER NOT NULL DEFAULT 0
);
GRANT SELECT ON public.user_profiles TO authenticated;
GRANT ALL ON public.user_profiles TO service_role;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read user_profiles" ON public.user_profiles FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- feedback_events
CREATE TABLE IF NOT EXISTS public.feedback_events (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  query_id UUID,
  user_id UUID,
  rating INTEGER NOT NULL DEFAULT 0,
  comment TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT, INSERT ON public.feedback_events TO authenticated;
GRANT ALL ON public.feedback_events TO service_role;
ALTER TABLE public.feedback_events ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read feedback_events" ON public.feedback_events FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "users insert feedback" ON public.feedback_events FOR INSERT TO authenticated WITH CHECK (auth.uid() = user_id);

-- Indexes for drill-down performance
CREATE INDEX IF NOT EXISTS idx_chat_responses_query_id ON public.chat_responses(query_id);
CREATE INDEX IF NOT EXISTS idx_retrieval_events_query_id ON public.retrieval_events(query_id);
CREATE INDEX IF NOT EXISTS idx_trace_spans_query_id ON public.trace_spans(query_id);
CREATE INDEX IF NOT EXISTS idx_trigger_events_query_id ON public.trigger_events(query_id);
CREATE INDEX IF NOT EXISTS idx_safety_events_query_id ON public.safety_events(query_id);
CREATE INDEX IF NOT EXISTS idx_chat_queries_created_at ON public.chat_queries(created_at DESC);

-- ============================================================================
-- Seed function for admin drill-down demo (admin-only)
-- ============================================================================
CREATE OR REPLACE FUNCTION public.seed_admin_demo()
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  q_full UUID := gen_random_uuid();
  q_no_response UUID := gen_random_uuid();
  q_no_retrieval UUID := gen_random_uuid();
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  -- Full trace
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, prompt_tokens, completion_tokens, cost_estimate)
  VALUES (q_full, 'What is the Beautiful State?', 'sarvam-30b', 'ok', 1850, 420, 180, 0.0012);
  INSERT INTO public.chat_responses (query_id, response_text, citations, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, confidence, judge_reasoning)
  VALUES (q_full, 'The Beautiful State is a state of inner calm, joy, and connection taught by Sri Preethaji & Sri Krishnaji.',
          '[{"source":"YT:abc123","title":"Intro to Beautiful State"}]'::jsonb,
          0.94, 0.91, 0.88, 0.85, false, 0.92, 'Answer faithfully grounded in retrieved teachings.');
  INSERT INTO public.retrieval_events (query_id, source_docs, scores)
  VALUES (q_full, ARRAY['Beautiful State teaching #1', 'Beautiful State teaching #2', 'Beautiful State teaching #3'], ARRAY[0.92, 0.88, 0.81]);
  INSERT INTO public.trace_spans (query_id, span_name, start_ms, duration_ms) VALUES
    (q_full, 'safety_check', 0, 40),
    (q_full, 'retrieve_documents', 40, 620),
    (q_full, 'rerank_documents', 660, 180),
    (q_full, 'generate_answer', 840, 900),
    (q_full, 'verify_answer', 1740, 110);
  INSERT INTO public.trigger_events (query_id, trigger_type, trigger_name) VALUES (q_full, 'retrieval', 'high_confidence');

  -- Partial trace: query only (no response, no retrieval)
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms)
  VALUES (q_no_response, 'How do I begin meditation?', 'sarvam-30b', 'error', 320);

  -- Partial trace: query + response but no retrieval rows
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, cost_estimate)
  VALUES (q_no_retrieval, 'Tell me about Sri Krishnaji.', 'sarvam-30b', 'ok', 1100, 0.0006);
  INSERT INTO public.chat_responses (query_id, response_text, citations, faithfulness, hallucination_flag, confidence, judge_reasoning)
  VALUES (q_no_retrieval, 'Sri Krishnaji is a co-founder of the O&O Academy.', '[]'::jsonb, 0.40, true, 0.45, 'Low retrieval — answer may be hallucinated.');

  RETURN jsonb_build_object(
    'ok', true,
    'full_trace_id', q_full,
    'missing_response_id', q_no_response,
    'missing_retrieval_id', q_no_retrieval
  );
END;
$$;

REVOKE EXECUTE ON FUNCTION public.seed_admin_demo() FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.seed_admin_demo() TO authenticated;
