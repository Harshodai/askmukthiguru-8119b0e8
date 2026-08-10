-- ============================================================================
-- REVERT: Restore the table grants. CAUTION: re-granting re-opens the grant-layer
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- exposure this migration closed (admin-only RLS policies remain the gate) —
-- only revert as part of a deliberate rollback.
-- GRANT ALL ON public.router_decisions TO anon;
-- GRANT ALL ON public.router_decisions TO authenticated;
-- ============================================================================

-- CRIT-3: Revoke anon GRANT on router_decisions.
--
-- The original migration (20260626062100) granted ALL to anon, authenticated
-- and service_role. The harden migration (20260715000000) dropped the
-- permissive SELECT/INSERT policies and made them admin-only, but NEVER
-- revoked the anon GRANT. RLS currently masks the exposure, but the standing
-- table grant is a policy-regression away from re-opening.
--
-- authenticated gets NO grant: the backend writes this telemetry table via
-- service_role (RLS bypass), the SELECT/INSERT policies are admin-only, and
-- no user-facing read path exists (verified — the admin UI reads
-- chat_queries, not router_decisions). A plain authenticated SELECT grant
-- would itself be a grant-layer smell.
--
-- service_role access is intentionally left intact (backend telemetry sink).
--
-- Idempotent: REVOKE from a role that already lacks the grant is a no-op.
REVOKE ALL ON public.router_decisions FROM anon;

-- authenticated gets the same treatment: it too holds a standing GRANT ALL
-- (from the original migration), and no user-facing read/write path exists.
-- The backend writes this telemetry table via service_role (RLS bypass) and
-- the SELECT/INSERT policies are admin-only. Leaving authenticated with a
-- table grant would be the same grant-layer smell the anon revoke fixes.
-- service_role access is intentionally left intact (backend telemetry sink).
REVOKE ALL ON public.router_decisions FROM authenticated;

-- Force reload of PostgREST schema cache so permission changes apply immediately
NOTIFY pgrst, 'reload schema';
