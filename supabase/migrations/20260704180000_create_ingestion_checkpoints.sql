-- Ingestion checkpoints table to track processed chunks/transcripts across distributed workers.
-- Used as a fallback tier if Redis is unreachable in containerized environments.

CREATE TABLE IF NOT EXISTS public.ingestion_checkpoints (
    chunk_id TEXT PRIMARY KEY,
    tenant_id TEXT NOT NULL DEFAULT 'default',
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast tenant-based check
CREATE INDEX IF NOT EXISTS idx_ingestion_checkpoints_tenant ON public.ingestion_checkpoints (tenant_id);

-- Enable RLS
ALTER TABLE public.ingestion_checkpoints ENABLE ROW LEVEL SECURITY;

-- Policies for service_role and SELECT access
CREATE POLICY "Service role full access on ingestion_checkpoints"
    ON public.ingestion_checkpoints FOR ALL
    TO service_role
    USING (true) WITH CHECK (true);

