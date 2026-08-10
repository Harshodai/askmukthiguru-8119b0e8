-- ============================================================================
-- REVERT: Drop the partial unique index. NOTE: reverting allows multiple concurrent
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- active courses per user again (the race this migration closes) — only revert
-- with the app-side guard in place.
-- DROP INDEX IF EXISTS idx_user_course_progress_one_active;
-- ============================================================================

-- Enforce at most one active healing course per user at the database level.
--
-- assign_course_if_needed() (backend/services/healing_course_service.py) does
-- a check-then-upsert: SELECT for an existing active course, then upsert a
-- new row if none was found. That's not atomic under concurrent requests
-- (e.g. two browser tabs both passing the "no active course" check before
-- either upsert commits), so two different courses could both end up
-- status='active' for the same user.
--
-- This partial unique index makes the database the source of truth: a
-- second concurrent write to status='active' for the same user violates the
-- constraint and fails. assign_course_if_needed's existing try/except
-- around the upsert already logs and returns None on any DB error, so a
-- constraint violation degrades to "assignment skipped" rather than
-- crashing the request — no application code change needed.
CREATE UNIQUE INDEX IF NOT EXISTS idx_user_course_progress_one_active
  ON public.user_course_progress (user_id)
  WHERE status = 'active';
