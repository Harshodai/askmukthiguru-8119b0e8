-- ============================================================================
-- REVERT: Indexes only — drop them. NOTE: idx_retrieval_events_query_id is also created
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- by 20260527060500; the drop is idempotent either way.
-- DROP INDEX IF EXISTS idx_chat_queries_session_created;
-- DROP INDEX IF EXISTS idx_chat_queries_user_created;
-- DROP INDEX IF EXISTS idx_chat_queries_status_created;
-- DROP INDEX IF EXISTS idx_chat_responses_query_created;
-- DROP INDEX IF EXISTS idx_user_feedback_response_created;
-- DROP INDEX IF EXISTS idx_app_logs_request_id;
-- DROP INDEX IF EXISTS idx_app_logs_level_created;
-- DROP INDEX IF EXISTS idx_retrieval_events_query_id;
-- DROP INDEX IF EXISTS idx_trigger_events_created;
-- ============================================================================

-- Add recommended indexes for admin dashboard & analytics performance
-- Tables: chat_queries, chat_responses, user_feedback, app_logs

-- ============================================================================
-- chat_queries — session, user, and status lookups (admin queries, history)
-- ============================================================================
create index if not exists idx_chat_queries_session_created
  on chat_queries (session_id, created_at desc);

create index if not exists idx_chat_queries_user_created
  on chat_queries (anon_user_id, created_at desc);

create index if not exists idx_chat_queries_status_created
  on chat_queries (status, created_at desc);

-- ============================================================================
-- chat_responses — join+time analytics, hallucination metrics over time
-- ============================================================================
create index if not exists idx_chat_responses_query_created
  on chat_responses (query_id, created_at desc);

-- ============================================================================
-- user_feedback — time-sorted feedback analytics
-- ============================================================================
create index if not exists idx_user_feedback_response_created
  on user_feedback (response_id, created_at desc);

-- ============================================================================
-- app_logs — trace correlation and log-level filtering
-- ============================================================================
create index if not exists idx_app_logs_request_id
  on app_logs (request_id);

create index if not exists idx_app_logs_level_created
  on app_logs (level, created_at desc);

-- ============================================================================
-- retrieval_events & trigger_events — time-sorted analytics
-- ============================================================================
create index if not exists idx_retrieval_events_query_id
  on retrieval_events (query_id);

create index if not exists idx_trigger_events_created
  on trigger_events (created_at desc);
