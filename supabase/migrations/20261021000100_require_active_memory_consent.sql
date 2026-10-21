-- REVERT: MANUAL ONLY — no automatic down migration is safe.
-- This migration installs database-level consent enforcement and deletes legacy
-- pending_extractions rows that have no matching active receipt. Those queue
-- rows are intentionally discarded plaintext personal data and cannot be
-- reconstructed by reverting the schema. Before rollback, snapshot the DB and
-- separately review consent receipts, the deleted queue-row count, RLS policies,
-- triggers, function grants, and every tenant/receipt column. Restore the prior
-- policies/functions only after a security review; never disable consent checks
-- merely to make an old client work. No destructive rollback SQL is supplied.
--
-- Require an active, server-recorded consent receipt for direct authenticated
-- writes to durable user-memory tables. API-only checks are not enough because
-- Supabase exposes these tables to the browser Data API.
--
-- Keep this function in sync with services.memory_outbox.DEFAULT_CONSENT_VERSION.
CREATE OR REPLACE FUNCTION public.has_active_memory_consent(
    p_user_id uuid,
    p_tenant_id text
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = ''
AS $$
    SELECT
        p_user_id = (SELECT auth.uid())
        AND COALESCE((
            SELECT receipt.granted IS TRUE AND receipt.revoked_at IS NULL
            FROM public.memory_consent_receipts AS receipt
            WHERE receipt.user_id = p_user_id
              AND receipt.tenant_id = p_tenant_id
              AND receipt.consent_version = 'memory-v1'
            ORDER BY receipt.event_sequence DESC
            LIMIT 1
        ), FALSE);
$$;

REVOKE ALL ON FUNCTION public.has_active_memory_consent(uuid, text) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_active_memory_consent(uuid, text) TO authenticated, service_role;

-- Restrictive policies are intentional: PostgreSQL combines permissive policies
-- with OR, so a standalone owner policy must not bypass consent. Keep deletes
-- available after revocation so the user can still forget/erase existing data.
DO $$
DECLARE
    memory_table text;
BEGIN
    FOREACH memory_table IN ARRAY ARRAY[
        'guru_memories',
        'guru_core_memory',
        'guru_session_summaries',
        'canonical_memories'
    ]
    LOOP
        EXECUTE format(
            'DROP POLICY IF EXISTS memory_consent_required_insert ON public.%I',
            memory_table
        );
        EXECUTE format(
            'CREATE POLICY memory_consent_required_insert ON public.%I AS RESTRICTIVE FOR INSERT TO authenticated WITH CHECK (public.has_active_memory_consent(user_id, tenant_id))',
            memory_table
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS memory_consent_required_update ON public.%I',
            memory_table
        );
        EXECUTE format(
            'CREATE POLICY memory_consent_required_update ON public.%I AS RESTRICTIVE FOR UPDATE TO authenticated USING (true) WITH CHECK (public.has_active_memory_consent(user_id, tenant_id))',
            memory_table
        );
    END LOOP;
END $$;

COMMENT ON FUNCTION public.has_active_memory_consent(uuid, text) IS
    'True only when auth.uid() owns the row and has the active memory-v1 consent receipt for that tenant; used by restrictive RLS write policies.';

-- Queue rows also contain plaintext conversation data. Scope the legacy queue to
-- the same tenant as the user's consent receipt and prevent direct queue writes
-- after consent is revoked. Existing rows are assigned the historical default
-- tenant and are discarded by the worker if no matching active receipt exists.
ALTER TABLE public.pending_extractions
    ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT 'oneness';
ALTER TABLE public.pending_extractions
    ADD COLUMN IF NOT EXISTS consent_receipt_id uuid
    REFERENCES public.memory_consent_receipts(id) ON DELETE SET NULL;

-- Only attach queued text to the receipt active when the job was created.
-- Jobs predating the current grant are deleted rather than revived by re-consent.
WITH latest AS (
    SELECT DISTINCT ON (user_id, tenant_id, consent_version)
           user_id, tenant_id, consent_version, id, granted, revoked_at, created_at
    FROM public.memory_consent_receipts
    ORDER BY user_id, tenant_id, consent_version, event_sequence DESC
)
UPDATE public.pending_extractions AS pending
SET consent_receipt_id = latest.id
FROM latest
WHERE pending.consent_receipt_id IS NULL
  AND pending.status IN ('pending', 'processing')
  AND pending.user_id = latest.user_id
  AND pending.tenant_id = latest.tenant_id
  AND latest.consent_version = 'memory-v1'
  AND latest.granted IS TRUE
  AND latest.revoked_at IS NULL
  AND pending.created_at >= latest.created_at;

-- Queue rows without proof of consent are plaintext personal data, not useful
-- work; discard them instead of reprocessing under a later consent grant.
DELETE FROM public.pending_extractions
WHERE status IN ('pending', 'processing')
  AND consent_receipt_id IS NULL;

CREATE INDEX IF NOT EXISTS pending_extractions_user_tenant_receipt_idx
    ON public.pending_extractions (user_id, tenant_id, consent_receipt_id);

-- Atomic SKIP LOCKED leasing prevents overlapping cron invocations from
-- extracting/inserting the same queued conversation at the same time.
ALTER TABLE public.pending_extractions
    ADD COLUMN IF NOT EXISTS locked_at timestamptz,
    ADD COLUMN IF NOT EXISTS locked_by text;

CREATE OR REPLACE FUNCTION public.claim_pending_extractions(
    p_worker_id text,
    p_limit integer DEFAULT 50
)
RETURNS SETOF public.pending_extractions
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $claim_pending_extractions$
BEGIN
    IF NULLIF(pg_catalog.btrim(p_worker_id), '') IS NULL THEN
        RAISE EXCEPTION 'worker_id_required' USING ERRCODE = '22023';
    END IF;

    RETURN QUERY
    WITH candidates AS (
        SELECT pending.id
        FROM public.pending_extractions AS pending
        WHERE pending.status = 'pending'
           OR (
               pending.status = 'processing'
               AND (
                   pending.locked_at IS NULL
                   OR pending.locked_at < pg_catalog.now() - interval '10 minutes'
               )
           )
        ORDER BY pending.created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(COALESCE(p_limit, 50), 100))
    ), claimed AS (
        UPDATE public.pending_extractions AS pending
        SET status = 'processing',
            attempts = pending.attempts + 1,
            locked_at = pg_catalog.now(),
            locked_by = p_worker_id
        FROM candidates
        WHERE pending.id = candidates.id
        RETURNING pending.*
    )
    SELECT * FROM claimed;
END;
$claim_pending_extractions$;

REVOKE ALL ON FUNCTION public.claim_pending_extractions(text, integer)
    FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.claim_pending_extractions(text, integer)
    TO service_role;

DROP POLICY IF EXISTS memory_consent_required_insert ON public.pending_extractions;
CREATE POLICY memory_consent_required_insert
    ON public.pending_extractions AS RESTRICTIVE
    FOR INSERT TO authenticated
    WITH CHECK (public.has_active_memory_consent(user_id, tenant_id));

DROP POLICY IF EXISTS memory_consent_required_update ON public.pending_extractions;
CREATE POLICY memory_consent_required_update
    ON public.pending_extractions AS RESTRICTIVE
    FOR UPDATE TO authenticated
    USING (true)
    WITH CHECK (public.has_active_memory_consent(user_id, tenant_id));

-- RLS does not constrain service_role clients used by backend APIs and Edge
-- Functions. This trigger is the final write boundary for every durable-memory
-- writer, regardless of client role. FOR SHARE serializes a write against a
-- concurrent consent revoke/update so the write cannot race past revocation.
-- Serialize consent events and memory writes under the same per-user,
-- per-tenant advisory transaction lock. A row-level FOR SHARE on an older
-- grant does not serialize against an appended revocation event.
CREATE OR REPLACE FUNCTION public.serialize_memory_consent_receipt_mutation()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $memory_consent_receipt_lock$
DECLARE
    v_user_id uuid;
    v_tenant_id text;
BEGIN
    IF TG_OP = 'DELETE' THEN
        v_user_id := OLD.user_id;
        v_tenant_id := OLD.tenant_id;
    ELSE
        v_user_id := NEW.user_id;
        v_tenant_id := NEW.tenant_id;
    END IF;

    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            v_user_id::text || '|' || v_tenant_id || '|memory-v1',
            0
        )
    );

    -- The BIGSERIAL default fires before BEFORE INSERT triggers. Reassign while
    -- holding the lock so sequence order also reflects serialized event order.
    IF TG_OP = 'INSERT' THEN
        NEW.event_sequence := pg_catalog.nextval(
            pg_catalog.pg_get_serial_sequence(
                'public.memory_consent_receipts', 'event_sequence'
            )::regclass
        );
        RETURN NEW;
    ELSIF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;

    -- Consent history is append-only: change state by appending a new event.
    RAISE EXCEPTION 'consent receipts are immutable; append a new consent event'
        USING ERRCODE = '42501';
END;
$memory_consent_receipt_lock$;

REVOKE ALL ON FUNCTION public.serialize_memory_consent_receipt_mutation()
    FROM PUBLIC, anon, authenticated;

DROP TRIGGER IF EXISTS serialize_memory_consent_receipt_mutation
    ON public.memory_consent_receipts;
CREATE TRIGGER serialize_memory_consent_receipt_mutation
    BEFORE INSERT OR UPDATE OR DELETE ON public.memory_consent_receipts
    FOR EACH ROW EXECUTE FUNCTION public.serialize_memory_consent_receipt_mutation();

CREATE OR REPLACE FUNCTION public.enforce_active_memory_consent_before_write()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = ''
AS $memory_consent_write$
DECLARE
    v_active boolean;
    v_tenant_id text;
BEGIN
    -- Some legacy personal-projection tables use UUID tenant ids, while the
    -- shared consent ledger intentionally uses text tenant ids. Read the row
    -- value through JSON to avoid casting failures on either schema.
    v_tenant_id := NULLIF(pg_catalog.btrim(to_jsonb(NEW)->>'tenant_id'), '');
    IF v_tenant_id = '00000000-0000-0000-0000-000000000000' THEN
        -- This UUID is the historical default used by the legacy personal
        -- projection tables; it represents the configured legacy tenant.
        v_tenant_id := 'oneness';
    END IF;

    -- Queue workers must be able to update status/lease metadata and scrub
    -- sensitive payloads after consent has been withdrawn. No identity, tenant,
    -- receipt, or non-empty payload mutation is allowed on this cleanup path.
    IF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'memory_outbox' THEN
        IF NEW.user_id IS NOT DISTINCT FROM OLD.user_id
           AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
           AND NEW.consent_receipt_id IS NOT DISTINCT FROM OLD.consent_receipt_id
           AND (NEW.payload IS NOT DISTINCT FROM OLD.payload OR NEW.payload = '{}'::jsonb) THEN
            RETURN NEW;
        END IF;
    ELSIF TG_OP = 'UPDATE' AND TG_TABLE_NAME = 'pending_extractions' THEN
        IF NEW.user_id IS NOT DISTINCT FROM OLD.user_id
           AND NEW.tenant_id IS NOT DISTINCT FROM OLD.tenant_id
           AND NEW.consent_receipt_id IS NOT DISTINCT FROM OLD.consent_receipt_id
           AND (NEW.payload IS NOT DISTINCT FROM OLD.payload OR NEW.payload = '{}'::jsonb) THEN
            RETURN NEW;
        END IF;
    END IF;

    IF NEW.user_id IS NULL OR v_tenant_id IS NULL THEN
        RAISE EXCEPTION 'user and tenant are required for memory writes'
            USING ERRCODE = '42501';
    END IF;

    -- The matching consent-event trigger takes this same lock before inserting
    -- a grant/revocation. The two transactions therefore have a serial order.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            NEW.user_id::text || '|' || v_tenant_id || '|memory-v1',
            0
        )
    );

    SELECT receipt.granted IS TRUE AND receipt.revoked_at IS NULL
    INTO v_active
    FROM public.memory_consent_receipts AS receipt
    WHERE receipt.user_id = NEW.user_id
      AND receipt.tenant_id = v_tenant_id
      AND receipt.consent_version = 'memory-v1'
    ORDER BY receipt.event_sequence DESC
    LIMIT 1;

    IF NOT COALESCE(v_active, FALSE) THEN
        RAISE EXCEPTION 'active memory consent required for user and tenant'
            USING ERRCODE = '42501';
    END IF;

    RETURN NEW;
END;
$memory_consent_write$;

REVOKE ALL ON FUNCTION public.enforce_active_memory_consent_before_write()
    FROM PUBLIC, anon, authenticated;

DO $memory_consent_trigger$
DECLARE
    memory_table text;
    tenant_data_type text;
BEGIN
    FOREACH memory_table IN ARRAY ARRAY[
        'guru_memories',
        'guru_core_memory',
        'guru_session_summaries',
        'canonical_memories',
        'pending_extractions',
        'memory_outbox',
        'user_personas',
        'user_skills',
        'user_scene_blocks',
        'user_episodes',
        'user_profiles',
        'conversation_memories',
        'memory_compaction_snapshots',
        'canonical_memory_compaction_snapshots',
        'canonical_memory_events',
        'memory_audit_events'
    ]
    LOOP
        IF to_regclass(format('public.%I', memory_table)) IS NULL THEN
            CONTINUE;
        END IF;
        -- Some existing personal-projection tables deliberately use UUID tenant
        -- columns with the all-zero UUID as their legacy default. Preserve those
        -- schemas; forcing the text tenant name "oneness" into a UUID column
        -- makes the migration fail before any consent trigger is installed.
        EXECUTE format(
            'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT ''oneness''',
            memory_table
        );
        SELECT column_info.data_type
          INTO tenant_data_type
          FROM information_schema.columns AS column_info
         WHERE column_info.table_schema = 'public'
           AND column_info.table_name = memory_table
           AND column_info.column_name = 'tenant_id';

        IF tenant_data_type IN ('text', 'character varying') THEN
            EXECUTE format(
                'ALTER TABLE public.%I ALTER COLUMN tenant_id SET DEFAULT ''oneness''',
                memory_table
            );
        ELSIF tenant_data_type = 'uuid' THEN
            -- Retain the table's UUID default. The trigger maps only the
            -- documented all-zero legacy sentinel to the text consent tenant.
            NULL;
        ELSE
            RAISE EXCEPTION 'Unsupported tenant_id type on public.%: %',
                memory_table, tenant_data_type;
        END IF;

        EXECUTE format(
            'DROP TRIGGER IF EXISTS enforce_memory_consent_before_write ON public.%I',
            memory_table
        );
        EXECUTE format(
            'CREATE TRIGGER enforce_memory_consent_before_write BEFORE INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.enforce_active_memory_consent_before_write()',
            memory_table
        );
    END LOOP;
END $memory_consent_trigger$;
