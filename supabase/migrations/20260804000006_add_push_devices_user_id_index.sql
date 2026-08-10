-- ============================================================================
-- REVERT: Index only — drop it
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- DROP INDEX IF EXISTS idx_push_devices_user_id_active;
-- ============================================================================

-- P1-DB-10: push_devices(user_id, active) composite index.
-- push_service.py filters .eq("active", True) and optionally .eq("user_id", user_id)
-- to fan out pushes; the only existing index is push_devices_uq_token (platform, token),
-- so every send does a full-table scan. Columns verified against
-- 20260713000000_create_push_devices.sql (user_id uuid, active boolean).

CREATE INDEX IF NOT EXISTS idx_push_devices_user_id_active
  ON public.push_devices(user_id, active);

-- EXPLAIN verification deferred to CI/prod (no local Supabase); the global
-- "send to all active devices" fan-out filters on active only and will fall
-- back to a seq scan, which is acceptable for the push payload sizes involved.
