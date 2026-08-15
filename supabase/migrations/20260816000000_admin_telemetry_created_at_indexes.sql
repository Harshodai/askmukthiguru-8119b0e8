-- ============================================================================
-- REVERT: Indexes only — drop them
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- DROP INDEX IF EXISTS idx_chat_responses_created_at;
-- DROP INDEX IF EXISTS idx_feedback_events_created_at;
-- DROP INDEX IF EXISTS idx_trigger_events_name_created_at;
-- DROP INDEX IF EXISTS idx_safety_events_created_at;
-- ============================================================================

-- Admin dashboard KPI/timeseries endpoints (app/telemetry_db.py: get_kpis,
-- get_timeseries_data, get_trigger_events, get_safety_events) filter and
-- order these tables by created_at on every load, plus one composite
-- predicate -- none of it was covered by the original telemetry schema
-- (20260527060500), which only indexed chat_queries.created_at and the
-- query_id FK columns used for drill-down joins. Every dashboard tile was a
-- sequential scan on its own table:
--
--   chat_responses: get_kpis hallucination_rate + timeseries hallucination_rate
--     both do .gte/.lte("created_at", ...) with no filter that reaches the
--     existing idx_chat_responses_query_id.
--   feedback_events: get_kpis thumbs_up_rate + timeseries thumbs_up_rate,
--     same shape; feedback_events had zero indexes before this migration.
--   trigger_events: get_kpis serene_mind_trigger_rate is
--     .eq("trigger_name","DISTRESS").gte("created_at", ...) -- the existing
--     idx_trigger_events_query_id does not serve this predicate at all.
--   safety_events: get_safety_events .gte/.lte("created_at", ...).order(...),
--     same gap as feedback_events (zero indexes before this migration).

CREATE INDEX IF NOT EXISTS idx_chat_responses_created_at
  ON public.chat_responses(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_feedback_events_created_at
  ON public.feedback_events(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_trigger_events_name_created_at
  ON public.trigger_events(trigger_name, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_safety_events_created_at
  ON public.safety_events(created_at DESC);

-- EXPLAIN verification deferred to CI/prod (no local Supabase available in
-- this sandbox). Row counts on these tables are still small enough that
-- Postgres may keep choosing seq scans regardless until they grow -- these
-- indexes make the range-scan path available, not mandatory.
