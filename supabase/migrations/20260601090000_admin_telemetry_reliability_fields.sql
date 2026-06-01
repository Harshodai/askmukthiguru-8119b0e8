-- Reliability telemetry fields for admin console, streaming, model routing, and eval traces.

ALTER TABLE public.chat_queries
  ADD COLUMN IF NOT EXISTS session_id uuid,
  ADD COLUMN IF NOT EXISTS provider text,
  ADD COLUMN IF NOT EXISTS route_decision text,
  ADD COLUMN IF NOT EXISTS cache_hit boolean,
  ADD COLUMN IF NOT EXISTS ttft_ms integer,
  ADD COLUMN IF NOT EXISTS tokens_per_second numeric;

ALTER TABLE public.chat_responses
  ADD COLUMN IF NOT EXISTS evaluation_trace jsonb DEFAULT '{}'::jsonb;

ALTER TABLE public.retrieval_events
  ADD COLUMN IF NOT EXISTS chunk_ids text[] DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS top_k integer,
  ADD COLUMN IF NOT EXISTS retrieval_hit boolean;

ALTER TABLE public.trace_spans
  ADD COLUMN IF NOT EXISTS attributes jsonb DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_chat_queries_model_created_at
  ON public.chat_queries(model, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_chat_queries_route_created_at
  ON public.chat_queries(route_decision, created_at DESC);

