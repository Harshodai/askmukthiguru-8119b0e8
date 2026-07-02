-- Migration: Create staging_quality_queue table for quality staging
CREATE TABLE IF NOT EXISTS public.staging_quality_queue (
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  source_url text NOT NULL,
  content_preview text NOT NULL,
  quality_score integer NOT NULL,
  fail_reasons text[] NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  reviewer_notes text NOT NULL DEFAULT '',
  content_hash text,
  created_at timestamptz NOT NULL DEFAULT now(),
  reviewed_at timestamptz,
  reviewed_by uuid REFERENCES auth.users(id)
);

ALTER TABLE public.staging_quality_queue ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Allow read access to anyone" ON public.staging_quality_queue;
CREATE POLICY "Allow read access to anyone" ON public.staging_quality_queue
  FOR SELECT USING (true);

DROP POLICY IF EXISTS "Allow write access to authenticated users" ON public.staging_quality_queue;
CREATE POLICY "Allow write access to authenticated users" ON public.staging_quality_queue
  FOR ALL TO authenticated USING (true);

GRANT SELECT ON public.staging_quality_queue TO authenticated, anon;
GRANT ALL ON public.staging_quality_queue TO service_role;
