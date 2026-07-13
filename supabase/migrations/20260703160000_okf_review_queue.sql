-- Create OKF Review Queue Table
CREATE TABLE IF NOT EXISTS okf_review_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    entry_json JSONB NOT NULL,
    source_video_id TEXT,
    source_video_title TEXT,
    guru_slug TEXT DEFAULT 'default',
    status TEXT DEFAULT 'pending', -- pending, approved, rejected, edited
    reviewer_notes TEXT,
    submitted_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by UUID
);

-- Enable RLS
ALTER TABLE okf_review_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins have full access to okf_review_queue"
    ON okf_review_queue
    FOR ALL
    TO authenticated
    USING (public.has_role(auth.uid(), 'admin'::public.app_role))
    WITH CHECK (public.has_role(auth.uid(), 'admin'::public.app_role));
