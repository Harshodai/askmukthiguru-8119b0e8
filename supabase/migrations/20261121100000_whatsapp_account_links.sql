-- ==============================================================================
-- Migration: 20261121100000_whatsapp_account_links.sql
-- Description: Schema and RLS policies for WhatsApp account linking, two-channel
--              cryptographic challenges, and DPDP-compliant consent separation.
-- ==============================================================================

-- 1. WhatsApp Account Links
CREATE TABLE IF NOT EXISTS public.whatsapp_account_links (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    tenant_id TEXT NOT NULL DEFAULT 'oneness',
    phone_number_hash TEXT NOT NULL UNIQUE,
    phone_number_masked TEXT NOT NULL,
    phone_number_encrypted TEXT,
    status TEXT NOT NULL CHECK (status IN ('active', 'revoked', 'unlinked')) DEFAULT 'active',
    sync_history_consent BOOLEAN NOT NULL DEFAULT false,
    memory_write_consent BOOLEAN NOT NULL DEFAULT false,
    linked_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    revoked_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now())
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_account_links_user_id
    ON public.whatsapp_account_links(user_id);

CREATE INDEX IF NOT EXISTS idx_whatsapp_account_links_phone_hash
    ON public.whatsapp_account_links(phone_number_hash);

-- Enable RLS
ALTER TABLE public.whatsapp_account_links ENABLE ROW LEVEL SECURITY;

-- RLS Policies for authenticated users
DROP POLICY IF EXISTS whatsapp_account_links_select ON public.whatsapp_account_links;
CREATE POLICY whatsapp_account_links_select
    ON public.whatsapp_account_links
    FOR SELECT
    TO authenticated
    USING (auth.uid() = user_id);

DROP POLICY IF EXISTS whatsapp_account_links_update ON public.whatsapp_account_links;
CREATE POLICY whatsapp_account_links_update
    ON public.whatsapp_account_links
    FOR UPDATE
    TO authenticated
    USING (auth.uid() = user_id)
    WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS whatsapp_account_links_delete ON public.whatsapp_account_links;
CREATE POLICY whatsapp_account_links_delete
    ON public.whatsapp_account_links
    FOR DELETE
    TO authenticated
    USING (auth.uid() = user_id);

-- Service role bypass for backend orchestrator
GRANT ALL ON TABLE public.whatsapp_account_links TO service_role;
GRANT SELECT, UPDATE, DELETE ON TABLE public.whatsapp_account_links TO authenticated;


-- 2. WhatsApp Link Challenges (Time-bounded single-use tokens)
CREATE TABLE IF NOT EXISTS public.whatsapp_link_challenges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    challenge_token_hash TEXT NOT NULL UNIQUE,
    phone_number_hash TEXT NOT NULL,
    phone_number_masked TEXT NOT NULL,
    phone_number_raw TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT timezone('utc', now()),
    expires_at TIMESTAMPTZ NOT NULL,
    consumed_at TIMESTAMPTZ,
    confirmed_whatsapp BOOLEAN NOT NULL DEFAULT false,
    confirmed_web_user_id UUID REFERENCES auth.users(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_whatsapp_link_challenges_token_hash
    ON public.whatsapp_link_challenges(challenge_token_hash);

CREATE INDEX IF NOT EXISTS idx_whatsapp_link_challenges_phone_hash
    ON public.whatsapp_link_challenges(phone_number_hash);

-- Enable RLS
ALTER TABLE public.whatsapp_link_challenges ENABLE ROW LEVEL SECURITY;

-- Service role only for challenges (prevent token enumeration)
GRANT ALL ON TABLE public.whatsapp_link_challenges TO service_role;
