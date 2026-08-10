-- ============================================================================
-- REVERT: Restore the two dropped storage policies (originally from 20260511)
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- CAUTION: re-allows any authenticated user to upload/delete teaching images
-- (app-layer admin check is the only gate) — revert only deliberately.
-- CREATE POLICY "Authenticated users can upload teachings" ON storage.objects
--   FOR INSERT WITH CHECK (bucket_id = 'daily-teachings' AND auth.role() = 'authenticated');
-- CREATE POLICY "Authenticated users can delete teachings" ON storage.objects
--   FOR DELETE USING (bucket_id = 'daily-teachings' AND auth.role() = 'authenticated');
-- ============================================================================

DROP POLICY IF EXISTS "Authenticated users can upload teachings" ON storage.objects;
DROP POLICY IF EXISTS "Authenticated users can delete teachings" ON storage.objects;