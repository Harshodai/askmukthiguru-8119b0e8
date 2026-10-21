-- Consent is an event history, not a mutable single-row flag.
-- The old UNIQUE(user_id, tenant_id, consent_version) forced upsert() to
-- overwrite earlier grants/revocations. active_consent now reads the newest
-- event, so retain one immutable row per explicit consent transition.
ALTER TABLE public.memory_consent_receipts
    DROP CONSTRAINT IF EXISTS memory_consent_receipts_user_id_tenant_id_consent_version_key;

-- Use a database-generated monotonic ordering key so two consent transitions
-- with identical timestamps cannot be ordered by a random UUID.
ALTER TABLE public.memory_consent_receipts
    ADD COLUMN IF NOT EXISTS event_sequence BIGSERIAL;

CREATE INDEX IF NOT EXISTS idx_memory_consent_receipts_latest
    ON public.memory_consent_receipts
       (user_id, tenant_id, consent_version, event_sequence DESC);

-- Keep the configured legacy tenant ID unchanged. TenantContext uses
-- settings.default_tenant_id ("oneness" by default); keep SQL column defaults
-- aligned with that legacy tenant so snapshots and queued memory remain visible.
-- Tenant normalization is intentionally not inferred from a user's app metadata.
 
-- Bind legacy queued work to the currently active receipt before the new
-- worker starts requiring receipt identity. Never attach a revoked grant.
WITH latest AS (
    SELECT DISTINCT ON (user_id, tenant_id, consent_version)
           user_id, tenant_id, consent_version, id, granted, revoked_at
    FROM public.memory_consent_receipts
    ORDER BY user_id, tenant_id, consent_version, event_sequence DESC
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
  AND latest.revoked_at IS NULL
  -- A later grant must never retroactively authorize text queued before it.
  AND outbox.created_at >= latest.created_at;

-- Any legacy pending row without an active receipt is not safe to process.
UPDATE public.memory_outbox
SET status = 'failed',
    payload = '{}'::jsonb,
    processed_at = now(),
    error = 'Consent receipt missing or inactive during consent-history migration',
    locked_at = NULL,
    locked_by = NULL
WHERE consent_receipt_id IS NULL
  AND status IN ('pending', 'processing');

COMMENT ON TABLE public.memory_consent_receipts IS
    'Append-only memory consent events. The most recent event per user, tenant, and policy version determines active consent.';

-- Canonical memory facts and their partial uniqueness rule must be tenant-local.
-- The old index accidentally allowed only one active fact_key per user across
-- all tenants, and the old RPC looked up/superseded by user_id alone.
DROP INDEX IF EXISTS public.idx_canonical_memories_active_fact_key;
CREATE UNIQUE INDEX IF NOT EXISTS idx_canonical_memories_active_fact_key
    ON public.canonical_memories (user_id, tenant_id, fact_key)
    WHERE fact_key IS NOT NULL AND status = 'active';

CREATE OR REPLACE FUNCTION public.upsert_canonical_memory(
    p_user_id                UUID,
    p_tenant_id              TEXT,
    p_memory_type            TEXT,
    p_statement              TEXT,
    p_normalized_statement   TEXT,
    p_fact_key               TEXT,
    p_confidence             REAL,
    p_importance             REAL,
    p_sensitivity            TEXT,
    p_source_conversation_id TEXT,
    p_source_turn_index      INTEGER,
    p_extraction_method      TEXT,
    p_metadata               JSONB DEFAULT '{}'
) RETURNS UUID AS $$
DECLARE
    v_existing_id UUID;
    v_new_id      UUID;
    v_old_row     RECORD;
BEGIN
    IF p_fact_key IS NOT NULL THEN
        PERFORM pg_catalog.pg_advisory_xact_lock(
            pg_catalog.hashtextextended(
                p_user_id::text || '|' || p_tenant_id || '|' || p_fact_key, 0
            )
        );
        SELECT id INTO v_existing_id
        FROM public.canonical_memories
        WHERE user_id = p_user_id
          AND tenant_id = p_tenant_id
          AND fact_key = p_fact_key
          AND status = 'active'
        LIMIT 1;

        IF v_existing_id IS NOT NULL THEN
            SELECT * INTO v_old_row
            FROM public.canonical_memories
            WHERE id = v_existing_id
              AND user_id = p_user_id
              AND tenant_id = p_tenant_id;

            UPDATE public.canonical_memories
            SET status = 'superseded',
                valid_to = now(),
                version = version + 1
            WHERE id = v_existing_id
              AND user_id = p_user_id
              AND tenant_id = p_tenant_id;

            INSERT INTO public.memory_audit_events
                (user_id, memory_id, action, old_state, new_state)
            VALUES (p_user_id, v_existing_id, 'superseded', to_jsonb(v_old_row), NULL);
        END IF;
    END IF;

    INSERT INTO public.canonical_memories (
        user_id, tenant_id, memory_type, statement, normalized_statement,
        fact_key, confidence, importance, sensitivity, status,
        source_conversation_id, source_turn_index, extraction_method,
        evidence_count, valid_from, metadata
    ) VALUES (
        p_user_id, p_tenant_id, p_memory_type, p_statement, p_normalized_statement,
        p_fact_key, p_confidence, p_importance, p_sensitivity, 'active',
        p_source_conversation_id, p_source_turn_index, p_extraction_method,
        1, now(), p_metadata
    ) RETURNING id INTO v_new_id;

    INSERT INTO public.memory_audit_events (user_id, memory_id, action, new_state)
    VALUES (
        p_user_id, v_new_id, 'created',
        (SELECT to_jsonb(cm) FROM public.canonical_memories cm WHERE cm.id = v_new_id)
    );
    RETURN v_new_id;
END;
$$ LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp;

REVOKE EXECUTE ON FUNCTION public.upsert_canonical_memory(
    UUID, TEXT, TEXT, TEXT, TEXT, TEXT, REAL, REAL, TEXT, TEXT, INTEGER, TEXT, JSONB
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.upsert_canonical_memory(
    UUID, TEXT, TEXT, TEXT, TEXT, TEXT, REAL, REAL, TEXT, TEXT, INTEGER, TEXT, JSONB
) TO service_role;

-- Attribute surviving historical audit events to the tenant that owned the
-- referenced memory. Rows for already-erased memories remain NULL and are
-- exported as legacy, unattributed events instead of falsely assigning a tenant.
ALTER TABLE public.canonical_memory_events
    ADD COLUMN IF NOT EXISTS tenant_id text;

UPDATE public.canonical_memory_events AS event
SET tenant_id = memory.tenant_id
FROM public.canonical_memories AS memory
WHERE event.tenant_id IS NULL
  AND event.memory_id = memory.id
  AND event.user_id = memory.user_id;

CREATE INDEX IF NOT EXISTS canonical_memory_events_user_tenant_created_idx
    ON public.canonical_memory_events (user_id, tenant_id, created_at DESC);

-- The writer's documented MERGED event was absent from the database CHECK,
-- making valid consolidation audit writes fail despite memory mutations.
ALTER TABLE public.canonical_memory_events
    DROP CONSTRAINT IF EXISTS canonical_memory_events_event_type_check;
ALTER TABLE public.canonical_memory_events
    ADD CONSTRAINT canonical_memory_events_event_type_check
    CHECK (event_type IN (
        'CREATED', 'UPDATED', 'DELETED', 'SUPERSEDED', 'EXPIRED', 'RESTORED', 'MERGED'
    ));

-- Consolidation snapshots are durable rollback state and must exist, be
-- tenant-scoped, and be owner-readable. They are not an in-memory best effort.
CREATE TABLE IF NOT EXISTS public.canonical_memory_compaction_snapshots (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id text NOT NULL DEFAULT 'oneness',
    memories_json text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS canonical_memory_compaction_snapshots_user_tenant_created_idx
    ON public.canonical_memory_compaction_snapshots (user_id, tenant_id, created_at DESC);
ALTER TABLE public.canonical_memory_compaction_snapshots ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS own_canonical_memory_compaction_snapshots_select
    ON public.canonical_memory_compaction_snapshots;
CREATE POLICY own_canonical_memory_compaction_snapshots_select
    ON public.canonical_memory_compaction_snapshots FOR SELECT TO authenticated
    USING (auth.uid() = user_id);
GRANT SELECT, INSERT, UPDATE, DELETE ON public.canonical_memory_compaction_snapshots TO service_role;
GRANT SELECT ON public.canonical_memory_compaction_snapshots TO authenticated;
