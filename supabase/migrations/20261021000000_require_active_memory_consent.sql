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
        AND EXISTS (
            SELECT 1
            FROM public.memory_consent_receipts AS receipt
            WHERE receipt.user_id = p_user_id
              AND receipt.tenant_id = p_tenant_id
              AND receipt.consent_version = 'memory-v1'
              AND receipt.granted = TRUE
              AND receipt.revoked_at IS NULL
        );
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
