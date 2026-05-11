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
