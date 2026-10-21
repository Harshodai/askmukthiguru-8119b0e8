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
BEGIN
    -- The matching consent-event trigger takes this same lock before inserting
    -- a grant/revocation. The two transactions therefore have a serial order.
    PERFORM pg_catalog.pg_advisory_xact_lock(
        pg_catalog.hashtextextended(
            NEW.user_id::text || '|' || NEW.tenant_id || '|memory-v1',
            0
        )
    );

    SELECT receipt.granted IS TRUE AND receipt.revoked_at IS NULL
    INTO v_active
    FROM public.memory_consent_receipts AS receipt
    WHERE receipt.user_id = NEW.user_id
      AND receipt.tenant_id = NEW.tenant_id
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
        'conversation_memories'
    ]
    LOOP
        IF to_regclass(format('public.%I', memory_table)) IS NULL THEN
            CONTINUE;
        END IF;
        -- Older derived-memory tables did not all carry tenant_id. Add a
        -- deterministic legacy default, then make every future write explicit
        -- or use the same default tenant contract.
        EXECUTE format(
            'ALTER TABLE public.%I ADD COLUMN IF NOT EXISTS tenant_id TEXT NOT NULL DEFAULT ''oneness''',
            memory_table
        );
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

