-- ============================================================================
-- REVERT: Reverse REPLICA IDENTITY and remove the table from the realtime publication
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- ALTER TABLE public.daily_teachings REPLICA IDENTITY DEFAULT;
-- ALTER PUBLICATION supabase_realtime DROP TABLE public.daily_teachings;
-- ============================================================================

ALTER TABLE public.daily_teachings REPLICA IDENTITY FULL;
ALTER PUBLICATION supabase_realtime ADD TABLE public.daily_teachings;
