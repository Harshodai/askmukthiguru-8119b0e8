-- P0 release safety: database-level idempotency and single-active invariants.
-- This migration intentionally fails rather than deleting duplicate history.
-- Run the duplicate audit first and quarantine any conflicting rows.

CREATE UNIQUE INDEX IF NOT EXISTS uq_source_releases_identity_checksum
    ON public.source_releases (corpus_id, source_identity, content_checksum);

CREATE UNIQUE INDEX IF NOT EXISTS uq_source_releases_one_active
    ON public.source_releases (corpus_id, source_identity)
    WHERE status = 'active';

COMMENT ON INDEX public.uq_source_releases_identity_checksum IS
    'Prevents duplicate source releases when ingestion retries the same checksum.';
COMMENT ON INDEX public.uq_source_releases_one_active IS
    'Guarantees one active release per corpus/source; activation remains advisory-lock serialized.';
