-- ============================================================================
-- REVERT: Drop the three columns. NOTE: claim/confidence values are lost (decay_score
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- was defaulted 1.0). memory_service.py retries writes without these columns, so
-- downgrade is safe for the app.
-- ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS claim;
-- ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS confidence;
-- ALTER TABLE public.guru_memories DROP COLUMN IF EXISTS decay_score;
-- ============================================================================

-- Add missing columns to guru_memories that were defined in 20260618044620 but
-- never applied because CREATE TABLE IF NOT EXISTS skipped the existing table.
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS claim TEXT;
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS confidence DOUBLE PRECISION;
ALTER TABLE public.guru_memories ADD COLUMN IF NOT EXISTS decay_score DOUBLE PRECISION DEFAULT 1.0;
