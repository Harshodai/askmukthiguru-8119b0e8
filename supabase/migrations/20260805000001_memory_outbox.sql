CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS public.memory_consent_receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id text NOT NULL DEFAULT 'default',
    consent_version text NOT NULL,
    granted boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    revoked_at timestamptz,
    UNIQUE (user_id, tenant_id, consent_version)
);

CREATE INDEX IF NOT EXISTS idx_memory_consent_receipts_user_tenant
    ON public.memory_consent_receipts (user_id, tenant_id, consent_version);

CREATE TABLE IF NOT EXISTS public.memory_outbox (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id text NOT NULL DEFAULT 'default',
    session_id text NOT NULL,
    payload jsonb NOT NULL,
    consent_receipt_id uuid REFERENCES public.memory_consent_receipts(id) ON DELETE SET NULL,
    status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'done', 'failed')),
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    locked_at timestamptz,
    locked_by text,
    created_at timestamptz NOT NULL DEFAULT now(),
    processed_at timestamptz,
    error text
);

CREATE INDEX IF NOT EXISTS idx_memory_outbox_status_created
    ON public.memory_outbox (status, created_at);
CREATE INDEX IF NOT EXISTS idx_memory_outbox_user_tenant
    ON public.memory_outbox (user_id, tenant_id, created_at DESC);

CREATE TABLE IF NOT EXISTS public.memory_deletion_receipts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id uuid NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id text NOT NULL DEFAULT 'default',
    deleted_at timestamptz NOT NULL DEFAULT now(),
    store_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
    status text NOT NULL DEFAULT 'completed'
        CHECK (status IN ('completed', 'partial_failure')),
    error text
);

CREATE INDEX IF NOT EXISTS idx_memory_deletion_receipts_user_tenant
    ON public.memory_deletion_receipts (user_id, tenant_id, deleted_at DESC);

ALTER TABLE public.memory_consent_receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_outbox ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.memory_deletion_receipts ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "Users can read own memory consent receipts" ON public.memory_consent_receipts;
CREATE POLICY "Users can read own memory consent receipts"
    ON public.memory_consent_receipts FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can read own memory outbox rows" ON public.memory_outbox;
CREATE POLICY "Users can read own memory outbox rows"
    ON public.memory_outbox FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own memory outbox rows" ON public.memory_outbox;
CREATE POLICY "Users can delete own memory outbox rows"
    ON public.memory_outbox FOR DELETE TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can read own memory deletion receipts" ON public.memory_deletion_receipts;
CREATE POLICY "Users can read own memory deletion receipts"
    ON public.memory_deletion_receipts FOR SELECT TO authenticated
    USING (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.claim_memory_outbox(
    p_worker_id text,
    p_limit integer DEFAULT 50
)
RETURNS SETOF public.memory_outbox
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = public
AS $$
BEGIN
    RETURN QUERY
    WITH candidates AS (
        SELECT id
        FROM public.memory_outbox
        WHERE status = 'pending'
           OR (status = 'processing' AND locked_at < now() - interval '10 minutes')
        ORDER BY created_at
        FOR UPDATE SKIP LOCKED
        LIMIT GREATEST(1, LEAST(p_limit, 100))
    ), claimed AS (
        UPDATE public.memory_outbox AS outbox
        SET status = 'processing',
            attempts = outbox.attempts + 1,
            locked_at = now(),
            locked_by = p_worker_id,
            error = NULL
        FROM candidates
        WHERE outbox.id = candidates.id
        RETURNING outbox.*
    )
    SELECT * FROM claimed;
END;
$$;

REVOKE ALL ON FUNCTION public.claim_memory_outbox(text, integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.claim_memory_outbox(text, integer) TO service_role;

COMMENT ON TABLE public.memory_outbox IS
    'Durable, consented memory extraction intents; payloads are deleted on account-wide erasure.';
