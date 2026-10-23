-- Provenance for memory consent receipts.
--
-- An auto-created default grant (`active_consent(auto_grant_default=True)`) must
-- be auditable and distinguishable from a seeker's explicit opt-in. Existing
-- rows predate the distinction and were written by the explicit consent
-- endpoints, so the default backfills them as `user_explicit`.

ALTER TABLE public.memory_consent_receipts
    ADD COLUMN IF NOT EXISTS source text NOT NULL DEFAULT 'user_explicit';

ALTER TABLE public.memory_consent_receipts
    DROP CONSTRAINT IF EXISTS memory_consent_receipts_source_check;

ALTER TABLE public.memory_consent_receipts
    ADD CONSTRAINT memory_consent_receipts_source_check
    CHECK (source IN ('user_explicit', 'auto_default'));
