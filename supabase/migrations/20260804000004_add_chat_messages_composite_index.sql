-- ============================================================================
-- REVERT: Index only — drop it. The pre-existing idx_chat_messages_conversation
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- (20260506064449) stays untouched.
-- DROP INDEX IF EXISTS idx_chat_messages_conv_created;
-- ============================================================================

-- P1-DB-3: chat_messages(conversation_id, created_at DESC) composite index.
-- Every conversation view lists messages ordered by created_at (created in
-- 20260506064449_d698be63-b027-463b-ba24-a90cec443811.sql); the existing
-- idx_chat_messages_conversation index can serve the filter but not the sort.
-- The new index covers both. Leading column matches the old index, which is
-- kept for any plain (conversation_id) lookups and FK cascade checks.

CREATE INDEX IF NOT EXISTS idx_chat_messages_conv_created
  ON public.chat_messages(conversation_id, created_at DESC);

-- EXPLAIN verification deferred to CI/prod (no local Supabase); index choice
-- mirrors the ORM query shape (filter conversation_id, order created_at DESC).
