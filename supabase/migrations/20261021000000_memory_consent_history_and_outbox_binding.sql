-- Consent is an event history, not a mutable single-row flag.
-- The old UNIQUE(user_id, tenant_id, consent_version) forced upsert() to
-- overwrite earlier grants/revocations. active_consent now reads the newest
-- event, so retain one immutable row per explicit consent transition.
ALTER TABLE public.memory_consent_receipts
    DROP CONSTRAINT IF EXISTS memory_consent_receipts_user_id_tenant_id_consent_version_key;

CREATE INDEX IF NOT EXISTS idx_memory_consent_receipts_latest
    ON public.memory_consent_receipts
       (user_id, tenant_id, consent_version, created_at DESC, id DESC);

-- Bind legacy queued work to the currently active receipt before the new
-- worker starts requiring receipt identity. Never attach a revoked grant.
WITH latest AS (
    SELECT DISTINCT ON (user_id, tenant_id, consent_version)
           user_id, tenant_id, consent_version, id, granted, revoked_at
    FROM public.memory_consent_receipts
    ORDER BY user_id, tenant_id, consent_version, created_at DESC, id DESC
)
UPDATE public.memory_outbox AS outbox
SET consent_receipt_id = latest.id
FROM latest
WHERE outbox.consent_receipt_id IS NULL
  AND outbox.status IN ('pending', 'processing')
  AND outbox.user_id = latest.user_id
  AND outbox.tenant_id = latest.tenant_id
  AND latest.consent_version = 'memory-v1'
  AND latest.granted IS TRUE
  AND latest.revoked_at IS NULL;

-- Any legacy pending row without an active receipt is not safe to process.
UPDATE public.memory_outbox
SET status = 'failed',
    processed_at = now(),
    error = 'Consent receipt missing or inactive during consent-history migration'
WHERE consent_receipt_id IS NULL
  AND status IN ('pending', 'processing');

COMMENT ON TABLE public.memory_consent_receipts IS
    'Append-only memory consent events. The most recent event per user, tenant, and policy version determines active consent.';
