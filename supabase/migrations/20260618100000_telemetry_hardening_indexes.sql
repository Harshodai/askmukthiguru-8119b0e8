-- Telemetry hardening: add indexes for faster writes and common query patterns
-- 1. Composite index for user/session filtering (most common admin query)
-- 2. Index for metric_type time-series queries
-- 3. Index for session-based lookups

CREATE INDEX IF NOT EXISTS telemetry_events_user_session_created_idx
  ON public.telemetry_events(user_id, session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_events_metric_type_created_idx
  ON public.telemetry_events(metric_type, created_at DESC);

CREATE INDEX IF NOT EXISTS telemetry_events_session_created_idx
  ON public.telemetry_events(session_id, created_at DESC);

-- Force reload of PostgREST schema cache
NOTIFY pgrst, 'reload schema';