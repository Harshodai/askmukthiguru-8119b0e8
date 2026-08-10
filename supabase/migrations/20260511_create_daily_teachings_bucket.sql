-- ============================================================================
-- REVERT: Drop the three storage policies and (optionally) the bucket itself
-- Manual undo for this migration. Review by a human before running in prod;
-- never auto-revert. See docs/runbooks/MIGRATION_ROLLBACK.md.
-- ============================================================================

-- REVERT: <undo SQL> (comment block; do not execute without review)
-- ----------------------------------------------------------------------------
-- NOTE: later migrations (20260715000000, 20260724054031) drop/replace some of
-- these policy names — the DROP IF EXISTS above is safe regardless of order.
-- DELETE FROM storage.objects WHERE bucket_id = 'daily-teachings';
-- DELETE FROM storage.buckets WHERE id = 'daily-teachings';
-- -- CAUTION: bucket deletion is destructive to all teaching images.
-- ============================================================================

-- Create the daily-teachings storage bucket for admin teaching uploads
INSERT INTO storage.buckets (id, name, public)
VALUES ('daily-teachings', 'daily-teachings', true)
ON CONFLICT (id) DO NOTHING;

-- Allow anyone to read (public bucket for images)
CREATE POLICY "Public read access for daily teachings"
  ON storage.objects FOR SELECT
  USING (bucket_id = 'daily-teachings');

-- Allow authenticated users to upload (admin check is enforced in the app layer)
CREATE POLICY "Authenticated users can upload teachings"
  ON storage.objects FOR INSERT
  WITH CHECK (
    bucket_id = 'daily-teachings'
    AND auth.role() = 'authenticated'
  );

-- Allow authenticated users to delete their uploads
CREATE POLICY "Authenticated users can delete teachings"
  ON storage.objects FOR DELETE
  USING (
    bucket_id = 'daily-teachings'
    AND auth.role() = 'authenticated'
  );
