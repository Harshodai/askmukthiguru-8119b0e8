-- Ingest job tracking table for distributed Celery pipeline.
-- Tracks each ingestion job from pending → running → completed/failed.
-- Used by celery_config.update_job_progress() for real-time progress.

CREATE TABLE IF NOT EXISTS ingest_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_url TEXT NOT NULL,
    source_type VARCHAR(20) DEFAULT 'video',
    status VARCHAR(20) DEFAULT 'pending'
        CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    progress_pct INT DEFAULT 0
        CHECK (progress_pct >= 0 AND progress_pct <= 100),
    chunks_indexed INT DEFAULT 0,
    error_message TEXT,
    worker_id VARCHAR(50),
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Index for active job queries
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_status ON ingest_jobs (status);
CREATE INDEX IF NOT EXISTS idx_ingest_jobs_created_at ON ingest_jobs (created_at DESC);

-- RLS: service role full access, anon read-only
ALTER TABLE ingest_jobs ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Service role full access on ingest_jobs"
    ON ingest_jobs FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

CREATE POLICY "Anon read-only on ingest_jobs"
    ON ingest_jobs FOR SELECT
    TO anon
    USING (true);
