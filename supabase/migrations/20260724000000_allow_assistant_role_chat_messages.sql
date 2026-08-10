-- ============================================================================
-- REVERT: Restore the two-role CHECK constraint
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- ALTER TABLE public.chat_messages DROP CONSTRAINT IF EXISTS chat_messages_role_check;
-- ALTER TABLE public.chat_messages ADD CONSTRAINT chat_messages_role_check CHECK (role IN ('user', 'guru'));
-- NOTE: existing 'assistant' rows violate the restored constraint — clean them
-- first if any exist.
-- ============================================================================

ALTER TABLE public.chat_messages DROP CONSTRAINT IF EXISTS chat_messages_role_check;
ALTER TABLE public.chat_messages ADD CONSTRAINT chat_messages_role_check CHECK (role IN ('user', 'guru', 'assistant'));
