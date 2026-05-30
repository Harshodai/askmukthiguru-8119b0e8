
-- ===== Column additions =====
ALTER TABLE public.alert_rules
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS window_minutes integer NOT NULL DEFAULT 15,
  ADD COLUMN IF NOT EXISTS channel text NOT NULL DEFAULT 'email',
  ADD COLUMN IF NOT EXISTS target text NOT NULL DEFAULT '';

UPDATE public.alert_rules SET active = enabled WHERE active IS DISTINCT FROM enabled;

ALTER TABLE public.alert_events
  ADD COLUMN IF NOT EXISTS rule_name text,
  ADD COLUMN IF NOT EXISTS resolved_at timestamptz;

ALTER TABLE public.eval_runs
  ADD COLUMN IF NOT EXISTS triggered_by text NOT NULL DEFAULT 'manual',
  ADD COLUMN IF NOT EXISTS prompt_version_id uuid;

ALTER TABLE public.golden_questions
  ADD COLUMN IF NOT EXISTS active boolean NOT NULL DEFAULT true,
  ADD COLUMN IF NOT EXISTS expected_sources text[] NOT NULL DEFAULT '{}'::text[];

ALTER TABLE public.annotations
  ADD COLUMN IF NOT EXISTS label text,
  ADD COLUMN IF NOT EXISTS notes text,
  ADD COLUMN IF NOT EXISTS promoted_to_golden boolean NOT NULL DEFAULT false,
  ADD COLUMN IF NOT EXISTS response_id uuid;

ALTER TABLE public.safety_events
  ADD COLUMN IF NOT EXISTS type text,
  ADD COLUMN IF NOT EXISTS excerpt text;

ALTER TABLE public.ingestion_runs
  ADD COLUMN IF NOT EXISTS duration_ms integer NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS error_log text;

ALTER TABLE public.app_logs
  ADD COLUMN IF NOT EXISTS request_id text NOT NULL DEFAULT '';

-- ===== Admin management RPCs =====
CREATE OR REPLACE FUNCTION public.list_admins()
RETURNS TABLE(id uuid, email text, created_at timestamptz)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RAISE EXCEPTION 'not_admin';
  END IF;

  RETURN QUERY
  SELECT u.id, u.email::text, u.created_at
  FROM public.user_roles r
  JOIN auth.users u ON u.id = r.user_id
  WHERE r.role = 'admin'::public.app_role
  ORDER BY u.created_at;
END;
$$;

CREATE OR REPLACE FUNCTION public.promote_admin_by_email(_email text)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
DECLARE
  uid uuid;
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  SELECT id INTO uid FROM auth.users WHERE lower(email) = lower(_email) LIMIT 1;
  IF uid IS NULL THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'user_not_found');
  END IF;

  INSERT INTO public.user_roles (user_id, role)
  VALUES (uid, 'admin'::public.app_role)
  ON CONFLICT (user_id, role) DO NOTHING;

  RETURN jsonb_build_object('ok', true, 'user_id', uid);
END;
$$;

CREATE OR REPLACE FUNCTION public.demote_admin_by_id(_user_id uuid)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  IF _user_id = auth.uid() THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'cannot_demote_self');
  END IF;

  DELETE FROM public.user_roles WHERE user_id = _user_id AND role = 'admin'::public.app_role;
  RETURN jsonb_build_object('ok', true);
END;
$$;

-- ===== Extended seed =====
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
  pv1 UUID := gen_random_uuid();
  pv2 UUID := gen_random_uuid();
  rule1 UUID := gen_random_uuid();
  run1 UUID := gen_random_uuid();
  req_id TEXT := encode(gen_random_bytes(6), 'hex');
  i INT;
BEGIN
  IF NOT public.has_role(auth.uid(), 'admin'::public.app_role) THEN
    RETURN jsonb_build_object('ok', false, 'reason', 'not_admin');
  END IF;

  -- Prompt versions
  INSERT INTO public.prompt_versions (id, name, version, body, active)
  VALUES (pv1, 'guru_default', 1, 'You are Sri Preethaji...', false)
  ON CONFLICT DO NOTHING;
  INSERT INTO public.prompt_versions (id, name, version, body, active)
  VALUES (pv2, 'guru_default', 2, 'You are Sri Preethaji & Sri Krishnaji...', true)
  ON CONFLICT DO NOTHING;

  -- Full trace tied to v2
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, prompt_tokens, completion_tokens, cost_estimate, prompt_version_id)
  VALUES (q_full, 'What is the Beautiful State?', 'sarvam-30b', 'ok', 1850, 420, 180, 0.0012, pv2);
  INSERT INTO public.chat_responses (query_id, response_text, citations, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, confidence, judge_reasoning)
  VALUES (q_full, 'The Beautiful State is a state of inner calm, joy, and connection.',
          '[{"source":"YT:abc123","title":"Intro to Beautiful State"}]'::jsonb,
          0.94, 0.91, 0.88, 0.85, false, 0.92, 'Faithfully grounded.');
  INSERT INTO public.retrieval_events (query_id, source_docs, scores)
  VALUES (q_full, ARRAY['YT:abc123#1','YT:abc123#2','YT:def456#1'], ARRAY[0.92, 0.88, 0.81]);
  INSERT INTO public.trace_spans (query_id, span_name, start_ms, duration_ms) VALUES
    (q_full, 'safety_check', 0, 40),
    (q_full, 'retrieve_documents', 40, 620),
    (q_full, 'rerank_documents', 660, 180),
    (q_full, 'generate_answer', 840, 900),
    (q_full, 'verify_answer', 1740, 110);
  INSERT INTO public.trigger_events (query_id, trigger_type, trigger_name) VALUES (q_full, 'retrieval', 'high_confidence');

  -- Partial: no response
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, prompt_version_id)
  VALUES (q_no_response, 'How do I begin meditation?', 'sarvam-30b', 'error', 320, pv2);

  -- Partial: no retrieval, low confidence
  INSERT INTO public.chat_queries (id, query_text, model, status, latency_ms, cost_estimate, prompt_version_id)
  VALUES (q_no_retrieval, 'Tell me about Sri Krishnaji.', 'sarvam-30b', 'ok', 1100, 0.0006, pv1);
  INSERT INTO public.chat_responses (query_id, response_text, citations, faithfulness, answer_relevancy, context_precision, context_recall, hallucination_flag, confidence, judge_reasoning)
  VALUES (q_no_retrieval, 'Sri Krishnaji is a co-founder of the O&O Academy.', '[]'::jsonb, 0.40, 0.55, 0.50, 0.45, true, 0.45, 'Low retrieval — likely hallucinated.');

  -- 7-day trigger trend (one per day)
  FOR i IN 0..6 LOOP
    INSERT INTO public.trigger_events (query_id, trigger_type, trigger_name, created_at)
    VALUES (q_full, 'meditation', CASE WHEN i % 2 = 0 THEN 'serene_mind' ELSE 'fallback' END, now() - (i || ' days')::interval);
  END LOOP;

  -- Alert rule + fired event
  INSERT INTO public.alert_rules (id, name, metric, comparator, threshold, enabled, active, window_minutes, channel, target)
  VALUES (rule1, 'High hallucination rate', 'hallucination_rate', '>', 0.15, true, true, 60, 'email', 'admin@example.com')
  ON CONFLICT DO NOTHING;
  INSERT INTO public.alert_events (rule_id, rule_name, value, message, fired_at)
  VALUES (rule1, 'High hallucination rate', 0.22, 'Hallucination rate above 15% in last hour', now() - interval '2 hours');

  -- Eval run + golden question
  INSERT INTO public.eval_runs (id, name, status, summary, triggered_by, prompt_version_id, started_at, finished_at)
  VALUES (run1, 'Nightly RAGAS', 'ok',
    jsonb_build_object('total', 25, 'passed', 22, 'avg_faithfulness', 0.89, 'avg_answer_relevancy', 0.86, 'avg_context_precision', 0.83, 'avg_context_recall', 0.81),
    'scheduled', pv2, now() - interval '1 day', now() - interval '23 hours');

  INSERT INTO public.golden_questions (question, expected_answer, tags, active, expected_sources)
  VALUES ('What is the Beautiful State?', 'A state of inner calm, joy, connection.', ARRAY['core','teaching'], true, ARRAY['YT:abc123']);

  -- Ingestion run
  INSERT INTO public.ingestion_runs (source, status, chunks_added, duration_ms)
  VALUES ('https://youtu.be/sample123', 'ok', 42, 18500);

  -- Annotation
  INSERT INTO public.annotations (query_id, body, label, notes, promoted_to_golden)
  VALUES (q_full, 'Reviewer notes', 'good', 'Clear and grounded answer.', true);

  -- Safety event
  INSERT INTO public.safety_events (query_id, rule, severity, action, type, excerpt)
  VALUES (q_no_retrieval, 'low_confidence_output', 'medium', 'flagged', 'pii_output', 'Sri Krishnaji is a co-founder...');

  -- App logs sharing a request_id
  INSERT INTO public.app_logs (level, message, context, request_id) VALUES
    ('info', 'chat request received', jsonb_build_object('user', 'demo'), req_id),
    ('info', 'retrieval ok', jsonb_build_object('k', 3), req_id),
    ('warn', 'low confidence answer', jsonb_build_object('confidence', 0.45), req_id);

  -- Topic cluster
  INSERT INTO public.query_clusters (label, size, centroid)
  VALUES ('Beautiful State teachings', 12, '{"x":0.1,"y":0.2}'::jsonb);

  RETURN jsonb_build_object(
    'ok', true,
    'full_trace_id', q_full,
    'missing_response_id', q_no_response,
    'missing_retrieval_id', q_no_retrieval,
    'request_id', req_id
  );
END;
$$;

GRANT EXECUTE ON FUNCTION public.list_admins() TO authenticated;
GRANT EXECUTE ON FUNCTION public.promote_admin_by_email(text) TO authenticated;
GRANT EXECUTE ON FUNCTION public.demote_admin_by_id(uuid) TO authenticated;
