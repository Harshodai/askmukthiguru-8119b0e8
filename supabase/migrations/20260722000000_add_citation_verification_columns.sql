-- ============================================================================
-- REVERT: Drop the citation-verification columns. NOTE: flag values are lost
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- (recomputable by re-running verification).
-- ALTER TABLE public.chat_responses DROP COLUMN IF EXISTS citations_verified;
-- ALTER TABLE public.chat_responses DROP COLUMN IF EXISTS orphan_citations_stripped;
-- ============================================================================

-- Task 2: persist citation post-verification flags per response.
ALTER TABLE public.chat_responses
    ADD COLUMN IF NOT EXISTS citations_verified boolean DEFAULT NULL,
    ADD COLUMN IF NOT EXISTS orphan_citations_stripped boolean DEFAULT NULL;

-- Notify PostgREST to reload its schema cache so the new columns are visible immediately.
NOTIFY pgrst, 'reload schema';
