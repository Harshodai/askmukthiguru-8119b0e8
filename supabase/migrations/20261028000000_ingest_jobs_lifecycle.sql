-- ============================================================================
-- REVERT: Drop columns and indexes added for ingest jobs lifecycle.
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
--
-- REVERT:
-- DROP INDEX IF EXISTS public.idx_ingest_jobs_status_heartbeat_at;
-- ALTER TABLE public.ingest_jobs DROP COLUMN IF EXISTS source_identity;
-- ALTER TABLE public.ingest_jobs DROP COLUMN IF EXISTS attempt;
-- ALTER TABLE public.ingest_jobs DROP COLUMN IF EXISTS heartbeat_at;
-- ALTER TABLE public.ingest_jobs DROP COLUMN IF EXISTS updated_at;
-- ============================================================================

-- Ingest job lifecycle columns & heartbeat tracking for stale job sweeper.
-- Enables detection of hung/dead Celery workers and graceful error recovery.

ALTER TABLE public.ingest_jobs ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT NOW();
ALTER TABLE public.ingest_jobs ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMPTZ;
ALTER TABLE public.ingest_jobs ADD COLUMN IF NOT EXISTS attempt INT DEFAULT 0;
ALTER TABLE public.ingest_jobs ADD COLUMN IF NOT EXISTS source_identity TEXT;

CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status_heartbeat_at
    ON public.ingest_jobs (status, heartbeat_at);
