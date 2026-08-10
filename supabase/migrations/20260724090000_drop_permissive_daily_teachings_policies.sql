-- ============================================================================
-- REVERT: Restore the two dropped SELECT policies. CAUTION: "Public can read teachings"
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- re-opens anon read of ALL teachings (no expiry filter) — restore only as part
-- of a deliberate rollback.
-- CREATE POLICY "Public can read teachings" ON public.daily_teachings FOR SELECT USING (true);
-- CREATE POLICY "daily_teachings_public" ON public.daily_teachings FOR SELECT USING (true);
-- ============================================================================

DROP POLICY IF EXISTS "Public can read teachings" ON public.daily_teachings;
DROP POLICY IF EXISTS "daily_teachings_public" ON public.daily_teachings;

NOTIFY pgrst, 'reload schema';
