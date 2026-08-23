-- Fix: the raw-text ingestion idempotency check accepted an idempotency_key
-- parameter but never actually compared it to anything stored -- it only
-- filtered ingest_jobs by source_url, so a single successful job for a URL
-- blocked all future reprocessing of that URL forever, regardless of content
-- changes or target collection. Adds the column the app code already sends
-- so the comparison in app/api/ingest.py can actually be meaningful.
ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS idempotency_key TEXT;

CREATE INDEX IF NOT EXISTS idx_ingest_jobs_idempotency_key
    ON ingest_jobs (idempotency_key)
    WHERE idempotency_key IS NOT NULL;
